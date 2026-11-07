"""Bounded as-of trade versus candle-profile comparison; descriptive only."""

import argparse
import csv
import gzip
import hashlib
import json
import math
from collections import defaultdict
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, localcontext
from fractions import Fraction
from pathlib import Path

PROTOCOL_PATH = Path("research/results/profile-comparison-protocol-2026-11-04-v4.json")
CANDLE_PATH = Path("research/data/bitget-5m-2026-09-17_2026-11-01.csv.gz")
SYMBOL = "AAPLUSDT"
START_MS = 1789653600000
END_MS = 1789657200000
BAR_MS = 5 * 60 * 1000
WINDOW_MS = 15 * 60 * 1000
BIN_COUNT = 24
TRADE_OBJECTS = (
    "bitget_futures/2026-09-17/13/AAPLUSDT_trades.parquet",
    "bitget_futures/2026-09-17/14/AAPLUSDT_trades.parquet",
    "bitget_futures/2026-09-17/15/AAPLUSDT_trades.parquet",
)
TARGET_TRADE_SHA256 = "8234c5e765fb83a1990b3db6e02ff114b68ce346322317fa37a4502f293f0138"
CANDLE_SHA256 = "1364e80e62353c853f2bacb4ba5dba59e2f618ca72e80a1b1fb493bb8a57992f"
MAX_SOURCE_BYTES = 20 * 1024 * 1024
MAX_SOURCE_ROWS = 2_000_000
TRADE_COLUMNS = (
    "received_time", "event_time", "symbol", "trade_id", "price", "quantity",
    "trade_time", "is_buyer_maker", "order_type",
)


def _decimal(value, name, allow_zero=False):
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValueError(f"Invalid {name}") from exc
    if not result.is_finite() or (result < 0 if allow_zero else result <= 0):
        raise ValueError(f"Invalid {name}")
    return result


def _integer(value, name):
    if isinstance(value, bool):
        raise ValueError(f"Invalid {name}")
    try:
        result = int(value)
    except (ValueError, TypeError, OverflowError) as exc:
        raise ValueError(f"Invalid {name}") from exc
    if result < 0 or str(value) != str(result):
        raise ValueError(f"Invalid {name}")
    return result


def _as_fraction(value):
    if isinstance(value, Fraction):
        return value
    if isinstance(value, Decimal):
        return Fraction(value)
    return Fraction(_decimal(value, "numeric value", allow_zero=True))


def _number_text(value):
    """Serialize exact rational calculations as deterministic decimal strings."""
    fraction = value if isinstance(value, Fraction) else Fraction(value)
    with localcontext() as context:
        context.prec = 28
        return str(Decimal(fraction.numerator) / Decimal(fraction.denominator))


def _utc_ms(value):
    return datetime.fromtimestamp(value / 1000, tz=timezone.utc).isoformat().replace("+00:00", "Z")


