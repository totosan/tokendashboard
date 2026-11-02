#!/usr/bin/env python3
"""Offline audit of frozen walk-forward data gates; this is not a return evaluator."""

from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
import math
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
PROTOCOL_PATH = ROOT / "research/results/walkforward-protocol.json"
DEFAULT_SNAPSHOTS = {
    "5m": ROOT / "research/data/bitget-5m-2026-09-17_2026-11-01.csv.gz",
    "15m": ROOT / "research/data/bitget-15m-2026-09-17_2026-11-01.csv.gz",
}
SYMBOLS = (
    "BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT", "DOGEUSDT",
    "ADAUSDT", "LINKUSDT", "TSLAUSDT", "NVDAUSDT", "AAPLUSDT", "COINUSDT",
)
BAR_MS = {"5m": 5 * 60_000, "15m": 15 * 60_000}
REQUIRED_FIELDS = ("timestamp", "symbol", "open", "high", "low", "close", "base_volume", "quote_volume")
WARMUP_MS = 96 * 60 * 60_000
REFERENCE_DATE = "2026-11-02T00:00:00Z"
INSPECTED_RANGE = ("2026-09-17T00:00:00Z", "2026-11-01T00:00:00Z")
HASH_INPUTS = (
    "research/intraday_eval.py",
    "research/hypothesis_eval.py",
    "research/indicator_eval.py",
    "research/regime_eval.py",
    "research/event_uncertainty.py",
    "research/results/indicator-protocol.json",
    "research/results/regime-protocol.json",
    "research/results/hypotheses-5m.json",
    "research/results/hypotheses-15m.json",
    "research/results/indicators-5m.json",
    "research/results/indicators-15m.json",
    "research/results/regimes-5m.json",
    "research/results/regimes-15m.json",
    "research/results/uncertainty-5m.json",
    "research/results/uncertainty-15m.json",
)


def parse_utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError(f"UTC timestamp needs a timezone: {value}")
    return parsed.astimezone(timezone.utc)


def iso_utc(stamp_ms: int) -> str:
    return datetime.fromtimestamp(stamp_ms / 1000, timezone.utc).isoformat().replace("+00:00", "Z")


def iso_day(stamp_ms: int) -> str:
    return datetime.fromtimestamp(stamp_ms / 1000, timezone.utc).date().isoformat()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def relative_path(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(ROOT))
    except ValueError:
        return str(path)


def load_protocol() -> dict[str, Any]:
    protocol = json.loads(PROTOCOL_PATH.read_text(encoding="utf-8"))
    indicator_path = ROOT / protocol["fixed_arm_family"]["indicator_arm_source"]["protocol_path"]
    indicator_hash = sha256_file(indicator_path)
    if indicator_hash != protocol["fixed_arm_family"]["indicator_arm_source"]["protocol_sha256"]:
        raise ValueError("Frozen indicator protocol hash changed")
    indicator_protocol = json.loads(indicator_path.read_text(encoding="utf-8"))
    indicator_arms = indicator_protocol["arms"]
    frozen_arms = protocol["fixed_arm_family"]["arms"]
    for arm in ("prior_utc_day_breakout", "wilder_rsi14_reclaim", "bollinger20_reentry"):
        if frozen_arms.get(arm) != indicator_arms.get(arm):
            raise ValueError(f"Frozen walk-forward rule differs from indicator protocol: {arm}")
    expected_count = (
        len(frozen_arms)
        * len(protocol["frozen_inputs"]["timeframes"])
        * len(protocol["frozen_inputs"]["groups"])
        * 2
    )
    if expected_count != protocol["dependence_and_multiplicity"]["primary_hypothesis_count"]:
        raise ValueError("Primary hypothesis count does not match the frozen arm family")
    return protocol


def read_snapshot(path: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]], int]:
    """Return parsed rows, row-level parse errors, and input row count."""
    opener = gzip.open if path.suffix == ".gz" else open
    rows: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    with opener(path, "rt", newline="", encoding="utf-8") as source:
        reader = csv.DictReader(source)
        if reader.fieldnames is None or any(field not in reader.fieldnames for field in REQUIRED_FIELDS):
            return rows, [{"row": 1, "reason": "missing_required_columns"}], 0
        for line_number, raw in enumerate(reader, start=2):
            try:
                row = {
                    "timestamp": int(raw["timestamp"]),
                    "symbol": raw["symbol"],
                    **{field: float(raw[field]) for field in REQUIRED_FIELDS[2:]},
                }
            except (TypeError, ValueError, KeyError, OverflowError):
                errors.append({"row": line_number, "reason": "unparseable_row"})
                continue
            rows.append(row)
    return rows, errors, len(rows) + len(errors)


