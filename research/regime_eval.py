#!/usr/bin/env python3
"""Causal regime analysis of saved Bitget events and OHLCV snapshots."""

from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
import math
import statistics
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


BAR_MS = {"5m": 5 * 60_000, "15m": 15 * 60_000}
SPLIT_MS = int(datetime(2026, 10, 17, tzinfo=timezone.utc).timestamp() * 1000)
COSTS_BPS = (12, 22, 37)
STRATEGIES = ("dashboard_breakout", "three_close_momentum_baseline")
GROUPS = {
    "btc_eth": {"BTCUSDT", "ETHUSDT"},
    "alts": {"ADAUSDT", "BNBUSDT", "DOGEUSDT", "LINKUSDT", "SOLUSDT", "XRPUSDT"},
    "stock_perps": {"AAPLUSDT", "COINUSDT", "NVDAUSDT", "TSLAUSDT"},
}
VOLATILITY_BUCKETS = ("low", "middle", "high")
TREND_BUCKETS = ("range", "trend")
PERIODS = ("development", "out_of_sample")
SIDES = ("long", "short")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_snapshot(path: Path) -> list[dict[str, Any]]:
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt", newline="", encoding="utf-8") as source:
        rows = []
        for raw in csv.DictReader(source):
            try:
                row = {
                    "timestamp": int(raw["timestamp"]),
                    "symbol": raw["symbol"],
                    **{
                        key: float(raw[key])
                        for key in ("open", "high", "low", "close", "base_volume", "quote_volume")
                    },
                }
            except (KeyError, TypeError, ValueError) as error:
                raise ValueError(f"Invalid snapshot row: {raw!r}") from error
            if not all(math.isfinite(value) for key, value in row.items() if key != "symbol"):
                raise ValueError(f"Non-finite snapshot row: {raw!r}")
            if (
                min(row["open"], row["high"], row["low"], row["close"]) <= 0
                or row["high"] < max(row["open"], row["close"])
                or row["low"] > min(row["open"], row["close"])
            ):
                raise ValueError(f"Invalid OHLC relationship: {raw!r}")
            rows.append(row)
    return rows


def read_events(path: Path) -> list[dict[str, Any]]:
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt", newline="", encoding="utf-8") as source:
        rows = []
        for raw in csv.DictReader(source):
            try:
                row = dict(raw)
                for key in ("gross_bps", "mfe_bps", "mae_bps"):
                    row[key] = float(raw[key])
                row["signal_ms"] = timestamp_ms(raw["signal_time_utc"])
                row["entry_ms"] = timestamp_ms(raw["entry_time_utc"])
            except (KeyError, TypeError, ValueError) as error:
                raise ValueError(f"Invalid saved event: {raw!r}") from error
            if row["side"] not in SIDES or row["strategy"] not in STRATEGIES:
                raise ValueError(f"Unexpected event dimensions: {raw!r}")
            if not all(math.isfinite(row[key]) for key in ("gross_bps", "mfe_bps", "mae_bps")):
                raise ValueError(f"Non-finite saved outcome: {raw!r}")
            rows.append(row)
    return rows


def timestamp_ms(value: str) -> int:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError(f"Timestamp must include a timezone: {value}")
    return int(parsed.astimezone(timezone.utc).timestamp() * 1000)


def contiguous_segments(rows: list[dict[str, Any]], bar_ms: int) -> list[list[dict[str, Any]]]:
    ordered = sorted(rows, key=lambda row: int(row["timestamp"]))
    result: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []
    previous = None
    for row in ordered:
        stamp = int(row["timestamp"])
        if stamp % bar_ms:
            raise ValueError(f"Unaligned candle timestamp {stamp} for cadence {bar_ms}")
        if previous is not None and stamp == previous:
            raise ValueError(f"Duplicate candle timestamp {stamp}")
        if current and stamp - int(current[-1]["timestamp"]) != bar_ms:
            result.append(current)
            current = []
        current.append(row)
        previous = stamp
    if current:
        result.append(current)
    return result


def type7_quantile(values: list[float], probability: float) -> float:
    if not values:
        raise ValueError("Quantile requires at least one observation")
    ordered = sorted(values)
    h = (len(ordered) - 1) * probability
    lower = math.floor(h)
    upper = math.ceil(h)
    weight = h - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


