"""Adaptive-block sign-flip max-T candidate with cell-level eligibility and refusal rules (v3).

Reuses the v2 generators, tallies, Wilson intervals and gate thresholds unchanged.
"""

from __future__ import annotations

import argparse
import itertools
import json
import math
import random
import signal
import sys
import time
from pathlib import Path

import practical_inference_v2 as v2
from practical_inference_v2 import (
    ALPHA, CHOSEN_ARM, DAYS, MAX_ARTIFACT_BYTES, MAX_PROTOCOL_BYTES, MAX_RUNTIME,
    MIN_ACTIVE_DAYS, MIN_EVENTS, PANELS, SCENARIOS, Tally, decide, synthetic_panel,
    validate_panel, write_json, _frozen, _scenario_seed, _sha,
)

ROOT = Path(__file__).parent
PROTOCOL_PATH = ROOT / "results/practical-inference-v3-protocol-2026-11-05.json"
OUTPUT_PATH = ROOT / "results/practical-inference-v3-calibration-2026-11-05.json"
V2_PROTOCOL_PATH = v2.PROTOCOL_PATH
V2_RESULT_PATH = v2.OUTPUT_PATH

MIN_BLOCK_DAYS = 4
MIN_BLOCKS = 5
MIN_ELIGIBLE_CELLS = 6
RHO_CAP = 0.95
BLOCK_RULE_NUMERATOR = 2.0


def block_layout(rho_hat):
    """Declared block rule: L = max(4, ceil(2/(1-rho))), K = floor(28/L); None if K < 5."""
    rho = min(max(rho_hat, 0.0), RHO_CAP)
    length = max(MIN_BLOCK_DAYS, math.ceil(BLOCK_RULE_NUMERATOR / (1 - rho) - 1e-12))
    count = DAYS // length
    return (length, count) if count >= MIN_BLOCKS else None


def lag1(series):
    mean = sum(series) / len(series)
    den = sum((x - mean) ** 2 for x in series)
    if den <= 0:
        return None
    return sum((a - mean) * (b - mean) for a, b in zip(series, series[1:])) / den


def test_panel(sums, counts):
    """Return (adjusted p-values for eligible cells with their indices, info) or (None, reason)."""
    validate_panel(sums, counts)
    cells = len(sums[0])
    eligible = [
        h for h in range(cells)
        if sum(counts[d][h] for d in range(DAYS)) >= MIN_EVENTS
        and sum(1 for d in range(DAYS) if counts[d][h] > 0) >= MIN_ACTIVE_DAYS
    ]
    if len(eligible) < MIN_ELIGIBLE_CELLS:
        return None, "too_few_eligible_cells"
    daily = [
        sum(sums[d][h] / math.sqrt(max(counts[d][h], 1)) for h in eligible) / len(eligible)
        for d in range(DAYS)
    ]
    rho_hat = lag1(daily)
    if rho_hat is None:
        return None, "degenerate_daily_series"
    layout = block_layout(rho_hat)
    if layout is None:
        return None, "insufficient_blocks_under_dependence"
    length, count = layout
    offset = DAYS - length * count
    blocks, norms = [], []
    for h in eligible:
        column = [
            sum(sums[offset + b * length + i][h] for i in range(length))
            for b in range(count)
        ]
        norm = math.sqrt(sum(v * v for v in column))
        if norm <= 0:
            return None, "degenerate_cell"
        blocks.append(column)
        norms.append(norm)
    observed = [sum(col) / n for col, n in zip(blocks, norms)]
    maxima = []
    for bits in itertools.product((1, 0), repeat=count):
        signs = [1.0 if bit else -1.0 for bit in bits]
        maxima.append(max(
            sum(s * v for s, v in zip(signs, col)) / n for col, n in zip(blocks, norms)
        ))
    adjusted = {
        h: sum(1 for m in maxima if m >= t - 1e-12) / len(maxima)
        for h, t in zip(eligible, observed)
    }
    return adjusted, {"rho_hat": rho_hat, "block_days": length, "blocks": count}


