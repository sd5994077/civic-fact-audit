"""
Generate a source-admission policy impact report.

Outputs:
- Total flagged verification sources
- Flagged source counts by race and candidate
- Claims that newly fail minimum verification evidence after flagged-source exclusion
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

from sqlalchemy import func, select

from app.db.database import SessionLocal, get_engine
from app.models.entities import Candidate, Claim, Source, Statement
from app.models.enums import SourceClass, SourceOrigin


@dataclass
class ClaimEvidenceState:
    candidate_name: str
    state: str | None
    office: str | None
    election_cycle: int | None
    race_stage: str | None
    all_verification_classes: set[SourceClass] = field(default_factory=set)
    eligible_verification_classes: set[SourceClass] = field(default_factory=set)


def main() -> None:
    get_engine()
    db = SessionLocal()
    try:
        total_flagged = (
            db.execute(
                select(func.count(Source.id)).where(
                    Source.source_origin == SourceOrigin.verification,
                    Source.policy_flagged.is_(True),
                )
            )
            .scalar_one()
        )

        flagged_rows = db.execute(
            select(
                Candidate.name,
                Candidate.state,
                Candidate.office,
                Candidate.election_cycle,
                Candidate.race_stage,
                Source.id,
            )
            .join(Statement, Statement.candidate_id == Candidate.id)
            .join(Claim, Claim.statement_id == Statement.id)
            .join(Source, Source.claim_id == Claim.id)
            .where(Source.source_origin == SourceOrigin.verification, Source.policy_flagged.is_(True))
        ).all()

        by_race_candidate: Counter[tuple[str, str | None, str | None, int | None, str | None]] = Counter()
        for row in flagged_rows:
            by_race_candidate[(row.name, row.state, row.office, row.election_cycle, row.race_stage)] += 1

        evidence_rows = db.execute(
            select(
                Claim.id,
                Candidate.name,
                Candidate.state,
                Candidate.office,
                Candidate.election_cycle,
                Candidate.race_stage,
                Source.source_class,
                Source.source_origin,
                Source.policy_flagged,
            )
            .join(Statement, Statement.id == Claim.statement_id)
            .join(Candidate, Candidate.id == Statement.candidate_id)
            .outerjoin(Source, Source.claim_id == Claim.id)
            .where(Claim.fact_checkable.is_(True))
        ).all()

        by_claim: dict[object, ClaimEvidenceState] = {}
        for row in evidence_rows:
            claim_id = row.id
            state = by_claim.get(claim_id)
            if state is None:
                state = ClaimEvidenceState(
                    candidate_name=row.name,
                    state=row.state,
                    office=row.office,
                    election_cycle=row.election_cycle,
                    race_stage=row.race_stage.value if row.race_stage is not None else None,
                )
                by_claim[claim_id] = state

            if row.source_origin != SourceOrigin.verification or row.source_class is None:
                continue
            state.all_verification_classes.add(row.source_class)
            if not row.policy_flagged:
                state.eligible_verification_classes.add(row.source_class)

        newly_failing_claims: list[tuple[object, ClaimEvidenceState]] = []
        for claim_id, claim_state in by_claim.items():
            old_pass = SourceClass.primary in claim_state.all_verification_classes and SourceClass.secondary in claim_state.all_verification_classes
            new_pass = SourceClass.primary in claim_state.eligible_verification_classes and SourceClass.secondary in claim_state.eligible_verification_classes
            if old_pass and not new_pass:
                newly_failing_claims.append((claim_id, claim_state))

        print('Source-admission policy impact report')
        print(f'total_flagged_verification_sources={total_flagged}')
        print('flagged_by_race_candidate:')
        for key, count in sorted(by_race_candidate.items(), key=lambda item: (-item[1], item[0][0].lower())):
            name, race_state, office, cycle, stage = key
            print(f'- candidate={name} state={race_state} office={office} cycle={cycle} stage={stage} flagged_sources={count}')

        print(f'claims_newly_failing_minimum_verification_evidence={len(newly_failing_claims)}')
        for claim_id, claim_state in newly_failing_claims[:100]:
            print(
                f'- claim_id={claim_id} candidate={claim_state.candidate_name} '
                f'state={claim_state.state} office={claim_state.office} cycle={claim_state.election_cycle} stage={claim_state.race_stage}'
            )
    finally:
        db.close()


if __name__ == '__main__':
    main()
