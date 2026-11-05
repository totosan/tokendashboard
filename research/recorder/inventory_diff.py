"""Diff consecutive full-inventory snapshots (kind 'inventory') written by the recorder.

Usage: python3 -m research.recorder.inventory_diff DIR   (read-only, finite)
"""
import gzip
import json
import sys
from pathlib import Path

TRACKED = ("symbolStatus", "offTime", "limitOpenTime", "launchTime", "deliveryTime")


def load_inventories(root):
    """Inventory records in chronological order, skipping torn/unparseable gzip tails."""
    out = []
    for path in sorted(Path(root).glob("*/*/*/*/records.jsonl.gz")):
        try:
            with gzip.open(path, "rt", encoding="utf-8") as handle:
                for line in handle:
                    record = json.loads(line)
                    if record.get("kind") == "inventory":
                        out.append(record)
        except (OSError, EOFError, ValueError):
            continue
    return sorted(out, key=lambda r: r["available_ms"])


def symbol_map(record):
    data = json.loads(record["raw_response"])["data"]
    return {row["symbol"]: row for row in data}


def diff(old, new):
    """old/new: records. Returns added, removed and per-symbol changes of tracked fields."""
    a, b = symbol_map(old), symbol_map(new)
    changed = {}
    for symbol in sorted(set(a) & set(b)):
        delta = {k: [a[symbol].get(k), b[symbol].get(k)] for k in TRACKED
                 if a[symbol].get(k) != b[symbol].get(k)}
        if delta:
            changed[symbol] = delta
    return {"from_ms": old["available_ms"], "to_ms": new["available_ms"],
            "added": sorted(set(b) - set(a)), "removed": sorted(set(a) - set(b)),
            "changed": changed}


def diff_all(root):
    records = load_inventories(root)
    return [diff(x, y) for x, y in zip(records, records[1:])]


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 1:
        print(__doc__)
        return 1
    print(json.dumps(diff_all(argv[0]), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
