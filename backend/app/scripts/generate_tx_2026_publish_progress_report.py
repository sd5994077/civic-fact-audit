"""
Generate Texas 2026 claim publish progress KPIs.
"""

from __future__ import annotations

from collections import Counter

from sqlalchemy.exc import ProgrammingError

from app.db.database import SessionLocal, get_engine
from app.services.evaluation_service import EvaluationService


def main() -> None:
    get_engine()
    db = SessionLocal()
    try:
        try:
            unpublished_rows = EvaluationService.list_publish_queue(
                db,
                state='TX',
                office='US Senate',
                election_cycle=2026,
                include_already_published=False,
                only_gate_passed=False,
                limit=5000,
            )
            all_rows = EvaluationService.list_publish_queue(
                db,
                state='TX',
                office='US Senate',
                election_cycle=2026,
                include_already_published=True,
                only_gate_passed=False,
                limit=5000,
            )
        except ProgrammingError as exc:
            message = str(exc).lower()
            if 'claims.is_published' in message:
                print('Database schema is behind model changes. Run: alembic upgrade head')
                return
            raise

        published = [row for row in all_rows if row['is_published']]
        ready_unpublished = [row for row in unpublished_rows if row['publish_gate_passed']]
        blocked_unpublished = [row for row in unpublished_rows if not row['publish_gate_passed']]

        blocked_reason_counts: Counter[str] = Counter()
        for row in blocked_unpublished:
            blocked_reason_counts.update(row['publish_gate_failures'])

        total = len(all_rows)
        published_count = len(published)
        published_pct = (published_count / total * 100.0) if total else 0.0

        print('Texas 2026 publish progress KPIs')
        print(f'total_fact_checkable_claims={total}')
        print(f'published_claims={published_count}')
        print(f'published_percent={published_pct:.1f}')
        print(f'ready_unpublished_claims={len(ready_unpublished)}')
        print(f'blocked_unpublished_claims={len(blocked_unpublished)}')
        print('blocked_by_reason:')
        for code, count in sorted(blocked_reason_counts.items(), key=lambda item: (-item[1], item[0])):
            print(f'- {code}: {count}')
    finally:
        db.close()


if __name__ == '__main__':
    main()
