import uuid

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.models.entities import Claim, Source
from app.models.enums import SourceClass
from app.schemas.api import AddSourceRequest


class SourceService:
    @staticmethod
    def add_source(db: Session, claim_id: uuid.UUID, payload: AddSourceRequest) -> list[Source]:
        claim = db.get(Claim, claim_id)
        if claim is None:
            raise AppError('claim_not_found', 'Claim does not exist.', status_code=404)

        source = Source(
            claim_id=claim.id,
            url=str(payload.url),
            source_class=payload.source_class,
            publisher=payload.publisher,
            quality_score=payload.quality_score,
        )
        db.add(source)
        try:
            db.commit()
        except IntegrityError as exc:
            db.rollback()
            raise AppError(
                'duplicate_source',
                'This source URL is already attached to the claim.',
                status_code=409,
            ) from exc

        sources = db.scalars(select(Source).where(Source.claim_id == claim.id).order_by(Source.created_at.asc())).all()
        return list(sources)

    @staticmethod
    def has_minimum_evidence(db: Session, claim_id: uuid.UUID) -> bool:
        sources = db.scalars(select(Source.source_class).where(Source.claim_id == claim_id)).all()
        source_set = set(sources)
        return SourceClass.primary in source_set and SourceClass.secondary in source_set
