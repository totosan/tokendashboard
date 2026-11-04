"""Forward-only, bounded recorder of Bitget PUBLIC market data (issue #26).

Public GET only, no API keys. Every run is finite: --max-cycles and --duration-seconds
are hard caps. Output is append-only gzip-JSONL partitioned by UTC hour.
Sampled REST snapshots, NOT a continuous L2 feed and NOT historical backfill.
"""

import argparse
import gzip
import hashlib
import json
import os
import re
import signal
import threading
import time
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, build_opener

from research.trade_pagination import NoRedirect

BASE = "https://api.bitget.com"
PRODUCT = "USDT-FUTURES"
MAX_RESPONSE = 1024 * 1024
SCHEMA_VERSION = 1
SYMBOL_RE = re.compile(r"[A-Z0-9]{2,30}")
STOP = threading.Event()


def endpoints(symbol, depth):
    return {
        "orderbook": (BASE + "/api/v3/market/orderbook",
                      {"category": PRODUCT, "symbol": symbol, "limit": str(depth)}),
        "ticker": (BASE + "/api/v2/mix/market/ticker",
                   {"symbol": symbol, "productType": PRODUCT}),
        "funding": (BASE + "/api/v2/mix/market/current-fund-rate",
                    {"symbol": symbol, "productType": PRODUCT}),
        "contract": (BASE + "/api/v2/mix/market/contracts",
                     {"symbol": symbol, "productType": PRODUCT}),
    }


FAST = ("orderbook", "ticker")
SLOW = ("funding", "contract")


def build_url(base, params):
    return base + "?" + urlencode(params)


def fetch(url, timeout):
    request = Request(url, headers={"User-Agent": "tokendashboard-recorder/1.0",
                                    "Cache-Control": "no-cache"}, method="GET")
    with build_opener(NoRedirect).open(request, timeout=timeout) as response:
        raw = response.read(MAX_RESPONSE + 1)
        if response.status != 200 or len(raw) > MAX_RESPONSE:
            raise ValueError("Non-200 or oversized public response")
        return raw


def decimal(value):
    try:
        out = Decimal(str(value))
    except InvalidOperation:
        raise ValueError("Not a decimal: %r" % (value,))
    if not out.is_finite():
        raise ValueError("Non-finite decimal")
    return out


def normalize(kind, payload, depth):
    """Validate the envelope and extract contract-aligned fields (exchange_ms + values)."""
    if not isinstance(payload, dict) or payload.get("code") != "00000":
        raise ValueError("Bitget API error or invalid envelope")
    data = payload["data"]
    if kind == "orderbook":
        bids, asks = data["b"], data["a"]
        for side in (bids, asks):
            if not isinstance(side, list) or not 1 <= len(side) <= depth:
                raise ValueError("Missing or excessive depth levels")
            for level in side:
                if len(level) != 2 or decimal(level[0]) <= 0 or decimal(level[1]) <= 0:
                    raise ValueError("Invalid level")
        if decimal(bids[0][0]) >= decimal(asks[0][0]):
            raise ValueError("Locked or crossed snapshot")
        return {"exchange_ms": int(data["ts"]), "bid": str(bids[0][0]), "ask": str(asks[0][0]),
                "bid_quantity": str(bids[0][1]), "ask_quantity": str(asks[0][1]),
                "bid_levels": len(bids), "ask_levels": len(asks)}
    row = data[0] if isinstance(data, list) else data
    if kind == "ticker":
        out = {"exchange_ms": int(row.get("ts") or payload["requestTime"])}
        for key, name in (("bidPr", "bid"), ("askPr", "ask"), ("bidSz", "bid_quantity"),
                          ("askSz", "ask_quantity"), ("lastPr", "last"),
                          ("markPrice", "mark"), ("indexPrice", "index"),
                          ("fundingRate", "funding_rate")):
            if row.get(key) not in (None, ""):
                out[name] = str(decimal(row[key]))
        return out
    if kind == "funding":
        out = {"exchange_ms": int(payload["requestTime"]),
               "funding_rate": str(decimal(row["fundingRate"]))}
        if row.get("fundingRateInterval") not in (None, ""):
            out["funding_interval_hours"] = str(row["fundingRateInterval"])
        if row.get("nextUpdate") not in (None, ""):
            out["next_update_ms"] = int(row["nextUpdate"])
        return out
    if kind == "contract":
        out = {"exchange_ms": int(payload["requestTime"])}
        for key, name in (("makerFeeRate", "maker_fee_rate"), ("takerFeeRate", "taker_fee_rate"),
                          ("sizeMultiplier", "contract_multiplier"),
                          ("minTradeNum", "min_trade_num"), ("pricePlace", "price_place"),
                          ("volumePlace", "volume_place"), ("symbolStatus", "symbol_status")):
            if row.get(key) not in (None, ""):
                out[name] = str(row[key])
        return out
    raise ValueError("Unknown kind")