def _canonical_hash(value):
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                     allow_nan=False).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def load_trade_sources(source_dir, manifest_path):
    """Load only manifest-bound trade objects, retaining source-partition identity."""
    try:
        import pyarrow
        import pyarrow.parquet as pq
    except ImportError as exc:
        raise ValueError("Use the pinned CHD environment with PyArrow 26.0.1") from exc

    manifest_bytes = manifest_path.read_bytes()
    manifest = json.loads(manifest_bytes)
    if manifest.get("provider") != "CryptoHFTData; third-party collector, not official Bitget archive":
        raise ValueError("Unexpected trade manifest provider")
    requested_objects = manifest.get("requested_objects")
    if (manifest.get("status") != "BOUNDED_SAMPLE_OBSERVED"
            or (requested_objects is not None
                and not set(TRADE_OBJECTS).issubset(set(requested_objects)))):
        raise ValueError("Trade manifest does not declare the required observed objects")
    if manifest.get("pyarrow_version") != "26.0.1" or pyarrow.__version__ != "26.0.1":
        raise ValueError("Trade manifest and installed PyArrow must both be version 26.0.1")
    records = {row.get("object"): row for row in manifest.get("objects", [])}
    loaded, object_reports = [], []
    duplicate_count = 0
    conflict_count = 0
    conflicts = []
    time_mismatch_count = 0
    time_mismatches = []
    seen = {}

    for object_name in TRADE_OBJECTS:
        record = records.get(object_name)
        if not record or record.get("status") != "OBSERVED":
            raise ValueError(f"Required observed trade object missing: {object_name}")
        local_name = record.get("local_file")
        if not isinstance(local_name, str) or Path(local_name).name != local_name:
            raise ValueError(f"Invalid local file mapping for {object_name}")
        path = source_dir / local_name
        size = path.stat().st_size
        if size > MAX_SOURCE_BYTES or size != record.get("bytes"):
            raise ValueError(f"Trade object size mismatch/budget exceeded: {object_name}")
        sha256 = hashlib.sha256(path.read_bytes()).hexdigest()
        if sha256 != record.get("sha256"):
            raise ValueError(f"Trade object SHA-256 mismatch: {object_name}")
        if object_name == TRADE_OBJECTS[1] and sha256 != TARGET_TRADE_SHA256:
            raise ValueError("Target receive-hour trade object differs from frozen hash")

        parquet = pq.ParquetFile(path)
        if parquet.metadata.num_rows > MAX_SOURCE_ROWS:
            raise ValueError(f"Trade object exceeds row budget: {object_name}")
        if parquet.metadata.num_rows != record.get("rows"):
            raise ValueError(f"Trade object row count differs from manifest: {object_name}")
        if tuple(parquet.schema_arrow.names) != TRADE_COLUMNS:
            raise ValueError(f"Unexpected trade schema: {object_name}")
        rows_before = len(loaded)
        for batch in parquet.iter_batches(columns=list(TRADE_COLUMNS), batch_size=8192):
            for row in batch.to_pylist():
                if row["symbol"] != SYMBOL:
                    raise ValueError(f"Unexpected symbol in {object_name}")
                identity = _integer(row["trade_id"], "trade ID")
                trade_time = _integer(row["trade_time"], "trade_time")
                event_time = _integer(row["event_time"], "event_time")
                received_time = _integer(row["received_time"], "received_time")
                price = _decimal(row["price"], "trade price")
                quantity = _decimal(row["quantity"], "trade quantity")
                if not isinstance(row["is_buyer_maker"], bool) or not isinstance(row["order_type"], str):
                    raise ValueError(f"Invalid provider trade fields in {object_name}")
                if event_time != trade_time:
                    time_mismatch_count += 1
                    if len(time_mismatches) < 100:
                        time_mismatches.append({
                            "trade_id": identity, "event_time": event_time, "trade_time": trade_time,
                            "receive_hour_object": object_name,
                        })
                fingerprint = (
                    received_time, event_time, row["symbol"], price, quantity,
                    trade_time, row["is_buyer_maker"], row["order_type"],
                )
                if identity in seen:
                    if seen[identity]["fingerprint"] != fingerprint:
                        conflict_count += 1
                        if len(conflicts) < 100:
                            conflicts.append({
                                "trade_id": identity,
                                "first_object": seen[identity]["object"],
                                "repeated_object": object_name,
                            })
                    else:
                        duplicate_count += 1
                    continue
                seen[identity] = {"fingerprint": fingerprint, "object": object_name}
                loaded.append({
                    "trade_id": identity, "trade_time": trade_time, "event_time": event_time,
                    "received_time": received_time, "price": price, "quantity": quantity,
                    "is_buyer_maker": row["is_buyer_maker"], "order_type": row["order_type"],
                    "receive_hour_object": object_name,
                })
        object_reports.append({
            "object": object_name, "local_file": local_name, "sha256": sha256,
            "bytes": size, "parquet_rows": parquet.metadata.num_rows,
            "unique_rows_loaded": len(loaded) - rows_before,
        })

    return loaded, {
        "provider": manifest["provider"],
        "manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
        "pyarrow_version": pyarrow.__version__,
        "objects": object_reports,
        "raw_rows": sum(row["parquet_rows"] for row in object_reports),
        "unique_trade_ids": len(seen),
        "identical_duplicate_rows_removed": duplicate_count,
        "conflicting_trade_id_count": conflict_count,
        "conflicting_trade_ids": conflicts,
        "event_time_trade_time_mismatch_count": time_mismatch_count,
        "event_time_trade_time_mismatches": time_mismatches,
        "target_object_sha256": TARGET_TRADE_SHA256,
        "coverage": "Observed receive-hour objects, not a complete exchange-ledger certificate",
    }


