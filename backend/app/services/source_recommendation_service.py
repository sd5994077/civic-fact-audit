from __future__ import annotations

import uuid
from dataclasses import dataclass
from urllib.parse import quote_plus

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


class SourceRecommendationService:
    @staticmethod
    def _normalize_url(url: str) -> str:
        return url.strip().rstrip('/').lower()

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
        query = SourceRecommendationService._build_search_query(context)
        query_encoded = quote_plus(query)

        suggestions: list[dict[str, object]] = []
        seen_urls: set[str] = set()
        for template in sorted(policy.templates, key=lambda item: (item.priority, item.template_id)):
            if not SourceRecommendationService._template_matches_context(template, context):
                continue
            if not template.url_template:
                continue
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
            seen_urls.add(normalized_url)
            suggestions.append(
                {
                    'template_id': template.template_id,
                    'source_class': template.source_class,
                    'source_origin': SourceOrigin.verification,
                    'url': url,
                    'publisher': template.publisher,
                    'rationale': template.rationale,
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