def partition_path(root, utc_ms):
    stamp = datetime.fromtimestamp(utc_ms / 1000, timezone.utc).strftime("%Y/%m/%d/%H")
    return Path(root) / stamp / "records.jsonl.gz"


def append_member(path, lines):
    """One complete gzip member per write: O_APPEND + fsync, never rewrites old bytes."""
    path.parent.mkdir(parents=True, exist_ok=True)
    blob = gzip.compress(("".join(lines)).encode(), mtime=0)
    fd = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o644)
    try:
        view = memoryview(blob)
        while view:
            view = view[os.write(fd, view):]
        os.fsync(fd)
    finally:
        os.close(fd)


def make_record(kind, symbol, url, raw, received_ns, started_ns, cycle, run_id, depth):
    fields = normalize(kind, json.loads(raw), depth)
    exchange_ms = fields.pop("exchange_ms")
    received_ms = received_ns // 10**6
    record = {
        "schema_version": SCHEMA_VERSION, "run_id": run_id, "cycle": cycle, "kind": kind,
        "instrument": {"venue": "bitget", "product": PRODUCT, "symbol": symbol,
                       "quote_currency": "USDT", "settlement_currency": "USDT"},
        "event_ms": exchange_ms,  # exchange clock
        "available_ms": received_ms,  # local receive clock (#7 availability)
        "request_started_ns": started_ns, "received_ns": received_ns,
        "clock_skew_ms": received_ms - exchange_ms,
        "url": url, "fields": fields,
        "raw_response": raw.decode("utf-8"),
        "raw_response_sha256": hashlib.sha256(raw).hexdigest(),
        "raw_response_bytes": len(raw),
    }
    record["record_sha256"] = record_hash(record)
    return record


def record_hash(record):
    body = {k: v for k, v in record.items() if k != "record_sha256"}
    return hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


class RateLimiter:
    def __init__(self, min_gap, clock=time.monotonic, wait=None):
        self.min_gap, self.clock, self.last = min_gap, clock, None
        self.wait = wait or STOP.wait

    def acquire(self):
        if self.last is not None:
            gap = self.min_gap - (self.clock() - self.last)
            if gap > 0:
                self.wait(gap)
        self.last = self.clock()


def get_with_retries(fetcher, url, timeout, retries, backoff, wait):
    last = None
    for attempt in range(retries + 1):
        if STOP.is_set():
            raise InterruptedError("stop requested")
        try:
            return fetcher(url, timeout)
        except (OSError, ValueError, TimeoutError) as exc:
            last = exc
            if attempt < retries:
                wait(backoff * 2 ** attempt)
    raise last


