import unittest

from research.inference_calibration import (
    event_weighted_means,
    holm_step_down,
    moving_block_indices,
    null_center_daily_sums,
    synchronous_block_draws,
    synchronous_block_pvalues,
)


class InferenceCalibrationTests(unittest.TestCase):
    def test_exact_null_centering_uses_event_weighted_mean(self):
        sums = [[2.0], [9.0], [0.0]]
        counts = [[2], [3], [0]]
        means, centered = null_center_daily_sums(sums, counts)
        self.assertEqual(means, [11 / 5])
        self.assertAlmostEqual(sum(row[0] for row in centered), 0.0)
        self.assertEqual(centered[2], [0.0])

    def test_empty_days_are_retained_not_conditioned_away(self):
        sums = [[2.0], [0.0], [0.0], [6.0]]
        counts = [[1], [0], [0], [3]]
        self.assertEqual(event_weighted_means(sums, counts), [2.0])
        _, centered = null_center_daily_sums(sums, counts)
        self.assertEqual(len(centered), 4)
        self.assertEqual(centered[1:3], [[0.0], [0.0]])

    def test_same_sampled_days_apply_to_every_cell(self):
        sums = [[1.0, 3.0], [2.0, 4.0], [3.0, 5.0], [4.0, 6.0], [5.0, 7.0]]
        counts = [[1, 1] for _ in sums]
        draws = synchronous_block_draws(
            __import__("random").Random(42), 4, days=5, block_days=5
        )
        self.assertEqual(len(draws[0]), len(draws[1]))
        self.assertEqual(draws, synchronous_block_draws(
            __import__("random").Random(42), 4, days=5, block_days=5
        ))
        p_values = synchronous_block_pvalues(sums, counts, draws)
        self.assertEqual(len(p_values), 2)
        self.assertTrue(all(0 <= value <= 1 for value in p_values))

    def test_nonwrapping_block_sampler_stays_inside_calendar(self):
        draws = moving_block_indices(__import__("random").Random(42), 28, 5)
        self.assertEqual(len(draws), 28)
        self.assertTrue(all(0 <= day < 28 for day in draws))
        for start in range(0, len(draws), 5):
            block = draws[start:start + 5]
            self.assertTrue(all(b == a + 1 for a, b in zip(block, block[1:])))

    def test_known_holm_step_down(self):
        result = holm_step_down([0.01, 0.04, 0.03], alpha=0.05)
        self.assertEqual(result["status"], "VALID_FAMILY")
        self.assertEqual(result["adjusted_p_values"], [0.03, 0.06, 0.06])
        self.assertEqual(result["rejected"], [True, False, False])

    def test_any_missing_cell_invalidates_entire_family(self):
        result = holm_step_down([0.001, None, 0.02])
        self.assertEqual(result, {
            "status": "INVALID_FAMILY",
            "family_size": 3,
            "adjusted_p_values": None,
            "rejected": None,
        })

    def test_invalid_finite_p_value_invalidates_entire_family(self):
        self.assertEqual(holm_step_down([0.01, float("nan")])["status"], "INVALID_FAMILY")

    def test_synchronous_draw_results_are_deterministic(self):
        sums = [[1.0, 2.0], [3.0, 4.0], [2.0, 5.0], [6.0, 3.0], [0.0, 1.0]]
        counts = [[1, 1] for _ in sums]
        draws = [[0, 1, 2, 3, 4], [4, 3, 2, 1, 0], [1, 2, 3, 4, 0]]
        expected = synchronous_block_pvalues(sums, counts, draws)
        self.assertEqual(expected, synchronous_block_pvalues(sums, counts, draws))


if __name__ == "__main__":
    unittest.main()
