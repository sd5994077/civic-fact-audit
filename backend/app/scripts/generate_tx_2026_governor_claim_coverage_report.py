"""
Generate published-verified-claim coverage report for Texas 2026 Governor profile.

Pass condition:
- every candidate has at least 3 published verified claims
"""

from __future__ import annotations

from app.db.database import SessionLocal, get_engine
from app.models.enums import RaceStage
from app.scripts.generate_profile_claim_coverage_report import CoverageTarget, build_and_print_report


def main() -> None:
    get_engine()
    db = SessionLocal()
    try:
        passed = build_and_print_report(
            db,
            target=CoverageTarget(
                profile_id='tx_2026_governor',
                label='Texas 2026 Governor',
                state='TX',
                office='Governor',
                election_cycle=2026,
                race_stages=(RaceStage.general,),
                minimum_published_verified_claims=3,
            ),
        )
    finally:
        db.close()

    if not passed:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
