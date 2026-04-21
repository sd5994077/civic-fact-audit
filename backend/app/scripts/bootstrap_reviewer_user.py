"""
Create or update a local reviewer account for authenticated adjudication.
"""

from __future__ import annotations

from sqlalchemy import func, select

from app.core.config import settings
from app.db.database import SessionLocal, get_engine
from app.models.entities import ReviewerUser
from app.services.auth_service import AuthService


def main() -> None:
    get_engine()
    db = SessionLocal()
    try:
        email = settings.reviewer_bootstrap_email.strip().lower()
        existing = db.execute(select(ReviewerUser).where(func.lower(ReviewerUser.email) == email)).scalars().first()
        password_hash = AuthService.hash_password(settings.reviewer_bootstrap_password)

        if existing is None:
            reviewer = ReviewerUser(
                email=email,
                display_name=settings.reviewer_bootstrap_name,
                password_hash=password_hash,
                role='reviewer',
                is_active=True,
            )
            db.add(reviewer)
            db.commit()
            print(f'Created reviewer user: {email}')
            return

        existing.display_name = settings.reviewer_bootstrap_name
        existing.password_hash = password_hash
        existing.role = 'reviewer'
        existing.is_active = True
        db.commit()
        print(f'Updated reviewer user: {email}')
    finally:
        db.close()


if __name__ == '__main__':
    main()
