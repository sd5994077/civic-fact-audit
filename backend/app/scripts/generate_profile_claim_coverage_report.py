"""
Shared helpers for current-profile published-verified-claim coverage reports.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.entities import Candidate
from app.models.enums import RaceStage
from app.services.evaluation_service import EvaluationService


_VERIFIED_VERDICTS = {'supported', 'mixed', 'unsupported'}


@dataclass(frozen=True)
class CoverageTarget:
    profile_id: str
    label: str
    state: str
    office: str
    election_cycle: int
    race_stages: tuple[RaceStage, ...] | None
    minimum_published_verified_claims: int = 3
    limit: int = 5000


def _load_candidate_names(db: Session, *, target: CoverageTarget) -> list[str]:
    query = select(Candidate.name).where(
        func.lower(Candidate.state) == target.state.lower(),
        func.lower(Candidate.office) == target.office.lower(),
        Candidate.election_cycle == target.election_cycle,
        Candidate.is_active.is_(True),
    )
    if target.race_stages:
        query = query.where(Candidate.race_stage.in_(target.race_stages))
    return sorted({name for name in db.execute(query).scalars().all() if isinstance(name, str) and name.strip()})


def _load_publish_rows(db: Session, *, target: CoverageTarget) -> list[dict[str, object]]:
    stages: list[RaceStage | None] = list(dict.fromkeys(target.race_stages)) if target.race_stages else [None]
    rows: list[dict[str, object]] = []
    seen_claim_ids: set[str] = set()
    for stage in stages:
        stage_rows = EvaluationService.list_publish_queue(
            db,
            state=target.state,
            office=target.office,
            election_cycle=target.election_cycle,
            race_stage=stage,
            include_already_published=True,
            only_gate_passed=False,
            limit=target.limit,
        )
        for row in stage_rows:
            claim_id_text = str(row.get('claim_id', '')).strip()
            if claim_id_text and claim_id_text in seen_claim_ids:
                continue
            if claim_id_text:
                seen_claim_ids.add(claim_id_text)
            rows.append(row)
    return rows


def build_and_print_report(db: Session, *, target: CoverageTarget) -> bool:
    rows = _load_publish_rows(db, target=target)
    candidate_names = _load_candidate_names(db, target=target)
    candidate_keys = {name.casefold(): name for name in candidate_names}

    counts: dict[str, dict[str, int]] = {
        name: {'fact_checkable': 0, 'evaluated_verified': 0, 'published_verified': 0} for name in candidate_names
    }
    for row in rows:
        candidate_name = str(row.get('candidate_name', '')).strip()
        if not candidate_name:
            continue
        normalized_key = candidate_name.casefold()
        canonical_name = candidate_keys.get(normalized_key)
        if canonical_name is None:
            continue
        verdict = str(row.get('latest_verdict') or '').strip().lower()
        counts[canonical_name]['fact_checkable'] += 1
        if verdict in _VERIFIED_VERDICTS:
            counts[canonical_name]['evaluated_verified'] += 1
            if bool(row.get('is_published')):
                counts[canonical_name]['published_verified'] += 1

    race_stages_text = ','.join(stage.value for stage in target.race_stages) if target.race_stages else 'all'

    print(f'Coverage report for {target.label} ({target.profile_id})')
    print(
        f"filters=state:{target.state} office:{target.office} election_cycle:{target.election_cycle} "
        f"race_stages:{race_stages_text} active_only:true"
    )
    print(f'minimum_published_verified_claims={target.minimum_published_verified_claims}')
    print('candidate_coverage:')

    failures: list[str] = []
    for candidate_name in sorted(counts.keys(), key=lambda name: name.lower()):
        candidate_counts = counts[candidate_name]
        published_verified = candidate_counts['published_verified']
        status = 'pass' if published_verified >= target.minimum_published_verified_claims else 'fail'
        if status == 'fail':
            failures.append(candidate_name)
        print(
            f"- candidate={candidate_name} fact_checkable_claims={candidate_counts['fact_checkable']} "
            f"evaluated_verified_claims={candidate_counts['evaluated_verified']} "
            f"published_verified_claims={published_verified} status={status}"
        )

    print(f'candidate_total={len(counts)}')
    print(f'candidate_passed={len(counts) - len(failures)}')
    print(f'candidate_failed={len(failures)}')
    if failures:
        print('failed_candidates:')
        for candidate_name in failures:
            print(f'- {candidate_name}')
        return False
    return True
