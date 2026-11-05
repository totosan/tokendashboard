"""Bounded, anonymous, read-only acquisition from the Binance USD-M public bulk archive.

Datasets: daily 'metrics' (5m OI / long-short / taker ratios) and monthly 5m 'klines'.
Default is a dry-run plan (no network). --execute downloads under hard caps: host allowlist
(data.binance.vision), https only, no redirects, per-request timeout, rate limit, max files,
max total MiB, wall clock. Raw zips stay LOCAL in --directory (never committed; the default
directory is git-excluded); the manifest holds only URLs, sizes and SHA-256. Resume-safe:
files already on disk are verified and kept; missing archive days (404) are recorded.
"""

import argparse
import hashlib
import json
import sys
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener

HOST = "data.binance.vision"
BASE = "https://" + HOST + "/data/futures/um"
DEFAULT_DIR = Path("research/data/binance_raw")
MAX_FILES = 20
MAX_MIB = 5.0
TIMEOUT = 10
MIN_INTERVAL = 0.2
WALL = 80
HARD_MAX_FILES = 6000
HARD_MAX_MIB = 200.0
EST_BYTES = {"metrics": 11_000, "klines5m": 300_000}


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        return None


def parse_day(s):
    return date.fromisoformat(s)


def plan(dataset, symbols, start, end):
    """Deterministic list of (symbol, label, url, relpath), symbol-major then chronological."""
    items = []
    for sym in symbols:
        if dataset == "metrics":
            d = start
            while d <= end:
                name = "%s-metrics-%s.zip" % (sym, d.isoformat())
                items.append((sym, d.isoformat(), "%s/daily/metrics/%s/%s" % (BASE, sym, name),
                              "metrics/%s/%s" % (sym, name)))
                d += timedelta(days=1)
        elif dataset == "klines5m":
            y, m = start.year, start.month
            while (y, m) <= (end.year, end.month):
                name = "%s-5m-%04d-%02d.zip" % (sym, y, m)
                items.append((sym, "%04d-%02d" % (y, m), "%s/monthly/klines/%s/5m/%s" % (BASE, sym, name),
                              "klines5m/%s/%s" % (sym, name)))
                y, m = (y + 1, 1) if m == 12 else (y, m + 1)
        else:
            raise ValueError("unknown dataset " + dataset)
    for _, _, url, _ in items:
        assert urlparse(url).netloc == HOST and url.startswith("https://")
    return items


def sha256_file(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def fetch(url, timeout, max_bytes):
    """Returns (status, bytes|None). Never follows redirects; refuses non-allowlisted hosts."""
    if urlparse(url).netloc != HOST or not url.startswith("https://"):
        raise ValueError("host not allowlisted")
    opener = build_opener(NoRedirect)
    try:
        with opener.open(Request(url, headers={"User-Agent": "tokendashboard-research"}), timeout=timeout) as r:
            data = r.read(max_bytes + 1)
            if len(data) > max_bytes:
                return "too_large", None
            return r.status, data
    except HTTPError as e:
        return e.code, None
    except (URLError, TimeoutError, OSError) as e:
        return "error:" + type(e).__name__, None


def run(dataset, symbols, start, end, directory, execute, max_files=MAX_FILES, max_mib=MAX_MIB,
        timeout=TIMEOUT, interval=MIN_INTERVAL, wall=WALL, fetcher=fetch, sleep=time.sleep,
        clock=time.monotonic):
    max_files = min(max_files, HARD_MAX_FILES)
    max_mib = min(max_mib, HARD_MAX_MIB)
    items = plan(dataset, symbols, start, end)
    est = len(items) * EST_BYTES[dataset]
    man = {"dataset": dataset, "symbols": list(symbols), "start": start.isoformat(), "end": end.isoformat(),
           "mode": "execute" if execute else "dry_run", "planned_files": len(items),
           "estimated_total_mib": round(est / 1048576, 2),
           "caps": {"max_files": max_files, "max_mib": max_mib, "timeout_s": timeout,
                    "min_interval_s": interval, "wall_s": wall},
           "files": [], "missing": [], "errors": [], "stopped_by": None}
    if not execute:
        return man
    directory = Path(directory)
    t0, total, fetched, last = clock(), 0, 0, 0.0
    for sym, label, url, rel in items:
        path = directory / rel
        if path.exists():
            b = path.stat().st_size
            man["files"].append({"symbol": sym, "label": label, "url": url, "bytes": b,
                                 "sha256": sha256_file(path), "source": "resume"})
            total += b
            continue
        if fetched >= max_files:
            man["stopped_by"] = "max_files"
            break
        if clock() - t0 > wall:
            man["stopped_by"] = "wall_clock"
            break
        wait = interval - (clock() - last)
        if wait > 0:
            sleep(wait)
        last = clock()
        remaining = int(max_mib * 1048576) - total
        status, data = fetcher(url, timeout, max(remaining, 0))
        fetched += 1
        if status == 200 and data is not None:
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(".part")
            tmp.write_bytes(data)
            tmp.replace(path)
            total += len(data)
            man["files"].append({"symbol": sym, "label": label, "url": url, "bytes": len(data),
                                 "sha256": hashlib.sha256(data).hexdigest(), "source": "download"})
        elif status == 404:
            man["missing"].append({"symbol": sym, "label": label, "url": url})
        elif status == "too_large":
            man["stopped_by"] = "max_mib"
            break
        else:
            man["errors"].append({"url": url, "status": str(status)})
            if len(man["errors"]) >= 3:
                man["stopped_by"] = "errors"
                break
        if total >= max_mib * 1048576:
            man["stopped_by"] = "max_mib"
            break
    man["total_bytes"] = total
    man["downloaded_files"] = sum(f["source"] == "download" for f in man["files"])
    man["requests"] = fetched
    return man


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dataset", choices=sorted(EST_BYTES), default="metrics")
    ap.add_argument("--symbols", default="BTCUSDT")
    ap.add_argument("--start", type=parse_day, required=True)
    ap.add_argument("--end", type=parse_day, required=True)
    ap.add_argument("--directory", type=Path, default=DEFAULT_DIR)
    ap.add_argument("--execute", action="store_true", help="download (default: dry-run plan)")
    ap.add_argument("--max-files", type=int, default=MAX_FILES)
    ap.add_argument("--max-mib", type=float, default=MAX_MIB)
    ap.add_argument("--manifest", type=Path)
    a = ap.parse_args(argv)
    if a.end < a.start:
        ap.error("end before start")
    man = run(a.dataset, [s.strip() for s in a.symbols.split(",") if s.strip()], a.start, a.end,
              a.directory, a.execute, a.max_files, a.max_mib)
    man["created_utc"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    text = json.dumps(man, indent=1, sort_keys=True)
    if a.manifest:
        a.manifest.write_text(text + "\n")
    print(text if not a.manifest else "manifest written: %s" % a.manifest)
    return 0 if not man["errors"] else 1


if __name__ == "__main__":
    sys.exit(main())
