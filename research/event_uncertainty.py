#!/usr/bin/env python3
"""Describe event dependence using synchronized UTC-day bootstrap blocks."""

from __future__ import annotations

import argparse
import csv
import gzip
import json
import math
import random
import statistics
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path

from research.intraday_eval import ROUND_TRIP_COSTS_BPS, parse_utc, sha256_file


def percentile(values: list[float], probability: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * probability
    lower = math.floor(position)
    upper = math.ceil(position)
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def interval(values: list[float]) -> list[float | None]:
    return [percentile(values, 0.025), percentile(values, 0.975)]


def utc_days(start: datetime, end: datetime) -> list[str]:
    if start >= end or start.time() != datetime.min.time() or end.time() != datetime.min.time():
        raise ValueError("Period bounds must be increasing UTC midnight timestamps")
    return [
        (start + timedelta(days=index)).date().isoformat()
        for index in range((end - start).days)
    ]


def load_events(path: Path, summary: dict) -> list[dict]:
    step = {"5m": timedelta(minutes=5), "15m": timedelta(minutes=15)}[summary["granularity"]]
    start = parse_utc(summary["range_start_utc"])
    split = parse_utc(summary["development_oos_split_utc"])
    end = parse_utc(summary["range_end_utc_exclusive"])
    events = []
    seen = set()
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt", encoding="utf-8", newline="") as source:
        for row in csv.DictReader(source):
            entry = parse_utc(row["entry_time_utc"])
            signal = parse_utc(row["signal_time_utc"])
            expected_period = "development" if entry < split else "out_of_sample"
            gross = float(row["gross_bps"])
            key = (row["strategy"], row["symbol"], row["side"], entry)
            if (
                not math.isfinite(gross)
                or row["symbol"] not in summary["symbols"]
                or row["side"] not in ("long", "short")
                or row["strategy"] not in ("dashboard_breakout", "three_close_momentum_baseline")
                or row["period"] != expected_period
                or not start <= signal < entry
                or entry + step > end
                or entry - signal != step
                or entry.timestamp() % step.total_seconds()
                or key in seen
            ):
                raise ValueError(f"Invalid or duplicate event: {row!r}")
            seen.add(key)
            group = (
                "BTC_ETH" if row["symbol"] in ("BTCUSDT", "ETHUSDT")
                else "stock_perpetuals" if row["symbol"] in summary["tradfi_symbols"]
                else "altcoins"
            )
            events.append({
                **row, "gross_bps": gross, "day": entry.date().isoformat(), "group": group,
            })
    return events


def daily_totals(events: list[dict], days: list[str]) -> list[tuple[int, float]]:
    totals: dict[str, list] = {day: [0, 0.0] for day in days}
    for event in events:
        day = event["day"]
        if day not in totals:
            raise ValueError(f"Event day outside period: {day}")
        totals[day][0] += 1
        totals[day][1] += event["gross_bps"]
    return [(count, total) for count, total in totals.values()]


def sampled_mean(totals: list[tuple[int, float]], indices: list[int]) -> float | None:
    count = sum(totals[index][0] for index in indices)
    return sum(totals[index][1] for index in indices) / count if count else None


def describe(events: list[dict], days: list[str], draws: list[list[int]]) -> dict:
    totals = daily_totals(events, days)
    boot = [sampled_mean(totals, draw) for draw in draws]
    valid = [value for value in boot if value is not None]
    n = len(events)
    mean = statistics.mean(event["gross_bps"] for event in events) if n else None
    symbols = Counter(event["symbol"] for event in events)
    entries = Counter(event["entry_time_utc"] for event in events)
    gross_interval = interval(valid)
    return {
        "n_events": n,
        "calendar_days": len(days),
        "active_days": sum(count > 0 for count, _ in totals),
        "symbols_with_events": len(symbols),
        "events_by_symbol": dict(sorted(symbols.items())),
        "largest_symbol_event_share": max(symbols.values()) / n if n else None,
        "unique_entry_times": len(entries),
        "max_simultaneous_events": max(entries.values(), default=0),
        "zero_return_events": sum(event["gross_bps"] == 0 for event in events),
        "mean_gross_bps": mean,
        "day_block_bootstrap_95pct_mean_gross_bps": gross_interval,
        "bootstrap_valid_replicates": len(valid),
        "bootstrap_empty_replicates": len(boot) - len(valid),
        "cost_sensitivity": {
            str(int(cost)): {
                "mean_net_bps": mean - cost if mean is not None else None,
                "day_block_bootstrap_95pct_mean_net_bps": [
                    bound - cost if bound is not None else None for bound in gross_interval
                ],
            }
            for cost in ROUND_TRIP_COSTS_BPS
        },
    }


def analyze(events: list[dict], summary: dict, replicates: int = 2000, seed: int = 20261101) -> dict:
    if replicates < 100:
        raise ValueError("Use at least 100 bootstrap replicates")
    start = parse_utc(summary["range_start_utc"])
    split = parse_utc(summary["development_oos_split_utc"])
    end = parse_utc(summary["range_end_utc_exclusive"])
    results = []
    for period, left, right in (
        ("development", start, split), ("out_of_sample", split, end),
    ):
        days = utc_days(left, right)
        rng = random.Random(seed)
        draws = [[rng.randrange(len(days)) for _ in days] for _ in range(replicates)]
        for group in ("BTC_ETH", "altcoins", "stock_perpetuals"):
            for side in ("long", "short"):
                arms = {}
                daily = {}
                for strategy in ("dashboard_breakout", "three_close_momentum_baseline"):
                    subset = [
                        event for event in events
                        if (event["period"], event["group"], event["side"], event["strategy"])
                        == (period, group, side, strategy)
                    ]
                    arms[strategy] = describe(subset, days, draws)
                    daily[strategy] = daily_totals(subset, days)
                paired = []
                for draw in draws:
                    first = sampled_mean(daily["dashboard_breakout"], draw)
                    second = sampled_mean(daily["three_close_momentum_baseline"], draw)
                    if first is not None and second is not None:
                        paired.append(first - second)
                first_mean = arms["dashboard_breakout"]["mean_gross_bps"]
                second_mean = arms["three_close_momentum_baseline"]["mean_gross_bps"]
                results.append({
                    "period": period, "group": group, "side": side, "arms": arms,
                    "breakout_minus_baseline_mean_gross_bps": (
                        first_mean - second_mean
                        if first_mean is not None and second_mean is not None else None
                    ),
                    "synchronized_day_bootstrap_95pct_difference_bps": interval(paired),
                    "paired_valid_replicates": len(paired),
                })
    return {
        "granularity": summary["granularity"],
        "range_start_utc": summary["range_start_utc"],
        "development_oos_split_utc": summary["development_oos_split_utc"],
        "range_end_utc_exclusive": summary["range_end_utc_exclusive"],
        "seed": seed,
        "replicates": replicates,
        "block": "UTC calendar day, synchronously across symbols and both arms; empty days retained",
        "estimand": "event-weighted mean return; paired difference uses matched day resamples, not matched events",
        "limitations": [
            "Descriptive resampling sensitivity, not a validated trading edge or portfolio simulation.",
            "Within-day cross-symbol dependence is retained; dependence across days is not modeled.",
            "Short periods and sparse signals make percentile intervals unstable.",
            "Intervals are marginal, not multiplicity-corrected; no statistical discovery claims.",
            "OOS has already been inspected; this is exploratory reuse, not fresh validation.",
            "Cost scenarios are fixed assumptions; no measured fees, spread, slippage, funding or fills.",
            "Shared signal lookbacks, simultaneous symbols/arms and consecutive returns create dependence; event N is not independent N.",
        ],
        "results": results,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--events", type=Path, required=True)
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    summary = json.loads(args.summary.read_text(encoding="utf-8"))
    events = load_events(args.events, summary)
    dimensions = ("strategy", "side", "period", "symbol")
    actual_counts = Counter(tuple(event[key] for key in dimensions) for event in events)
    expected_counts = {
        tuple(row[key] for key in dimensions): row["n"]
        for row in summary["results_by_strategy_side_period_symbol"]
    }
    if actual_counts != expected_counts:
        raise ValueError("Per-strategy/side/period/symbol event counts differ from summary")
    result = analyze(events, summary)
    result["sources"] = {
        str(path): sha256_file(path) for path in (args.events, args.summary)
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
