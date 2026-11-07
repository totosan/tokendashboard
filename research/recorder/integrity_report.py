"""Integrity, gap and coverage report over recorder partitions (read-only, offline).

Gap windows are missing data: they MUST be excluded from analysis/backtests, never
interpolated, forward-filled or otherwise synthesised.
"""

import argparse
import gzip
import hashlib
import json
import zlib
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from research.recorder.recorder import record_hash


POLICY = ("Gap windows and buckets below the coverage threshold must be EXCLUDED from analysis; "
          "never interpolate or forward-fill missing market data.")
BUCKETS = {"hour": 3600_000, "day": 86400_000}


def label(bucket, start_ms):
    fmt = "%Y-%m-%dT%H:00Z" if bucket == "hour" else "%Y-%m-%d"
    return datetime.fromtimestamp(start_ms / 1000, timezone.utc).strftime(fmt)


def coverage(points, max_gap_seconds, min_coverage_pct):
    """Covered time per UTC hour/day over the stream's own observed span.

    Time between two consecutive samples counts as covered only if the gap is <= max_gap_seconds.
    Partial first/last buckets are measured against the observed span, not the full bucket.
    """
    times = [p[0] for p in points]
    first, last = times[0], times[-1]
    covered = {b: defaultdict(float) for b in BUCKETS}
    for a, b in zip(times, times[1:]):
        if (b - a) / 1000 > max_gap_seconds:
            continue
        for name, size in BUCKETS.items():
            cursor = a
            while cursor < b:
                start = cursor // size * size
                stop = min(b, start + size)
                covered[name][start] += stop - cursor
                cursor = stop
    out = {}
    for name, size in BUCKETS.items():
        rows = []
        for start in range(first // size * size, last + 1, size):
            span = min(last, start + size) - max(first, start)
            pct = 100.0 * covered[name].get(start, 0.0) / span if span > 0 else 100.0
            rows.append({"bucket": label(name, start), "coverage_pct": round(pct, 2),
                         "below_threshold": pct < min_coverage_pct})
        out[name] = rows
    return out


def scan(root, max_gap_seconds, min_coverage_pct=95.0):
    root = Path(root)
    report = {"partitions": 0, "records": 0, "corrupt_partitions": [], "bad_records": [],
              "duplicate_records": 0, "backward_exchange_time": 0, "gaps": [],
              "by_stream": {}, "coverage": {}, "min_coverage_pct": min_coverage_pct,
              "unclean_startups": [], "recovered_partitions": [], "ntp_unsynchronized_records": 0,
              "policy": POLICY}
    seen = set()
    streams = defaultdict(list)
    for path in sorted(root.glob("*/*/*/*/records.jsonl.gz")):
        report["partitions"] += 1
        try:
            text = gzip.decompress(path.read_bytes()).decode()
        except (OSError, EOFError, zlib.error, UnicodeDecodeError) as exc:
            report["corrupt_partitions"].append({"path": str(path), "error": type(exc).__name__})
            continue
        for number, line in enumerate(text.splitlines(), 1):
            where = "%s:%d" % (path, number)
            try:
                rec = json.loads(line)
                ok = (rec["record_sha256"] == record_hash(rec) and rec["raw_response_sha256"]
                      == hashlib.sha256(rec["raw_response"].encode()).hexdigest())
            except (ValueError, KeyError, TypeError):
                ok = False
            if not ok:
                report["bad_records"].append(where)
                continue
            if rec["record_sha256"] in seen:
                report["duplicate_records"] += 1
                continue
            seen.add(rec["record_sha256"])
            if (rec.get("clock_sync") or {}).get("ntp_synchronized") is False:
                report["ntp_unsynchronized_records"] += 1
            report["records"] += 1
            streams[(rec["instrument"]["symbol"], rec["kind"])].append(
                (rec["available_ms"], rec["event_ms"]))
    for (symbol, kind), points in sorted(streams.items()):
        points.sort()
        name = "%s/%s" % (symbol, kind)
        report["by_stream"][name] = {"records": len(points), "first_ms": points[0][0],
                                     "last_ms": points[-1][0]}
        if kind in ("orderbook", "ticker"):
            for (a, ea), (b, eb) in zip(points, points[1:]):
                if eb < ea:
                    report["backward_exchange_time"] += 1
                if (b - a) / 1000 > max_gap_seconds:
                    report["gaps"].append({"stream": name, "from_ms": a, "to_ms": b,
                                           "seconds": (b - a) / 1000, "action": "EXCLUDE"})
            report["coverage"][name] = coverage(points, max_gap_seconds, min_coverage_pct)
    events = Path(root) / "_meta" / "events.jsonl"
    if events.exists():
        for line in events.read_text(errors="replace").splitlines():
            try:
                ev = json.loads(line)
            except ValueError:
                continue
            if ev.get("event") == "startup" and ev.get("unclean_shutdown_detected"):
                report["unclean_startups"].append({"run_id": ev.get("run_id"),
                                                   "ts_ms": ev.get("ts_ms")})
                report["recovered_partitions"] += ev.get("recovered_partitions", [])
    report["ok"] = not (report["corrupt_partitions"] or report["bad_records"])
    report["low_coverage_buckets"] = [
        {"stream": name, "granularity": g, **row}
        for name, c in report["coverage"].items() for g, rows in c.items()
        for row in rows if row["below_threshold"]]
    report["coverage_ok"] = not report["low_coverage_buckets"]
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    parser.add_argument("--max-gap-seconds", type=float, default=60.0,
                        help="Gaps between orderbook/ticker samples above this are reported; "
                             "expected gaps between bounded timer runs appear here")
    parser.add_argument("--min-coverage-pct", type=float, default=95.0,
                        help="Hour/day buckets below this coverage are flagged for exclusion")
    args = parser.parse_args(argv)
    report = scan(args.root, args.max_gap_seconds, args.min_coverage_pct)
    print(json.dumps(report, indent=2))
    if not report["ok"]:
        return 1
    return 0 if report["coverage_ok"] else 3


if __name__ == "__main__":
    raise SystemExit(main())
