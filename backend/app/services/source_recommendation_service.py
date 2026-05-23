from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from urllib.parse import quote_plus

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.core.source_admission_policy import find_partisan_rule_match, is_social_url
from app.core.source_recommendation_policy import SourceRecommendationTemplate, get_source_recommendation_policy
from app.models.entities import Candidate, Claim, Source, Statement
from app.models.enums import SourceClass, SourceOrigin


@dataclass(frozen=True)
class ClaimRecommendationContext:
    claim_id: uuid.UUID
    claim_text: str
    issue_tag: str | None
    statement_text: str
    candidate_name: str
    candidate_party: str | None
    candidate_office: str | None
    candidate_state: str | None
    election_cycle: int | None
    race_stage: str | None


@dataclass(frozen=True)
class RecommendationValidationResult:
    status: str
    http_status: int | None = None
    final_url: str | None = None
    page_title: str | None = None
    topic_overlap_score: float | None = None
    validation_note: str | None = None


class SourceRecommendationService:
    _HTTP_TIMEOUT_SECONDS = 4.0
    _MAX_HTML_SCAN_CHARS = 18000
    _STOPWORDS = {
        'about', 'against', 'after', 'again', 'also', 'among', 'because', 'before', 'being', 'claim',
        'congress', 'could', 'election', 'first', 'from', 'have', 'john', 'more', 'over', 'percent',
        'record', 'senator', 'senate', 'state', 'than', 'that', 'their', 'there', 'these', 'they',
        'this', 'time', 'trump', 'with', 'would', 'voted', 'voting',
    }
    _EMPTY_RESULT_PATTERNS = (
        'no results found',
        'no results matched',
        'did not match any documents',
        'we could not find any results',
        '0 results',
        'no search results',
    )
    _NUMERIC_VOTING_PATTERNS = (
        r'\b\d{1,3}%\b',
        r'\b\d+\s+out\s+of\s+\d+\b',
        r'\bvoted with trump\b',
        r'\bpro-trump voting record\b',
        r'\bstronger pro-trump\b',
        r'\bpresidential support\b',
    )
    _METHODOLOGY_PATTERNS = (
        'methodology',
        'roll call',
        'roll-call',
        'voteview',
        'presidential support',
        'dw-nominate',
        'dw nominate',
        'score',
        'scoring',
        'how we calculated',
    )
    _FUNDING_CLAIM_PATTERNS = (
        r'\$\s*\d',
        r'\b\d+(\.\d+)?\s*(billion|million)\b',
        r'\breimbursement(s)?\b',
        r'\bfederal (funding|reimbursement|reimbursements|aid|grant|grants)\b',
        r'\bobligation(s)?\b',
        r'\ballocation(s)?\b',
        r'\boperation lone star\b',
    )
    _MIN_TOPIC_OVERLAP_DEFAULT = 0.2
    _MIN_TOPIC_OVERLAP_FUNDING = 0.25

    @staticmethod
    def _normalize_url(url: str) -> str:
        return url.strip().rstrip('/').lower()

    @staticmethod
    def _collapse_whitespace(value: str) -> str:
        return re.sub(r'\s+', ' ', value or '').strip()

    @staticmethod
    def _build_search_query(context: ClaimRecommendationContext) -> str:
        parts: list[str] = [
            context.candidate_name,
            context.candidate_office or '',
            context.candidate_state or '',
            str(context.election_cycle or ''),
            context.issue_tag or '',
        ]
        claim_excerpt = context.claim_text.strip()
        if claim_excerpt:
            parts.append(claim_excerpt[:180])
        return ' '.join(part for part in parts if part).strip()

    @staticmethod
    def _is_numeric_voting_claim(context: ClaimRecommendationContext) -> bool:
        issue = (context.issue_tag or '').strip().lower()
        haystack = ' '.join([context.claim_text or '', context.statement_text or '', issue]).lower()
        if issue == 'voting_record':
            return True
        return any(re.search(pattern, haystack) for pattern in SourceRecommendationService._NUMERIC_VOTING_PATTERNS)

    @staticmethod
    def _is_funding_claim(context: ClaimRecommendationContext) -> bool:
        issue = (context.issue_tag or '').strip().lower()
        haystack = ' '.join([context.claim_text or '', context.statement_text or '', issue]).lower()
        if issue in {'budget', 'spending', 'immigration', 'border', 'funding'}:
            return True
        return any(re.search(pattern, haystack) for pattern in SourceRecommendationService._FUNDING_CLAIM_PATTERNS)

    @staticmethod
    def _build_funding_query(context: ClaimRecommendationContext) -> str:
        # Prefer a shorter query for search endpoints; long full-claim queries often yield empty/irrelevant results.
        claim = (context.claim_text or '').lower()
        amount_match = re.search(r'(\$\s*\d[\d\.,]*\s*(billion|million)?)', claim)
        amount = amount_match.group(1) if amount_match else ''
        parts = [
            context.candidate_name,
            context.candidate_state or '',
            'Operation Lone Star' if 'operation lone star' in claim else '',
            'reimbursement' if 'reimburse' in claim else 'funding',
            amount,
        ]
        return ' '.join(part for part in parts if part).strip()

    @staticmethod
    def _build_template_query(
        template: SourceRecommendationTemplate,
        context: ClaimRecommendationContext,
        *,
        numeric_voting_claim: bool,
    ) -> str:
        funding_claim = SourceRecommendationService._is_funding_claim(context)
        if funding_claim and template.supports_funding_claims:
            query = SourceRecommendationService._build_funding_query(context)
        else:
            query = SourceRecommendationService._build_search_query(context)

        hint = (template.query_hint or '').strip()
        if hint and (numeric_voting_claim or funding_claim):
            query = f'{query} {hint}'.strip()
        return query

    @staticmethod
    def _template_matches_context(template: SourceRecommendationTemplate, context: ClaimRecommendationContext) -> bool:
        context_state = (context.candidate_state or '').strip().upper()
        context_office = (context.candidate_office or '').strip().lower()
        context_stage = (context.race_stage or '').strip().lower()
        context_issue = (context.issue_tag or '').strip().lower()

        if template.state is not None and template.state != context_state:
            return False
        if template.office is not None and template.office != context_office:
            return False
        if template.race_stage is not None and template.race_stage != context_stage:
            return False
        if template.issue_tags and context_issue not in set(template.issue_tags):
            return False
        return True

    @staticmethod
    def _load_claim_context(db: Session, claim_id: uuid.UUID) -> ClaimRecommendationContext:
        row = (
            db.execute(
                select(Claim, Statement, Candidate)
                .join(Statement, Statement.id == Claim.statement_id)
                .join(Candidate, Candidate.id == Statement.candidate_id)
                .where(Claim.id == claim_id)
            )
            .first()
        )
        if row is None:
            raise AppError('claim_not_found', 'Claim does not exist.', status_code=404)
        claim, statement, candidate = row
        return ClaimRecommendationContext(
            claim_id=claim.id,
            claim_text=claim.claim_text,
            issue_tag=claim.issue_tag,
            statement_text=statement.statement_text,
            candidate_name=candidate.name,
            candidate_party=candidate.party,
            candidate_office=candidate.office,
            candidate_state=candidate.state,
            election_cycle=candidate.election_cycle,
            race_stage=candidate.race_stage.value if candidate.race_stage is not None else None,
        )

    @staticmethod
    def _load_source_snapshot(db: Session, claim_id: uuid.UUID) -> tuple[set[str], int, int]:
        sources = db.scalars(select(Source).where(Source.claim_id == claim_id)).all()
        urls = {SourceRecommendationService._normalize_url(source.url) for source in sources}
        verification_primary_count = 0
        verification_secondary_count = 0
        for source in sources:
            if source.source_origin != SourceOrigin.verification or bool(getattr(source, 'policy_flagged', False)):
                continue
            if source.source_class == SourceClass.primary:
                verification_primary_count += 1
            elif source.source_class == SourceClass.secondary:
                verification_secondary_count += 1
        return urls, verification_primary_count, verification_secondary_count

    @staticmethod
    def _render_template_url(template: SourceRecommendationTemplate, context: ClaimRecommendationContext, query_encoded: str) -> str | None:
        try:
            return template.url_template.format(
                query=query_encoded,
                candidate_name=quote_plus(context.candidate_name),
                office=quote_plus(context.candidate_office or ''),
                state=quote_plus(context.candidate_state or ''),
                issue_tag=quote_plus(context.issue_tag or ''),
                election_cycle=str(context.election_cycle or ''),
            )
        except (KeyError, ValueError, IndexError):
            # Keep endpoint resilient to misconfigured templates by skipping bad rows.
            return None

    @staticmethod
    def _extract_title(html_text: str) -> str | None:
        match = re.search(r'<title[^>]*>(.*?)</title>', html_text, flags=re.IGNORECASE | re.DOTALL)
        if not match:
            return None
        title = re.sub(r'<[^>]+>', ' ', match.group(1))
        title = SourceRecommendationService._collapse_whitespace(title)
        return title or None

    @staticmethod
    def _build_expected_terms(context: ClaimRecommendationContext) -> list[str]:
        funding_claim = SourceRecommendationService._is_funding_claim(context)
        base_text = ' '.join([
            context.candidate_name,
            context.issue_tag or '',
            context.claim_text,
        ])

        # Funding / reimbursement claims benefit from tighter expected terms: include money/program tokens
        # and avoid letting generic office/cycle words crowd out the signal.
        if funding_claim:
            lowered_claim = (context.claim_text or '').lower()
            amount_match = re.search(r'(\$\s*\d[\d\.,]*\s*(billion|million)?)', lowered_claim)
            amount = amount_match.group(1) if amount_match else ''
            base_text = ' '.join(
                filter(
                    None,
                    [
                        context.candidate_name,
                        'operation lone star' if 'operation lone star' in lowered_claim else '',
                        'reimbursement' if 'reimburs' in lowered_claim else '',
                        amount,
                        context.claim_text,
                    ],
                )
            )

        raw_terms = re.findall(r'[A-Za-z0-9]+', base_text.lower())
        terms: list[str] = []
        seen: set[str] = set()
        for term in raw_terms:
            if len(term) < 4 or term in SourceRecommendationService._STOPWORDS or term in seen:
                continue
            terms.append(term)
            seen.add(term)
            if len(terms) >= 10:
                break
        surname_parts = [part.lower() for part in re.findall(r'[A-Za-z0-9]+', context.candidate_name) if len(part) >= 4]
        for surname in surname_parts:
            if surname not in seen:
                terms.insert(0, surname)
                seen.add(surname)
                break
        return terms[:10]

    @staticmethod
    def _compute_topic_overlap(text: str, expected_terms: list[str]) -> float:
        if not expected_terms:
            return 0.0
        lowered = text.lower()
        matches = sum(1 for term in expected_terms if term in lowered)
        return round(matches / len(expected_terms), 2)

    @staticmethod
    def _validate_recommendation_url(
        url: str,
        context: ClaimRecommendationContext,
        *,
        require_methodology_signals: bool = False,
    ) -> RecommendationValidationResult:
        headers = {'User-Agent': 'civic-fact-audit-source-validator/1.0'}
        try:
            response = httpx.get(url, follow_redirects=True, timeout=SourceRecommendationService._HTTP_TIMEOUT_SECONDS, headers=headers)
        except httpx.HTTPError as exc:
            return RecommendationValidationResult(
                status='unreachable',
                validation_note=f'Network check failed: {exc.__class__.__name__}.',
            )

        content_type = (response.headers.get('content-type') or '').lower()
        final_url = str(response.url)
        if response.status_code >= 400:
            return RecommendationValidationResult(
                status='unreachable',
                http_status=response.status_code,
                final_url=final_url,
                validation_note=f'HTTP {response.status_code}.',
            )

        if 'text/html' not in content_type and 'text/plain' not in content_type:
            return RecommendationValidationResult(
                status='validated',
                http_status=response.status_code,
                final_url=final_url,
                validation_note='Reachable non-HTML response.',
                topic_overlap_score=0.0,
            )

        html_text = response.text[:SourceRecommendationService._MAX_HTML_SCAN_CHARS]
        collapsed = SourceRecommendationService._collapse_whitespace(re.sub(r'<[^>]+>', ' ', html_text))
        lowered = collapsed.lower()
        if any(pattern in lowered for pattern in SourceRecommendationService._EMPTY_RESULT_PATTERNS):
            return RecommendationValidationResult(
                status='no_results',
                http_status=response.status_code,
                final_url=final_url,
                page_title=SourceRecommendationService._extract_title(html_text),
                validation_note='Search page returned no visible results.',
            )

        expected_terms = SourceRecommendationService._build_expected_terms(context)
        overlap = SourceRecommendationService._compute_topic_overlap(
            ' '.join(filter(None, [SourceRecommendationService._extract_title(html_text) or '', collapsed])),
            expected_terms,
        )
        if require_methodology_signals and not any(pattern in lowered for pattern in SourceRecommendationService._METHODOLOGY_PATTERNS):
            return RecommendationValidationResult(
                status='weak_match',
                http_status=response.status_code,
                final_url=final_url,
                page_title=SourceRecommendationService._extract_title(html_text),
                topic_overlap_score=overlap,
                validation_note='Reachable, but methodology signals are missing for this numeric voting-record claim.',
            )
        min_overlap = SourceRecommendationService._MIN_TOPIC_OVERLAP_FUNDING if SourceRecommendationService._is_funding_claim(context) else SourceRecommendationService._MIN_TOPIC_OVERLAP_DEFAULT
        # Guard against low-relevance redirects (e.g., being sent to an unrelated old page).
        if overlap < min_overlap:
            return RecommendationValidationResult(
                status='weak_match',
                http_status=response.status_code,
                final_url=final_url,
                page_title=SourceRecommendationService._extract_title(html_text),
                topic_overlap_score=overlap,
                validation_note='Reachable, but relevance to the claim appears weak.',
            )
        note = 'Reachable and topic-aligned.' if overlap > 0 else 'Reachable, but topic alignment is weak.'
        return RecommendationValidationResult(
            status='validated',
            http_status=response.status_code,
            final_url=final_url,
            page_title=SourceRecommendationService._extract_title(html_text),
            topic_overlap_score=overlap,
            validation_note=note,
        )

    @staticmethod
    def get_recommendations(
        db: Session,
        *,
        claim_id: uuid.UUID,
        limit: int | None = None,
    ) -> dict[str, object]:
        policy = get_source_recommendation_policy()
        context = SourceRecommendationService._load_claim_context(db, claim_id)
        existing_urls, verification_primary_count, verification_secondary_count = SourceRecommendationService._load_source_snapshot(
            db, claim_id
        )
        capped_limit = min(max(int(limit or policy.default_limit), 1), 12)
        numeric_voting_claim = SourceRecommendationService._is_numeric_voting_claim(context)
        funding_claim = SourceRecommendationService._is_funding_claim(context)

        suggestions: list[dict[str, object]] = []
        seen_urls: set[str] = set()
        for template in sorted(policy.templates, key=lambda item: (item.priority, item.template_id)):
            if not SourceRecommendationService._template_matches_context(template, context):
                continue
            if numeric_voting_claim and not template.supports_numeric_voting_claims:
                continue
            if funding_claim and not template.supports_funding_claims:
                continue
            if not template.url_template:
                continue
            query = SourceRecommendationService._build_template_query(
                template,
                context,
                numeric_voting_claim=numeric_voting_claim,
            )
            query_encoded = quote_plus(query)
            url = SourceRecommendationService._render_template_url(template, context, query_encoded)
            if url is None:
                continue
            normalized_url = SourceRecommendationService._normalize_url(url)
            if normalized_url in existing_urls or normalized_url in seen_urls:
                continue
            if is_social_url(url):
                continue
            if find_partisan_rule_match(publisher=template.publisher, url=url) is not None:
                continue
            validation = SourceRecommendationService._validate_recommendation_url(
                url,
                context,
                require_methodology_signals=numeric_voting_claim and template.requires_methodology_signals,
            )
            if validation.status in {'unreachable', 'no_results', 'weak_match'}:
                continue
            min_overlap = template.min_topic_overlap
            if min_overlap is not None and validation.topic_overlap_score is not None and validation.topic_overlap_score < float(min_overlap):
                continue
            seen_urls.add(normalized_url)
            suggestions.append(
                {
                    'template_id': template.template_id,
                    'source_class': template.source_class,
                    'source_origin': SourceOrigin.verification,
                    'url': url,
                    'publisher': template.publisher,
                    'rationale': template.rationale,
                    'validation_status': validation.status,
                    'http_status': validation.http_status,
                    'final_url': validation.final_url,
                    'page_title': validation.page_title,
                    'topic_overlap_score': validation.topic_overlap_score,
                    'validation_note': validation.validation_note,
                }
            )
            if len(suggestions) >= capped_limit:
                break

        missing: list[SourceClass] = []
        if verification_primary_count < 1:
            missing.append(SourceClass.primary)
        if verification_secondary_count < 1:
            missing.append(SourceClass.secondary)

        return {
            'claim_id': context.claim_id,
            'policy_version': policy.version,
            'recommendations': [
                {
                    'rank': idx + 1,
                    **item,
                }
                for idx, item in enumerate(suggestions)
            ],
            'verification_primary_count': verification_primary_count,
            'verification_secondary_count': verification_secondary_count,
            'missing_source_classes': missing,
        }
