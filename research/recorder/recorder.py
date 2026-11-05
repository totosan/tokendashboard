"""Forward-only, bounded recorder of Bitget PUBLIC market data (issue #26).

Public GET only, no API keys. Every run is finite: --max-cycles and --duration-seconds
are hard caps. Output is append-only gzip-JSONL partitioned by UTC hour.
Sampled REST snapshots, NOT a continuous L2 feed and NOT historical backfill.
"""

import argparse
import gzip
import http.client
import hashlib
import json
import os
import re
import signal
import subprocess
import threading
import time
import zlib
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from urllib.parse import urlencode
from urllib.parse import urlsplit

BASE = "https://api.bitget.com"
PRODUCT = "USDT-FUTURES"
MAX_RESPONSE = 4 * 1024 * 1024  # full contract inventory is several hundred KB
SCHEMA_VERSION = 1
SYMBOL_RE = re.compile(r"[A-Z0-9]{2,30}")
META_DIR = "_meta"
INVENTORY_STATE = "inventory_state.json"
CLEAN_MARKER = "clean_shutdown.json"
RUN_STATE = "run_state.json"
CLOCK_REFRESH_SECONDS = 60
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
        "open_interest": (BASE + "/api/v2/mix/market/open-interest",
                          {"symbol": symbol, "productType": PRODUCT}),
        "long_short": (BASE + "/api/v2/mix/market/long-short",
                       {"symbol": symbol, "period": SENTIMENT_PERIOD}),
        "account_long_short": (BASE + "/api/v2/mix/market/account-long-short",
                               {"symbol": symbol, "period": SENTIMENT_PERIOD}),
        "position_long_short": (BASE + "/api/v2/mix/market/position-long-short",
                                {"symbol": symbol, "period": SENTIMENT_PERIOD}),
        "taker_buy_sell": (BASE + "/api/v2/mix/market/taker-buy-sell",
                           {"symbol": symbol, "period": SENTIMENT_PERIOD}),
    }


FAST = ("orderbook", "ticker")
SENTIMENT = ("open_interest", "long_short", "account_long_short", "position_long_short",
             "taker_buy_sell")
SLOW = ("funding", "contract") + SENTIMENT
SENTIMENT_PERIOD = "5m"
NO_DATA_CODE = "40054"  # Bitget answers HTTP 400 + this code when a symbol has no such data


def build_url(base, params):
    return base + "?" + urlencode(params)


_CONN = {}


def _close_connection():
    conn = _CONN.pop("conn", None)
    if conn is not None:
        try:
            conn.close()
        except OSError:
            pass


def fetch(url, timeout):
    """Public GET over one reused keep-alive HTTPS connection (a TLS handshake per request
    dominated Pi CPU). Any error drops the connection so the retry reconnects; no redirects."""
    parts = urlsplit(url)
    if parts.scheme != "https" or parts.netloc != urlsplit(BASE).netloc:
        raise ValueError("Only the Bitget public HTTPS host is allowed")
    conn = _CONN.get("conn")
    if conn is None:
        conn = _CONN["conn"] = http.client.HTTPSConnection(parts.netloc, timeout=timeout)
    conn.timeout = timeout
    if conn.sock is not None:
        conn.sock.settimeout(timeout)
    try:
        conn.request("GET", parts.path + "?" + parts.query, headers={
            "User-Agent": "tokendashboard-recorder/1.0", "Cache-Control": "no-cache"})
        response = conn.getresponse()
        raw = response.read(MAX_RESPONSE + 1)
        status = response.status
    except http.client.HTTPException as exc:
        _close_connection()
        raise OSError("HTTP protocol error: %s" % type(exc).__name__) from exc
    except BaseException:
        _close_connection()
        raise
    if status == 400 and len(raw) <= MAX_RESPONSE and is_no_data(raw):
        return raw
    if status != 200 or len(raw) > MAX_RESPONSE:
        _close_connection()
        raise ValueError("Non-200 or oversized public response")
    return raw


