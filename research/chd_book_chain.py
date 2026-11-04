"""Verify source-bound checkpoints and adjacent CHD book-hour handovers."""

import argparse
import hashlib
import json
from pathlib import Path

from research.budget_chd_study import checkpoint_book, replay_book
from research.candle_open_diagnostic import load_manifest
from research.chd_sample import validate_object


def read_checkpoint(path, expected_hash, source_path, source_hash, symbol):
    if hashlib.sha256(path.read_bytes()).hexdigest() != expected_hash:
        raise ValueError("Checkpoint hash mismatch")
    checkpoint = json.loads(path.read_text())
    if (hashlib.sha256(source_path.read_bytes()).hexdigest() != source_hash
            or checkpoint["source_sha256"] != source_hash):
        raise ValueError("Checkpoint source hash mismatch")
    checkpoint_book(checkpoint, symbol)
    return checkpoint


def chain(directory, checkpoint_directory):
    import pyarrow.parquet as pq

    sources = load_manifest(directory, "orderbook")
    if not sources:
        raise ValueError("No observed book sources")
    parsed = [validate_object(record["object"]) for _, record in sources]
    symbols = {match[3] for match in parsed}
    if len(symbols) != 1:
        raise ValueError("Cannot chain different symbols")
    symbol = next(iter(symbols))
    stamps = [f"{match[1]}T{match[2]}" for match in parsed]
    from datetime import datetime
    hours = [datetime.strptime(stamp, "%Y-%m-%dT%H") for stamp in stamps]
    if any((right - left).total_seconds() != 3600 for left, right in zip(hours, hours[1:])):
        raise ValueError("Require strictly adjacent receive-hour objects in order")
    checkpoint_directory.mkdir(parents=True, exist_ok=False)
    reports = []
    initial = None
    for index, (path, record) in enumerate(sources):
        parquet = pq.ParquetFile(path)
        rows = (row for batch in parquet.iter_batches(batch_size=8192)
                for row in batch.to_pylist())
        report, checkpoint = replay_book(rows, symbol, initial)
        report["source"] = record
        reports.append(report)
        if checkpoint is None:
            raise ValueError("Cannot export/import invalid final state")
        checkpoint["source_sha256"] = record["sha256"]
        output = checkpoint_directory / f"{index:02d}-checkpoint.json"
        with output.open("x") as target:
            json.dump(checkpoint, target, indent=2)
            target.write("\n")
        digest = hashlib.sha256(output.read_bytes()).hexdigest()
        report["checkpoint_sha256"] = digest
        initial = read_checkpoint(output, digest, path, record["sha256"], symbol)
    continuous = all(r["status"] == "SEQUENCE_CONSISTENT_SAMPLE" for r in reports)
    continuous = continuous and all(r["imported_state_handover"] in (
        "EXACT_SNAPSHOT_HANDOVER", "PSEQ_LINKED_HANDOVER") for r in reports[1:])
    return {
        "status": "ADJACENT_SAMPLE_CONSISTENT" if continuous else "UNVERIFIED_INTERVALS",
        "symbol": symbol, "source_reports": reports,
        "limitations": [
            "Two adjacent receive-hour samples only, not multi-symbol/day coverage",
            "Matching boundary snapshots/pseq demonstrate internal consistency, not exchange completeness",
            "Checkpoints bind local source bytes and schema; no exchange checksum certification",
            "No historical September state recovered, execution costs or fills inferred",
        ],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--checkpoints", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("Refusing to overwrite report")
    report = chain(args.directory, args.checkpoints)
    with args.output.open("x") as output:
        json.dump(report, output, indent=2)
        output.write("\n")
    print(report["status"])
    return 0 if report["status"] == "ADJACENT_SAMPLE_CONSISTENT" else 2


if __name__ == "__main__":
    raise SystemExit(main())
