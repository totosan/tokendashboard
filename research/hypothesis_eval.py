#!/usr/bin/env python3
"""Causal fixed-rule follow-up comparisons on saved Bitget candle snapshots."""

from __future__ import annotations

import argparse
import bisect
import csv
import gzip
import hashlib
import json
import math
import statistics
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

if __package__:
    from . import intraday_eval as existing
else:
    import intraday_eval as existing

BASE_MS = {"5m": 5 * 60_000, "15m": 15 * 60_000}
SPLIT_MS = int(datetime(2026, 10, 17, tzinfo=timezone.utc).timestamp() * 1000)
COSTS_BPS = (12, 22, 37)
TRADFI = {"TSLAUSDT", "NVDAUSDT", "AAPLUSDT", "COINUSDT"}
BTC_ETH = {"BTCUSDT", "ETHUSDT"}
RVOL_THRESHOLD = 1.5
EMA_FAST, EMA_SLOW = 20, 50
VWAP_RECLAIM_BPS = 0.0
BOX_BARS = 12
BOX_MAX_HEIGHT_PCT = 0.02
BOX_RETEST_TOLERANCE_PCT = 0.001
BOX_MAX_RETEST_BARS = 3

RULES = {
    "dashboard_breakout": (
        "Existing intraday_eval.breakout_signal; 3 rising oriented impulse candles, one "
        "opposing handle, then close beyond handle; 5-50% retracement, handle low above "
        "impulse origin, handle high <=0.2% above impulse peak, confirmation quote-volume "
        "/ handle quote-volume >=1.0."
    ),
    "three_close_momentum": (
        "Existing intraday_eval.momentum_signal; three strictly rising (long) or falling "
        "(short) closes; one signal at each qualifying close."
    ),
    "momentum_rvol_1_5": (
        "Three-close momentum, separately filtered: signal-bar quote_volume divided by "
        "the arithmetic mean of the prior 20 bars' quote_volume >=1.5."
    ),
    "momentum_1h_ema20_context": (
        "Three-close momentum, separately filtered: latest fully completed, UTC-aligned "
        "1h aggregate close is above its EMA20 for long / below for short."
    ),
    "momentum_4h_ema20_context": (
        "Three-close momentum, separately filtered: latest fully completed, UTC-aligned "
        "4h aggregate close is above its EMA20 for long / below for short."
    ),
    "ema20_50_cross": (
        "Standalone crossover: EMA20 crosses above EMA50 for long / below for short at "
        "signal close. Each EMA is seeded with its first-period SMA; alpha=2/(period+1)."
    ),
    "utc_session_vwap_reclaim": (
        "Standalone UTC-day VWAP reclaim: HLC3 weighted by base_volume from 00:00 UTC; "
        "signal when close crosses from below to above VWAP (long) or above to below "
        "(short), using current completed bar and prior same-day bar."
    ),
    "box12_breakout_retest": (
        "Standalone candidate: box is high/low of exactly the 12 bars preceding a "
        "breakout bar; box height / box midpoint <=2%. A completed close beyond the box "
        "must occur 1-3 bars before signal; intervening closes stay beyond its boundary. "
        "Retest bar touches within 0.1% of boundary and closes beyond it; signal at that "
        "retest close. First matching most-recent breakout only."
    ),
}


def read_snapshot(path: Path) -> list[dict[str, Any]]:
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt", newline="", encoding="utf-8") as source:
        rows = []
        for raw in csv.DictReader(source):
            row = {
                "timestamp": int(raw["timestamp"]),
                "symbol": raw["symbol"],
                **{key: float(raw[key]) for key in ("open", "high", "low", "close", "base_volume", "quote_volume")},
            }
            if not all(math.isfinite(row[key]) for key in row if key not in ("symbol",)):
                raise ValueError(f"Non-finite snapshot row: {raw!r}")
            rows.append(row)
    return rows