def is_no_data(raw):
    try:
        payload = json.loads(raw)
    except ValueError:
        return False
    return isinstance(payload, dict) and payload.get("code") == NO_DATA_CODE


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
    if (kind in SENTIMENT and isinstance(payload, dict)
            and payload.get("code") == NO_DATA_CODE):
        return {"exchange_ms": int(payload["requestTime"]), "no_data": "true",
                "code": NO_DATA_CODE}
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
    if kind == "inventory":
        if not isinstance(data, list) or not data:
            raise ValueError("Empty contract inventory")
        statuses = {}
        for item in data:
            status = str(item.get("symbolStatus", ""))
            statuses[status] = statuses.get(status, 0) + 1
        return {"exchange_ms": int(payload["requestTime"]), "symbol_count": len(data),
                "status_counts": statuses}
    if kind == "open_interest":
        items = data["openInterestList"]
        if not isinstance(items, list) or not items:
            raise ValueError("Empty open interest")
        return {"exchange_ms": int(data["ts"]), "open_interest": str(decimal(items[0]["size"]))}
    if kind in SENTIMENT:
        if not isinstance(data, list) or not data:
            raise ValueError("Empty sentiment series")
        row = max(data, key=lambda item: int(item["ts"]))  # latest 5m bucket; raw keeps series
        out = {"exchange_ms": int(row["ts"]), "period": SENTIMENT_PERIOD, "points": len(data)}
        names = {"long_short": (("longRatio", "long_ratio"), ("shortRatio", "short_ratio"),
                                ("longShortRatio", "long_short_ratio")),
                 "account_long_short": (("longAccountRatio", "long_account_ratio"),
                                        ("shortAccountRatio", "short_account_ratio"),
                                        ("longShortAccountRatio", "long_short_account_ratio")),
                 "position_long_short": (("longPositionRatio", "long_position_ratio"),
                                         ("shortPositionRatio", "short_position_ratio"),
                                         ("longShortPositionRatio", "long_short_position_ratio")),
                 "taker_buy_sell": (("buyVolume", "buy_volume"), ("sellVolume", "sell_volume"))}
        for key, name in names[kind]:
            out[name] = str(decimal(row[key]))
        return out
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


def inventory_url():
    return build_url(BASE + "/api/v2/mix/market/contracts", {"productType": PRODUCT})


def inventory_due(root, now_ms):
    """True unless an inventory snapshot was already stored for the current UTC day."""
    try:
        state = json.loads((Path(root) / META_DIR / INVENTORY_STATE).read_text())
        return state.get("utc_date") != utc_date(now_ms)
    except (OSError, ValueError, AttributeError):
        return True


def utc_date(ms):
    return datetime.fromtimestamp(ms / 1000, timezone.utc).strftime("%Y-%m-%d")


def record_inventory(root, fetcher, limiter, now_ns, run_id, cycle, clock_sync, timeout,
                     retries, backoff, wait):
    url = inventory_url()
    limiter.acquire()
    started = now_ns()
    raw = get_with_retries(fetcher, url, timeout, retries, backoff, wait)
    received = now_ns()
    record = make_record("inventory", "ALL", url, raw, received, started, cycle, run_id, 1,
                         clock_sync)
    append_member(partition_path(root, record["available_ms"]),
                  [json.dumps(record, sort_keys=True) + "\n"])
    write_durable(Path(root) / META_DIR / INVENTORY_STATE, json.dumps(
        {"utc_date": utc_date(record["available_ms"]), "available_ms": record["available_ms"],
         "raw_response_sha256": record["raw_response_sha256"]}).encode())
    return record


def partition_path(root, utc_ms):
    stamp = datetime.fromtimestamp(utc_ms / 1000, timezone.utc).strftime("%Y/%m/%d/%H")
    return Path(root) / stamp / "records.jsonl.gz"


def append_member(path, lines):
    """One complete gzip member per write: O_APPEND + fsync, never rewrites old bytes."""
    path.parent.mkdir(parents=True, exist_ok=True)
    blob = gzip.compress(("".join(lines)).encode(), mtime=0)
    created = not path.exists()
    fd = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o644)
    try:
        view = memoryview(blob)
        while view:
            view = view[os.write(fd, view):]
        os.fsync(fd)
    finally:
        os.close(fd)
    if created:
        fsync_dir(path.parent)


