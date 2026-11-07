import copy
import unittest
from decimal import Decimal

from research.budget_chd_study import book_readiness, compare_candles, parse_ms, replay_book, trade_study


def trade(identity=1, stamp=0, **changes):
    return {
        "trade_id": identity, "trade_time": stamp, "received_time": (stamp + 2) * 10**6,
        "symbol": "AAPLUSDT", "price": "10", "quantity": "2",
        "is_buyer_maker": False, **changes,
    }


class BudgetStudyTests(unittest.TestCase):
    def test_half_open_window_and_unknown_empty_minutes(self):
        result = trade_study([trade(), trade(2, 120000)], "AAPLUSDT", 0, 120000)
        self.assertEqual(result["unique_observed_trades"], 1)
        self.assertEqual(result["outside_window_trades"], 1)
        self.assertEqual(result["minute_bars"][0]["base_volume"], "2")
        self.assertNotIn("base_volume", result["minute_bars"][1])
        self.assertEqual(result["minute_bars"][0]["available_not_before_receive_ns"], 60_000_000_000)

    def test_stable_event_order_vwap_profile_conservation(self):
        rows = [trade(2, 2, price="12"), trade(1, 0), trade(3, 2, price="11", quantity="1")]
        result = trade_study(rows, "AAPLUSDT", 0, 60000)
        bar = result["minute_bars"][0]
        self.assertEqual((bar["open"], bar["close"], bar["high"]), ("10", "11", "12"))
        self.assertEqual(bar["quote_volume"], "55")
        self.assertEqual(bar["vwap"], "11")
        self.assertEqual(
            sum(map(Decimal, result["whole_window_profile_ex_post"]["base_volume"])),
            Decimal(result["base_volume"]),
        )

    def test_duplicates_dedup_but_conflicts_refused(self):
        result = trade_study([trade(), trade()], "AAPLUSDT", 0, 60000)
        self.assertEqual(result["identical_duplicates_removed"], 1)
        with self.assertRaisesRegex(ValueError, "Conflicting"):
            trade_study([trade(), trade(price="11")], "AAPLUSDT", 0, 60000)

    def test_invalid_values_and_types_refused(self):
        for changes in [
            {"price": "NaN"}, {"quantity": "-1"}, {"symbol": "OTHER"},
            {"trade_time": 1.5}, {"trade_id": True}, {"is_buyer_maker": "false"},
        ]:
            with self.subTest(changes=changes), self.assertRaises((ValueError, ArithmeticError)):
                trade_study([trade(**changes)], "AAPLUSDT", 0, 60000)
        with self.assertRaises(ValueError):
            trade_study([], "AAPLUSDT", 0, 60000)
        with self.assertRaises(ValueError):
            trade_study([trade()], "AAPLUSDT", 1, 60000)

    def test_late_receive_prevents_premature_availability(self):
        bar = trade_study([trade(received_time=90_000_000_000)], "AAPLUSDT", 0, 60000)["minute_bars"][0]
        self.assertEqual(bar["available_not_before_receive_ns"], 90_000_000_000)

    def test_exact_candle_comparison_and_difference_not_adjusted(self):
        report = trade_study([trade(i, i * 60000) for i in range(5)], "AAPLUSDT", 0, 300000)
        candle = {
            "timestamp": "0", "symbol": "AAPLUSDT", "open": "10", "high": "10",
            "low": "10", "close": "10", "base_volume": "10", "quote_volume": "100",
        }
        self.assertEqual(compare_candles(report, [candle])["comparisons"][0]["status"], "EXACT_MATCH")
        original = copy.deepcopy(report)
        candle["base_volume"] = "11"
        result = compare_candles(report, [candle])["comparisons"][0]
        self.assertEqual(result["status"], "DIFFERENCES")
        self.assertEqual(result["trade_minus_saved_candle"]["base_volume"], "-1")
        self.assertEqual(report, original)

    def test_partial_candle_is_not_compared_as_full(self):
        report = trade_study([trade()], "AAPLUSDT", 0, 60000)
        result = compare_candles(report, [{"timestamp": "0", "symbol": "AAPLUSDT"}])
        self.assertEqual(result["comparisons"][0]["status"], "INSUFFICIENT_OBSERVATIONS")

    def test_book_audit_not_replay_claim(self):
        row = {"symbol": "AAPLUSDT", "event_type": "update", "received_time": 1,
               "final_update_id": 100, "prev_final_update_id": None}
        result = book_readiness([row, row], "AAPLUSDT")
        self.assertEqual(result["status"], "NOT_REPLAY_READY")
        self.assertEqual(result["updates_without_chain_fields"], 1)
        snapshot = {**row, "event_type": "snapshot", "received_time": 0}
        result = book_readiness([snapshot, {**row, "prev_final_update_id": 90}], "AAPLUSDT")
        self.assertEqual(result["status"], "CANDIDATE_REQUIRES_REPLAY")

    def test_explicit_timezone(self):
        self.assertEqual(parse_ms("1970-01-01T00:00:00Z"), 0)
        with self.assertRaises(ValueError):
            parse_ms("2026-09-17T14:00:00")

    def test_replay_snapshot_replace_delete_and_gap_recovery(self):
        def row(seq, prev, event="update", side="bid", price="10", quantity="2"):
            return {"symbol": "AAPLUSDT", "received_time": seq, "event_time": seq,
                    "event_type": event, "final_update_id": seq, "prev_final_update_id": prev,
                    "side": side, "price": price, "quantity": quantity}

        initial = [row(100, None, "snapshot"), row(100, None, "snapshot", "ask", "11")]
        report, state = replay_book(initial + [row(105, 100, quantity="3")], "AAPLUSDT")
        self.assertEqual(report["status"], "SEQUENCE_CONSISTENT_SAMPLE")
        self.assertEqual(state["bids"], [["10", "3"]])
        report, state = replay_book(initial + [row(105, 99)], "AAPLUSDT")
        self.assertIsNone(state)
        self.assertEqual(report["gap_or_cross_events"], 1)
        report, state = replay_book(initial + [row(105, None)], "AAPLUSDT")
        self.assertIsNone(state)
        report, state = replay_book(
            initial + [row(105, 100, quantity="0"), row(106, 105, price="9")], "AAPLUSDT")
        self.assertEqual(state["bids"], [["9", "2"]])
        report, state = replay_book(
            initial + [row(105, 99), row(110, None, "snapshot", "noop", "0", "0")],
            "AAPLUSDT")
        self.assertEqual(state["bids"], [])
        self.assertEqual(state["asks"], [])
        self.assertIsNone(report["last_valid_quote"])

    def test_replay_requires_snapshot_rejects_bad_order_and_crossing(self):
        base = {"symbol": "AAPLUSDT", "received_time": 1, "event_time": 1,
                "event_type": "update", "final_update_id": 1, "prev_final_update_id": None,
                "side": "bid", "price": "10", "quantity": "1"}
        report, state = replay_book([base], "AAPLUSDT")
        self.assertIsNone(state)
        self.assertEqual(report["quoted_message_states"], 0)
        snapshot_after = {**base, "received_time": 2, "event_time": 2,
                          "final_update_id": 2, "event_type": "snapshot"}
        ask_after = {**snapshot_after, "side": "ask", "price": "11"}
        report, state = replay_book([base, snapshot_after, ask_after], "AAPLUSDT")
        self.assertIsNotNone(state)
        self.assertEqual(report["status"], "REPLAY_HAS_UNVERIFIED_INTERVALS")
        snapshot = {**base, "event_type": "snapshot"}
        ask = {**snapshot, "side": "ask", "price": "9"}
        report, state = replay_book([snapshot, ask], "AAPLUSDT")
        self.assertIsNone(state)
        with self.assertRaisesRegex(ValueError, "backward"):
            replay_book([snapshot, {**snapshot, "received_time": 0}], "AAPLUSDT")
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            replay_book([snapshot, snapshot], "AAPLUSDT")


if __name__ == "__main__":
    unittest.main()
