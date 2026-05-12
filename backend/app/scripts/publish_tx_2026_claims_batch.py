"""
Publish eligible Texas 2026 U.S. Senate claims in batch.

Usage:
- Dry run (default): python -m app.scripts.publish_tx_2026_claims_batch
- Apply changes:      python -m app.scripts.publish_tx_2026_claims_batch --apply --approver reviewer@local
"""

from __future__ import annotations

import argparse

from sqlalchemy.exc import ProgrammingError

from app.db.database import SessionLocal, get_engine
from app.services.evaluation_service import EvaluationService


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Publish eligible Texas 2026 claims in batch.')
    parser.add_argument('--apply', action='store_true', help='Apply publishes. Without this flag, only report eligibility.')
    parser.add_argument('--approver', default='tx_2026_admin_batch', help='Approver id used for publish attribution.')
    parser.add_argument('--limit', type=int, default=1000, help='Max rows to inspect in publish queue.')
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    get_engine()
    db = SessionLocal()
    try:
        try:
            rows = EvaluationService.list_publish_queue(
                db,
                state='TX',
                office='US Senate',
                election_cycle=2026,
                include_already_published=False,
                only_gate_passed=False,
                limit=max(1, args.limit),
            )
        except ProgrammingError as exc:
            message = str(exc).lower()
            if 'claims.is_published' in message:
                print('Database schema is behind model changes. Run: alembic upgrade head')
                return
            raise
        eligible = [row for row in rows if row['publish_gate_passed']]
        blocked = [row for row in rows if not row['publish_gate_passed']]
        print(f'publish_queue_total={len(rows)} eligible={len(eligible)} blocked={len(blocked)} apply={args.apply}')
        for row in blocked[:25]:
            print(f"blocked claim_id={row['claim_id']} failures={','.join(row['publish_gate_failures'])}")
        if not args.apply:
            return

        published = 0
        for row in eligible:
            EvaluationService.publish_claim(db, row['claim_id'], approver_id=args.approver)
            published += 1
        print(f'published={published}')
    finally:
        db.close()


if __name__ == '__main__':
    main()