def segments(bars: list[dict[str, Any]], bar_ms: int) -> list[list[dict[str, Any]]]:
    """Split at missing/duplicate cadence so no signal lookback crosses a gap."""
    result: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []
    for bar in sorted(bars, key=lambda row: int(row["timestamp"])):
        if current and int(bar["timestamp"]) - int(current[-1]["timestamp"]) != bar_ms:
            result.append(current)
            current = []
        current.append(bar)
    if current:
        result.append(current)
    return result


def ema_series(values: list[float], period: int) -> list[float | None]:
    output: list[float | None] = [None] * len(values)
    if len(values) < period:
        return output
    value = statistics.mean(values[:period])
    output[period - 1] = value
    alpha = 2 / (period + 1)
    for index in range(period, len(values)):
        value = alpha * values[index] + (1 - alpha) * value
        output[index] = value
    return output


def completed_higher_timeframe_context(
    bars: list[dict[str, Any]], base_ms: int, higher_ms: int
) -> dict[int, tuple[float, float] | None]:
    """Return (last complete HTF close, its EMA20), keyed by base-bar timestamp."""
    bars_per_bin = higher_ms // base_ms
    grouped: dict[int, list[dict[str, Any]]] = defaultdict(list)
    by_stamp = {int(row["timestamp"]): row for row in bars}
    for row in bars:
        stamp = int(row["timestamp"])
        grouped[stamp // higher_ms * higher_ms].append(row)

    complete: list[tuple[int, float]] = []
    for start, members in sorted(grouped.items()):
        stamps = sorted(int(row["timestamp"]) for row in members)
        expected = list(range(start, start + higher_ms, base_ms))
        if stamps == expected and all(stamp in by_stamp for stamp in expected):
            complete.append((start + higher_ms, float(by_stamp[expected[-1]]["close"])))

    # An incomplete/missing bin breaks context continuity and restarts EMA warmup.
    ema_by_end: dict[int, tuple[float, float] | None] = {}
    run: list[tuple[int, float]] = []
    for item in complete:
        if run and item[0] - run[-1][0] != higher_ms:
            _store_htf_run(run, ema_by_end)
            run = []
        run.append(item)
    if run:
        _store_htf_run(run, ema_by_end)

    result = {}
    ends = sorted(ema_by_end)
    for row in bars:
        close_time = int(row["timestamp"]) + base_ms
        position = bisect.bisect_right(ends, close_time) - 1
        result[int(row["timestamp"])] = ema_by_end[ends[position]] if position >= 0 else None
    return result


def _store_htf_run(run: list[tuple[int, float]], destination: dict[int, tuple[float, float] | None]) -> None:
    ema = ema_series([value for _, value in run], 20)
    for (end, close), average in zip(run, ema):
        destination[end] = (close, average) if average is not None else None


def vwap_by_bar(bars: list[dict[str, Any]]) -> list[float]:
    current_day = None
    notional = volume = 0.0
    result = []
    for row in bars:
        day = int(row["timestamp"]) // 86_400_000
        if day != current_day:
            current_day, notional, volume = day, 0.0, 0.0
        base_volume = float(row["base_volume"])
        typical = (float(row["high"]) + float(row["low"]) + float(row["close"])) / 3
        notional += typical * base_volume
        volume += base_volume
        result.append(notional / volume if volume > 0 else math.nan)
    return result


def box_retest_signal(bars: list[dict[str, Any]], index: int, side: str) -> bool:
    """Evaluate the frozen 12-bar box / 1-3-bar retest definition."""
    sign = 1 if side == "long" else -1
    for breakout_index in range(index - 1, max(-1, index - BOX_MAX_RETEST_BARS - 1), -1):
        start = breakout_index - BOX_BARS
        if start < 0:
            continue
        box = bars[start:breakout_index]
        if len(box) != BOX_BARS:
            continue
        top = max(float(row["high"]) for row in box)
        bottom = min(float(row["low"]) for row in box)
        midpoint = (top + bottom) / 2
        if midpoint <= 0 or (top - bottom) / midpoint > BOX_MAX_HEIGHT_PCT:
            continue
        boundary = top if side == "long" else bottom
        breakout_close = float(bars[breakout_index]["close"])
        if sign * (breakout_close - boundary) <= 0:
            continue
        if any(sign * (float(bars[j]["close"]) - boundary) <= 0 for j in range(breakout_index + 1, index)):
            continue
        bar = bars[index]
        tolerance = boundary * BOX_RETEST_TOLERANCE_PCT
        touched = (
            float(bar["low"]) <= boundary + tolerance
            if side == "long" else float(bar["high"]) >= boundary - tolerance
        )
        if touched and sign * (float(bar["close"]) - boundary) > 0:
            return True
        # A newer breakout is authoritative; don't substitute an older box after it.
        return False
    return False


def _signal_arms(bars: list[dict[str, Any]], bar_ms: int) -> dict[tuple[int, str, str], bool]:
    arms: dict[tuple[int, str, str], bool] = {}
    context_1h = completed_higher_timeframe_context(bars, bar_ms, 60 * 60_000)
    context_4h = completed_higher_timeframe_context(bars, bar_ms, 4 * 60 * 60_000)
    global_index = {id(row): index for index, row in enumerate(bars)}
    for run in segments(bars, bar_ms):
        # Higher-timeframe series are computed over complete bins; base indicators restart
        # at every base-cadence gap to prevent borrowing stale lookback state.
        closes = [float(row["close"]) for row in run]
        fast, slow = ema_series(closes, EMA_FAST), ema_series(closes, EMA_SLOW)
        session_vwap = vwap_by_bar(run)
        for local_index, row in enumerate(run):
            index = global_index[id(row)]
            if index + 1 >= len(bars) or int(bars[index + 1]["timestamp"]) - int(row["timestamp"]) != bar_ms:
                continue
            stamp = int(row["timestamp"])
            if local_index >= 2:
                window = run[local_index - 2:local_index + 1]
                for side in ("long", "short"):
                    momentum = existing.momentum_signal(window, side)
                    if momentum:
                        arms[(stamp, side, "three_close_momentum")] = True
                        if local_index >= 20:
                            prior_mean = statistics.mean(float(item["quote_volume"]) for item in run[local_index - 20:local_index])
                            rvol = float(row["quote_volume"]) / prior_mean if prior_mean > 0 else 0
                            if rvol >= RVOL_THRESHOLD:
                                arms[(stamp, side, "momentum_rvol_1_5")] = True
                        for label, contexts in (
                            ("momentum_1h_ema20_context", context_1h),
                            ("momentum_4h_ema20_context", context_4h),
                        ):
                            value = contexts.get(stamp)
                            if value and value[1] is not None:
                                close, average = value
                                if (side == "long" and close > average) or (side == "short" and close < average):
                                    arms[(stamp, side, label)] = True
            if local_index >= 4:
                window = run[local_index - 4:local_index + 1]
                for side in ("long", "short"):
                    if existing.breakout_signal(window, side, min_volume=1.0):
                        arms[(stamp, side, "dashboard_breakout")] = True
            if fast[local_index] is not None and slow[local_index] is not None and local_index > 0:
                if fast[local_index - 1] is not None and slow[local_index - 1] is not None:
                    if fast[local_index - 1] <= slow[local_index - 1] and fast[local_index] > slow[local_index]:
                        arms[(stamp, "long", "ema20_50_cross")] = True
                    if fast[local_index - 1] >= slow[local_index - 1] and fast[local_index] < slow[local_index]:
                        arms[(stamp, "short", "ema20_50_cross")] = True
            if local_index > 0 and stamp // 86_400_000 == int(run[local_index - 1]["timestamp"]) // 86_400_000:
                previous = float(run[local_index - 1]["close"]) - session_vwap[local_index - 1]
                current = float(row["close"]) - session_vwap[local_index]
                if previous <= VWAP_RECLAIM_BPS * float(run[local_index - 1]["close"]) / 10_000 and current > 0:
                    arms[(stamp, "long", "utc_session_vwap_reclaim")] = True
                if previous >= -VWAP_RECLAIM_BPS * float(run[local_index - 1]["close"]) / 10_000 and current < 0:
                    arms[(stamp, "short", "utc_session_vwap_reclaim")] = True
            if local_index >= BOX_BARS + 1:
                for side in ("long", "short"):
                    if box_retest_signal(run, local_index, side):
                        arms[(stamp, side, "box12_breakout_retest")] = True
    # Existing breakout requires the configured timeframe's cadence.
    return arms


def evaluate(rows: list[dict[str, Any]], granularity: str, source_path: Path) -> dict[str, Any]:
    bar_ms = BASE_MS[granularity]
    existing.BAR_MS = bar_ms
    by_symbol: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_symbol[str(row["symbol"])].append(row)
    events: list[dict[str, Any]] = []
    for symbol, unsorted_bars in sorted(by_symbol.items()):
        bars = sorted(unsorted_bars, key=lambda item: int(item["timestamp"]))
        arms = _signal_arms(bars, bar_ms)
        indexed = {int(row["timestamp"]): index for index, row in enumerate(bars)}
        for (stamp, side, arm), _ in arms.items():
            index = indexed[stamp]
            signal, entry_bar = bars[index], bars[index + 1]
            entry = float(entry_bar["open"])
            sign = 1 if side == "long" else -1
            events.append({
                "symbol": symbol, "side": side, "arm": arm,
                "signal_timestamp": stamp, "entry_timestamp": int(entry_bar["timestamp"]),
                "period": "development" if int(entry_bar["timestamp"]) < SPLIT_MS else "out_of_sample",
                "gross_bps": sign * (float(entry_bar["close"]) / entry - 1) * 10_000,
                "mfe_bps": sign * (
                    float(entry_bar["high"] if side == "long" else entry_bar["low"]) / entry - 1
                ) * 10_000,
                "mae_bps": sign * (
                    float(entry_bar["low"] if side == "long" else entry_bar["high"]) / entry - 1
                ) * 10_000,
            })
    return _payload(events, granularity, source_path, rows)


def _stats(events: list[dict[str, Any]]) -> dict[str, Any]:
    gross = [float(event["gross_bps"]) for event in events]
    return {
        "n": len(gross),
        "mean_gross_bps": statistics.mean(gross) if gross else None,
        "median_gross_bps": statistics.median(gross) if gross else None,
        "win_rate_gross_pct": sum(value > 0 for value in gross) / len(gross) * 100 if gross else None,
        "mean_mfe_bps": statistics.mean(float(event["mfe_bps"]) for event in events) if gross else None,
        "mean_mae_bps": statistics.mean(float(event["mae_bps"]) for event in events) if gross else None,
        "mean_net_bps_by_round_trip_cost": {
            str(cost): statistics.mean(gross) - cost if gross else None for cost in COSTS_BPS
        },
        "win_rate_net_pct_by_round_trip_cost": {
            str(cost): sum(value - cost > 0 for value in gross) / len(gross) * 100 if gross else None
            for cost in COSTS_BPS
        },
    }


def _payload(events: list[dict[str, Any]], granularity: str, source_path: Path, rows: list[dict[str, Any]]) -> dict[str, Any]:
    groups = {
        "btc_eth": lambda symbol: symbol in BTC_ETH,
        "alts": lambda symbol: symbol not in BTC_ETH and symbol not in TRADFI,
        "stock_perps": lambda symbol: symbol in TRADFI,
    }
    arms = tuple(RULES)
    summaries = []
    for arm in arms:
        for group, includes in groups.items():
            symbols = sorted({str(row["symbol"]) for row in rows if includes(str(row["symbol"]))})
            for side in ("long", "short"):
                for period in ("development", "out_of_sample"):
                    subset = [event for event in events if event["arm"] == arm and event["side"] == side
                              and event["period"] == period and includes(event["symbol"])]
                    baseline = [event for event in events if event["arm"] == "three_close_momentum"
                                and event["side"] == side and event["period"] == period and includes(event["symbol"])]
                    result = {
                        "timeframe": granularity, "arm": arm, "asset_group": group,
                        "symbols": symbols, "side": side, "period": period,
                        **_stats(subset),
                        "baseline_retention_vs_three_close_momentum": (
                            len(subset) / len(baseline) if baseline else None
                        ),
                    }
                    summaries.append(result)
    start = min(int(row["timestamp"]) for row in rows)
    end = max(int(row["timestamp"]) for row in rows) + BASE_MS[granularity]
    return {
        "source_snapshot": str(source_path),
        "source_snapshot_sha256": hashlib.sha256(source_path.read_bytes()).hexdigest(),
        "source": "Saved Bitget USDT-FUTURES historical-candles snapshot; no network/API fetch.",
        "granularity": granularity,
        "range_start_utc": datetime.fromtimestamp(start / 1000, timezone.utc).isoformat(),
        "range_end_utc_exclusive": datetime.fromtimestamp(end / 1000, timezone.utc).isoformat(),
        "split_by_entry_timestamp_utc": datetime.fromtimestamp(SPLIT_MS / 1000, timezone.utc).isoformat(),
        "timeframes": [granularity],
        "sides": ["long", "short"],
        "groups": {
            "btc_eth": ["BTCUSDT", "ETHUSDT"],
            "alts": sorted({str(row["symbol"]) for row in rows if str(row["symbol"]) not in BTC_ETH | TRADFI}),
            "stock_perps": sorted(TRADFI & {str(row["symbol"]) for row in rows}),
        },
        "exact_rules": RULES,
        "parameters": {
            "base_bar_cadence_required": True, "entry": "next base-timeframe candle open",
            "outcome": "one next candle only; MFE/MAE from entry open to that candle high/low",
            "rvol_prior_bars": 20, "rvol_threshold": RVOL_THRESHOLD,
            "higher_timeframes": {"1h": "complete UTC bins only, EMA20; reset after missing bin; 20-bin warmup",
                                  "4h": "complete UTC bins only, EMA20; reset after missing bin; 20-bin warmup"},
            "ema_cross": {"fast": EMA_FAST, "slow": EMA_SLOW, "seed": "first-period simple average", "alpha": "2/(period+1)"},
            "vwap": "UTC calendar day; cumulative HLC3 * base_volume / cumulative base_volume; no cross-midnight",
            "box": {"lookback_bars": BOX_BARS, "max_height_pct_midpoint": BOX_MAX_HEIGHT_PCT * 100,
                    "retest_tolerance_pct": BOX_RETEST_TOLERANCE_PCT * 100,
                    "retest_window_bars": BOX_MAX_RETEST_BARS},
            "round_trip_cost_scenarios_bps": {
                "12": "Two 6 bps taker fees; historical fee constancy unverified.",
                "22": "12 bps assumed fees + 10 bps assumed spread/slippage.",
                "37": "12 bps assumed fees + 25 bps assumed spread/slippage.",
            },
        },
        "protocol": (
            "Fixed rules were declared before evaluation. Variants are separate one-at-a-time arms, "
            "not cumulatively optimized. Signals are event-level and can overlap; no portfolio sizing, "
            "funding, liquidation, execution, spread, queue, or market impact model. OOS timestamps "
            "were already inspected by the parent study; this is exploratory reuse, not untouched validation."
        ),
        "omissions_and_scope": [
            "No actual trade-level volume, order-book profile/POC/value area, RSI, Bollinger, daily levels, or walk-forward analysis.",
            "OHLCV VWAP proxy and fixed box definition are hypotheses, not validated strategy specifications.",
            "Only the saved 45-day, 12-symbol Bitget snapshots are used; no broader data and no Binance API.",
            "No guarantee or financial recommendation; scenarios are not measured execution results.",
        ],
        "bar_counts_by_symbol": {
            symbol: sum(str(row["symbol"]) == symbol for row in rows)
            for symbol in sorted({str(row["symbol"]) for row in rows})
        },
        "result_count": len(summaries),
        "results_by_arm_group_side_period": summaries,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--granularity", choices=tuple(BASE_MS), required=True)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    rows = read_snapshot(args.input)
    if not rows:
        raise SystemExit("Snapshot has no rows")
    result = evaluate(rows, args.granularity, args.input)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Wrote {result['result_count']} cells to {args.output}")


if __name__ == "__main__":
    main()