def load_candles(path):
    raw = path.read_bytes()
    sha256 = hashlib.sha256(raw).hexdigest()
    if sha256 != CANDLE_SHA256:
        raise ValueError("Saved Bitget 5m candle file differs from frozen SHA-256")
    grouped, invalid_stamps, parse_errors = defaultdict(list), set(), []
    invalid_timestamp_count = 0
    invalid_cadence_count = 0
    with gzip.open(path, "rt", newline="", encoding="utf-8") as source:
        reader = csv.DictReader(source)
        required = {"timestamp", "open", "high", "low", "close", "base_volume", "symbol"}
        if not reader.fieldnames or not required.issubset(reader.fieldnames):
            raise ValueError("Unexpected saved candle CSV schema")
        for line_number, row in enumerate(reader, 2):
            if row.get("symbol") != SYMBOL:
                continue
            try:
                stamp = _integer(row["timestamp"], "candle timestamp")
            except ValueError:
                invalid_timestamp_count += 1
                parse_errors.append({"line": line_number, "reason": "INVALID_TIMESTAMP"})
                continue
            if not START_MS <= stamp < END_MS:
                continue
            if stamp % BAR_MS:
                invalid_cadence_count += 1
                parse_errors.append({"timestamp": stamp, "line": line_number, "reason": "INVALID_CADENCE"})
                continue
            try:
                values = {
                    key: _decimal(row[key], f"candle {key}", allow_zero=(key == "base_volume"))
                    for key in ("open", "high", "low", "close", "base_volume")
                }
                if (values["high"] < max(values["open"], values["close"])
                        or values["low"] > min(values["open"], values["close"])
                        or values["high"] < values["low"]):
                    raise ValueError("INVALID_OHLC")
                grouped[stamp].append({"timestamp": stamp, **values})
            except ValueError as exc:
                invalid_stamps.add(stamp)
                parse_errors.append({"timestamp": stamp, "line": line_number, "reason": str(exc)})

    bars, dispositions = {}, {}
    for stamp in range(START_MS, END_MS, BAR_MS):
        rows = grouped.get(stamp, [])
        if stamp in invalid_stamps:
            dispositions[stamp] = "INVALID_ROW"
        elif not rows:
            dispositions[stamp] = "MISSING_OR_INVALID"
        elif len(rows) != 1:
            dispositions[stamp] = "DUPLICATE_TIMESTAMP"
        else:
            bars[stamp] = rows[0]
            dispositions[stamp] = "VALID"
    return bars, {
        "provider": "Saved official Bitget 5m USDT-FUTURES candles",
        "sha256": sha256, "bytes": len(raw), "path": str(path),
        "expected_bars": (END_MS - START_MS) // BAR_MS,
        "valid_bars": len(bars),
        "invalid_timestamp_count": invalid_timestamp_count,
        "invalid_cadence_count": invalid_cadence_count,
        "bar_dispositions": {_utc_ms(stamp): state for stamp, state in dispositions.items()},
        "parse_errors": parse_errors[:100],
        "coverage": "Saved same-hour bars; source agreement is checked per rolling window",
    }, dispositions


def _bin_index(price, edges):
    if price == edges[-1]:
        return BIN_COUNT - 1
    for index in range(BIN_COUNT):
        if edges[index] <= price < edges[index + 1]:
            return index
    raise ValueError("Price outside frozen common profile range")


