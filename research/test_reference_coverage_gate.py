import unittest

from reference_coverage_gate import (
    SESSION_REQUIREMENTS,
    UNIVERSE_REQUIREMENTS,
    evaluate_reference_coverage,
)


class ReferenceCoverageGateTests(unittest.TestCase):
    def test_absence_fails_closed(self):
        result = evaluate_reference_coverage({})
        self.assertFalse(result["survivorship_corrected_comparison_ready"])
        self.assertFalse(result["historical_stock_session_comparison_ready"])

    def test_current_observations_do_not_imply_history(self):
        result = evaluate_reference_coverage({
            "recent_notice_request_successful": True,
            "all_recent_notice_pages_fetched": True,
            "current_instruments_available": True,
            "current_aapl_index_components_available": True,
            "current_reference_exchange_known": True,
        })
        self.assertEqual(result["universe_missing"], list(UNIVERSE_REQUIREMENTS))
        self.assertEqual(result["session_missing"], list(SESSION_REQUIREMENTS))

    def test_truthy_non_booleans_are_not_attestations(self):
        for value in (1, "true", ["source"], None, False):
            with self.subTest(value=value):
                result = evaluate_reference_coverage({
                    key: value
                    for key in UNIVERSE_REQUIREMENTS + SESSION_REQUIREMENTS
                })
                self.assertFalse(result["survivorship_corrected_comparison_ready"])
                self.assertFalse(result["historical_stock_session_comparison_ready"])

    def test_completeness_is_independent_for_each_objective(self):
        result = evaluate_reference_coverage({
            key: True for key in UNIVERSE_REQUIREMENTS
        })
        self.assertTrue(result["survivorship_corrected_comparison_ready"])
        self.assertFalse(result["historical_stock_session_comparison_ready"])

    def test_each_requirement_is_mandatory(self):
        complete = {
            key: True for key in UNIVERSE_REQUIREMENTS + SESSION_REQUIREMENTS
        }
        result = evaluate_reference_coverage(complete)
        self.assertTrue(result["survivorship_corrected_comparison_ready"])
        self.assertTrue(result["historical_stock_session_comparison_ready"])
        for key in complete:
            with self.subTest(key=key):
                result = evaluate_reference_coverage({
                    k: v for k, v in complete.items() if k != key
                })
                readiness = (
                    "survivorship_corrected_comparison_ready"
                    if key in UNIVERSE_REQUIREMENTS
                    else "historical_stock_session_comparison_ready"
                )
                self.assertFalse(result[readiness])


if __name__ == "__main__":
    unittest.main()
