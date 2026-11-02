import unittest
from unittest.mock import patch

from research import indicator_eval as indicator
from research import intraday_eval as existing
from research import hypothesis_eval as helpers


MS = 900_000
DAY = indicator.DAY_MS


def bars(closes, start=0, cadence=MS):
    return [
        {"timestamp": start + index * cadence, "symbol": "BTCUSDT",
         "open": close, "high": close + 1, "low": close - 1, "close": close,
         "base_volume": 1, "quote_volume": close}
        for index, close in enumerate(closes)
    ]


class IndicatorTests(unittest.TestCase):
    def test_rsi_seed_wilder_update_and_constant_cases(self):
        self.assertEqual(indicator.rsi14([100] * 14), [None] * 14)
        self.assertEqual(indicator.rsi14([100] * 16)[14:], [50, 50])
        self.assertEqual(indicator.rsi14(list(range(100, 116)))[14:], [100, 100])
        self.assertEqual(indicator.rsi14(list(range(116, 100, -1)))[14:], [0, 0])
        closes = [100 + index % 2 for index in range(15)] + [102]
        result = indicator.rsi14(closes)
        self.assertEqual(result[14], 50)
        self.assertAlmostEqual(result[15], 100 - 100 / (1 + (6.5 + 2) / 6.5))

    def test_rsi_both_directions_and_earliest_signal(self):
        for side, closes in (
            ("long", list(range(115, 100, -1)) + [115]),
            ("short", list(range(100, 115)) + [100]),
        ):
            signals = indicator.signal_arms(bars(closes), MS)
            self.assertIn((15 * MS, side, indicator.ARMS[1]), signals)
            self.assertFalse(any(stamp < 15 * MS and arm == indicator.ARMS[1]
                                 for stamp, _, arm in signals))

    def test_rsi_equality_previous_included_current_excluded(self):
        for previous, current, expected in ((30, 31, "long"), (70, 69, "short"),
                                            (29, 30, None), (71, 70, None)):
            with patch.object(indicator, "rsi14", return_value=[previous, current]):
                signals = indicator.signal_arms(bars([100, 101]), MS)
            hits = {side for _, side, arm in signals if arm == indicator.ARMS[1]}
            self.assertEqual(hits, {expected} if expected else set())

    def test_bollinger_population_warmup_and_zero_volatility(self):
        self.assertEqual(indicator.bollinger20([100] * 21), [None] * 21)
        bands = indicator.bollinger20(list(range(100, 121)))
        self.assertEqual(bands[:19], [None] * 19)
        self.assertAlmostEqual(bands[19][0], 109.5 - 2 * (33.25 ** .5))

    def test_bollinger_both_directions(self):
        for side, extreme in (("long", 80), ("short", 120)):
            signals = indicator.signal_arms(bars([100] * 19 + [extreme, 100]), MS)
            self.assertIn((20 * MS, side, indicator.ARMS[2]), signals)
            self.assertFalse(any(stamp < 20 * MS and arm == indicator.ARMS[2]
                                 for stamp, _, arm in signals))

    def test_bollinger_strict_equality_and_zero_vol_suppression(self):
        for closes, band_pair in (
            ([90, 100], [(90, 110), (90, 110)]),
            ([89, 90], [(90, 110), (90, 110)]),
            ([110, 100], [(90, 110), (90, 110)]),
            ([111, 110], [(90, 110), (90, 110)]),
            ([80, 100], [None, (90, 110)]),
        ):
            with patch.object(indicator, "bollinger20", return_value=band_pair):
                self.assertFalse(any(arm == indicator.ARMS[2]
                                     for _, _, arm in indicator.signal_arms(bars(closes), MS)))

    def test_daily_both_directions_midnight_and_equality(self):
        for side, last in (("long", 102), ("short", 98)):
            source = bars([100] * 96 + [last])
            self.assertIn((DAY, side, indicator.ARMS[0]), indicator.signal_arms(source, MS))
        for last in (99, 101):
            self.assertFalse(any(arm == indicator.ARMS[0] for _, _, arm in
                                 indicator.signal_arms(bars([100] * 96 + [last]), MS)))

    def test_missing_partial_or_nonadjacent_prior_day(self):
        full = bars([100] * 96 + [102])
        for source in (full[1:], full[:20] + full[21:],
                       full[:96] + bars([102], start=2 * DAY), bars([100, 102], start=DAY)):
            self.assertFalse(any(arm == indicator.ARMS[0]
                                 for _, _, arm in indicator.signal_arms(source, MS)))
        with self.assertRaises(ValueError):
            indicator.signal_arms(bars([100], start=1), MS)

    def test_daily_previous_equality_included_and_beyond_not_repeated(self):
        source = bars([100] * 96 + [102, 103])
        for row in source[:96]:
            row["high"] = 100
        signals = indicator.signal_arms(source, MS)
        self.assertIn((DAY, "long", indicator.ARMS[0]), signals)
        self.assertNotIn((DAY + MS, "long", indicator.ARMS[0]), signals)
        source = bars([100] * 96 + [98, 97])
        for row in source[:96]:
            row["low"] = 100
        signals = indicator.signal_arms(source, MS)
        self.assertIn((DAY, "short", indicator.ARMS[0]), signals)
        self.assertNotIn((DAY + MS, "short", indicator.ARMS[0]), signals)

    def test_cadence_is_explicit_and_never_mutates_shared_globals(self):
        original = existing.BAR_MS
        for cadence in (300_000, MS, 300_000):
            source = bars(list(range(115, 100, -1)) + [115, 100], cadence=cadence)
            self.assertTrue(indicator.collect_events(source, cadence))
            self.assertEqual(existing.BAR_MS, original)

    def test_gap_resets_rsi_bb_and_daily_context(self):
        source = bars([100] * 96 + list(range(115, 100, -1)))
        source += bars([115, 80, 100], start=source[-1]["timestamp"] + 2 * MS)
        suffix = source[-3:][0]["timestamp"]
        self.assertFalse(any(stamp >= suffix for stamp, _, _ in indicator.signal_arms(source, MS)))
        duplicate = bars([100] * 20) + bars([80, 100], start=19 * MS)
        self.assertFalse(any(arm == indicator.ARMS[2]
                             for _, _, arm in indicator.signal_arms(duplicate, MS)))

    def test_future_bar_invariance_all_arms(self):
        source = bars([100] * 96 + [102] + list(range(115, 100, -1)) + [115]
                      + [100] * 19 + [80, 100])
        before = indicator.signal_arms(source, MS)
        extended = source + bars([300, 1, 200], start=source[-1]["timestamp"] + MS)
        after = indicator.signal_arms(extended, MS)
        cutoff = source[-1]["timestamp"]
        self.assertEqual(before, {hit for hit in after if hit[0] <= cutoff})
        self.assertEqual({arm for _, _, arm in before}, set(indicator.ARMS))
        # Every prefix must agree even when it ends exactly on a signal candle.
        for length in (97, 113, len(source)):
            prefix = source[:length]
            self.assertEqual(indicator.signal_arms(prefix, MS),
                             {hit for hit in before if hit[0] <= prefix[-1]["timestamp"]})

    def test_next_bar_split_boundary_metrics_and_no_global_leak(self):
        old_cadence = existing.BAR_MS
        source = bars(list(range(115, 100, -1)) + [115, 100],
                      start=helpers.SPLIT_MS - 16 * MS)
        source[-1].update(open=100, high=103, low=98, close=101)
        events = indicator.collect_events(source, MS)
        event = next(event for event in events if event["arm"] == indicator.ARMS[1])
        self.assertEqual(event["period"], "out_of_sample")
        self.assertAlmostEqual(event["gross_bps"], 100)
        self.assertAlmostEqual(event["mfe_bps"], 300)
        self.assertAlmostEqual(event["mae_bps"], -200)
        short = existing.evaluate_event(source, 15, "short", "test", helpers.SPLIT_MS)
        self.assertAlmostEqual(short["gross_bps"], -100)
        self.assertAlmostEqual(short["mfe_bps"], 200)
        self.assertAlmostEqual(short["mae_bps"], -300)
        earlier = [{**row, "timestamp": row["timestamp"] - MS} for row in source]
        self.assertTrue(all(event["period"] == "development"
                            for event in indicator.collect_events(earlier, MS)))
        missing_entry = source[:-1] + [{**source[-1], "timestamp": source[-1]["timestamp"] + MS}]
        self.assertFalse(indicator.collect_events(missing_entry, MS))
        self.assertFalse(indicator.collect_events(source[:-1], MS))
        self.assertEqual(existing.BAR_MS, old_cadence)

    def test_metrics_and_all_empty_cells(self):
        empty = indicator.summarize([], [], "5m")
        self.assertEqual(len(empty), 36)
        self.assertTrue(all(cell["n"] == 0 and cell["mean_gross_bps"] is None for cell in empty))
        self.assertEqual(empty[0]["mean_net_bps_by_round_trip_cost"], {"12": None, "22": None, "37": None})
        events = [{"gross_bps": value, "mfe_bps": 50, "mae_bps": -10} for value in (12, 22, 38)]
        stats = helpers._stats(events)
        self.assertEqual(stats["n"], 3)
        self.assertEqual(stats["median_gross_bps"], 22)
        self.assertEqual(stats["mean_mfe_bps"], 50)
        self.assertEqual(stats["mean_mae_bps"], -10)
        self.assertAlmostEqual(stats["mean_net_bps_by_round_trip_cost"]["12"], 12)
        self.assertAlmostEqual(stats["win_rate_net_pct_by_round_trip_cost"]["22"], 100 / 3)


if __name__ == "__main__":
    unittest.main()