def validate_row(row: dict[str, Any], step_ms: int) -> tuple[dict[str, Any] | None, str | None]:
    try:
        stamp = int(row["timestamp"])
        symbol = str(row["symbol"])
        values = {key: float(row[key]) for key in REQUIRED_FIELDS[2:]}
    except (TypeError, ValueError, KeyError, OverflowError):
        return None, "unparseable_row"
    if not symbol:
        return None, "empty_symbol"
    if stamp % step_ms:
        return None, "unaligned_timestamp"
    if not all(math.isfinite(value) for value in values.values()):
        return None, "non_finite_value"
    opened, high, low, close = (values[key] for key in ("open", "high", "low", "close"))
    if min(opened, high, low, close) <= 0:
        return None, "non_positive_price"
    if high < max(opened, close) or low > min(opened, close) or high < low:
        return None, "invalid_ohlc_order"
    if values["base_volume"] < 0 or values["quote_volume"] < 0:
        return None, "negative_volume"
    return {"timestamp": stamp, "symbol": symbol, **values}, None


def _missing_dates(stamps: set[int], start: int, end: int, step: int) -> list[str]:
    dates: list[str] = []
    for stamp in range(start, end, step):
        if stamp not in stamps:
            dates.append(iso_day(stamp))
    return sorted(set(dates))


def _audit_fold(
    fold: dict[str, Any],
    valid_rows: list[dict[str, Any]],
    expected_symbols: tuple[str, ...],
    granularity: str,
    reference_date: str,
    inspected_ranges: tuple[tuple[str, str], ...],
    previous_end_ms: int | None,
) -> dict[str, Any]:
    step = BAR_MS[granularity]
    start_ms = int(parse_utc(fold["validation_start_utc"]).timestamp() * 1000)
    end_ms = int(parse_utc(fold["validation_end_utc_exclusive"]).timestamp() * 1000)
    warmup_start_ms = start_ms - WARMUP_MS
    issues: list[str] = []
    duration_days = (end_ms - start_ms) / 86_400_000
    if end_ms <= start_ms or start_ms % step or end_ms % step:
        issues.append("invalid_or_unaligned_fold_bounds")
    if duration_days != 28:
        issues.append("fold_not_28_calendar_days")
    if start_ms < int(parse_utc(reference_date).timestamp() * 1000):
        issues.append("fold_not_forward_of_reference_date")
    if previous_end_ms is not None and start_ms != previous_end_ms:
        issues.append("folds_overlap_or_are_not_consecutive")
    for inspected_start, inspected_end in inspected_ranges:
        inspected_start_ms = int(parse_utc(inspected_start).timestamp() * 1000)
        inspected_end_ms = int(parse_utc(inspected_end).timestamp() * 1000)
        if start_ms < inspected_end_ms and end_ms > inspected_start_ms:
            issues.append("fold_overlaps_inspected_window")

    by_symbol: dict[str, set[int]] = defaultdict(set)
    for row in valid_rows:
        if warmup_start_ms <= row["timestamp"] < end_ms:
            by_symbol[row["symbol"]].add(row["timestamp"])
    symbols_report = []
    expected_count = (end_ms - warmup_start_ms) // step
    complete_grid = True
    for symbol in expected_symbols:
        stamps = by_symbol.get(symbol, set())
        missing = [
            stamp for stamp in range(warmup_start_ms, end_ms, step)
            if stamp not in stamps
        ]
        if missing:
            complete_grid = False
        symbols_report.append({
            "symbol": symbol,
            "expected_bars": expected_count,
            "observed_unique_bars": len(stamps),
            "missing_bars": len(missing),
            "missing_utc_dates": sorted({iso_day(stamp) for stamp in missing}),
            "warmup_complete": not any(stamp < start_ms for stamp in missing),
            "validation_grid_complete": not any(stamp >= start_ms for stamp in missing),
        })

    latest_entries = {}
    latest_signals = {}
    for horizon in (1, 2, 3):
        latest_entries[str(horizon)] = iso_utc(end_ms - horizon * step)
        latest_signals[str(horizon)] = iso_utc(end_ms - (horizon + 1) * step)
    data_ready = not issues and complete_grid
    return {
        "fold_id": fold["fold_id"],
        "validation_start_utc": fold["validation_start_utc"],
        "validation_end_utc_exclusive": fold["validation_end_utc_exclusive"],
        "calendar_days": duration_days,
        "warmup_start_utc": iso_utc(warmup_start_ms),
        "required_warmup_hours": WARMUP_MS / 3_600_000,
        "latest_admissible_entry_open_utc_by_horizon": latest_entries,
        "latest_admissible_signal_timestamp_utc_by_horizon": latest_signals,
        "symbols": symbols_report,
        "fold_issues": sorted(set(issues)),
        "future_data_complete": complete_grid,
        "fold_data_status": "DATA_READY" if data_ready else "NOT_READY",
        "event_minimum_status": "NOT_EVALUATED",
        "complete_outcome_windows_status": "DATA_READY" if data_ready else "NOT_READY",
    }


