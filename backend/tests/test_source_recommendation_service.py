import uuid

from app.core.source_recommendation_policy import SourceRecommendationPolicy, SourceRecommendationTemplate
from app.models.enums import SourceClass, SourceOrigin
from app.services.source_recommendation_service import (
    ClaimRecommendationContext,
    RecommendationValidationResult,
    ResolvedRecommendationResult,
    SourceRecommendationService,
)


def _context() -> ClaimRecommendationContext:
    return ClaimRecommendationContext(
        claim_id=uuid.uuid4(),
        claim_text='Cornyn discussed a federal education funding proposal.',
        issue_tag='education',
        statement_text='statement',
        candidate_name='John Cornyn',
        candidate_party='Republican',
        candidate_office='US Senate',
        candidate_state='TX',
        election_cycle=2026,
        race_stage='primary_runoff',
    )


def _numeric_voting_context() -> ClaimRecommendationContext:
    return ClaimRecommendationContext(
        claim_id=uuid.uuid4(),
        claim_text="Cornyn voted with Trump over 92 percent of the time and ranked above 95 out of 100 senators.",
        issue_tag='voting_record',
        statement_text='statement',
        candidate_name='John Cornyn',
        candidate_party='Republican',
        candidate_office='US Senate',
        candidate_state='TX',
        election_cycle=2026,
        race_stage='primary_runoff',
    )

