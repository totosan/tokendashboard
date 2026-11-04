import unittest
from decimal import Decimal
from fractions import Fraction

from research.rolling_profile_comparison import (
    BAR_MS,
    END_MS,
    START_MS,
    WINDOW_MS,
    _node_scores,
    _profile,
    build_report,
    evaluate_window,
)


def fixture_sources():
    trades, bars = [], {}
    for index, stamp in enumerate(range(START_MS, END_MS, BAR_MS)):
        opened = Decimal("100") + Decimal(index) / 10
        prices = (opened, opened + 2, opened - 1, opened + Decimal("0.5"))
        for offset, price in enumerate(prices, 1):
            trade_time = stamp + offset * 1000
            trades.append({
                "trade_id": index * 10 + offset,
                "trade_time": trade_time,
                "event_time": trade_time,
                "received_time": trade_time * 1_000_000 + 10_000_000,
                "price": price,
                "quantity": Decimal(1),
                "is_buyer_maker": False,
                "order_type": "market",
                "receive_hour_object": "fixture",
            })
        bars[stamp] = {
            "timestamp": stamp, "open": prices[0], "high": prices[1],
            "low": prices[2], "close": prices[3], "base_volume": Decimal(4),
        }
    return trades, bars


class RollingProfileTests(unittest.TestCase):
    def test_all_frozen_windows_and_transitions_are_retained(self):
        trades, bars = fixture_sources()
        report = build_report(
            trades, bars, {}, {}, {}, generated_utc="2026-11-04T00:00:00+00:00",
        )
        self.assertEqual(report["status"], "DESCRIPTIVE_APPROXIMATION_COMPARISON")
        self.assertEqual(report["window_summary"]["planned_windows"], 10)
        self.assertEqual(report["window_summary"]["comparable_windows"], 10)
        self.assertEqual(len(report["windows"]), 10)
        self.assertEqual(len(report["profile_change_transitions"]), 9)
        replay = build_report(
            trades, bars, {}, {}, {}, generated_utc="2026-11-05T00:00:00+00:00",
        )
        self.assertNotEqual(report["generated_utc"], replay["generated_utc"])
        self.assertEqual(report["payload_sha256"], replay["payload_sha256"])
        for window in report["windows"]:
            self.assertEqual(window["status"], "COMPARABLE")
            self.assertTrue(window["profiles"]["candle_distribution_volume_conserved"])
            self.assertEqual(
                sum(map(Decimal, window["profiles"]["trade_at_price"]["bin_base_volume"])),
                Decimal(window["trade_coverage"]["asof_base_volume"]),
            )

    def test_half_open_event_time_and_strict_receive_cutoff(self):
        trades, bars = fixture_sources()
        start = START_MS
        end = START_MS + WINDOW_MS
        # A trade exactly at the left edge is included.
        left_edge = {
            **trades[0], "trade_time": start, "event_time": start,
            "received_time": end * 1_000_000 - 1,
        }
        # Event time exactly at the right edge is excluded.
        right_edge = {
            **trades[-1], "trade_time": end, "event_time": end,
            "received_time": end * 1_000_000 - 1,
        }
        # A pre-boundary event received exactly at the cutoff is unavailable.
        late = {
            **trades[1], "trade_time": end - 1, "event_time": end - 1,
            "received_time": end * 1_000_000,
        }
        result, _ = evaluate_window(
            [left_edge, right_edge, late],
            {stamp: bars[stamp] for stamp in range(start, end, BAR_MS)},
            start, end,
        )
        self.assertEqual(result["trade_coverage"]["event_time_observations"], 2)
        self.assertEqual(result["trade_coverage"]["asof_available_observations"], 1)
        self.assertEqual(result["trade_coverage"]["late_or_unavailable_observations"], 1)
        self.assertIn("LATE_EVENT_TIME_TRADES", result["reasons"])
        self.assertEqual(
            result["trade_coverage"]["receive_hour_counts"]["bitget_futures/2026-09-17/13/AAPLUSDT_trades.parquet"],
            {"asof": 0, "late_or_unavailable": 0},
        )

    def test_missing_bar_and_volume_mismatch_block_shape_comparison(self):
        trades, bars = fixture_sources()
        start, end = START_MS, START_MS + WINDOW_MS
        missing = dict(bars)
        del missing[start + BAR_MS]
        result, _ = evaluate_window(
            trades, missing, start, end,
            candle_dispositions={start + BAR_MS: "MISSING_OR_INVALID"},
        )
        self.assertEqual(result["status"], "NOT_COMPARABLE")
        self.assertIn("CANDLE_MISSING_OR_INVALID", result["reasons"])
        self.assertIsNone(result["fidelity"])

        changed = dict(bars)
        changed[start + 2 * BAR_MS] = {
            **bars[start + 2 * BAR_MS], "base_volume": Decimal(5),
        }
        result, _ = evaluate_window(trades, changed, start, end)
        self.assertIn("TRADE_CANDLE_BASE_VOLUME_MISMATCH", result["reasons"])
        self.assertIsNone(result["fidelity"])

    def test_invalid_bar_disposition_blocks_even_if_another_row_is_usable(self):
        trades, bars = fixture_sources()
        start, end = START_MS, START_MS + WINDOW_MS
        result, _ = evaluate_window(
            trades,
            {stamp: bars[stamp] for stamp in range(start, end, BAR_MS)},
            start, end,
            candle_dispositions={start + BAR_MS: "INVALID_ROW"},
        )
        self.assertEqual(result["status"], "NOT_COMPARABLE")
        self.assertIn("CANDLE_INVALID_ROW", result["reasons"])
        self.assertIsNone(result["profiles"])

    def test_ambiguous_last_millisecond_close_is_not_invented(self):
        trades, bars = fixture_sources()
        start, end = START_MS, START_MS + WINDOW_MS
        rows = [row for row in trades if start <= row["trade_time"] < end]
        final_time = max(row["trade_time"] for row in rows)
        rows.append({
            **rows[-1], "trade_id": 999_999, "price": Decimal("555"),
            "received_time": (end - 1) * 1_000_000,
        })
        result, _ = evaluate_window(
            rows, {stamp: bars[stamp] for stamp in range(start, end, BAR_MS)}, start, end,
        )
        self.assertIsNone(result["source_consistency"]["trade_close"])
        self.assertEqual(result["source_consistency"]["trade_close_status"],
                         "AMBIGUOUS_MAX_TIMESTAMP_TIE")
        self.assertIn("AMBIGUOUS_TRADE_CLOSE", result["reasons"])
        self.assertGreaterEqual(final_time, start)

    def test_poc_tie_and_value_area_expand_lower_side_first(self):
        bins = [Fraction(0) for _ in range(24)]
        bins[4], bins[5], bins[6] = Fraction(2), Fraction(5), Fraction(2)
        profile = _profile(bins, [Fraction(index) for index in range(25)])
        self.assertEqual(profile["poc_bin"], 5)
        self.assertEqual([profile["va_left"], profile["va_right"]], [4, 5])
        tied = [Fraction(0) for _ in range(24)]
        tied[3] = tied[8] = Fraction(1)
        profile = _profile(tied, [Fraction(index) for index in range(25)])
        self.assertEqual(profile["poc_bin"], 3)

    def test_empty_node_sets_have_undefined_scores(self):
        result = _node_scores([], [4])
        self.assertEqual(result["undefined"], "EMPTY_NODE_SET")
        self.assertIsNone(result["precision"])
        result = _node_scores([3, 5], [5, 6])
        self.assertEqual(result["matched"], 1)
        self.assertEqual(result["precision"], "0.5")
        self.assertEqual(result["recall"], "0.5")
        self.assertEqual(result["f1"], "0.5")


if __name__ == "__main__":
    unittest.main()
