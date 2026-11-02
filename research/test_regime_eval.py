import unittest

from research import regime_eval as regime


def bars(count, start=0, step=300_000, close=100.0):
    return [
        {
            "timestamp": start + index * step,
            "symbol": "BTCUSDT",
            "open": close,
            "high": close + 0.1,
            "low": close - 0.1,
            "close": close,
            "base_volume": 1.0,
            "quote_volume": 100.0,
        }
        for index in range(count)
    ]


def box_sequence(side="long", start=0, step=300_000, inside_offsets=()):
    result = bars(12, start, step)
    if side == "long":
        result.append({
            "timestamp": start + 12 * step, "symbol": "BTCUSDT",
            "open": 100.0, "high": 101.2, "low": 99.9, "close": 101.0,
            "base_volume": 1.0, "quote_volume": 100.0,
        })
    else:
        result.append({
            "timestamp": start + 12 * step, "symbol": "BTCUSDT",
            "open": 100.0, "high": 100.1, "low": 98.8, "close": 99.0,
            "base_volume": 1.0, "quote_volume": 100.0,
        })
    for offset in range(1, 4):
        close = 100.1 if offset in inside_offsets else (101.0 if side == "long" else 99.0)
        result.append({
            "timestamp": start + (12 + offset) * step, "symbol": "BTCUSDT",
            "open": close, "high": close + 0.2, "low": close - 0.2, "close": close,
            "base_volume": 1.0, "quote_volume": 100.0,
        })
    return result