def prospective_protocol():
    _, family = _frozen()
    return {
        "protocol_id": "issue-22-practical-inference-candidate-v3-adaptive-blocks",
        "created_at_utc": "2026-11-05",
        "status": "FROZEN_BEFORE_ANY_V3_CALIBRATION",
        "scope": "Synthetic calibration of a 12-hypothesis adaptive-block sign-flip max-T candidate. No market data, no efficacy claim, no change to walkforward-protocol.json, dist/, or v1/v2 artifacts.",
        "source_hashes": {
            "research/results/walkforward-protocol.json": _sha(v2.WALKFORWARD_PATH),
            "research/results/practical-inference-v2-protocol-2026-11-04.json": _sha(V2_PROTOCOL_PATH),
            "research/results/practical-inference-v2-calibration-2026-11-04.json": _sha(V2_RESULT_PATH),
        },
        "v2_result_motivating_v3": "v2 FAIL: size inflated under serial_heteroskedastic (any-rejection 0.097) and long_memory_serial (0.248) with fixed 4-day blocks; sparse_days refusal 6.35% > 5%. Defects fixed here from theory only; no v2 rate was used to select a constant.",
        "family": family,
        "family_choice": "Identical to v2: base arm three_close_momentum x 2 timeframes x 3 groups x 2 sides (12 of the 132 frozen hypotheses).",
        "config": {
            "alpha": ALPHA, "days_per_panel": DAYS, "hypotheses": 12,
            "minimum_events_per_cell": MIN_EVENTS,
            "minimum_nonempty_days_per_cell": MIN_ACTIVE_DAYS,
            "minimum_eligible_cells": MIN_ELIGIBLE_CELLS,
            "minimum_block_days": MIN_BLOCK_DAYS, "minimum_blocks": MIN_BLOCKS,
            "block_rule_numerator": BLOCK_RULE_NUMERATOR, "rho_cap": RHO_CAP,
            "panels_per_scenario": PANELS, "seed": v2.SEED,
            "scenario_generators_and_seeds": "Identical to v2 (same panels).",
            "maximum_runtime_seconds": MAX_RUNTIME,
            "maximum_artifact_bytes": MAX_ARTIFACT_BYTES,
        },
        "statistic": {
            "dependence_estimate": "Daily series D_t = mean over eligible cells of S_th / sqrt(max(C_th,1)); rho_hat = lag-1 sample autocorrelation of D_t (a declared dependence proxy; sign-flip validity needs near-independent blocks).",
            "block_rule": "rho = clip(rho_hat, 0, 0.95); L = max(4, ceil(2/(1-rho))); K = floor(28/L) non-overlapping contiguous blocks of L days taken from the end of the fold (the earliest 28-K*L days are dropped). Theory: AR(1) correlation time is about 1/(1-rho) days, so blocks of about twice that length leave residual between-block correlation of order rho^L, which is small only when K is not tiny.",
            "resolution_refusal": "If K < 5 the panel is refused as INCONCLUSIVE (insufficient_blocks_under_dependence). Reason: with K blocks the smallest attainable sign-flip p-value is 2^-K; K=5 gives 1/32 and K<=4 gives >= 1/16 > .05, so no rejection is possible and size cannot be controlled at this resolution. This is a refusal, never a pass.",
            "cell_eligibility": "A cell is eligible if >= 30 events and >= 10 nonempty days. Ineligible cells are dropped from the tested family (eligibility uses counts only, which are independent of outcomes by declared assumption; the retained family is still tested with single-step max-T so FWER is controlled for it). The panel is refused (too_few_eligible_cells) only if fewer than 6 of 12 cells are eligible. Replaces v2's whole-panel refusal on any ineligible cell.",
            "cell_statistic": "B[b][h] = block sum of S; T_h = sum_b B[b][h] / sqrt(sum_b B[b][h]^2).",
            "reference_distribution": "Exact enumeration of all 2^K block sign vectors, shared across eligible cells.",
            "multiplicity": "Single-step max-T over eligible cells: adjusted p_h = #{vectors with max_j T*_j >= T_h} / 2^K; reject if <= .05.",
            "other_refusals": "degenerate_daily_series, degenerate_cell.",
        },
        "assumptions": [
            "Block sums approximately independent and symmetric about 0 at the null boundary; lag-1 autocorrelation is only a proxy for long-memory dependence.",
            "Event counts independent of outcomes.",
            "A 28-day fold has few blocks; when rho_hat > 0.6 the rule gives L >= 6, K <= 4 and the design refuses rather than tests.",
            "Only 28-day folds and the declared generators are covered.",
        ],
        "calibration_rules": {
            "runs": "Exactly one run: 2000 panels per scenario for the same 7 scenarios and seeds as v2. No retry, reseed or parameter change.",
            "thresholds": "Unchanged from v2: FAIL if any null FWER Wilson lower bound > .075 or power Wilson upper bound < .30; PASS only if all null FWER Wilson upper bounds <= .075, power Wilson lower bound >= .50, every scenario refusal rate <= 5%, and no runtime failure; otherwise INCONCLUSIVE.",
            "expected_honest_outcome": "Refusals under serial/long-memory scenarios are by design and count against the unchanged 5% refusal limit, so a PASS requires the dependence rule to keep size controlled without refusing more than 5% in any scenario. If it does not, the finding is that no tested valid method with so few days resolves persistent dependence.",
            "runtime": f"{MAX_RUNTIME}s deadline; failure persisted as RUNTIME_OR_EXECUTION_FAILURE; no rerun.",
        },
    }


