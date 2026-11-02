import base64
import copy
import json
import unittest
from decimal import Decimal
from unittest.mock import patch
from urllib.error import URLError

from research.trade_pagination import END_MS, START_MS, ProbeError, digest
from research.trade_profile_window import Client, MAX_REQUESTS, PARAMETERS, profile, run


def payload(ids=("100", "99"), prices=("10", "20")):
    return {"code": "00000", "data": [
        {"tradeId": i, "symbol": "AAPLUSDT", "ts": str(START_MS),
         "price": prices[n % len(prices)], "size": "1"}
        for n, i in enumerate(ids)
    ]}


class FakeClient:
    def __init__(self, evidence, pages):
        self.evidence, self.pages = evidence, iter(pages)

    def fetch(self, parameters, page):
        record = {"parameters": copy.deepcopy(parameters)}
        self.evidence["requests"].append(record)
        return next(self.pages), record


class Reply:
    code = 200

    def __init__(self, raw):
        self.raw = raw

    def geturl(self):
        return "https://api.bitget.com/api/v2/mix/market/fills-history"

    def read(self, limit):
        return self.raw[:limit]

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class WindowTests(unittest.TestCase):
    def execute(self, pages):
        evidence = {"requests": []}
        run(FakeClient(evidence, pages), evidence)
        return evidence

    def test_terminal_and_cursor(self):
        e = self.execute([payload(), payload(("98",)), {"code": "00000", "data": []}])
        self.assertEqual(e["status"], "ENDPOINT_COMPLETE")
        self.assertFalse(e["trade_ledger_complete"])
        self.assertEqual(e["verified_unique_trades"], 3)
        self.assertEqual(e["requests"][1]["parameters"]["idLessThan"], "99")
        self.assertEqual(e["requests"][2]["parameters"]["idLessThan"], "98")
        self.assertNotIn("idLessThan", e["requests"][0]["parameters"])
        self.assertIsNotNone(e["profile"])
        self.assertEqual(e["candle_comparison"]["status"], "MISSING_EVIDENCE")

    def test_empty_first_page_has_no_profile(self):
        e = self.execute([{"code": "00000", "data": []}])
        self.assertTrue(e["endpoint_complete"])
        self.assertIsNone(e["profile"])

    def test_short_page_does_not_prove_exhaustion(self):
        pages = [payload((str(100 - i),)) for i in range(MAX_REQUESTS)]
        e = self.execute(pages)
        self.assertEqual(e["status"], "TRUNCATED")
        self.assertFalse(e["endpoint_complete"])
        self.assertIsNone(e["profile"])
        self.assertEqual(len(e["requests"]), MAX_REQUESTS)

    def test_duplicate_order_cursor_and_bad_empty(self):
        cases = [
            [payload(), payload(("99",))],
            [payload(("99", "100"))],
            [payload(), payload(("101",))],
            [{"code": "40000", "data": []}],
            [{"code": "00000", "data": None}],
        ]
        for pages in cases:
            with self.subTest(pages=pages):
                e = self.execute(pages)
                self.assertEqual(e["status"], "TRUNCATED")
                self.assertIsNone(e["profile"])

    def test_window_boundaries_and_temporal_order(self):
        for ts, valid in ((START_MS - 1, False), (START_MS, True),
                          (END_MS - 1, True), (END_MS, False)):
            p = payload(("100",))
            p["data"][0]["ts"] = str(ts)
            e = self.execute([p, {"code": "00000", "data": []}])
            self.assertEqual(e["endpoint_complete"], valid)
        p = payload()
        p["data"][1]["ts"] = str(START_MS + 1)
        self.assertFalse(self.execute([p])["endpoint_complete"])
        first, second = payload(("100",)), payload(("99",))
        second["data"][0]["ts"] = str(START_MS + 1)
        self.assertFalse(self.execute([first, second])["endpoint_complete"])

    def test_client_budget_and_error(self):
        client = Client({"requests": [{}] * MAX_REQUESTS})
        with patch.object(client.opener, "open") as opened:
            with self.assertRaises(ProbeError):
                client.fetch(PARAMETERS, 1)
            opened.assert_not_called()
        e = {"requests": []}
        client = Client(e)
        with patch.object(client.opener, "open", side_effect=URLError("offline")):
            run(client, e)
        self.assertEqual(len(e["requests"]), 1)
        self.assertIn("error", e["requests"][0])
        self.assertEqual(e["status"], "TRUNCATED")

    def test_raw_bytes_hash_parameters_and_timeout(self):
        raw = json.dumps(payload()).encode()
        e = {"requests": []}
        client = Client(e)
        parameters = dict(PARAMETERS)
        with patch.object(client.opener, "open", return_value=Reply(raw)) as opened:
            response, record = client.fetch(parameters, 1)
        opened.assert_called_once()
        self.assertEqual(opened.call_args.kwargs["timeout"], 10)
        self.assertEqual(response, payload())
        self.assertEqual(base64.b64decode(record["raw_response_base64"]), raw)
        self.assertEqual(record["raw_response_sha256"], digest(raw))
        parameters["idLessThan"] = "1"
        self.assertNotIn("idLessThan", record["parameters"])
        self.assertIn("finished_utc", record)
        with patch.object(client.opener, "open", side_effect=TimeoutError("deadline")):
            run(client, e)
        self.assertEqual(e["status"], "TRUNCATED")
        self.assertEqual(len(e["requests"]), 2)

    def test_capped_and_invalid_bodies_are_preserved(self):
        for raw in (b"x" * 32, b"not-json"):
            e = {"requests": []}
            client = Client(e)
            with patch("research.trade_profile_window.MAX_BYTES", 32):
                with patch.object(client.opener, "open", return_value=Reply(raw)):
                    run(client, e)
            self.assertEqual(e["status"], "TRUNCATED")
            self.assertIsNone(e["profile"])
            self.assertEqual(base64.b64decode(e["requests"][0]["raw_response_base64"]), raw)