def run(root, symbols, cycles, interval, duration, depth=50, slow_every=30, min_gap=0.25,
        retries=2, backoff=1.0, timeout=10, fetcher=fetch, wait=None, now_ns=time.time_ns,
        monotonic=time.monotonic):
    wait = wait or STOP.wait
    if not symbols or not all(SYMBOL_RE.fullmatch(s) for s in symbols):
        raise ValueError("Expected uppercase Bitget symbols")
    if not 1 <= cycles <= 100000 or not 0 <= interval <= 3600 or not 1 <= depth <= 200:
        raise ValueError("Bounds: cycles 1-100000, interval 0-3600s, depth 1-200")
    if not 1 <= duration <= 86400 or not 1 <= slow_every <= 100000 or not 0 <= retries <= 5:
        raise ValueError("Bounds: duration 1-86400s, slow-every>=1, retries 0-5")
    run_id = "%s-%d" % (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"), os.getpid())
    limiter = RateLimiter(min_gap, monotonic, wait)
    end = monotonic() + duration
    summary = {"run_id": run_id, "records": 0, "failures": [], "cycles_completed": 0,
               "stop_reason": "MAX_CYCLES"}
    for cycle in range(1, cycles + 1):
        if STOP.is_set():
            summary["stop_reason"] = "SIGNAL"
            break
        if monotonic() >= end:
            summary["stop_reason"] = "DURATION_CAP"
            break
        cycle_started = monotonic()
        kinds = FAST + (SLOW if (cycle - 1) % slow_every == 0 else ())
        for symbol in symbols:
            urls = endpoints(symbol, depth)
            for kind in kinds:
                if STOP.is_set() or monotonic() >= end:
                    break
                url = build_url(*urls[kind])
                try:
                    limiter.acquire()
                    started = now_ns()
                    raw = get_with_retries(fetcher, url, min(timeout, max(1, end - monotonic())),
                                           retries, backoff, wait)
                    received = now_ns()
                    record = make_record(kind, symbol, url, raw, received, started, cycle,
                                         run_id, depth)
                    append_member(partition_path(root, record["available_ms"]),
                                  [json.dumps(record, sort_keys=True) + "\n"])
                    summary["records"] += 1
                except InterruptedError:
                    break
                except (OSError, ValueError, KeyError, TypeError, IndexError,
                        ArithmeticError, TimeoutError) as exc:
                    summary["failures"].append({"cycle": cycle, "symbol": symbol, "kind": kind,
                                                "type": type(exc).__name__, "message": str(exc)})
        summary["cycles_completed"] = cycle
        if cycle < cycles:
            remaining = min(interval - (monotonic() - cycle_started), end - monotonic())
            if remaining > 0:
                wait(remaining)
    if STOP.is_set():
        summary["stop_reason"] = "SIGNAL"
    summary["exit_status"] = 0 if summary["records"] and not summary["failures"] else (
        2 if summary["records"] else 1)
    return summary


def handle_term(signum, frame):
    STOP.set()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--symbols", default="AAPLUSDT,BTCUSDT")
    parser.add_argument("--max-cycles", type=int, default=10)
    parser.add_argument("--interval", type=float, default=5.0)
    parser.add_argument("--duration-seconds", type=int, default=300, help="Hard wall-clock cap")
    parser.add_argument("--depth", type=int, default=50)
    parser.add_argument("--slow-every", type=int, default=30,
                        help="Funding/contract-fee config every N cycles (always cycle 1)")
    parser.add_argument("--min-request-gap", type=float, default=0.25)
    parser.add_argument("--retries", type=int, default=2)
    args = parser.parse_args(argv)
    signal.signal(signal.SIGTERM, handle_term)
    signal.signal(signal.SIGINT, handle_term)
    try:
        summary = run(args.output_dir, [s.strip() for s in args.symbols.split(",") if s.strip()],
                      args.max_cycles, args.interval, args.duration_seconds, args.depth,
                      args.slow_every, args.min_request_gap, args.retries)
    except ValueError as exc:
        parser.error(str(exc))
    print(json.dumps(summary, indent=2))
    return summary["exit_status"]


if __name__ == "__main__":
    raise SystemExit(main())
