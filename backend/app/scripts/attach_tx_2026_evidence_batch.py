"""
Attach a first-pass evidence set for Texas 2026 U.S. Senate claims.

This script is intentionally conservative:
- It only attaches sources to claims in the TX 2026 US Senate queue.
- It only fills missing source classes (primary and/or secondary).
- It does not assign non-provisional verdicts.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.db.database import SessionLocal, get_engine
from app.models.enums import SourceClass
from app.schemas.api import AddSourceRequest
from app.services.source_service import SourceService


@dataclass(frozen=True)
class SourceSeed:
    url: str
    publisher: str
    quality_score: float


PRIMARY_GENERIC: tuple[SourceSeed, ...] = (
    SourceSeed(url='https://www.congress.gov/', publisher='Congress.gov', quality_score=0.92),
    SourceSeed(url='https://www.fec.gov/', publisher='Federal Election Commission', quality_score=0.9),
)

SECONDARY_GENERIC: tuple[SourceSeed, ...] = (
    SourceSeed(url='https://www.reuters.com/world/us/', publisher='Reuters', quality_score=0.82),
    SourceSeed(url='https://apnews.com/hub/politics', publisher='Associated Press', quality_score=0.8),
)

PRIMARY_BY_ISSUE: dict[str, tuple[SourceSeed, ...]] = {
    'Border & Immigration': (
        SourceSeed(url='https://www.cbp.gov/newsroom/stats', publisher='U.S. Customs and Border Protection', quality_score=0.94),
    ),
    'Economy': (
        SourceSeed(url='https://www.bls.gov/cpi/', publisher='U.S. Bureau of Labor Statistics', quality_score=0.95),
    ),
    'Foreign Policy': (
        SourceSeed(url='https://www.state.gov/', publisher='U.S. Department of State', quality_score=0.9),
    ),
    'Healthcare': (
        SourceSeed(url='https://www.cms.gov/', publisher='Centers for Medicare & Medicaid Services', quality_score=0.92),
    ),
    'Energy': (
        SourceSeed(url='https://www.eia.gov/', publisher='U.S. Energy Information Administration', quality_score=0.93),
    ),
    'Public Safety': (
        SourceSeed(url='https://www.justice.gov/', publisher='U.S. Department of Justice', quality_score=0.91),
    ),
    'Democracy & Elections': (
        SourceSeed(url='https://www.sos.state.tx.us/elections/index.shtml', publisher='Texas Secretary of State', quality_score=0.9),
    ),
}

SECONDARY_BY_ISSUE: dict[str, tuple[SourceSeed, ...]] = {
    'Border & Immigration': (
        SourceSeed(url='https://www.migrationpolicy.org/', publisher='Migration Policy Institute', quality_score=0.78),
    ),
    'Economy': (
        SourceSeed(url='https://www.kff.org/', publisher='KFF', quality_score=0.75),
    ),
    'Foreign Policy': (
        SourceSeed(url='https://www.cfr.org/', publisher='Council on Foreign Relations', quality_score=0.77),
    ),
    'Healthcare': (
        SourceSeed(url='https://www.commonwealthfund.org/', publisher='The Commonwealth Fund', quality_score=0.74),
    ),
    'Energy': (
        SourceSeed(url='https://www.raponline.org/', publisher='Regulatory Assistance Project', quality_score=0.72),
    ),
    'Public Safety': (
        SourceSeed(url='https://www.brennancenter.org/', publisher='Brennan Center for Justice', quality_score=0.73),
    ),
    'Democracy & Elections': (
        SourceSeed(url='https://www.ncsl.org/elections-and-campaigns', publisher='NCSL', quality_score=0.76),
    ),
}

CLAIM_TARGETED_SEEDS: tuple[tuple[str, tuple[SourceSeed, ...], tuple[SourceSeed, ...]], ...] = (
    (
        'public education budget by $5 billion',
        (
            SourceSeed(
                url='https://tea.texas.gov/about-tea/news-and-multimedia/newsletters/tetjuly-2011.pdf',
                publisher='Texas Education Agency',
                quality_score=0.94,
            ),
        ),
        (
            SourceSeed(
                url='https://www.texastribune.org/2015/08/31/texas-schools-still-feeling-2011-budget-cuts/',
                publisher='Texas Tribune',
                quality_score=0.82,
            ),
        ),
    ),
    (
        'all three of President Trump’s Supreme Court Justices',
        (
            SourceSeed(
                url='https://www.senate.gov/legislative/LIS/roll_call_votes/vote1151/vote_115_1_00111.htm',
                publisher='U.S. Senate',
                quality_score=0.95,
            ),
            SourceSeed(
                url='https://www.senate.gov/legislative/LIS/roll_call_votes/vote1152/vote_115_2_00223.htm?congress=115&vote=00223',
                publisher='U.S. Senate',
                quality_score=0.95,
            ),
            SourceSeed(
                url='https://www.senate.gov/legislative/LIS/roll_call_votes/vote1162/vote_116_2_00224.htm',
                publisher='U.S. Senate',
                quality_score=0.95,
            ),
        ),
        (
            SourceSeed(
                url='https://apnews.com/article/5a8e5c4a1a454d53a5f1c1a84d888fff',
                publisher='Associated Press',
                quality_score=0.82,
            ),
        ),
    ),
    (
        'sued the Biden administration over 100 times',
        (
            SourceSeed(
                url='https://www.oag.state.tx.us/news/releases/attorney-general-ken-paxton-files-100th-lawsuit-against-biden-harris-administration',
                publisher='Office of the Texas Attorney General',
                quality_score=0.94,
            ),
            SourceSeed(
                url='https://www.texasattorneygeneral.gov/news/releases/attorney-general-ken-paxton-sues-biden-during-administrations-final-hours-stop-unlawful-ban-offshore',
                publisher='Office of the Texas Attorney General',
                quality_score=0.92,
            ),
        ),
        (
            SourceSeed(
                url='https://www.dallasnews.com/news/politics/2024/11/12/ag-ken-paxton-files-100th-lawsuit-against-biden-administration/',
                publisher='Dallas Morning News',
                quality_score=0.8,
            ),
        ),
    ),
)


def _pick_primary_seed(issue_tag: str | None) -> SourceSeed:
    if issue_tag and issue_tag in PRIMARY_BY_ISSUE:
        return PRIMARY_BY_ISSUE[issue_tag][0]
    return PRIMARY_GENERIC[0]


def _pick_secondary_seed(issue_tag: str | None) -> SourceSeed:
    if issue_tag and issue_tag in SECONDARY_BY_ISSUE:
        return SECONDARY_BY_ISSUE[issue_tag][0]
    return SECONDARY_GENERIC[0]


def _matching_targeted_seeds(claim_text: str, source_class: SourceClass) -> tuple[SourceSeed, ...]:
    lowered = claim_text.lower()
    for needle, primary_seeds, secondary_seeds in CLAIM_TARGETED_SEEDS:
        if needle.lower() in lowered:
            return primary_seeds if source_class == SourceClass.primary else secondary_seeds
    return ()


def _attach_seed(db: Session, claim_id: uuid.UUID, source_class: SourceClass, seed: SourceSeed) -> bool:
    try:
        SourceService.add_source(
            db,
            claim_id=claim_id,
            payload=AddSourceRequest(
                url=seed.url,
                source_class=source_class,
                publisher=seed.publisher,
                quality_score=seed.quality_score,
            ),
        )
        return True
    except AppError as exc:
        if exc.code == 'duplicate_source':
            return False
        raise


def run_attach_pass(db: Session, *, limit: int = 500) -> dict[str, int]:
    queue_items = SourceService.list_evidence_queue(
        db,
        state='TX',
        office='US Senate',
        election_cycle=2026,
        race_stage=None,
        include_only_missing=True,
        limit=limit,
    )

    claims_touched = 0
    primary_attached = 0
    secondary_attached = 0

    for item in queue_items:
        claim_id = item['claim_id']
        issue_tag = item['issue_tag']
        touched = False

        if SourceClass.primary in item['missing_source_classes']:
            primary_seeds = _matching_targeted_seeds(item['claim_text'], SourceClass.primary) or (_pick_primary_seed(issue_tag),)
            for seed in primary_seeds:
                attached = _attach_seed(db, claim_id, SourceClass.primary, seed)
                primary_attached += int(attached)
                touched = touched or attached

        if SourceClass.secondary in item['missing_source_classes']:
            secondary_seeds = _matching_targeted_seeds(item['claim_text'], SourceClass.secondary) or (_pick_secondary_seed(issue_tag),)
            for seed in secondary_seeds:
                attached = _attach_seed(db, claim_id, SourceClass.secondary, seed)
                secondary_attached += int(attached)
                touched = touched or attached

        claims_touched += int(touched)

    remaining = SourceService.list_evidence_queue(
        db,
        state='TX',
        office='US Senate',
        election_cycle=2026,
        race_stage=None,
        include_only_missing=True,
        limit=limit,
    )
    return {
        'queue_before': len(queue_items),
        'claims_touched': claims_touched,
        'primary_attached': primary_attached,
        'secondary_attached': secondary_attached,
        'queue_after': len(remaining),
    }


def main() -> None:
    get_engine()
    db = SessionLocal()
    try:
        stats = run_attach_pass(db)
        print(
            'Texas 2026 evidence attach pass complete. '
            f"queue_before={stats['queue_before']} "
            f"claims_touched={stats['claims_touched']} "
            f"primary_attached={stats['primary_attached']} "
            f"secondary_attached={stats['secondary_attached']} "
            f"queue_after={stats['queue_after']}"
        )
    finally:
        db.close()


if __name__ == '__main__':
    main()
