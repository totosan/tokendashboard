#!/usr/bin/env python3
"""Offline fixed indicator comparisons; see the pre-recorded protocol JSON."""

from __future__ import annotations

import argparse
import json
import statistics
from collections import defaultdict
from pathlib import Path

from . import hypothesis_eval as helpers
from . import intraday_eval as existing

DAY_MS = 86_400_000
ARMS = ("prior_utc_day_breakout", "wilder_rsi14_reclaim", "bollinger20_reentry")
BASELINES = ("dashboard_breakout", "three_close_momentum")
PROTOCOL = Path(__file__).parent / "results/indicator-protocol.json"
GROUPS = {
    "btc_eth": helpers.BTC_ETH,
    "stock_perps": helpers.TRADFI,
}


def rsi14(closes: list[float]) -> list[float | None]:
    result = [None] * len(closes)
    if len(closes) < 15:
        return result
    changes = [right - left for left, right in zip(closes, closes[1:])]
    gain = statistics.mean(max(delta, 0) for delta in changes[:14])
    loss = statistics.mean(max(-delta, 0) for delta in changes[:14])
    for index in range(14, len(closes)):
        if index > 14:
            gain = (13 * gain + max(changes[index - 1], 0)) / 14
            loss = (13 * loss + max(-changes[index - 1], 0)) / 14
        result[index] = (
            50.0 if gain == loss == 0 else
            100.0 if loss == 0 else 100 - 100 / (1 + gain / loss)
        )
    return result


def bollinger20(closes: list[float]) -> list[tuple[float, float] | None]:
    result = [None] * len(closes)
    for index in range(19, len(closes)):
        window = closes[index - 19:index + 1]
        mean = statistics.mean(window)
        sigma = statistics.pstdev(window)
        if sigma > 0:
            result[index] = (mean - 2 * sigma, mean + 2 * sigma)
    return result


def signal_arms(bars: list[dict], bar_ms: int) -> set[tuple[int, str, str]]:
    """Signals depend on completed history only, independent of entry availability."""
    signals = set()
    if any(int(row["timestamp"]) % bar_ms for row in bars):
        raise ValueError("Unaligned candle timestamp")
    for run in helpers.segments(bars, bar_ms):
        closes = [float(row["close"]) for row in run]
        rsi, bands = rsi14(closes), bollinger20(closes)
        days = defaultdict(list)
        for index, row in enumerate(run):
            stamp = int(row["timestamp"])
            day = stamp // DAY_MS
            # Only earlier rows are in the daily cache; never consume a future day.
            prior = days.get(day - 1, [])
            if index > 0 and len(prior) == DAY_MS // bar_ms:
                start = (day - 1) * DAY_MS
                if [int(item["timestamp"]) for item in prior] == list(range(start, start + DAY_MS, bar_ms)):
                    high = max(float(item["high"]) for item in prior)
                    low = min(float(item["low"]) for item in prior)
                    if closes[index - 1] <= high and closes[index] > high:
                        signals.add((stamp, "long", ARMS[0]))
                    if closes[index - 1] >= low and closes[index] < low:
                        signals.add((stamp, "short", ARMS[0]))
            days[day].append(row)
            # Retain only the current and previous day.
            for old in list(days):
                if old < day - 1:
                    del days[old]
            if index > 0 and rsi[index - 1] is not None and rsi[index] is not None:
                if rsi[index - 1] <= 30 < rsi[index]:
                    signals.add((stamp, "long", ARMS[1]))
                if rsi[index - 1] >= 70 > rsi[index]:
                    signals.add((stamp, "short", ARMS[1]))
            if index > 0 and bands[index - 1] is not None and bands[index] is not None:
                if closes[index - 1] < bands[index - 1][0] and closes[index] > bands[index][0]:
                    signals.add((stamp, "long", ARMS[2]))
                if closes[index - 1] > bands[index - 1][1] and closes[index] < bands[index][1]:
                    signals.add((stamp, "short", ARMS[2]))
    return signals


