from __future__ import annotations

import re
import uuid
from datetime import date
from dataclasses import dataclass
from typing import Any
from urllib.parse import parse_qs, quote_plus, urlparse

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
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
    page_type: str | None = None
    evidence_text: str | None = None


@dataclass(frozen=True)
class ResolvedRecommendationResult:
    discovery_url: str
    evidence_url: str | None
    url: str
    page_type: str
    recommendation_role: str
    validation_note: str
    matched_anchors: list[str]
    missing_anchors: list[str]
    official_url: str | None = None


@dataclass(frozen=True)
class ParsedBillIdentifier:
    original_text: str
    bill_type: str
    bill_number: int


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
    _NON_ATTACHABLE_PAGE_TYPES = {'search_results', 'homepage', 'section_page'}
    _FUNDING_CONTEXT_PATTERNS = ('reimbursement', 'funding', 'grant', 'obligation', 'allocation')
    _SEARCH_QUERY_KEYS = frozenset({'q', 'query', 'k', 'term', 'search'})
    _SEARCH_PATH_SEGMENTS = frozenset({'search', 'find', 'result', 'results'})
    _FUNDING_REQUIRED_CONTEXT_ANCHORS = 2
    _USASPENDING_SEARCH_API_URL = 'https://api.usaspending.gov/api/v2/search/spending_by_award/'
    # USAspending /api/v2/search/spending_by_award/ requires award_type_codes and expects them
    # to come from a single award-type group. We keep this intentionally narrow and deterministic.
    _USASPENDING_GRANT_AWARD_TYPE_CODES = ('02', '03', '04', '05')
    _USASPENDING_DIRECT_PAYMENT_AWARD_TYPE_CODES = ('10',)
    _FEDERAL_REGISTER_SEARCH_API_URL = 'https://www.federalregister.gov/api/v1/documents.json'
    _CONGRESS_BILL_API_BASE_URL = 'https://api.congress.gov/v3/bill'
    _RESOLVER_RESULT_LIMIT = 10
    _FEDERAL_REGISTER_ACCESS_BLOCK_DOMAINS = frozenset({'unblock.federalregister.gov'})
    # USAspending award pages are JS-rendered; HTML body is too sparse for topic-overlap checks.
    # Federal Register and Congress.gov pages render full HTML, so overlap validation is meaningful.
    _RESOLVER_TRUSTED_DOMAINS = frozenset({'www.usaspending.gov'})
    _STATE_ABBR_TO_NAME = {
        'AL': 'alabama', 'AK': 'alaska', 'AZ': 'arizona', 'AR': 'arkansas', 'CA': 'california',
        'CO': 'colorado', 'CT': 'connecticut', 'DE': 'delaware', 'FL': 'florida', 'GA': 'georgia',
        'HI': 'hawaii', 'ID': 'idaho', 'IL': 'illinois', 'IN': 'indiana', 'IA': 'iowa',
        'KS': 'kansas', 'KY': 'kentucky', 'LA': 'louisiana', 'ME': 'maine', 'MD': 'maryland',
        'MA': 'massachusetts', 'MI': 'michigan', 'MN': 'minnesota', 'MS': 'mississippi',
        'MO': 'missouri', 'MT': 'montana', 'NE': 'nebraska', 'NV': 'nevada', 'NH': 'new hampshire',
        'NJ': 'new jersey', 'NM': 'new mexico', 'NY': 'new york', 'NC': 'north carolina',
        'ND': 'north dakota', 'OH': 'ohio', 'OK': 'oklahoma', 'OR': 'oregon', 'PA': 'pennsylvania',
        'RI': 'rhode island', 'SC': 'south carolina', 'SD': 'south dakota', 'TN': 'tennessee',
        'TX': 'texas', 'UT': 'utah', 'VT': 'vermont', 'VA': 'virginia', 'WA': 'washington',
        'WV': 'west virginia', 'WI': 'wisconsin', 'WY': 'wyoming', 'DC': 'district of columbia',
    }
    _BILL_ID_PATTERNS = (
        (re.compile(r'\b(S)\.\s*(\d+)\b', re.IGNORECASE), 's'),
        (re.compile(r'\b(S)\s+(\d+)\b', re.IGNORECASE), 's'),
        (re.compile(r'\b(H\.?\s*R)\.?\s*(\d+)\b', re.IGNORECASE), 'hr'),
        (re.compile(r'\b(S\.?\s*J\.?\s*RES)\.?\s*(\d+)\b', re.IGNORECASE), 'sjres'),
        (re.compile(r'\b(H\.?\s*J\.?\s*RES)\.?\s*(\d+)\b', re.IGNORECASE), 'hjres'),
        (re.compile(r'\b(S\.?\s*RES)\.?\s*(\d+)\b', re.IGNORECASE), 'sres'),
        (re.compile(r'\b(H\.?\s*RES)\.?\s*(\d+)\b', re.IGNORECASE), 'hres'),
    )
    _CONGRESS_EXPLICIT_PATTERN = re.compile(r'\b(\d{1,3})(st|nd|rd|th)\s+congress\b', re.IGNORECASE)
    _BILL_TYPE_SEGMENT = {
        's': 'senate-bill',
        'hr': 'house-bill',
        'sjres': 'senate-joint-resolution',
        'hjres': 'house-joint-resolution',
        'sres': 'senate-resolution',
        'hres': 'house-resolution',
    }
    _SOURCE_CATEGORY_DEFAULT_BY_CLASS = {
        SourceClass.primary: 'primary_record',
        SourceClass.secondary: 'secondary_news',
    }

    @staticmethod
    def _normalize_url(url: str) -> str:
        return url.strip().rstrip('/').lower()

    @staticmethod
    def _is_resolver_trusted_url(url: str) -> bool:
        host = urlparse(url).netloc.lower()
        return host in SourceRecommendationService._RESOLVER_TRUSTED_DOMAINS

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
        amount = ''
        amount_value = SourceRecommendationService._extract_claim_amount_value(claim)
        if amount_value is not None:
            if amount_value >= 1_000_000_000:
                amount = f'{round(amount_value / 1_000_000_000, 2)} billion'
            elif amount_value >= 1_000_000:
                amount = f'{round(amount_value / 1_000_000, 2)} million'
            elif amount_value >= 1_000:
                amount = f'{round(amount_value / 1_000, 2)} thousand'
            else:
                amount = str(int(amount_value))
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
    def _normalize_issue_tag(value: str | None) -> str:
        text = (value or '').strip().lower()
        if not text:
            return ''
        # Keep policy tags compatible with UI-style labels like "Democracy & Elections".
        text = text.replace('&', ' and ')
        normalized = re.sub(r'[^a-z0-9]+', '_', text).strip('_')
        return normalized

    @staticmethod
    def _template_matches_context(template: SourceRecommendationTemplate, context: ClaimRecommendationContext) -> bool:
        context_state = (context.candidate_state or '').strip().upper()
        context_office = (context.candidate_office or '').strip().lower()
        context_stage = (context.race_stage or '').strip().lower()
        context_issue = SourceRecommendationService._normalize_issue_tag(context.issue_tag)

        if template.state is not None and template.state != context_state:
            return False
        if template.office is not None and template.office != context_office:
            return False
        if template.race_stage is not None and template.race_stage != context_stage:
            return False
        if template.issue_tags:
            template_issue_tags = {SourceRecommendationService._normalize_issue_tag(tag) for tag in template.issue_tags}
            if context_issue not in template_issue_tags:
                return False
        return True

    @staticmethod
    def _source_category_for_template(template: SourceRecommendationTemplate) -> str:
        if template.source_category:
            return template.source_category
        return SourceRecommendationService._SOURCE_CATEGORY_DEFAULT_BY_CLASS.get(
            template.source_class,
            'secondary_news',
        )

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
    def _classify_page_type(final_url: str, content_type: str, lowered_text: str) -> str:
        if 'application/pdf' in content_type or final_url.lower().endswith('.pdf'):
            return 'pdf_or_report'
        parsed = urlparse(final_url)
        path = (parsed.path or '/').strip().lower()
        query = parse_qs(parsed.query or '')
        path_segments = [segment for segment in path.split('/') if segment]
        has_search_path = any(
            segment in SourceRecommendationService._SEARCH_PATH_SEGMENTS
            or segment.endswith('-search')
            or segment.endswith('_search')
            for segment in path_segments
        )
        has_search_query = any(key in SourceRecommendationService._SEARCH_QUERY_KEYS for key in query.keys())
        if path in {'', '/'} and not query:
            return 'homepage'
        has_search_segment = any(re.search(r'(search|results?)', segment) for segment in path_segments)
        if has_search_path or (has_search_query and (not path_segments or has_search_segment)):
            return 'search_results'
        if any(token in lowered_text for token in ('search results', 'results for', 'showing results')):
            return 'search_results'
        if re.search(r'/(tag|topics?|sections?|category|categories|world|politics|us)/?$', path):
            return 'section_page'
        if re.search(r'/(documents?|report|reports?|record|records|filings?|docket|award|awards)/', path):
            return 'evidence_page'
        if len(path) > 1:
            return 'article'
        return 'unknown'

    @staticmethod
    def _extract_numeric_value(text: str) -> float | None:
        normalized = text.lower().replace(',', '').replace('$', '').strip()
        match = re.search(r'(\d+(?:\.\d+)?)\s*(billion|million|thousand|bn|mn|b|m|k)?\b', normalized)
        if not match:
            return None
        value = float(match.group(1))
        unit = (match.group(2) or '').strip()
        if unit in {'billion', 'bn', 'b'}:
            value *= 1_000_000_000
        elif unit in {'million', 'mn', 'm'}:
            value *= 1_000_000
        elif unit in {'thousand', 'k'}:
            value *= 1_000
        return value

    @staticmethod
    def _extract_claim_amount_value(claim_text: str) -> float | None:
        candidates = re.findall(
            r'\$?\s*\d[\d,]*(?:\.\d+)?\s*(?:billion|million|thousand|bn|mn|b|m|k)?\b',
            claim_text.lower(),
        )
        for candidate in candidates:
            value = SourceRecommendationService._extract_numeric_value(candidate)
            if value is None:
                continue
            has_scale_suffix = bool(re.search(r'(billion|million|thousand|bn|mn|b|m|k)\b', candidate))
            if '$' in candidate or has_scale_suffix or value >= 1_000_000:
                return value
        return None

    @staticmethod
    def _contains_state_reference(state: str, lowered_text: str) -> bool:
        normalized_state = state.strip().lower()
        if not normalized_state:
            return False
        # Two-letter abbreviations need word-boundary checks to avoid false positives
        # such as matching "tx" inside unrelated words.
        if len(normalized_state) == 2:
            if re.search(rf'\b{re.escape(normalized_state)}\b', lowered_text):
                return True
            full_name = SourceRecommendationService._STATE_ABBR_TO_NAME.get(normalized_state.upper())
            if full_name and re.search(rf'\b{re.escape(full_name)}\b', lowered_text):
                return True
            return False
        return re.search(rf'\b{re.escape(normalized_state)}\b', lowered_text) is not None

    @staticmethod
    def _funding_anchor_assessment(
        context: ClaimRecommendationContext,
        lowered_text: str,
        *,
        amount_tolerance_pct: float = 0.05,
    ) -> tuple[list[str], list[str]]:
        matched: list[str] = []
        missing: list[str] = []
        claim = (context.claim_text or '').lower()
        text_no_commas = lowered_text.replace(',', '')

        claim_value = SourceRecommendationService._extract_claim_amount_value(claim)
        amount_ok = False
        if claim_value is not None:
            for candidate in re.findall(r'(\d+(?:\.\d+)?\s*(?:billion|million|thousand|bn|mn|b|m|k)?)', text_no_commas):
                page_value = SourceRecommendationService._extract_numeric_value(candidate)
                if page_value is None:
                    continue
                tolerance = max(1_000_000, claim_value * amount_tolerance_pct)
                if abs(page_value - claim_value) <= tolerance:
                    amount_ok = True
                    break
        if amount_ok:
            matched.append('amount')
        else:
            missing.append('amount')

        if 'operation lone star' in claim:
            if 'operation lone star' in lowered_text:
                matched.append('program')
            else:
                missing.append('program')

        state = (context.candidate_state or '').strip().lower()
        if state:
            if SourceRecommendationService._contains_state_reference(state, lowered_text):
                matched.append('state')
            else:
                missing.append('state')

        if any(token in lowered_text for token in SourceRecommendationService._FUNDING_CONTEXT_PATTERNS):
            matched.append('funding_context')
        else:
            missing.append('funding_context')
        return matched, missing

    @staticmethod
    def _federal_register_item_is_attachable(
        context: ClaimRecommendationContext,
        matched_anchors: list[str],
        missing_anchors: list[str],
    ) -> bool:
        # FR metadata never contains dollar amounts; gate on program + state + funding_context only.
        claim = (context.claim_text or '').lower()
        if 'operation lone star' in claim and 'program' in missing_anchors:
            return False
        context_matches = sum(
            1 for name in ('program', 'state', 'funding_context') if name in matched_anchors
        )
        return context_matches >= SourceRecommendationService._FUNDING_REQUIRED_CONTEXT_ANCHORS

    @staticmethod
    def _funding_anchor_match_is_attachable(context: ClaimRecommendationContext, matched_anchors: list[str], missing_anchors: list[str]) -> bool:
        if 'amount' in missing_anchors:
            return False
        claim = (context.claim_text or '').lower()
        if 'operation lone star' in claim and 'program' in missing_anchors:
            return False
        context_anchor_matches = sum(
            1 for name in ('program', 'state', 'funding_context') if name in matched_anchors
        )
        return context_anchor_matches >= SourceRecommendationService._FUNDING_REQUIRED_CONTEXT_ANCHORS

    @staticmethod
    def _build_usaspending_search_payload(context: ClaimRecommendationContext) -> dict[str, Any]:
        claim = (context.claim_text or '').lower()
        amount = SourceRecommendationService._extract_claim_amount_value(claim)
        keyword_parts: list[str] = [context.candidate_name]
        if context.candidate_state:
            state_name = SourceRecommendationService._STATE_ABBR_TO_NAME.get(context.candidate_state.upper())
            keyword_parts.append(state_name.title() if state_name else context.candidate_state)
        if 'operation lone star' in claim:
            keyword_parts.append('Operation Lone Star')
        if 'reimburs' in claim:
            keyword_parts.append('reimbursement')
        elif 'obligation' in claim:
            keyword_parts.append('obligation')
        else:
            keyword_parts.append('funding')
        keywords = [part for part in keyword_parts if part and len(part.strip()) >= 3]
        if 'grant' in claim or 'grants' in claim or 'reimburs' in claim or 'operation lone star' in claim:
            award_type_codes = list(SourceRecommendationService._USASPENDING_GRANT_AWARD_TYPE_CODES)
        else:
            award_type_codes = list(SourceRecommendationService._USASPENDING_DIRECT_PAYMENT_AWARD_TYPE_CODES)
        filters: dict[str, Any] = {
            'award_type_codes': award_type_codes,
            'keywords': keywords,
        }
        if amount is not None:
            tolerance = amount * 0.4
            filters['award_amount'] = [
                {'lower_bound': max(0, amount - tolerance), 'upper_bound': amount + tolerance}
            ]
        return {
            'fields': [
                'Award ID',
                'generated_internal_id',
                'generated_unique_award_id',
                'Recipient Name',
                'Description',
                'Award Amount',
                'Award Type',
                'Start Date',
                'End Date',
            ],
            'limit': SourceRecommendationService._RESOLVER_RESULT_LIMIT,
            'page': 1,
            'sort': 'Award Amount',
            'order': 'desc',
            'filters': filters,
            'subawards': False,
        }

    @staticmethod
    def _resolve_usaspending_discovery_url(
        url: str,
        context: ClaimRecommendationContext,
    ) -> ResolvedRecommendationResult:
        headers = {'User-Agent': 'civic-fact-audit-source-resolver/1.0'}
        discovery_url = url
        try:
            payload = SourceRecommendationService._build_usaspending_search_payload(context)
            response = httpx.post(
                SourceRecommendationService._USASPENDING_SEARCH_API_URL,
                json=payload,
                timeout=SourceRecommendationService._HTTP_TIMEOUT_SECONDS,
                headers=headers,
            )
            response.raise_for_status()
            data = response.json()
        except (httpx.HTTPError, ValueError):
            return ResolvedRecommendationResult(
                discovery_url=discovery_url,
                evidence_url=None,
                url=discovery_url,
                page_type='search_results',
                recommendation_role='discovery_only',
                validation_note='USAspending search could not be resolved to a specific evidence record.',
                matched_anchors=[],
                missing_anchors=['amount', 'state', 'funding_context'],
            )

        results = data.get('results') if isinstance(data, dict) else None
        if not isinstance(results, list) or not results:
            return ResolvedRecommendationResult(
                discovery_url=discovery_url,
                evidence_url=None,
                url=discovery_url,
                page_type='no_results',
                recommendation_role='discovery_only',
                validation_note='USAspending search returned no candidate records.',
                matched_anchors=[],
                missing_anchors=['amount', 'state', 'funding_context'],
            )

        best_candidate: ResolvedRecommendationResult | None = None
        for item in results[: SourceRecommendationService._RESOLVER_RESULT_LIMIT]:
            if not isinstance(item, dict):
                continue
            item_text = SourceRecommendationService._collapse_whitespace(
                ' '.join(
                    [
                        str(item.get('Description') or ''),
                        str(item.get('Recipient Name') or ''),
                        str(item.get('Award Type') or ''),
                        str(item.get('Award ID') or ''),
                        str(item.get('Award Amount') or ''),
                    ]
                )
            ).lower()
            # Use the same 40% tolerance as the award_amount API filter so items that
            # passed the server-side range check also pass the anchor amount check.
            matched, missing = SourceRecommendationService._funding_anchor_assessment(
                context, item_text, amount_tolerance_pct=0.4
            )
            award_identifier = item.get('generated_internal_id') or item.get('generated_unique_award_id') or item.get('Award ID')
            if not award_identifier:
                continue
            evidence_url = f'https://www.usaspending.gov/award/{award_identifier}'
            attachable = SourceRecommendationService._funding_anchor_match_is_attachable(context, matched, missing)
            result = ResolvedRecommendationResult(
                discovery_url=discovery_url,
                evidence_url=evidence_url if attachable else None,
                url=evidence_url if attachable else discovery_url,
                page_type='evidence_page' if attachable else 'search_results',
                recommendation_role='attachable_evidence' if attachable else 'discovery_only',
                validation_note=(
                    'Actual USAspending award record found with required funding anchors.'
                    if attachable
                    else 'USAspending search could not be resolved to a specific evidence record.'
                ),
                matched_anchors=matched,
                missing_anchors=missing,
            )
            if attachable:
                return result
            if best_candidate is None:
                best_candidate = result

        if best_candidate is not None:
            return best_candidate
        return ResolvedRecommendationResult(
            discovery_url=discovery_url,
            evidence_url=None,
            url=discovery_url,
            page_type='search_results',
            recommendation_role='discovery_only',
            validation_note='USAspending search could not be resolved to a specific evidence record.',
            matched_anchors=[],
            missing_anchors=['amount', 'state', 'funding_context'],
        )

    @staticmethod
    def _resolve_federal_register_discovery_url(
        url: str,
        context: ClaimRecommendationContext,
    ) -> ResolvedRecommendationResult:
        headers = {'User-Agent': 'civic-fact-audit-source-resolver/1.0'}
        discovery_url = url
        query = SourceRecommendationService._build_funding_query(context)
        params = {
            'order': 'newest',
            'per_page': SourceRecommendationService._RESOLVER_RESULT_LIMIT,
            'conditions[term]': query,
        }
        try:
            response = httpx.get(
                SourceRecommendationService._FEDERAL_REGISTER_SEARCH_API_URL,
                params=params,
                timeout=SourceRecommendationService._HTTP_TIMEOUT_SECONDS,
                headers=headers,
            )
            response.raise_for_status()
            data = response.json()
        except (httpx.HTTPError, ValueError):
            return ResolvedRecommendationResult(
                discovery_url=discovery_url,
                evidence_url=None,
                url=discovery_url,
                page_type='search_results',
                recommendation_role='discovery_only',
                validation_note='Federal Register search could not be resolved to a specific evidence document.',
                matched_anchors=[],
                missing_anchors=['amount', 'state', 'funding_context'],
            )

        results = data.get('results') if isinstance(data, dict) else None
        if not isinstance(results, list) or not results:
            return ResolvedRecommendationResult(
                discovery_url=discovery_url,
                evidence_url=None,
                url=discovery_url,
                page_type='no_results',
                recommendation_role='discovery_only',
                validation_note='Federal Register search returned no candidate documents.',
                matched_anchors=[],
                missing_anchors=['amount', 'state', 'funding_context'],
            )

        fallback: ResolvedRecommendationResult | None = None
        for item in results[: SourceRecommendationService._RESOLVER_RESULT_LIMIT]:
            if not isinstance(item, dict):
                continue
            html_url = item.get('html_url')
            if not isinstance(html_url, str) or not html_url:
                continue
            text = SourceRecommendationService._collapse_whitespace(
                ' '.join(
                    [
                        str(item.get('title') or ''),
                        str(item.get('abstract') or ''),
                        str(item.get('type') or ''),
                        str(item.get('agencies') or ''),
                    ]
                )
            ).lower()
            matched, missing = SourceRecommendationService._funding_anchor_assessment(context, text)
            # Amount is intentionally not required for FR items; strip it from the reviewer-facing
            # missing_anchors list so it doesn't appear as a gap in the workbench UI.
            display_missing = [m for m in missing if m != 'amount']
            official_url = item.get('pdf_url')
            attachable = SourceRecommendationService._federal_register_item_is_attachable(context, matched, missing)
            resolved = ResolvedRecommendationResult(
                discovery_url=discovery_url,
                evidence_url=html_url if attachable else None,
                url=html_url if attachable else discovery_url,
                page_type='evidence_page' if attachable else 'search_results',
                recommendation_role='attachable_evidence' if attachable else 'discovery_only',
                validation_note=(
                    'Actual Federal Register document found with required funding anchors.'
                    if attachable
                    else 'Federal Register search could not be resolved to a specific evidence document.'
                ),
                matched_anchors=matched,
                missing_anchors=display_missing,
                official_url=official_url if isinstance(official_url, str) and official_url else None,
            )
            if attachable:
                return resolved
            if fallback is None:
                fallback = resolved

        if fallback is not None:
            return fallback
        return ResolvedRecommendationResult(
            discovery_url=discovery_url,
            evidence_url=None,
            url=discovery_url,
            page_type='search_results',
            recommendation_role='discovery_only',
            validation_note='Federal Register search could not be resolved to a specific evidence document.',
            matched_anchors=[],
            missing_anchors=['amount', 'state', 'funding_context'],
        )

    @staticmethod
    def _resolve_structured_discovery_url(
        *,
        template: SourceRecommendationTemplate,
        url: str,
        context: ClaimRecommendationContext,
        funding_claim: bool,
    ) -> ResolvedRecommendationResult | None:
        if template.template_id == 'tx_senate_congress_primary':
            return SourceRecommendationService._resolve_congress_bill_discovery_url(url, context)
        if not funding_claim:
            return None
        if template.template_id == 'usaspending_primary':
            return SourceRecommendationService._resolve_usaspending_discovery_url(url, context)
        if template.template_id == 'federal_register_primary':
            return SourceRecommendationService._resolve_federal_register_discovery_url(url, context)
        return None

    @staticmethod
    def _parse_explicit_bill_identifiers(claim_text: str) -> list[ParsedBillIdentifier]:
        parsed: list[tuple[int, ParsedBillIdentifier]] = []
        seen: set[tuple[str, int]] = set()
        for pattern, bill_type in SourceRecommendationService._BILL_ID_PATTERNS:
            for match in pattern.finditer(claim_text or ''):
                bill_number = int(match.group(2))
                key = (bill_type, bill_number)
                if key in seen:
                    continue
                seen.add(key)
                parsed.append(
                    (
                        match.start(),
                        ParsedBillIdentifier(
                            original_text=match.group(0).strip(),
                            bill_type=bill_type,
                            bill_number=bill_number,
                        ),
                    )
                )
        parsed.sort(key=lambda item: item[0])
        return [item[1] for item in parsed]

    @staticmethod
    def _extract_explicit_congress_number(claim_text: str) -> int | None:
        match = SourceRecommendationService._CONGRESS_EXPLICIT_PATTERN.search(claim_text or '')
        if match is None:
            return None
        return int(match.group(1))

    @staticmethod
    def _infer_current_congress_number(today: date | None = None) -> int:
        current_year = (today or date.today()).year
        return ((current_year - 1789) // 2) + 1

    @staticmethod
    def _candidate_congress_numbers(claim_text: str) -> list[int]:
        explicit = SourceRecommendationService._extract_explicit_congress_number(claim_text)
        if explicit is not None:
            return [explicit]
        current = SourceRecommendationService._infer_current_congress_number()
        return [current, current - 1]

    @staticmethod
    def _fetch_congress_bill_record(
        *,
        congress_number: int,
        bill_type: str,
        bill_number: int,
    ) -> dict[str, Any] | None:
        api_key = (settings.congress_api_key or '').strip()
        if not api_key:
            return None

        headers = {'User-Agent': 'civic-fact-audit-source-resolver/1.0'}
        params = {'api_key': api_key, 'format': 'json'}
        endpoint = f'{SourceRecommendationService._CONGRESS_BILL_API_BASE_URL}/{congress_number}/{bill_type}/{bill_number}'
        try:
            response = httpx.get(
                endpoint,
                params=params,
                timeout=SourceRecommendationService._HTTP_TIMEOUT_SECONDS,
                headers=headers,
            )
        except httpx.HTTPError:
            return None
        if response.status_code == 404:
            return None
        try:
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError):
            return None
        bill = payload.get('bill') if isinstance(payload, dict) else None
        return bill if isinstance(bill, dict) else None

    @staticmethod
    def _build_congress_bill_url(
        *,
        congress_number: int,
        bill_type: str,
        bill_number: int,
        bill_record: dict[str, Any],
    ) -> str:
        canonical = bill_record.get('url')
        if isinstance(canonical, str) and canonical.startswith('https://www.congress.gov/'):
            return canonical.rstrip('/')
        segment = SourceRecommendationService._BILL_TYPE_SEGMENT.get(bill_type)
        if segment is None:
            segment = bill_type
        return f'https://www.congress.gov/bill/{congress_number}th-congress/{segment}/{bill_number}'

    @staticmethod
    def _resolve_congress_bill_discovery_url(
        url: str,
        context: ClaimRecommendationContext,
    ) -> ResolvedRecommendationResult:
        discovery_url = url
        if not (settings.congress_api_key or '').strip():
            return ResolvedRecommendationResult(
                discovery_url=discovery_url,
                evidence_url=None,
                url=discovery_url,
                page_type='search_results',
                recommendation_role='discovery_only',
                validation_note='Congress.gov API key missing; bill resolver skipped.',
                matched_anchors=[],
                missing_anchors=['api_key'],
            )

        parsed_bill_ids = SourceRecommendationService._parse_explicit_bill_identifiers(context.claim_text)
        if not parsed_bill_ids:
            return ResolvedRecommendationResult(
                discovery_url=discovery_url,
                evidence_url=None,
                url=discovery_url,
                page_type='search_results',
                recommendation_role='discovery_only',
                validation_note='No explicit bill identifier found; Congress.gov link kept as research-only.',
                matched_anchors=[],
                missing_anchors=['explicit_bill_identifier'],
            )

        congress_candidates = SourceRecommendationService._candidate_congress_numbers(context.claim_text)
        successes: list[tuple[ParsedBillIdentifier, int, str]] = []
        for bill_id in parsed_bill_ids:
            for congress_number in congress_candidates:
                record = SourceRecommendationService._fetch_congress_bill_record(
                    congress_number=congress_number,
                    bill_type=bill_id.bill_type,
                    bill_number=bill_id.bill_number,
                )
                if record is None:
                    continue
                evidence_url = SourceRecommendationService._build_congress_bill_url(
                    congress_number=congress_number,
                    bill_type=bill_id.bill_type,
                    bill_number=bill_id.bill_number,
                    bill_record=record,
                )
                successes.append((bill_id, congress_number, evidence_url))

        if not successes:
            return ResolvedRecommendationResult(
                discovery_url=discovery_url,
                evidence_url=None,
                url=discovery_url,
                page_type='search_results',
                recommendation_role='discovery_only',
                validation_note='No matching Congress.gov bill record found.',
                matched_anchors=[],
                missing_anchors=['bill_record'],
            )

        success_keys = {(item[0].bill_type, item[0].bill_number) for item in successes}
        ambiguous = False
        if len(successes) > len(success_keys):
            ambiguous = True
        if len(parsed_bill_ids) > 1 and len(success_keys) != len(parsed_bill_ids):
            ambiguous = True
        if len(successes) > 1:
            first_url = successes[0][2]
            if any(item[2] != first_url for item in successes[1:]):
                ambiguous = True
        if ambiguous:
            return ResolvedRecommendationResult(
                discovery_url=discovery_url,
                evidence_url=None,
                url=discovery_url,
                page_type='search_results',
                recommendation_role='discovery_only',
                validation_note='Multiple possible Congress.gov bill records found; reviewer should inspect manually.',
                matched_anchors=[],
                missing_anchors=['ambiguous_bill_record'],
            )

        bill_id, _, evidence_url = successes[0]
        normalized_anchor = f'{bill_id.bill_type.upper()} {bill_id.bill_number}'
        return ResolvedRecommendationResult(
            discovery_url=discovery_url,
            evidence_url=evidence_url,
            url=evidence_url,
            page_type='article',
            recommendation_role='attachable_evidence',
            validation_note='Resolved official Congress.gov bill record. Reviewer must confirm the bill page supports the claim.',
            matched_anchors=[bill_id.original_text, normalized_anchor],
            missing_anchors=[],
            official_url=None,
        )

    @staticmethod
    def _is_federal_register_access_block_result(
        *,
        template: SourceRecommendationTemplate,
        validation: RecommendationValidationResult,
    ) -> bool:
        if template.template_id != 'federal_register_primary':
            return False
        final_url = (validation.final_url or '').strip().lower()
        if not final_url:
            return False
        host = urlparse(final_url).netloc.lower()
        if host in SourceRecommendationService._FEDERAL_REGISTER_ACCESS_BLOCK_DOMAINS:
            return True
        page_title = (validation.page_title or '').lower()
        if 'request access' in page_title:
            return True
        return False

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
                page_type=SourceRecommendationService._classify_page_type(final_url, content_type, ''),
            )

        html_text = response.text[:SourceRecommendationService._MAX_HTML_SCAN_CHARS]
        collapsed = SourceRecommendationService._collapse_whitespace(re.sub(r'<[^>]+>', ' ', html_text))
        lowered = collapsed.lower()
        page_type = SourceRecommendationService._classify_page_type(final_url, content_type, lowered)
        if any(pattern in lowered for pattern in SourceRecommendationService._EMPTY_RESULT_PATTERNS):
            return RecommendationValidationResult(
                status='no_results',
                http_status=response.status_code,
                final_url=final_url,
                page_title=SourceRecommendationService._extract_title(html_text),
                validation_note='Search page returned no visible results.',
                page_type=page_type,
                evidence_text=lowered,
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
                page_type=page_type,
                evidence_text=lowered,
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
                page_type=page_type,
                evidence_text=lowered,
            )
        note = 'Reachable and topic-aligned.' if overlap > 0 else 'Reachable, but topic alignment is weak.'
        return RecommendationValidationResult(
            status='validated',
            http_status=response.status_code,
            final_url=final_url,
            page_title=SourceRecommendationService._extract_title(html_text),
            topic_overlap_score=overlap,
            validation_note=note,
            page_type=page_type,
            evidence_text=lowered,
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
            if (
                funding_claim
                and template.template_id != 'tx_senate_congress_primary'
                and not template.supports_funding_claims
            ):
                continue
            if (
                not funding_claim
                and template.template_id != 'tx_senate_congress_primary'
                and template.supports_funding_claims
            ):
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
            if normalized_url in seen_urls:
                continue
            if is_social_url(url):
                continue
            if find_partisan_rule_match(publisher=template.publisher, url=url) is not None:
                continue

            resolved = SourceRecommendationService._resolve_structured_discovery_url(
                template=template,
                url=url,
                context=context,
                funding_claim=funding_claim,
            )
            candidate_url = resolved.url if resolved is not None else url

            validation = SourceRecommendationService._validate_recommendation_url(
                candidate_url,
                context,
                require_methodology_signals=numeric_voting_claim and template.requires_methodology_signals,
            )
            if validation.status == 'unreachable':
                continue
            if SourceRecommendationService._is_federal_register_access_block_result(
                template=template,
                validation=validation,
            ):
                continue
            if validation.status == 'no_results' and resolved is None:
                continue
            min_overlap = template.min_topic_overlap
            if (
                resolved is None
                and
                validation.status != 'weak_match'
                and min_overlap is not None
                and validation.topic_overlap_score is not None
                and validation.topic_overlap_score < float(min_overlap)
            ):
                continue

            recommendation_role = resolved.recommendation_role if resolved is not None else 'attachable_evidence'
            validation_note = resolved.validation_note if resolved is not None else validation.validation_note
            page_type = resolved.page_type if resolved is not None else (validation.page_type or 'unknown')
            matched_anchors = list(resolved.matched_anchors) if resolved is not None else []
            missing_anchors = list(resolved.missing_anchors) if resolved is not None else []
            discovery_url = resolved.discovery_url if resolved is not None else url
            evidence_url = resolved.evidence_url if resolved is not None else None
            official_url = resolved.official_url if resolved is not None else None

            if resolved is None:
                if validation.status == 'weak_match':
                    recommendation_role = 'discovery_only'
                if page_type in SourceRecommendationService._NON_ATTACHABLE_PAGE_TYPES:
                    recommendation_role = 'discovery_only'
                    if page_type == 'search_results':
                        validation_note = 'Search page: useful for discovery, not attachable evidence.'
                    elif page_type in {'homepage', 'section_page'}:
                        validation_note = 'Homepage or section page: useful for discovery, not attachable evidence.'

                if funding_claim and page_type not in SourceRecommendationService._NON_ATTACHABLE_PAGE_TYPES:
                    funding_text = (validation.evidence_text or '').lower()
                    matched_anchors, missing_anchors = SourceRecommendationService._funding_anchor_assessment(context, funding_text)
                    if not SourceRecommendationService._funding_anchor_match_is_attachable(context, matched_anchors, missing_anchors):
                        recommendation_role = 'discovery_only'
                        if 'amount' in missing_anchors:
                            validation_note = 'Missing claimed amount.'
                        elif missing_anchors:
                            validation_note = f'Missing funding anchors: {", ".join(missing_anchors)}.'
                    else:
                        evidence_url = candidate_url
            else:
                # For resolver-produced URLs from trusted government databases, JS-rendered pages
                # return sparse HTML and score low on topic overlap. Accept any HTTP 200 without
                # requiring overlap; the resolver's own anchor checks are the evidence gate.
                trusted_resolved = (
                    recommendation_role == 'attachable_evidence'
                    and resolved.evidence_url is not None
                    and SourceRecommendationService._is_resolver_trusted_url(resolved.evidence_url)
                )
                if not trusted_resolved and validation.status == 'weak_match':
                    previous_role = recommendation_role
                    recommendation_role = 'discovery_only'
                    evidence_url = None
                    if previous_role == 'attachable_evidence':
                        if template.template_id == 'tx_senate_congress_primary':
                            validation_note = 'Congress.gov bill record resolved, but evidence page validation failed.'
                        else:
                            validation_note = 'Resolved record did not pass relevance checks; kept as research link.'
                if validation.status == 'no_results':
                    # Award page returned "no results" text — link is broken regardless of trust.
                    recommendation_role = 'discovery_only'
                    evidence_url = None
                    validation_note = 'Resolved record returned no usable results; kept as research link.'
                if (validation.page_type or '') in SourceRecommendationService._NON_ATTACHABLE_PAGE_TYPES:
                    previous_role = recommendation_role
                    recommendation_role = 'discovery_only'
                    evidence_url = None
                    if previous_role == 'attachable_evidence':
                        validation_note = 'Resolved link is not a direct evidence page; kept as research link.'
                # The resolver (USAspending, Federal Register, Congress) already ran its own anchor
                # assessment before setting recommendation_role. Do not re-run the generic funding
                # anchor check here — it uses the wrong thresholds for resolver-sourced records
                # (e.g., FR metadata never contains dollar amounts).

            if (
                template.template_id == 'usaspending_primary'
                and recommendation_role != 'attachable_evidence'
                and not evidence_url
            ):
                # USAspending search links open the advanced-search shell without applying meaningful
                # prefilled filters, so unresolved discovery links are misleading in Workbench.
                continue

            suggestion_url = evidence_url or candidate_url
            normalized_suggestion_url = SourceRecommendationService._normalize_url(suggestion_url)
            if normalized_suggestion_url in existing_urls or normalized_suggestion_url in seen_urls:
                continue
            seen_urls.add(normalized_suggestion_url)
            suggestions.append(
                {
                    'template_id': template.template_id,
                    'source_class': template.source_class,
                    'source_category': SourceRecommendationService._source_category_for_template(template),
                    'source_origin': SourceOrigin.verification,
                    'url': suggestion_url,
                    'publisher': template.publisher,
                    'rationale': template.rationale,
                    'validation_status': validation.status,
                    'http_status': validation.http_status,
                    'final_url': validation.final_url,
                    'page_title': validation.page_title,
                    'topic_overlap_score': validation.topic_overlap_score,
                    'validation_note': validation_note,
                    'page_type': page_type,
                    'recommendation_role': recommendation_role,
                    'discovery_url': discovery_url,
                    'evidence_url': evidence_url,
                    'official_url': official_url,
                    'matched_anchors': matched_anchors,
                    'missing_anchors': missing_anchors,
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
