import uuid

from app.core.source_recommendation_policy import SourceRecommendationPolicy, SourceRecommendationTemplate
from app.models.enums import SourceClass, SourceOrigin
from app.services.source_recommendation_service import ClaimRecommendationContext, SourceRecommendationService


def _context() -> ClaimRecommendationContext:
    return ClaimRecommendationContext(
        claim_id=uuid.uuid4(),
        claim_text='Cornyn voted with Trump more than 92 percent of the time.',
        issue_tag='voting_record',
        statement_text='statement',
        candidate_name='John Cornyn',
        candidate_party='Republican',
        candidate_office='US Senate',
        candidate_state='TX',
        election_cycle=2026,
        race_stage='primary_runoff',
    )


def test_get_recommendations_filters_existing_social_and_partisan(monkeypatch) -> None:
    ctx = _context()
    policy = SourceRecommendationPolicy(
        version='test-policy-v1',
        default_limit=6,
        templates=(
            SourceRecommendationTemplate(
                template_id='already_attached',
                source_class=SourceClass.primary,
                publisher='Congress.gov',
                url_template='https://www.congress.gov/search',
                rationale='primary record',
                priority=10,
            ),
            SourceRecommendationTemplate(
                template_id='social_blocked',
                source_class=SourceClass.primary,
                publisher='X',
                url_template='https://x.com/search?q={query}',
                rationale='should be blocked',
                priority=20,
            ),
            SourceRecommendationTemplate(
                template_id='partisan_blocked',
                source_class=SourceClass.secondary,
                publisher='Daily Kos',
                url_template='https://www.dailykos.com/search?q={query}',
                rationale='should be blocked',
                priority=30,
            ),
            SourceRecommendationTemplate(
                template_id='secondary_ok',
                source_class=SourceClass.secondary,
                publisher='Reuters',
                url_template='https://www.reuters.com/site-search/?query={query}',
                rationale='secondary corroboration',
                priority=40,
            ),
        ),
    )

    monkeypatch.setattr('app.services.source_recommendation_service.get_source_recommendation_policy', lambda: policy)
    monkeypatch.setattr(
        SourceRecommendationService,
        '_load_claim_context',
        staticmethod(lambda _db, _claim_id: ctx),
    )
    monkeypatch.setattr(
        SourceRecommendationService,
        '_load_source_snapshot',
        staticmethod(lambda _db, _claim_id: ({'https://www.congress.gov/search'}, 0, 1)),
    )

    result = SourceRecommendationService.get_recommendations(object(), claim_id=ctx.claim_id, limit=6)
    assert result['policy_version'] == 'test-policy-v1'
    assert result['verification_primary_count'] == 0
    assert result['verification_secondary_count'] == 1
    assert result['missing_source_classes'] == [SourceClass.primary]
    recommendations = result['recommendations']
    assert len(recommendations) == 1
    assert recommendations[0]['template_id'] == 'secondary_ok'
    assert recommendations[0]['source_origin'] == SourceOrigin.verification
    assert recommendations[0]['rank'] == 1


def test_get_recommendations_respects_scope_priority_and_limit(monkeypatch) -> None:
    ctx = _context()
    policy = SourceRecommendationPolicy(
        version='test-policy-v1',
        default_limit=6,
        templates=(
            SourceRecommendationTemplate(
                template_id='wrong_state',
                source_class=SourceClass.primary,
                publisher='Congress.gov',
                url_template='https://www.congress.gov/search?q={query}',
                rationale='wrong state scope',
                priority=5,
                state='CA',
            ),
            SourceRecommendationTemplate(
                template_id='best_match',
                source_class=SourceClass.primary,
                publisher='Congress.gov',
                url_template='https://www.congress.gov/search?q={query}',
                rationale='best match',
                priority=10,
                state='TX',
                office='us senate',
                issue_tags=('voting_record',),
            ),
            SourceRecommendationTemplate(
                template_id='second_choice',
                source_class=SourceClass.secondary,
                publisher='Reuters',
                url_template='https://www.reuters.com/site-search/?query={query}',
                rationale='second choice',
                priority=20,
            ),
        ),
    )
    monkeypatch.setattr('app.services.source_recommendation_service.get_source_recommendation_policy', lambda: policy)
    monkeypatch.setattr(
        SourceRecommendationService,
        '_load_claim_context',
        staticmethod(lambda _db, _claim_id: ctx),
    )
    monkeypatch.setattr(
        SourceRecommendationService,
        '_load_source_snapshot',
        staticmethod(lambda _db, _claim_id: (set(), 0, 0)),
    )

    result = SourceRecommendationService.get_recommendations(object(), claim_id=ctx.claim_id, limit=1)
    recommendations = result['recommendations']
    assert len(recommendations) == 1
    assert recommendations[0]['template_id'] == 'best_match'
    assert recommendations[0]['rank'] == 1
    assert result['missing_source_classes'] == [SourceClass.primary, SourceClass.secondary]


def test_get_recommendations_skips_malformed_url_templates(monkeypatch) -> None:
    ctx = _context()
    policy = SourceRecommendationPolicy(
        version='test-policy-v1',
        default_limit=6,
        templates=(
            SourceRecommendationTemplate(
                template_id='bad_template',
                source_class=SourceClass.primary,
                publisher='Congress.gov',
                url_template='https://www.congress.gov/search?q={unknown_placeholder}',
                rationale='invalid placeholder',
                priority=10,
            ),
            SourceRecommendationTemplate(
                template_id='good_template',
                source_class=SourceClass.secondary,
                publisher='Reuters',
                url_template='https://www.reuters.com/site-search/?query={query}',
                rationale='valid template',
                priority=20,
            ),
        ),
    )
    monkeypatch.setattr('app.services.source_recommendation_service.get_source_recommendation_policy', lambda: policy)
    monkeypatch.setattr(
        SourceRecommendationService,
        '_load_claim_context',
        staticmethod(lambda _db, _claim_id: ctx),
    )
    monkeypatch.setattr(
        SourceRecommendationService,
        '_load_source_snapshot',
        staticmethod(lambda _db, _claim_id: (set(), 0, 0)),
    )

    result = SourceRecommendationService.get_recommendations(object(), claim_id=ctx.claim_id, limit=6)
    recommendations = result['recommendations']
    assert len(recommendations) == 1
    assert recommendations[0]['template_id'] == 'good_template'
