import hashlib
import secrets
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.models.entities import ApiKey


class ApiKeyService:
    _PREFIX = 'cfa_'

    @staticmethod
    def _hash(plaintext: str) -> str:
        return hashlib.sha256(plaintext.encode()).hexdigest()

    @staticmethod
    def generate() -> tuple[str, str]:
        """Return (plaintext_key, sha256_hex). Caller stores only the hash."""
        plaintext = ApiKeyService._PREFIX + secrets.token_urlsafe(32)
        return plaintext, ApiKeyService._hash(plaintext)

    @staticmethod
    def create_key(db: Session, *, name: str, created_by_reviewer_id: str) -> tuple[ApiKey, str]:
        plaintext, key_hash = ApiKeyService.generate()
        api_key = ApiKey(
            name=name,
            key_hash=key_hash,
            created_by_reviewer_id=created_by_reviewer_id,
        )
        db.add(api_key)
        db.commit()
        db.refresh(api_key)
        return api_key, plaintext

    @staticmethod
    def list_keys(db: Session) -> list[ApiKey]:
        return list(db.execute(select(ApiKey).order_by(ApiKey.created_at.desc())).scalars().all())

    @staticmethod
    def revoke_key(db: Session, *, key_id: uuid.UUID) -> ApiKey:
        api_key = db.get(ApiKey, key_id)
        if api_key is None:
            raise AppError('not_found', 'API key not found.', status_code=404)
        api_key.is_active = False
        db.commit()
        db.refresh(api_key)
        return api_key

    @staticmethod
    def verify_key(db: Session, *, plaintext: str) -> ApiKey | None:
        key_hash = ApiKeyService._hash(plaintext)
        return db.execute(
            select(ApiKey).where(ApiKey.key_hash == key_hash, ApiKey.is_active.is_(True))
        ).scalars().first()

    @staticmethod
    def record_usage(db: Session, *, api_key: ApiKey) -> None:
        try:
            api_key.last_used_at = datetime.now(timezone.utc)
            db.commit()
        except Exception:
            db.rollback()
