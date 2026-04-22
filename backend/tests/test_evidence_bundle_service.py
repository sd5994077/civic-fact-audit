import uuid
from types import SimpleNamespace

from app.models.enums import EvidenceLinkType, SourceClass, SourceOrigin
from app.services.evidence_bundle_service import _build_desired_bundle_links


def test_build_desired_bundle_links_separates_stance_from_verification() -> None:
    statement_id = uuid.uuid4()
    candidate_source_id = uuid.uuid4()
    verification_source_id = uuid.uuid4()
    claim = SimpleNamespace(
        statement=SimpleNamespace(id=statement_id, source_url='https://candidate.example.com/issues'),
        sources=[
            SimpleNamespace(
                id=candidate_source_id,
                url='https://candidate.example.com/platform',
                publisher='Campaign',
                quality_score=0.6,
                source_class=SourceClass.primary,
                source_origin=SourceOrigin.candidate,
            ),
            SimpleNamespace(
                id=verification_source_id,
                url='https://reuters.com/fact-check',
                publisher='Reuters',
                quality_score=0.9,
                source_class=SourceClass.secondary,
                source_origin=SourceOrigin.verification,
            ),
        ],
    )

    links = _build_desired_bundle_links(claim)

    assert [link.link_type for link in links] == [
        EvidenceLinkType.stance,
        EvidenceLinkType.stance,
        EvidenceLinkType.verification,
    ]
    assert links[0].statement_id == statement_id
    assert links[1].source_id == candidate_source_id
    assert links[2].source_id == verification_source_id


def test_build_desired_bundle_links_orders_candidate_and_verification_sources_deterministically() -> None:
    claim = SimpleNamespace(
        statement=SimpleNamespace(id=uuid.uuid4(), source_url='https://candidate.example.com/issues'),
        sources=[
            SimpleNamespace(
                id=uuid.uuid4(),
                url='https://example.com/b',
                publisher='B',
                quality_score=0.5,
                source_class=SourceClass.secondary,
                source_origin=SourceOrigin.verification,
            ),
            SimpleNamespace(
                id=uuid.uuid4(),
                url='https://example.com/a',
                publisher='A',
                quality_score=0.9,
                source_class=SourceClass.primary,
                source_origin=SourceOrigin.verification,
            ),
        ],
    )

    links = _build_desired_bundle_links(claim)

    assert [link.url for link in links] == [
        'https://candidate.example.com/issues',
        'https://example.com/a',
        'https://example.com/b',
    ]
    assert [link.display_order for link in links] == [0, 0, 1]