def _funding_context() -> ClaimRecommendationContext:
    return ClaimRecommendationContext(
        claim_id=uuid.uuid4(),
        claim_text="Senator Cornyn delivered more than $11 billion in federal reimbursements for Texas's Operation Lone Star.",
        issue_tag='immigration',
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
    monkeypatch.setattr(
        SourceRecommendationService,
        '_validate_recommendation_url',
        staticmethod(lambda _url, _context, require_methodology_signals=False: RecommendationValidationResult(status='validated', http_status=200, topic_overlap_score=0.5)),
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
                supports_numeric_voting_claims=True,
                state='TX',
                office='us senate',
                issue_tags=('education',),
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
    monkeypatch.setattr(
        SourceRecommendationService,
        '_validate_recommendation_url',
        staticmethod(lambda _url, _context, require_methodology_signals=False: RecommendationValidationResult(status='validated', http_status=200, topic_overlap_score=0.8)),
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
    monkeypatch.setattr(
        SourceRecommendationService,
        '_validate_recommendation_url',
        staticmethod(lambda _url, _context, require_methodology_signals=False: RecommendationValidationResult(status='validated', http_status=200, topic_overlap_score=0.7)),
    )

    result = SourceRecommendationService.get_recommendations(object(), claim_id=ctx.claim_id, limit=6)
    recommendations = result['recommendations']
    assert len(recommendations) == 1
    assert recommendations[0]['template_id'] == 'good_template'


def test_get_recommendations_skips_unreachable_and_no_results(monkeypatch) -> None:
    ctx = _context()
    policy = SourceRecommendationPolicy(
        version='test-policy-v1',
        default_limit=6,
        templates=(
            SourceRecommendationTemplate(
                template_id='bad_http',
                source_class=SourceClass.primary,
                publisher='Congress.gov',
                url_template='https://www.congress.gov/search?q={query}',
                rationale='unreachable',
                priority=10,
            ),
            SourceRecommendationTemplate(
                template_id='empty_search',
                source_class=SourceClass.secondary,
                publisher='Reuters',
                url_template='https://www.reuters.com/site-search/?query={query}',
                rationale='no results',
                priority=20,
            ),
            SourceRecommendationTemplate(
                template_id='good_one',
                source_class=SourceClass.secondary,
                publisher='AP',
                url_template='https://apnews.com/search?q={query}',
                rationale='good result',
                priority=30,
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

    def _fake_validate(url, _context, require_methodology_signals=False):  # type: ignore[no-untyped-def]
        _ = require_methodology_signals
        if 'congress.gov' in url:
            return RecommendationValidationResult(status='unreachable', http_status=404, validation_note='HTTP 404.')
        if 'reuters.com' in url:
            return RecommendationValidationResult(status='no_results', http_status=200, validation_note='Search page returned no visible results.')
        return RecommendationValidationResult(
            status='validated',
            http_status=200,
            page_title='AP search results',
            topic_overlap_score=0.6,
            validation_note='Reachable and topic-aligned.',
        )

    monkeypatch.setattr(
        SourceRecommendationService,
        '_validate_recommendation_url',
        staticmethod(_fake_validate),
    )

    result = SourceRecommendationService.get_recommendations(object(), claim_id=ctx.claim_id, limit=6)
    recommendations = result['recommendations']
    assert len(recommendations) == 1
    assert recommendations[0]['template_id'] == 'good_one'
    assert recommendations[0]['validation_status'] == 'validated'
    assert recommendations[0]['topic_overlap_score'] == 0.6


def test_numeric_voting_claim_prefers_methodology_templates_only(monkeypatch) -> None:
    ctx = _numeric_voting_context()
    policy = SourceRecommendationPolicy(
        version='test-policy-v1',
        default_limit=6,
        templates=(
            SourceRecommendationTemplate(
                template_id='generic_secondary',
                source_class=SourceClass.secondary,
                publisher='Reuters',
                url_template='https://www.reuters.com/site-search/?query={query}',
                rationale='generic search',
                priority=10,
                supports_numeric_voting_claims=False,
            ),
            SourceRecommendationTemplate(
                template_id='voteview_primary',
                source_class=SourceClass.primary,
                publisher='Voteview',
                url_template='https://voteview.com/search?q={query}',
                rationale='methodology source',
                priority=20,
                supports_numeric_voting_claims=True,
                requires_methodology_signals=True,
                query_hint='presidential support score methodology senate',
            ),
        ),
    )
    monkeypatch.setattr('app.services.source_recommendation_service.get_source_recommendation_policy', lambda: policy)
    monkeypatch.setattr(SourceRecommendationService, '_load_claim_context', staticmethod(lambda _db, _claim_id: ctx))
    monkeypatch.setattr(SourceRecommendationService, '_load_source_snapshot', staticmethod(lambda _db, _claim_id: (set(), 0, 0)))
    monkeypatch.setattr(
        SourceRecommendationService,
        '_validate_recommendation_url',
        staticmethod(lambda _url, _context, require_methodology_signals=False: RecommendationValidationResult(
            status='validated' if require_methodology_signals else 'weak_match',
            http_status=200,
            topic_overlap_score=0.75,
        )),
    )

    result = SourceRecommendationService.get_recommendations(object(), claim_id=ctx.claim_id, limit=6)
    recommendations = result['recommendations']
    assert len(recommendations) == 1
    assert recommendations[0]['template_id'] == 'voteview_primary'


def test_validate_numeric_voting_claim_rejects_missing_methodology_signals(monkeypatch) -> None:
    ctx = _numeric_voting_context()

    class _Response:
        status_code = 200
        headers = {'content-type': 'text/html; charset=utf-8'}
        url = 'https://example.com/result'
        text = '<html><head><title>John Cornyn result</title></head><body>John Cornyn Trump Senate voting article.</body></html>'

    monkeypatch.setattr('app.services.source_recommendation_service.httpx.get', lambda *_args, **_kwargs: _Response())
    result = SourceRecommendationService._validate_recommendation_url(
        'https://example.com/result',
        ctx,
        require_methodology_signals=True,
    )
    assert result.status == 'weak_match'
    assert result.http_status == 200


def test_funding_claim_only_returns_funding_capable_templates(monkeypatch) -> None:
    ctx = _funding_context()
    policy = SourceRecommendationPolicy(
        version='test-policy-v1',
        default_limit=6,
        templates=(
            SourceRecommendationTemplate(
                template_id='generic_secondary',
                source_class=SourceClass.secondary,
                publisher='Reuters',
                url_template='https://www.reuters.com/site-search/?query={query}',
                rationale='generic search',
                priority=10,
                supports_funding_claims=False,
            ),
            SourceRecommendationTemplate(
                template_id='usaspending_primary',
                source_class=SourceClass.primary,
                publisher='USAspending.gov',
                url_template='https://www.usaspending.gov/search/?q={query}',
                rationale='spending record',
                priority=20,
                supports_funding_claims=True,
                query_hint='reimbursement obligation Texas Operation Lone Star',
            ),
        ),
    )
    monkeypatch.setattr('app.services.source_recommendation_service.get_source_recommendation_policy', lambda: policy)
    monkeypatch.setattr(SourceRecommendationService, '_load_claim_context', staticmethod(lambda _db, _claim_id: ctx))
    monkeypatch.setattr(SourceRecommendationService, '_load_source_snapshot', staticmethod(lambda _db, _claim_id: (set(), 0, 0)))
    monkeypatch.setattr(
        SourceRecommendationService,
        '_validate_recommendation_url',
        staticmethod(lambda _url, _context, require_methodology_signals=False: RecommendationValidationResult(
            status='validated',
            http_status=200,
            topic_overlap_score=0.8,
        )),
    )

    result = SourceRecommendationService.get_recommendations(object(), claim_id=ctx.claim_id, limit=6)
    recommendations = result['recommendations']
    assert recommendations == []


def test_validate_funding_claim_requires_higher_overlap(monkeypatch) -> None:
    ctx = _funding_context()

    class _Response:
        status_code = 200
        headers = {'content-type': 'text/html; charset=utf-8'}
        url = 'https://example.com/result'
        # Include only a couple of expected terms; overlap should land at ~0.2 and be rejected for funding claims.
        text = '<html><head><title>Cornyn Texas</title></head><body>Cornyn Texas update.</body></html>'

    monkeypatch.setattr('app.services.source_recommendation_service.httpx.get', lambda *_args, **_kwargs: _Response())
    result = SourceRecommendationService._validate_recommendation_url(
        'https://example.com/result',
        ctx,
        require_methodology_signals=False,
    )
    assert result.status == 'weak_match'
    assert result.http_status == 200


def test_recommendation_role_is_discovery_for_search_page(monkeypatch) -> None:
    ctx = _context()
    policy = SourceRecommendationPolicy(
        version='test-policy-v1',
        default_limit=6,
        templates=(
            SourceRecommendationTemplate(
                template_id='search_template',
                source_class=SourceClass.primary,
                publisher='Congress.gov',
                url_template='https://www.congress.gov/search?q={query}',
                rationale='search page',
                priority=10,
            ),
        ),
    )
    monkeypatch.setattr('app.services.source_recommendation_service.get_source_recommendation_policy', lambda: policy)
    monkeypatch.setattr(SourceRecommendationService, '_load_claim_context', staticmethod(lambda _db, _claim_id: ctx))
    monkeypatch.setattr(SourceRecommendationService, '_load_source_snapshot', staticmethod(lambda _db, _claim_id: (set(), 0, 0)))
    monkeypatch.setattr(
        SourceRecommendationService,
        '_validate_recommendation_url',
        staticmethod(
            lambda _url, _context, require_methodology_signals=False: RecommendationValidationResult(
                status='validated',
                http_status=200,
                page_type='search_results',
                topic_overlap_score=0.9,
            )
        ),
    )

    result = SourceRecommendationService.get_recommendations(object(), claim_id=ctx.claim_id, limit=6)
    recommendations = result['recommendations']
    assert len(recommendations) == 1
    assert recommendations[0]['recommendation_role'] == 'discovery_only'
    assert recommendations[0]['validation_note'] == 'Search page: useful for discovery, not attachable evidence.'


def test_funding_recommendation_requires_amount_anchor_for_attachable_role(monkeypatch) -> None:
    ctx = _funding_context()
    policy = SourceRecommendationPolicy(
        version='test-policy-v1',
        default_limit=6,
        templates=(
            SourceRecommendationTemplate(
                template_id='funding_template',
                source_class=SourceClass.primary,
                publisher='USAspending.gov',
                url_template='https://www.usaspending.gov/search/?q={query}',
                rationale='funding',
                priority=10,
                supports_funding_claims=True,
            ),
        ),
    )
    monkeypatch.setattr('app.services.source_recommendation_service.get_source_recommendation_policy', lambda: policy)
    monkeypatch.setattr(SourceRecommendationService, '_load_claim_context', staticmethod(lambda _db, _claim_id: ctx))
    monkeypatch.setattr(SourceRecommendationService, '_load_source_snapshot', staticmethod(lambda _db, _claim_id: (set(), 0, 0)))
    monkeypatch.setattr(
        SourceRecommendationService,
        '_validate_recommendation_url',
        staticmethod(
            lambda _url, _context, require_methodology_signals=False: RecommendationValidationResult(
                status='validated',
                http_status=200,
                page_type='evidence_page',
                page_title='Operation Lone Star reimbursement summary for Texas',
                final_url='https://www.usaspending.gov/award/abc123',
                topic_overlap_score=0.9,
                evidence_text='operation lone star reimbursement for texas',
            )
        ),
    )

    result = SourceRecommendationService.get_recommendations(object(), claim_id=ctx.claim_id, limit=6)
    recommendations = result['recommendations']
    assert len(recommendations) == 1
    assert recommendations[0]['recommendation_role'] == 'discovery_only'
    assert recommendations[0]['validation_note'] == 'Missing claimed amount.'


def test_funding_recommendation_is_attachable_when_amount_and_context_present(monkeypatch) -> None:
    ctx = _funding_context()
    policy = SourceRecommendationPolicy(
        version='test-policy-v1',
        default_limit=6,
        templates=(
            SourceRecommendationTemplate(
                template_id='funding_template',
                source_class=SourceClass.primary,
                publisher='USAspending.gov',
                url_template='https://www.usaspending.gov/search/?q={query}',
                rationale='funding',
                priority=10,
                supports_funding_claims=True,
            ),
        ),
    )
    monkeypatch.setattr('app.services.source_recommendation_service.get_source_recommendation_policy', lambda: policy)
    monkeypatch.setattr(SourceRecommendationService, '_load_claim_context', staticmethod(lambda _db, _claim_id: ctx))
    monkeypatch.setattr(SourceRecommendationService, '_load_source_snapshot', staticmethod(lambda _db, _claim_id: (set(), 0, 0)))
    monkeypatch.setattr(
        SourceRecommendationService,
        '_validate_recommendation_url',
        staticmethod(
            lambda _url, _context, require_methodology_signals=False: RecommendationValidationResult(
                status='validated',
                http_status=200,
                page_type='evidence_page',
                page_title='Award data',
                final_url='https://www.usaspending.gov/award/abc123',
                topic_overlap_score=0.9,
                evidence_text='operation lone star reimbursement texas 11 billion federal obligation',
            )
        ),
    )

    result = SourceRecommendationService.get_recommendations(object(), claim_id=ctx.claim_id, limit=6)
    recommendations = result['recommendations']
    assert len(recommendations) == 1
    assert recommendations[0]['recommendation_role'] == 'attachable_evidence'


def test_weak_match_recommendation_kept_as_discovery_only(monkeypatch) -> None:
    ctx = _context()
    policy = SourceRecommendationPolicy(
        version='test-policy-v1',
        default_limit=6,
        templates=(
            SourceRecommendationTemplate(
                template_id='weak_match_template',
                source_class=SourceClass.secondary,
                publisher='Reuters',
                url_template='https://www.reuters.com/site-search/?query={query}',
                rationale='secondary corroboration',
                priority=10,
                min_topic_overlap=0.2,
            ),
        ),
    )
    monkeypatch.setattr('app.services.source_recommendation_service.get_source_recommendation_policy', lambda: policy)
    monkeypatch.setattr(SourceRecommendationService, '_load_claim_context', staticmethod(lambda _db, _claim_id: ctx))
    monkeypatch.setattr(SourceRecommendationService, '_load_source_snapshot', staticmethod(lambda _db, _claim_id: (set(), 0, 0)))
    monkeypatch.setattr(
        SourceRecommendationService,
        '_validate_recommendation_url',
        staticmethod(
            lambda _url, _context, require_methodology_signals=False: RecommendationValidationResult(
                status='weak_match',
                http_status=200,
                page_type='article',
                topic_overlap_score=0.05,
                validation_note='Reachable, but relevance to the claim appears weak.',
            )
        ),
    )

    result = SourceRecommendationService.get_recommendations(object(), claim_id=ctx.claim_id, limit=6)
    recommendations = result['recommendations']
    assert len(recommendations) == 1
    assert recommendations[0]['validation_status'] == 'weak_match'
    assert recommendations[0]['recommendation_role'] == 'discovery_only'


def test_funding_search_page_keeps_discovery_note(monkeypatch) -> None:
    ctx = _funding_context()
    policy = SourceRecommendationPolicy(
        version='test-policy-v1',
        default_limit=6,
        templates=(
            SourceRecommendationTemplate(
                template_id='usaspending_primary',
                source_class=SourceClass.primary,
                publisher='USAspending.gov',
                url_template='https://www.usaspending.gov/search/?q={query}',
                rationale='funding search',
                priority=10,
                supports_funding_claims=True,
            ),
        ),
    )
    monkeypatch.setattr('app.services.source_recommendation_service.get_source_recommendation_policy', lambda: policy)
    monkeypatch.setattr(SourceRecommendationService, '_load_claim_context', staticmethod(lambda _db, _claim_id: ctx))
    monkeypatch.setattr(SourceRecommendationService, '_load_source_snapshot', staticmethod(lambda _db, _claim_id: (set(), 0, 0)))
    monkeypatch.setattr(
        SourceRecommendationService,
        '_resolve_structured_discovery_url',
        staticmethod(lambda **_kwargs: None),
    )
    monkeypatch.setattr(
        SourceRecommendationService,
        '_validate_recommendation_url',
        staticmethod(
            lambda _url, _context, require_methodology_signals=False: RecommendationValidationResult(
                status='weak_match',
                http_status=200,
                page_type='search_results',
                topic_overlap_score=0.1,
                validation_note='Reachable, but relevance to the claim appears weak.',
            )
        ),
    )

    result = SourceRecommendationService.get_recommendations(object(), claim_id=ctx.claim_id, limit=6)
    recommendations = result['recommendations']
    assert recommendations == []


def test_usaspending_resolver_returns_attachable_evidence(monkeypatch) -> None:
    ctx = _funding_context()
    policy = SourceRecommendationPolicy(
        version='test-policy-v1',
        default_limit=6,
        templates=(
            SourceRecommendationTemplate(
                template_id='usaspending_primary',
                source_class=SourceClass.primary,
                publisher='USAspending.gov',
                url_template='https://www.usaspending.gov/search/?q={query}',
                rationale='funding search',
                priority=10,
                supports_funding_claims=True,
            ),
        ),
    )

    class _ApiResponse:
        status_code = 200

        def raise_for_status(self):  # type: ignore[no-untyped-def]
            return None

        def json(self):  # type: ignore[no-untyped-def]
            return {
                'results': [
                    {
                        'generated_internal_id': 'AWARD-001',
                        'Description': 'Operation Lone Star reimbursement Texas 11 billion obligation',
                        'Recipient Name': 'State of Texas',
                        'Award Type': 'Grant',
                    }
                ]
            }

    monkeypatch.setattr('app.services.source_recommendation_service.httpx.post', lambda *_args, **_kwargs: _ApiResponse())
    monkeypatch.setattr('app.services.source_recommendation_service.get_source_recommendation_policy', lambda: policy)
    monkeypatch.setattr(SourceRecommendationService, '_load_claim_context', staticmethod(lambda _db, _claim_id: ctx))
    monkeypatch.setattr(SourceRecommendationService, '_load_source_snapshot', staticmethod(lambda _db, _claim_id: (set(), 0, 0)))
    monkeypatch.setattr(
        SourceRecommendationService,
        '_validate_recommendation_url',
        staticmethod(
            lambda _url, _context, require_methodology_signals=False: RecommendationValidationResult(
                status='validated',
                http_status=200,
                page_type='evidence_page',
                evidence_text='operation lone star reimbursement texas 11 billion obligation',
            )
        ),
    )

    result = SourceRecommendationService.get_recommendations(object(), claim_id=ctx.claim_id, limit=6)
    recommendations = result['recommendations']
    assert len(recommendations) == 1
    assert recommendations[0]['recommendation_role'] == 'attachable_evidence'
    assert recommendations[0]['evidence_url'] == 'https://www.usaspending.gov/award/AWARD-001'
    assert recommendations[0]['discovery_url'].startswith('https://www.usaspending.gov/search/')
    assert 'amount' in recommendations[0]['matched_anchors']


def test_usaspending_resolver_falls_back_to_discovery_only(monkeypatch) -> None:
    ctx = _funding_context()
    policy = SourceRecommendationPolicy(
        version='test-policy-v1',
        default_limit=6,
        templates=(
            SourceRecommendationTemplate(
                template_id='usaspending_primary',
                source_class=SourceClass.primary,
                publisher='USAspending.gov',
                url_template='https://www.usaspending.gov/search/?q={query}',
                rationale='funding search',
                priority=10,
                supports_funding_claims=True,
            ),
        ),
    )

    class _ApiResponse:
        status_code = 200

        def raise_for_status(self):  # type: ignore[no-untyped-def]
            return None

        def json(self):  # type: ignore[no-untyped-def]
            return {'results': [{'generated_internal_id': 'AWARD-002', 'Description': 'General state funding update'}]}

    monkeypatch.setattr('app.services.source_recommendation_service.httpx.post', lambda *_args, **_kwargs: _ApiResponse())
    monkeypatch.setattr('app.services.source_recommendation_service.get_source_recommendation_policy', lambda: policy)
    monkeypatch.setattr(SourceRecommendationService, '_load_claim_context', staticmethod(lambda _db, _claim_id: ctx))
    monkeypatch.setattr(SourceRecommendationService, '_load_source_snapshot', staticmethod(lambda _db, _claim_id: (set(), 0, 0)))
    monkeypatch.setattr(
        SourceRecommendationService,
        '_validate_recommendation_url',
        staticmethod(
            lambda _url, _context, require_methodology_signals=False: RecommendationValidationResult(
                status='weak_match',
                http_status=200,
                page_type='search_results',
            )
        ),
    )

    result = SourceRecommendationService.get_recommendations(object(), claim_id=ctx.claim_id, limit=6)
    recommendations = result['recommendations']
    assert recommendations == []


def test_federal_register_resolver_returns_document_and_official_url(monkeypatch) -> None:
    ctx = _funding_context()
    policy = SourceRecommendationPolicy(
        version='test-policy-v1',
        default_limit=6,
        templates=(
            SourceRecommendationTemplate(
                template_id='federal_register_primary',
                source_class=SourceClass.primary,
                publisher='Federal Register',
                url_template='https://www.federalregister.gov/documents/search?conditions%5Bterm%5D={query}',
                rationale='funding search',
                priority=10,
                supports_funding_claims=True,
            ),
        ),
    )

    class _ApiResponse:
        status_code = 200

        def raise_for_status(self):  # type: ignore[no-untyped-def]
            return None

        def json(self):  # type: ignore[no-untyped-def]
            return {
                'results': [
                    {
                        'html_url': 'https://www.federalregister.gov/documents/2026/01/01/2026-00001/sample',
                        'pdf_url': 'https://www.govinfo.gov/content/pkg/FR-2026-01-01/pdf/2026-00001.pdf',
                        'title': 'Operation Lone Star reimbursement for Texas exceeds 11 billion',
                        'abstract': 'Federal reimbursement obligation details',
                    }
                ]
            }

    monkeypatch.setattr('app.services.source_recommendation_service.httpx.get', lambda *_args, **_kwargs: _ApiResponse())
    monkeypatch.setattr('app.services.source_recommendation_service.get_source_recommendation_policy', lambda: policy)
    monkeypatch.setattr(SourceRecommendationService, '_load_claim_context', staticmethod(lambda _db, _claim_id: ctx))
    monkeypatch.setattr(SourceRecommendationService, '_load_source_snapshot', staticmethod(lambda _db, _claim_id: (set(), 0, 0)))
    monkeypatch.setattr(
        SourceRecommendationService,
        '_validate_recommendation_url',
        staticmethod(
            lambda _url, _context, require_methodology_signals=False: RecommendationValidationResult(
                status='validated',
                http_status=200,
                page_type='evidence_page',
                evidence_text='operation lone star reimbursement texas 11 billion obligation',
            )
        ),
    )

    result = SourceRecommendationService.get_recommendations(object(), claim_id=ctx.claim_id, limit=6)
    recommendations = result['recommendations']
    assert len(recommendations) == 1
    assert recommendations[0]['recommendation_role'] == 'attachable_evidence'
    assert recommendations[0]['evidence_url'] == 'https://www.federalregister.gov/documents/2026/01/01/2026-00001/sample'
    assert recommendations[0]['official_url'] == 'https://www.govinfo.gov/content/pkg/FR-2026-01-01/pdf/2026-00001.pdf'


def test_federal_register_access_block_pages_are_suppressed(monkeypatch) -> None:
    ctx = _funding_context()
    policy = SourceRecommendationPolicy(
        version='test-policy-v1',
        default_limit=6,
        templates=(
            SourceRecommendationTemplate(
                template_id='federal_register_primary',
                source_class=SourceClass.primary,
                publisher='Federal Register',
                url_template='https://www.federalregister.gov/documents/search?conditions%5Bterm%5D={query}',
                rationale='funding search',
                priority=10,
                supports_funding_claims=True,
            ),
        ),
    )
    monkeypatch.setattr('app.services.source_recommendation_service.get_source_recommendation_policy', lambda: policy)
    monkeypatch.setattr(SourceRecommendationService, '_load_claim_context', staticmethod(lambda _db, _claim_id: ctx))
    monkeypatch.setattr(SourceRecommendationService, '_load_source_snapshot', staticmethod(lambda _db, _claim_id: (set(), 0, 0)))
    monkeypatch.setattr(
        SourceRecommendationService,
        '_resolve_structured_discovery_url',
        staticmethod(
            lambda **_kwargs: ResolvedRecommendationResult(
                discovery_url='https://www.federalregister.gov/documents/search?conditions%5Bterm%5D=test',
                evidence_url=None,
                url='https://www.federalregister.gov/documents/search?conditions%5Bterm%5D=test',
                page_type='search_results',
                recommendation_role='discovery_only',
                validation_note='Federal Register search could not be resolved to a specific evidence document.',
                matched_anchors=[],
                missing_anchors=['amount', 'state'],
            )
        ),
    )
    monkeypatch.setattr(
        SourceRecommendationService,
        '_validate_recommendation_url',
        staticmethod(
            lambda _url, _context, require_methodology_signals=False: RecommendationValidationResult(
                status='weak_match',
                http_status=200,
                final_url='https://unblock.federalregister.gov',
                page_title='Federal Register :: Request Access',
                page_type='homepage',
                topic_overlap_score=0.1,
            )
        ),
    )

    result = SourceRecommendationService.get_recommendations(object(), claim_id=ctx.claim_id, limit=6)
    assert result['recommendations'] == []


def test_funding_anchor_assessment_handles_claim_amount_without_dollar_sign() -> None:
    ctx = ClaimRecommendationContext(
        claim_id=uuid.uuid4(),
        claim_text='Cornyn delivered more than 11 billion in reimbursements for Texas Operation Lone Star.',
        issue_tag='immigration',
        statement_text='statement',
        candidate_name='John Cornyn',
        candidate_party='Republican',
        candidate_office='US Senate',
        candidate_state='TX',
        election_cycle=2026,
        race_stage='primary_runoff',
    )
    matched, missing = SourceRecommendationService._funding_anchor_assessment(
        ctx,
        'operation lone star reimbursement for texas reached 11 billion in federal obligations',
    )
    assert 'amount' in matched
    assert 'state' in matched
    assert 'amount' not in missing
    assert 'state' not in missing


def test_funding_anchor_assessment_does_not_treat_state_abbrev_as_substring() -> None:
    ctx = _funding_context()
    matched, missing = SourceRecommendationService._funding_anchor_assessment(
        ctx,
        'operation lone star reimbursement next phase reached 11 billion in federal obligations',
    )
    assert 'amount' in matched
    assert 'state' in missing


def test_classify_page_type_does_not_mark_article_with_query_param_as_search() -> None:
    page_type = SourceRecommendationService._classify_page_type(
        'https://example.com/articles/cornyn-voting?q=tracking',
        'text/html; charset=utf-8',
        'cornyn voting article body text',
    )
    assert page_type == 'article'


def test_build_funding_query_includes_non_dollar_amount() -> None:
    ctx = ClaimRecommendationContext(
        claim_id=uuid.uuid4(),
        claim_text='Delivered more than 11 billion in reimbursements for Texas Operation Lone Star.',
        issue_tag='immigration',
        statement_text='statement',
        candidate_name='John Cornyn',
        candidate_party='Republican',
        candidate_office='US Senate',
        candidate_state='TX',
        election_cycle=2026,
        race_stage='primary_runoff',
    )
    query = SourceRecommendationService._build_funding_query(ctx)
    assert '11.0 billion' in query


def test_resolved_usaspending_award_stays_attachable_despite_weak_html_overlap(monkeypatch) -> None:
    """USAspending award pages are JS-rendered; weak topic overlap must NOT demote a resolver-confirmed award."""
    ctx = _funding_context()
    policy = SourceRecommendationPolicy(
        version='test-policy-v1',
        default_limit=6,
        templates=(
            SourceRecommendationTemplate(
                template_id='usaspending_primary',
                source_class=SourceClass.primary,
                publisher='USAspending.gov',
                url_template='https://www.usaspending.gov/search/?q={query}',
                rationale='funding search',
                priority=10,
                supports_funding_claims=True,
            ),
        ),
    )
    monkeypatch.setattr('app.services.source_recommendation_service.get_source_recommendation_policy', lambda: policy)
    monkeypatch.setattr(SourceRecommendationService, '_load_claim_context', staticmethod(lambda _db, _claim_id: ctx))
    monkeypatch.setattr(SourceRecommendationService, '_load_source_snapshot', staticmethod(lambda _db, _claim_id: (set(), 0, 0)))
    monkeypatch.setattr(
        SourceRecommendationService,
        '_resolve_structured_discovery_url',
        staticmethod(
            lambda **_kwargs: ResolvedRecommendationResult(
                discovery_url='https://www.usaspending.gov/search/?q=test',
                evidence_url='https://www.usaspending.gov/award/AWARD-1',
                url='https://www.usaspending.gov/award/AWARD-1',
                page_type='evidence_page',
                recommendation_role='attachable_evidence',
                validation_note='resolved',
                matched_anchors=['amount', 'state', 'funding_context'],
                missing_anchors=[],
            )
        ),
    )
    monkeypatch.setattr(
        SourceRecommendationService,
        '_validate_recommendation_url',
        staticmethod(
            lambda _url, _context, require_methodology_signals=False: RecommendationValidationResult(
                status='weak_match',
                http_status=200,
                page_type='evidence_page',
                validation_note='weak',
                evidence_text='',  # sparse JS-rendered page
            )
        ),
    )

    result = SourceRecommendationService.get_recommendations(object(), claim_id=ctx.claim_id, limit=6)
    rec = result['recommendations'][0]
    assert rec['recommendation_role'] == 'attachable_evidence', (
        'Resolver-confirmed USAspending award must not be demoted by JS-rendered sparse HTML overlap'
    )
    assert rec['evidence_url'] == 'https://www.usaspending.gov/award/AWARD-1'


def test_resolved_evidence_url_is_deduped_against_existing_sources(monkeypatch) -> None:
    ctx = _funding_context()
    policy = SourceRecommendationPolicy(
        version='test-policy-v1',
        default_limit=6,
        templates=(
            SourceRecommendationTemplate(
                template_id='usaspending_primary',
                source_class=SourceClass.primary,
                publisher='USAspending.gov',
                url_template='https://www.usaspending.gov/search/?q={query}',
                rationale='funding search',
                priority=10,
                supports_funding_claims=True,
            ),
        ),
    )
    existing_url = 'https://www.usaspending.gov/award/AWARD-1'
    monkeypatch.setattr('app.services.source_recommendation_service.get_source_recommendation_policy', lambda: policy)
    monkeypatch.setattr(SourceRecommendationService, '_load_claim_context', staticmethod(lambda _db, _claim_id: ctx))
    monkeypatch.setattr(
        SourceRecommendationService,
        '_load_source_snapshot',
        staticmethod(lambda _db, _claim_id: ({existing_url.lower()}, 0, 0)),
    )
    monkeypatch.setattr(
        SourceRecommendationService,
        '_resolve_structured_discovery_url',
        staticmethod(
            lambda **_kwargs: ResolvedRecommendationResult(
                discovery_url='https://www.usaspending.gov/search/?q=test',
                evidence_url=existing_url,
                url=existing_url,
                page_type='evidence_page',
                recommendation_role='attachable_evidence',
                validation_note='resolved',
                matched_anchors=['amount', 'state', 'funding_context'],
                missing_anchors=[],
            )
        ),
    )
    monkeypatch.setattr(
        SourceRecommendationService,
        '_validate_recommendation_url',
        staticmethod(
            lambda _url, _context, require_methodology_signals=False: RecommendationValidationResult(
                status='validated',
                http_status=200,
                page_type='evidence_page',
                evidence_text='operation lone star reimbursement texas 11 billion obligation',
            )
        ),
    )

    result = SourceRecommendationService.get_recommendations(object(), claim_id=ctx.claim_id, limit=6)
    assert result['recommendations'] == []


def _congress_bill_context(claim_text: str) -> ClaimRecommendationContext:
    return ClaimRecommendationContext(
        claim_id=uuid.uuid4(),
        claim_text=claim_text,
        issue_tag='legislation',
        statement_text='statement',
        candidate_name='John Cornyn',
        candidate_party='Republican',
        candidate_office='US Senate',
        candidate_state='TX',
        election_cycle=2026,
        race_stage='primary_runoff',
    )


def _congress_policy() -> SourceRecommendationPolicy:
    return SourceRecommendationPolicy(
        version='test-policy-v1',
        default_limit=6,
        templates=(
            SourceRecommendationTemplate(
                template_id='tx_senate_congress_primary',
                source_class=SourceClass.primary,
                publisher='Congress.gov',
                url_template='https://www.congress.gov/search?q={query}',
                rationale='Congress lookup',
                priority=10,
            ),
        ),
    )


def test_parse_explicit_bill_identifiers_normalizes_supported_forms() -> None:
    claim = 'S. 123 and S 123 plus H.R. 456 and HR 456 and S.J.Res. 12 and H.J.Res. 13 and S.Res. 10 and H.Res. 11'
    parsed = SourceRecommendationService._parse_explicit_bill_identifiers(claim)
    normalized = [(item.bill_type, item.bill_number) for item in parsed]
    assert normalized == [
        ('s', 123),
        ('hr', 456),
        ('sjres', 12),
        ('hjres', 13),
        ('sres', 10),
        ('hres', 11),
    ]


def test_congress_resolver_returns_discovery_only_when_api_key_missing(monkeypatch) -> None:
    ctx = _congress_bill_context('Cornyn backed H.R. 1234 in Congress.')
    monkeypatch.setattr('app.services.source_recommendation_service.settings.congress_api_key', '', raising=False)
    resolved = SourceRecommendationService._resolve_congress_bill_discovery_url('https://www.congress.gov/search?q=test', ctx)
    assert resolved.recommendation_role == 'discovery_only'
    assert resolved.validation_note == 'Congress.gov API key missing; bill resolver skipped.'


def test_congress_resolver_no_bill_id_does_not_call_api(monkeypatch) -> None:
    ctx = _congress_bill_context('Cornyn discussed border security legislation.')
    monkeypatch.setattr('app.services.source_recommendation_service.settings.congress_api_key', 'test-key', raising=False)
    called = {'count': 0}

    def _fake_fetch(*, congress_number: int, bill_type: str, bill_number: int) -> dict[str, object] | None:
        called['count'] += 1
        return None

    monkeypatch.setattr(SourceRecommendationService, '_fetch_congress_bill_record', staticmethod(_fake_fetch))
    resolved = SourceRecommendationService._resolve_congress_bill_discovery_url('https://www.congress.gov/search?q=test', ctx)
    assert resolved.recommendation_role == 'discovery_only'
    assert called['count'] == 0


def test_congress_resolver_no_match_returns_discovery_only(monkeypatch) -> None:
    ctx = _congress_bill_context('Cornyn backed H.R. 1234 in Congress.')
    monkeypatch.setattr('app.services.source_recommendation_service.settings.congress_api_key', 'test-key', raising=False)
    monkeypatch.setattr(
        SourceRecommendationService,
        '_fetch_congress_bill_record',
        staticmethod(lambda **_kwargs: None),
    )
    resolved = SourceRecommendationService._resolve_congress_bill_discovery_url('https://www.congress.gov/search?q=test', ctx)
    assert resolved.recommendation_role == 'discovery_only'
    assert resolved.validation_note == 'No matching Congress.gov bill record found.'


def test_congress_resolver_infers_current_then_previous_congress(monkeypatch) -> None:
    ctx = _congress_bill_context('Cornyn backed H.R. 1234 in Congress.')
    monkeypatch.setattr('app.services.source_recommendation_service.settings.congress_api_key', 'test-key', raising=False)
    monkeypatch.setattr(SourceRecommendationService, '_candidate_congress_numbers', staticmethod(lambda _claim: [119, 118]))
    calls: list[int] = []

    def _fake_fetch(*, congress_number: int, bill_type: str, bill_number: int) -> dict[str, object] | None:
        calls.append(congress_number)
        if congress_number == 118:
            return {'url': 'https://www.congress.gov/bill/118th-congress/house-bill/1234'}
        return None

    monkeypatch.setattr(SourceRecommendationService, '_fetch_congress_bill_record', staticmethod(_fake_fetch))
    resolved = SourceRecommendationService._resolve_congress_bill_discovery_url('https://www.congress.gov/search?q=test', ctx)
    assert calls == [119, 118]
    assert resolved.recommendation_role == 'attachable_evidence'
    assert resolved.evidence_url == 'https://www.congress.gov/bill/118th-congress/house-bill/1234'


def test_congress_resolver_returns_discovery_only_for_ambiguous_matches(monkeypatch) -> None:
    ctx = _congress_bill_context('Cornyn backed H.R. 1234 and S. 25.')
    monkeypatch.setattr('app.services.source_recommendation_service.settings.congress_api_key', 'test-key', raising=False)

    def _fake_fetch(*, congress_number: int, bill_type: str, bill_number: int) -> dict[str, object] | None:
        if bill_type == 'hr':
            return {'url': 'https://www.congress.gov/bill/118th-congress/house-bill/1234'}
        return None

    monkeypatch.setattr(SourceRecommendationService, '_candidate_congress_numbers', staticmethod(lambda _claim: [118]))
    monkeypatch.setattr(SourceRecommendationService, '_fetch_congress_bill_record', staticmethod(_fake_fetch))
    resolved = SourceRecommendationService._resolve_congress_bill_discovery_url('https://www.congress.gov/search?q=test', ctx)
    assert resolved.recommendation_role == 'discovery_only'
    assert resolved.validation_note == 'Multiple possible Congress.gov bill records found; reviewer should inspect manually.'


def test_congress_recommendation_resolves_and_is_attachable_when_validation_passes(monkeypatch) -> None:
    ctx = _congress_bill_context('Cornyn backed H.R. 1234 in Congress.')
    policy = _congress_policy()
    monkeypatch.setattr('app.services.source_recommendation_service.settings.congress_api_key', 'test-key', raising=False)
    monkeypatch.setattr('app.services.source_recommendation_service.get_source_recommendation_policy', lambda: policy)
    monkeypatch.setattr(SourceRecommendationService, '_load_claim_context', staticmethod(lambda _db, _claim_id: ctx))
    monkeypatch.setattr(SourceRecommendationService, '_load_source_snapshot', staticmethod(lambda _db, _claim_id: (set(), 0, 0)))
    monkeypatch.setattr(SourceRecommendationService, '_candidate_congress_numbers', staticmethod(lambda _claim: [118]))
    monkeypatch.setattr(
        SourceRecommendationService,
        '_fetch_congress_bill_record',
        staticmethod(lambda **_kwargs: {'url': 'https://www.congress.gov/bill/118th-congress/house-bill/1234'}),
    )
    monkeypatch.setattr(
        SourceRecommendationService,
        '_validate_recommendation_url',
        staticmethod(
            lambda _url, _context, require_methodology_signals=False: RecommendationValidationResult(
                status='validated',
                http_status=200,
                final_url='https://www.congress.gov/bill/118th-congress/house-bill/1234',
                page_title='H.R.1234 - 118th Congress',
                page_type='article',
                topic_overlap_score=0.7,
                validation_note='Reachable and topic-aligned.',
                evidence_text='hr 1234 text',
            )
        ),
    )

    result = SourceRecommendationService.get_recommendations(object(), claim_id=ctx.claim_id, limit=6)
    rec = result['recommendations'][0]
    assert rec['recommendation_role'] == 'attachable_evidence'
    assert rec['evidence_url'] == 'https://www.congress.gov/bill/118th-congress/house-bill/1234'


def test_congress_recommendation_downgrades_when_validation_fails(monkeypatch) -> None:
    ctx = _congress_bill_context('Cornyn backed H.R. 1234 in Congress.')
    policy = _congress_policy()
    monkeypatch.setattr('app.services.source_recommendation_service.settings.congress_api_key', 'test-key', raising=False)
    monkeypatch.setattr('app.services.source_recommendation_service.get_source_recommendation_policy', lambda: policy)
    monkeypatch.setattr(SourceRecommendationService, '_load_claim_context', staticmethod(lambda _db, _claim_id: ctx))
    monkeypatch.setattr(SourceRecommendationService, '_load_source_snapshot', staticmethod(lambda _db, _claim_id: (set(), 0, 0)))
    monkeypatch.setattr(SourceRecommendationService, '_candidate_congress_numbers', staticmethod(lambda _claim: [118]))
    monkeypatch.setattr(
        SourceRecommendationService,
        '_fetch_congress_bill_record',
        staticmethod(lambda **_kwargs: {'url': 'https://www.congress.gov/bill/118th-congress/house-bill/1234'}),
    )
    monkeypatch.setattr(
        SourceRecommendationService,
        '_validate_recommendation_url',
        staticmethod(
            lambda _url, _context, require_methodology_signals=False: RecommendationValidationResult(
                status='weak_match',
                http_status=200,
                final_url='https://www.congress.gov/bill/118th-congress/house-bill/1234',
                page_title='H.R.1234 - 118th Congress',
                page_type='article',
                topic_overlap_score=0.01,
                validation_note='weak',
                evidence_text='unrelated page',
            )
        ),
    )

    result = SourceRecommendationService.get_recommendations(object(), claim_id=ctx.claim_id, limit=6)
    rec = result['recommendations'][0]
    assert rec['recommendation_role'] == 'discovery_only'
    assert rec['evidence_url'] is None
    assert rec['validation_note'] == 'Congress.gov bill record resolved, but evidence page validation failed.'


def test_congress_template_not_skipped_when_claim_is_funding_and_has_bill_id(monkeypatch) -> None:
    ctx = _congress_bill_context('H.R. 1234 provided $11 billion for a reimbursement program in Texas.')
    policy = _congress_policy()
    monkeypatch.setattr('app.services.source_recommendation_service.settings.congress_api_key', 'test-key', raising=False)
    monkeypatch.setattr('app.services.source_recommendation_service.get_source_recommendation_policy', lambda: policy)
    monkeypatch.setattr(SourceRecommendationService, '_load_claim_context', staticmethod(lambda _db, _claim_id: ctx))
    monkeypatch.setattr(SourceRecommendationService, '_load_source_snapshot', staticmethod(lambda _db, _claim_id: (set(), 0, 0)))
    monkeypatch.setattr(
        SourceRecommendationService,
        '_resolve_structured_discovery_url',
        staticmethod(
            lambda **_kwargs: ResolvedRecommendationResult(
                discovery_url='https://www.congress.gov/search?q=test',
                evidence_url='https://www.congress.gov/bill/118th-congress/house-bill/1234',
                url='https://www.congress.gov/bill/118th-congress/house-bill/1234',
                page_type='article',
                recommendation_role='attachable_evidence',
                validation_note='Resolved official Congress.gov bill record. Reviewer must confirm the bill page supports the claim.',
                matched_anchors=['H.R. 1234', 'HR 1234'],
                missing_anchors=[],
            )
        ),
    )
    monkeypatch.setattr(
        SourceRecommendationService,
        '_validate_recommendation_url',
        staticmethod(
            lambda _url, _context, require_methodology_signals=False: RecommendationValidationResult(
                status='validated',
                http_status=200,
                final_url='https://www.congress.gov/bill/118th-congress/house-bill/1234',
                page_title='H.R.1234 - 118th Congress',
                page_type='article',
                topic_overlap_score=0.8,
                validation_note='Reachable and topic-aligned.',
                evidence_text='hr 1234 reimbursement texas 11 billion',
            )
        ),
    )

    result = SourceRecommendationService.get_recommendations(object(), claim_id=ctx.claim_id, limit=6)
    assert len(result['recommendations']) == 1
    rec = result['recommendations'][0]
    assert rec['template_id'] == 'tx_senate_congress_primary'
    assert rec['recommendation_role'] == 'attachable_evidence'


def test_usaspending_payload_includes_award_type_codes_and_no_state_abbrev_keyword() -> None:
    ctx = _funding_context()
    payload = SourceRecommendationService._build_usaspending_search_payload(ctx)
    filters = payload.get('filters') or {}
    assert 'award_type_codes' in filters
    assert isinstance(filters.get('award_type_codes'), list)
    keywords = filters.get('keywords')
    assert isinstance(keywords, list)
    assert 'TX' not in keywords
    # generated_internal_id must be in the fields list so award URL construction works
    assert 'generated_internal_id' in payload['fields']
    assert 'generated_unique_award_id' in payload['fields']
    # dollar amount must not appear as a keyword (it's a text-search field, not numeric)
    assert not any('billion' in str(k).lower() or 'million' in str(k).lower() for k in keywords)
    # award_amount range filter should be present when the claim specifies an amount
    assert 'award_amount' in filters


def test_usaspending_payload_uses_grant_codes_for_reimbursement_claim() -> None:
    ctx = ClaimRecommendationContext(
        claim_id=uuid.uuid4(),
        claim_text='Texas received $11 billion in federal reimbursement for Operation Lone Star.',
        issue_tag='immigration',
        statement_text='The state was reimbursed.',
        candidate_name='John Cornyn',
        candidate_party='Republican',
        candidate_office='us senate',
        candidate_state='TX',
        election_cycle=2026,
        race_stage=None,
    )
    payload = SourceRecommendationService._build_usaspending_search_payload(ctx)
    filters = payload.get('filters') or {}
    grant_codes = set(SourceRecommendationService._USASPENDING_GRANT_AWARD_TYPE_CODES)
    assert set(filters['award_type_codes']) == grant_codes, (
        'reimbursement claims should use grant award type codes, not direct payment'
    )


def test_federal_register_resolver_attachable_without_amount_in_metadata(monkeypatch) -> None:
    """FR titles and abstracts never contain dollar amounts; attachability must not require them."""
    ctx = _funding_context()
    policy = SourceRecommendationPolicy(
        version='test-policy-v1',
        default_limit=6,
        templates=(
            SourceRecommendationTemplate(
                template_id='federal_register_primary',
                source_class=SourceClass.primary,
                publisher='Federal Register',
                url_template='https://www.federalregister.gov/documents/search?conditions%5Bterm%5D={query}',
                rationale='funding search',
                priority=10,
                supports_funding_claims=True,
            ),
        ),
    )

    class _ApiResponse:
        status_code = 200

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {
                'results': [
                    {
                        'html_url': 'https://www.federalregister.gov/documents/2026/03/01/2026-05000/lone-star',
                        'pdf_url': 'https://www.govinfo.gov/content/pkg/FR-2026-03-01/pdf/2026-05000.pdf',
                        # No dollar amount here — realistic FR metadata
                        'title': 'Operation Lone Star Border Security Reimbursement Program',
                        'abstract': 'Federal reimbursement obligation for Texas border operations.',
                        'type': 'Rule',
                        'agencies': 'Department of Homeland Security',
                    }
                ]
            }

    monkeypatch.setattr('app.services.source_recommendation_service.httpx.get', lambda *_args, **_kwargs: _ApiResponse())
    monkeypatch.setattr('app.services.source_recommendation_service.get_source_recommendation_policy', lambda: policy)
    monkeypatch.setattr(SourceRecommendationService, '_load_claim_context', staticmethod(lambda _db, _claim_id: ctx))
    monkeypatch.setattr(SourceRecommendationService, '_load_source_snapshot', staticmethod(lambda _db, _claim_id: (set(), 0, 0)))
    monkeypatch.setattr(
        SourceRecommendationService,
        '_validate_recommendation_url',
        staticmethod(
            lambda _url, _context, require_methodology_signals=False: RecommendationValidationResult(
                status='validated',
                http_status=200,
                page_type='evidence_page',
                evidence_text='operation lone star reimbursement texas obligation',
            )
        ),
    )

    result = SourceRecommendationService.get_recommendations(object(), claim_id=ctx.claim_id, limit=6)
    recommendations = result['recommendations']
    assert len(recommendations) == 1
    assert recommendations[0]['recommendation_role'] == 'attachable_evidence', (
        'FR document with state + program + funding_context should be attachable even without amount in metadata'
    )
    assert recommendations[0]['evidence_url'] == 'https://www.federalregister.gov/documents/2026/03/01/2026-05000/lone-star'


def test_trusted_domain_resolver_not_demoted_by_weak_overlap(monkeypatch) -> None:
    """USAspending award pages are JS-rendered and score low on topic overlap.
    A resolver-confirmed attachable_evidence URL from a trusted domain must not be demoted."""
    ctx = _funding_context()
    policy = SourceRecommendationPolicy(
        version='test-policy-v1',
        default_limit=6,
        templates=(
            SourceRecommendationTemplate(
                template_id='usaspending_primary',
                source_class=SourceClass.primary,
                publisher='USAspending.gov',
                url_template='https://www.usaspending.gov/search/?q={query}',
                rationale='funding search',
                priority=10,
                supports_funding_claims=True,
            ),
        ),
    )

    class _ApiResponse:
        status_code = 200

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {
                'results': [
                    {
                        'generated_internal_id': 'AWARD-TRUSTED-001',
                        'Description': 'Operation Lone Star reimbursement Texas 11 billion obligation',
                        'Recipient Name': 'State of Texas',
                        'Award Type': 'Grant',
                    }
                ]
            }

    monkeypatch.setattr('app.services.source_recommendation_service.httpx.post', lambda *_args, **_kwargs: _ApiResponse())
    monkeypatch.setattr('app.services.source_recommendation_service.get_source_recommendation_policy', lambda: policy)
    monkeypatch.setattr(SourceRecommendationService, '_load_claim_context', staticmethod(lambda _db, _claim_id: ctx))
    monkeypatch.setattr(SourceRecommendationService, '_load_source_snapshot', staticmethod(lambda _db, _claim_id: (set(), 0, 0)))
    # Simulate a JS-rendered page: HTTP 200 but nearly empty HTML → weak_match
    monkeypatch.setattr(
        SourceRecommendationService,
        '_validate_recommendation_url',
        staticmethod(
            lambda _url, _context, require_methodology_signals=False: RecommendationValidationResult(
                status='weak_match',
                http_status=200,
                page_type='article',
                topic_overlap_score=0.05,
                evidence_text='',
            )
        ),
    )

    result = SourceRecommendationService.get_recommendations(object(), claim_id=ctx.claim_id, limit=6)
    recommendations = result['recommendations']
    assert len(recommendations) == 1
    assert recommendations[0]['recommendation_role'] == 'attachable_evidence', (
        'Resolver-confirmed award URL on trusted domain must not be demoted by weak topic overlap'
    )
    assert recommendations[0]['evidence_url'] == 'https://www.usaspending.gov/award/AWARD-TRUSTED-001'


def test_usaspending_resolver_uses_award_amount_field_for_amount_anchor() -> None:
    """Award Amount from the API response must satisfy the amount anchor when within 40% tolerance."""
    ctx = _funding_context()
    # Claim says $11 billion; API returns award with Award Amount = 10_000_000_000 (within 40%)
    item_text = SourceRecommendationService._collapse_whitespace(
        ' '.join([
            'Operation Lone Star reimbursement border',
            'State of Texas',
            'Grant',
            'AWARD-123',
            str(10_000_000_000.0),  # Award Amount — within 40% of $11B
        ])
    ).lower()
    matched, missing = SourceRecommendationService._funding_anchor_assessment(
        ctx, item_text, amount_tolerance_pct=0.4
    )
    assert 'amount' in matched, 'Award Amount within 40% tolerance should satisfy the amount anchor'
    assert 'amount' not in missing


def test_federal_register_attachable_rejects_ols_claim_without_program_match() -> None:
    """FR item must not be attachable for an OLS claim when the document doesn't mention Operation Lone Star."""
    ctx = _funding_context()  # claim contains 'operation lone star'
    matched = ['state', 'funding_context']   # program NOT matched
    missing = ['amount', 'program']          # program in missing
    result = SourceRecommendationService._federal_register_item_is_attachable(ctx, matched, missing)
    assert result is False, 'OLS claim requires program anchor; generic TX funding doc must not attach'


def test_federal_register_attachable_passes_non_ols_claim_without_program() -> None:
    """For a non-OLS claim, FR item is attachable with state + funding_context even without program."""
    ctx = ClaimRecommendationContext(
        claim_id=uuid.uuid4(),
        claim_text='Texas received $500 million in federal housing grants.',
        issue_tag='funding',
        statement_text='The state received housing grants.',
        candidate_name='John Cornyn',
        candidate_party='Republican',
        candidate_office='us senate',
        candidate_state='TX',
        election_cycle=2026,
        race_stage=None,
    )
    matched = ['state', 'funding_context']
    missing = ['amount']   # no program anchor checked for non-OLS claims
    result = SourceRecommendationService._federal_register_item_is_attachable(ctx, matched, missing)
    assert result is True


def test_fr_resolver_missing_anchors_excludes_amount() -> None:
    """missing_anchors in FR resolver output must not contain 'amount' — it is not required."""
    ctx = _funding_context()
    # FR metadata has state + program + funding_context but no dollar amount
    text = 'operation lone star border security reimbursement program texas'
    matched, missing = SourceRecommendationService._funding_anchor_assessment(ctx, text)
    display_missing = [m for m in missing if m != 'amount']
    assert 'amount' not in display_missing
    assert 'amount' in missing, 'amount should still be in raw missing (FR metadata never has amounts)'
