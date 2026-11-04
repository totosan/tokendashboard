#!/usr/bin/env python3
"""Frozen-arm event evaluator, restricted to development data.

Run ``python -m research.walkforward_eval --source synthetic`` for a reproducible
offline smoke run, or ``--source inspected`` for the two exact hash-pinned saved
snapshots. There is deliberately no arbitrary input path or future-data mode.
``--output`` saves all result cells; ``--evidence-output`` saves a small digest.
Neither output is future validation, inference, an execution model, or P&L.

Development folds are explicitly NOT the reserved 28-day folds. Floors and
rules are unchanged, but these observations can never satisfy future gates.
Signal timestamps denote candle opens. Following the protocol's explicit
timestamp formula, signal-close availability and next-bar entry share a UTC
boundary; entry never uses the signal candle's open.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from . import hypothesis_eval as hypothesis
from . import indicator_eval as indicator
from . import intraday_eval as intraday
from . import walkforward_readiness as readiness

DAY_MS = 86_400_000
HORIZONS = (1, 2, 3)
COSTS = (12, 22, 37)
ARMS = tuple(hypothesis.RULES) + indicator.ARMS
PINNED_IMPLEMENTATIONS = (
    "research/intraday_eval.py",
    "research/hypothesis_eval.py",
    "research/indicator_eval.py",
    "research/regime_eval.py",
    "research/event_uncertainty.py",
    "research/results/indicator-protocol.json",
    "research/results/regime-protocol.json",
)


def milliseconds(value: str) -> int:
    return int(readiness.parse_utc(value).timestamp() * 1000)


DEVELOPMENT_START, DEVELOPMENT_END = map(milliseconds, readiness.INSPECTED_RANGE)


@dataclass(frozen=True)
class DevelopmentFold:
    fold_id: str
    start: int
    end: int


DEVELOPMENT_FOLDS = (
    DevelopmentFold("development-01", milliseconds("2026-09-21T00:00:00Z"),
                    milliseconds("2026-10-05T00:00:00Z")),
    DevelopmentFold("development-02", milliseconds("2026-10-05T00:00:00Z"),
                    milliseconds("2026-10-19T00:00:00Z")),
    DevelopmentFold("development-03", milliseconds("2026-10-19T00:00:00Z"),
                    DEVELOPMENT_END),
)


def frozen_configuration() -> tuple[dict, dict, dict]:
    """Fail closed if a pinned implementation or fixed family has changed."""
    protocol = readiness.load_protocol()
    hashes = {}
    for relative in PINNED_IMPLEMENTATIONS:
        actual = readiness.sha256_file(readiness.ROOT / relative)
        expected = protocol["frozen_inputs"]["source_version_sha256"][relative]
        if actual != expected:
            raise ValueError(f"Frozen source hash changed: {relative}")
        hashes[relative] = actual
    family = protocol["fixed_arm_family"]
    if set(family["arms"]) != set(ARMS) or len(ARMS) != 11:
        raise ValueError("Frozen eleven-arm family mismatch")
    if tuple(family["outcomes"]["diagnostic_horizons_base_bars"]) != HORIZONS:
        raise ValueError("Frozen horizons changed")
    if tuple(map(int, family["round_trip_cost_scenarios_bps"])) != COSTS:
        raise ValueError("Frozen costs changed")
    if protocol["reserved_forward_folds"]["warmup"]["required_calendar_hours_before_each_fold"] != 96:
        raise ValueError("Frozen warmup changed")
    minimums = protocol["readiness_and_minimum_evidence"]["minimum_future_validation"]
    floors = {
        "fold": tuple(map(int, re.findall(r"\d+", minimums[
            "per_fold_per_arm_group_side_timeframe_horizon"]))),
        "pooled": tuple(map(int, re.findall(r"\d+", minimums[
            "pooled_per_arm_group_side_timeframe_horizon"]))),
    }
    if floors != {"fold": (30, 10, 2), "pooled": (100, 20, 2)}:
        raise ValueError("Unrecognized frozen reporting floors")
    return protocol, hashes, floors


def check_folds(folds: tuple[DevelopmentFold, ...]) -> None:
    if not folds or len({fold.fold_id for fold in folds}) != len(folds):
        raise ValueError("Development folds need unique IDs")
    previous_end = None
    for fold in folds:
        if (not fold.fold_id.startswith("development-") or
                fold.start < DEVELOPMENT_START + readiness.WARMUP_MS or
                not fold.start < fold.end <= DEVELOPMENT_END or
                any(fold.start % step or fold.end % step for step in readiness.BAR_MS.values()) or
                (previous_end is not None and fold.start != previous_end)):
            raise ValueError("Only aligned, consecutive inspected-range development folds are permitted")
        previous_end = fold.end


def _integer_stamp(raw: dict) -> int:
    value = raw["timestamp"]
    if isinstance(value, bool) or not re.fullmatch(r"-?\d+", str(value)):
        raise ValueError("Timestamp must be an integer number of milliseconds")
    return int(value)


def prepare_rows(rows: list[dict], timeframe: str) -> tuple[dict[str, list[dict]], dict]:
    """Quarantine all copies of duplicate/invalid keys; never fill a missing bar.

    An unaligned corrupt observation invalidates its containing cadence bucket,
    conservatively restarting history there. Unlocatable corruption blocks the
    entire timeframe: its continuity cannot be established.
    """
    step = readiness.BAR_MS[timeframe]
    errors = Counter()
    keys = Counter()
    invalid = set()
    valid = {}
    unlocatable = False
    for raw in rows:
        try:
            stamp = _integer_stamp(raw)
        except (ValueError, KeyError, TypeError):
            errors["unparseable_timestamp"] += 1
            unlocatable = True
            continue
        # Check before feature/outcome processing, including otherwise invalid rows.
        if not DEVELOPMENT_START <= stamp < DEVELOPMENT_END:
            raise ValueError("Reserved/uninspected timestamps forbidden in development evaluator")
        symbol = raw.get("symbol")
        if symbol not in readiness.SYMBOLS:
            errors["non_panel_symbol"] += 1
            unlocatable = True
            continue
        key = (symbol, stamp)
        keys[key] += 1
        parsed, reason = readiness.validate_row(raw, step)
        if reason:
            errors[reason] += 1
            invalid.add((symbol, stamp // step * step))
        else:
            valid[key] = parsed
    duplicate_keys = {key for key, count in keys.items() if count > 1}
    invalid.update(duplicate_keys)
    grouped = {symbol: [] for symbol in readiness.SYMBOLS}
    if not unlocatable:
        for key, row in sorted(valid.items()):
            if key not in invalid:
                grouped[key[0]].append(row)
    observed = {raw.get("symbol") for raw in rows if isinstance(raw.get("symbol"), str)}
    return grouped, {
        "input_rows": len(rows),
        "usable_rows": sum(map(len, grouped.values())),
        "row_error_counts": dict(sorted(errors.items())),
        "duplicate_keys": len(duplicate_keys),
        "duplicate_extra_rows": sum(keys[key] - 1 for key in duplicate_keys),
        "quarantined_keys": len(invalid),
        "unlocatable_corruption_blocks_timeframe": unlocatable,
        "panel_exact": observed == set(readiness.SYMBOLS),
        "observed_symbols": sorted(observed),
    }


def frozen_signals(run: list[dict], step: int) -> set[tuple[int, str, str]]:
    """Reuse the frozen implementations, including signals with missing outcomes.

    hypothesis._signal_arms suppresses a final signal unless a next row exists.
    A presence-only sentinel enables that last signal. Its values are copies of
    known history; its signals are discarded and it is NEVER an outcome bar.
    The pinned features use only bins closing by each real signal's close, so
    the sentinel cannot supply feature information at an earlier real close.
    Call only on a validated, single-symbol contiguous run.
    """
    if not run:
        return set()
    sentinel = {**run[-1], "timestamp": run[-1]["timestamp"] + step}
    previous_step = intraday.BAR_MS
    try:
        # Both pinned momentum and dashboard rules use this module global.
        intraday.BAR_MS = step
        signals = set(hypothesis._signal_arms(run + [sentinel], step))
        signals.update(indicator.signal_arms(run, step))
    finally:
        intraday.BAR_MS = previous_step
    return {hit for hit in signals if hit[0] <= run[-1]["timestamp"]}


def entry_rejection(signal: int, entry: int, exit_close: int,
                    run_start: int, fold: DevelopmentFold, step: int) -> str | None:
    if not fold.start <= entry < fold.end:
        return "purged_boundary"
    if signal < fold.start or exit_close > fold.end:
        return "purged_boundary"
    if entry < fold.start + 3 * step or entry >= fold.end - 3 * step:
        return "embargoed"
    if entry - run_start < readiness.WARMUP_MS:
        return "insufficient_warmup"
    return None


def outcome(bars: dict[int, dict], signal: int, side: str, horizon: int,
            step: int) -> dict | None:
    entry_stamp = signal + step
    held = [bars.get(entry_stamp + index * step) for index in range(horizon)]
    if any(row is None for row in held):
        return None
    entry = held[0]["open"]
    sign = 1 if side == "long" else -1
    favorable = (max(row["high"] for row in held) if side == "long"
                 else min(row["low"] for row in held))
    adverse = (min(row["low"] for row in held) if side == "long"
               else max(row["high"] for row in held))
    return {
        "signal_timestamp": signal,
        "signal_close_timestamp": entry_stamp,
        "entry_timestamp": entry_stamp,
        "exit_close_timestamp": entry_stamp + horizon * step,
        "gross_bps": sign * (held[-1]["close"] / entry - 1) * 10_000,
        "mfe_bps": sign * (favorable / entry - 1) * 10_000,
        "mae_bps": sign * (adverse / entry - 1) * 10_000,
    }


def evaluate_fold(grouped: dict[str, list[dict]], timeframe: str,
                  fold: DevelopmentFold, groups: dict) -> tuple[list[dict], dict, dict]:
    """Return actual development events, exhaustive disposition counts, and grid evidence."""
    step = readiness.BAR_MS[timeframe]
    events = []
    counts = defaultdict(Counter)
    grid = []
    group_for = {symbol: group for group, symbols in groups.items() for symbol in symbols}
    left = fold.start - readiness.WARMUP_MS
    for symbol in readiness.SYMBOLS:
        bars = [row for row in grouped[symbol] if left <= row["timestamp"] < fold.end]
        indexed = {row["timestamp"]: row for row in bars}
        warmup_missing = sum(stamp not in indexed for stamp in range(left, fold.start, step))
        validation_missing = sum(stamp not in indexed for stamp in range(fold.start, fold.end, step))
        grid.append({
            "symbol": symbol,
            "expected_warmup_bars": readiness.WARMUP_MS // step,
            "missing_warmup_bars": warmup_missing,
            "expected_validation_bars": (fold.end - fold.start) // step,
            "missing_validation_bars": validation_missing,
        })
        # Restart ALL indicator state per fold and at every integrity/cadence gap.
        for run in hypothesis.segments(bars, step):
            for signal, side, arm in sorted(frozen_signals(run, step)):
                entry = signal + step
                # The last signal belongs to neither adjacent sample if entry
                # is outside this fold. Count it as purged in the originating fold.
                if signal < fold.start - step:
                    continue
                for horizon in HORIZONS:
                    key = (arm, group_for[symbol], side, horizon, fold.fold_id)
                    counter = counts[key]
                    counter["candidates"] += 1
                    rejection = entry_rejection(
                        signal, entry, entry + horizon * step, run[0]["timestamp"], fold, step)
                    if rejection:
                        counter[rejection] += 1
                        continue
                    label = outcome(indexed, signal, side, horizon, step)
                    if label is None:
                        counter["incomplete"] += 1
                        continue
                    counter["completed"] += 1
                    events.append({
                        "timeframe": timeframe, "fold_id": fold.fold_id,
                        "symbol": symbol, "asset_group": group_for[symbol],
                        "arm": arm, "side": side, "horizon": horizon, **label,
                    })
    return events, counts, {
        "fold_id": fold.fold_id,
        "start_utc": readiness.iso_utc(fold.start),
        "end_utc_exclusive": readiness.iso_utc(fold.end),
        "warmup_start_utc": readiness.iso_utc(left),
        "calendar_days": (fold.end - fold.start) / DAY_MS,
        "symbol_grids": grid,
        "complete_grid": all(not item["missing_warmup_bars"] and
                             not item["missing_validation_bars"] for item in grid),
    }


def summarize_cell(events: list[dict], counts: Counter, floor: tuple[int, int, int]) -> dict:
    n = len(events)
    dates = len({readiness.iso_day(event["entry_timestamp"]) for event in events})
    symbols = sorted({event["symbol"] for event in events})
    sufficient = n >= floor[0] and dates >= floor[1] and len(symbols) >= floor[2]
    # Use the same frozen descriptive stats and costs, but suppress ALL return
    # estimates when any event/date/symbol floor fails.
    stats = hypothesis._stats(events if sufficient else [])
    stats["n"] = n
    return {
        **stats, "distinct_entry_utc_dates": dates, "observed_symbols": symbols,
        "minimum_events": floor[0], "minimum_dates": floor[1], "minimum_symbols": floor[2],
        "floor_status": "PASS" if sufficient else "INSUFFICIENT_EVENTS",
        "estimate_status": "DEVELOPMENT_DESCRIPTIVE_ONLY" if sufficient else "NOT_ESTIMABLE",
        **{name: counts[name] for name in (
            "candidates", "completed", "incomplete", "purged_boundary",
            "embargoed", "insufficient_warmup")},
    }


def evaluate_development(rows_by_timeframe: dict[str, list[dict]], *,
                         source_kind: str,
                         folds: tuple[DevelopmentFold, ...] = DEVELOPMENT_FOLDS,
                         provenance: dict | None = None) -> dict:
    """In-memory development API. Dates are guarded even for synthetic inputs."""
    if source_kind not in ("synthetic", "inspected"):
        raise ValueError("Only synthetic or already-inspected development data are allowed")
    if set(rows_by_timeframe) - set(readiness.BAR_MS):
        raise ValueError("Unsupported timeframe")
    check_folds(folds)
    protocol, hashes, floors = frozen_configuration()
    groups = protocol["frozen_inputs"]["groups"]
    cells = []
    quality = {}
    for timeframe in readiness.BAR_MS:
        grouped, integrity = prepare_rows(rows_by_timeframe.get(timeframe, []), timeframe)
        event_buckets = defaultdict(list)
        all_counts = defaultdict(Counter)
        fold_grids = []
        for fold in folds:
            events, counts, grid = evaluate_fold(grouped, timeframe, fold, groups)
            fold_grids.append(grid)
            for event in events:
                base = (event["arm"], event["asset_group"], event["side"], event["horizon"])
                event_buckets[(*base, fold.fold_id)].append(event)
                event_buckets[(*base, "pooled")].append(event)
            for key, counter in counts.items():
                all_counts[key].update(counter)
                all_counts[(*key[:-1], "pooled")].update(counter)
        quality[timeframe] = {
            **integrity, "folds": fold_grids,
            "development_grid_status": "COMPLETE" if (
                integrity["panel_exact"] and not integrity["row_error_counts"]
                and not integrity["duplicate_keys"] and
                all(grid["complete_grid"] for grid in fold_grids)) else "NOT_READY",
        }
        for arm in ARMS:
            for group in groups:
                for side in ("long", "short"):
                    for horizon in HORIZONS:
                        for fold_id in [fold.fold_id for fold in folds] + ["pooled"]:
                            key = (arm, group, side, horizon, fold_id)
                            cells.append({
                                "timeframe": timeframe, "arm": arm, "asset_group": group,
                                "panel_symbols": groups[group], "side": side, "horizon": horizon,
                                "fold_id": fold_id,
                                **summarize_cell(event_buckets[key], all_counts[key],
                                                 floors["pooled" if fold_id == "pooled" else "fold"]),
                            })
    return {
        "report_id": "frozen-walkforward-development-evaluator-v1",
        "evaluation_status": "DEVELOPMENT_ONLY",
        "source_kind": source_kind,
        "empirical_future_validation_status": "NOT_RUN",
        "overall_readiness": "NOT_READY",
        "original_inference_status": "FAIL",
        "known_covariance_oracle_status": "INCONCLUSIVE",
        "inferential_analysis": "NOT_RUN; no p-values, intervals, or market-validity claims",
        "protocol_id": protocol["protocol_id"],
        "protocol_sha256": readiness.sha256_file(readiness.PROTOCOL_PATH),
        "frozen_source_sha256": hashes,
        "evaluator_sha256": readiness.sha256_file(Path(__file__)),
        "source_provenance": provenance or {"kind": "in-memory development fixtures"},
        "permitted_input_range_utc": list(readiness.INSPECTED_RANGE),
        "development_folds": [
            {"fold_id": fold.fold_id, "start_utc": readiness.iso_utc(fold.start),
             "end_utc_exclusive": readiness.iso_utc(fold.end)} for fold in folds
        ],
        "reserved_fold_policy": "Never loaded or evaluated; development folds cannot satisfy future gates",
        "signal_close_entry_convention": (
            "Signal timestamp is candle open; signal close and next candle entry-open share "
            "the boundary signal_timestamp + bar_ms, per the frozen explicit timestamp formula. "
            "They are separate price observations, not distinct clock instants."
        ),
        "unresolved_protocol_ambiguities": [
            "The prose 'strictly after signal close' conflicts with adjacent-candle "
            "signal-close/next-open clock equality. Development code follows the explicit "
            "entry_timestamp = signal_timestamp + one bar formula; the protocol is not amended."
        ],
        "cost_scenarios_bps": protocol["fixed_arm_family"]["round_trip_cost_scenarios_bps"],
        "cost_interpretation": "Assumed round-trip sensitivities subtracted once; not measured fees, fills, funding or P&L",
        "entry_price_limitation": (
            "Next-open outcomes are hypothetical OHLCV descriptors, NOT evidence of a "
            "post-signal executable price. The separately verified bounded G01 diagnostic "
            "found all 12 inspected AAPL 5m opens equal the previous official close and "
            "last observed pre-boundary trade, not the first observed in-bucket trade; "
            "adjacent receive partitions supplied no late target-hour events. This does "
            "not establish an executable entry or a universal candle convention, and "
            "does not change any frozen arm, protocol, or outcome formula."
        ),
        "dependence": "Events overlap and are dependent; floors do not establish power or independence",
        "count_unit": (
            "Arm/side/symbol signal x horizon disposition, not independent samples. "
            "Pooled totals sum all three horizons. Boundary rejects may appear in both "
            "adjacent fold counters; no completed outcome is reused across folds."
        ),
        "quality": quality,
        "result_count": len(cells),
        "cells": cells,
    }


def synthetic_rows(timeframe: str) -> list[dict]:
    """Deterministic OHLCV code fixture, not a simulated tradable market."""
    step = readiness.BAR_MS[timeframe]
    rows = []
    for symbol_index, symbol in enumerate(readiness.SYMBOLS):
        previous = 100.0
        for index, stamp in enumerate(range(DEVELOPMENT_START, DEVELOPMENT_END, step)):
            phase = (stamp - DEVELOPMENT_START) / DAY_MS
            close = 100 + 5 * math.sin(phase * math.pi / 2 + symbol_index / 3)
            close += 0.6 * math.sin(index / 7)
            opened = previous
            volume = 10.0 if index % 23 else 30.0
            rows.append({
                "timestamp": stamp, "symbol": symbol, "open": opened,
                "high": max(opened, close) + .05, "low": min(opened, close) - .05,
                "close": close, "base_volume": volume, "quote_volume": volume * close,
            })
            previous = close
    return rows


def inspected_inputs(protocol: dict) -> tuple[dict, dict]:
    """No caller-supplied path: only exact, previously inspected pinned inputs."""
    rows = {}
    provenance = {}
    for timeframe, config in protocol["frozen_inputs"]["timeframes"].items():
        relative = config["snapshot"]
        # Check the protocol path too, rather than allowing a changed protocol
        # to direct this development command to an arbitrary/reserved source.
        if readiness.ROOT / relative != readiness.DEFAULT_SNAPSHOTS[timeframe]:
            raise ValueError("Only the original inspected snapshot paths are permitted")
        path = readiness.DEFAULT_SNAPSHOTS[timeframe]
        expected = protocol["frozen_inputs"]["source_version_sha256"][relative]
        actual = readiness.sha256_file(path)
        if actual != expected:
            raise ValueError(f"Inspected snapshot hash mismatch: {relative}")
        parsed, errors, count = readiness.read_snapshot(path)
        if errors:
            raise ValueError(f"Inspected snapshot contains parse errors: {relative}")
        rows[timeframe] = parsed
        provenance[timeframe] = {"path": relative, "sha256": actual, "input_rows": count}
    return rows, provenance


def evidence_digest(report: dict) -> dict:
    """Small persistent evidence; full cells are reproducible, not silently omitted."""
    encoded = json.dumps(report["cells"], sort_keys=True, separators=(",", ":"), allow_nan=False)
    totals = {}
    for timeframe in readiness.BAR_MS:
        selected = [cell for cell in report["cells"]
                    if cell["timeframe"] == timeframe and cell["fold_id"] == "pooled"]
        totals[timeframe] = {
            "pooled_cells": len(selected),
            "zero_event_cells": sum(cell["n"] == 0 for cell in selected),
            "insufficient_cells": sum(cell["floor_status"] != "PASS" for cell in selected),
            **{name: sum(cell[name] for cell in selected) for name in (
                "candidates", "completed", "incomplete", "purged_boundary",
                "embargoed", "insufficient_warmup")},
        }
    return {
        **{key: report[key] for key in (
            "report_id", "evaluation_status", "source_kind", "overall_readiness",
            "empirical_future_validation_status", "original_inference_status",
            "known_covariance_oracle_status", "inferential_analysis",
            "protocol_id", "protocol_sha256", "frozen_source_sha256",
            "evaluator_sha256", "source_provenance", "permitted_input_range_utc",
            "development_folds", "reserved_fold_policy", "signal_close_entry_convention",
            "unresolved_protocol_ambiguities", "cost_scenarios_bps", "cost_interpretation",
            "entry_price_limitation", "dependence", "count_unit", "result_count")},
        "artifact_scope": "Small development smoke digest; all cells are emitted by --output, no event export",
        "cells_sha256": hashlib.sha256(encoded.encode()).hexdigest(),
        "pooled_disposition_totals_by_timeframe": totals,
        "development_grid_status": {key: value["development_grid_status"]
                                    for key, value in report["quality"].items()},
        "reproduction": (
            f"python -m research.walkforward_eval --source {report['source_kind']} "
            "--evidence-output research/results/walkforward-evaluator-development.json"
        ),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", choices=("synthetic", "inspected"), default="synthetic")
    parser.add_argument("--output", type=Path, help="Optional complete development cells JSON")
    parser.add_argument("--evidence-output", type=Path, help="Optional compact reproducible smoke digest")
    args = parser.parse_args(argv)
    protocol, _, _ = frozen_configuration()
    if args.source == "synthetic":
        rows = {timeframe: synthetic_rows(timeframe) for timeframe in readiness.BAR_MS}
        provenance = {
            "generator": "research.walkforward_eval.synthetic_rows",
            "deterministic": True, "seed": "no random inputs",
            "input_rows": {timeframe: len(value) for timeframe, value in rows.items()},
        }
    else:
        rows, provenance = inspected_inputs(protocol)
    report = evaluate_development(rows, source_kind=args.source, provenance=provenance)
    for path, payload in ((args.output, report), (args.evidence_output, evidence_digest(report))):
        if path is not None:
            # Never overwrite the frozen protocol, sources, snapshots, or audit.
            protected = {readiness.ROOT / name for name in
                         protocol["frozen_inputs"]["source_version_sha256"]}
            protected.update((readiness.PROTOCOL_PATH, Path(__file__),
                              readiness.ROOT / "research/results/walkforward-readiness.json"))
            if path.resolve() in {item.resolve() for item in protected}:
                raise ValueError("Cannot overwrite frozen/readiness inputs")
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n")
    print(f"DEVELOPMENT_ONLY: {report['result_count']} cells; future empirical validation NOT_RUN")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
