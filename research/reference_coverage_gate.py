"""Fail-closed evidence gate; current notices and index feeds imply no history."""

UNIVERSE_REQUIREMENTS = (
    "opening_inventory_2026_09_17_verified",
    "historical_contract_identity_chain_verified",
    "effective_lifecycle_ledger_complete",
    "notice_publication_effective_times_reconciled",
    "historical_coverage_complete",
)
SESSION_REQUIREMENTS = (
    "historical_underlying_identity_mapping_verified",
    "historical_primary_listing_mapping_verified",
    "historical_reference_market_mapping_verified",
    "historical_session_calendar_ledger_verified",
    "historical_halts_and_exceptions_verified",
)


def evaluate_reference_coverage(evidence):
    """Require explicit boolean attestations, never infer them from observations.

    Attestations must be backed by independently reviewed source evidence. This
    gate checks declarations, not the truth or provenance of those declarations.
    """
    universe_missing = [
        key for key in UNIVERSE_REQUIREMENTS if evidence.get(key) is not True
    ]
    session_missing = [
        key for key in SESSION_REQUIREMENTS if evidence.get(key) is not True
    ]
    return {
        "survivorship_corrected_comparison_ready": not universe_missing,
        "historical_stock_session_comparison_ready": not session_missing,
        "universe_missing": universe_missing,
        "session_missing": session_missing,
    }