def _profile(bins, edges):
    total = sum(bins, Fraction(0))
    if total <= 0:
        raise ValueError("Cannot profile zero volume")
    poc = max(range(BIN_COUNT), key=lambda index: bins[index])
    left = right = poc
    area = bins[poc]
    while area * 10 < total * 7:
        if left == 0:
            right += 1
            area += bins[right]
        elif right == BIN_COUNT - 1 or bins[left - 1] >= bins[right + 1]:
            left -= 1
            area += bins[left]
        else:
            right += 1
            area += bins[right]
    hvn, lvn = [], []
    for index in range(1, BIN_COUNT - 1):
        center, lower, upper = bins[index], bins[index - 1], bins[index + 1]
        if center > lower and center > upper and 4 * center >= 3 * (lower + upper):
            hvn.append(index)
        if center < lower and center < upper and 4 * center <= lower + upper:
            lvn.append(index)
    return {
        "bins": bins, "total": total, "normalized": [value / total for value in bins],
        "poc_bin": poc, "poc_price": (edges[poc] + edges[poc + 1]) / 2,
        "poc_displacement_bps": (
            ((edges[poc] + edges[poc + 1]) / 2 - (edges[0] + edges[-1]) / 2)
            / ((edges[0] + edges[-1]) / 2) * 10000
        ),
        "va_left": left, "va_right": right,
        "va_low": edges[left], "va_high": edges[right + 1],
        "va_fraction": area / total, "hvn": hvn, "lvn": lvn,
    }


def _profile_output(profile):
    return {
        "bin_base_volume": [_number_text(value) for value in profile["bins"]],
        "total_base_volume": _number_text(profile["total"]),
        "normalized_bin_volume": [_number_text(value) for value in profile["normalized"]],
        "poc_bin": profile["poc_bin"],
        "poc_price": _number_text(profile["poc_price"]),
        "poc_displacement_bps_from_common_midpoint": _number_text(profile["poc_displacement_bps"]),
        "value_area_bins_inclusive": [profile["va_left"], profile["va_right"]],
        "value_area_price_bounds": [_number_text(profile["va_low"]), _number_text(profile["va_high"])],
        "value_area_volume_fraction": _number_text(profile["va_fraction"]),
        "hvn_bin_indices": profile["hvn"], "lvn_bin_indices": profile["lvn"],
    }


def _pearson(left, right):
    x, y = [float(value) for value in left], [float(value) for value in right]
    mean_x, mean_y = sum(x) / len(x), sum(y) / len(y)
    dx, dy = [value - mean_x for value in x], [value - mean_y for value in y]
    xx, yy = sum(value * value for value in dx), sum(value * value for value in dy)
    if xx == 0 or yy == 0:
        return None
    return round(sum(a * b for a, b in zip(dx, dy)) / math.sqrt(xx * yy), 12)


def _interval_overlap(first_low, first_high, second_low, second_high):
    union = max(first_high, second_high) - min(first_low, second_low)
    if union <= 0:
        return None
    intersection = max(Fraction(0), min(first_high, second_high) - max(first_low, second_low))
    return intersection / union


def _node_scores(reference, candidate):
    if not reference or not candidate:
        return {"matched": len(set(reference) & set(candidate)), "precision": None,
                "recall": None, "f1": None, "undefined": "EMPTY_NODE_SET"}
    matched = len(set(reference) & set(candidate))
    precision = Fraction(matched, len(candidate))
    recall = Fraction(matched, len(reference))
    f1 = Fraction(2 * matched, len(reference) + len(candidate)) if matched else Fraction(0)
    return {
        "matched": matched, "precision": _number_text(precision),
        "recall": _number_text(recall), "f1": _number_text(f1), "undefined": None,
    }


