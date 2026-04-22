from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.errors import AppError
from app.models.entities import Claim, ClaimEvidenceBundle, ClaimEvidenceLink, Source
from app.models.enums import EvidenceLinkType, SourceOrigin
from app.schemas.api import ClaimEvidenceBundleRead, EvidenceBundleLinkRead


@dataclass(frozen=True)
class _DesiredBundleLink:
    link_type: EvidenceLinkType
    statement_id: uuid.UUID | None
    source_id: uuid.UUID | None
    url: str
    label: str | None
    display_order: int


def _build_bundle_link_read(link: ClaimEvidenceLink) -> EvidenceBundleLinkRead:
    source = link.source
    return EvidenceBundleLinkRead(
        id=link.id,
        bundle_id=link.bundle_id,
        statement_id=link.statement_id,
        source_id=link.source_id,
        url=link.url,
        label=link.label,
        link_type=link.link_type,
        source_class=source.source_class if source is not None else None,
        source_origin=source.source_origin if source is not None else None,
        publisher=source.publisher if source is not None else None,
        quality_score=source.quality_score if source is not None else None,
        display_order=link.display_order,
        created_at=link.created_at,
    )


def _bundle_read(bundle: ClaimEvidenceBundle) -> ClaimEvidenceBundleRead:
    stance_links: list[EvidenceBundleLinkRead] = []
    verification_links: list[EvidenceBundleLinkRead] = []
    for link in bundle.links:
        read_link = _build_bundle_link_read(link)
        if link.link_type == EvidenceLinkType.stance:
            stance_links.append(read_link)
        else:
            verification_links.append(read_link)
    return ClaimEvidenceBundleRead(
        id=bundle.id,
        claim_id=bundle.claim_id,
        is_curated=bundle.is_curated,
        stance_links=stance_links,
        verification_links=verification_links,
    )


def _build_desired_bundle_links(claim: Claim) -> list[_DesiredBundleLink]:
    desired: list[_DesiredBundleLink] = [
        _DesiredBundleLink(
            link_type=EvidenceLinkType.stance,
            statement_id=claim.statement.id,
            source_id=None,
            url=claim.statement.source_url,
            label='Candidate statement',
            display_order=0,
        )
    ]

    candidate_sources = sorted(
        [src for src in claim.sources if src.source_origin == SourceOrigin.candidate],
        key=lambda src: (src.source_class.value, -src.quality_score, src.url),
    )
    verification_sources = sorted(
        [src for src in claim.sources if src.source_origin == SourceOrigin.verification],
        key=lambda src: (src.source_class.value, -src.quality_score, src.url),
    )

    for idx, src in enumerate(candidate_sources, start=1):
        desired.append(
            _DesiredBundleLink(
                link_type=EvidenceLinkType.stance,
                statement_id=None,
                source_id=src.id,
                url=src.url,
                label=src.publisher,
                display_order=idx,
            )
        )

    for idx, src in enumerate(verification_sources):
        desired.append(
            _DesiredBundleLink(
                link_type=EvidenceLinkType.verification,
                statement_id=None,
                source_id=src.id,
                url=src.url,
                label=src.publisher,
                display_order=idx,
            )
        )
    return desired


class EvidenceBundleService:
    @staticmethod
    def sync_claim_bundle(db: Session, claim_id: uuid.UUID, *, commit: bool = True) -> ClaimEvidenceBundleRead:
        claim = (
            db.execute(
                select(Claim)
                .options(
                    selectinload(Claim.statement),
                    selectinload(Claim.sources),
                    selectinload(Claim.evidence_bundle).selectinload(ClaimEvidenceBundle.links).selectinload(ClaimEvidenceLink.source),
                )
                .where(Claim.id == claim_id)
            )
            .scalars()
            .first()
        )
        if claim is None:
            raise AppError('claim_not_found', 'Claim does not exist.', status_code=404)

        bundle = claim.evidence_bundle
        if bundle is None:
            bundle = ClaimEvidenceBundle(claim_id=claim.id, is_curated=False)
            db.add(bundle)
            db.flush()
        elif bundle.is_curated:
            db.refresh(bundle)
            return _bundle_read(bundle)

        desired_links = _build_desired_bundle_links(claim)
        desired_keys = {(item.link_type, item.url) for item in desired_links}
        existing_by_key = {(link.link_type, link.url): link for link in bundle.links}

        for link in list(bundle.links):
            if (link.link_type, link.url) not in desired_keys:
                db.delete(link)

        for desired in desired_links:
            existing = existing_by_key.get((desired.link_type, desired.url))
            if existing is None:
                db.add(
                    ClaimEvidenceLink(
                        bundle_id=bundle.id,
                        statement_id=desired.statement_id,
                        source_id=desired.source_id,
                        url=desired.url,
                        label=desired.label,
                        link_type=desired.link_type,
                        display_order=desired.display_order,
                    )
                )
                continue

            existing.statement_id = desired.statement_id
            existing.source_id = desired.source_id
            existing.label = desired.label
            existing.display_order = desired.display_order

        if commit:
            db.commit()
        else:
            db.flush()
        db.expire_all()
        bundles = EvidenceBundleService.get_bundles_for_claim_ids(db, [claim.id])
        return bundles[claim.id]

    @staticmethod
    def get_bundles_for_claim_ids(db: Session, claim_ids: list[uuid.UUID]) -> dict[uuid.UUID, ClaimEvidenceBundleRead]:
        if not claim_ids:
            return {}
        bundles = (
            db.execute(
                select(ClaimEvidenceBundle)
                .options(selectinload(ClaimEvidenceBundle.links).selectinload(ClaimEvidenceLink.source))
                .where(ClaimEvidenceBundle.claim_id.in_(claim_ids))
            )
            .scalars()
            .all()
        )
        return {bundle.claim_id: _bundle_read(bundle) for bundle in bundles}
