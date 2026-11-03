"""Bounded public REST depth polling; sampled snapshots, NOT a continuous L2 feed."""

import argparse
import base64
import hashlib
import json
import re
import signal
import time
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, build_opener

from research.trade_pagination import NoRedirect

ENDPOINT = "https://api.bitget.com/api/v3/market/orderbook"
DOCUMENTATION = "https://www.bitget.com/docs/catalog/market/market-data#get-order-book"
MAX_RESPONSE = 1024 * 1024
MAX_RECORDING = 20 * 1024 * 1024


def validate(payload, limit):
    if not isinstance(payload, dict) or payload.get("code") != "00000":
        raise ValueError("Bitget returned an API error or invalid envelope")
    data = payload["data"]
    stamp = data["ts"]
    if not isinstance(stamp, (str, int)) or isinstance(stamp, bool) or not str(stamp).isdigit() or int(stamp) <= 0:
        raise ValueError("Invalid snapshot millisecond timestamp")
    sides = {}
    for key in ("b", "a"):
        levels = data[key]
        if not isinstance(levels, list) or not 1 <= len(levels) <= limit:
            raise ValueError("Missing or excessive depth levels")
        parsed = []
        for level in levels:
            if not isinstance(level, list) or len(level) != 2:
                raise ValueError("Expected [price,quantity] levels")
            price, size = (Decimal(str(v)) for v in level)
            if not all(v.is_finite() and v > 0 for v in (price, size)):
                raise ValueError("Snapshot prices/quantities must be finite and positive")
            parsed.append((price, size))
        prices = [p for p, _ in parsed]
        if prices != sorted(set(prices), reverse=key == "b"):
            raise ValueError("Unsorted or duplicate depth levels")
        sides[key] = parsed
    if sides["b"][0][0] >= sides["a"][0][0]:
        raise ValueError("Locked or crossed snapshot")
    return {"exchange_timestamp_ms": int(stamp), "bid_levels": len(sides["b"]),
            "ask_levels": len(sides["a"])}


def deadline(signum, frame):
    raise TimeoutError("Whole-request deadline reached")


def fetch(url, timeout):
    with build_opener(NoRedirect).open(Request(
        url, headers={"User-Agent": "tokendashboard-research/1.0", "Cache-Control": "no-cache"},
    ), timeout=timeout) as response:
        raw = response.read(MAX_RESPONSE + 1)
        if response.status != 200 or len(raw) > MAX_RESPONSE:
            raise ValueError("Non-200 or oversized public snapshot")
        return raw


def record(directory, symbol, samples, interval, depth, fetcher=fetch):
    if not re.fullmatch(r"[A-Z0-9]{2,30}", symbol):
        raise ValueError("Expected an uppercase Bitget symbol")
    if not 1 <= samples <= 3600 or not 1 <= interval <= 60 or not 1 <= depth <= 1000:
        raise ValueError("Bounds: samples1–3600, interval1–60s, depth1–1000")
    if samples * interval > 3600:
        raise ValueError("Each recording must be bounded to one hour")
    directory.mkdir(parents=True, exist_ok=False)
    url = ENDPOINT + "?" + urlencode({
        "category": "USDT-FUTURES", "symbol": symbol, "limit": str(depth),
    })
    manifest = {
        "status": "RUNNING", "symbol": symbol, "url": url, "documentation": DOCUMENTATION,
        "requested_samples": samples, "interval_seconds": interval, "depth_limit_per_side": depth,
        "semantics": "Independent sampled current top-N REST books; no delta continuity or historical backfill",
        "started_utc": datetime.now(timezone.utc).isoformat(),
        "records": [], "failures": [], "raw_jsonl": str(directory / "snapshots.jsonl"),
        "limits": {"recording_bytes": MAX_RECORDING, "response_bytes": MAX_RESPONSE,
                   "whole_request_seconds": 10, "retries": 0},
    }
    total, previous_stamp = 0, None
    stop = time.monotonic() + 3600
    old_handler = signal.signal(signal.SIGALRM, deadline)
    try:
        with (directory / "snapshots.jsonl").open("x") as output:
            for index in range(samples):
                if time.monotonic() >= stop:
                    raise TimeoutError("One-hour recording limit reached")
                started = time.time_ns()
                try:
                    signal.setitimer(signal.ITIMER_REAL, min(10, stop - time.monotonic()))
                    raw = fetcher(url, 10)
                finally:
                    signal.setitimer(signal.ITIMER_REAL, 0)
                received = time.time_ns()
                if len(raw) > MAX_RESPONSE:
                    raise ValueError("Response exceeds byte cap")
                summary = validate(json.loads(raw), depth)
                stamp = summary["exchange_timestamp_ms"]
                if abs(received // 10**6 - stamp) > 60000:
                    raise ValueError("Snapshot timestamp differs from local receive clock by >60s")
                if previous_stamp is not None and stamp < previous_stamp:
                    raise ValueError("Snapshot exchange time moved backward")
                summary["repeated_exchange_timestamp"] = stamp == previous_stamp
                previous_stamp = stamp
                item = {
                    "request_started_ns": started, "received_ns": received, **summary,
                    "raw_response_base64": base64.b64encode(raw).decode("ascii"),
                    "raw_response_sha256": hashlib.sha256(raw).hexdigest(),
                    "raw_response_bytes": len(raw),
                }
                line = json.dumps(item) + "\n"
                total += len(line.encode())
                if total > MAX_RECORDING:
                    raise ValueError("Recording disk-byte budget reached")
                output.write(line)
                output.flush()
                manifest["records"].append({k: v for k, v in item.items() if k != "raw_response_base64"})
                if index + 1 < samples:
                    time.sleep(min(interval, max(0, stop - time.monotonic())))
        manifest["status"] = "COMPLETE_SAMPLED_SNAPSHOTS"
    except (OSError, ValueError, KeyError, TypeError, ArithmeticError) as exc:
        manifest["status"] = "FAILED_PARTIAL"
        manifest["failures"].append({"type": type(exc).__name__, "message": str(exc)})
    except KeyboardInterrupt:
        manifest["status"] = "INTERRUPTED_PARTIAL"
        manifest["failures"].append({"type": "KeyboardInterrupt", "message": "Stopped by user"})
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, old_handler)
        manifest["finished_utc"] = datetime.now(timezone.utc).isoformat()
        raw_path = directory / "snapshots.jsonl"
        manifest["saved_jsonl_bytes"] = raw_path.stat().st_size if raw_path.exists() else 0
        manifest["saved_jsonl_sha256"] = hashlib.sha256(raw_path.read_bytes()).hexdigest() if raw_path.exists() else None
        (directory / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, required=True, help="New directory; never overwritten")
    parser.add_argument("--symbol", default="AAPLUSDT")
    parser.add_argument("--samples", type=int, default=3)
    parser.add_argument("--interval", type=float, default=2)
    parser.add_argument("--depth", type=int, default=50)
    args = parser.parse_args()
    try:
        result = record(args.directory, args.symbol, args.samples, args.interval, args.depth)
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    print(json.dumps(result, indent=2))
    return 0 if result["status"] == "COMPLETE_SAMPLED_SNAPSHOTS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