class Tally3(Tally):
    def __init__(self, name):
        super().__init__(name)
        self.block_days = {}

    def add3(self, adjusted, info):
        if adjusted is None:
            self.add(None, info)
            return
        self.panels += 1
        self.valid += 1
        key = str(info["block_days"])
        self.block_days[key] = self.block_days.get(key, 0) + 1
        rejected = {h: p <= ALPHA for h, p in adjusted.items()}
        self.any_rejection += any(rejected.values())
        for h, r in rejected.items():
            self.cell_rejections[h] += r

    def report(self):
        out = super().report()
        out["block_days_used"] = dict(sorted(self.block_days.items()))
        return out


class _Terminated(Exception):
    pass


def _on_term(signum, frame):
    raise _Terminated("SIGTERM")


def run():
    if OUTPUT_PATH.exists():
        raise FileExistsError("REFUSE: the single bounded calibration run already exists")
    if json.loads(PROTOCOL_PATH.read_text()) != prospective_protocol():
        raise ValueError("REFUSE: protocol file differs from the frozen design")
    signal.signal(signal.SIGTERM, _on_term)
    start = time.monotonic()
    tallies = {name: Tally3(name) for name in SCENARIOS}
    failure = None
    try:
        for name in SCENARIOS:
            rng = random.Random(_scenario_seed(name))
            for _ in range(PANELS):
                if time.monotonic() - start > MAX_RUNTIME:
                    raise TimeoutError("internal runtime deadline")
                sums, counts = synthetic_panel(rng, name)
                adjusted, info = test_panel(sums, counts)
                tallies[name].add3(adjusted, info)
    except BaseException as exc:  # persist partial evidence
        failure = f"{type(exc).__name__}: {exc}"
    reports = [t.report() for t in tallies.values()]
    artifact = {
        "protocol_id": prospective_protocol()["protocol_id"],
        "protocol_sha256": _sha(PROTOCOL_PATH),
        "actual_market_data_used": False,
        "artifact_status": "COMPLETE_SYNTHETIC_ONLY",
        "calibration_gate": decide(reports, runtime_failed=failure is not None),
        "runtime_seconds": round(time.monotonic() - start, 3),
        "results": {r["scenario"]: r for r in reports},
        "limitations": [
            "Synthetic generators only; no market validity or efficacy claim.",
            "Frozen walkforward-protocol.json, dist/ and v1/v2 artifacts are unchanged; this result does not satisfy them.",
        ],
    }
    if failure:
        artifact["artifact_status"] = "RUNTIME_OR_EXECUTION_FAILURE"
        artifact["failure"] = failure
    write_json(OUTPUT_PATH, artifact)
    print(OUTPUT_PATH, artifact["calibration_gate"])
    return 1 if failure else 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--write-protocol", action="store_true")
    group.add_argument("--run", action="store_true")
    args = parser.parse_args()
    if args.write_protocol:
        if PROTOCOL_PATH.exists():
            raise FileExistsError("REFUSE: never overwrite the frozen design")
        write_json(PROTOCOL_PATH, prospective_protocol(), MAX_PROTOCOL_BYTES)
        print(PROTOCOL_PATH)
        return 0
    return run()


if __name__ == "__main__":
    sys.exit(main())