def features_for_segment(
    bars: list[dict[str, Any]], bar_ms: int
) -> dict[int, dict[str, Any]]:
    """Features for one cadence-contiguous segment; keys are candle-open labels."""
    features: dict[int, dict[str, Any]] = {}
    normalized_ranges: list[float | None] = [None] * len(bars)
    for index, bar in enumerate(bars):
        if index:
            prior_close = float(bars[index - 1]["close"])
            true_range = max(
                float(bar["high"]) - float(bar["low"]),
                abs(float(bar["high"]) - prior_close),
                abs(float(bar["low"]) - prior_close),
            )
            normalized_ranges[index] = 10_000 * true_range / float(bar["close"])

    volatility_values: list[float | None] = [None] * len(bars)
    for index in range(20, len(bars)):
        window = normalized_ranges[index - 19:index + 1]
        if all(value is not None for value in window):
            volatility_values[index] = statistics.mean(value for value in window if value is not None)
    for index, bar in enumerate(bars):
        stamp = int(bar["timestamp"])
        current_v = volatility_values[index]
        vol_bucket = None
        vol_q33 = vol_q67 = None
        if current_v is not None and index >= 120:
            prior = [value for value in volatility_values[index - 100:index] if value is not None]
            if len(prior) == 100:
                vol_q33 = type7_quantile(prior, 1 / 3)
                vol_q67 = type7_quantile(prior, 2 / 3)
                if current_v <= vol_q33:
                    vol_bucket = "low"
                elif current_v <= vol_q67:
                    vol_bucket = "middle"
                else:
                    vol_bucket = "high"

        er = None
        trend_bucket = None
        if index >= 20:
            displacement = abs(float(bar["close"]) - float(bars[index - 20]["close"]))
            path = sum(
                abs(float(bars[j]["close"]) - float(bars[j - 1]["close"]))
                for j in range(index - 19, index + 1)
            )
            er = displacement / path if path else 0.0
            trend_bucket = "range" if er <= 0.30 else "trend"
        features[stamp] = {
            "volatility_bps": current_v,
            "volatility_q33_bps": vol_q33,
            "volatility_q67_bps": vol_q67,
            "volatility_bucket": vol_bucket,
            "efficiency_ratio_20": er,
            "trend_range": trend_bucket,
            "feature_available_at_utc": datetime.fromtimestamp((stamp + bar_ms) / 1000, timezone.utc).isoformat(),
        }
    return features


def build_feature_map(
    rows: list[dict[str, Any]], bar_ms: int
) -> tuple[dict[tuple[str, int], dict[str, Any]], dict[str, list[list[dict[str, Any]]]]]:
    by_symbol: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_symbol[str(row["symbol"])].append(row)
    feature_map: dict[tuple[str, int], dict[str, Any]] = {}
    segments: dict[str, list[list[dict[str, Any]]]] = {}
    for symbol, symbol_rows in sorted(by_symbol.items()):
        symbol_segments = contiguous_segments(symbol_rows, bar_ms)
        segments[symbol] = symbol_segments
        for segment in symbol_segments:
            for stamp, feature in features_for_segment(segment, bar_ms).items():
                feature_map[(symbol, stamp)] = feature
    return feature_map, segments


def group_for(symbol: str) -> str:
    for group, members in GROUPS.items():
        if symbol in members:
            return group
    raise ValueError(f"Symbol not in frozen asset groups: {symbol}")


def period_for(entry_ms: int) -> str:
    return "development" if entry_ms < SPLIT_MS else "out_of_sample"


