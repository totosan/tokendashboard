import json
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from research.walkforward_readiness import (
    BAR_MS,
    INSPECTED_RANGE,
    audit_rows,
    load_protocol,
    main,
)


SYMBOLS = ("AAAUSDT", "BBBUSDT")


def stamp(value):
    return int(datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp() * 1000)


def candle(timestamp, symbol="AAAUSDT"):
    return {
        "timestamp": timestamp,
        "symbol": symbol,
        "open": 100.0,
        "high": 101.0,
        "low": 99.0,
        "close": 100.5,
        "base_volume": 2.0,
        "quote_volume": 201.0,
    }


def synthetic_folds():
    first = datetime(2026, 11, 10, tzinfo=timezone.utc)
    folds = []
    for index in range(3):
        start = first + timedelta(days=index * 28)
        end = start + timedelta(days=28)
        folds.append({
            "fold_id": f"test-{index + 1}",
            "validation_start_utc": start.isoformat().replace("+00:00", "Z"),
            "validation_end_utc_exclusive": end.isoformat().replace("+00:00", "Z"),
        })
    return folds


def complete_synthetic_rows(granularity="15m"):
    step = BAR_MS[granularity]
    start = stamp(synthetic_folds()[0]["validation_start_utc"]) - 96 * 60 * 60_000
    end = stamp(synthetic_folds()[-1]["validation_end_utc_exclusive"])
    return [
        candle(timestamp, symbol)
        for symbol in SYMBOLS
        for timestamp in range(start, end, step)
    ]


class WalkForwardReadinessTests(unittest.TestCase):
    def test_detects_gaps_duplicates_and_invalid_rows(self):
        step = BAR_MS["5m"]
        rows = [candle(0), candle(step * 2), candle(step * 2)]
        invalid = candle(step)
        invalid["high"] = 98
        result = audit_rows(
            rows + [invalid], "5m", expected_symbols=("AAAUSDT",),
            folds=[], reference_date="2026-11-02T00:00:00Z",
        )
        self.assertEqual(result["duplicate_observation_count"], 1)
        self.assertEqual(result["source_grid_missing_bar_count"], 1)
        self.assertEqual(result["row_error_counts_by_reason"]["invalid_ohlc_order"], 1)
        self.assertEqual(result["quality_gate_status"], "NOT_READY")

    def test_detects_inspected_fold_overlap_and_fold_overlap(self):
        folds = synthetic_folds()
        folds[0] = {
            "fold_id": "inspected",
            "validation_start_utc": "2026-10-01T00:00:00Z",
            "validation_end_utc_exclusive": "2026-10-29T00:00:00Z",
        }
        folds[1] = {
            "fold_id": "overlap",
            "validation_start_utc": "2026-10-28T00:00:00Z",
            "validation_end_utc_exclusive": "2026-11-25T00:00:00Z",
        }
        result = audit_rows(
            [], "15m", expected_symbols=SYMBOLS, folds=folds,
            inspected_ranges=(INSPECTED_RANGE,),
        )
        self.assertIn("fold_overlaps_inspected_window", result["reserved_folds"][0]["fold_issues"])
        self.assertIn(
            "folds_overlap_or_are_not_consecutive",
            result["reserved_folds"][1]["fold_issues"],
        )
        self.assertIn(
            "fold_not_forward_of_reference_date",
            result["reserved_folds"][0]["fold_issues"],
        )

    def test_warmup_boundary_is_required_exactly(self):
        fold = synthetic_folds()[0]
        step = BAR_MS["15m"]
        start = stamp(fold["validation_start_utc"]) - 96 * 60 * 60_000
        end = stamp(fold["validation_end_utc_exclusive"])
        rows = [
            candle(timestamp, symbol)
            for symbol in SYMBOLS
            for timestamp in range(start + step, end, step)
        ]
        result = audit_rows(
            rows, "15m", expected_symbols=SYMBOLS, folds=[fold],
            reference_date="2026-11-02T00:00:00Z",
            inspected_ranges=(INSPECTED_RANGE,),
        )
        per_symbol = result["reserved_folds"][0]["symbols"]
        self.assertTrue(all(not symbol["warmup_complete"] for symbol in per_symbol))
        self.assertTrue(all(symbol["validation_grid_complete"] for symbol in per_symbol))
        self.assertEqual(result["reserved_folds"][0]["fold_data_status"], "NOT_READY")

    def test_future_data_unavailable_is_not_ready_and_cli_fails_gate(self):
        result = audit_rows(
            [candle(0)], "5m", expected_symbols=("AAAUSDT",), folds=[],
        )
        self.assertEqual(result["future_data_readiness"], "NOT_READY")
        with patch.object(Path, "write_text") as write_report:
            code = main([
                "--input-5m", "missing-5m.csv.gz",
                "--input-15m", "missing-15m.csv.gz",
                "--output", "not-created-report.json",
            ])
        self.assertEqual(code, 2)
        write_report.assert_called_once()

    def test_horizon_edges_keep_signal_entry_and_exit_distinct(self):
        folds = synthetic_folds()
        result = audit_rows(
            complete_synthetic_rows("15m"), "15m",
            expected_symbols=SYMBOLS, folds=folds,
            reference_date="2026-11-02T00:00:00Z",
            inspected_ranges=(INSPECTED_RANGE,),
        )
        fold = result["reserved_folds"][0]
        end = stamp(fold["validation_end_utc_exclusive"])
        step = BAR_MS["15m"]
        self.assertEqual(
            stamp(fold["latest_admissible_entry_open_utc_by_horizon"]["3"]) + 3 * step,
            end,
        )
        self.assertEqual(
            stamp(fold["latest_admissible_signal_timestamp_utc_by_horizon"]["3"]) + 4 * step,
            end,
        )
        self.assertNotEqual(
            fold["latest_admissible_signal_timestamp_utc_by_horizon"]["3"],
            fold["latest_admissible_entry_open_utc_by_horizon"]["3"],
        )

    def test_complete_forward_panel_is_data_ready_not_validation(self):
        result = audit_rows(
            complete_synthetic_rows(), "15m",
            expected_symbols=SYMBOLS, folds=synthetic_folds(),
            reference_date="2026-11-02T00:00:00Z",
            inspected_ranges=(INSPECTED_RANGE,),
        )
        self.assertEqual(result["quality_gate_status"], "PASS")
        self.assertEqual(result["future_data_readiness"], "DATA_READY")
        self.assertTrue(all(
            fold["fold_data_status"] == "DATA_READY"
            for fold in result["reserved_folds"]
        ))
        self.assertEqual(result["event_count_and_statistical_gates"], "NOT_EVALUATED")

    def test_primary_family_includes_all_indicator_arms_and_132_hypotheses(self):
        protocol = load_protocol()
        arms = protocol["fixed_arm_family"]["arms"]
        indicator_protocol = json.loads(
            (Path(__file__).parent / "results/indicator-protocol.json").read_text()
        )
        indicator_arms = indicator_protocol["arms"]
        for arm in ("prior_utc_day_breakout", "wilder_rsi14_reclaim", "bollinger20_reentry"):
            self.assertEqual(arms[arm], indicator_arms[arm])
        self.assertEqual(len(arms), 11)
        self.assertEqual(protocol["dependence_and_multiplicity"]["primary_hypothesis_count"], 132)
        self.assertEqual(protocol["amends_protocol_id"], "issue-22-fixed-panel-walkforward-v1")
        self.assertIn("no past preregistration claim", protocol["amendment"]["prior_version_status"])


if __name__ == "__main__":
    unittest.main()
