"""Narrowed day-block sign-flip max-T candidate with one bounded synthetic calibration (v2)."""

from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import math
import random
import signal
import sys
import time
from pathlib import Path


ROOT = Path(__file__).parent
WALKFORWARD_PATH = ROOT / "results/walkforward-protocol.json"
V1_PROTOCOL_PATH = ROOT / "results/practical-inference-protocol-2026-11-04.json"
PROTOCOL_PATH = ROOT / "results/practical-inference-v2-protocol-2026-11-04.json"
OUTPUT_PATH = ROOT / "results/practical-inference-v2-calibration-2026-11-04.json"

ALPHA = 0.05
DAYS = 28
BLOCK_DAYS = 4
BLOCKS = DAYS // BLOCK_DAYS
MIN_EVENTS = 30
MIN_ACTIVE_DAYS = 10
CHOSEN_ARM = "three_close_momentum"
NULL_SCENARIOS = (
    "iid_heteroskedastic",
    "serial_heteroskedastic",
    "shared_cross_cell_heteroskedastic",
    "sparse_days",
    "skewed_mean_zero",
    "long_memory_serial",
)
POWER_SCENARIO = "power_three_of_twelve"
SCENARIOS = NULL_SCENARIOS + (POWER_SCENARIO,)
POWER_CELLS = (0, 4, 8)
POWER_EFFECT = 0.5
SEED = 202611042215
PANELS = 2000
MAX_RUNTIME = 110
MAX_ARTIFACT_BYTES = 8 * 1024 * 1024
MAX_PROTOCOL_BYTES = 256 * 1024

CONFIG = {
    "alpha": ALPHA,
    "days_per_panel": DAYS,
    "block_days": BLOCK_DAYS,
    "blocks": BLOCKS,
    "hypotheses": 12,
    "event_counts": "On an active cell-day, 2 + Bernoulli(0.5) events; counts are independent of outcomes.",
    "minimum_events_per_cell": MIN_EVENTS,
    "minimum_nonempty_days_per_cell": MIN_ACTIVE_DAYS,
    "panels_per_scenario": PANELS,
    "seed": SEED,
    "maximum_runtime_seconds": MAX_RUNTIME,
    "maximum_artifact_bytes": MAX_ARTIFACT_BYTES,
    "confidence_z": 1.959963984540054,
}


def _frozen():
    frozen = json.loads(WALKFORWARD_PATH.read_text())
    inputs = frozen["frozen_inputs"]
    arms = list(frozen["fixed_arm_family"]["arms"])
    if CHOSEN_ARM not in arms:
        raise ValueError("REFUSE: chosen arm missing from frozen walk-forward protocol")
    family = [
        f"{CHOSEN_ARM}|{timeframe}|{group}|{side}"
        for timeframe in inputs["timeframes"]
        for group in inputs["groups"]
        for side in ("long", "short")
    ]
    if len(family) != CONFIG["hypotheses"] or len(set(family)) != len(family):
        raise ValueError("REFUSE: narrowed family must contain exactly 12 distinct hypotheses")
    if len(arms) * len(family) != frozen["dependence_and_multiplicity"]["primary_hypothesis_count"]:
        raise ValueError("REFUSE: narrowed family does not embed in the frozen 132 family")
    return frozen, family


