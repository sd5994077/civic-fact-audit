"""
Create or update a reviewer account by email.

Usage:
    python -m app.scripts.create_reviewer \\
        --email second@local \\
        --password "SecurePass1!" \\
        --name "Second Reviewer" \\
        --role reviewer

Roles: admin | reviewer
"""

from __future__ import annotations

import argparse

from sqlalchemy import func, select

from app.db.database import SessionLocal, get_engine
from app.models.entities import ReviewerUser
from app.services.auth_service import AuthService


def main() -> None:
    parser = argparse.ArgumentParser(description='Create or update a reviewer account.')
    parser.add_argument('--email', required=True)
    parser.add_argument('--password', required=True)
    parser.add_argument('--name', required=True)
    parser.add_argument('--role', default='reviewer', choices=['admin', 'reviewer'])
    args = parser.parse_args()

    get_engine()
    db = SessionLocal()
    try:
        email = args.email.strip().lower()
        password_hash = AuthService.hash_password(args.password)
        existing = db.execute(
            select(ReviewerUser).where(func.lower(ReviewerUser.email) == email)
        ).scalars().first()

        if existing is None:
            reviewer = ReviewerUser(
                email=email,
                display_name=args.name,
                password_hash=password_hash,
                role=args.role,
                is_active=True,
            )
            db.add(reviewer)
            db.commit()
            print(f'Created {args.role}: {email}')
        else:
            existing.display_name = args.name
            existing.password_hash = password_hash
            existing.role = args.role
            existing.is_active = True
            db.commit()
            print(f'Updated {args.role}: {email}')
    finally:
        db.close()


if __name__ == '__main__':
    main()
