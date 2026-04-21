"""
Generate a Texas 2026 evidence queue report.

Reports claims missing required primary/secondary sources for review work allocation.
"""

from __future__ import annotations

from collections import Counter

from app.db.database import SessionLocal, get_engine
from app.models.enums import SourceClass
from app.services.source_service import SourceService


def main() -> None:
    get_engine()
    db = SessionLocal()
    try:
        rows = SourceService.list_evidence_queue(
            db,
            state='TX',
            office='US Senate',
            election_cycle=2026,
            race_stage=None,
            include_only_missing=True,
            limit=1000,
        )
        print(f'Texas 2026 evidence queue items: {len(rows)}')

        by_candidate = Counter(row['candidate_name'] for row in rows)
        missing_primary = sum(1 for row in rows if SourceClass.primary in row['missing_source_classes'])
        missing_secondary = sum(1 for row in rows if SourceClass.secondary in row['missing_source_classes'])

        print(f'Missing primary source: {missing_primary}')
        print(f'Missing secondary source: {missing_secondary}')
        print('Queue by candidate:')
        for name, count in sorted(by_candidate.items(), key=lambda item: (-item[1], item[0].lower())):
            print(f'- {name}: {count}')

        print('Top queue items (up to 25):')
        for row in rows[:25]:
            missing = ','.join(cls.value for cls in row['missing_source_classes']) or 'none'
            print(
                f"- claim_id={row['claim_id']} candidate={row['candidate_name']} "
                f"stage={row['race_stage']} missing={missing} "
                f"published_at={row['statement_published_at'].isoformat()} "
                f"url={row['statement_source_url']}"
            )
    finally:
        db.close()


if __name__ == '__main__':
    main()
