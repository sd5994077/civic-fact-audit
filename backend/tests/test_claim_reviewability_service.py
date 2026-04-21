from app.services.claim_reviewability_service import ClaimReviewabilityService


def test_classify_text_rejects_slogans() -> None:
    result = ClaimReviewabilityService.classify_text("It's time to Start Flipping Tables.")

    assert result['fact_checkable'] is False
    assert result['reviewability_reason'] == 'campaign_rhetoric_or_slogan'


def test_classify_text_accepts_record_checkable_claims() -> None:
    result = ClaimReviewabilityService.classify_text(
        'Cornyn voted against the 2025 spending bill and said it would add $95 billion to the deficit.'
    )

    assert result['fact_checkable'] is True
    assert result['reviewability_reason'] == 'contains_objective_or_record_checkable_signal'


def test_build_extraction_metadata_includes_reviewability_fields() -> None:
    metadata = ClaimReviewabilityService.parse_metadata(
        ClaimReviewabilityService.build_extraction_metadata(
            provider='local',
            text='The unemployment rate fell from 5% to 4% in 2025.',
        )
    )

    assert metadata['provider'] == 'local'
    assert metadata['fact_checkable'] is True
    assert metadata['classifier'] == 'heuristic_v1'
