"""Synthetic-only calibration for the frozen UTC-day moving-block protocol."""

from __future__ import annotations

import json
import math
import random
from pathlib import Path


ROOT = Path(__file__).parent
PROTOCOL_PATH = ROOT / "results" / "walkforward-protocol.json"
OUTPUT_PATH = ROOT / "results" / "inference-calibration.json"

# Frozen before simulation. Keep this modest run as a diagnostic, not a substitute
# for a larger calibration study or actual reserved-fold validation.
CONFIG = {
    "seed": 20261102,
    "days_per_fold": 28,
    "block_days": 5,
    "hypothesis_count": 132,
    "simulation_replicates_per_scenario": 120,
    "bootstrap_draws_per_replicate": 199,
    "nominal_type_i": 0.05,
    "type_i_point_tolerance": [0.025, 0.075],
    "familywise_upper_wilson_tolerance": 0.075,
    "confidence_level": 0.95,
}

SCENARIOS = ("iid_day_null", "shared_crossarm_factor", "ar1_day_null", "sparse_empty_days")


def event_weighted_means(daily_sums, daily_counts):
    """Return one event-weighted mean per cell; empty calendar days remain rows."""
    days = len(daily_sums)
    if days == 0 or len(daily_counts) != days:
        raise ValueError("daily sums and counts must have the same nonzero day count")
    cells = len(daily_sums[0])
    if cells == 0 or any(len(row) != cells for row in daily_sums + daily_counts):
        raise ValueError("daily panels must be rectangular and have at least one cell")
    totals = [0.0] * cells
    counts = [0] * cells
    for day in range(days):
        for cell in range(cells):
            count = daily_counts[day][cell]
            value = daily_sums[day][cell]
            if count < 0 or not math.isfinite(value):
                raise ValueError("event counts must be nonnegative and sums finite")
            totals[cell] += value
            counts[cell] += count
    return [totals[cell] / counts[cell] if counts[cell] else None for cell in range(cells)]


def null_center_daily_sums(daily_sums, daily_counts):
    """Center each cell at its event-weighted mean without removing empty dates."""
    means = event_weighted_means(daily_sums, daily_counts)
    centered = []
    for day, row in enumerate(daily_sums):
        centered.append([
            row[cell] - means[cell] * daily_counts[day][cell]
            if means[cell] is not None else 0.0
            for cell in range(len(means))
        ])
    return means, centered


def moving_block_indices(rng, days, block_days=5):
    """Sample non-wrapping contiguous day blocks until the original day count."""
    if days < block_days or block_days < 1:
        raise ValueError("days must be at least one complete block")
    sampled = []
    while len(sampled) < days:
        start = rng.randrange(days - block_days + 1)
        sampled.extend(range(start, start + block_days))
    return sampled[:days]


def synchronous_block_draws(rng, draw_count, days=28, block_days=5):
    """Make one shared matrix of date-index draws, reused for every panel cell."""
    if draw_count < 1:
        raise ValueError("at least one bootstrap draw is required")
    return [
        moving_block_indices(rng, days, block_days)
        for _ in range(draw_count)
    ]


def synchronous_block_pvalues(daily_sums, daily_counts, draws):
    """One-sided, null-centered event-mean tests using shared date draws for all cells."""
    observed, centered = null_center_daily_sums(daily_sums, daily_counts)
    if any(value is None for value in observed):
        return [None] * len(observed)
    days = len(daily_sums)
    cells = len(observed)
    if any(len(draw) != days or any(index < 0 or index >= days for index in draw) for draw in draws):
        raise ValueError("each synchronous draw must contain valid indices for the full fold")

    exceedances = [0] * cells
    for draw in draws:
        sampled_sums = [0.0] * cells
        sampled_counts = [0] * cells
        for day in draw:
            row_sums = daily_sums[day]
            row_counts = daily_counts[day]
            centered_row = centered[day]
            for cell in range(cells):
                sampled_sums[cell] += centered_row[cell]
                sampled_counts[cell] += row_counts[cell]
        for cell in range(cells):
            # A zero-event resample contributes the null value 0; it is not dropped.
            statistic = (
                sampled_sums[cell] / sampled_counts[cell]
                if sampled_counts[cell] else 0.0
            )
            if statistic >= observed[cell]:
                exceedances[cell] += 1
    draw_count = len(draws)
    if not draw_count:
        raise ValueError("at least one bootstrap draw is required")
    return [(exceedances[cell] + 1) / (draw_count + 1) for cell in range(cells)]


