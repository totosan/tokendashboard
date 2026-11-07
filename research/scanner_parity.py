#!/usr/bin/env python3
"""Bounded synthetic comparison with the unchanged dashboard scanner modules."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import subprocess
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
MINUTE = 60_000
PATTERN = ROOT / "dist/pattern.js"
TRADFI = ROOT / "dist/tradfi.js"
BRIDGE = Path(__file__).with_name("scanner_parity_bridge.js")
MAX_ARTIFACT_BYTES = 8 * 1024 * 1024


def candle(stamp: int, opened: float, high: float, low: float, closed: float,
           volume: float = 100.0) -> list[float | int]:
    return [stamp, opened, high, low, closed, volume, volume]


def pattern_fixture(minutes: int = 1, confirmation: bool = True,
                    mirrored: bool = False) -> list[list[float | int]]:
    duration = minutes * MINUTE
    bars = [candle(i * duration, 100, 100.2, 99.8, 100) for i in range(10)]
    bars.extend([
        candle(10 * duration, 100, 101.2, 100, 101, 300),
        candle(11 * duration, 101, 103, 101, 102, 300),
        candle(12 * duration, 102, 104, 102, 103.5, 300),
        candle(13 * duration, 103.5, 103.7, 102.7, 102.8, 100),
        candle(14 * duration, 102.8, 103, 102.5, 102.6, 100),
    ])
    if confirmation:
        bars.append(candle(15 * duration, 102.6, 104.1, 102.6, 104, 150))
    if minutes > 1:
        minute_bars = []
        for row in bars:
            stamp, opened, high, low, closed, volume, _ = row
            minute_bars.extend(
                candle(stamp + offset * MINUTE, opened, high, low, closed,
                       volume / minutes)
                for offset in range(minutes)
            )
        bars = minute_bars
    if mirrored:
        bars = [
            [row[0], 200 - row[1], 200 - row[3], 200 - row[2],
             200 - row[4], row[5], row[6]]
            for row in bars
        ]
    return bars


def tradfi_fixture(confirmation: bool = False, close_above: bool = True,
                   low: float = 102.0) -> list[list[float | int]]:
    bars = [
        candle(0, 100, 100.2, 99.8, 100),
        candle(MINUTE, 100, 100.2, 99.8, 100),
        candle(2 * MINUTE, 100, 101.2, 100, 101, 300),
        candle(3 * MINUTE, 101, 103, 101, 102, 300),
        candle(4 * MINUTE, 102, 104, 102, 103.5, 300),
        candle(5 * MINUTE, 103.5, 103.7, 102.6, 102.8, 100),
        candle(6 * MINUTE, 102.8, 103, low, 102.6, 100),
    ]
    if confirmation:
        close = 103.3 if close_above else 102.9
        bars.append(candle(7 * MINUTE, 102.7, 103.4, low + 0.1, close, 120))
    return bars


def _case(name: str, scanner: str, bars: list[list[float | int]],
          duration: int, end: int | None = None, **kwargs: Any) -> dict[str, Any]:
    return {
        "name": name,
        "scanner": scanner,
        "candles": bars,
        "end": end if end is not None else int(bars[-1][0]) + duration,
        **kwargs,
    }


def fixture_cases() -> list[dict[str, Any]]:
    pattern_1m = pattern_fixture()
    pattern_5m = pattern_fixture(minutes=5)
    pattern_gap = pattern_fixture()
    pattern_gap.pop(11)
    pattern_short = pattern_fixture(mirrored=True)
    pattern_future = pattern_fixture()
    pattern_future.extend([
        candle(16 * MINUTE, 103.5, 110, 103.4, 109, 900),
        candle(17 * MINUTE, 109, 112, 108, 111, 900),
    ])
    cases = [
        _case("pattern-1m-pullback", "pattern", pattern_fixture(confirmation=False),
              MINUTE, options={"minutes": 1, "pullbackBars": 2}),
        _case("pattern-1m-confirmed", "pattern", pattern_1m, MINUTE,
              options={"minutes": 1, "pullbackBars": 2}),
        _case("pattern-5m-confirmed", "pattern", pattern_5m, 5 * MINUTE,
              options={"minutes": 5, "pullbackBars": 2}),
        _case("pattern-short-confirmed", "pattern", pattern_short, MINUTE,
              options={"minutes": 1, "pullbackBars": 2}),
        _case("pattern-gap", "pattern", pattern_gap, MINUTE,
              options={"minutes": 1, "pullbackBars": 2}),
        _case("pattern-unsupported-2m", "pattern", pattern_1m, MINUTE,
              options={"minutes": 2}),
        _case("pattern-unsupported-pullback", "pattern", pattern_1m, MINUTE,
              options={"minutes": 1, "pullbackBars": 1}),
        _case("pattern-future-invariance", "pattern", pattern_future, MINUTE,
              end=16 * MINUTE, options={"minutes": 1, "pullbackBars": 2}),
        _case("tradfi-watch", "tradfi", tradfi_fixture(), MINUTE, minImpulse=3),
        _case("tradfi-triggered", "tradfi", tradfi_fixture(confirmation=True), MINUTE,
              minImpulse=3),
        _case("tradfi-high-with-close-below", "tradfi",
              tradfi_fixture(confirmation=True, close_above=False), MINUTE, minImpulse=3),
        _case("tradfi-retrace-half-inclusive", "tradfi",
              tradfi_fixture(low=102.0), MINUTE, minImpulse=3),
        _case("tradfi-reject-over-retrace", "tradfi",
              tradfi_fixture(low=101.99), MINUTE, minImpulse=3),
    ]
    tradfi_gap = tradfi_fixture(confirmation=True)
    tradfi_gap.pop(3)
    cases.append(_case("tradfi-gap", "tradfi", tradfi_gap, MINUTE, minImpulse=3))
    tradfi_future = tradfi_fixture()
    tradfi_future.extend([
        candle(7 * MINUTE, 102.6, 120, 102.5, 119),
        candle(8 * MINUTE, 119, 125, 118, 124),
    ])
    cases.append(_case("tradfi-future-invariance", "tradfi", tradfi_future,
                       MINUTE, end=7 * MINUTE, minImpulse=3))
    tradfi_short = [
        [row[0], 200 - row[1], 200 - row[3], 200 - row[2],
         200 - row[4], row[5], row[6]]
        for row in tradfi_fixture()
    ]
    cases.append(_case("tradfi-short-unsupported", "tradfi", tradfi_short,
                       MINUTE, minImpulse=0))
    exact_threshold = tradfi_fixture()
    exact_threshold[4][4] = 103
    cases.append(_case("tradfi-exact-min-impulse", "tradfi", exact_threshold,
                       MINUTE, minImpulse=3))
    five_minute = [
        candle(i * 5 * MINUTE, 100 + i, 101 + i, 99 + i, 100 + i)
        for i in range(6)
    ]
    cases.append(_case("tradfi-5m-unsupported", "tradfi", five_minute,
                       5 * MINUTE, minImpulse=0))
    if len(cases) > 32:
        raise ValueError("Synthetic suite exceeded its hard case limit")
    return cases


def aggregate_reference(raw: list[list[Any]], minutes: int, end: int) -> list[list[float | int]]:
    duration = minutes * MINUTE
    groups: dict[int, dict[int, list[float]]] = {}
    for row in raw:
        values = [float(value) for value in row[:7]]
        if (
            len(values) < 7 or not all(math.isfinite(value) for value in values)
            or values[0] % MINUTE or values[0] + MINUTE > end
            or values[1] <= 0 or values[4] <= 0
            or values[2] < max(values[1], values[4])
            or values[3] > min(values[1], values[4]) or values[6] < 0
        ):
            continue
        stamp = int(values[0])
        bucket = stamp // duration * duration
        if bucket + duration > end:
            continue
        groups.setdefault(bucket, {})[stamp] = values
    result = []
    for stamp, group in groups.items():
        if len(group) != minutes:
            continue
        rows = [group.get(stamp + i * MINUTE) for i in range(minutes)]
        if any(row is None for row in rows):
            continue
        complete = [row for row in rows if row is not None]
        result.append([
            stamp, complete[0][1], max(row[2] for row in complete),
            min(row[3] for row in complete), complete[-1][4],
            sum(row[5] for row in complete), sum(row[6] for row in complete),
        ])
    return sorted(result, key=lambda row: row[0])


def pattern_reference(raw: list[list[Any]], end: int,
                      options: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    opts = {
        "minutes": 1, "pullbackBars": 3, "minImpulse": 1, "minVolume": 1.5,
        "maxRetracement": 0.5, "requireQuiet": True, **(options or {}),
    }
    minutes, pullback_bars = opts["minutes"], opts["pullbackBars"]
    if minutes not in (1, 5) or pullback_bars not in (2, 3, 4):
        return []
    candles = aggregate_reference(raw, minutes, end)
    duration = minutes * MINUTE
    last_closed = end // duration * duration
    if not candles or candles[-1][0] + duration != last_closed:
        return []
    found = []
    for side in ("long", "short"):
        sign = 1 if side == "long" else -1
        bars = []
        for c in candles:
            oriented_high, oriented_low = (sign * c[2], sign * c[3])
            bars.append({
                "t": c[0], "o": sign * c[1],
                "h": max(oriented_high, oriented_low),
                "l": min(oriented_high, oriented_low), "c": sign * c[4], "v": c[6],
            })
        for confirmed in (False, True):
            pb_end = len(bars) - (1 if confirmed else 0)
            pb_start = pb_end - pullback_bars
            if pb_start < 12:
                continue
            pb = bars[pb_start:pb_end]
            if any(
                b["c"] >= b["o"] or (i > 0 and b["c"] >= pb[i - 1]["c"])
                for i, b in enumerate(pb)
            ):
                continue
            for length in range(2, 7):
                start = pb_start - length
                if start < 10:
                    continue
                baseline = bars[start - 10:start]
                impulse = bars[start:pb_start]
                segment = bars[start - 10:]
                if any(
                    segment[i]["t"] - segment[i - 1]["t"] != duration
                    for i in range(1, len(segment))
                ):
                    continue
                origin = impulse[0]["o"]
                finish = impulse[-1]["c"]
                peak = max(b["h"] for b in impulse)
                low = min(b["l"] for b in pb)
                swing = peak - origin
                impulse_pct = (finish - origin) / abs(origin) * 100
                baseline_level = max(b["h"] for b in baseline)
                if (
                    not swing > 0 or impulse_pct < opts["minImpulse"]
                    or finish <= baseline_level or origin > baseline_level
                    or sum(b["c"] > b["o"] for b in impulse) < math.ceil(length * 2 / 3)
                    or finish < peak - swing * 0.2
                ):
                    continue
                impulse_average = sum(b["v"] for b in impulse) / length
                baseline_average = sum(b["v"] for b in baseline) / 10
                pullback_average = sum(b["v"] for b in pb) / pullback_bars
                volume_ratio = impulse_average / baseline_average if baseline_average > 0 else 0
                retracement = (peak - low) / swing
                impulse_body = sum(abs(b["c"] - b["o"]) for b in impulse) / length
                pullback_body = sum(abs(b["c"] - b["o"]) for b in pb) / pullback_bars
                body_ratio = pullback_body / (impulse_body or math.inf)
                if (
                    volume_ratio < opts["minVolume"] or retracement < 0.05
                    or retracement > opts["maxRetracement"] or low <= origin
                    or body_ratio >= 0.8
                    or (opts["requireQuiet"] and pullback_average >= impulse_average)
                ):
                    continue
                trigger = pb[-1]["h"]
                last = bars[-1]
                if confirmed and not (
                    last["c"] > last["o"] and last["c"] > trigger and last["l"] > low
                ):
                    continue
                found.append({
                    "side": side, "status": "confirmed" if confirmed else "pullback",
                    "minutes": minutes, "pullbackBars": pullback_bars,
                    "impulseBars": length, "impulsePct": sign * impulse_pct,
                    "volumeRatio": volume_ratio,
                    "pullbackVolumeRatio": pullback_average / impulse_average
                    if impulse_average > 0 else None,
                    "retracement": retracement, "trigger": sign * trigger,
                    "invalidation": sign * low, "impulseExtreme": sign * peak,
                    "rangeLevel": sign * baseline_level,
                    "start": impulse[0]["t"], "pullbackStart": pb[0]["t"],
                    "pullbackEnd": pb[-1]["t"] + duration, "end": last_closed,
                    "setupMinutes": (
                        length + pullback_bars + (1 if confirmed else 0)
                    ) * minutes,
                    "candles": candles[max(0, start - 4):],
                })
    found.sort(key=lambda result: (
        -(result["status"] == "confirmed"), -result["volumeRatio"],
        -abs(result["impulsePct"]),
    ))
    unique = []
    for result in found:
        if all(previous["side"] != result["side"] for previous in unique):
            unique.append(result)
    return unique


def tradfi_reference(raw: list[list[Any]], end: int, min_impulse: float) -> dict[str, Any] | None:
    rows = sorted((row for row in raw if float(row[0]) < end), key=lambda row: float(row[0]))
    if not rows or float(rows[-1][0]) != end - MINUTE:
        return None
    for triggered in (True, False):
        pullback_end = len(rows) - (1 if triggered else 0)
        for count in range(1, 4):
            pullback_start = pullback_end - count
            pullback = rows[pullback_start:pullback_end]
            if (
                pullback_start < 2 or len(pullback) != count
                or any(not float(row[4]) < float(row[1]) for row in pullback)
            ):
                continue
            for length in range(2, 7):
                start = pullback_start - length
                impulse = rows[start:pullback_start]
                if start < 0 or len(impulse) != length:
                    continue
                segment = rows[start:]
                if any(
                    float(segment[i][0]) - float(segment[i - 1][0]) != MINUTE
                    for i in range(1, len(segment))
                ):
                    continue
                if sum(float(row[4]) > float(row[1]) for row in impulse) < math.ceil(length * 2 / 3):
                    continue
                origin = float(impulse[0][1])
                peak = max(float(row[2]) for row in impulse)
                swing = peak - origin
                finish = float(impulse[-1][4])
                low = min(float(row[3]) for row in pullback)
                if not origin > 0 or not swing > 0 or finish <= origin:
                    continue
                impulse_pct = (finish / origin - 1) * 100
                retracement = (peak - low) / swing
                if impulse_pct < min_impulse or retracement < 0 or retracement > 0.5 or low <= origin:
                    continue
                trigger = float(pullback[-1][2])
                last = rows[-1]
                if triggered and not (
                    float(last[2]) > trigger and float(last[3]) > low
                ):
                    continue
                impulse_volume = sum(float(row[6]) for row in impulse) / length
                pullback_volume = sum(float(row[6]) for row in pullback) / count
                return {
                    "status": "triggered" if triggered else "watch",
                    "trigger": trigger, "low": low, "impulse": impulse_pct,
                    "retrace": retracement, "pullbackBars": count,
                    "ratio": pullback_volume / impulse_volume if impulse_volume > 0 else None,
                    "closedAt": end,
                    "candles": [float(row[4]) for row in rows[max(0, start - 2):]],
                    "closeAbove": bool(triggered and float(last[4]) > trigger),
                }
    return None


def research_acceptance_guard(raw: list[list[Any]], signal: dict[str, Any],
                              minutes: int) -> bool:
    """Require the full 10-bar reference window through signal end to be gap-free."""
    duration = minutes * MINUTE
    required_start = int(signal["start"]) - 10 * duration
    required_end = int(signal["end"]) - duration
    stamps = {
        int(row[0]) // duration * duration
        for row in aggregate_reference(raw, minutes, int(signal["end"]))
    }
    return all(
        stamp in stamps
        for stamp in range(required_start, required_end + duration, duration)
    )


def _plain(value: Any) -> Any:
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, list):
        return [_plain(item) for item in value]
    if isinstance(value, dict):
        return {key: _plain(item) for key, item in value.items()}
    return value


def _python_result(case: dict[str, Any]) -> Any:
    if case["scanner"] == "pattern":
        return pattern_reference(case["candles"], case["end"], case.get("options"))
    return tradfi_reference(case["candles"], case["end"], case["minImpulse"])


def source_hashes() -> dict[str, str]:
    return {
        "dist/pattern.js": hashlib.sha256(PATTERN.read_bytes()).hexdigest(),
        "dist/tradfi.js": hashlib.sha256(TRADFI.read_bytes()).hexdigest(),
        "research/scanner_parity_bridge.js": hashlib.sha256(BRIDGE.read_bytes()).hexdigest(),
    }


def run_suite() -> dict[str, Any]:
    cases = fixture_cases()
    encoded = json.dumps({"cases": cases}, separators=(",", ":"), allow_nan=False)
    if len(encoded.encode("utf-8")) > MAX_ARTIFACT_BYTES:
        raise ValueError("Fixture input exceeds the 8 MiB hard limit")
    completed = subprocess.run(
        ["node", str(BRIDGE)],
        input=encoded,
        text=True,
        capture_output=True,
        check=True,
        timeout=10,
        cwd=ROOT,
    )
    if len(completed.stdout.encode("utf-8")) > MAX_ARTIFACT_BYTES:
        raise ValueError("Bridge output exceeds the 8 MiB hard limit")
    actual = json.loads(completed.stdout)["cases"]
    if [row["name"] for row in actual] != [case["name"] for case in cases]:
        raise AssertionError("Bridge returned unexpected fixture names or order")
    comparisons = []
    for case, observed in zip(cases, actual):
        reference = _plain(_python_result(case))
        if observed["output"] != reference:
            raise AssertionError(
                f"Reference mismatch for {case['name']}: JS={observed['output']!r}, "
                f"Python={reference!r}"
            )
        comparisons.append({
            "name": case["name"], "scanner": case["scanner"],
            "output": observed["output"], "reference_matched": True,
        })
    return {
        "suite": "finite synthetic fixtures; no market-data acquisition",
        "fixture_count": len(cases),
        "source_sha256": source_hashes(),
        "comparison": comparisons,
    }


def write_results(path: Path) -> None:
    result = run_suite()
    encoded = json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n"
    if len(encoded.encode("utf-8")) > MAX_ARTIFACT_BYTES:
        raise ValueError("Result artifact exceeds the 8 MiB hard limit")
    path.write_text(encoded, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write-results", type=Path)
    args = parser.parse_args()
    if args.write_results:
        write_results(args.write_results)
    else:
        print(json.dumps(run_suite(), indent=2, sort_keys=True, allow_nan=False))


if __name__ == "__main__":
    main()