def _sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def prospective_protocol():
    _, family = _frozen()
    return {
        "protocol_id": "issue-22-practical-inference-candidate-v2-narrowed",
        "created_at_utc": "2026-11-04",
        "status": "FROZEN_BEFORE_ANY_V2_CALIBRATION",
        "scope": "Synthetic calibration of a narrowed 12-hypothesis day-block sign-flip max-T candidate. No market data, no efficacy claim, no change to walkforward-protocol.json or the v1 artifacts.",
        "source_hashes": {
            "research/results/walkforward-protocol.json": _sha(WALKFORWARD_PATH),
            "research/results/practical-inference-protocol-2026-11-04.json": _sha(V1_PROTOCOL_PATH),
        },
        "family": family,
        "family_choice": {
            "rule": "Structural, performance-blind: the single base arm three_close_momentum crossed with every frozen timeframe x group x side (1 x 2 x 3 x 2 = 12 of the 132 frozen hypotheses).",
            "justification": "momentum_rvol_1_5, momentum_1h_ema20_context and momentum_4h_ema20_context are filtered subsets of three_close_momentum, so testing the base arm covers the shared signal without multiplying near-duplicate hypotheses; the remaining arms are different signal definitions and stay in the 132 exploratory family. Choice made from the protocol text only, with no outcome data.",
            "relation_to_132": "Strict subset. The 132 family and its Holm plan are unchanged; v2 is a separate narrowed candidate and does not retroactively relabel any inspected data.",
        },
        "config": CONFIG,
        "statistic": {
            "daily_panel": "28 UTC calendar rows x 12 columns of event-outcome sums S and event counts C; empty days remain.",
            "blocks": "Seven fixed non-overlapping contiguous 4-day blocks (28 = 7 x 4). The frozen walk-forward plan names 5-day blocks for resampling; 4 is used here only so blocks tile the 28-day fold exactly and exact enumeration is possible. This is a declared difference.",
            "cell_statistic": "B[b][h] = sum of S over block b. T_h = sum_b B[b][h] / sqrt(sum_b B[b][h]^2), a self-normalised block-sum statistic for H0: block sums symmetric about 0 (theta <= 0).",
            "reference_distribution": "Exact enumeration of all 2^7 = 128 block sign vectors, one vector shared by all 12 hypotheses; no Monte Carlo resampling error.",
            "multiplicity": "Single-step max-T: adjusted p_h = #{sign vectors with max_j T*_j >= T_h} / 128. Reject h if adjusted p_h <= .05 (at most 6 of 128 vectors).",
            "eligibility": "Every hypothesis needs >= 30 events, >= 10 nonempty days and positive sum of squared block sums; otherwise the whole panel is refused (counted as no rejection, reported separately).",
        },
        "assumptions": [
            "Block sums are independent across blocks and symmetric about zero under the null boundary theta = 0; heavy skew or dependence across 4-day blocks violates this.",
            "Calibration is at the null boundary theta = 0; strictly negative means are expected to be more conservative but are not simulated.",
            "Only a 28-day fold is covered; other lengths need new calibration.",
        ],
        "synthetic_cases": {
            "iid_heteroskedastic": "Gaussian noise (loadings common/group/noise 0/0/1) with lognormal day volatility.",
            "serial_heteroskedastic": "AR(1) common rho .65 and group AR(1) rho .45, loadings .55/.35/.75.",
            "shared_cross_cell_heteroskedastic": "iid common day factor, loadings .90/.20/.45.",
            "sparse_days": "72% active days, 90% active cells per day, iid noise; no forced empty cell.",
            "skewed_mean_zero": "Per-event noise Exp(1)-1 (mean 0, skewed) with day volatility plus common gaussian loading .5.",
            "long_memory_serial": "Common AR(1) rho .90 and group AR(1) rho .80, loadings .70/.50/.50: dependence extending across block boundaries.",
            POWER_SCENARIO: f"iid_heteroskedastic noise plus +{POWER_EFFECT} per-event mean on cells {list(POWER_CELLS)} (one false null in 3 of 12 hypotheses; noise sd about 1).",
        },
        "calibration_rules": {
            "runs": "Exactly one run: 2000 independent panels for each of 7 scenarios, seeded per scenario from the frozen seed. No retry, reseed, or parameter change after seeing results.",
            "intervals": "Two-sided 95% Wilson intervals for each null scenario's any-rejection rate (FWER) and for power; marginal per-cell rates reported as diagnostics.",
            "fail": "FAIL if any null scenario FWER Wilson lower bound exceeds .075, or power scenario any-rejection Wilson upper bound is below .30.",
            "pass": "PASS only if every null scenario has FWER Wilson upper bound <= .075, power Wilson lower bound >= .50, and every scenario has refusal rate <= 5%, and no runtime failure.",
            "inconclusive": "Anything else (including a FWER upper bound above .075 without a lower bound above it, low power, or refusals > 5%).",
            "interpretation": "A PASS is a synthetic size/power result for this exact v2 candidate on the declared generators only. It validates no market assumption and supports no efficacy claim. Power is for the declared alternative only.",
            "runtime": f"{MAX_RUNTIME}s internal monotonic deadline; SIGTERM or exception persists RUNTIME_OR_EXECUTION_FAILURE with partial tallies; no rerun.",
        },
    }


def write_json(path, value, limit=MAX_ARTIFACT_BYTES):
    text = json.dumps(value, indent=2, sort_keys=True) + "\n"
    if len(text.encode("utf-8")) > limit:
        raise RuntimeError("artifact exceeds the predeclared size limit")
    path.write_text(text)


def wilson(successes, trials):
    if trials <= 0 or not 0 <= successes <= trials:
        raise ValueError("positive binomial trial count and valid successes required")
    z = CONFIG["confidence_z"]
    rate = successes / trials
    den = 1 + z * z / trials
    center = (rate + z * z / (2 * trials)) / den
    half = z * math.sqrt(rate * (1 - rate) / trials + z * z / (4 * trials * trials)) / den
    return [max(0.0, center - half), min(1.0, center + half)]


