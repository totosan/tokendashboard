import json
import math
import random
import unittest
from unittest.mock import patch

from research import inference_redesign as model


class InferenceRedesignTests(unittest.TestCase):
    def test_protocol_is_fixed_and_complete(self):
        protocol = json.loads(model.PROTOCOL_PATH.read_text())
        self.assertEqual(protocol, model.prospective_protocol())
        self.assertEqual(len(set(protocol["family"])), 132)
        self.assertEqual(len({name.split("|")[0] for name in protocol["family"]}), 11)

    def test_known_null_and_reflection(self):
        counts = [[1], [2], [0]]
        sums = [[1.0], [-1.0], [0.0]]
        self.assertEqual(model.oracle_pvalues(sums, counts, "iid_day_null"), [.5])
        p = model.oracle_pvalues([[2.0], [3.0]], [[1], [1]], "iid_day_null")[0]
        reflected = model.oracle_pvalues([[-2.0], [-3.0]], [[1], [1]], "iid_day_null")[0]
        self.assertAlmostEqual(p + reflected, 1.0)
        self.assertAlmostEqual(model.normal_survival(1.959963984540054), .025)

    def test_ar_variance_matches_dense_known_covariance(self):
        counts = [2, 0, 1, 3, 0, 2]
        for rho in (0.0, .45, .65):
            dense = sum(
                c * d * rho ** abs(t - u) * (1 - rho ** (2 * (min(t, u) + 1)))
                for t, c in enumerate(counts) for u, d in enumerate(counts)
            )
            self.assertAlmostEqual(model.ar_quadratic(counts, rho), dense)

    def test_day_permutation_only_under_iid(self):
        sums = [[1.0], [4.0], [-2.0], [0.0]]
        counts = [[1], [3], [2], [0]]
        order = [2, 0, 3, 1]
        p = model.oracle_pvalues(sums, counts, "iid_day_null")
        self.assertEqual(p, model.oracle_pvalues(
            [sums[d] for d in order], [counts[d] for d in order], "iid_day_null",
        ))
        self.assertNotEqual(
            model.oracle_pvalues(sums, counts, "ar1_day_null"),
            model.oracle_pvalues([sums[d] for d in order], [counts[d] for d in order], "ar1_day_null"),
        )

    def test_synchronized_family_identical_cells_and_column_permutation(self):
        sums = [[float(day)] * 132 for day in range(3)]
        counts = [[1] * 132 for _ in sums]
        pvalues = model.oracle_pvalues(sums, counts, "shared_crossarm_factor")
        self.assertEqual(len(set(pvalues)), 1)
        sums[0][0] = -4
        pvalues = model.oracle_pvalues(sums, counts, "iid_day_null")
        self.assertEqual(model.oracle_pvalues(
            [list(reversed(row)) for row in sums], counts, "iid_day_null",
        ), list(reversed(pvalues)))

    def test_analytic_tail_resolves_holm_and_finite_floor(self):
        self.assertLess(model.normal_survival(4), .05 / 132)
        self.assertGreater(model.normal_survival(100), 0)
        self.assertLessEqual(model.normal_survival(100), .05 / 132)
        self.assertGreater(1 / (2638 + 1), .05 / 132)
        self.assertLessEqual(1 / (2640 + 1), .05 / 132)
        self.assertFalse(model.prospective_protocol()["single_design"]["finite_resolution"]["simulation_p_values"])

    def test_holm_and_missing_family_refusal(self):
        self.assertEqual(model.holm([.01, .04, .03], expected_size=3)["rejected"], [True, False, False])
        self.assertEqual(model.holm([.0001] * 132)["rejected"], [True] * 132)
        for values in ([.001] * 131, [.001] * 131 + [None], [.001] * 131 + [math.nan]):
            self.assertIsNone(model.holm(values)["rejected"])

    def test_empty_days_not_empty_cell_zero_statistic(self):
        p = model.oracle_pvalues([[0.0], [2.0]], [[0], [1]], "iid_day_null")
        self.assertEqual(p, model.oracle_pvalues([[2.0]], [[1]], "iid_day_null"))
        self.assertEqual(model.oracle_pvalues([[0.0]], [[0]], "iid_day_null"), [None])
        with self.assertRaises(ValueError):
            model.oracle_pvalues([[1.0]], [[0]], "iid_day_null")

    def test_no_pseudoreplication_or_refused_family_fwer(self):
        tally = model.Tally()
        for _ in range(5):
            tally.add([.5] * 132)
        report = tally.report()
        self.assertEqual(report["holm_132"]["complete_independent_families"], 5)
        self.assertEqual(report["marginal_type_i"][0]["independent_replicates"], 5)
        self.assertEqual(model.gate(report), "INCONCLUSIVE")
        tally.add([None] + [.5] * 131)
        report = tally.report()
        self.assertEqual(report["holm_132"]["refused_families"], 1)
        self.assertIsNone(report["holm_132"]["wilson_95"])
        self.assertIsNone(report["holm_132"]["unconditional_rate"])
        self.assertEqual(model.gate(report, assumptions_apply=False), "INCONCLUSIVE_ASSUMPTIONS_VIOLATED")

    def test_known_null_single_day_exact_uniform_transform(self):
        # A one-event synthetic cell has exactly the declared Gaussian variance.
        a, b, noise, _, _ = model.parameters("iid_day_null")
        sd = math.sqrt(a * a + b * b + noise * noise)
        for z, tail in ((0, .5), (1.959963984540054, .025), (-1.959963984540054, .975)):
            self.assertAlmostEqual(model.oracle_pvalues([[sd * z]], [[1]], "iid_day_null")[0], tail)

    def test_seed_determinism_and_whole_panel_shape(self):
        for scenario in model.SCENARIOS:
            left = model.synthetic_panel(random.Random(24), scenario)
            self.assertEqual(left, model.synthetic_panel(random.Random(24), scenario))
            self.assertEqual(len(left[0]), 28)
            self.assertEqual(len(left[0][0]), 132)
            self.assertEqual(model.oracle_pvalues(*left, scenario), model.oracle_pvalues(*left, scenario))

    def test_budget_failure_persists_nonzero_without_simulation(self):
        saved = {}
        with patch.object(model, "check_deadline", side_effect=TimeoutError("test deadline")), \
             patch.object(model, "save", side_effect=lambda path, value: saved.update(json.loads(json.dumps(value)))):
            self.assertEqual(model.run(), 1)
        self.assertEqual(saved["artifact_status"], "RUNTIME_OR_EXECUTION_FAILURE")
        self.assertEqual(saved["calibration_gate"], "INCONCLUSIVE")
        self.assertEqual(saved["partial_scenario"]["report"]["attempted_independent_panels"], 0)


if __name__ == "__main__":
    unittest.main()