def fsync_dir(directory):
    try:
        fd = os.open(directory, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(fd)
    except OSError:
        pass
    finally:
        os.close(fd)


def valid_prefix_length(data):
    """Byte length of the leading run of complete gzip members whose payload is whole JSONL."""
    pos = 0
    while pos < len(data):
        decoder = zlib.decompressobj(31)
        try:
            out = decoder.decompress(data[pos:])
        except zlib.error:
            break
        if not decoder.eof or not out.endswith(b"\n"):
            break
        pos = len(data) - len(decoder.unused_data)
    return pos


def recover_partition(path, root, now_ms):
    """Truncate a torn trailing member to the last valid one; keep the removed bytes in _quarantine."""
    path = Path(path)
    data = path.read_bytes()
    good = valid_prefix_length(data)
    if good == len(data):
        return None
    quarantine = Path(root) / META_DIR / "quarantine" / (
        "%s.%d.torn" % ("_".join(path.relative_to(root).parts), now_ms))
    quarantine.parent.mkdir(parents=True, exist_ok=True)
    with open(quarantine, "wb") as handle:
        handle.write(data[good:])
        handle.flush()
        os.fsync(handle.fileno())
    fd = os.open(path, os.O_WRONLY)
    try:
        os.ftruncate(fd, good)
        os.fsync(fd)
    finally:
        os.close(fd)
    return {"path": str(path), "kept_bytes": good, "quarantined_bytes": len(data) - good,
            "quarantine_file": str(quarantine)}


def recover_torn_partitions(root, now_ms, newest=2):
    """After an unclean shutdown only the most recent partitions can hold a torn write."""
    root = Path(root)
    found = sorted(root.glob("*/*/*/*/records.jsonl.gz"))[-newest:]
    return [r for r in (recover_partition(p, root, now_ms) for p in found) if r]


def write_durable(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "wb") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())
    fsync_dir(path.parent)


def log_event(root, event):
    """Append-only JSONL audit log of lifecycle events, fsynced."""
    path = Path(root) / META_DIR / "events.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o644)
    try:
        os.write(fd, (json.dumps(event, sort_keys=True) + "\n").encode())
        os.fsync(fd)
    finally:
        os.close(fd)


def begin_run(root, run_id, now_ms, clock_sync):
    """Detect unclean shutdown, repair torn files, log startup, then arm the running state.

    The clean marker is consumed here; it is only written again by finish_run, so a crash,
    power loss or SIGKILL leaves no marker and is detected on the next start.
    """
    root = Path(root)
    meta = root / META_DIR
    clean, started = meta / CLEAN_MARKER, meta / RUN_STATE
    if clean.exists():
        previous = "clean"
    elif started.exists():
        previous = "unclean"
    else:
        previous = "first_run"
    recovered = recover_torn_partitions(root, now_ms) if previous == "unclean" else []
    event = {"event": "startup", "run_id": run_id, "ts_ms": now_ms,
             "previous_shutdown": previous, "unclean_shutdown_detected": previous == "unclean",
             "recovered_partitions": recovered, "clock_sync": clock_sync}
    log_event(root, event)
    if clean.exists():
        clean.unlink()
        fsync_dir(meta)
    write_durable(started, json.dumps({"run_id": run_id, "ts_ms": now_ms}).encode())
    return event


def finish_run(root, run_id, now_ms, stop_reason):
    """Clean-shutdown marker: only reached on normal finish or graceful SIGTERM/SIGINT stop."""
    meta = Path(root) / META_DIR
    log_event(root, {"event": "shutdown", "run_id": run_id, "ts_ms": now_ms,
                     "stop_reason": stop_reason})
    write_durable(meta / CLEAN_MARKER, json.dumps(
        {"run_id": run_id, "ts_ms": now_ms, "stop_reason": stop_reason}).encode())