def _fidelity(trade_profile, candle_profile, edges):
    range_mid = (edges[0] + edges[-1]) / 2
    poc_delta = candle_profile["poc_price"] - trade_profile["poc_price"]
    poc_delta_bps = poc_delta / range_mid * 10000
    trade_vector, candle_vector = trade_profile["normalized"], candle_profile["normalized"]
    tvd = sum((abs(a - b) for a, b in zip(trade_vector, candle_vector)), Fraction(0)) / 2
    va_overlap = _interval_overlap(
        trade_profile["va_low"], trade_profile["va_high"],
        candle_profile["va_low"], candle_profile["va_high"],
    )
    return {
        "poc_bin_exact_match": trade_profile["poc_bin"] == candle_profile["poc_bin"],
        "candidate_minus_trade_poc_price": _number_text(poc_delta),
        "candidate_minus_trade_poc_bps": _number_text(poc_delta_bps),
        "absolute_poc_displacement_bps": _number_text(abs(poc_delta_bps)),
        "normalized_profile_total_variation_distance": _number_text(tvd),
        "normalized_profile_pearson_correlation": _pearson(trade_vector, candle_vector),
        "value_area_price_interval_iou": _number_text(va_overlap) if va_overlap is not None else None,
        "value_area_lower_boundary_candidate_minus_trade": _number_text(
            candle_profile["va_low"] - trade_profile["va_low"]),
        "value_area_upper_boundary_candidate_minus_trade": _number_text(
            candle_profile["va_high"] - trade_profile["va_high"]),
        "hvn_nodes": _node_scores(trade_profile["hvn"], candle_profile["hvn"]),
        "lvn_nodes": _node_scores(trade_profile["lvn"], candle_profile["lvn"]),
    }


