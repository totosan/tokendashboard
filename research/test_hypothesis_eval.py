import unittest

from research.hypothesis_eval import (
    completed_higher_timeframe_context,
    segments,
    box_retest_signal,
    vwap_by_bar,
)
from research.intraday_eval import BAR_MS, momentum_signal


def candle(timestamp, opened=100, high=101, low=99, closed=100, volume=10):
    return {
        "timestamp": timestamp, "symbol": "TESTUSDT", "open": opened, "high": high,
        "low": low, "close": closed, "base_volume": volume, "quote_volume": volume * 100,
    }


class CausalityAndCadenceTests(unittest.TestCase):
    def test_gap_starts_a_new_base_run_and_momentum_does_not_cross_it(self):
        bars = [candle(i * BAR_MS, closed=100 + i) for i in range(3)]
        bars.append(candle(4 * BAR_MS, closed=104))
        runs = segments(bars, BAR_MS)
        self.assertEqual([len(run) for run in runs], [3, 1])
        self.assertFalse(momentum_signal([bars[1], bars[2], bars[3]], "long"))

    def test_htf_context_appears_only_after_twentieth_complete_bin(self):
        base_ms, higher_ms = 60 * 60_000, 4 * 60 * 60_000
        bars = [candle(i * base_ms, closed=100 + i / 10) for i in range(80)]
        context = completed_higher_timeframe_context(bars, base_ms, higher_ms)
        # The close at 79h is one hour before bin 20 completes; it cannot see bin 20.
        self.assertIsNone(context[78 * base_ms])
        # The final hourly candle closes exactly at 80h, so all 20 bins are now known.
        self.assertIsNotNone(context[79 * base_ms])

    def test_incomplete_higher_timeframe_bin_is_not_used(self):
        base_ms, higher_ms = 60 * 60_000, 4 * 60 * 60_000
        bars = [candle(i * base_ms) for i in range(79)]
        context = completed_higher_timeframe_context(bars, base_ms, higher_ms)
        self.assertIsNone(context[78 * base_ms])

    def test_missing_htf_bin_resets_ema_warmup(self):
        base_ms, higher_ms = 60 * 60_000, 4 * 60 * 60_000
        bars = [candle(i * base_ms) for i in range(80) if i not in (40,)]
        context = completed_higher_timeframe_context(bars, base_ms, higher_ms)
        # The missing hour invalidates the 40-44h bin and resets the run after it.
        self.assertIsNone(context[79 * base_ms])

    def test_completed_missing_bin_invalidates_previous_warmed_context(self):
        base_ms, higher_ms = 60 * 60_000, 4 * 60 * 60_000
        bars = [candle(i * base_ms) for i in range(88) if i != 81]
        context = completed_higher_timeframe_context(bars, base_ms, higher_ms)
        self.assertIsNotNone(context[79 * base_ms])
        self.assertIsNone(context[83 * base_ms])
        self.assertIsNone(context[84 * base_ms])

    def test_vwap_requires_complete_session_from_midnight(self):
        import math

        base_ms = 60 * 60_000
        bars = [candle(i * base_ms) for i in (0, 1, 3, 4, 24, 25)]
        values = vwap_by_bar(bars, base_ms)
        self.assertEqual(values[:2], [100, 100])
        self.assertTrue(all(math.isnan(value) for value in values[2:4]))
        self.assertEqual(values[4:], [100, 100])
        self.assertTrue(math.isnan(vwap_by_bar([candle(base_ms)], base_ms)[0]))


class RuleDirectionTests(unittest.TestCase):
    def test_momentum_baseline_long_and_short_directions(self):
        rising = [candle(i * BAR_MS, closed=100 + i) for i in range(3)]
        falling = [candle(i * BAR_MS, closed=102 - i) for i in range(3)]
        self.assertTrue(momentum_signal(rising, "long"))
        self.assertFalse(momentum_signal(rising, "short"))
        self.assertTrue(momentum_signal(falling, "short"))
        self.assertFalse(momentum_signal(falling, "long"))

    def test_box_retest_long_and_mirrored_short(self):
        bars = [candle(i * BAR_MS, opened=100, high=101, low=99, closed=100) for i in range(12)]
        bars.append(candle(12 * BAR_MS, opened=100.8, high=101.8, low=100.7, closed=101.5))
        bars.append(candle(13 * BAR_MS, opened=101.5, high=101.7, low=100.95, closed=101.4))
        self.assertTrue(box_retest_signal(bars, 13, "long"))

        mirrored = [
            candle(
                row["timestamp"], opened=200 - row["open"], high=200 - row["low"],
                low=200 - row["high"], closed=200 - row["close"],
            )
            for row in bars
        ]
        self.assertTrue(box_retest_signal(mirrored, 13, "short"))


if __name__ == "__main__":
    unittest.main()
