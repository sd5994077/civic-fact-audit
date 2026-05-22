from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi.testclient import TestClient

from app.db.database import get_db
from app.main import app
from app.models.enums import RaceStage, Verdict
from app.services.auth_dependency_service import ApiKeyIdentity, require_api_key


class _FakeResult:
    def __init__(self, rows: list[dict]) -> None:
        self._rows = rows

    def mappings(self) -> "_FakeResult":
        return self

    def all(self) -> list[dict]:
        return self._rows

    def first(self) -> dict | None:
        return self._rows[0] if self._rows else None


class _FakeDb:
    def __init__(self, rows: list[dict]) -> None:
        self._rows = rows

    def execute(self, _stmt):  # type: ignore[no-untyped-def]
        return _FakeResult(self._rows)


def _override_api_key() -> ApiKeyIdentity:
    return ApiKeyIdentity(api_key_id=uuid.uuid4(), name='test-key')


def test_public_race_summary_returns_profile_rows() -> None:
    rows = [
        {
            'state': 'TX',
            'office': 'Governor',
            'election_cycle': 2026,
            'race_stage': RaceStage.general,
            'candidate_count': 2,
            'published_claim_count': 12,
            'latest_published_at': datetime(2026, 5, 19, 12, 0, tzinfo=timezone.utc),
        }
    ]

    def _override_db():  # type: ignore[no-untyped-def]
        yield _FakeDb(rows)

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[require_api_key] = _override_api_key
    client = TestClient(app)

    try:
        response = client.get('/v1/public/race-summary?limit=10')
        assert response.status_code == 200
        payload = response.json()
        assert len(payload) == 1
        assert payload[0]['state'] == 'TX'
        assert payload[0]['office'] == 'Governor'
        assert payload[0]['published_claim_count'] == 12
    finally:
        app.dependency_overrides.clear()


def test_get_public_claim_returns_not_found_for_missing_claim() -> None:
    def _override_db():  # type: ignore[no-untyped-def]
        yield _FakeDb([])

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[require_api_key] = _override_api_key
    client = TestClient(app)

    try:
        response = client.get(f'/v1/public/claims/{uuid.uuid4()}')
        assert response.status_code == 404
        assert response.json()['error']['code'] == 'not_found'
    finally:
        app.dependency_overrides.clear()


def test_public_claims_list_maps_rows() -> None:
    rows = [
        {
            'claim_id': str(uuid.uuid4()),
            'claim_text': 'Sample published claim.',
            'issue_tag': 'education',
            'published_at': datetime(2026, 5, 19, 12, 0, tzinfo=timezone.utc),
            'verdict': Verdict.supported,
            'confidence': 0.88,
            'rationale': 'Matches official record.',
            'candidate_id': str(uuid.uuid4()),
            'candidate_name': 'Candidate A',
            'candidate_party': 'Independent',
            'candidate_office': 'Governor',
            'candidate_state': 'TX',
            'election_cycle': 2026,
            'race_stage': RaceStage.general,
            'statement_source_url': 'https://example.com/claim-level-page',
            'statement_published_at': datetime(2026, 5, 18, 12, 0, tzinfo=timezone.utc),
        }
    ]

    def _override_db():  # type: ignore[no-untyped-def]
        yield _FakeDb(rows)

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[require_api_key] = _override_api_key
    client = TestClient(app)

    try:
        response = client.get('/v1/public/claims?state=TX&office=Governor&limit=25')
        assert response.status_code == 200
        payload = response.json()
        assert len(payload) == 1
        assert payload[0]['candidate_name'] == 'Candidate A'
        assert payload[0]['verdict'] == Verdict.supported.value
    finally:
        app.dependency_overrides.clear()