def evaluate_window(trades, bars, start_ms, end_ms, candle_dispositions=None, global_errors=None):
    """Evaluate one half-open as-of window; profiles are diagnostics, not signals."""
    candle_dispositions = candle_dispositions or {}
    global_errors = global_errors or []
    event_trades = [row for row in trades if start_ms <= row["trade_time"] < end_ms]
    end_ns = end_ms * 1_000_000
    asof_trades = [row for row in event_trades if row["received_time"] < end_ns]
    late_trades = [row for row in event_trades if row["received_time"] >= end_ns]
    expected_stamps = list(range(start_ms, end_ms, BAR_MS))
    window_bars = [bars[stamp] for stamp in expected_stamps if stamp in bars]
    candle_issues = [
        (stamp, candle_dispositions.get(stamp, "VALID" if stamp in bars else "MISSING"))
        for stamp in expected_stamps
        if candle_dispositions.get(stamp, "VALID" if stamp in bars else "MISSING") != "VALID"
    ]
    reasons = []
    if global_errors:
        reasons.extend(global_errors)
    if len(window_bars) != 3 or candle_issues:
        reasons.extend(f"CANDLE_{state}" for _, state in candle_issues)
        if len(window_bars) != 3 and not candle_issues:
            reasons.append("CANDLE_MISSING")
    if len(asof_trades) == 0:
        reasons.append("NO_ASOF_TRADE_OBSERVATIONS")
    if late_trades:
        reasons.append("LATE_EVENT_TIME_TRADES")

    receive_counts = {
        object_name: {"asof": 0, "late_or_unavailable": 0}
        for object_name in TRADE_OBJECTS
    }
    for row in event_trades:
        key = row["receive_hour_object"]
        counts = receive_counts.setdefault(key, {"asof": 0, "late_or_unavailable": 0})
        counts["asof" if row["received_time"] < end_ns else "late_or_unavailable"] += 1

    result = {
        "start_utc": _utc_ms(start_ms), "end_utc": _utc_ms(end_ms),
        "status": "NOT_COMPARABLE", "reasons": reasons,
        "trade_coverage": {
            "event_time_observations": len(event_trades),
            "asof_available_observations": len(asof_trades),
            "late_or_unavailable_observations": len(late_trades),
            "receive_hour_counts": receive_counts,
            "asof_base_volume": _number_text(sum(
                (Fraction(row["quantity"]) for row in asof_trades), Fraction(0))),
            "event_window_base_volume_including_late": _number_text(sum(
                (Fraction(row["quantity"]) for row in event_trades), Fraction(0))),
            "latest_asof_received_time_ns": max(
                (row["received_time"] for row in asof_trades), default=None),
        },
        "candle_coverage": {
            "expected_5m_bars": 3, "valid_5m_bars": len(window_bars),
            "timestamps_utc": [_utc_ms(stamp) for stamp in expected_stamps if stamp in bars],
        },
        "source_consistency": None, "profiles": None, "fidelity": None,
    }
    if len(window_bars) != 3 or candle_issues or not asof_trades:
        return result, None

    candle = {
        "open": window_bars[0]["open"],
        "high": max(row["high"] for row in window_bars),
        "low": min(row["low"] for row in window_bars),
        "close": window_bars[-1]["close"],
        "base_volume": sum((Fraction(row["base_volume"]) for row in window_bars), Fraction(0)),
    }
    trade_high = max(row["price"] for row in asof_trades)
    trade_low = min(row["price"] for row in asof_trades)
    max_trade_time = max(row["trade_time"] for row in asof_trades)
    max_time_prices = {row["price"] for row in asof_trades if row["trade_time"] == max_trade_time}
    trade_close = next(iter(max_time_prices)) if len(max_time_prices) == 1 else None
    trade_volume = sum((Fraction(row["quantity"]) for row in asof_trades), Fraction(0))
    differences = {
        "trade_minus_candle_high": _number_text(Fraction(trade_high) - Fraction(candle["high"])),
        "trade_minus_candle_low": _number_text(Fraction(trade_low) - Fraction(candle["low"])),
        "trade_minus_candle_close": (
            _number_text(Fraction(trade_close) - Fraction(candle["close"]))
            if trade_close is not None else None
        ),
        "asof_trade_minus_candle_base_volume": _number_text(trade_volume - candle["base_volume"]),
    }
    result["source_consistency"] = {
        "trade_high": str(trade_high), "candle_high": str(candle["high"]),
        "trade_low": str(trade_low), "candle_low": str(candle["low"]),
        "trade_close": str(trade_close) if trade_close is not None else None,
        "trade_close_status": "UNAMBIGUOUS" if trade_close is not None else "AMBIGUOUS_MAX_TIMESTAMP_TIE",
        "candle_close": str(candle["close"]),
        "asof_trade_base_volume": _number_text(trade_volume),
        "candle_base_volume": _number_text(candle["base_volume"]),
        "differences": differences,
    }
    if trade_close is None:
        reasons.append("AMBIGUOUS_TRADE_CLOSE")
    else:
        if trade_high != candle["high"]:
            reasons.append("TRADE_CANDLE_HIGH_MISMATCH")
        if trade_low != candle["low"]:
            reasons.append("TRADE_CANDLE_LOW_MISMATCH")
        if trade_close != candle["close"]:
            reasons.append("TRADE_CANDLE_CLOSE_MISMATCH")
    if trade_volume != candle["base_volume"]:
        reasons.append("TRADE_CANDLE_BASE_VOLUME_MISMATCH")

    common_low = min(Fraction(trade_low), *(Fraction(row["low"]) for row in window_bars))
    common_high = max(Fraction(trade_high), *(Fraction(row["high"]) for row in window_bars))
    if common_high <= common_low:
        reasons.append("DEGENERATE_PRICE_RANGE")
        result["reasons"] = sorted(set(reasons))
        return result, None
    edges = [common_low + (common_high - common_low) * Fraction(index, BIN_COUNT)
             for index in range(BIN_COUNT + 1)]
    trade_bins = [Fraction(0) for _ in range(BIN_COUNT)]
    for row in asof_trades:
        trade_bins[_bin_index(Fraction(row["price"]), edges)] += Fraction(row["quantity"])

    candle_bins = [Fraction(0) for _ in range(BIN_COUNT)]
    bar_low, bar_high, bar_volume = Fraction(candle["low"]), Fraction(candle["high"]), candle["base_volume"]
    if bar_low == bar_high:
        candle_bins[_bin_index(bar_low, edges)] = bar_volume
    else:
        for index in range(BIN_COUNT):
            overlap = max(Fraction(0), min(bar_high, edges[index + 1]) - max(bar_low, edges[index]))
            if overlap:
                candle_bins[index] += bar_volume * overlap / (bar_high - bar_low)

    trade_profile = _profile(trade_bins, edges)
    candle_profile = _profile(candle_bins, edges)
    result["profiles"] = {
        "common_price_range": [_number_text(common_low), _number_text(common_high)],
        "bin_edges": [_number_text(edge) for edge in edges],
        "trade_at_price": _profile_output(trade_profile),
        "candle_range_spread_approximation": _profile_output(candle_profile),
        "candle_distribution_volume_conserved": sum(candle_bins, Fraction(0)) == bar_volume,
    }

    shape_reasons = set(reasons)
    result["reasons"] = sorted(shape_reasons)
    if not shape_reasons:
        result["status"] = "COMPARABLE"
        result["fidelity"] = _fidelity(trade_profile, candle_profile, edges)
    internal = {
        "status": result["status"], "edges": edges,
        "trade": trade_profile, "candle": candle_profile,
    }
    return result, internal


