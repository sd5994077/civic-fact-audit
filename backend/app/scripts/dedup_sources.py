"""
Deduplicate source rows that share the same (claim_id, url).

Keeps the oldest row (lowest created_at) and deletes the rest.
Safe to re-run — idempotent.
"""
from __future__ import annotations

from app.db.database import SessionLocal, get_engine
from app.models.entities import Source
from sqlalchemy import text


def main() -> None:
    get_engine()
    db = SessionLocal()
    try:
        dupes = db.execute(text("""
            SELECT claim_id::text, url, array_agg(id::text ORDER BY created_at ASC) AS ids
            FROM sources
            GROUP BY claim_id, url
            HAVING count(*) > 1
        """)).fetchall()

        if not dupes:
            print("No duplicate sources found — nothing to do.")
            return

        deleted = 0
        for row in dupes:
            keep_id, *extra_ids = row.ids
            print(f"claim {row.claim_id[:8]}… url={row.url[:60]}")
            print(f"  keeping {keep_id[:8]}…, removing {len(extra_ids)} duplicate(s)")
            for extra_id in extra_ids:
                source = db.get(Source, extra_id)
                if source:
                    db.delete(source)
                    deleted += 1

        db.commit()
        print(f"\nDone — removed {deleted} duplicate source row(s).")
    finally:
        db.close()


if __name__ == "__main__":
    main()
