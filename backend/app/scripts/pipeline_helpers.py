"""Shared race-context helpers for the generic ingestion pipeline.

RaceContext captures the filter parameters derived from a registered intake
profile. All functions accept a RaceContext so they can be called from any
pipeline runner (generic or bespoke) and tested without a live database.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.core.intake_profiles import IntakeProfile
from app.models.entities import Candidate, Claim, Statement
from app.models.enums import RaceStage
from app.services.claim_extraction_service import ClaimExtractionService
from app.services.claim_reviewability_service import ClaimReviewabilityService

MAX_CLAIMS_PER_STATEMENT = 5
TX_2026_SENATE_PROFILE_ID = 'tx_2026_senate'
TX_2026_SENATE_STAGES: tuple[RaceStage, ...] = (RaceStage.primary, RaceStage.primary_runoff)


@dataclass(frozen=True)
class RaceContext:
    profile_id: str
    label: str
    state: str
    office: str
    election_cycle: int
    race_stage: RaceStage


def race_context_from_profile(profile: IntakeProfile) -> RaceContext:
    try:
        stage = RaceStage(profile.race_stage)
    except ValueError as exc:
        raise ValueError(
            f"Profile '{profile.profile_id}' has unknown race_stage "
            f"'{profile.race_stage}'. Valid values: {[s.value for s in RaceStage]}"
        ) from exc
    return RaceContext(
        profile_id=profile.profile_id,
        label=profile.label,
        state=profile.state.strip().lower(),
        office=profile.office.strip().lower(),
        election_cycle=profile.election_cycle,
        race_stage=stage,
    )


def candidate_stages_for_context(ctx: RaceContext) -> tuple[RaceStage, ...]:
    if ctx.profile_id == TX_2026_SENATE_PROFILE_ID and ctx.race_stage == RaceStage.primary:
        return TX_2026_SENATE_STAGES
    return (ctx.race_stage,)


def build_candidate_filter(ctx: RaceContext) -> tuple[object, ...]:
    stages = candidate_stages_for_context(ctx)
    return (
        func.lower(Candidate.state) == ctx.state,
        func.lower(Candidate.office) == ctx.office,
        Candidate.election_cycle == ctx.election_cycle,
        Candidate.race_stage.in_(stages) if len(stages) > 1 else Candidate.race_stage == stages[0],
    )


def build_unextracted_statement_query(ctx: RaceContext) -> Select[tuple[uuid.UUID]]:
    claim_counts = (
        select(Claim.statement_id, func.count(Claim.id).label('claim_count'))
        .group_by(Claim.statement_id)
        .subquery()
    )
    return (
        select(Statement.id)
        .join(Candidate, Candidate.id == Statement.candidate_id)
        .outerjoin(claim_counts, claim_counts.c.statement_id == Statement.id)
        .where(
            *build_candidate_filter(ctx),
            func.coalesce(claim_counts.c.claim_count, 0) == 0,
        )
        .order_by(Statement.published_at.asc())
    )


def run_extraction(db: Session, ctx: RaceContext) -> tuple[int, int]:
    statement_ids = db.execute(build_unextracted_statement_query(ctx)).scalars().all()
    extracted_count = 0
    skipped_count = 0

    for statement_id in statement_ids:
        try:
            claims = ClaimExtractionService.extract_claims(
                db,
                statement_id=statement_id,
                max_claims=MAX_CLAIMS_PER_STATEMENT,
            )
            extracted_count += len(claims)
        except AppError as exc:
            skipped_count += 1
            print(f'[SKIP extraction] statement_id={statement_id} code={exc.code}')

    return extracted_count, skipped_count


def run_reviewability_backfill(db: Session, ctx: RaceContext) -> tuple[int, int]:
    claims: list[Claim] = (
        db.execute(
            select(Claim)
            .join(Statement, Statement.id == Claim.statement_id)
            .join(Candidate, Candidate.id == Statement.candidate_id)
            .where(*build_candidate_filter(ctx))
            .order_by(Statement.published_at.asc())
        )
        .scalars()
        .all()
    )

    updated = 0
    flagged_non_fact_checkable = 0

    for claim in claims:
        prior_metadata = ClaimReviewabilityService.parse_metadata(claim.extraction_metadata)
        updated_metadata = ClaimReviewabilityService.build_extraction_metadata(
            provider=prior_metadata.get('provider', 'local'),
            text=claim.claim_text,
            existing_metadata=prior_metadata,
        )
        if claim.extraction_metadata != updated_metadata:
            claim.extraction_metadata = updated_metadata
            updated += 1

        metadata = ClaimReviewabilityService.parse_metadata(claim.extraction_metadata)
        is_fact_checkable = bool(metadata.get('fact_checkable', True))
        claim.fact_checkable = is_fact_checkable
        if not is_fact_checkable:
            flagged_non_fact_checkable += 1

    db.commit()
    return updated, flagged_non_fact_checkable


def build_kpi_snapshot(db: Session, ctx: RaceContext) -> dict[str, int]:
    candidate_filter = build_candidate_filter(ctx)

    candidate_count = db.execute(select(func.count(Candidate.id)).where(*candidate_filter)).scalar_one()
    statement_count = (
        db.execute(
            select(func.count(Statement.id))
            .join(Candidate, Candidate.id == Statement.candidate_id)
            .where(*candidate_filter)
        )
        .scalar_one()
    )
    claim_count = (
        db.execute(
            select(func.count(Claim.id))
            .join(Statement, Statement.id == Claim.statement_id)
            .join(Candidate, Candidate.id == Statement.candidate_id)
            .where(*candidate_filter)
        )
        .scalar_one()
    )
    fact_checkable_count = (
        db.execute(
            select(func.count(Claim.id))
            .join(Statement, Statement.id == Claim.statement_id)
            .join(Candidate, Candidate.id == Statement.candidate_id)
            .where(*candidate_filter, Claim.fact_checkable.is_(True))
        )
        .scalar_one()
    )

    return {
        'candidates': int(candidate_count),
        'statements': int(statement_count),
        'claims': int(claim_count),
        'fact_checkable_claims': int(fact_checkable_count),
    }