def _profile_turnover(previous, current):
    return sum((abs(a - b) for a, b in zip(previous["normalized"], current["normalized"])),
               Fraction(0)) / 2


def _node_delta(previous, current, key):
    before, after = set(previous[key]), set(current[key])
    return {"added": len(after - before), "removed": len(before - after)}


def _change_transitions(window_internal, end_boundaries):
    transitions = []
    for index in range(len(end_boundaries) - 1):
        previous, current = window_internal[index], window_internal[index + 1]
        base = {
            "from_end_utc": _utc_ms(end_boundaries[index]),
            "to_end_utc": _utc_ms(end_boundaries[index + 1]),
        }
        if not previous or not current or previous["status"] != "COMPARABLE" or current["status"] != "COMPARABLE":
            transitions.append({
                **base, "status": "NOT_COMPARABLE",
                "reason": "One or both adjacent windows failed the frozen source-consistency gate",
            })
            continue
        midpoint = (previous["edges"][0] + previous["edges"][-1]) / 2
        trade_move = (current["trade"]["poc_price"] - previous["trade"]["poc_price"]) / midpoint * 10000
        candle_move = (current["candle"]["poc_price"] - previous["candle"]["poc_price"]) / midpoint * 10000
        trade_sign = (trade_move > 0) - (trade_move < 0)
        candle_sign = (candle_move > 0) - (candle_move < 0)
        transitions.append({
            **base, "status": "COMPARABLE",
            "poc_move_bps": {
                "trade": _number_text(trade_move), "candle": _number_text(candle_move),
                "same_sign_or_zero_agreement": trade_sign == candle_sign,
                "absolute_move_error_bps": _number_text(abs(candle_move - trade_move)),
            },
            "normalized_profile_turnover_by_bin_index": {
                "trade": _number_text(_profile_turnover(previous["trade"], current["trade"])),
                "candle": _number_text(_profile_turnover(previous["candle"], current["candle"])),
            },
            "value_area_interval_overlap_iou": {
                "trade": _number_text(_interval_overlap(
                    previous["trade"]["va_low"], previous["trade"]["va_high"],
                    current["trade"]["va_low"], current["trade"]["va_high"],
                )),
                "candle": _number_text(_interval_overlap(
                    previous["candle"]["va_low"], previous["candle"]["va_high"],
                    current["candle"]["va_low"], current["candle"]["va_high"],
                )),
            },
            "node_changes_by_bin_index": {
                f"{source}_{node}": _node_delta(previous[source], current[source], node)
                for source in ("trade", "candle") for node in ("hvn", "lvn")
            },
        })
    return transitions