def verify_baseline(
    rows: list[dict[str, Any]],
    snapshot_rows: list[dict[str, Any]],
    snapshot_path: Path,
    source_summary_path: Path,
    event_path: Path,
    bar_ms: int,
) -> dict[str, Any]:
    source = json.loads(source_summary_path.read_text(encoding="utf-8"))
    expected_snapshot_hash = source.get("snapshot_sha256")
    actual_snapshot_hash = sha256_file(snapshot_path)
    if expected_snapshot_hash != actual_snapshot_hash:
        raise ValueError("Snapshot SHA-256 does not match the saved source summary")
    expected_counts = Counter({
        (
            item["strategy"],
            item["side"],
            item["period"],
            item["symbol"],
        ): int(item["n"])
        for item in source.get("results_by_strategy_side_period_symbol", [])
    })
    observed_counts = Counter(
        (row["strategy"], row["side"], row["period"], row["symbol"]) for row in rows
    )
    if expected_counts != observed_counts:
        raise ValueError(
            "Saved event-export per-symbol/strategy/side/period counts do not match source summary"
        )
    candle_keys = {(str(row["symbol"]), int(row["timestamp"])) for row in snapshot_rows}
    for event in rows:
        expected_entry = event["signal_ms"] + bar_ms
        if event["entry_ms"] != expected_entry:
            raise ValueError(f"Saved event entry is not next-bar open: {event}")
        if event["period"] != period_for(event["entry_ms"]):
            raise ValueError(f"Saved event period disagrees with entry-time split: {event}")
        if (event["symbol"], event["signal_ms"]) not in candle_keys:
            raise ValueError(f"Saved signal timestamp is not a candle-open label: {event}")
        if (event["symbol"], event["entry_ms"]) not in candle_keys:
            raise ValueError(f"Saved entry timestamp is not a candle-open label: {event}")
    return {
        "snapshot_sha256": actual_snapshot_hash,
        "event_export_sha256": sha256_file(event_path),
        "source_summary_sha256": sha256_file(source_summary_path),
        "event_rows": len(rows),
        "counts_by_strategy_side_period_symbol": [
            {
                "strategy": key[0],
                "side": key[1],
                "period": key[2],
                "symbol": key[3],
                "n": count,
            }
            for key, count in sorted(observed_counts.items())
        ],
        "per_symbol_counts_match_source_summary": True,
        "event_entry_timestamps_and_period_match": True,
        "signal_and_entry_candles_present_in_snapshot": True,
    }


def make_empty_cells(
    regime_names: tuple[str, ...], group: str | None = None, strategy: str | None = None
) -> dict[tuple[Any, ...], list[dict[str, Any]]]:
    cells = {}
    groups = (group,) if group is not None else tuple(GROUPS)
    strategies = (strategy,) if strategy is not None else STRATEGIES
    for item in strategies:
        for asset_group in groups:
            for side in SIDES:
                for period in PERIODS:
                    for regime in regime_names:
                        cells[(item, asset_group, side, period, regime)] = []
    return cells


def summarize_outcomes(events: list[dict[str, Any]]) -> dict[str, Any]:
    if not events:
        return {
            "n": 0,
            "mean_gross_bps": None,
            "median_gross_bps": None,
            "mean_mfe_bps": None,
            "mean_mae_bps": None,
            "win_rate_gross_pct": None,
            "mean_net_bps_by_round_trip_cost": {str(cost): None for cost in COSTS_BPS},
        }
    gross = [float(row["gross_bps"]) for row in events]
    return {
        "n": len(events),
        "mean_gross_bps": statistics.mean(gross),
        "median_gross_bps": statistics.median(gross),
        "mean_mfe_bps": statistics.mean(float(row["mfe_bps"]) for row in events),
        "mean_mae_bps": statistics.mean(float(row["mae_bps"]) for row in events),
        "win_rate_gross_pct": 100 * sum(value > 0 for value in gross) / len(gross),
        "mean_net_bps_by_round_trip_cost": {
            str(cost): statistics.mean(gross) - cost for cost in COSTS_BPS
        },
    }


def materialize_cells(
    cells: dict[tuple[Any, ...], list[dict[str, Any]]], feature_name: str
) -> list[dict[str, Any]]:
    output = []
    for key, events in sorted(cells.items()):
        strategy, group, side, period, regime = key
        output.append({
            "strategy": strategy,
            "asset_group": group,
            "side": side,
            "period": period,
            "regime": regime,
            **summarize_outcomes(events),
        })
    return output


