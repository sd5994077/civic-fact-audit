import re
import uuid
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.models.entities import Claim, Statement
from app.models.enums import ClaimStatus


@dataclass
class ProposedClaim:
    text: str
    confidence: float
    issue_tag: str | None


class ClaimExtractionService:
    @staticmethod
    def _heuristic_extract(statement_text: str, max_claims: int) -> list[ProposedClaim]:
        sentence_candidates = re.split(r'(?<=[.!?])\s+', statement_text.strip())
        extracted: list[ProposedClaim] = []
        for sentence in sentence_candidates:
            cleaned = sentence.strip()
            if len(cleaned) < 20:
                continue
            confidence = min(0.95, 0.45 + (min(len(cleaned), 220) / 500))
            extracted.append(ProposedClaim(text=cleaned, confidence=round(confidence, 3), issue_tag=None))
            if len(extracted) >= max_claims:
                break
        return extracted

    @classmethod
    def extract_claims(cls, db: Session, statement_id: uuid.UUID, max_claims: int) -> list[Claim]:
        statement = db.get(Statement, statement_id)
        if statement is None:
            raise AppError('statement_not_found', 'Statement does not exist.', status_code=404)

        proposed_claims = cls._heuristic_extract(statement.statement_text, max_claims)
        if not proposed_claims:
            raise AppError('no_claims_extracted', 'No extractable claims were found in statement text.', status_code=422)

        stored_claims: list[Claim] = []
        for proposed in proposed_claims:
            claim = Claim(
                statement_id=statement.id,
                claim_text=proposed.text,
                issue_tag=proposed.issue_tag,
                extraction_confidence=proposed.confidence,
                extraction_method='heuristic_v1',
                extraction_metadata='{"provider": "local"}',
                status=ClaimStatus.draft,
            )
            db.add(claim)
            stored_claims.append(claim)

        db.commit()
        for claim in stored_claims:
            db.refresh(claim)
        return stored_claims