def build_report(trades, bars, trade_source, candle_source, candle_dispositions,
                 global_errors=None, generated_utc=None):
    global_errors = list(global_errors or [])
    end_boundaries = list(range(START_MS + WINDOW_MS, END_MS + 1, BAR_MS))
    reports, internals = [], []
    for end_ms in end_boundaries:
        report, internal = evaluate_window(
            trades, bars, end_ms - WINDOW_MS, end_ms,
            candle_dispositions=candle_dispositions, global_errors=global_errors,
        )
        reports.append(report)
        internals.append(internal)
    comparable = [row for row in reports if row["status"] == "COMPARABLE"]
    transitions = _change_transitions(internals, end_boundaries)
    report = {
        "schema_version": 1,
        "protocol_id": "issue-13-g04-common-rolling-profile-comparison-v4",
        "status": "DESCRIPTIVE_APPROXIMATION_COMPARISON" if comparable else "NO_COMPARABLE_WINDOWS",
        "generated_utc": generated_utc or datetime.now(timezone.utc).isoformat(),
        "symbol": SYMBOL,
        "instrument": "Bitget USDT-FUTURES AAPLUSDT stock-referenced perpetual; not listed-equity data",
        "source_integrity_errors": global_errors,
        "trade_source": trade_source,
        "candle_source": candle_source,
        "window_summary": {
            "planned_windows": len(reports),
            "comparable_windows": len(comparable),
            "not_comparable_windows": len(reports) - len(comparable),
            "poc_bin_exact_matches": sum(
                row["fidelity"]["poc_bin_exact_match"] for row in comparable),
        },
        "windows": reports,
        "profile_change_transitions": transitions,
        "payload_hash_policy": "SHA-256 of canonical report excluding generated_utc and payload_sha256",
        "interpretation_limits": [
            "Exploratory one-symbol/one-hour comparison of observed source agreement, not a strategy or performance test",
            "Observed public trades are not a complete exchange-ledger certificate",
            "Saved historical candle publication time is unknown; no end-to-end live availability claim",
            "The 15m candle is reconstructed from three 5m bars and is a proxy for the dashboard's native 15m input",
            "Ten rolling windows overlap heavily and are not independent replications",
            "No returns, costs, fills, significance tests or predictive utility were evaluated",
        ],
    }
    stable_payload = {
        key: value for key, value in report.items()
        if key not in ("generated_utc", "payload_sha256")
    }
    report["payload_sha256"] = _canonical_hash(stable_payload)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--candles", type=Path, default=CANDLE_PATH)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("Refusing to overwrite an existing report")
    try:
        protocol = json.loads(PROTOCOL_PATH.read_text())
        if protocol.get("protocol_id") != "issue-13-g04-common-rolling-profile-comparison-v4":
            raise ValueError("Unexpected frozen protocol")
        sources = protocol["instrument_and_sources"]
        if (sources["symbol"] != SYMBOL
                or tuple(sources["trade_source"]["receive_hour_objects"]) != TRADE_OBJECTS
                or sources["trade_source"]["target_object_sha256"] != TARGET_TRADE_SHA256
                or sources["candle_source"]["sha256"] != CANDLE_SHA256):
            raise ValueError("Implementation source constraints differ from frozen protocol")
        trades, trade_source = load_trade_sources(args.source_dir, args.manifest)
        bars, candle_source, candle_dispositions = load_candles(args.candles)
        global_errors = []
        if trade_source["event_time_trade_time_mismatch_count"]:
            global_errors.append("EVENT_TIME_TRADE_TIME_MISMATCH")
        if trade_source["conflicting_trade_id_count"]:
            global_errors.append("CONFLICTING_TRADE_ID")
        if candle_source["invalid_timestamp_count"]:
            global_errors.append("INVALID_CANDLE_TIMESTAMP")
        if candle_source["invalid_cadence_count"]:
            global_errors.append("INVALID_CANDLE_CADENCE")
        report = build_report(
            trades, bars, trade_source, candle_source, candle_dispositions,
            global_errors=global_errors,
        )
        with args.output.open("x", encoding="utf-8") as output:
            json.dump(report, output, indent=2, allow_nan=False)
            output.write("\n")
        print(json.dumps({
            "status": report["status"], "output": str(args.output),
            "comparable_windows": report["window_summary"]["comparable_windows"],
            "planned_windows": report["window_summary"]["planned_windows"],
            "payload_sha256": report["payload_sha256"],
        }))
        return 0
    except (OSError, ValueError, KeyError, TypeError, ArithmeticError, json.JSONDecodeError) as exc:
        raise SystemExit(f"Profile comparison failed; no success report: {exc}") from exc


if __name__ == "__main__":
    raise SystemExit(main())
