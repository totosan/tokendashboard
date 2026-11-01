#!/usr/bin/env python3
"""Reproduce a one-bar evaluation of Bitget perpetual candles."""

from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
import math
import re
import statistics
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

API = "https://api.bitget.com/api/v2/mix/market/history-candles"
PRODUCT_TYPE = "USDT-FUTURES"
GRANULARITY = "15m"
BAR_MS = 15 * 60 * 1000
FIELDS = ("timestamp", "open", "high", "low", "close", "base_volume", "quote_volume")
DEFAULT_SYMBOLS = (
    "BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT",
    "XRPUSDT", "DOGEUSDT", "ADAUSDT", "LINKUSDT",
    "TSLAUSDT", "NVDAUSDT", "AAPLUSDT", "COINUSDT",
)
DEFAULT_TRADFI = ("TSLAUSDT", "NVDAUSDT", "AAPLUSDT", "COINUSDT")
ROUND_TRIP_COSTS_BPS = (12.0, 22.0, 37.0)


def parse_utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError(f"Timestamp must include a timezone: {value}")
    return parsed.astimezone(timezone.utc)


def timestamp_ms(value: datetime) -> int:
    return int(value.timestamp() * 1000)


def request_page(symbol: str, start_ms: int, end_ms: int) -> list[list[str]]:
    query = urlencode({
        "symbol": symbol,
        "productType": PRODUCT_TYPE,
        "granularity": GRANULARITY,
        "startTime": start_ms,
        "endTime": end_ms,
        "limit": 200,
    })
    request = Request(API + "?" + query, headers={"User-Agent": "tokendashboard-research/1.0"})
    for attempt in range(4):
        try:
            with urlopen(request, timeout=30) as response:
                payload = json.load(response)
            if payload.get("code") != "00000":
                raise RuntimeError(f"Bitget API error for {symbol}: {payload.get('code')} {payload.get('msg')}")
            data = payload.get("data")
            if not isinstance(data, list):
                raise RuntimeError(f"Bitget returned a non-list candle payload for {symbol}")
            return data
        except HTTPError as error:
            if error.code != 429 or attempt == 3:
                raise RuntimeError(f"Bitget HTTP {error.code} while reading {symbol}") from error
            time.sleep(2**attempt)
        except URLError as error:
            if attempt == 3:
                raise RuntimeError(f"Bitget request failed for {symbol}: {error}") from error
            time.sleep(2**attempt)
    raise RuntimeError(f"Bitget request exhausted retries for {symbol}")


def fetch_symbol(symbol: str, start_ms: int, end_ms: int) -> list[dict[str, float | int | str]]:
    rows: dict[int, dict[str, float | int | str]] = {}
    cursor = start_ms
    while cursor < end_ms:
        page_end = min(end_ms, cursor + 200 * BAR_MS)
        payload = request_page(symbol, cursor, page_end)
        page = []
        for raw in payload:
            if not isinstance(raw, list) or len(raw) < 7:
                raise RuntimeError(f"Unexpected candle shape for {symbol}: {raw!r}")
            try:
                stamp = int(raw[0])
                values = [float(value) for value in raw[1:7]]
            except (TypeError, ValueError) as error:
                raise RuntimeError(f"Invalid candle value for {symbol}: {raw!r}") from error
            if not all(math.isfinite(value) for value in values):
                raise RuntimeError(f"Non-finite candle value for {symbol}: {raw!r}")
            opened, high, low, closed, base_volume, quote_volume = values
            if (
                stamp < cursor or stamp + BAR_MS > page_end
                or stamp % BAR_MS
                or min(opened, high, low, closed) <= 0
                or high < max(opened, closed)
                or low > min(opened, closed)
                or min(base_volume, quote_volume) < 0
            ):
                continue
            page.append({
                "timestamp": stamp,
                "symbol": symbol,
                "open": opened,
                "high": high,
                "low": low,
                "close": closed,
                "base_volume": base_volume,
                "quote_volume": quote_volume,
            })
        for row in page:
            rows[int(row["timestamp"])] = row
        cursor = page_end
        time.sleep(0.075)
    return [rows[stamp] for stamp in sorted(rows)]


