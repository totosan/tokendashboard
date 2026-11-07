"""G04 coverage matrix: run the frozen rolling profile comparison per symbol/receive-hour cell."""

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from research import rolling_profile_comparison as rpc

SYMBOLS = ("AAPLUSDT", "BTCUSDT")
TARGET_HOURS = (14, 15)
DAY = "2026-09-17"
FROZEN_AAPL_14_SHA256 = "8234c5e765fb83a1990b3db6e02ff114b68ce346322317fa37a4502f293f0138"
HOUR_MS = 3600 * 1000
BASE_MS = int(datetime(2026, 9, 17, tzinfo=timezone.utc).timestamp()) * 1000


def cell_config(symbol, hour):
    objects = tuple(f"bitget_futures/{DAY}/{h:02d}/{symbol}_trades.parquet"
                    for h in (hour - 1, hour, hour + 1))
    start = BASE_MS + hour * HOUR_MS
    return {"symbol": symbol, "objects": objects, "start_ms": start, "end_ms": start + HOUR_MS}


def run_cell(config, source_dir, manifest_path, candles, target_sha):
    saved = {name: getattr(rpc, name) for name in
             ("SYMBOL", "TRADE_OBJECTS", "START_MS", "END_MS", "TARGET_TRADE_SHA256")}
    try:
        rpc.SYMBOL, rpc.TRADE_OBJECTS = config["symbol"], config["objects"]
        rpc.START_MS, rpc.END_MS = config["start_ms"], config["end_ms"]
        rpc.TARGET_TRADE_SHA256 = target_sha
        trades, trade_source = rpc.load_trade_sources(source_dir, manifest_path)
        bars, candle_source, dispositions = rpc.load_candles(candles)
        errors = []
        if trade_source["event_time_trade_time_mismatch_count"]:
            errors.append("EVENT_TIME_TRADE_TIME_MISMATCH")
        if trade_source["conflicting_trade_id_count"]:
            errors.append("CONFLICTING_TRADE_ID")
        if candle_source["invalid_timestamp_count"]:
            errors.append("INVALID_CANDLE_TIMESTAMP")
        if candle_source["invalid_cadence_count"]:
            errors.append("INVALID_CANDLE_CADENCE")
        return rpc.build_report(trades, bars, trade_source, candle_source, dispositions,
                                global_errors=errors)
    finally:
        for name, value in saved.items():
            setattr(rpc, name, value)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", type=Path, required=True)
    parser.add_argument("--candles", type=Path, default=rpc.CANDLE_PATH)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("Refusing to overwrite an existing report")
    manifest_path = args.source_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    hashes = {row["object"]: row["sha256"] for row in manifest["objects"] if row.get("sha256")}
    cells = []
    for symbol in SYMBOLS:
        for hour in TARGET_HOURS:
            config = cell_config(symbol, hour)
            target = hashes[config["objects"][1]]
            if symbol == "AAPLUSDT" and hour == 14 and target != FROZEN_AAPL_14_SHA256:
                raise SystemExit("AAPLUSDT hour 14 differs from frozen hash")
            report = run_cell(config, args.source_dir, manifest_path, args.candles, target)
            cells.append({"symbol": symbol, "target_receive_hour_utc": hour,
                          "objects": list(config["objects"]), "report": report})
    result = {
        "issue": 13, "package": "G04-coverage",
        "status": "DESCRIPTIVE_MATRIX_OBSERVED_NO_EFFICACY_CLAIM",
        "manifest_sha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
        "cells": cells,
        "summary": [{"symbol": c["symbol"], "hour": c["target_receive_hour_utc"],
                     "report_status": c["report"]["status"],
                     "source_integrity_errors": c["report"]["source_integrity_errors"],
                     **c["report"]["window_summary"],
                     "payload_sha256": c["report"]["payload_sha256"]} for c in cells],
        "limits": ["Descriptive source agreement only; no returns, costs, fills or significance",
                   "Hour-14 and hour-15 cells use receive-hour objects h-1..h+1; hour 16 object is used only as a post-window lookahead partition",
                   "Non-AAPL/hour-14 target hashes are bound to the observed manifest, not frozen in advance"],
    }
    with args.output.open("x", encoding="utf-8") as out:
        json.dump(result, out, indent=1, allow_nan=False)
        out.write("\n")
    print(json.dumps(result["summary"], indent=1))


if __name__ == "__main__":
    main()