def audit_rows(
    rows: list[dict[str, Any]],
    granularity: str,
    *,
    parse_errors: list[dict[str, Any]] | None = None,
    expected_symbols: tuple[str, ...] = SYMBOLS,
    folds: list[dict[str, Any]] | None = None,
    inspected_ranges: tuple[tuple[str, str], ...] = (INSPECTED_RANGE,),
    reference_date: str = REFERENCE_DATE,
    source_path: Path | None = None,
    source_row_count: int | None = None,
) -> dict[str, Any]:
    if granularity not in BAR_MS:
        raise ValueError(f"Unsupported timeframe: {granularity}")
    protocol = load_protocol()
    step = BAR_MS[granularity]
    row_errors = list(parse_errors or [])
    valid_rows: list[dict[str, Any]] = []
    for index, row in enumerate(rows, start=2):
        validated, error = validate_row(row, step)
        if error:
            row_errors.append({"row": index, "reason": error})
        elif validated:
            valid_rows.append(validated)

    counts = Counter((row["symbol"], row["timestamp"]) for row in valid_rows)
    duplicate_count = sum(count - 1 for count in counts.values() if count > 1)
    duplicate_examples = [
        {"symbol": symbol, "timestamp_utc": iso_utc(stamp), "count": count}
        for (symbol, stamp), count in sorted(counts.items()) if count > 1
    ][:25]
    observed_symbols = sorted({row["symbol"] for row in valid_rows})
    symbol_set_matches = set(observed_symbols) == set(expected_symbols)
    if valid_rows:
        grid_start = min(row["timestamp"] for row in valid_rows)
        grid_end = max(row["timestamp"] for row in valid_rows) + step
        per_symbol = defaultdict(set)
        for row in valid_rows:
            per_symbol[row["symbol"]].add(row["timestamp"])
        source_coverage = []
        expected_grid_count = (grid_end - grid_start) // step
        for symbol in expected_symbols:
            stamps = per_symbol.get(symbol, set())
            missing = [
                stamp for stamp in range(grid_start, grid_end, step)
                if stamp not in stamps
            ]
            source_coverage.append({
                "symbol": symbol,
                "expected_bars": expected_grid_count,
                "observed_unique_bars": len(stamps),
                "missing_bars": len(missing),
                "missing_utc_dates": sorted({iso_day(stamp) for stamp in missing}),
            })
        date_grid = []
        cursor = datetime.fromtimestamp(grid_start / 1000, timezone.utc).date()
        final_date = datetime.fromtimestamp((grid_end - 1) / 1000, timezone.utc).date()
        while cursor <= final_date:
            day_start = int(datetime(cursor.year, cursor.month, cursor.day, tzinfo=timezone.utc).timestamp() * 1000)
            day_end = day_start + 86_400_000
            left, right = max(day_start, grid_start), min(day_end, grid_end)
            expected_today = len(range(left, right, step))
            for symbol in expected_symbols:
                observed_today = sum(left <= stamp < right for stamp in per_symbol.get(symbol, set()))
                date_grid.append({
                    "date_utc": cursor.isoformat(),
                    "symbol": symbol,
                    "expected_bars": expected_today,
                    "observed_bars": observed_today,
                    "missing_bars": expected_today - observed_today,
                })
            cursor += timedelta(days=1)
        source_window = [iso_utc(grid_start), iso_utc(grid_end)]
    else:
        source_coverage = [
            {"symbol": symbol, "expected_bars": 0, "observed_unique_bars": 0,
             "missing_bars": 0, "missing_utc_dates": []}
            for symbol in expected_symbols
        ]
        date_grid = []
        source_window = [None, None]

    missing_grid = sum(entry["missing_bars"] for entry in source_coverage)
    error_counts = Counter(entry["reason"] for entry in row_errors)
    normalized_folds = folds if folds is not None else protocol["reserved_forward_folds"]["folds"]
    fold_reports = []
    previous_end = None
    for fold in normalized_folds:
        current = _audit_fold(
            fold, valid_rows, expected_symbols, granularity, reference_date,
            inspected_ranges, previous_end,
        )
        fold_reports.append(current)
        previous_end = int(parse_utc(fold["validation_end_utc_exclusive"]).timestamp() * 1000)

    fold_data_ready = bool(fold_reports) and all(
        report["fold_data_status"] == "DATA_READY" for report in fold_reports
    )
    fold_count_ready = len(normalized_folds) == 3 and all(
        report["calendar_days"] == 28 for report in fold_reports
    )
    quality_ready = (
        not row_errors and duplicate_count == 0 and missing_grid == 0
        and symbol_set_matches and bool(valid_rows)
    )
    all_data_ready = quality_ready and fold_data_ready and fold_count_ready
    source_hash = None
    source_missing = False
    if source_path is not None:
        source_missing = not source_path.is_file()
        if not source_missing:
            source_hash = sha256_file(source_path)
    issue_hashes = {}
    if source_path is None:
        for relative in HASH_INPUTS:
            path = ROOT / relative
            if path.is_file():
                issue_hashes[relative] = sha256_file(path)

    return {
        "timeframe": granularity,
        "source_path": relative_path(source_path) if source_path else None,
        "source_sha256": source_hash,
        "source_missing": source_missing,
        "source_row_count": source_row_count if source_row_count is not None else len(rows),
        "valid_row_count": len(valid_rows),
        "source_window_utc": {"start_inclusive": source_window[0], "end_exclusive": source_window[1]},
        "observed_symbols": observed_symbols,
        "expected_symbols": list(expected_symbols),
        "symbol_panel_exact": symbol_set_matches,
        "row_error_count": len(row_errors),
        "row_error_counts_by_reason": dict(sorted(error_counts.items())),
        "row_error_examples": row_errors[:25],
        "duplicate_observation_count": duplicate_count,
        "duplicate_examples": duplicate_examples,
        "source_grid_missing_bar_count": missing_grid,
        "source_per_symbol_grid": source_coverage,
        "source_per_symbol_date_grid": date_grid,
        "quality_gate_status": "PASS" if quality_ready else "NOT_READY",
        "reserved_fold_count": len(fold_reports),
        "reserved_folds": fold_reports,
        "future_data_readiness": "DATA_READY" if all_data_ready else "NOT_READY",
        "event_count_and_statistical_gates": "NOT_EVALUATED",
        "source_version_sha256": issue_hashes,
    }


