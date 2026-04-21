"""
Generate a small adjudication packet for Texas 2026 U.S. Senate claims.

Purpose:
- Pull review-ready claims (minimum evidence attached).
- Select a balanced batch per candidate.
- Print JSON payload templates for manual `POST /v1/claims/{id}/evaluate`.
"""

from __future__ import annotations

import json
from collections import defaultdict
from typing import Any

from sqlalchemy import select

from app.db.database import SessionLocal, get_engine
from app.models.entities import Source
from app.services.evaluation_service import EvaluationService

PER_CANDIDATE_LIMIT = 1


def _select_balanced_batch(rows: list[dict[str, Any]], per_candidate_limit: int) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[str(row['candidate_id'])].append(row)

    selected: list[dict[str, Any]] = []
    for _, items in grouped.items():
        selected.extend(items[:per_candidate_limit])
    return selected


def _load_sources_by_claim(db, claim_ids: list[Any]) -> dict[Any, list[dict[str, Any]]]:
    if not claim_ids:
        return {}
    source_rows = (
        db.execute(
            select(Source)
            .where(Source.claim_id.in_(claim_ids))
            .order_by(Source.claim_id.asc(), Source.source_class.asc(), Source.quality_score.desc())
        )
        .scalars()
        .all()
    )
    by_claim: dict[Any, list[dict[str, Any]]] = defaultdict(list)
    for src in source_rows:
        by_claim[src.claim_id].append(
            {
                'url': src.url,
                'source_class': src.source_class.value,
                'publisher': src.publisher,
                'quality_score': src.quality_score,
            }
        )
    return by_claim


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
        selected = _select_balanced_batch(rows, PER_CANDIDATE_LIMIT)
        claim_ids = [row['claim_id'] for row in selected]
        sources_by_claim = _load_sources_by_claim(db, claim_ids)

        packet = []
        for row in selected:
            packet.append(
                {
                    'claim_id': str(row['claim_id']),
                    'candidate_name': row['candidate_name'],
                    'candidate_party': row['candidate_party'],
                    'race_stage': row['race_stage'].value if row['race_stage'] is not None else None,
                    'issue_tag': row['issue_tag'],
                    'claim_text': row['claim_text'],
                    'statement_source_url': row['statement_source_url'],
                    'statement_published_at': row['statement_published_at'].isoformat(),
                    'sources': sources_by_claim.get(row['claim_id'], []),
                    'latest_verdict': row['latest_verdict'].value if row['latest_verdict'] is not None else None,
                    'evaluate_payload_template': {
                        'verdict': 'supported',
                        'confidence': 0.7,
                        'rationale': 'Human reviewer rationale goes here with concise fact pattern.',
                        'citation_notes': 'Cite which primary and secondary sources support this verdict.',
                    },
                    'evaluate_header_template': {
                        'Authorization': 'Bearer <access_token_from_/v1/auth/login>',
                    },
                }
            )

        print(f'Texas 2026 adjudication packet items: {len(packet)}')
        print(json.dumps(packet, indent=2))
    finally:
        db.close()


if __name__ == '__main__':
    main()
