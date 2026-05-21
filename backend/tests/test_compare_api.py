from datetime import datetime, timezone
import uuid

from fastapi.testclient import TestClient

from app.db.database import get_db
from app.main import app
from app.models.enums import RaceStage
from app.schemas.api import CandidatePublicRead, CompareRaceMeta, CompareResponse


def _override_db():  # type: ignore[no-untyped-def]
    yield object()


def test_compare_export_json_includes_disclaimer(monkeypatch) -> None:
    candidate = CandidatePublicRead(
        id=uuid.uuid4(),
        name='Candidate A',
        party='Independent',
        office='US Senate',
        state='TX',
        election_cycle=2026,
        race_stage=RaceStage.primary,
        created_at=datetime(2026, 5, 1, tzinfo=timezone.utc),
    )
    payload = CompareResponse(
        race=CompareRaceMeta(
            state='TX',
            office='US Senate',
            election_cycle=2026,
            race_stage=RaceStage.primary,
            as_of=datetime(2026, 5, 1, tzinfo=timezone.utc),
            disclaimer='This comparison is evidence-traceable, not an endorsement or voting recommendation.',
        ),
        candidates=[candidate],
        issues=[],
    )

    def _fake_compare_office_state(**_kwargs):  # type: ignore[no-untyped-def]
        return payload

    monkeypatch.setattr('app.api.v1.compare.ComparisonService.compare_office_state', _fake_compare_office_state)
    app.dependency_overrides[get_db] = _override_db

    client = TestClient(app)
    response = client.get('/v1/compare/export?state=TX&office=US%20Senate&format=json')
    body = response.json()
    assert response.status_code == 200
    assert 'voting recommendation' in body['disclaimer'].lower()
    app.dependency_overrides.clear()


def test_compare_stage_alias_maps_to_race_stage(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def _fake_compare_office_state(**kwargs):  # type: ignore[no-untyped-def]
        captured.update(kwargs)
        candidate = CandidatePublicRead(
            id=uuid.uuid4(),
            name='Candidate A',
            party='Independent',
            office='US Senate',
            state='TX',
            election_cycle=2026,
            race_stage=RaceStage.primary_runoff,
            created_at=datetime(2026, 5, 1, tzinfo=timezone.utc),
        )
        return CompareResponse(
            race=CompareRaceMeta(
                state='TX',
                office='US Senate',
                election_cycle=2026,
                race_stage=RaceStage.primary_runoff,
                as_of=datetime(2026, 5, 1, tzinfo=timezone.utc),
                disclaimer='This comparison is evidence-traceable, not an endorsement or voting recommendation.',
            ),
            candidates=[candidate],
            issues=[],
        )

    monkeypatch.setattr('app.api.v1.compare.ComparisonService.compare_office_state', _fake_compare_office_state)
    app.dependency_overrides[get_db] = _override_db

    client = TestClient(app)
    response = client.get('/v1/compare?state=TX&office=US%20Senate&election_cycle=2026&stage=primary_runoff')
    assert response.status_code == 200
    assert captured['race_stage'] == RaceStage.primary_runoff
    app.dependency_overrides.clear()
