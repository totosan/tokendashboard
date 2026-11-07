import unittest

from research.intraday_eval import BAR_MS, breakout_signal, evaluate_event, orient


def candle(timestamp, opened, high, low, closed, volume=1000):
    return {
        "timestamp": timestamp,
        "symbol": "TESTUSDT",
        "open": opened,
        "high": high,
        "low": low,
        "close": closed,
        "base_volume": volume,
        "quote_volume": volume,
    }


class BreakoutSignalTests(unittest.TestCase):
    def setUp(self):
        self.bars = [
            candle(0, 100, 102, 99, 101),
            candle(BAR_MS, 101, 103, 100, 102),
            candle(2 * BAR_MS, 102, 105, 101, 104),
            candle(3 * BAR_MS, 104, 104.5, 103.5, 103.8),
            candle(4 * BAR_MS, 103.8, 106, 103.7, 105.5, 1200),
        ]

    def test_confirms_long_breakout(self):
        result = breakout_signal(self.bars, "long")
        self.assertIsNotNone(result)
        self.assertAlmostEqual(result["volume_ratio"], 1.2)
        self.assertGreater(result["trigger"], 104)

    def test_confirms_mirrored_short_breakout(self):
        mirrored = [
            candle(
                int(row["timestamp"]),
                200 - float(row["open"]),
                200 - float(row["low"]),
                200 - float(row["high"]),
                200 - float(row["close"]),
                int(float(row["quote_volume"])),
            )
            for row in self.bars
        ]
        self.assertIsNotNone(breakout_signal(mirrored, "short"))

    def test_rejects_insufficient_confirmation_volume(self):
        low_volume = [*self.bars[:-1], candle(4 * BAR_MS, 103.8, 106, 103.7, 105.5, 900)]
        self.assertIsNone(breakout_signal(low_volume, "long", min_volume=1.0))

    def test_rejects_time_gap(self):
        gap = [*self.bars[:3], candle(4 * BAR_MS, 104, 104.5, 103.5, 103.8), self.bars[4]]
        self.assertIsNone(breakout_signal(gap, "long"))

    def test_short_orientation_swaps_high_and_low(self):
        oriented = orient(self.bars[0], "short")
        self.assertEqual(oriented["high"], -99)
        self.assertEqual(oriented["low"], -102)

    def test_short_mfe_and_mae_use_favorable_and_adverse_extremes(self):
        bars = [
            candle(0, 100, 101, 99, 100),
            candle(BAR_MS, 100, 101, 98, 99),
        ]
        result = evaluate_event(bars, 0, "short", "test", 0)
        self.assertAlmostEqual(result["gross_bps"], 100)
        self.assertAlmostEqual(result["mfe_bps"], 200)
        self.assertAlmostEqual(result["mae_bps"], -100)

    def test_split_classifies_event_by_entry_time(self):
        bars = [
            candle(0, 100, 101, 99, 100),
            candle(BAR_MS, 100, 101, 98, 99),
        ]
        result = evaluate_event(bars, 0, "short", "test", BAR_MS)
        self.assertEqual(result["period"], "out_of_sample")


if __name__ == "__main__":
    unittest.main()