def analyze_existing(
    events: list[dict[str, Any]],
    feature_map: dict[tuple[str, int], dict[str, Any]],
) -> dict[str, Any]:
    volatility_cells = make_empty_cells(VOLATILITY_BUCKETS)
    trend_cells = make_empty_cells(TREND_BUCKETS)
    unavailable = Counter()
    feature_available = Counter()
    for event in events:
        feature = feature_map.get((event["symbol"], event["signal_ms"]))
        if feature is None:
            unavailable["no_signal_bar"] += 1
            continue
        vol = feature["volatility_bucket"]
        trend = feature["trend_range"]
        if vol is None:
            unavailable["volatility_unavailable"] += 1
        else:
            key = (
                event["strategy"], group_for(event["symbol"]), event["side"],
                event["period"], vol,
            )
            volatility_cells[key].append(event)
            feature_available["volatility_events"] += 1
        if trend is None:
            unavailable["trend_range_unavailable"] += 1
        else:
            key = (
                event["strategy"], group_for(event["symbol"]), event["side"],
                event["period"], trend,
            )
            trend_cells[key].append(event)
            feature_available["trend_range_events"] += 1
    return {
        "event_rows": len(events),
        "volatility_unavailable_event_count": unavailable["volatility_unavailable"],
        "trend_range_unavailable_event_count": unavailable["trend_range_unavailable"],
        "signal_bar_missing_event_count": unavailable["no_signal_bar"],
        "volatility_classified_event_count": feature_available["volatility_events"],
        "trend_range_classified_event_count": feature_available["trend_range_events"],
        "by_volatility": materialize_cells(volatility_cells, "volatility_bucket"),
        "by_trend_range": materialize_cells(trend_cells, "trend_range"),
    }


def box_candidates(
    segments: dict[str, list[list[dict[str, Any]]]],
    feature_map: dict[tuple[str, int], dict[str, Any]],
    bar_ms: int,
) -> tuple[list[dict[str, Any]], Counter]:
    candidates: list[dict[str, Any]] = []
    coverage = Counter()
    for symbol, symbol_segments in segments.items():
        for bars in symbol_segments:
            for index in range(12, len(bars)):
                box = bars[index - 12:index]
                top = max(float(row["high"]) for row in box)
                bottom = min(float(row["low"]) for row in box)
                midpoint = (top + bottom) / 2
                if midpoint <= 0 or (top - bottom) / midpoint > 0.02:
                    continue
                previous_close = float(bars[index - 1]["close"])
                close = float(bars[index]["close"])
                for side in SIDES:
                    if side == "long":
                        qualifies = close > top and previous_close <= top
                    else:
                        qualifies = close < bottom and previous_close >= bottom
                    if not qualifies:
                        continue
                    signal_ms = int(bars[index]["timestamp"])
                    entry_ms = signal_ms + bar_ms
                    future_bars = bars[index + 1:index + 4]
                    complete = (
                        len(future_bars) == 3
                        and all(
                            int(row["timestamp"]) == entry_ms + offset * bar_ms
                            for offset, row in enumerate(future_bars)
                        )
                    )
                    period = period_for(entry_ms)
                    window_periods = [period_for(entry_ms + offset * bar_ms) for offset in range(3)]
                    crossing = any(value != period for value in window_periods)
                    feature = feature_map.get((symbol, signal_ms), {})
                    feature_vol = feature.get("volatility_bucket")
                    feature_trend = feature.get("trend_range")
                    event: dict[str, Any] = {
                        "symbol": symbol,
                        "asset_group": group_for(symbol),
                        "side": side,
                        "period": period,
                        "signal_ms": signal_ms,
                        "entry_ms": entry_ms,
                        "box_high": top,
                        "box_low": bottom,
                        "volatility_bucket": feature_vol,
                        "trend_range": feature_trend,
                        "window_complete": complete,
                        "split_crossing": crossing,
                    }
                    if not complete:
                        coverage["incomplete_window"] += 1
                    if crossing:
                        coverage["split_crossing"] += 1
                    if feature_vol is None:
                        coverage["volatility_unavailable"] += 1
                    if feature_trend is None:
                        coverage["trend_range_unavailable"] += 1
                    if complete:
                        entry_bar, late_bar = future_bars[0], future_bars[1]
                        first_failure_offset = next(
                            (
                                offset
                                for offset, row in enumerate(future_bars, start=1)
                                if bottom <= float(row["close"]) <= top
                            ),
                            None,
                        )
                        event["first_failure_offset"] = first_failure_offset
                        event["failed"] = first_failure_offset is not None
                        event["immediate"] = one_bar_outcome(entry_bar, side)
                        event["late"] = one_bar_outcome(late_bar, side)
                        coverage["complete_window"] += 1
                        if first_failure_offset is not None:
                            coverage["failed_complete"] += 1
                            coverage[f"first_failure_offset_{first_failure_offset}"] += 1
                        else:
                            coverage["nonfailed_complete"] += 1
                            coverage["no_failure_in_window"] += 1
                    if crossing:
                        coverage["crossing_breakouts"] += 1
                    candidates.append(event)
    return candidates, coverage


