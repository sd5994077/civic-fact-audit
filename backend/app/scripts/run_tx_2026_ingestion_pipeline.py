"""
Run a full Texas 2026 U.S. Senate ingestion refresh pipeline.
"""

from __future__ import annotations

from app.db.database import SessionLocal, get_engine
from app.scripts.backfill_tx_2026_claim_reviewability import run_backfill
from app.scripts.extract_tx_2026_claims_batch import run_extraction
from app.scripts.generate_tx_2026_ingestion_kpi_report import build_kpi_snapshot
from app.scripts.ingest_tx_2026_statement_batch import SEEDS as ROUND1_SEEDS
from app.scripts.ingest_tx_2026_statement_batch import ingest_batch
from app.scripts.ingest_tx_2026_statement_batch_round2 import SEEDS as ROUND2_SEEDS
from app.scripts.ingest_tx_2026_statement_batch_round3 import SEEDS as ROUND3_SEEDS
from app.scripts.map_tx_2026_claim_issue_frames import run_mapping


def main() -> None:
    get_engine()
    db = SessionLocal()
    try:
        before = build_kpi_snapshot(db)
        created1, missing1, dup1 = ingest_batch(db, ROUND1_SEEDS)
        created2, missing2, dup2 = ingest_batch(db, ROUND2_SEEDS)
        created3, missing3, dup3 = ingest_batch(db, ROUND3_SEEDS)
        extracted_claims, skipped_statements = run_extraction(db)
        metadata_updated, non_fact_checkable = run_backfill(db)
        mapping_stats = run_mapping(db)
        after = build_kpi_snapshot(db)

        print('Texas 2026 ingestion refresh complete.')
        print(
            'statement_ingest: '
            f'created={created1 + created2 + created3} '
            f'missing_candidate={missing1 + missing2 + missing3} '
            f'duplicate={dup1 + dup2 + dup3}'
        )
        print(f'claim_extraction: claims_created={extracted_claims} statements_skipped={skipped_statements}')
        print(f'reviewability_backfill: metadata_updated={metadata_updated} non_fact_checkable={non_fact_checkable}')
        print(
            'issue_frame_mapping: '
            f"mapped={mapping_stats['claims_mapped']} "
            f"already_mapped={mapping_stats['claims_already_mapped']} "
            f"unmapped={mapping_stats['claims_unmapped']}"
        )
        print(f'kpi_before={before}')
        print(f'kpi_after={after}')
    finally:
        db.close()


if __name__ == '__main__':
    main()