class RegimeEvalTests(unittest.TestCase):
    def test_features_are_invariant_to_future_bar_changes(self):
        original = bars(150)
        for index, row in enumerate(original):
            row["close"] += index * 0.01
            row["open"] = row["close"]
            row["high"] = row["close"] + 0.2
            row["low"] = row["close"] - 0.2
        altered = [dict(row) for row in original]
        for row in altered[131:]:
            row["high"] *= 1.5
            row["low"] *= 0.7
            row["close"] *= 1.1
        before = regime.features_for_segment(original, 300_000)
        after = regime.features_for_segment(altered, 300_000)
        for index in range(131):
            self.assertEqual(before[index * 300_000], after[index * 300_000])

    def test_feature_warmup_and_gaps_reset_history(self):
        complete = bars(130)
        values = regime.features_for_segment(complete, 300_000)
        self.assertIsNone(values[19 * 300_000]["efficiency_ratio_20"])
        self.assertEqual(values[20 * 300_000]["trend_range"], "range")
        self.assertIsNone(values[119 * 300_000]["volatility_bucket"])
        self.assertIn(values[120 * 300_000]["volatility_bucket"], regime.VOLATILITY_BUCKETS)
        broken = bars(121)
        del broken[70]
        feature_map, segments = regime.build_feature_map(broken, 300_000)
        self.assertEqual(len(segments["BTCUSDT"]), 2)
        self.assertIsNone(feature_map[("BTCUSDT", broken[-1]["timestamp"])]["volatility_bucket"])

    def test_box_breakout_has_mirrored_long_and_short_directions(self):
        long_rows = box_sequence("long")
        short_rows = box_sequence("short", start=10_200_000)
        for row in short_rows:
            row["symbol"] = "ETHUSDT"
        feature_map, segments = regime.build_feature_map(long_rows + short_rows, 300_000)
        candidates, _ = regime.box_candidates(segments, feature_map, 300_000)
        signal_candidates = [row for row in candidates if row["signal_ms"] in (3_600_000, 13_800_000)]
        self.assertEqual({(row["symbol"], row["side"]) for row in signal_candidates},
                         {("BTCUSDT", "long"), ("ETHUSDT", "short")})

    def test_outcome_window_missing_bars_is_not_nonfailure(self):
        rows = box_sequence("long")[:14]
        feature_map, segments = regime.build_feature_map(rows, 300_000)
        candidates, coverage = regime.box_candidates(segments, feature_map, 300_000)
        self.assertEqual(len(candidates), 1)
        self.assertFalse(candidates[0]["window_complete"])
        self.assertNotIn("failed", candidates[0])
        self.assertEqual(coverage["incomplete_window"], 1)
        cell = regime.summarize_box_cell(candidates)
        self.assertEqual(cell["qualifying_breakouts_n"], 1)
        self.assertEqual(cell["eligible_complete_non_crossing_n"], 0)
        self.assertIsNone(cell["failure_rate_pct_complete_non_crossing"])
        self.assertEqual(cell["first_failure_timing"]["denominator_eligible_complete_non_crossing_n"], 0)

    def test_development_outcome_window_crossing_split_is_excluded(self):
        step = 300_000
        start = regime.SPLIT_MS - 14 * step
        rows = box_sequence("long", start=start, step=step)
        feature_map, segments = regime.build_feature_map(rows, step)
        candidates, _ = regime.box_candidates(segments, feature_map, step)
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0]["period"], "development")
        self.assertTrue(candidates[0]["split_crossing"])
        summary = regime.summarize_box_cell(candidates)
        self.assertEqual(summary["split_crossing_n"], 1)
        self.assertEqual(summary["eligible_complete_non_crossing_n"], 0)
        self.assertEqual(summary["first_failure_timing"]["denominator_eligible_complete_non_crossing_n"], 0)

    def test_first_failure_offset_and_delayed_entry_timing(self):
        expected_relative = {
            1: "before_delayed_entry",
            2: "at_delayed_entry",
            3: "after_delayed_entry",
        }
        for offset, relative_label in expected_relative.items():
            with self.subTest(offset=offset):
                rows = box_sequence("long", inside_offsets=(offset,))
                feature_map, segments = regime.build_feature_map(rows, 300_000)
                candidates, _ = regime.box_candidates(segments, feature_map, 300_000)
                self.assertEqual(candidates[0]["first_failure_offset"], offset)
                timing = regime.summarize_box_cell(candidates)["first_failure_timing"]
                self.assertEqual(timing[f"offset_{offset}_bars_after_signal_n" if offset > 1 else "offset_1_bar_after_signal_n"], 1)
                self.assertEqual(timing["relative_to_delayed_entry"][relative_label], 1)
                self.assertEqual(timing["denominator_eligible_complete_non_crossing_n"], 1)

    def test_first_failure_counts_only_first_reentry_and_reports_no_failure(self):
        rows = box_sequence("long", inside_offsets=(2, 3))
        feature_map, segments = regime.build_feature_map(rows, 300_000)
        candidates, _ = regime.box_candidates(segments, feature_map, 300_000)
        timing = regime.summarize_box_cell(candidates)["first_failure_timing"]
        self.assertEqual(candidates[0]["first_failure_offset"], 2)
        self.assertEqual(timing["offset_2_bars_after_signal_n"], 1)
        self.assertEqual(timing["offset_3_bars_after_signal_n"], 0)
        self.assertEqual(timing["no_failure_in_three_bar_window_n"], 0)
        self.assertEqual(sum(timing[key] for key in (
            "offset_1_bar_after_signal_n",
            "offset_2_bars_after_signal_n",
            "offset_3_bars_after_signal_n",
            "no_failure_in_three_bar_window_n",
        )), timing["denominator_eligible_complete_non_crossing_n"])

        rows = box_sequence("long")
        feature_map, segments = regime.build_feature_map(rows, 300_000)
        candidates, _ = regime.box_candidates(segments, feature_map, 300_000)
        timing = regime.summarize_box_cell(candidates)["first_failure_timing"]
        self.assertIsNone(candidates[0]["first_failure_offset"])
        self.assertEqual(timing["no_failure_in_three_bar_window_n"], 1)

    def test_empty_cells_are_emitted_for_existing_and_box_events(self):
        existing = regime.analyze_existing([], {})
        self.assertEqual(len(existing["by_volatility"]), 2 * 3 * 2 * 2 * 3)
        self.assertEqual(len(existing["by_trend_range"]), 2 * 3 * 2 * 2 * 2)
        self.assertTrue(all(cell["n"] == 0 for cell in existing["by_volatility"]))
        self.assertTrue(all(cell["n"] == 0 for cell in existing["by_trend_range"]))
        box = regime.analyze_box([], "volatility_bucket", regime.VOLATILITY_BUCKETS)
        self.assertEqual(len(box["by_group_side_entry_period_regime"]), 3 * 2 * 2 * 3)
        self.assertTrue(all(
            cell["qualifying_breakouts_n"] == 0
            and cell["failure_rate_pct_complete_non_crossing"] is None
            for cell in box["by_group_side_entry_period_regime"]
        ))

    def test_quantile_type7_and_box_failure_inclusive_edges(self):
        self.assertAlmostEqual(regime.type7_quantile(list(range(101)), 1 / 3), 100 / 3)
        rows = box_sequence("long", inside_offsets=(1,))
        feature_map, segments = regime.build_feature_map(rows, 300_000)
        candidates, _ = regime.box_candidates(segments, feature_map, 300_000)
        self.assertEqual(len(candidates), 1)
        self.assertTrue(candidates[0]["failed"])
        self.assertEqual(candidates[0]["immediate"]["gross_bps"], 0.0)


if __name__ == "__main__":
    unittest.main()
