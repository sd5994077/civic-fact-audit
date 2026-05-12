import uuid

from fastapi.testclient import TestClient

from app.core.errors import AppError
from app.db.database import get_db
from app.main import app
from app.models.enums import SourceClass, SourceOrigin


def _override_db():  # type: ignore[no-untyped-def]
    yield object()


def test_add_source_returns_422_for_policy_violation(monkeypatch) -> None:
    app.dependency_overrides[get_db] = _override_db

    def _fake_add_source(_db, _claim_id, _payload):  # type: ignore[no-untyped-def]
        raise AppError(
            'source_admission_policy_violation',
            'Partisan/advocacy sources cannot be added as verification evidence.',
            status_code=422,
            details={'rejection_field': 'source_origin', 'matched_rule': {'field': 'domain'}},
        )

    monkeypatch.setattr('app.api.v1.claims.SourceService.add_source', _fake_add_source)

    client = TestClient(app)
    response = client.post(
        f'/v1/claims/{uuid.uuid4()}/sources',
        json={
            'url': 'https://www.dailykos.com/stories/example',
            'source_class': SourceClass.secondary.value,
            'source_origin': SourceOrigin.verification.value,
            'publisher': 'Daily Kos',
            'quality_score': 0.5,
            'is_direct_candidate_quote': False,
        },
    )
    assert response.status_code == 422
    body = response.json()
    assert body['error']['code'] == 'source_admission_policy_violation'
    assert body['error']['details']['rejection_field'] == 'source_origin'
    app.dependency_overrides.clear()


def test_add_sources_bulk_returns_mixed_policy_results(monkeypatch) -> None:
    app.dependency_overrides[get_db] = _override_db
    claim_id = uuid.uuid4()

    def _fake_attach_bulk(_db, _payload):  # type: ignore[no-untyped-def]
        return {
            'total': 2,
            'attached': 1,
            'failed': 1,
            'results': [
                {
                    'claim_id': claim_id,
                    'url': 'https://example.gov/record',
                    'source_class': SourceClass.primary,
                    'source_origin': SourceOrigin.verification,
                    'status': 'attached',
                    'error': None,
                },
                {
                    'claim_id': claim_id,
                    'url': 'https://www.dailykos.com/stories/example',
                    'source_class': SourceClass.secondary,
                    'source_origin': SourceOrigin.verification,
                    'status': 'policy_violation',
                    'error': {
                        'code': 'source_admission_policy_violation',
                        'message': 'Partisan/advocacy sources cannot be added as verification evidence.',
                        'details': {'rejection_field': 'source_origin'},
                    },
                },
            ],
        }

    monkeypatch.setattr('app.api.v1.claims.SourceService.attach_sources_bulk', _fake_attach_bulk)

    client = TestClient(app)
    response = client.post(
        '/v1/claims/sources/bulk',
        json=[
            {
                'claim_id': str(claim_id),
                'url': 'https://example.gov/record',
                'source_class': SourceClass.primary.value,
                'source_origin': SourceOrigin.verification.value,
                'quality_score': 0.95,
            },
            {
                'claim_id': str(claim_id),
                'url': 'https://www.dailykos.com/stories/example',
                'source_class': SourceClass.secondary.value,
                'source_origin': SourceOrigin.verification.value,
                'publisher': 'Daily Kos',
                'quality_score': 0.4,
            },
        ],
    )
    assert response.status_code == 200
    body = response.json()
    assert body['total'] == 2
    assert body['attached'] == 1
    assert body['failed'] == 1
    assert body['results'][1]['status'] == 'policy_violation'
    assert body['results'][1]['error']['code'] == 'source_admission_policy_violation'
    app.dependency_overrides.clear()
