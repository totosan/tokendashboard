"""Integrity and gap report over recorder partitions (read-only, offline)."""

import argparse
import gzip
import hashlib
import json
import zlib
from collections import defaultdict
from pathlib import Path

from research.recorder.recorder import record_hash


def scan(root, max_gap_seconds):
    root = Path(root)
    report = {"partitions": 0, "records": 0, "corrupt_partitions": [], "bad_records": [],
              "duplicate_records": 0, "backward_exchange_time": 0, "gaps": [],
              "by_stream": {}}
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
                                           "seconds": (b - a) / 1000})
    report["ok"] = not (report["corrupt_partitions"] or report["bad_records"])
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    parser.add_argument("--max-gap-seconds", type=float, default=60.0,
                        help="Gaps between orderbook/ticker samples above this are reported; "
                             "expected gaps between bounded timer runs appear here")
    args = parser.parse_args(argv)
    report = scan(args.root, args.max_gap_seconds)
    print(json.dumps(report, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