def read_clock_sync(runner=subprocess.run):
    """NTP status from timedatectl when available; None means unknown, never assumed good."""
    try:
        out = runner(["timedatectl", "show", "-p", "NTPSynchronized", "--value"],
                     capture_output=True, text=True, timeout=5, check=False)
        value = out.stdout.strip().lower()
        if out.returncode == 0 and value in ("yes", "no"):
            return {"ntp_synchronized": value == "yes", "source": "timedatectl"}
    except (OSError, subprocess.SubprocessError, AttributeError):
        pass
    # systemd-timesyncd touches this file once the clock has synchronized
    if os.path.exists("/run/systemd/timesync/synchronized"):
        return {"ntp_synchronized": True, "source": "timesyncd_marker"}
    return {"ntp_synchronized": None, "source": "unavailable"}


def make_record(kind, symbol, url, raw, received_ns, started_ns, cycle, run_id, depth,
                clock_sync=None):
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
        "clock_sync": clock_sync or {"ntp_synchronized": None, "source": "unavailable"},
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
        monotonic=time.monotonic, clock_status=read_clock_sync, inventory=True):
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
    clock_sync, clock_at = clock_status(), monotonic()
    startup = begin_run(root, run_id, now_ns() // 10**6, clock_sync)
    summary = {"run_id": run_id, "previous_shutdown": startup["previous_shutdown"],
               "recovered_partitions": startup["recovered_partitions"],
               "clock_sync": clock_sync, "records": 0, "failures": [], "cycles_completed": 0,
               "stop_reason": "MAX_CYCLES", "no_data": []}
    no_data = set()
    for cycle in range(1, cycles + 1):
        if STOP.is_set():
            summary["stop_reason"] = "SIGNAL"
            break
        if monotonic() >= end:
            summary["stop_reason"] = "DURATION_CAP"
            break
        cycle_started = monotonic()
        if inventory and inventory_due(root, now_ns() // 10**6):
            try:
                record_inventory(root, fetcher, limiter, now_ns, run_id, cycle, clock_sync,
                                 min(timeout, max(1, end - monotonic())), retries, backoff, wait)
                summary["records"] += 1
                summary["inventory_recorded"] = summary.get("inventory_recorded", 0) + 1
            except InterruptedError:
                pass
            except (OSError, ValueError, KeyError, TypeError, IndexError, AttributeError,
                    ArithmeticError, TimeoutError) as exc:
                summary["failures"].append({"cycle": cycle, "symbol": "ALL", "kind": "inventory",
                                            "type": type(exc).__name__, "message": str(exc)})
                inventory = False  # retry on next run, not every cycle
        kinds = FAST + (SLOW if (cycle - 1) % slow_every == 0 else ())
        for symbol in symbols:
            urls = endpoints(symbol, depth)
            for kind in kinds:
                if STOP.is_set() or monotonic() >= end:
                    break
                if (symbol, kind) in no_data:
                    continue
                url = build_url(*urls[kind])
                try:
                    limiter.acquire()
                    started = now_ns()
                    raw = get_with_retries(fetcher, url, min(timeout, max(1, end - monotonic())),
                                           retries, backoff, wait)
                    received = now_ns()
                    if monotonic() - clock_at >= CLOCK_REFRESH_SECONDS:
                        clock_sync, clock_at = clock_status(), monotonic()
                    record = make_record(kind, symbol, url, raw, received, started, cycle,
                                         run_id, depth, clock_sync)
                    append_member(partition_path(root, record["available_ms"]),
                                  [json.dumps(record, sort_keys=True) + "\n"])
                    summary["records"] += 1
                    if record["fields"].get("no_data"):
                        no_data.add((symbol, kind))
                        summary["no_data"].append({"symbol": symbol, "kind": kind})
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
    finish_run(root, run_id, now_ns() // 10**6, summary["stop_reason"])
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
                        help="Funding/contract-fee/sentiment kinds every N cycles (always cycle 1)")
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
    _close_connection()
    print(json.dumps(summary, indent=2))
    return summary["exit_status"]


if __name__ == "__main__":
    raise SystemExit(main())