def holm_step_down(p_values, alpha=0.05):
    """Apply Holm to the complete family, refusing to silently drop invalid cells."""
    count = len(p_values)
    if count == 0 or any(
        value is None or not math.isfinite(value) or value < 0 or value > 1
        for value in p_values
    ):
        return {
            "status": "INVALID_FAMILY",
            "family_size": count,
            "adjusted_p_values": None,
            "rejected": None,
        }
    ordered = sorted(enumerate(p_values), key=lambda item: (item[1], item[0]))
    adjusted = [0.0] * count
    running_max = 0.0
    rejected = [False] * count
    still_rejecting = True
    for rank, (index, value) in enumerate(ordered):
        candidate = min(1.0, (count - rank) * value)
        running_max = max(running_max, candidate)
        adjusted[index] = running_max
        if still_rejecting and value <= alpha / (count - rank):
            rejected[index] = True
        else:
            still_rejecting = False
    return {
        "status": "VALID_FAMILY",
        "family_size": count,
        "adjusted_p_values": adjusted,
        "rejected": rejected,
    }


def wilson_interval(successes, trials, confidence_z=1.959963984540054):
    if trials <= 0 or successes < 0 or successes > trials:
        raise ValueError("invalid binomial counts")
    rate = successes / trials
    z2 = confidence_z * confidence_z
    denominator = 1 + z2 / trials
    center = (rate + z2 / (2 * trials)) / denominator
    half = confidence_z * math.sqrt(
        rate * (1 - rate) / trials + z2 / (4 * trials * trials)
    ) / denominator
    return [max(0.0, center - half), min(1.0, center + half)]


def _ar1(rng, days, rho):
    values = []
    previous = 0.0
    scale = math.sqrt(1 - rho * rho)
    for _ in range(days):
        previous = rho * previous + scale * rng.gauss(0.0, 1.0)
        values.append(previous)
    return values


def _synthetic_panel(rng, scenario, days=28, cells=132):
    """Create zero-mean event panels with scenario-specific day dependence."""
    arms = 11
    if scenario == "ar1_day_null":
        common = _ar1(rng, days, 0.65)
        arm_factors = [_ar1(rng, days, 0.45) for _ in range(arms)]
    else:
        common = [rng.gauss(0.0, 1.0) for _ in range(days)]
        arm_factors = [
            [rng.gauss(0.0, 1.0) for _ in range(days)] for _ in range(arms)
        ]

    daily_sums = [[0.0] * cells for _ in range(days)]
    daily_counts = [[0] * cells for _ in range(days)]
    shared_sparse_days = (
        {day for day in range(days) if rng.random() < 0.35}
        if scenario == "sparse_empty_days" else set(range(days))
    )
    for day in range(days):
        for cell in range(cells):
            arm = cell // (cells // arms)
            if scenario == "sparse_empty_days":
                if day not in shared_sparse_days or rng.random() >= 0.55:
                    continue
            count = 1 + (rng.random() < 0.35) + (rng.random() < 0.10)
            count = int(count)
            if scenario == "shared_crossarm_factor":
                shared_loading, arm_loading, noise = 0.90, 0.20, 0.25
            elif scenario == "sparse_empty_days":
                shared_loading, arm_loading, noise = 0.65, 0.25, 0.70
            else:
                shared_loading, arm_loading, noise = 0.55, 0.35, 0.75
            total = 0.0
            for _ in range(count):
                total += (
                    shared_loading * common[day]
                    + arm_loading * arm_factors[arm][day]
                    + noise * rng.gauss(0.0, 1.0)
                )
            daily_sums[day][cell] = total
            daily_counts[day][cell] = count
    return daily_sums, daily_counts