class ProfileTests(unittest.TestCase):
    def test_bins_boundaries_conservation_and_tie(self):
        rows = [{"price": str(i), "size": "1"} for i in range(1, 22)]
        p = profile(rows)
        self.assertEqual(list(map(Decimal, p["base_volume"])), [Decimal(1)] * 19 + [Decimal(2)])
        self.assertEqual(p["poc_bin"], 19)
        self.assertEqual(p["value_area_bins_inclusive"], [6, 19])
        self.assertEqual(Decimal(p["total_base_volume"]), Decimal(21))
        tied = profile([{"price": "1", "size": "1"}, {"price": "21", "size": "1"}])
        self.assertEqual(tied["poc_bin"], 0)
        self.assertEqual(tied["value_area_bins_inclusive"], [0, 19])

    def test_value_area_adjacent_tie_chooses_lower(self):
        rows = [{"price": str(p), "size": str(s)}
                for p, s in ((1, 1), (21, 1), (10, 4), (9, 2), (11, 2))]
        self.assertEqual(profile(rows)["value_area_bins_inclusive"], [8, 10])

    def test_flat(self):
        p = profile([{"price": "5", "size": "2"}, {"price": "5", "size": "3"}])
        self.assertEqual(p["base_volume"][0], "5")
        self.assertEqual(p["value_area_bins_inclusive"], [0, 0])
        self.assertEqual(p["bin_edges"], ["5"] * 21)

    def test_empty_zero_nonfinite(self):
        with self.assertRaises(ProbeError):
            profile([])
        for field in ("price", "size"):
            for value in ("0", "-1", "NaN", "Infinity", "-Infinity", "bad", None):
                row = {"price": "1", "size": "1", field: value}
                with self.subTest(field=field, value=value), self.assertRaises(ProbeError):
                    profile([row])


if __name__ == "__main__":
    unittest.main()
