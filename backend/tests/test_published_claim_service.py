import uuid
from datetime import datetime, timezone

from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session

from app.db.database import Base
from app.models.entities import Candidate, Claim, ClaimEvaluation, Source, Statement
from app.models.enums import RaceStage, StatementSourceType
from app.services.published_claim_service import PublishedClaimService


def test_published_claims_paginates_all_claims_and_excludes_drafts() -> None:
    engine = create_engine('sqlite://')
    @event.listens_for(engine, 'connect')
    def configure_sqlite(connection, _record) -> None:
        # PostgreSQL's full-text index is irrelevant to this pagination test.
        connection.create_function('to_tsvector', 2, lambda language, text: text, deterministic=True)
    Base.metadata.create_all(engine, tables=[model.__table__ for model in (Candidate, Statement, Claim, ClaimEvaluation, Source)])
    with Session(engine) as db:
        candidate = Candidate(id=uuid.uuid4(), name='Candidate A', party='Independent',
                              state='TX', office='US Senate', election_cycle=2026, race_stage=RaceStage.general)
        db.add(candidate)
        statement = Statement(id=uuid.uuid4(), candidate_id=candidate.id,
                              source_type=StatementSourceType.speech, source_url='https://example.com/statement',
                              statement_text='Record', published_at=datetime.now(timezone.utc))
        db.add(statement)
        db.flush()
        for number in range(13):
            db.add(Claim(id=uuid.uuid4(), statement_id=statement.id, claim_text=f'Claim {number}',
                         issue_tag=f'issue-{number % 11}', extraction_confidence=0.9,
                         fact_checkable=True, is_published=number < 12,
                         published_at=datetime.now(timezone.utc) if number < 12 else None))
        db.commit()
        kwargs = dict(state='TX', office='US Senate', election_cycle=2026, race_stage=RaceStage.general, limit=5)
        pages = [PublishedClaimService.list_claims(db, offset=offset, **kwargs) for offset in (0, 5, 10)]
        claims = [claim for page in pages for claim in page]
        assert [len(page) for page in pages] == [5, 5, 2]
        assert len({claim.claim_id for claim in claims}) == 12
        assert len({claim.issue_tag for claim in claims}) == 11
        assert 'Claim 12' not in [claim.claim_text for claim in claims]
