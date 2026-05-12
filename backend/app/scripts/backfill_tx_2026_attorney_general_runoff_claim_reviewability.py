"""
Backfill reviewability metadata for Texas 2026 Attorney General runoff claims.

Purpose:
- Mark clearly specific, checkable policy commitments as fact-checkable.
- Keep broad rhetoric out of evidence/review/compare workflows.
"""

from __future__ import annotations

import json
import re

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.database import SessionLocal, get_engine
from app.models.entities import Candidate, Claim, Statement
from app.models.enums import RaceStage
from app.services.claim_reviewability_service import ClaimReviewabilityService


def _load_target_claims(db: Session) -> list[Claim]:
    return (
        db.execute(
            select(Claim)
            .join(Statement, Statement.id == Claim.statement_id)
            .join(Candidate, Candidate.id == Statement.candidate_id)
            .where(
                func.lower(Candidate.state) == 'tx',
                func.lower(Candidate.office) == 'attorney general',
                Candidate.election_cycle == 2026,
                Candidate.race_stage == RaceStage.primary_runoff,
            )
            .order_by(Statement.published_at.asc())
        )
        .scalars()
        .all()
    )


def _is_specific_policy_commitment(text: str) -> bool:
    normalized = text.lower()
    normalized_tokens = re.sub(r'[^a-z0-9]+', ' ', normalized).strip()
    quarterly_contract_report = (
        'quarterly' in normalized_tokens
        and 'outside counsel' in normalized_tokens
        and 'contract amount' in normalized_tokens
        and 'case matter' in normalized_tokens
    )
    pia_sla_metrics = (
        'public information act' in normalized_tokens
        and 'five business days' in normalized_tokens
        and 'monthly' in normalized_tokens
        and 'dashboard' in normalized_tokens
    )
    monthly_opinion_backlog_report = (
        'monthly' in normalized_tokens
        and 'backlog report' in normalized_tokens
        and 'opinion' in normalized_tokens
        and 'request' in normalized_tokens
    )
    quarterly_consumer_protection_totals = (
        'quarterly' in normalized_tokens
        and 'consumer protection' in normalized_tokens
        and 'restitution' in normalized_tokens
    )
    quarterly_election_referral_stats = (
        'quarterly' in normalized_tokens
        and 'election fraud' in normalized_tokens
        and 'referral' in normalized_tokens
        and 'disposition' in normalized_tokens
    )
    monthly_agency_pia_metrics = (
        'monthly' in normalized_tokens
        and 'public information act' in normalized_tokens
        and 'response time metrics' in normalized_tokens
        and 'agency' in normalized_tokens
    )
    return (
        quarterly_contract_report
        or pia_sla_metrics
        or monthly_opinion_backlog_report
        or quarterly_consumer_protection_totals
        or quarterly_election_referral_stats
        or monthly_agency_pia_metrics
    )


def run_backfill(db: Session) -> tuple[int, int]:
    claims = _load_target_claims(db)
    updated = 0
    fact_checkable_count = 0

    for claim in claims:
        prior_metadata = ClaimReviewabilityService.parse_metadata(claim.extraction_metadata)
        fact_checkable = _is_specific_policy_commitment(claim.claim_text)
        metadata = {
            **prior_metadata,
            'fact_checkable': fact_checkable,
            'reviewability_override': 'tx_2026_attorney_general_runoff_policy_specificity_v1',
        }
        updated_metadata = json.dumps(metadata, separators=(',', ':'), sort_keys=True)
        if claim.extraction_metadata != updated_metadata:
            claim.extraction_metadata = updated_metadata
            updated += 1
        claim.fact_checkable = fact_checkable
        if fact_checkable:
            fact_checkable_count += 1

    db.commit()
    return updated, fact_checkable_count


def main() -> None:
    get_engine()
    db = SessionLocal()
    try:
        updated, fact_checkable_count = run_backfill(db)
        print(
            'Texas 2026 Attorney General runoff reviewability backfill complete. '
            f'claims_updated={updated} fact_checkable={fact_checkable_count}'
        )
    finally:
        db.close()


if __name__ == '__main__':
    main()
