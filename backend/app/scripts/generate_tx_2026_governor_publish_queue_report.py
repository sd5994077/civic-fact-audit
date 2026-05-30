"""
Generate a Texas 2026 Governor publish queue diagnostics report.
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
            rows = EvaluationService.list_publish_queue(
                db,
                state='TX',
                office='Governor',
                election_cycle=2026,
                include_already_published=False,
                only_gate_passed=False,
                limit=1000,
            )
        except ProgrammingError as exc:
            message = str(exc).lower()
            if 'claims.is_published' in message:
                print('Database schema is behind model changes. Run: alembic upgrade head')
                return
            raise

        ready = [row for row in rows if row['publish_gate_passed']]
        blocked = [row for row in rows if not row['publish_gate_passed']]

        blocked_reason_counts: Counter[str] = Counter()
        for row in blocked:
            blocked_reason_counts.update(row['publish_gate_failures'])

        print(f'Texas 2026 Governor publish queue items: {len(rows)}')
        print(f'Ready to publish: {len(ready)}')
        print(f'Blocked: {len(blocked)}')
        print('Blocked by reason:')
        for code, count in sorted(blocked_reason_counts.items(), key=lambda item: (-item[1], item[0])):
            print(f'- {code}: {count}')

        print('Top blocked items (up to 25):')
        for row in blocked[:25]:
            print(
                f"- claim_id={row['claim_id']} candidate={row['candidate_name']} "
                f"verdict={row['latest_verdict']} failures={','.join(row['publish_gate_failures'])} "
                f"url={row['statement_source_url']}"
            )
    finally:
        db.close()


if __name__ == '__main__':
    main()