def audit_snapshot(path: Path, granularity: str) -> dict[str, Any]:
    if not path.is_file():
        return audit_rows(
            [], granularity, parse_errors=[{"row": None, "reason": "source_file_unavailable"}],
            source_path=path, source_row_count=0,
        )
    try:
        rows, parse_errors, count = read_snapshot(path)
    except (OSError, EOFError, gzip.BadGzipFile, UnicodeError) as error:
        return audit_rows(
            [], granularity, parse_errors=[{"row": None, "reason": f"source_read_error:{type(error).__name__}"}],
            source_path=path, source_row_count=0,
        )
    return audit_rows(
        rows, granularity, parse_errors=parse_errors, source_path=path,
        source_row_count=count,
    )


def build_report(input_paths: dict[str, Path]) -> dict[str, Any]:
    protocol = load_protocol()
    timeframes = {
        timeframe: audit_snapshot(path, timeframe)
        for timeframe, path in input_paths.items()
    }
    frozen_source_hashes = {}
    for relative, expected_hash in protocol["frozen_inputs"]["source_version_sha256"].items():
        path = ROOT / relative
        actual_hash = sha256_file(path) if path.is_file() else None
        frozen_source_hashes[relative] = {
            "expected_sha256": expected_hash,
            "actual_sha256": actual_hash,
            "matches": actual_hash == expected_hash,
        }
    source_versions_match = bool(frozen_source_hashes) and all(
        entry["matches"] for entry in frozen_source_hashes.values()
    )
    data_ready = bool(timeframes) and set(timeframes) == set(BAR_MS) and source_versions_match and all(
        result["future_data_readiness"] == "DATA_READY" for result in timeframes.values()
    )
    failed_gates = []
    for timeframe, result in timeframes.items():
        if result["quality_gate_status"] != "PASS":
            failed_gates.append(f"{timeframe}:snapshot_quality")
        for fold in result["reserved_folds"]:
            if fold["fold_data_status"] != "DATA_READY":
                failed_gates.append(f"{timeframe}:{fold['fold_id']}:future_grid_warmup_or_leakage")
    if not data_ready:
        failed_gates.append("future_validation_data_not_available_or_not_complete")
    if not source_versions_match:
        failed_gates.append("frozen_source_hash_missing_or_changed")
    failed_gates.append("event_minimums_and_empirical_inference_not_evaluated")
    protocol_hashes = {}
    if PROTOCOL_PATH.is_file():
        protocol_hashes[relative_path(PROTOCOL_PATH)] = sha256_file(PROTOCOL_PATH)
    protocol_hashes[relative_path(Path(__file__))] = sha256_file(Path(__file__))
    return {
        "report_id": "issue-22-walkforward-readiness-audit-v1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "audit_scope": "Offline snapshot and future-fold readiness audit only; no signals, returns, event counts, confidence intervals, or actual validation are computed.",
        "protocol_id": protocol["protocol_id"],
        "amends_protocol_id": protocol.get("amends_protocol_id"),
        "protocol_amendment": protocol.get("amendment"),
        "primary_arm_count": len(protocol["fixed_arm_family"]["arms"]),
        "primary_hypothesis_count": protocol["dependence_and_multiplicity"]["primary_hypothesis_count"],
        "indicator_arm_source": protocol["fixed_arm_family"]["indicator_arm_source"],
        "protocol_path": relative_path(PROTOCOL_PATH),
        "protocol_sha256": protocol_hashes.get(relative_path(PROTOCOL_PATH)),
        "protocol_status": protocol["status"],
        "overall_readiness": "NOT_READY" if not data_ready else "DATA_READY",
        "empirical_validation_status": "NOT_RUN",
        "future_validation_data_readiness": "DATA_READY" if data_ready else "NOT_READY",
        "frozen_source_versions_match": source_versions_match,
        "frozen_source_hashes": frozen_source_hashes,
        "required_gates_failed": sorted(set(failed_gates)),
        "no_zero_return_imputation": True,
        "timeframes": timeframes,
        "report_source_sha256": protocol_hashes,
        "interpretation": (
            "Readiness status is not performance evidence or a validation result. Existing inspected "
            "Sep 17-Nov 1, 2026 snapshots are development/exploration only. Missing future bars remain "
            "missing; no market calls or acquisition are performed."
        ),
        "cli_required_validation_exit_code": 2 if not data_ready else 2,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-5m", type=Path, default=DEFAULT_SNAPSHOTS["5m"])
    parser.add_argument("--input-15m", type=Path, default=DEFAULT_SNAPSHOTS["15m"])
    parser.add_argument(
        "--output", type=Path,
        default=ROOT / "research/results/walkforward-readiness.json",
    )
    args = parser.parse_args(argv)
    report = build_report({"5m": args.input_5m, "15m": args.input_15m})
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    print(
        f"{report['overall_readiness']}: offline readiness report saved to "
        f"{relative_path(args.output)}; empirical_validation_status=NOT_RUN"
    )
    return 0 if report["overall_readiness"] == "VALIDATION_READY" else 2


if __name__ == "__main__":
    sys.exit(main())
