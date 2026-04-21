"""
Generate a Texas 2026 review queue report.

Lists claims that already meet the minimum evidence threshold and are ready
for human adjudication.
"""

from __future__ import annotations

from collections import Counter

from app.db.database import SessionLocal, get_engine
from app.models.enums import Verdict
from app.services.evaluation_service import EvaluationService


def main() -> None:
    get_engine()
    db = SessionLocal()
    try:
        rows = EvaluationService.list_review_queue(
            db,
            state='TX',
            office='US Senate',
            election_cycle=2026,
            race_stage=None,
            require_minimum_evidence=True,
            limit=1000,
        )
        print(f'Texas 2026 review queue items: {len(rows)}')

        by_candidate = Counter(row['candidate_name'] for row in rows)
        provisional = sum(1 for row in rows if row['latest_verdict'] == Verdict.insufficient)
        unevaluated = sum(1 for row in rows if row['latest_verdict'] is None)

        print(f'Latest verdict still provisional: {provisional}')
        print(f'No evaluation yet: {unevaluated}')
        print('Queue by candidate:')
        for name, count in sorted(by_candidate.items(), key=lambda item: (-item[1], item[0].lower())):
            print(f'- {name}: {count}')

        print('Top review-ready items (up to 25):')
        for row in rows[:25]:
            verdict = row['latest_verdict'].value if row['latest_verdict'] is not None else 'none'
            print(
                f"- claim_id={row['claim_id']} candidate={row['candidate_name']} "
                f"stage={row['race_stage']} verdict={verdict} "
                f"primary={row['primary_source_count']} secondary={row['secondary_source_count']} "
                f"published_at={row['statement_published_at'].isoformat()} "
                f"url={row['statement_source_url']}"
            )
    finally:
        db.close()


if __name__ == '__main__':
    main()
