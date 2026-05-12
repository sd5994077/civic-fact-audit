"""
Backfill source-admission policy flags for legacy verification sources.

This script is non-destructive: it preserves existing source rows and marks
violating legacy verification sources so evidence gates can exclude them.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.source_admission_policy import get_source_admission_policy
from app.db.database import SessionLocal, get_engine
from app.models.entities import Source
from app.models.enums import SourceOrigin
from app.services.source_service import SourceService


def run_backfill(db: Session) -> dict[str, int]:
    policy = get_source_admission_policy()
    rows = db.execute(select(Source).where(Source.source_origin == SourceOrigin.verification)).scalars().all()

    scanned = 0
    newly_flagged = 0
    already_flagged = 0

    for source in rows:
        scanned += 1
        match = SourceService.get_partisan_match(publisher=source.publisher, url=source.url)
        if match is None:
            continue

        if source.policy_flagged:
            already_flagged += 1
            continue

        source.policy_flagged = True
        source.policy_flagged_at = datetime.now(timezone.utc)
        source.policy_flag_reason = json.dumps(
            {
                'code': 'source_admission_policy_violation',
                'policy_version': policy.version,
                'matched_rule': {
                    'field': match.field,
                    'match_type': match.match_type,
                    'pattern': match.pattern,
                    'value': match.value,
                },
                'note': 'Legacy verification source violates source-admission policy and is excluded from verification sufficiency checks.',
            },
            sort_keys=True,
        )
        newly_flagged += 1

    db.commit()
    return {
        'scanned_verification_sources': scanned,
        'newly_flagged': newly_flagged,
        'already_flagged': already_flagged,
        'total_flagged_after_run': newly_flagged + already_flagged,
    }


def main() -> None:
    get_engine()
    db = SessionLocal()
    try:
        summary = run_backfill(db)
        print('Source-admission legacy backfill complete.')
        for key, value in summary.items():
            print(f'{key}={value}')
    finally:
        db.close()


if __name__ == '__main__':
    main()