def collect_events(rows: list[dict], bar_ms: int) -> list[dict]:
    by_symbol = defaultdict(list)
    for row in rows:
        by_symbol[row["symbol"]].append(row)
    events = []
    for bars in by_symbol.values():
        bars.sort(key=lambda row: int(row["timestamp"]))
        signals = signal_arms(bars, bar_ms)
        # Iterate runs so an otherwise valid signal never enters across a gap.
        for run in helpers.segments(bars, bar_ms):
            for index, row in enumerate(run[:-1]):
                for side in ("long", "short"):
                    for arm in ARMS:
                        if (int(row["timestamp"]), side, arm) in signals:
                            event = existing.evaluate_event(run, index, side, arm, helpers.SPLIT_MS)
                            event["arm"] = arm
                            events.append(event)
    return events


def group_for(symbol: str) -> str:
    return next((name for name, members in GROUPS.items() if symbol in members), "alts")


def summarize(events: list[dict], rows: list[dict], granularity: str) -> list[dict]:
    cells = []
    for arm in ARMS:
        for group in ("btc_eth", "alts", "stock_perps"):
            for side in ("long", "short"):
                for period in ("development", "out_of_sample"):
                    subset = [event for event in events if event["arm"] == arm
                              and group_for(event["symbol"]) == group
                              and event["side"] == side and event["period"] == period]
                    cells.append({
                        "timeframe": granularity, "arm": arm, "asset_group": group,
                        "side": side, "period": period,
                        "symbols": sorted({row["symbol"] for row in rows if group_for(row["symbol"]) == group}),
                        **helpers._stats(subset),
                    })
    return cells


def evaluate(source: Path, baseline_path: Path, granularity: str) -> dict:
    protocol = json.loads(PROTOCOL.read_text())
    baseline = json.loads(baseline_path.read_text())
    source_hash = existing.sha256_file(source)
    if baseline["source_snapshot_sha256"] != source_hash or baseline["granularity"] != granularity:
        raise ValueError("Baseline snapshot hash/timeframe mismatch")
    rows = helpers.read_snapshot(source)
    if not rows:
        raise ValueError("Empty snapshot")
    cells = summarize(collect_events(rows, helpers.BASE_MS[granularity]), rows, granularity)
    saved = [cell for cell in baseline["results_by_arm_group_side_period"] if cell["arm"] in BASELINES]
    expected = {(arm, group, side, period) for arm in BASELINES
                for group in ("btc_eth", "alts", "stock_perps")
                for side in ("long", "short") for period in ("development", "out_of_sample")}
    actual = {(cell["arm"], cell["asset_group"], cell["side"], cell["period"]) for cell in saved}
    if len(saved) != 24 or actual != expected:
        raise ValueError("Incomplete saved baseline cells")
    paths = [source, baseline_path, PROTOCOL, Path(__file__),
             Path(__file__).with_name("test_indicator_eval.py"),
             Path(helpers.__file__), Path(existing.__file__)]
    return {
        "granularity": granularity,
        "protocol": protocol,
        "sha256_by_source": {str(path): existing.sha256_file(path) for path in paths},
        "source_snapshot_sha256": source_hash,
        "baseline_provenance": "Copied existing saved baseline cells, not recalculated; matching snapshot hash required.",
        "baseline_exact_rules": {arm: baseline["exact_rules"][arm] for arm in BASELINES},
        "range_start_utc": baseline["range_start_utc"],
        "range_end_utc_exclusive": baseline["range_end_utc_exclusive"],
        "split_by_entry_timestamp_utc": baseline["split_by_entry_timestamp_utc"],
        "bar_counts_by_symbol": {symbol: sum(row["symbol"] == symbol for row in rows)
                                 for symbol in sorted({row["symbol"] for row in rows})},
        "result_count": len(cells) + len(saved),
        "results_by_arm_group_side_period": cells + saved,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--granularity", choices=tuple(helpers.BASE_MS), required=True)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = evaluate(args.input, args.baseline, args.granularity)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n")
    print(f"Wrote {result['result_count']} cells to {args.output}")


if __name__ == "__main__":
    main()
