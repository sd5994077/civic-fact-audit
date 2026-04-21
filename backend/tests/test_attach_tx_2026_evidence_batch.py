from __future__ import annotations

import uuid

from app.models.enums import SourceClass
from app.scripts import attach_tx_2026_evidence_batch as script


def test_pick_primary_seed_uses_issue_specific() -> None:
    seed = script._pick_primary_seed('Economy')
    assert seed.url == 'https://www.bls.gov/cpi/'


def test_pick_secondary_seed_falls_back_to_generic() -> None:
    seed = script._pick_secondary_seed('NotARealIssue')
    assert seed.url == 'https://www.reuters.com/world/us/'


def test_matching_targeted_seeds_prefers_claim_specific_sources() -> None:
    seeds = script._matching_targeted_seeds(
        'Helped confirm all three of President Trump’s Supreme Court Justices — Neil Gorsuch, Brett Kavanaugh, and Amy Coney Barrett.',
        SourceClass.primary,
    )

    assert len(seeds) == 3
    assert seeds[0].publisher == 'U.S. Senate'


def test_run_attach_pass_attaches_only_missing_sources(monkeypatch) -> None:
    claim_id = uuid.uuid4()
    queue_calls = {'count': 0}
    attached: list[tuple[uuid.UUID, SourceClass, str]] = []

    def fake_list_evidence_queue(*args, **kwargs):  # type: ignore[no-untyped-def]
        queue_calls['count'] += 1
        if queue_calls['count'] == 1:
            return [
                {
                    'claim_id': claim_id,
                    'issue_tag': 'Economy',
                    'claim_text': 'Inflation increased faster than wages.',
                    'missing_source_classes': [SourceClass.primary, SourceClass.secondary],
                }
            ]
        return []

    def fake_add_source(db, claim_id, payload):  # type: ignore[no-untyped-def]
        attached.append((claim_id, payload.source_class, str(payload.url)))
        return []

    monkeypatch.setattr(script.SourceService, 'list_evidence_queue', fake_list_evidence_queue)
    monkeypatch.setattr(script.SourceService, 'add_source', fake_add_source)

    stats = script.run_attach_pass(db=None)  # type: ignore[arg-type]

    assert stats['queue_before'] == 1
    assert stats['queue_after'] == 0
    assert stats['claims_touched'] == 1
    assert stats['primary_attached'] == 1
    assert stats['secondary_attached'] == 1
    assert attached == [
        (claim_id, SourceClass.primary, 'https://www.bls.gov/cpi/'),
        (claim_id, SourceClass.secondary, 'https://www.kff.org/'),
    ]


def test_run_attach_pass_uses_targeted_sources_when_claim_matches(monkeypatch) -> None:
    claim_id = uuid.uuid4()
    queue_calls = {'count': 0}
    attached: list[tuple[uuid.UUID, SourceClass, str]] = []

    def fake_list_evidence_queue(*args, **kwargs):  # type: ignore[no-untyped-def]
        queue_calls['count'] += 1
        if queue_calls['count'] == 1:
            return [
                {
                    'claim_id': claim_id,
                    'issue_tag': 'Campaign Messaging',
                    'claim_text': 'He’s sued the Biden administration over 100 times.',
                    'missing_source_classes': [SourceClass.primary, SourceClass.secondary],
                }
            ]
        return []

    def fake_add_source(db, claim_id, payload):  # type: ignore[no-untyped-def]
        attached.append((claim_id, payload.source_class, str(payload.url)))
        return []

    monkeypatch.setattr(script.SourceService, 'list_evidence_queue', fake_list_evidence_queue)
    monkeypatch.setattr(script.SourceService, 'add_source', fake_add_source)

    stats = script.run_attach_pass(db=None)  # type: ignore[arg-type]

    assert stats['primary_attached'] == 2
    assert stats['secondary_attached'] == 1
    assert attached == [
        (
            claim_id,
            SourceClass.primary,
            'https://www.oag.state.tx.us/news/releases/attorney-general-ken-paxton-files-100th-lawsuit-against-biden-harris-administration',
        ),
        (
            claim_id,
            SourceClass.primary,
            'https://www.texasattorneygeneral.gov/news/releases/attorney-general-ken-paxton-sues-biden-during-administrations-final-hours-stop-unlawful-ban-offshore',
        ),
        (
            claim_id,
            SourceClass.secondary,
            'https://www.dallasnews.com/news/politics/2024/11/12/ag-ken-paxton-files-100th-lawsuit-against-biden-administration/',
        ),
    ]