def one_bar_outcome(bar: dict[str, Any], side: str) -> dict[str, float]:
    entry = float(bar["open"])
    sign = 1 if side == "long" else -1
    favorable = float(bar["high"] if side == "long" else bar["low"])
    adverse = float(bar["low"] if side == "long" else bar["high"])
    return {
        "gross_bps": sign * (float(bar["close"]) / entry - 1) * 10_000,
        "mfe_bps": sign * (favorable / entry - 1) * 10_000,
        "mae_bps": sign * (adverse / entry - 1) * 10_000,
    }


def summarize_box_cell(events: list[dict[str, Any]]) -> dict[str, Any]:
    all_count = len(events)
    crossing = [event for event in events if event["split_crossing"]]
    incomplete = [event for event in events if not event["window_complete"]]
    eligible = [
        event for event in events if event["window_complete"] and not event["split_crossing"]
    ]
    failed = sum(bool(event["failed"]) for event in eligible)
    nonfailed = len(eligible) - failed
    failure_offsets = Counter(event["first_failure_offset"] for event in eligible)
    delayed_timing = {
        "before_delayed_entry": failure_offsets[1],
        "at_delayed_entry": failure_offsets[2],
        "after_delayed_entry": failure_offsets[3],
        "no_failure_in_window": failure_offsets[None],
    }

    def outcome(which: str) -> dict[str, Any]:
        values = [
            {**event[which], "symbol": event["symbol"]}
            for event in eligible
        ]
        result = summarize_outcomes(values)
        return result

    return {
        "qualifying_breakouts_n": all_count,
        "complete_three_bar_windows_n": sum(event["window_complete"] for event in events),
        "eligible_complete_non_crossing_n": len(eligible),
        "failed_n": failed,
        "nonfailed_n": nonfailed,
        "failure_rate_pct_complete_non_crossing": 100 * failed / len(eligible) if eligible else None,
        "first_failure_timing": {
            "denominator_eligible_complete_non_crossing_n": len(eligible),
            "failed_n": failed,
            "offset_1_bar_after_signal_n": failure_offsets[1],
            "offset_2_bars_after_signal_n": failure_offsets[2],
            "offset_3_bars_after_signal_n": failure_offsets[3],
            "no_failure_in_three_bar_window_n": failure_offsets[None],
            "relative_to_delayed_entry": delayed_timing,
        },
        "incomplete_window_n": len(incomplete),
        "split_crossing_n": len(crossing),
        "immediate_next_open_one_bar": outcome("immediate"),
        "one_bar_delayed_open_one_bar": outcome("late"),
    }


def analyze_box(
    candidates: list[dict[str, Any]], feature_name: str, regimes: tuple[str, ...]
) -> dict[str, Any]:
    cells: dict[tuple[str, str, str, str], list[dict[str, Any]]] = {}
    for group in GROUPS:
        for side in SIDES:
            for period in PERIODS:
                for regime in regimes:
                    cells[(group, side, period, regime)] = []
    feature_unavailable = 0
    for event in candidates:
        regime = event[feature_name]
        if regime is None:
            feature_unavailable += 1
            continue
        cells[(event["asset_group"], event["side"], event["period"], regime)].append(event)
    return {
        "qualifying_breakouts_n": len(candidates),
        "feature_unavailable_n": feature_unavailable,
        "by_group_side_entry_period_regime": [
            {
                "asset_group": group,
                "side": side,
                "period": period,
                "regime": regime,
                **summarize_box_cell(events),
            }
            for (group, side, period, regime), events in sorted(cells.items())
        ],
    }


