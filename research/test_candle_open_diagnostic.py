import copy
import csv
import gzip
import json
import unittest
from decimal import Decimal
from pathlib import Path

from research.candle_open_diagnostic import diagnose
from research.test_budget_chd_study import trade


class CandleDiagnosticTests(unittest.TestCase):
    def fixture(self):
        rows = [dict(trade(1, 299999, price="9"), event_time=299999)]
        for i in range(5):
            stamp = 300000 + i * 60000
            rows.append(dict(trade(i + 2, stamp, price="10"), event_time=stamp))
        candles = [
            {"symbol": "AAPLUSDT", "timestamp": "0", "close": "9"},
            {"symbol": "AAPLUSDT", "timestamp": "300000", "open": "9", "high": "10",
             "low": "10", "close": "10", "base_volume": "10", "quote_volume": "100"},
        ]
        return rows, candles

    def test_continuity_open_is_not_first_trade_and_sources_unchanged(self):
        rows, candles = self.fixture()
        original = copy.deepcopy((rows, candles))
        report = diagnose(rows, candles, "AAPLUSDT", 300000, 600000)
        cell = report["five_minute_comparisons"][0]
        self.assertTrue(cell["open_equals_previous_close"])
        self.assertTrue(cell["open_equals_previous_observed_trade"])
        self.assertFalse(cell["open_equals_first_observed_trade"])
        self.assertEqual(cell["trade_minus_saved_candle"]["open"], "1")
        self.assertEqual(original, (rows, candles))

    def test_adjacent_receive_partition_contains_late_target_trade(self):
        rows, candles = self.fixture()
        rows[-1]["received_time"] = 601000 * 10**6
        report = diagnose(rows, candles, "AAPLUSDT", 300000, 600000)
        self.assertEqual(report["target_trades_received_outside_target_hour"], 1)

    def test_missing_prior_duplicate_or_missing_minute_is_explicit(self):
        rows, candles = self.fixture()
        for changed in (candles[1:], candles + [candles[1]], candles[:1]):
            with self.subTest(candles=changed), self.assertRaises(ValueError):
                diagnose(rows, changed, "AAPLUSDT", 300000, 600000)
        with self.assertRaisesRegex(ValueError, "Incomplete"):
            diagnose(rows[:-1], candles, "AAPLUSDT", 300000, 600000)

    def test_no_forced_convention_when_evidence_differs(self):
        rows, candles = self.fixture()
        candles[1]["open"] = "10"
        report = diagnose(rows, candles, "AAPLUSDT", 300000, 600000)
        self.assertIn("Mixed", report["conclusion"])

    def test_persisted_sample_against_unchanged_official_and_original_trade_report(self):
        root = Path(__file__).parent
        result = json.loads((root / "results/candle-open-diagnostic-2026-11-04.json").read_text())
        original = json.loads((root / "results/budget-trades-2026-11-03.json").read_text())
        with gzip.open(root / "data/bitget-5m-2026-09-17_2026-11-01.csv.gz", "rt") as source:
            candles = {int(row["timestamp"]): row for row in csv.DictReader(source)
                       if row["symbol"] == "AAPLUSDT"}
        old = {row["timestamp"]: row
               for row in original["saved_5m_candle_comparison"]["comparisons"]}
        self.assertEqual(len(result["five_minute_comparisons"]), 12)
        self.assertEqual(result["target_trades_received_outside_target_hour"], 0)
        self.assertEqual(result["unique_target_trades"], 1720)
        for cell in result["five_minute_comparisons"]:
            stamp = cell["timestamp"]
            self.assertEqual(cell["trade_minus_saved_candle"], old[stamp]["trade_minus_saved_candle"])
            self.assertEqual(Decimal(cell["saved_open"]), Decimal(candles[stamp]["open"]))
            self.assertEqual(Decimal(cell["saved_open"]), Decimal(candles[stamp - 300000]["close"]))
            self.assertEqual(Decimal(cell["saved_open"]), Decimal(cell["previous_observed_trade_price"]))
            self.assertNotEqual(Decimal(cell["saved_open"]), Decimal(cell["first_observed_trade_price"]))


if __name__ == "__main__":
    unittest.main()
