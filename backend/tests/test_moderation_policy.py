from app.core.errors import AppError
from app.core.moderation_policy import enforce_boundary_safe_text, find_moderation_violation


def test_find_moderation_violation_detects_endorsement_phrase() -> None:
    violation = find_moderation_violation('Voters should vote for this candidate in November.')
    assert violation is not None
    assert violation.violation_type == 'endorsement_or_recommendation'
    assert violation.policy_version


def test_enforce_boundary_safe_text_accepts_neutral_language() -> None:
    enforce_boundary_safe_text(
        text='The cited records show partial alignment on the spending claim, with missing denominator context.',
        rejection_field='rationale',
    )


def test_enforce_boundary_safe_text_returns_structured_details() -> None:
    try:
        enforce_boundary_safe_text(text='You should vote for Candidate A.', rejection_field='rationale')
        assert False, 'Expected moderation_policy_violation'
    except AppError as exc:
        assert exc.code == 'moderation_policy_violation'
        assert exc.details['rejection_field'] == 'rationale'
        assert exc.details['matched_rule']
        assert exc.details['policy_version']
        assert exc.details['violation_type'] == 'endorsement_or_recommendation'