def analyze(
    granularity: str,
    snapshot_path: Path,
    event_path: Path,
    source_summary_path: Path,
) -> dict[str, Any]:
    bar_ms = BAR_MS[granularity]
    snapshot = read_snapshot(snapshot_path)
    events = read_events(event_path)
    integrity = verify_baseline(
        events, snapshot, snapshot_path, source_summary_path, event_path, bar_ms
    )
    feature_map, segments = build_feature_map(snapshot, bar_ms)
    existing = analyze_existing(events, feature_map)
    candidates, box_coverage = box_candidates(segments, feature_map, bar_ms)
    vol_summary = analyze_box(candidates, "volatility_bucket", VOLATILITY_BUCKETS)
    trend_summary = analyze_box(candidates, "trend_range", TREND_BUCKETS)
    eligible_box = [
        event for event in candidates
        if event["window_complete"] and not event["split_crossing"]
    ]
    failed_box = sum(bool(event["failed"]) for event in eligible_box)
    nonfailed_box = len(eligible_box) - failed_box
    failure_offsets = Counter(event["first_failure_offset"] for event in eligible_box)
    feature_counts = Counter()
    for feature in feature_map.values():
        feature_counts["bars"] += 1
        if feature["volatility_bucket"] is not None:
            feature_counts["volatility_classified_bars"] += 1
        if feature["trend_range"] is not None:
            feature_counts["trend_range_classified_bars"] += 1
    return {
        "protocol_id": "issue-18-causal-regimes-v1",
        "granularity": granularity,
        "range_utc": {
            "start": datetime.fromtimestamp(min(row["timestamp"] for row in snapshot) / 1000, timezone.utc).isoformat(),
            "end_exclusive": datetime.fromtimestamp(
                (max(row["timestamp"] for row in snapshot) + bar_ms) / 1000, timezone.utc
            ).isoformat(),
        },
        "entry_split_utc": "2026-10-17T00:00:00+00:00",
        "source_integrity": integrity,
        "snapshot_bar_count": len(snapshot),
        "symbol_count": len(segments),
        "contiguous_segment_count": sum(len(items) for items in segments.values()),
        "feature_coverage": dict(feature_counts),
        "existing_events": existing,
        "fixed_box_breakouts": {
            "all_qualifying_breakouts_n": len(candidates),
            "outcome_window_coverage": {
                "all_qualifying_breakouts_n": len(candidates),
                "complete_three_bar_windows_n": box_coverage["complete_window"],
                "incomplete_window_n": box_coverage["incomplete_window"],
                "split_crossing_n": box_coverage["split_crossing"],
                "eligible_complete_non_crossing_n": len(eligible_box),
                "failed_n": failed_box,
                "nonfailed_n": nonfailed_box,
                "failure_rate_pct_complete_non_crossing": (
                    100 * failed_box / len(eligible_box) if eligible_box else None
                ),
                "first_failure_timing": {
                    "denominator_eligible_complete_non_crossing_n": len(eligible_box),
                    "failed_n": failed_box,
                    "offset_1_bar_after_signal_n": failure_offsets[1],
                    "offset_2_bars_after_signal_n": failure_offsets[2],
                    "offset_3_bars_after_signal_n": failure_offsets[3],
                    "no_failure_in_three_bar_window_n": failure_offsets[None],
                    "relative_to_delayed_entry": {
                        "before_delayed_entry": failure_offsets[1],
                        "at_delayed_entry": failure_offsets[2],
                        "after_delayed_entry": failure_offsets[3],
                        "no_failure_in_window": failure_offsets[None],
                    },
                },
            },
            "by_volatility": vol_summary,
            "by_trend_range": trend_summary,
        },
        "interpretation": (
            "Retrospective event/outcome summaries on a previously inspected sample, not a "
            "portfolio backtest, fresh validation, or evidence that any regime is predictive. "
            "MFE/MAE are excursions, not P&L; net values subtract stated cost scenarios only."
        ),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--granularity", choices=tuple(BAR_MS), required=True)
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--events", type=Path, required=True)
    parser.add_argument("--source-summary", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    result = analyze(args.granularity, args.snapshot, args.events, args.source_summary)
    result["reproducibility_hashes"] = {
        "snapshot_sha256": sha256_file(args.snapshot),
        "event_export_sha256": sha256_file(args.events),
        "source_summary_sha256": sha256_file(args.source_summary),
        "protocol_sha256": sha256_file(Path("research/results/regime-protocol.json")),
        "analysis_code_sha256": sha256_file(Path(__file__)),
        "test_code_sha256": sha256_file(Path("research/test_regime_eval.py")),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