SIGNS = [
    tuple(1.0 if bit else -1.0 for bit in bits)
    for bits in itertools.product((1, 0), repeat=BLOCKS)
]  # first vector is all +1 (identity)


def validate_panel(sums, counts, cells=12):
    if len(sums) != DAYS or len(counts) != DAYS:
        raise ValueError("panel must have exactly 28 daily rows")
    for srow, crow in zip(sums, counts):
        if len(srow) != cells or len(crow) != cells:
            raise ValueError("panel must have exactly 12 columns")
        for s, c in zip(srow, crow):
            if not math.isfinite(s) or isinstance(c, bool) or not isinstance(c, int) or c < 0:
                raise ValueError("sums must be finite and counts nonnegative integers")
            if c == 0 and s != 0:
                raise ValueError("empty cell-day must have zero sum")


def test_panel(sums, counts):
    """Return (None, reason) if refused, else (adjusted p-values list, T list)."""
    validate_panel(sums, counts)
    cells = len(sums[0])
    blocks = []
    for h in range(cells):
        events = sum(counts[d][h] for d in range(DAYS))
        active = sum(1 for d in range(DAYS) if counts[d][h] > 0)
        if events < MIN_EVENTS or active < MIN_ACTIVE_DAYS:
            return None, "ineligible_cell"
        column = [
            sum(sums[b * BLOCK_DAYS + i][h] for i in range(BLOCK_DAYS))
            for b in range(BLOCKS)
        ]
        if sum(v * v for v in column) <= 0:
            return None, "degenerate_cell"
        blocks.append(column)
    norms = [math.sqrt(sum(v * v for v in col)) for col in blocks]
    observed = [sum(col) / n for col, n in zip(blocks, norms)]
    maxima = []
    for signs in SIGNS:
        best = -math.inf
        for col, n in zip(blocks, norms):
            value = sum(s * v for s, v in zip(signs, col)) / n
            if value > best:
                best = value
        maxima.append(best)
    adjusted = [
        sum(1 for m in maxima if m >= t - 1e-12) / len(SIGNS) for t in observed
    ]
    return adjusted, observed


def _ar1(rng, days, rho):
    previous = 0.0
    values = []
    for _ in range(days):
        previous = rho * previous + math.sqrt(1 - rho * rho) * rng.gauss(0, 1)
        values.append(previous)
    return values


def synthetic_panel(rng, scenario):
    if scenario not in SCENARIOS:
        raise ValueError("unknown scenario")
    cells = CONFIG["hypotheses"]
    sums = [[0.0] * cells for _ in range(DAYS)]
    counts = [[0] * cells for _ in range(DAYS)]
    volatility = [math.exp(0.35 * rng.gauss(0, 1) - 0.35 ** 2 / 2) for _ in range(DAYS)]
    common = [0.0] * DAYS
    groups = [[0.0] * DAYS for _ in range(3)]
    loadings = (0.0, 0.0, 1.0)
    if scenario == "serial_heteroskedastic":
        common = _ar1(rng, DAYS, 0.65)
        groups = [_ar1(rng, DAYS, 0.45) for _ in range(3)]
        loadings = (0.55, 0.35, 0.75)
    elif scenario == "long_memory_serial":
        common = _ar1(rng, DAYS, 0.90)
        groups = [_ar1(rng, DAYS, 0.80) for _ in range(3)]
        loadings = (0.70, 0.50, 0.50)
    elif scenario == "shared_cross_cell_heteroskedastic":
        common = [rng.gauss(0, 1) for _ in range(DAYS)]
        groups = [[rng.gauss(0, 1) for _ in range(DAYS)] for _ in range(3)]
        loadings = (0.90, 0.20, 0.45)
    elif scenario == "skewed_mean_zero":
        common = [rng.gauss(0, 1) for _ in range(DAYS)]
        loadings = (0.5, 0.0, 1.0)
    active_days = (
        {day for day in range(DAYS) if rng.random() < 0.72}
        if scenario == "sparse_days" else set(range(DAYS))
    )
    for day in range(DAYS):
        for cell in range(cells):
            if scenario == "sparse_days" and (day not in active_days or rng.random() >= 0.90):
                continue
            count = 2 + int(rng.random() < 0.5)
            counts[day][cell] = count
            group = (cell % 6) // 2
            a, b, c = loadings
            total = 0.0
            for _ in range(count):
                if scenario == "skewed_mean_zero":
                    noise = rng.expovariate(1.0) - 1.0
                else:
                    noise = rng.gauss(0, 1)
                shift = POWER_EFFECT if scenario == POWER_SCENARIO and cell in POWER_CELLS else 0.0
                total += shift + volatility[day] * (
                    a * common[day] + b * groups[group][day] + c * noise
                )
            sums[day][cell] = total
    return sums, counts


