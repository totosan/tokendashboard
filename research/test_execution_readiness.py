import copy
from dataclasses import asdict, replace
import hashlib
import io
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from research import execution_readiness as gate


I = gate.Instrument("bitget", "USDT-FUTURES", "AAPLUSDT", "USDT", "USDT", "1")
S = gate.Source("synthetic.json", hashlib.sha256(b"{}").hexdigest(), "/fixture")


def signal(**changes):
    return replace(gate.Signal(I, S, 1000, 1100, 1200, 100, "book"), **changes)


def quote(**changes):
    return replace(gate.Quote(I, S, "book", 1250, 1290, "100", "101", "2", "3"), **changes)


def fee(**changes):
    return replace(gate.Fee(I, S, "SYNTHETIC_ACCOUNT", "taker", "USDT",
                           1000, 2000, 900, "0.0006"), **changes)


def funding(at):
    return gate.Funding(I, S, at, at + 20, "-0.0001")


def holding(**changes):
    return replace(gate.Holding(I, S, "SYNTHETIC_ACCOUNT", 1300, 1500, "1"), **changes)


def synthetic_contract():
    return {
        "schema_version": 1, "mode": "SYNTHETIC_ONLY", "instrument": asdict(I),
        "window": {"start_ms": 1000, "end_ms": 2000},
        "policy": {"max_quote_age_ms": 50, "max_total_latency_ms": 300},
        "manifest_refs": [{"path": S.path, "sha256": S.sha256, "role": "fixture"}],
        "candidate": {
            "signals": [asdict(signal())], "quotes": [asdict(quote())],
            "fees": [asdict(fee())], "funding": [asdict(funding(1300))],
            "holdings": [asdict(holding())],
        },
    }


