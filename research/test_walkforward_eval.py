import copy
import json
import math
import unittest
from collections import Counter
from unittest.mock import patch

from research import hypothesis_eval as hypothesis
from research import indicator_eval as indicator
from research import intraday_eval as intraday
from research import walkforward_eval as evaluator
from research import walkforward_readiness as readiness


STEP = readiness.BAR_MS["15m"]
START = evaluator.DEVELOPMENT_FOLDS[0].start
FOLD = evaluator.DevelopmentFold("development-test", START, START + evaluator.DAY_MS)
GROUPS = readiness.load_protocol()["frozen_inputs"]["groups"]


def bars(closes, *, start=START, step=STEP, symbol="BTCUSDT"):
    return [
        {"timestamp": start + index * step, "symbol": symbol,
         "open": close, "high": close + .1, "low": close - .1, "close": close,
         "base_volume": 10., "quote_volume": close * 10}
        for index, close in enumerate(closes)
    ]


def complete_history(fold=FOLD, step=STEP, symbol="BTCUSDT"):
    start = fold.start - readiness.WARMUP_MS
    return bars([100.] * ((fold.end - start) // step), start=start, step=step, symbol=symbol)


def group_rows(rows, timeframe="15m"):
    return evaluator.prepare_rows(rows, timeframe)[0]


def mock_signals(*signals):
    def select(run, step):
        stamps = {row["timestamp"] for row in run}
        return {signal for signal in signals if signal[0] in stamps}
    return patch.object(evaluator, "frozen_signals", side_effect=select)


def signal(stamp, side="long", arm="three_close_momentum"):
    return stamp, side, arm


class FrozenRulesTests(unittest.TestCase):
    def test_hashes_and_exact_eleven_arm_family(self):
        protocol, hashes, floors = evaluator.frozen_configuration()
        self.assertEqual(len(hashes), 7)
        self.assertEqual(len(evaluator.ARMS), 11)
        self.assertEqual(set(evaluator.ARMS), set(protocol["fixed_arm_family"]["arms"]))
        self.assertEqual(floors, {"fold": (30, 10, 2), "pooled": (100, 20, 2)})
        for relative, actual in hashes.items():
            self.assertEqual(actual, protocol["frozen_inputs"]["source_version_sha256"][relative])

    def test_hash_mismatch_fails_closed(self):
        original = readiness.sha256_file
        with patch.object(readiness, "sha256_file", side_effect=lambda path:
                          "changed" if str(path).endswith("hypothesis_eval.py") else original(path)):
            with self.assertRaisesRegex(ValueError, "Frozen source hash changed"):
                evaluator.frozen_configuration()

    def test_exact_pinned_arm_parity_both_timeframes(self):
        for step in readiness.BAR_MS.values():
            source = bars([100 + 5 * math.sin(index / 20) for index in range(1200)],
                          start=evaluator.DEVELOPMENT_START, step=step)
            source[400]["quote_volume"] *= 3
            previous = intraday.BAR_MS
            try:
                intraday.BAR_MS = step
                expected = set(hypothesis._signal_arms(source, step))
                expected.update(indicator.signal_arms(source, step))
            finally:
                intraday.BAR_MS = previous
            actual = evaluator.frozen_signals(source, step)
            # The only compatibility difference is the newly visible final
            # signal, needed to count missing outcomes instead of losing it.
            self.assertEqual({hit for hit in actual if hit[0] < source[-1]["timestamp"]},
                             {hit for hit in expected if hit[0] < source[-1]["timestamp"]})
            self.assertEqual(intraday.BAR_MS, previous)

    def test_past_only_prefix_and_future_perturbation(self):
        for step in readiness.BAR_MS.values():
            source = bars([100 + 5 * math.sin(index / 9) for index in range(1100)],
                          start=evaluator.DEVELOPMENT_START, step=step)
            before = evaluator.frozen_signals(source, step)
            future = bars([400, 2, 300, 3], start=source[-1]["timestamp"] + step, step=step)
            after = evaluator.frozen_signals(source + future, step)
            self.assertEqual(before, {hit for hit in after if hit[0] <= source[-1]["timestamp"]})
            for length in (20, 50, 400, 960):
                prefix = source[:length]
                self.assertEqual(evaluator.frozen_signals(prefix, step),
                                 {hit for hit in before if hit[0] <= prefix[-1]["timestamp"]})

    def test_final_signal_exists_without_entry_and_input_is_not_mutated(self):
        source = bars([100, 101, 102])
        original = copy.deepcopy(source)
        self.assertIn(signal(source[-1]["timestamp"]), evaluator.frozen_signals(source, STEP))
        self.assertEqual(source, original)
        self.assertIsNone(evaluator.outcome({row["timestamp"]: row for row in source},
                                            source[-1]["timestamp"], "long", 1, STEP))

    def test_shared_cadence_restored_even_on_error(self):
        previous = intraday.BAR_MS
        with patch.object(hypothesis, "_signal_arms", side_effect=RuntimeError("test")):
            with self.assertRaises(RuntimeError):
                evaluator.frozen_signals(bars([100]), STEP)
        self.assertEqual(intraday.BAR_MS, previous)

    def test_indicator_arms_both_directions_on_real_implementations(self):
        for side, rsi_closes, extreme, daily_close in (
            ("long", list(range(115, 100, -1)) + [115], 80, 102),
            ("short", list(range(100, 115)) + [100], 120, 98),
        ):
            for closes, arm, start in (
                (rsi_closes, "wilder_rsi14_reclaim", START),
                ([100] * 19 + [extreme, 100], "bollinger20_reentry", START),
                ([100] * 96 + [daily_close], "prior_utc_day_breakout", START),
            ):
                hits = evaluator.frozen_signals(bars(closes, start=start), STEP)
                self.assertIn((START + (len(closes) - 1) * STEP, side, arm), hits)

    def test_all_eight_hypothesis_arms_have_both_direction_fixtures(self):
        for side in ("long", "short"):
            transform = (lambda value: value) if side == "long" else (lambda value: 200 - value)
            fixtures = []
            trend = bars([transform(95 + index / 200) for index in range(400)])
            trend[-1]["quote_volume"] = 100_000
            fixtures.append(trend)
            fixtures.append(bars([transform(100)] * 70 +
                                 [transform(100 - index / 10) for index in range(30)] +
                                 [transform(97 + index / 5) for index in range(80)]))
            box = bars([100] * 12)
            box += [
                {**bars([101.5], start=START + 12 * STEP)[0],
                 "open": 100.8, "high": 101.8, "low": 100.7},
                {**bars([101.4], start=START + 13 * STEP)[0],
                 "open": 101.5, "high": 101.7, "low": 100.95},
            ]
            for row in box[:12]:
                row.update(high=101, low=99)
            dashboard = [
                (100, 101.2, 99.9, 101), (101, 102.2, 100.9, 102),
                (102, 103.2, 101.9, 103), (103, 103.1, 102.5, 102.8),
                (102.8, 103.6, 102.7, 103.5),
            ]
            breakout = bars([100] * 5)
            for row, values in zip(breakout, dashboard):
                row.update(zip(("open", "high", "low", "close"), values))
            if side == "short":
                for source in (box, breakout):
                    for row in source:
                        opened, high, low, close = (row[key] for key in ("open", "high", "low", "close"))
                        row.update(open=200 - opened, high=200 - low,
                                   low=200 - high, close=200 - close)
            fixtures.extend((box, breakout))
            found = {arm for source in fixtures for _, hit_side, arm
                     in evaluator.frozen_signals(source, STEP) if hit_side == side}
            self.assertTrue(set(hypothesis.RULES) <= found,
                            f"{side} missing {set(hypothesis.RULES) - found}")


class IntegrityAndSafetyTests(unittest.TestCase):
    def test_reserved_dates_rejected_before_features(self):
        for stamp in (evaluator.DEVELOPMENT_START - STEP, evaluator.DEVELOPMENT_END,
                      evaluator.milliseconds("2027-02-01T00:00:00Z")):
            with patch.object(evaluator, "frozen_signals") as features:
                # Direct preparation rejects the timestamp before any real
                # feature computation (including the other timeframe).
                with self.assertRaisesRegex(ValueError, "Reserved/uninspected"):
                    evaluator.prepare_rows(bars([100], start=stamp), "15m")
                features.assert_not_called()
            with self.assertRaisesRegex(ValueError, "Reserved/uninspected"):
                evaluator.evaluate_development({"15m": bars([100], start=stamp)},
                                                source_kind="synthetic", folds=(FOLD,))

    def test_reserved_shifted_and_overlapping_folds_forbidden(self):
        for folds in (
            (evaluator.DevelopmentFold("future-01", START, FOLD.end),),
            (evaluator.DevelopmentFold("development-test", evaluator.DEVELOPMENT_END,
                                      evaluator.DEVELOPMENT_END + evaluator.DAY_MS),),
            (FOLD, FOLD),
            (FOLD, evaluator.DevelopmentFold("development-next", START, FOLD.end)),
            (evaluator.DevelopmentFold("development-test", START + 1, FOLD.end),),
        ):
            with self.assertRaises(ValueError):
                evaluator.check_folds(folds)

    def test_invalid_missing_fields_and_ohlc_are_quarantined(self):
        cases = (
            ({"open": -1}, "non_positive_price"),
            ({"high": 99}, "invalid_ohlc_order"),
            ({"low": 101}, "invalid_ohlc_order"),
            ({"close": float("nan")}, "non_finite_value"),
            ({"base_volume": -1}, "negative_volume"),
            ({"quote_volume": float("inf")}, "non_finite_value"),
            ({"open": "invalid"}, "unparseable_row"),
        )
        for changes, reason in cases:
            source = bars([100, 100, 100])
            source[1].update(changes)
            grouped, quality = evaluator.prepare_rows(source, "15m")
            self.assertEqual(quality["row_error_counts"], {reason: 1})
            self.assertEqual([len(run) for run in hypothesis.segments(grouped["BTCUSDT"], STEP)],
                             [1, 1])
        source = bars([100])
        del source[0]["high"]
        self.assertEqual(evaluator.prepare_rows(source, "15m")[1]["row_error_counts"],
                         {"unparseable_row": 1})

    def test_duplicate_valid_or_invalid_copy_removes_all_copies(self):
        for corrupt in (False, True):
            source = bars([100, 101, 102])
            duplicate = dict(source[1])
            if corrupt:
                duplicate["high"] = 1
            source.append(duplicate)
            grouped, quality = evaluator.prepare_rows(source, "15m")
            self.assertEqual(quality["duplicate_keys"], 1)
            self.assertEqual(len(grouped["BTCUSDT"]), 2)
            self.assertNotIn(START + STEP, {row["timestamp"] for row in grouped["BTCUSDT"]})

    def test_unaligned_row_breaks_containing_bucket_without_imputation(self):
        source = bars([100, 100, 100])
        source += bars([100], start=START + STEP + 1)
        grouped, quality = evaluator.prepare_rows(source, "15m")
        self.assertEqual(quality["row_error_counts"], {"unaligned_timestamp": 1})
        self.assertEqual([row["timestamp"] for row in grouped["BTCUSDT"]],
                         [START, START + 2 * STEP])

    def test_unlocatable_timestamp_or_unknown_symbol_fails_closed(self):
        for changes in ({"timestamp": "bad"}, {"timestamp": START + .5},
                        {"timestamp": True}, {"symbol": "UNINSPECTED"}):
            source = bars([100, 100])
            source[1].update(changes)
            grouped, quality = evaluator.prepare_rows(source, "15m")
            self.assertTrue(quality["unlocatable_corruption_blocks_timeframe"])
            self.assertEqual(sum(map(len, grouped.values())), 0)

    def test_sorted_input_and_zero_volume_are_valid(self):
        source = bars([100, 101, 102])
        source[1].update(base_volume=0, quote_volume=0)
        grouped, quality = evaluator.prepare_rows(list(reversed(source)), "15m")
        self.assertEqual(grouped["BTCUSDT"], source)
        self.assertEqual(quality["row_error_counts"], {})

    def test_cli_has_no_arbitrary_or_future_input_mode(self):
        for argv in (["--input", "reserved.csv"], ["--source", "future"],
                     ["--fold-start", "2027-02-01"]):
            with patch("sys.stderr"), self.assertRaises(SystemExit) as error:
                evaluator.main(argv)
            self.assertEqual(error.exception.code, 2)

    def test_inspected_hash_checked_before_csv_is_parsed(self):
        protocol = readiness.load_protocol()
        with patch.object(readiness, "sha256_file", return_value="wrong"), \
                patch.object(readiness, "read_snapshot") as reader:
            with self.assertRaisesRegex(ValueError, "hash mismatch"):
                evaluator.inspected_inputs(protocol)
            reader.assert_not_called()

    def test_inspected_paths_cannot_be_redirected(self):
        protocol = readiness.load_protocol()
        protocol["frozen_inputs"]["timeframes"]["5m"]["snapshot"] = "reserved-2027.csv"
        with patch.object(readiness, "sha256_file") as hasher:
            with self.assertRaisesRegex(ValueError, "original inspected"):
                evaluator.inspected_inputs(protocol)
            hasher.assert_not_called()

    def test_cli_writes_all_cells_and_never_fetches_market_data(self):
        with patch.object(evaluator, "synthetic_rows", return_value=[]), \
                patch.object(intraday, "request_page", side_effect=AssertionError("network")), \
                patch.object(evaluator.Path, "mkdir"), \
                patch.object(evaluator.Path, "write_text") as writer, patch("builtins.print"):
            self.assertEqual(evaluator.main(["--source", "synthetic", "--output",
                                             "research/results/not-written-development.json"]), 0)
        payload = json.loads(writer.call_args.args[0])
        self.assertEqual(len(payload["cells"]), 1584)
        self.assertNotIn("events", payload)
        self.assertEqual(payload["evaluation_status"], "DEVELOPMENT_ONLY")

    def test_cli_cannot_overwrite_frozen_protocol(self):
        with patch.object(evaluator, "synthetic_rows", return_value=[]), \
                patch.object(evaluator.Path, "write_text") as writer:
            with self.assertRaisesRegex(ValueError, "Cannot overwrite"):
                evaluator.main(["--output", str(readiness.PROTOCOL_PATH)])
            writer.assert_not_called()


class BoundaryAndOutcomeTests(unittest.TestCase):
    def test_exact_first_and_final_three_entry_embargoes(self):
        for step in readiness.BAR_MS.values():
            run_start = START - readiness.WARMUP_MS
            for offset in range(4):
                entry = START + offset * step
                result = evaluator.entry_rejection(entry - step, entry, entry + step,
                                                    run_start, FOLD, step)
                self.assertEqual(result, "purged_boundary" if offset == 0 else
                                 "embargoed" if offset < 3 else None)
            for offset in (1, 2, 3, 4):
                entry = FOLD.end - offset * step
                result = evaluator.entry_rejection(entry - step, entry, entry + step,
                                                    run_start, FOLD, step)
                self.assertEqual(result, "embargoed" if offset <= 3 else None)

    def test_entry_assignment_and_exit_boundary_are_exact(self):
        run_start = START - readiness.WARMUP_MS
        self.assertEqual(evaluator.entry_rejection(START - STEP, START, START + STEP,
                                                   run_start, FOLD, STEP), "purged_boundary")
        self.assertEqual(evaluator.entry_rejection(FOLD.end - STEP, FOLD.end,
                                                   FOLD.end + STEP, run_start, FOLD, STEP),
                         "purged_boundary")
        # Exit equal to fold end is not a purge; the final-entry embargo is a
        # separate gate. Exceeding it is a purge regardless of embargo.
        self.assertEqual(evaluator.entry_rejection(FOLD.end - 4 * STEP, FOLD.end - 3 * STEP,
                                                   FOLD.end, run_start, FOLD, STEP), "embargoed")
        self.assertEqual(evaluator.entry_rejection(FOLD.end - 4 * STEP, FOLD.end - 3 * STEP,
                                                   FOLD.end + 1, run_start, FOLD, STEP),
                         "purged_boundary")

    def test_horizon_returns_excursions_timestamps_both_directions(self):
        source = bars([100, 102, 97], start=START + STEP)
        source[0].update(open=100, high=104, low=98, close=101)
        source[1].update(high=106, low=99)
        source[2].update(high=103, low=95)
        indexed = {row["timestamp"]: row for row in source}
        for horizon, gross, favorable, adverse in ((1, 100, 400, -200),
                                                    (2, 200, 600, -200),
                                                    (3, -300, 600, -500)):
            long = evaluator.outcome(indexed, START, "long", horizon, STEP)
            short = evaluator.outcome(indexed, START, "short", horizon, STEP)
            self.assertAlmostEqual(long["gross_bps"], gross)
            self.assertAlmostEqual(long["mfe_bps"], favorable)
            self.assertAlmostEqual(long["mae_bps"], adverse)
            self.assertAlmostEqual(short["gross_bps"], -gross)
            self.assertAlmostEqual(short["mfe_bps"], -adverse)
            self.assertAlmostEqual(short["mae_bps"], -favorable)
            self.assertEqual(long["signal_timestamp"], START)
            self.assertEqual(long["signal_close_timestamp"], START + STEP)
            self.assertEqual(long["entry_timestamp"], START + STEP)
            self.assertEqual(long["exit_close_timestamp"], START + (horizon + 1) * STEP)
            self.assertLess(long["signal_timestamp"], long["entry_timestamp"])
            self.assertLess(long["entry_timestamp"], long["exit_close_timestamp"])

    def test_missing_held_bar_is_incomplete_not_zero(self):
        source = bars([100, 100, 100], start=START + STEP)
        indexed = {row["timestamp"]: row for row in source}
        del indexed[START + 2 * STEP]
        self.assertIsNotNone(evaluator.outcome(indexed, START, "long", 1, STEP))
        self.assertIsNone(evaluator.outcome(indexed, START, "long", 2, STEP))
        self.assertIsNone(evaluator.outcome(indexed, START, "short", 3, STEP))
        self.assertIsNone(evaluator.outcome({}, START, "long", 1, STEP))

    def test_complete_label_and_incomplete_counts_for_all_horizons(self):
        source = complete_history()
        stamp = START + 10 * STEP
        source = [row for row in source if row["timestamp"] != stamp + 3 * STEP]
        with mock_signals(signal(stamp)):
            events, counts, _ = evaluator.evaluate_fold(group_rows(source), "15m", FOLD, GROUPS)
        self.assertEqual([event["horizon"] for event in events], [1, 2])
        self.assertEqual(counts[("three_close_momentum", "btc_eth", "long", 3, FOLD.fold_id)]["incomplete"], 1)

    def test_96_hour_initial_warmup_and_reinitialization_exact_boundaries(self):
        long_fold = evaluator.DevelopmentFold("development-long", START, START + 7 * evaluator.DAY_MS)
        source = complete_history(long_fold)
        gap = START + 10 * STEP
        source = [row for row in source if row["timestamp"] != gap]
        restart = gap + STEP
        mature_entry = restart + readiness.WARMUP_MS
        signals = (signal(START + 3 * STEP), signal(mature_entry - 2 * STEP),
                   signal(mature_entry - STEP))
        with mock_signals(*signals):
            events, counts, _ = evaluator.evaluate_fold(group_rows(source), "15m", long_fold, GROUPS)
        self.assertEqual({event["signal_timestamp"] for event in events},
                         {START + 3 * STEP, mature_entry - STEP})
        for horizon in evaluator.HORIZONS:
            self.assertEqual(counts[("three_close_momentum", "btc_eth", "long",
                                     horizon, long_fold.fold_id)]["insufficient_warmup"], 1)
        entry = START + 4 * STEP
        self.assertIsNone(evaluator.entry_rejection(entry - STEP, entry, entry + STEP,
                                                    entry - readiness.WARMUP_MS, FOLD, STEP))
        self.assertEqual(evaluator.entry_rejection(entry - STEP, entry, entry + STEP,
                                                   entry - readiness.WARMUP_MS + STEP, FOLD, STEP),
                         "insufficient_warmup")

    def test_fold_reinitialization_discards_older_history(self):
        later = evaluator.DevelopmentFold("development-later", START + evaluator.DAY_MS,
                                           FOLD.end + evaluator.DAY_MS)
        source = complete_history(later)
        source += bars([100], start=later.start - readiness.WARMUP_MS - STEP)
        observed_starts = []
        def capture(run, step):
            observed_starts.append(run[0]["timestamp"])
            return set()
        with patch.object(evaluator, "frozen_signals", side_effect=capture):
            evaluator.evaluate_fold(group_rows(source), "15m", later, GROUPS)
        self.assertEqual(observed_starts, [later.start - readiness.WARMUP_MS])

    def test_real_signals_with_missing_entry_are_counted(self):
        source = complete_history()
        last_signal = START + 8 * STEP
        source = source[:(last_signal - source[0]["timestamp"]) // STEP + 1]
        source[-3]["close"], source[-2]["close"], source[-1]["close"] = 100, 101, 102
        for row in source[-3:]:
            row["high"] = row["close"] + .1
        events, counts, _ = evaluator.evaluate_fold(group_rows(source), "15m", FOLD, GROUPS)
        for horizon in evaluator.HORIZONS:
            key = ("three_close_momentum", "btc_eth", "long", horizon, FOLD.fold_id)
            self.assertEqual(counts[key]["incomplete"], 1)
        self.assertFalse(any(event["signal_timestamp"] == last_signal for event in events))

    def test_no_outcome_reused_across_adjacent_folds(self):
        next_fold = evaluator.DevelopmentFold("development-next", FOLD.end,
                                             FOLD.end + evaluator.DAY_MS)
        source = complete_history(next_fold)
        source += complete_history()[:96]
        grouped = group_rows(source)
        signals = (signal(FOLD.end - STEP), signal(FOLD.end + 3 * STEP))
        with mock_signals(*signals):
            first, _, _ = evaluator.evaluate_fold(grouped, "15m", FOLD, GROUPS)
            second, _, _ = evaluator.evaluate_fold(grouped, "15m", next_fold, GROUPS)
        self.assertEqual(first, [])
        self.assertTrue(second)
        self.assertTrue(all(event["entry_timestamp"] > FOLD.end for event in second))


def fake_events(n, dates=10, symbols=2):
    return [
        {"entry_timestamp": START + (index % dates) * evaluator.DAY_MS,
         "symbol": ("BTCUSDT", "ETHUSDT")[index % symbols],
         "gross_bps": 50., "mfe_bps": 80., "mae_bps": -20.}
        for index in range(n)
    ]


class ReportingTests(unittest.TestCase):
    def test_each_fold_and_pooled_floor_component_is_binding(self):
        for floor, cases in (
            ((30, 10, 2), ((29, 10, 2), (30, 9, 2), (30, 10, 1))),
            ((100, 20, 2), ((99, 20, 2), (100, 19, 2), (100, 20, 1))),
        ):
            for n, dates, symbols in cases:
                events = fake_events(n, dates, symbols)
                cell = evaluator.summarize_cell(events, Counter(completed=n), floor)
                self.assertEqual(cell["n"], n)
                self.assertEqual(cell["floor_status"], "INSUFFICIENT_EVENTS")
                for key in ("mean_gross_bps", "median_gross_bps", "mean_mfe_bps",
                            "mean_mae_bps", "win_rate_gross_pct"):
                    self.assertIsNone(cell[key])
                self.assertEqual(cell["mean_net_bps_by_round_trip_cost"],
                                 {"12": None, "22": None, "37": None})

    def test_floor_equality_and_fixed_cost_subtracted_once(self):
        for n, dates, floor in ((30, 10, (30, 10, 2)), (100, 20, (100, 20, 2))):
            cell = evaluator.summarize_cell(fake_events(n, dates), Counter(completed=n), floor)
            self.assertEqual(cell["floor_status"], "PASS")
            self.assertEqual(cell["estimate_status"], "DEVELOPMENT_DESCRIPTIVE_ONLY")
            self.assertEqual(cell["mean_gross_bps"], 50)
            self.assertEqual(cell["mean_net_bps_by_round_trip_cost"], {"12": 38, "22": 28, "37": 13})
            self.assertEqual(cell["win_rate_net_pct_by_round_trip_cost"],
                             {"12": 100, "22": 100, "37": 100})

    def test_no_empty_cells_omitted_and_no_zero_return_estimates(self):
        report = evaluator.evaluate_development({}, source_kind="synthetic")
        self.assertEqual(report["result_count"], 11 * 2 * 3 * 2 * 3 * 4)
        dimensions = {
            (cell["arm"], cell["timeframe"], cell["asset_group"], cell["side"],
             cell["horizon"], cell["fold_id"]) for cell in report["cells"]
        }
        self.assertEqual(len(dimensions), report["result_count"])
        self.assertTrue(all(cell["n"] == 0 and cell["mean_gross_bps"] is None
                            and cell["estimate_status"] == "NOT_ESTIMABLE" for cell in report["cells"]))
        self.assertEqual(report["empirical_future_validation_status"], "NOT_RUN")
        self.assertEqual(report["original_inference_status"], "FAIL")
        self.assertEqual(report["known_covariance_oracle_status"], "INCONCLUSIVE")
        self.assertIn("NOT evidence of a post-signal executable price",
                      report["entry_price_limitation"])
        self.assertIn("all 12 inspected AAPL 5m opens", report["entry_price_limitation"])
        self.assertTrue(report["unresolved_protocol_ambiguities"])
        json.dumps(report, allow_nan=False)

    def test_real_event_cell_and_pooled_counts_match_and_dispositions_conserve(self):
        source = complete_history()
        for index, row in enumerate(source):
            row.update(close=100 + index / 100, high=101 + index / 100)
        report = evaluator.evaluate_development({"15m": source}, source_kind="synthetic", folds=(FOLD,))
        self.assertEqual(report["result_count"], 11 * 2 * 3 * 2 * 3 * 2)
        selected = [cell for cell in report["cells"] if cell["timeframe"] == "15m"
                    and cell["arm"] == "three_close_momentum" and cell["side"] == "long"
                    and cell["asset_group"] == "btc_eth" and cell["horizon"] == 1]
        self.assertEqual(len(selected), 2)
        self.assertGreater(selected[0]["n"], 0)
        self.assertEqual(selected[0]["n"], selected[1]["n"])
        self.assertIsNone(selected[0]["mean_gross_bps"])  # one date/symbol is below floors
        for cell in report["cells"]:
            self.assertEqual(cell["n"], cell["completed"])
            self.assertEqual(cell["candidates"], sum(cell[key] for key in (
                "completed", "incomplete", "purged_boundary", "embargoed", "insufficient_warmup")))
        digest = evaluator.evidence_digest(report)
        self.assertEqual(digest, evaluator.evidence_digest(report))
        self.assertEqual(len(digest["cells_sha256"]), 64)
        self.assertNotIn("cells", digest)
        self.assertEqual(digest["entry_price_limitation"], report["entry_price_limitation"])

    def test_synthetic_fixture_is_deterministic_valid_and_inspected_range_only(self):
        first = evaluator.synthetic_rows("15m")
        self.assertEqual(first, evaluator.synthetic_rows("15m"))
        self.assertEqual(len(first), 45 * 96 * 12)
        self.assertEqual(min(row["timestamp"] for row in first), evaluator.DEVELOPMENT_START)
        self.assertEqual(max(row["timestamp"] for row in first), evaluator.DEVELOPMENT_END - STEP)
        _, quality = evaluator.prepare_rows(first, "15m")
        self.assertEqual(quality["row_error_counts"], {})
        self.assertEqual(quality["duplicate_keys"], 0)
        self.assertTrue(quality["panel_exact"])


if __name__ == "__main__":
    unittest.main()
