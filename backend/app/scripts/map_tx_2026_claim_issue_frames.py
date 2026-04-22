"""
Map Texas 2026 U.S. Senate claims into shared issue frames.

Purpose:
- Normalize comparable claims under shared comparison questions.
- Keep mapping idempotent and race-scoped.
- Leave ambiguous or campaign-message claims unmapped instead of forcing weak parity.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.database import SessionLocal, get_engine
from app.models.entities import Candidate, Claim, IssueFrame, Statement
from app.models.enums import RaceStage, SourceClass

TARGET_STATE = 'TX'
TARGET_OFFICE = 'US Senate'
TARGET_ELECTION_CYCLE = 2026
TARGET_STAGES: tuple[RaceStage, ...] = (RaceStage.primary, RaceStage.primary_runoff)


@dataclass(frozen=True)
class IssueFrameDefinition:
    frame_key: str
    title: str
    comparison_question: str
    allowed_candidate_source_classes: tuple[SourceClass, ...]
    allowed_verification_source_classes: tuple[SourceClass, ...]
    issue_tags: tuple[str, ...]
    claim_text_needles: tuple[str, ...] = ()


FRAME_DEFINITIONS: tuple[IssueFrameDefinition, ...] = (
    IssueFrameDefinition(
        frame_key='tx-2026-us-senate-public-education-funding',
        title='Public Education Funding',
        comparison_question='What verifiable record exists for each candidate claim about Texas public-school funding?',
        allowed_candidate_source_classes=(SourceClass.primary,),
        allowed_verification_source_classes=(SourceClass.primary, SourceClass.secondary),
        issue_tags=('Education',),
        claim_text_needles=('public education budget', 'classroom', 'school funding', 'education budget'),
    ),
    IssueFrameDefinition(
        frame_key='tx-2026-us-senate-supreme-court-confirmations',
        title='Supreme Court Confirmation Record',
        comparison_question='What does the public voting record show about each candidate claim on Supreme Court confirmations?',
        allowed_candidate_source_classes=(SourceClass.primary,),
        allowed_verification_source_classes=(SourceClass.primary, SourceClass.secondary),
        issue_tags=('Democracy & Rule of Law',),
        claim_text_needles=('supreme court', 'justices', 'gorsuch', 'kavanaugh', 'amy coney barrett'),
    ),
    IssueFrameDefinition(
        frame_key='tx-2026-us-senate-federal-lawsuit-record',
        title='Federal Lawsuit Record',
        comparison_question='What documented court or attorney-general record supports each candidate claim about lawsuits against a federal administration?',
        allowed_candidate_source_classes=(SourceClass.primary,),
        allowed_verification_source_classes=(SourceClass.primary, SourceClass.secondary),
        issue_tags=('Democracy & Rule of Law',),
        claim_text_needles=('sued the biden administration', 'lawsuit', 'lawsuits', '100 times'),
    ),
    IssueFrameDefinition(
        frame_key='tx-2026-us-senate-border-enforcement-record',
        title='Border Enforcement Record',
        comparison_question='What official and independent evidence supports each candidate claim about border encounters or immigration enforcement?',
        allowed_candidate_source_classes=(SourceClass.primary,),
        allowed_verification_source_classes=(SourceClass.primary, SourceClass.secondary),
        issue_tags=('Border & Immigration',),
        claim_text_needles=('border', 'immigration', 'encounters'),
    ),
    IssueFrameDefinition(
        frame_key='tx-2026-us-senate-inflation-and-costs',
        title='Inflation and Cost of Living',
        comparison_question='What economic data supports each candidate claim about inflation, prices, wages, or household costs?',
        allowed_candidate_source_classes=(SourceClass.primary,),
        allowed_verification_source_classes=(SourceClass.primary, SourceClass.secondary),
        issue_tags=('Economy',),
        claim_text_needles=('inflation', 'prices', 'wages', 'cost of living'),
    ),
    IssueFrameDefinition(
        frame_key='tx-2026-us-senate-drug-pricing-policy',
        title='Drug Pricing Policy',
        comparison_question='What policy and program evidence supports each candidate claim about prescription-drug pricing?',
        allowed_candidate_source_classes=(SourceClass.primary,),
        allowed_verification_source_classes=(SourceClass.primary, SourceClass.secondary),
        issue_tags=('Healthcare',),
        claim_text_needles=('drug prices', 'drug pricing', 'negotiated purchasing'),
    ),
    IssueFrameDefinition(
        frame_key='tx-2026-us-senate-energy-and-gas-prices',
        title='Energy and Gas Prices',
        comparison_question='What market or policy evidence supports each candidate claim about energy policy and gasoline prices?',
        allowed_candidate_source_classes=(SourceClass.primary,),
        allowed_verification_source_classes=(SourceClass.primary, SourceClass.secondary),
        issue_tags=('Energy',),
        claim_text_needles=('gasoline', 'gas prices', 'energy policy', 'oil'),
    ),
    IssueFrameDefinition(
        frame_key='tx-2026-us-senate-foreign-policy-security',
        title='Foreign Policy and Security',
        comparison_question='What documented evidence supports each candidate claim about foreign-policy threats, state actors, or national-security events?',
        allowed_candidate_source_classes=(SourceClass.primary,),
        allowed_verification_source_classes=(SourceClass.primary, SourceClass.secondary),
        issue_tags=('Foreign Policy',),
        claim_text_needles=('iran', 'israel', 'dis-information', 'disinformation'),
    ),
    IssueFrameDefinition(
        frame_key='tx-2026-us-senate-public-safety-record',
        title='Public Safety Record',
        comparison_question='What documented crime, prosecution, or enforcement record supports each candidate public-safety claim?',
        allowed_candidate_source_classes=(SourceClass.primary,),
        allowed_verification_source_classes=(SourceClass.primary, SourceClass.secondary),
        issue_tags=('Public Safety',),
        claim_text_needles=('crime', 'prosecuted', 'convicted', 'justice'),
    ),
    IssueFrameDefinition(
        frame_key='tx-2026-us-senate-election-administration',
        title='Election Administration and Integrity',
        comparison_question='What official election-administration record supports each candidate claim about voting, ballots, or election integrity?',
        allowed_candidate_source_classes=(SourceClass.primary,),
        allowed_verification_source_classes=(SourceClass.primary, SourceClass.secondary),
        issue_tags=('Democracy & Elections',),
        claim_text_needles=('election', 'vote', 'ballot'),
    ),
)


def _normalize_text(text: str | None) -> str:
    return ' '.join((text or '').lower().split())


def _should_map_claim(claim: Claim) -> bool:
    if not claim.fact_checkable:
        return False
    if not claim.issue_tag or claim.issue_tag == 'Campaign Messaging':
        return False
    return True


def _match_frame_definition(issue_tag: str | None, claim_text: str) -> IssueFrameDefinition | None:
    normalized_tag = (issue_tag or '').strip()
    normalized_text = _normalize_text(claim_text)
    if not normalized_tag or normalized_tag == 'Campaign Messaging':
        return None

    specific_matches = [
        frame
        for frame in FRAME_DEFINITIONS
        if normalized_tag in frame.issue_tags and any(needle in normalized_text for needle in frame.claim_text_needles)
    ]
    if specific_matches:
        return specific_matches[0]

    tag_matches = [frame for frame in FRAME_DEFINITIONS if normalized_tag in frame.issue_tags]
    if len(tag_matches) == 1:
        return tag_matches[0]
    return None


def _get_or_create_issue_frame(db: Session, frame_def: IssueFrameDefinition) -> tuple[IssueFrame, bool]:
    existing = db.execute(select(IssueFrame).where(IssueFrame.frame_key == frame_def.frame_key)).scalars().first()
    if existing is not None:
        return existing, False

    issue_frame = IssueFrame(
        frame_key=frame_def.frame_key,
        title=frame_def.title,
        comparison_question=frame_def.comparison_question,
        allowed_candidate_source_classes=list(frame_def.allowed_candidate_source_classes),
        allowed_verification_source_classes=list(frame_def.allowed_verification_source_classes),
        state=TARGET_STATE,
        office=TARGET_OFFICE,
        election_cycle=TARGET_ELECTION_CYCLE,
        race_stage=None,
        is_active=True,
    )
    db.add(issue_frame)
    db.flush()
    return issue_frame, True


def _load_target_claims(db: Session) -> list[Claim]:
    return (
        db.execute(
            select(Claim)
            .join(Statement, Statement.id == Claim.statement_id)
            .join(Candidate, Candidate.id == Statement.candidate_id)
            .where(
                func.lower(Candidate.state) == TARGET_STATE.lower(),
                func.lower(Candidate.office) == TARGET_OFFICE.lower(),
                Candidate.election_cycle == TARGET_ELECTION_CYCLE,
                Candidate.race_stage.in_(TARGET_STAGES),
            )
            .order_by(Statement.published_at.asc(), Claim.created_at.asc())
        )
        .scalars()
        .all()
    )


def run_mapping(db: Session) -> dict[str, int]:
    created_frames = 0
    claims_mapped = 0
    claims_already_mapped = 0
    claims_skipped = 0
    claims_unmapped = 0

    for claim in _load_target_claims(db):
        if not _should_map_claim(claim):
            claims_skipped += 1
            continue

        frame_def = _match_frame_definition(claim.issue_tag, claim.claim_text)
        if frame_def is None:
            claims_unmapped += 1
            continue

        issue_frame, created = _get_or_create_issue_frame(db, frame_def)
        created_frames += int(created)

        if claim.issue_frame_id == issue_frame.id:
            claims_already_mapped += 1
            continue

        claim.issue_frame_id = issue_frame.id
        claims_mapped += 1

    db.commit()
    return {
        'frames_created': created_frames,
        'claims_mapped': claims_mapped,
        'claims_already_mapped': claims_already_mapped,
        'claims_skipped': claims_skipped,
        'claims_unmapped': claims_unmapped,
    }


def main() -> None:
    get_engine()
    db = SessionLocal()
    try:
        stats = run_mapping(db)
        print(
            'Texas 2026 issue-frame mapping complete. '
            f"frames_created={stats['frames_created']} "
            f"claims_mapped={stats['claims_mapped']} "
            f"claims_already_mapped={stats['claims_already_mapped']} "
            f"claims_skipped={stats['claims_skipped']} "
            f"claims_unmapped={stats['claims_unmapped']}"
        )
    finally:
        db.close()


if __name__ == '__main__':
    main()