class JoinTests(unittest.TestCase):
    def test_quote_asof_boundary_and_input_order(self):
        older = quote(event_ms=1200, available_ms=1250)
        future = quote(event_ms=1301, available_ms=1301)
        unavailable = quote(event_ms=1290, available_ms=1310)
        for rows in ([older, future, quote(), unavailable],
                     [unavailable, quote(), future, older]):
            selected, reasons = gate.quote_asof(signal(), rows, 50, 300)
            self.assertEqual(selected, quote())
            self.assertEqual(reasons, [])

    def test_stale(self):
        self.assertEqual(gate.quote_asof(signal(), [quote()], 49, 300)[1], ["QUOTE_STALE"])

    def test_cross_symbol_product_source_and_currency(self):
        for other in (replace(I, symbol="BTCUSDT"), replace(I, product="COIN-FUTURES"),
                      replace(I, venue="other"), replace(I, settlement_currency="USD")):
            with self.subTest(other=other):
                self.assertIn("MISMATCH", gate.quote_asof(
                    signal(), [quote(instrument=other)], 50, 300)[1][0])
        self.assertIn("MISMATCH", gate.quote_asof(
            signal(), [quote(stream="other")], 50, 300)[1][0])

    def test_future_and_unavailable(self):
        for row in (quote(event_ms=1301, available_ms=1302), quote(available_ms=1301)):
            self.assertEqual(gate.quote_asof(signal(), [row], 50, 300)[1],
                             ["QUOTE_FUTURE_OR_UNAVAILABLE"])

    def test_missing_and_latency_limit(self):
        self.assertEqual(gate.quote_asof(signal(), [], 50, 300)[1], ["MISSING_QUOTES"])
        self.assertEqual(gate.quote_asof(signal(), [quote()], 50, 299)[1],
                         ["LATENCY_LIMIT_EXCEEDED"])

    def test_conflicting_ordering_ties(self):
        self.assertEqual(gate.quote_asof(signal(), [quote(), quote(bid="99")], 50, 300)[1],
                         ["QUOTE_ORDER_AMBIGUOUS"])
        self.assertEqual(gate.quote_asof(signal(), [quote(), quote()], 50, 300)[1], [])

    def test_signal_availability_and_clock_order(self):
        for changes in ({"available_ms": 999}, {"scan_ms": 1099},
                        {"manual_latency_ms": -1}, {"event_ms": float("nan")},
                        {"event_ms": True}, {"scan_ms": "1200"}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                signal(**changes)

    def test_invalid_prices_quantities_and_clocks(self):
        for changes in ({"bid": "NaN"}, {"ask": "Infinity"}, {"bid_quantity": "0"},
                        {"ask_quantity": "-1"}, {"bid": "102"}, {"bid": 100},
                        {"available_ms": 1249}, {"event_ms": float("inf")}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                quote(**changes)

    def test_fee_half_open_out_of_order(self):
        a = fee(end_ms=1500)
        b = fee(start_ms=1500, rate="0.0004")
        for at, expected in ((1499, a), (1500, b), (1999, b)):
            selected, reasons = gate.fee_asof([b, a], I, a.account, "taker", "USDT", at)
            self.assertEqual((selected, reasons), (expected, []))
        self.assertEqual(gate.fee_asof([a, b], I, a.account, "taker", "USDT", 2000)[1],
                         ["FEE_MISSING_OR_INAPPLICABLE"])

    def test_overlapping_fee_intervals_and_duplicates(self):
        for rows in ([fee(), fee(start_ms=1500)], [fee(), fee()]):
            self.assertEqual(gate.fee_asof(rows, I, fee().account, "taker", "USDT", 1300)[1],
                             ["FEE_INTERVAL_OVERLAP"])

    def test_fee_applicability_availability(self):
        for account, liquidity, currency in (("other", "taker", "USDT"),
                                             (fee().account, "maker", "USDT"),
                                             (fee().account, "taker", "USD")):
            self.assertEqual(gate.fee_asof([fee()], I, account, liquidity, currency, 1300)[1],
                             ["FEE_MISSING_OR_INAPPLICABLE"])
        self.assertEqual(gate.fee_asof([fee(available_ms=1400)], I, fee().account,
                                      "taker", "USDT", 1300)[1], ["FEE_FUTURE_UNAVAILABLE"])
        self.assertEqual(gate.fee_asof([fee()], I, "UNKNOWN", "taker", "USDT", 1300)[1],
                         ["ACCOUNT_UNKNOWN"])

    def test_fee_funding_nonfinite_and_empty_intervals(self):
        for create in (lambda: fee(rate="NaN"), lambda: fee(end_ms=1000),
                       lambda: replace(funding(1300), rate="Infinity"),
                       lambda: holding(exit_ms=1300), lambda: holding(quantity="0")):
            with self.assertRaises(ValueError):
                create()

    def test_exact_funding_ownership_edges_and_order(self):
        rows = [funding(1500), funding(1300), funding(1299), funding(1499)]
        selected = gate.funding_for_holding(holding(), rows)
        self.assertEqual([r.settlement_ms for r in selected], [1300, 1499])
        self.assertGreater(selected[0].available_ms, holding().entry_ms)
        # Adjacent holdings assign the shared edge once under the chosen convention.
        following = gate.funding_for_holding(holding(entry_ms=1500, exit_ms=1700), rows)
        self.assertEqual([r.settlement_ms for r in following], [1500])

    def test_funding_mismatch_and_duplicate_rejected(self):
        for rows in ([funding(1300), funding(1300)],
                     [replace(funding(1300), instrument=replace(I, symbol="BTCUSDT"))]):
            with self.assertRaises(ValueError):
                gate.funding_for_holding(holding(), rows)


class AuditTests(unittest.TestCase):
    def audit_synthetic(self, contract=None, raw=b"{}"):
        with patch.object(Path, "exists", return_value=True), \
                patch.object(gate, "read_bytes", return_value=raw):
            return gate.audit(contract or synthetic_contract())

    def test_synthetic_ready_is_explicitly_nonauthorizing(self):
        result = self.audit_synthetic()
        self.assertEqual(result["status"], "SYNTHETIC_ONLY")
        self.assertFalse(result["authorizes_execution"])
        self.assertEqual(result["actual_exchange_account_ownership"], "UNKNOWN")
        self.assertEqual(result["scenario_funding_counts"], [1])

    def test_no_self_attestation_can_authorize_real_readiness(self):
        contract = synthetic_contract()
        contract["mode"] = "EXISTING_EVIDENCE"
        result = self.audit_synthetic(contract)
        self.assertEqual(result["status"], "NOT_READY")
        self.assertIn("SOURCE_UNVERIFIED", result["reasons"])
        contract["ready"] = True
        with self.assertRaisesRegex(ValueError, "fields"):
            self.audit_synthetic(contract)

    def test_missing_inputs_and_manifests(self):
        contract = synthetic_contract()
        contract["candidate"] = {name: [] for name in contract["candidate"]}
        with patch.object(Path, "exists", return_value=False):
            result = gate.audit(contract)
        self.assertIn("MISSING_SOURCE_MANIFEST", result["reasons"])
        for name in contract["candidate"]:
            self.assertIn("MISSING_" + name.upper(), result["reasons"])

    def test_evidence_hashes_and_row_source_binding(self):
        result = self.audit_synthetic(raw=b'{"changed":true}')
        self.assertIn("EVIDENCE_HASH_MISMATCH", result["reasons"])
        self.assertEqual(result["manifest_evidence"][0]["observed_sha256"],
                         hashlib.sha256(b'{"changed":true}').hexdigest())
        contract = synthetic_contract()
        contract["candidate"]["quotes"][0]["source"]["sha256"] = "0" * 64
        self.assertIn("ROW_SOURCE_NOT_BOUND_TO_MANIFEST", self.audit_synthetic(contract)["reasons"])

    def test_schema_and_bounds(self):
        for mutate in (lambda c: c.update(schema_version=True),
                       lambda c: c["candidate"].update(quotes=[{}] * 1001),
                       lambda c: c["policy"].update(max_quote_age_ms=float("inf")),
                       lambda c: c["manifest_refs"][0].update(path="../escape.json"),
                       lambda c: c["manifest_refs"][0].update(sha256="not-a-hash"),
                       lambda c: c["candidate"]["signals"][0].update(available_ms="1100")):
            contract = synthetic_contract()
            mutate(contract)
            with self.subTest(contract=contract), self.assertRaises((ValueError, TypeError)):
                self.audit_synthetic(contract)

    def test_json_duplicate_keys_and_nonfinite(self):
        for raw in (b'{"x":NaN}', b'{"x":Infinity}', b'{"x":1,"x":2}', b'not-json'):
            with self.assertRaises(ValueError):
                gate.load_json(raw)

    def test_cli_malformed_persists_explicit_error_and_exit1(self):
        for raw in (b'not-json', b'{"x":NaN}', b'{}'):
            with patch.object(gate, "read_bytes", return_value=raw), \
                    patch.object(Path, "write_text") as write, patch("sys.stdout", new=io.StringIO()):
                code = gate.main([])
            self.assertEqual(code, 1)
            report = json.loads(write.call_args.args[0])
            self.assertEqual(report["status"], "ERROR")
            self.assertIn("error", report)

    def test_cli_synthetic_also_exit2_and_contract_hash(self):
        contract = synthetic_contract()
        raw = json.dumps(contract).encode()
        with patch.object(gate, "read_bytes", side_effect=[raw, b"{}"]), \
                patch.object(Path, "exists", return_value=True), \
                patch.object(Path, "write_text") as write, patch("sys.stdout", new=io.StringIO()):
            code = gate.main([])
        self.assertEqual(code, 2)
        report = json.loads(write.call_args.args[0])
        self.assertEqual(report["status"], "SYNTHETIC_ONLY")
        self.assertEqual(report["contract"]["sha256"], hashlib.sha256(raw).hexdigest())

    def test_cli_cannot_overwrite_input_or_evidence(self):
        raw = json.dumps(synthetic_contract()).encode()
        for output in (gate.DEFAULT_CONTRACT, S.path):
            with patch.object(gate, "read_bytes", return_value=raw), \
                    patch.object(Path, "write_text") as write, patch("sys.stderr", new=io.StringIO()):
                self.assertEqual(gate.main(["--output", output]), 1)
            write.assert_not_called()

    def test_existing_evidence_is_not_ready_and_all_hashes_match(self):
        contract = gate.load_json(gate.read_bytes(gate.ROOT / gate.DEFAULT_CONTRACT))
        result = gate.audit(copy.deepcopy(contract))
        self.assertEqual(result["status"], "NOT_READY")
        self.assertIn("BOOK_TIME_WINDOW_MISMATCH", result["reasons"])
        self.assertIn("FUNDING_HISTORICAL_SCHEDULE_SOURCE_UNVERIFIED", result["reasons"])
        self.assertTrue(all(r["status"] == "HASH_MATCH" for r in result["manifest_evidence"]))
        self.assertEqual(result["candidate_counts"]["quotes"], 0)
        self.assertLess(len(json.dumps(result)), 16000)


if __name__ == "__main__":
    unittest.main()
