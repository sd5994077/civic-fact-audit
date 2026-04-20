"""
Seed an example Texas US Senate comparison dataset.

This is intentionally labeled as an example dataset for UI development and API wiring.
It is not a verified, complete audit of any real-world race.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.database import SessionLocal, get_engine
from app.models.entities import Candidate, Claim, ClaimEvaluation, Source, Statement
from app.models.enums import ClaimStatus, SourceClass, StatementSourceType, Verdict


@dataclass(frozen=True)
class SeedClaim:
    issue_tag: str
    claim_text: str
    statement_source_url: str
    statement_source_type: StatementSourceType
    statement_published_at: datetime
    verdict: Verdict
    confidence: float
    rationale: str
    citation_notes: str
    # Minimum evidence policy: supported/mixed/unsupported require >=1 primary and >=1 secondary.
    sources_primary: list[str]
    sources_secondary: list[str]


def _get_or_create_candidate(db: Session, *, name: str, party: str | None, office: str, state: str) -> Candidate:
    existing = (
        db.execute(
            select(Candidate).where(
                Candidate.name == name,
                Candidate.office == office,
                Candidate.state == state,
            )
        )
        .scalars()
        .first()
    )
    if existing is not None:
        return existing

    candidate = Candidate(name=name, party=party, office=office, state=state)
    db.add(candidate)
    db.commit()
    db.refresh(candidate)
    return candidate


def _insert_statement_with_claim_and_eval(db: Session, *, candidate: Candidate, seed: SeedClaim) -> None:
    stmt = Statement(
        candidate_id=candidate.id,
        source_type=seed.statement_source_type,
        source_url=seed.statement_source_url,
        statement_text=seed.claim_text,
        published_at=seed.statement_published_at,
    )
    db.add(stmt)
    db.flush()

    claim = Claim(
        statement_id=stmt.id,
        claim_text=seed.claim_text,
        issue_tag=seed.issue_tag,
        extraction_confidence=0.9,
        extraction_method='seed',
        extraction_metadata='example_dataset',
        status=ClaimStatus.reviewed,
    )
    db.add(claim)
    db.flush()

    for url in seed.sources_primary:
        db.add(
            Source(
                claim_id=claim.id,
                url=url,
                source_class=SourceClass.primary,
                publisher=None,
                quality_score=0.9,
            )
        )
    for url in seed.sources_secondary:
        db.add(
            Source(
                claim_id=claim.id,
                url=url,
                source_class=SourceClass.secondary,
                publisher=None,
                quality_score=0.8,
            )
        )

    evaluation = ClaimEvaluation(
        claim_id=claim.id,
        verdict=seed.verdict,
        confidence=seed.confidence,
        rationale=seed.rationale,
        citation_notes=seed.citation_notes,
        reviewer_id='seed_tx_us_senate_example',
    )
    db.add(evaluation)
    db.flush()


def main() -> None:
    # Ensure SessionLocal is configured (database engine is lazy).
    get_engine()

    db = SessionLocal()
    try:
        office = 'US Senate'
        state = 'TX'

        # Example candidates for UI wiring only.
        candidate_a = _get_or_create_candidate(db, name='Candidate A (Example)', party='Example', office=office, state=state)
        candidate_b = _get_or_create_candidate(db, name='Candidate B (Example)', party='Example', office=office, state=state)

        published = datetime(2026, 4, 1, 12, 0, tzinfo=timezone.utc)

        # Keep the sources to widely recognized, stable domains. These are placeholders for future curation.
        seeds_a = [
            SeedClaim(
                issue_tag='Democracy & Rule of Law',
                claim_text='January 6 was unlawful; multiple participants were prosecuted and convicted in court.',
                statement_source_url='https://www.congress.gov/',
                statement_source_type=StatementSourceType.speech,
                statement_published_at=published,
                verdict=Verdict.supported,
                confidence=0.7,
                rationale='Court records and DOJ reporting support that prosecutions and convictions occurred.',
                citation_notes='See DOJ summaries and federal court records.',
                sources_primary=['https://www.justice.gov/usao-dc/capitol-breach-cases'],
                sources_secondary=['https://apnews.com/'],
            ),
            SeedClaim(
                issue_tag='Border & Immigration',
                claim_text='Border encounters increased over the last several years; monthly totals vary by year.',
                statement_source_url='https://www.cbp.gov/newsroom/stats',
                statement_source_type=StatementSourceType.interview,
                statement_published_at=published,
                verdict=Verdict.mixed,
                confidence=0.55,
                rationale='Aggregate encounter counts can be sourced, but claims often omit key context and definitions.',
                citation_notes='Use CBP encounter stats; define which encounter series is referenced.',
                sources_primary=['https://www.cbp.gov/newsroom/stats'],
                sources_secondary=['https://www.kff.org/'],
            ),
            SeedClaim(
                issue_tag='Healthcare',
                claim_text='Drug prices can be reduced through negotiated purchasing in certain programs.',
                statement_source_url='https://www.cms.gov/',
                statement_source_type=StatementSourceType.press_release,
                statement_published_at=published,
                verdict=Verdict.insufficient,
                confidence=0.4,
                rationale='The statement is too general to verify without a specific policy scope, program, or benchmark.',
                citation_notes='Needs the specific program and measurable target.',
                sources_primary=[],
                sources_secondary=[],
            ),
        ]

        seeds_b = [
            SeedClaim(
                issue_tag='Democracy & Rule of Law',
                claim_text='January 6 was a peaceful protest and no real crimes were committed.',
                statement_source_url='https://apnews.com/',
                statement_source_type=StatementSourceType.social,
                statement_published_at=published,
                verdict=Verdict.unsupported,
                confidence=0.7,
                rationale='Public court records and reporting contradict the claim that no crimes were committed.',
                citation_notes='Point to convictions and sentencing records.',
                sources_primary=['https://www.justice.gov/usao-dc/capitol-breach-cases'],
                sources_secondary=['https://www.politifact.com/'],
            ),
            SeedClaim(
                issue_tag='Economy',
                claim_text='Inflation was at record highs every month for years.',
                statement_source_url='https://www.bls.gov/cpi/',
                statement_source_type=StatementSourceType.debate,
                statement_published_at=published,
                verdict=Verdict.unsupported,
                confidence=0.6,
                rationale='Inflation levels varied; "record highs every month" is not supported by standard CPI series.',
                citation_notes='Use BLS CPI series and define the comparison window.',
                sources_primary=['https://www.bls.gov/cpi/'],
                sources_secondary=['https://www.reuters.com/'],
            ),
            SeedClaim(
                issue_tag='Energy',
                claim_text='Texas energy policy alone controls national gasoline prices.',
                statement_source_url='https://www.eia.gov/petroleum/gasdiesel/',
                statement_source_type=StatementSourceType.interview,
                statement_published_at=published,
                verdict=Verdict.insufficient,
                confidence=0.45,
                rationale='Gas prices reflect multiple global and domestic factors; this statement needs a defined causal mechanism.',
                citation_notes='Needs a specific causal claim and timeframe.',
                sources_primary=[],
                sources_secondary=[],
            ),
        ]

        for seed in seeds_a:
            _insert_statement_with_claim_and_eval(db, candidate=candidate_a, seed=seed)
        for seed in seeds_b:
            _insert_statement_with_claim_and_eval(db, candidate=candidate_b, seed=seed)

        db.commit()
    finally:
        db.close()


if __name__ == '__main__':
    main()