def _simulate_scenario(scenario, seed):
    rng = random.Random(seed)
    replicates = CONFIG["simulation_replicates_per_scenario"]
    bootstrap_draws = CONFIG["bootstrap_draws_per_replicate"]
    cells = CONFIG["hypothesis_count"]
    days = CONFIG["days_per_fold"]
    block = CONFIG["block_days"]
    rejections = [0] * cells
    valid_replicates_by_cell = [0] * cells
    holm_family_rejections = 0
    invalid_family_replicates = 0
    minimum_events = None
    minimum_p = None
    maximum_p = 0.0
    for _ in range(replicates):
        daily_sums, daily_counts = _synthetic_panel(rng, scenario, days, cells)
        means = event_weighted_means(daily_sums, daily_counts)
        observed_events = [
            sum(daily_counts[day][cell] for day in range(days))
            for cell in range(cells)
        ]
        minimum_events = min(observed_events) if minimum_events is None else min(
            minimum_events, min(observed_events)
        )
        draws_rng = random.Random(rng.getrandbits(64))
        draws = synchronous_block_draws(draws_rng, bootstrap_draws, days, block)
        p_values = synchronous_block_pvalues(daily_sums, daily_counts, draws)
        valid_p_values = [value for value in p_values if value is not None]
        if valid_p_values:
            minimum_p = min(valid_p_values) if minimum_p is None else min(
                minimum_p, min(valid_p_values)
            )
            maximum_p = max(maximum_p, max(valid_p_values))
        for cell, p_value in enumerate(p_values):
            if p_value is None:
                continue
            valid_replicates_by_cell[cell] += 1
            if p_value <= CONFIG["nominal_type_i"]:
                rejections[cell] += 1
        family = holm_step_down(p_values, CONFIG["nominal_type_i"])
        if family["status"] != "VALID_FAMILY":
            invalid_family_replicates += 1
        elif any(family["rejected"]):
            holm_family_rejections += 1

    rates = [
        rejections[cell] / valid_replicates_by_cell[cell]
        if valid_replicates_by_cell[cell] else 0.0
        for cell in range(cells)
    ]
    intervals = [
        wilson_interval(rejections[cell], valid_replicates_by_cell[cell])
        if valid_replicates_by_cell[cell] else [0.0, 1.0]
        for cell in range(cells)
    ]
    sorted_rates = sorted(rates)
    median_rate = (sorted_rates[65] + sorted_rates[66]) / 2
    sorted_lowers = sorted(interval[0] for interval in intervals)
    sorted_uppers = sorted(interval[1] for interval in intervals)
    family_interval = wilson_interval(holm_family_rejections, replicates)
    return {
        "replicates": replicates,
        "bootstrap_draws_per_replicate": bootstrap_draws,
        "minimum_events_in_any_cell": minimum_events,
        "minimum_valid_replicates_per_cell": min(valid_replicates_by_cell),
        "marginal_type_i": {
            "nominal": CONFIG["nominal_type_i"],
            "median_cell_rate": median_rate,
            "cell_rate_range": [min(rates), max(rates)],
            "median_cell_wilson_95_interval": [
                (sorted_lowers[65] + sorted_lowers[66]) / 2,
                (sorted_uppers[65] + sorted_uppers[66]) / 2,
            ],
            "per_cell_wilson_interval_coverage_of_nominal": sum(
                lower <= CONFIG["nominal_type_i"] <= upper
                for lower, upper in intervals
            ) / cells,
            "p_value_range_observed": [minimum_p, maximum_p],
        },
        "holm_132": {
            "status": (
                "NOT_ESTIMABLE_INVALID_FAMILY"
                if invalid_family_replicates else "ESTIMABLE"
            ),
            "invalid_family_replicates": invalid_family_replicates,
            "family_rejection_count": holm_family_rejections,
            "familywise_error_rate": (
                holm_family_rejections / replicates
                if not invalid_family_replicates else None
            ),
            "wilson_95_interval": (
                family_interval if not invalid_family_replicates else None
            ),
            "minimum_attainable_raw_p": 1 / (bootstrap_draws + 1),
            "first_holm_threshold_at_alpha_0_05": (
                CONFIG["nominal_type_i"] / cells
            ),
        },
    }


def _gate_status(scenarios):
    point_ok = all(
        CONFIG["type_i_point_tolerance"][0]
        <= result["marginal_type_i"]["median_cell_rate"]
        <= CONFIG["type_i_point_tolerance"][1]
        for result in scenarios.values()
    )
    if not point_ok:
        return "FAIL"
    if any(
        result["holm_132"]["status"] != "ESTIMABLE"
        for result in scenarios.values()
    ):
        return "INCONCLUSIVE"
    # This modest run cannot resolve the smallest Holm threshold; do not
    # claim familywise calibration from a run whose p-value grid cannot reach it.
    resolution_ok = all(
        result["holm_132"]["minimum_attainable_raw_p"]
        <= result["holm_132"]["first_holm_threshold_at_alpha_0_05"]
        for result in scenarios.values()
    )
    if not resolution_ok:
        return "INCONCLUSIVE"
    interval_ok = all(
        result["holm_132"]["wilson_95_interval"][1]
        <= CONFIG["familywise_upper_wilson_tolerance"]
        for result in scenarios.values()
    )
    return "PASS" if interval_ok else "INCONCLUSIVE"