def write_snapshot(path: Path, rows: list[dict[str, float | int | str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "wt", newline="", encoding="utf-8") as output:
        writer = csv.DictWriter(output, fieldnames=(*FIELDS, "symbol"))
        writer.writeheader()
        writer.writerows(rows)


def read_snapshot(path: Path) -> list[dict[str, float | int | str]]:
    opener = gzip.open if path.suffix == ".gz" else open
    rows = []
    with opener(path, "rt", newline="", encoding="utf-8") as source:
        for row in csv.DictReader(source):
            try:
                parsed = {
                    "timestamp": int(row["timestamp"]),
                    "symbol": row["symbol"],
                    **{field: float(row[field]) for field in FIELDS[1:]},
                }
            except (KeyError, TypeError, ValueError) as error:
                raise RuntimeError(f"Invalid snapshot row: {row!r}") from error
            if not all(math.isfinite(float(parsed[field])) for field in FIELDS[1:]):
                raise RuntimeError(f"Non-finite snapshot row: {row!r}")
            rows.append(parsed)
    return rows


def write_events(path: Path, events: list[dict[str, float | int | str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "wt", newline="", encoding="utf-8") as output:
        columns = (
            "symbol", "side", "strategy", "signal_time_utc", "entry_time_utc",
            "period", "gross_bps", "mfe_bps", "mae_bps",
        )
        writer = csv.DictWriter(output, fieldnames=columns)
        writer.writeheader()
        writer.writerows(events)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def orient(row: dict[str, float | int | str], side: str) -> dict[str, float | int]:
    sign = 1 if side == "long" else -1
    first, second = sign * float(row["high"]), sign * float(row["low"])
    return {
        "timestamp": int(row["timestamp"]),
        "open": sign * float(row["open"]),
        "high": max(first, second),
        "low": min(first, second),
        "close": sign * float(row["close"]),
        "volume": float(row["quote_volume"]),
    }


def breakout_signal(window: list[dict[str, float | int]], side: str, min_volume: float = 1.0) -> dict[str, float] | None:
    if len(window) != 5 or side not in ("long", "short") or min_volume < 0:
        return None
    bars = [orient(row, side) for row in window]
    if any(bars[index]["timestamp"] - bars[index - 1]["timestamp"] != BAR_MS for index in range(1, 5)):
        return None
    impulse, handle, confirmation = bars[:3], bars[3], bars[4]
    if any(bar["close"] <= bar["open"] for bar in impulse):
        return None
    if any(impulse[index]["close"] <= impulse[index - 1]["close"] for index in range(1, 3)):
        return None
    if handle["close"] >= handle["open"]:
        return None
    origin = impulse[0]["open"]
    peak = max(bar["high"] for bar in impulse)
    swing = peak - origin
    low, top = handle["low"], handle["high"]
    retracement = (peak - low) / swing if swing > 0 else math.inf
    if not (swing > 0 and 0.05 <= retracement <= 0.5 and low > origin):
        return None
    if top > peak + abs(peak) * 0.002:
        return None
    volume_ratio = confirmation["volume"] / handle["volume"] if handle["volume"] > 0 else math.nan
    if (
        confirmation["close"] <= confirmation["open"]
        or confirmation["close"] <= top
        or not math.isfinite(volume_ratio)
        or volume_ratio < min_volume
    ):
        return None
    return {"retracement": retracement, "volume_ratio": volume_ratio, "trigger": top}


def momentum_signal(window: list[dict[str, float | int]], side: str) -> bool:
    if len(window) < 3:
        return False
    if any(
        int(window[index]["timestamp"]) - int(window[index - 1]["timestamp"]) != BAR_MS
        for index in range(1, len(window))
    ):
        return False
    closes = [float(row["close"]) for row in window[-3:]]
    if side == "long":
        return closes[0] < closes[1] < closes[2]
    return closes[0] > closes[1] > closes[2]


def evaluate_event(
    bars: list[dict[str, float | int | str]], index: int, side: str, kind: str, split_ms: int
) -> dict[str, float | int | str] | None:
    if index + 1 >= len(bars):
        return None
    entry_bar = bars[index + 1]
    entry = float(entry_bar["open"])
    sign = 1 if side == "long" else -1
    result = {
        "symbol": str(bars[index]["symbol"]),
        "side": side,
        "strategy": kind,
        "signal_time_utc": datetime.fromtimestamp(int(bars[index]["timestamp"]) / 1000, timezone.utc).isoformat(),
        "entry_time_utc": datetime.fromtimestamp(int(entry_bar["timestamp"]) / 1000, timezone.utc).isoformat(),
        "period": "development" if int(entry_bar["timestamp"]) < split_ms else "out_of_sample",
        "gross_bps": sign * (float(entry_bar["close"]) / entry - 1) * 10000,
        "mfe_bps": sign * (
            float(entry_bar["high"] if side == "long" else entry_bar["low"]) / entry - 1
        ) * 10000,
        "mae_bps": sign * (
            float(entry_bar["low"] if side == "long" else entry_bar["high"]) / entry - 1
        ) * 10000,
    }
    return result


def collect_events(
    rows: list[dict[str, float | int | str]], split_ms: int, min_volume: float
) -> list[dict[str, float | int | str]]:
    grouped: dict[str, list[dict[str, float | int | str]]] = {}
    for row in rows:
        grouped.setdefault(str(row["symbol"]), []).append(row)
    events = []
    for symbol, bars in sorted(grouped.items()):
        bars.sort(key=lambda row: int(row["timestamp"]))
        for index in range(len(bars) - 1):
            if index >= 4:
                for side in ("long", "short"):
                    if breakout_signal(bars[index - 4:index + 1], side, min_volume):
                        event = evaluate_event(bars, index, side, "dashboard_breakout", split_ms)
                        if event:
                            events.append(event)
            if index >= 2:
                for side in ("long", "short"):
                    if momentum_signal(bars[index - 2:index + 1], side):
                        event = evaluate_event(bars, index, side, "three_close_momentum_baseline", split_ms)
                        if event:
                            events.append(event)
    return events


def summarize(events: list[dict[str, float | int | str]]) -> list[dict[str, float | int | str | None]]:
    dimensions = sorted({
        (str(event["strategy"]), str(event["side"]), str(event["period"]), str(event["symbol"]))
        for event in events
    })
    summaries = []
    for strategy, side, period, symbol in dimensions:
        subset = [
            event for event in events
            if (event["strategy"], event["side"], event["period"], event["symbol"])
            == (strategy, side, period, symbol)
        ]
        gross = [float(event["gross_bps"]) for event in subset]
        wins = [value for value in gross if value > 0]
        losses = [value for value in gross if value < 0]
        summaries.append({
            "strategy": strategy,
            "side": side,
            "period": period,
            "symbol": symbol,
            "n": len(gross),
            "mean_gross_bps": statistics.mean(gross),
            "median_gross_bps": statistics.median(gross),
            "win_rate_gross_pct": sum(value > 0 for value in gross) / len(gross) * 100,
            "mean_win_bps": statistics.mean(wins) if wins else None,
            "mean_loss_bps": statistics.mean(losses) if losses else None,
            "profit_factor_event_level": sum(wins) / abs(sum(losses)) if losses else None,
            "mean_mfe_bps": statistics.mean(float(event["mfe_bps"]) for event in subset),
            "median_mfe_bps": statistics.median(float(event["mfe_bps"]) for event in subset),
            "mean_mae_bps": statistics.mean(float(event["mae_bps"]) for event in subset),
            "median_mae_bps": statistics.median(float(event["mae_bps"]) for event in subset),
            "mean_net_bps_by_round_trip_cost": {
                str(int(cost)): statistics.mean(gross) - cost for cost in ROUND_TRIP_COSTS_BPS
            },
            "win_rate_net_pct_by_round_trip_cost": {
                str(int(cost)): sum(value - cost > 0 for value in gross) / len(gross) * 100
                for cost in ROUND_TRIP_COSTS_BPS
            },
        })
    return summaries


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--granularity", choices=("5m", "15m"))
    parser.add_argument("--start", help="Inclusive UTC range start (ISO-8601)")
    parser.add_argument("--end", help="Exclusive UTC range end (ISO-8601)")
    parser.add_argument("--symbols", nargs="+", default=DEFAULT_SYMBOLS)
    parser.add_argument("--tradfi-symbols", nargs="*", default=DEFAULT_TRADFI)
    parser.add_argument("--min-volume", type=float, default=1.0)
    parser.add_argument("--snapshot", type=Path, help="Write downloaded candles to CSV/CSV.GZ")
    parser.add_argument("--input", type=Path, help="Evaluate a previously saved CSV/CSV.GZ snapshot")
    parser.add_argument("--summary", type=Path, help="Write summary JSON")
    parser.add_argument("--events", type=Path, help="Write event-level CSV")
    return parser.parse_args()


def main() -> None:
    global BAR_MS, GRANULARITY
    args = parse_args()
    if args.input and not args.granularity:
        raise SystemExit("--granularity is required when evaluating a saved snapshot")
    GRANULARITY = args.granularity or "15m"
    BAR_MS = {"5m": 5 * 60 * 1000, "15m": 15 * 60 * 1000}[GRANULARITY]
    if args.min_volume < 0:
        raise SystemExit("--min-volume must be non-negative")
    if args.input:
        rows = read_snapshot(args.input)
        if not rows:
            raise SystemExit(f"Snapshot contains no candles: {args.input}")
        start = min(int(row["timestamp"]) for row in rows)
        end = max(int(row["timestamp"]) for row in rows) + BAR_MS
        source = str(args.input)
    else:
        if not args.start or not args.end:
            raise SystemExit("--start and --end are required unless --input is used")
        start_time, end_time = parse_utc(args.start), parse_utc(args.end)
        start, end = timestamp_ms(start_time), timestamp_ms(end_time)
        if start >= end or start % BAR_MS or end % BAR_MS:
            raise SystemExit(f"Range must be positive and aligned to {GRANULARITY} UTC bars")
        symbols = list(dict.fromkeys(symbol.upper() for symbol in args.symbols))
        if not all(re.fullmatch(r"[A-Z0-9]{2,40}", symbol) for symbol in symbols):
            raise SystemExit("Symbols must be uppercase Bitget contract codes")
        rows = []
        for symbol in symbols:
            symbol_rows = fetch_symbol(symbol, start, end)
            if not symbol_rows:
                raise SystemExit(f"No complete {GRANULARITY} candles returned for {symbol}")
            rows.extend(symbol_rows)
        source = f"Bitget {API}"
        if args.snapshot:
            write_snapshot(args.snapshot, rows)
    split = start + (end - start) * 2 // 3
    events = collect_events(rows, split, args.min_volume)
    payload = {
        "source": source,
        "endpoint": API,
        "product_type": PRODUCT_TYPE,
        "granularity": GRANULARITY,
        "range_start_utc": datetime.fromtimestamp(start / 1000, timezone.utc).isoformat(),
        "range_end_utc_exclusive": datetime.fromtimestamp(end / 1000, timezone.utc).isoformat(),
        "development_oos_split_utc": datetime.fromtimestamp(split / 1000, timezone.utc).isoformat(),
        "symbols": sorted({str(row["symbol"]) for row in rows}),
        "tradfi_symbols": sorted(set(args.tradfi_symbols)),
        "minimum_breakout_volume_ratio": args.min_volume,
        "breakout_rule": "3 rising oriented impulse candles + 1 opposing handle + closed confirmation beyond handle; 5-50% retracement; handle low above impulse origin; handle high within 0.2% of impulse peak; confirmation quote-volume / handle quote-volume >= threshold.",
        "baseline_rule": f"3 strictly rising (long) or falling (short) {GRANULARITY} closes; signal at the third close.",
        "entry_exit_assumption": f"Signal is known at candle close; entry at next {GRANULARITY} candle open; exit at that candle close; MFE/MAE use that candle high/low. No spread, fill queue, gaps beyond OHLC, funding, or market impact.",
        "cost_scenarios_round_trip_bps": {
            "12": "Two taker fees at 6 bps per side, matching the BTCUSDT/selected stock contract snapshot observed 2026-11-01; historical fee constancy is unverified.",
            "22": "12 bps fee scenario plus 10 bps assumed round-trip spread/slippage.",
            "37": "12 bps fee scenario plus 25 bps assumed round-trip spread/slippage.",
        },
        "interpretation": "Signals overlap and are event-level observations, not a portfolio backtest. Fee/spread values are scenarios, not measured historical execution costs. No leverage is applied.",
        "bar_counts_by_symbol": {
            symbol: sum(str(row["symbol"]) == symbol for row in rows)
            for symbol in sorted({str(row["symbol"]) for row in rows})
        },
        "coverage_by_symbol": {
            symbol: {
                "expected_bars": (end - start) // BAR_MS,
                "observed_bars": len(symbol_rows),
                "missing_bars": (end - start) // BAR_MS - len(symbol_rows),
                "first_bar_utc": datetime.fromtimestamp(
                    int(symbol_rows[0]["timestamp"]) / 1000, timezone.utc
                ).isoformat(),
                "last_bar_utc": datetime.fromtimestamp(
                    int(symbol_rows[-1]["timestamp"]) / 1000, timezone.utc
                ).isoformat(),
            }
            for symbol in sorted({str(row["symbol"]) for row in rows})
            for symbol_rows in [[row for row in rows if str(row["symbol"]) == symbol]]
        },
        "results_by_strategy_side_period_symbol": summarize(events),
    }
    snapshot_path = args.input or args.snapshot
    if snapshot_path and snapshot_path.exists():
        payload["snapshot_sha256"] = sha256_file(snapshot_path)
    if args.events:
        write_events(args.events, events)
    encoded = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    if args.summary:
        args.summary.parent.mkdir(parents=True, exist_ok=True)
        args.summary.write_text(encoded, encoding="utf-8")
    else:
        print(encoded, end="")


if __name__ == "__main__":
    main()