def _scenario_seed(name):
    return SEED + (SCENARIOS.index(name) + 1) * 100003


class Tally:
    def __init__(self, name):
        self.name = name
        self.panels = 0
        self.refused = {}
        self.any_rejection = 0
        self.cell_rejections = [0] * CONFIG["hypotheses"]
        self.valid = 0

    def add(self, adjusted, reason):
        self.panels += 1
        if adjusted is None:
            self.refused[reason] = self.refused.get(reason, 0) + 1
            return
        self.valid += 1
        rejected = [p <= ALPHA for p in adjusted]
        self.any_rejection += any(rejected)
        for i, r in enumerate(rejected):
            self.cell_rejections[i] += r

    def report(self):
        n = self.panels
        refused = sum(self.refused.values())
        out = {
            "scenario": self.name,
            "panels": n,
            "valid_panels": self.valid,
            "refused_panels": refused,
            "refusal_reasons": dict(sorted(self.refused.items())),
            "any_rejection": self.any_rejection,
        }
        if n:
            out["any_rejection_rate"] = self.any_rejection / n
            out["any_rejection_wilson_95"] = wilson(self.any_rejection, n)
            out["refusal_rate"] = refused / n
            out["marginal_rejection_rate_by_cell"] = [r / n for r in self.cell_rejections]
        return out


def decide(reports, runtime_failed=False):
    if runtime_failed:
        return "INCONCLUSIVE"
    by = {r["scenario"]: r for r in reports}
    if set(by) != set(SCENARIOS) or any(r["panels"] < PANELS for r in reports):
        return "INCONCLUSIVE"
    for name in NULL_SCENARIOS:
        if by[name]["any_rejection_wilson_95"][0] > 0.075:
            return "FAIL"
    if by[POWER_SCENARIO]["any_rejection_wilson_95"][1] < 0.30:
        return "FAIL"
    ok = all(by[n]["any_rejection_wilson_95"][1] <= 0.075 for n in NULL_SCENARIOS)
    ok = ok and by[POWER_SCENARIO]["any_rejection_wilson_95"][0] >= 0.50
    ok = ok and all(r["refusal_rate"] <= 0.05 for r in reports)
    return "PASS" if ok else "INCONCLUSIVE"


class _Terminated(Exception):
    pass


def _on_term(signum, frame):
    raise _Terminated("SIGTERM")


def run():
    if OUTPUT_PATH.exists():
        raise FileExistsError("REFUSE: the single bounded calibration run already exists")
    protocol_text = PROTOCOL_PATH.read_text()
    if json.loads(protocol_text) != prospective_protocol():
        raise ValueError("REFUSE: protocol file differs from the frozen design")
    signal.signal(signal.SIGTERM, _on_term)
    start = time.monotonic()
    tallies = {name: Tally(name) for name in SCENARIOS}
    artifact = {
        "protocol_id": prospective_protocol()["protocol_id"],
        "protocol_sha256": _sha(PROTOCOL_PATH),
        "actual_market_data_used": False,
        "artifact_status": "COMPLETE_SYNTHETIC_ONLY",
    }
    failure = None
    try:
        for name in SCENARIOS:
            rng = random.Random(_scenario_seed(name))
            for _ in range(PANELS):
                if time.monotonic() - start > MAX_RUNTIME:
                    raise TimeoutError("internal runtime deadline")
                sums, counts = synthetic_panel(rng, name)
                adjusted, info = test_panel(sums, counts)
                tallies[name].add(adjusted, info if adjusted is None else None)
    except BaseException as exc:  # persist partial evidence
        failure = f"{type(exc).__name__}: {exc}"
    reports = [t.report() for t in tallies.values()]
    gate = decide(reports, runtime_failed=failure is not None)
    artifact.update(
        {
            "calibration_gate": gate,
            "runtime_seconds": round(time.monotonic() - start, 3),
            "results": {r["scenario"]: r for r in reports},
            "limitations": [
                "Synthetic generators only; a PASS would not validate any market assumption or show efficacy.",
                "Power is for one declared alternative (+0.5 per event on 3 of 12 cells) only.",
                "Sign-flip validity relies on block-sum symmetry and independence across 4-day blocks.",
                "Frozen walkforward-protocol.json 132-family, 5-day-block plan and v1 artifacts are unchanged; this v2 result does not satisfy them.",
            ],
        }
    )
    if failure:
        artifact["artifact_status"] = "RUNTIME_OR_EXECUTION_FAILURE"
        artifact["failure"] = failure
    write_json(OUTPUT_PATH, artifact)
    print(OUTPUT_PATH, gate)
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
