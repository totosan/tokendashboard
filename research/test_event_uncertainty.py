import csv
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from research.event_uncertainty import (
    analyze, daily_totals, describe, load_events, percentile, sampled_mean, utc_days,
)


class EventUncertaintyTests(unittest.TestCase):
    def test_percentile_interpolates(self):
        self.assertEqual(percentile([0, 10], 0.25), 2.5)
        self.assertIsNone(percentile([], 0.5))

    def test_empty_days_are_retained(self):
        totals = daily_totals([{"day": "2026-10-17", "gross_bps": 6}], ["2026-10-17", "2026-10-18"])
        self.assertEqual(totals, [(1, 6), (0, 0)])
        self.assertIsNone(sampled_mean(totals, [1, 1]))
        self.assertEqual(sampled_mean(totals, [0, 1]), 6)

    def test_event_weighted_not_day_weighted(self):
        self.assertEqual(sampled_mean([(2, 20), (1, 40)], [0, 1]), 20)

    def test_empty_cell_is_explicit_not_zero_return(self):
        result = describe([], ["2026-10-17"], [[0], [0]])
        self.assertEqual(result["n_events"], 0)
        self.assertIsNone(result["mean_gross_bps"])
        self.assertEqual(result["day_block_bootstrap_95pct_mean_gross_bps"], [None, None])
        self.assertEqual(result["bootstrap_empty_replicates"], 2)

    def test_constant_returns_and_cost_shift(self):
        events = [
            {"day": day, "gross_bps": 6, "symbol": "BTCUSDT", "entry_time_utc": day}
            for day in ("2026-10-17", "2026-10-18")
        ]
        result = describe(events, ["2026-10-17", "2026-10-18"], [[0, 1], [1, 1]])
        self.assertEqual(result["day_block_bootstrap_95pct_mean_gross_bps"], [6, 6])
        self.assertEqual(result["cost_sensitivity"]["12"]["day_block_bootstrap_95pct_mean_net_bps"], [-6, -6])

    def test_synchronized_difference_and_determinism(self):
        summary = {
            "granularity": "5m", "range_start_utc": "2026-10-15T00:00:00Z",
            "development_oos_split_utc": "2026-10-17T00:00:00Z",
            "range_end_utc_exclusive": "2026-10-19T00:00:00Z",
        }
        events = [
            {
                "day": day, "gross_bps": value, "symbol": "BTCUSDT", "entry_time_utc": day,
                "period": "out_of_sample", "group": "BTC_ETH", "side": "long", "strategy": strategy,
            }
            for day, value in (("2026-10-17", 6), ("2026-10-18", -3))
            for strategy in ("dashboard_breakout", "three_close_momentum_baseline")
        ]
        first = analyze(events, summary, replicates=100)
        self.assertEqual(first, analyze(events, summary, replicates=100))
        cell = next(row for row in first["results"] if row["period"] == "out_of_sample" and row["group"] == "BTC_ETH" and row["side"] == "long")
        self.assertEqual(cell["synchronized_day_bootstrap_95pct_difference_bps"], [0, 0])

    def test_rejects_non_midnight_bounds(self):
        with self.assertRaises(ValueError):
            utc_days(datetime(2026, 10, 17, 1, tzinfo=timezone.utc), datetime(2026, 10, 18, tzinfo=timezone.utc))

    def test_rejects_duplicate_wrong_period_gap_and_nonfinite(self):
        summary = {
            "granularity": "5m", "range_start_utc": "2026-10-16T00:00:00Z",
            "development_oos_split_utc": "2026-10-17T00:00:00Z",
            "range_end_utc_exclusive": "2026-10-18T00:00:00Z",
            "symbols": ["BTCUSDT"], "tradfi_symbols": [],
        }
        row = {
            "symbol": "BTCUSDT", "side": "long", "strategy": "dashboard_breakout",
            "signal_time_utc": "2026-10-16T23:55:00Z", "entry_time_utc": "2026-10-17T00:00:00Z",
            "period": "out_of_sample", "gross_bps": "6",
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "events.csv"
            def write(rows):
                with path.open("w", newline="") as output:
                    writer = csv.DictWriter(output, fieldnames=row)
                    writer.writeheader()
                    writer.writerows(rows)
            write([row])
            self.assertEqual(len(load_events(path, summary)), 1)
            for rows in (
                [row, row], [{**row, "period": "development"}],
                [{**row, "signal_time_utc": "2026-10-16T23:50:00Z"}],
                [{**row, "gross_bps": "nan"}],
            ):
                write(rows)
                with self.assertRaises(ValueError):
                    load_events(path, summary)


if __name__ == "__main__":
    unittest.main()
