from __future__ import annotations

from sqlalchemy import func, select

from app.db.database import SessionLocal, get_engine
from app.models.entities import Candidate, Claim, Statement


def main() -> None:
    get_engine()
    db = SessionLocal()
    try:
        rows = (
            db.execute(
                select(Candidate.name, Claim.id, Claim.claim_text, Claim.issue_tag, Statement.source_url)
                .join(Statement, Statement.id == Claim.statement_id)
                .join(Candidate, Candidate.id == Statement.candidate_id)
                .where(
                    func.lower(Candidate.state) == 'tx',
                    func.lower(Candidate.office) == 'us senate',
                    Candidate.election_cycle == 2026,
                )
                .order_by(Statement.published_at.desc(), Candidate.name.asc())
            )
            .all()
        )
        for row in rows:
            print(f'{row.name} | {row.id} | issue_tag={row.issue_tag} | url={row.source_url}')
            print(f'  {row.claim_text}')
    finally:
        db.close()


if __name__ == '__main__':
    main()
