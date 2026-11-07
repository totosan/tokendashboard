"""Diagnose unchanged CHD/Bitget candle opens over a bounded development window."""

import argparse
import csv
import gzip
import hashlib
import json
from decimal import Decimal
from pathlib import Path

from research.budget_chd_study import compare_candles, parse_ms, trade_study
from research.chd_sample import inspect_parquet, validate_object


def diagnose(rows, candles, symbol, start, end):
    rows = list(rows)
    report = trade_study(rows, symbol, start, end)
    candles = [c for c in candles if c["symbol"] == symbol]
    saved = {int(c["timestamp"]): c for c in candles}
    if len(saved) != len(candles):
        raise ValueError("Duplicate saved candle")
    ordered = sorted(rows, key=lambda row: row["trade_time"])
    comparison = compare_candles(report, candles)
    evidence = []
    for cell in comparison["comparisons"]:
        stamp = cell["timestamp"]
        if cell["status"] == "INSUFFICIENT_OBSERVATIONS":
            raise ValueError("Incomplete observed minutes; cannot diagnose a full candle")
        candle = saved[stamp]
        prior = saved.get(stamp - 300000)
        if prior is None:
            raise ValueError("Previous official candle is required")
        before = [r for r in ordered if r["trade_time"] < stamp]
        inside = [r for r in ordered if stamp <= r["trade_time"] < stamp + 300000]
        if not before or not inside:
            raise ValueError("Missing prior/inside trade observations")
        opened = Decimal(candle["open"])
        evidence.append({
            **cell,
            "saved_open": candle["open"],
            "previous_saved_close": prior["close"],
            "previous_observed_trade_price": before[-1]["price"],
            "first_observed_trade_price": inside[0]["price"],
            "first_observed_trade_ms": inside[0]["trade_time"],
            "first_observed_receive_ns": inside[0]["received_time"],
            "open_equals_previous_close": opened == Decimal(prior["close"]),
            "open_equals_previous_observed_trade": opened == Decimal(before[-1]["price"]),
            "open_equals_first_observed_trade": opened == Decimal(inside[0]["price"]),
        })
    if len(evidence) != (end - start) // 300000:
        raise ValueError("Missing saved official candles")
    relevant = [row for row in rows if start <= row["trade_time"] < end]
    late = [row for row in relevant
            if not start * 10**6 <= row["received_time"] < end * 10**6]
    return {
        "status": "BOUNDED_OPEN_CONVENTION_EVIDENCE",
        "symbol": symbol, "event_window_ms": [start, end], "boundary": "[start,end)",
        "unique_target_trades": report["unique_observed_trades"],
        "target_trades_received_outside_target_hour": len(late),
        "target_event_time_differs_from_trade_time": sum(
            row["event_time"] != row["trade_time"] for row in relevant),
        "receive_minus_trade_ns_range": [
            min(row["received_time"] - row["trade_time"] * 10**6 for row in relevant),
            max(row["received_time"] - row["trade_time"] * 10**6 for row in relevant),
        ],
        "five_minute_comparisons": evidence,
        "conclusion": (
            "Every sampled saved open equals both the preceding official close and the last "
            "observed pre-boundary trade, not the first observed in-bucket trade."
            if all(c["open_equals_previous_close"] and c["open_equals_previous_observed_trade"]
                   and not c["open_equals_first_observed_trade"] for c in evidence)
            else "Mixed conventions/discrepancies; inspect every comparison."
        ),
        "limitations": [
            "Empirical convention evidence for this symbol/hour only, not a universal exchange contract",
            "Adjacent receive hours bound this check, not arbitrarily late arrivals or ledger completeness",
            "No original open/trade values changed; first-trade and continuity opens are distinct estimands",
            "A saved candle open is not evidence of an executable post-signal entry price",
            "No strategy, causal profile, return or inference computed",
        ],
    }


def load_manifest(directory, data_type):
    manifest = json.loads((directory / "manifest.json").read_text())
    sources = []
    for record in manifest["objects"]:
        match = validate_object(record["object"])
        if match[4] != data_type:
            continue
        if record["status"] != "OBSERVED":
            raise ValueError("Required source object was not observed")
        path = directory / record["local_file"]
        if path.parent.resolve() != directory.resolve():
            raise ValueError("Invalid local source path")
        if hashlib.sha256(path.read_bytes()).hexdigest() != record["sha256"]:
            raise ValueError("Source hash mismatch")
        inspect_parquet(path, record["object"])
        sources.append((path, record))
    return sources


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--candles", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    import pyarrow.parquet as pq

    sources = load_manifest(args.directory, "trades")
    expected = [f"bitget_futures/2026-09-17/{hour}/AAPLUSDT_trades.parquet"
                for hour in ("13", "14", "15")]
    if [record["object"] for _, record in sources] != expected:
        parser.error("Require unchanged AAPL receive-hour objects 13, 14 and 15 in order")
    original = json.loads(Path("research/data/chd-setup-verification-2026-11-03.json").read_text())
    if sources[1][1]["sha256"] != original["samples"][0]["sha256"]:
        parser.error("Reacquired target-hour hash differs from original; inspect before comparison")
    rows = [row for path, _ in sources
            for batch in pq.ParquetFile(path).iter_batches(batch_size=8192)
            for row in batch.to_pylist()]
    with gzip.open(args.candles, "rt") as source:
        result = diagnose(rows, csv.DictReader(source), "AAPLUSDT",
                          parse_ms("2026-09-17T14:00:00Z"), parse_ms("2026-09-17T15:00:00Z"))
    result["sources"] = [record for _, record in sources]
    result["saved_candle_source_sha256"] = hashlib.sha256(args.candles.read_bytes()).hexdigest()
    with args.output.open("x") as output:
        json.dump(result, output, indent=2)
        output.write("\n")
    print(result["conclusion"])


if __name__ == "__main__":
    main()