def _initial_artifact():
    protocol = json.loads(PROTOCOL_PATH.read_text())
    return {
        "artifact_status": "PREDECLARED_NOT_YET_SIMULATED",
        "scope": "Synthetic-only null calibration; not actual validation or future-data readiness.",
        "actual_market_data_used": False,
        "future_data_fetched": False,
        "reserved_validation_readiness": "NOT_READY_NOT_EVALUATED",
        "frozen_protocol": {
            "protocol_id": protocol["protocol_id"],
            "protocol_path": "research/results/walkforward-protocol.json",
            "fold_days": 28,
            "folds": protocol["reserved_forward_folds"]["folds"],
            "primary_hypothesis_count": protocol["dependence_and_multiplicity"][
                "primary_hypothesis_count"
            ],
            "block_plan": protocol["dependence_and_multiplicity"]["primary_dependence_plan"],
            "statistic": "Event-weighted mean net return; empty UTC dates are retained in the 28-day calendar panel.",
            "null": "Per-cell hypothesized net event mean = 0; center each cell's daily event sums by its observed event-weighted mean times that day's event count.",
        },
        "predeclared_simulation_config": CONFIG,
        "predeclared_scenarios": {
            "iid_day_null": "Independent daily global/arm factors and event noise; zero-mean event returns.",
            "shared_crossarm_factor": "Strong shared daily factor across all 132 hypotheses plus arm factor and event noise; zero mean.",
            "ar1_day_null": "Zero-mean AR(1) shared daily factor (rho=0.65) and arm factors (rho=0.45).",
            "sparse_empty_days": "Shared sparse active-date mask (35% daily activity), cell activity conditional on active dates (55%), and zero-mean outcomes; empty calendar days preserved.",
        },
        "predeclared_gate": {
            "individual_calibration": "FAIL if any scenario's median cell type-I point estimate falls outside the predeclared 0.025-0.075 tolerance; otherwise individual results remain diagnostic.",
            "family_calibration": "PASS only if all scenario Holm familywise 95% Wilson upper bounds are <=0.075 and raw p-value resolution reaches the first Holm threshold; FAIL on observed marginal point-rate breach; otherwise INCONCLUSIVE.",
            "scope_guard": "No raw iid event p-values, no reserved-data claims, and no implication of profitability or validation readiness.",
        },
        "results": {},
        "calibration_gate": "NOT_RUN",
    }


def main():
    artifact = _initial_artifact()
    OUTPUT_PATH.write_text(json.dumps(artifact, indent=2, sort_keys=True) + "\n")
    scenario_results = {}
    for index, scenario in enumerate(SCENARIOS):
        scenario_results[scenario] = _simulate_scenario(
            scenario, CONFIG["seed"] + (index + 1) * 100_003
        )
    artifact["artifact_status"] = "COMPLETE_SYNTHETIC_ONLY"
    artifact["results"] = scenario_results
    artifact["calibration_gate"] = _gate_status(scenario_results)
    artifact["interpretation"] = [
        "These are synthetic null experiments under specified illustrative dependence scenarios, not observed market data.",
        "The 28-day fold, non-wrapping 5-day blocks, shared sampled date indices, and empty calendar dates follow the frozen protocol.",
        "Finite p-values use (1 + exceedances) / (B + 1); a zero-event resample is retained and assigned null statistic 0, not omitted.",
        "The run is deliberately modest; its binomial intervals are Monte Carlo uncertainty, not market uncertainty.",
        "A PASS would not validate real-market assumptions, establish independent replications, or authorize claims on reserved folds.",
    ]
    artifact["limitations"] = [
        "Only 28 synthetic dates are available per simulated fold; moving blocks cannot characterize structural breaks or dependence longer than the block.",
        "Synthetic factor structures and sparse activity are illustrative and cannot span all plausible event-generating processes.",
        "Only empirical type-I rates are examined here; this is not a full power or confidence-interval coverage study.",
        "The finite bootstrap p-value grid may be too coarse for 132-test Holm significance thresholds.",
    ]
    artifact["gate_decision_reason"] = (
        "At least one scenario's median marginal type-I point estimate exceeded the predeclared upper tolerance of 0.075."
        if artifact["calibration_gate"] == "FAIL"
        else "See per-scenario family validity, Monte Carlo intervals, and p-value-resolution diagnostics."
    )
    OUTPUT_PATH.write_text(json.dumps(artifact, indent=2, sort_keys=True) + "\n")
    print(json.dumps({
        "output": str(OUTPUT_PATH),
        "scenario_status": artifact["calibration_gate"],
        "results": scenario_results,
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
