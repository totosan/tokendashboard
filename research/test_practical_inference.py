import json
import math
import random
import unittest
from unittest.mock import patch

from research import practical_inference as inference


class PracticalInferenceTests(unittest.TestCase):
    def test_protocol_freezes_exact_full_family_and_design(self):
        protocol = json.loads(inference.PROTOCOL_PATH.read_text())
        self.assertEqual(protocol, inference.prospective_protocol())
        self.assertEqual(len(protocol["family"]), 132)
        self.assertEqual(len(set(protocol["family"])), 132)
        self.assertEqual(protocol["config"]["hypotheses"], 132)
        self.assertEqual(protocol["config"]["replicates_per_scenario"], 1000)
        self.assertEqual(
            protocol["config"]["required_independent_panels_per_scenario"], 2000
        )
        self.assertEqual(len(protocol["synthetic_cases"]), 4)

    def test_panel_validation_rejects_malformed_and_nonfinite_data(self):
        sums = [[0.0] * 132 for _ in range(28)]
        counts = [[0] * 132 for _ in range(28)]
        inference.validate_panel(sums, counts)
        with self.assertRaises(ValueError):
            inference.validate_panel(sums[:-1], counts[:-1])
        invalid = [row[:] for row in sums]
        invalid[0][0] = math.nan
        with self.assertRaises(ValueError):
            inference.validate_panel(invalid, counts)
        invalid_counts = [row[:] for row in counts]
        invalid_counts[0][0] = -1
        with self.assertRaises(ValueError):
            inference.validate_panel(sums, invalid_counts)
        invalid[0][0] = 1.0
        with self.assertRaises(ValueError):
            inference.validate_panel(invalid, counts)

    def test_zero_event_or_sparse_cell_has_no_pvalue_and_refuses_full_family(self):
        sums = [[0.0] * 132 for _ in range(28)]
        counts = [[1] * 132 for _ in range(28)]
        for day in range(19):
            counts[day][0] = 0
        for day in range(28):
            counts[day][1] = 0
        pvalues = inference.cell_pvalues(sums, counts)
        self.assertEqual(pvalues[0], None)
        self.assertEqual(pvalues[1], None)
        self.assertEqual(len(pvalues), 132)
        self.assertEqual(inference.holm(pvalues)["status"], "REFUSED_INCOMPLETE_132_FAMILY")

    def test_unknown_covariance_student_t_and_holm_adjustment(self):
        self.assertAlmostEqual(inference.student_t_survival(0), 0.5)
        self.assertGreater(inference.student_t_survival(-2), 0.5)
        self.assertLess(inference.student_t_survival(5), 0.05 / 132)
        result = inference.holm([0.0001, 0.01, 0.02] + [1.0] * 129)
        self.assertEqual(result["status"], "COMPLETE_132_FAMILY")
        self.assertEqual(result["rejected"][:3], [True, False, False])
        self.assertFalse(any(result["rejected"][3:]))
        self.assertEqual(
            inference.holm([0.001] * 131 + [None])["status"],
            "REFUSED_INCOMPLETE_132_FAMILY",
        )

    def test_gate_requires_declared_precision_field(self):
        ci = [0.02, 0.06]
        report = {
            "independent_panels_attempted": 1000,
            "complete_132_family_panels": 1000,
            "refused_family_panels": 0,
            "familywise_wilson_95": ci,
            "marginal_type_i_by_cell": [
                {"wilson_95_pointwise": ci} for _ in range(132)
            ],
        }
        self.assertEqual(inference._gate(report), "INCONCLUSIVE")

    def test_synthetic_dependence_and_determinism(self):
        shared_a = inference.synthetic_panel(
            random.Random(inference._scenario_seed("shared_cross_cell_heteroskedastic")),
            "shared_cross_cell_heteroskedastic",
        )
        shared_b = inference.synthetic_panel(
            random.Random(inference._scenario_seed("shared_cross_cell_heteroskedastic")),
            "shared_cross_cell_heteroskedastic",
        )
        self.assertEqual(shared_a, shared_b)
        sums, counts = shared_a
        self.assertEqual((len(sums), len(sums[0])), (28, 132))
        self.assertEqual((len(counts), len(counts[0])), (28, 132))
        observed_counts = [value for row in counts for value in row]
        self.assertTrue(set(observed_counts) <= {2, 3})
        self.assertGreater(
            sum(value == 3 for value in observed_counts) / len(observed_counts),
            0.45,
        )
        self.assertLess(
            sum(value == 3 for value in observed_counts) / len(observed_counts),
            0.55,
        )
        col_a = [sums[d][0] / counts[d][0] for d in range(28)]
        col_b = [sums[d][24] / counts[d][24] for d in range(28)]
        mean_a, mean_b = sum(col_a) / 28, sum(col_b) / 28
        covariance = sum(
            (col_a[d] - mean_a) * (col_b[d] - mean_b) for d in range(28)
        )
        self.assertGreater(covariance, 0)

    def test_declared_count_distribution_in_every_scenario(self):
        for scenario in inference.SCENARIOS:
            with self.subTest(scenario=scenario):
                _, counts = inference.synthetic_panel(
                    random.Random(inference._scenario_seed(scenario)), scenario
                )
                active = [value for row in counts for value in row if value]
                self.assertTrue(active)
                self.assertTrue(set(active) <= {2, 3})
                fraction_three = sum(value == 3 for value in active) / len(active)
                self.assertGreater(fraction_three, 0.45)
                self.assertLess(fraction_three, 0.55)

    def test_sparse_empty_case_refuses_every_family_without_zero_fill(self):
        sums, counts = inference.synthetic_panel(
            random.Random(inference._scenario_seed("sparse_and_empty_cells")),
            "sparse_and_empty_cells",
        )
        self.assertEqual(inference.holm(inference.cell_pvalues(sums, counts))["rejected"], None)
        self.assertTrue(any(sum(row[cell] for row in counts) == 0 for cell in range(132)))
        self.assertTrue(all(
            sums[day][cell] == 0
            for day in range(28) for cell in range(132)
            if counts[day][cell] == 0
        ))

    def test_runtime_failure_saves_partial_status_and_returns_nonzero(self):
        saved = {}
        with patch.object(inference, "cell_pvalues", side_effect=RuntimeError("fixture failure")), \
             patch.object(inference, "write_json", side_effect=lambda path, value: saved.update(
                 json.loads(json.dumps(value))
             )):
            self.assertEqual(inference.run(), 1)
        self.assertEqual(saved["artifact_status"], "RUNTIME_OR_EXECUTION_FAILURE")
        self.assertEqual(saved["calibration_gate"], "INCONCLUSIVE")
        self.assertEqual(saved["partial_scenario"]["report"]["independent_panels_attempted"], 0)

    def test_execution_failure_preserves_prior_fail_gate(self):
        saved = {}
        initial = {
            "artifact_status": "RUNNING",
            "calibration_gate": "FAIL",
            "results": {"completed": {"status": "FAIL"}},
        }
        with patch.object(inference, "_initial_artifact", return_value=initial), \
             patch.object(inference, "synthetic_panel", side_effect=RuntimeError("fixture failure")), \
             patch.object(inference, "write_json", side_effect=lambda path, value: saved.update(
                 json.loads(json.dumps(value))
             )):
            self.assertEqual(inference.run(), 1)
        self.assertEqual(saved["artifact_status"], "RUNTIME_OR_EXECUTION_FAILURE")
        self.assertEqual(saved["execution_status"], "RUNTIME_OR_EXECUTION_FAILURE")
        self.assertEqual(saved["calibration_gate"], "FAIL")

    def test_final_artifact_write_failure_preserves_prior_fail_gate(self):
        class CapturePath:
            written = None

            def write_text(self, text):
                self.written = text

            def __str__(self):
                return "captured-output"

        output = CapturePath()
        initial = {
            "artifact_status": "RUNNING",
            "calibration_gate": "FAIL",
            "results": {"completed": {"status": "FAIL"}},
        }
        with patch.object(inference, "_initial_artifact", return_value=initial), \
             patch.object(inference, "synthetic_panel", side_effect=RuntimeError("fixture failure")), \
             patch.object(inference, "OUTPUT_PATH", output), \
             patch.object(inference, "write_json", side_effect=[None, RuntimeError("write failure")]):
            self.assertEqual(inference.run(), 1)
        saved = json.loads(output.written)
        self.assertEqual(saved["artifact_status"], "RUNTIME_OR_EXECUTION_FAILURE")
        self.assertEqual(saved["execution_status"], "RUNTIME_OR_EXECUTION_FAILURE")
        self.assertEqual(saved["calibration_gate"], "FAIL")


if __name__ == "__main__":
    unittest.main()
