"""Tests for ApiKeyService and require_api_key dependency."""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

import pytest

from app.core.errors import AppError
from app.services.api_key_service import ApiKeyService


class TestApiKeyGenerate:
    def test_plaintext_starts_with_prefix(self) -> None:
        plaintext, _ = ApiKeyService.generate()
        assert plaintext.startswith('cfa_')

    def test_hash_is_64_hex_chars(self) -> None:
        _, key_hash = ApiKeyService.generate()
        assert len(key_hash) == 64
        assert all(c in '0123456789abcdef' for c in key_hash)

    def test_two_calls_produce_different_keys(self) -> None:
        p1, h1 = ApiKeyService.generate()
        p2, h2 = ApiKeyService.generate()
        assert p1 != p2
        assert h1 != h2

    def test_hash_is_deterministic_for_same_plaintext(self) -> None:
        p, h = ApiKeyService.generate()
        assert ApiKeyService._hash(p) == h


class TestApiKeyCreate:
    def test_create_key_returns_active_key_and_plaintext(self) -> None:
        db = MagicMock()
        db.refresh = lambda obj: setattr(obj, '_refreshed', True)

        with patch.object(ApiKeyService, 'generate', return_value=('cfa_test', 'abc123')):
            api_key, plaintext = ApiKeyService.create_key(
                db, name='Test Key', created_by_reviewer_id='reviewer@local'
            )

        assert plaintext == 'cfa_test'
        assert api_key.key_hash == 'abc123'
        assert api_key.name == 'Test Key'
        db.add.assert_called_once()
        db.commit.assert_called_once()


class TestApiKeyVerify:
    def _make_active_key(self) -> MagicMock:
        key = MagicMock()
        key.is_active = True
        return key

    def test_verify_returns_key_for_valid_plaintext(self) -> None:
        db = MagicMock()
        plaintext = 'cfa_validkey'
        mock_key = self._make_active_key()
        db.execute.return_value.scalars.return_value.first.return_value = mock_key

        result = ApiKeyService.verify_key(db, plaintext=plaintext)

        assert result is mock_key
        call_args = db.execute.call_args
        assert call_args is not None

    def test_verify_returns_none_for_unknown_key(self) -> None:
        db = MagicMock()
        db.execute.return_value.scalars.return_value.first.return_value = None
        assert ApiKeyService.verify_key(db, plaintext='cfa_unknown') is None


class TestApiKeyRevoke:
    def test_revoke_deactivates_key(self) -> None:
        key_id = uuid.uuid4()
        mock_key = MagicMock()
        mock_key.is_active = True
        db = MagicMock()
        db.get.return_value = mock_key

        result = ApiKeyService.revoke_key(db, key_id=key_id)

        assert result.is_active is False
        db.commit.assert_called_once()

    def test_revoke_raises_not_found_for_missing_key(self) -> None:
        db = MagicMock()
        db.get.return_value = None
        with pytest.raises(AppError) as exc_info:
            ApiKeyService.revoke_key(db, key_id=uuid.uuid4())
        assert exc_info.value.status_code == 404
        assert exc_info.value.code == 'not_found'


class TestApiKeyRecordUsage:
    def test_record_usage_commits_last_used_at(self) -> None:
        db = MagicMock()
        api_key = MagicMock()
        ApiKeyService.record_usage(db, api_key=api_key)
        assert api_key.last_used_at is not None
        db.commit.assert_called_once()

    def test_record_usage_rolls_back_on_error(self) -> None:
        db = MagicMock()
        db.commit.side_effect = Exception('db error')
        api_key = MagicMock()
        ApiKeyService.record_usage(db, api_key=api_key)
        db.rollback.assert_called_once()


class TestRequireApiKey:
    def test_missing_header_raises_401(self) -> None:
        from app.services.auth_dependency_service import require_api_key
        db = MagicMock()
        with pytest.raises(AppError) as exc_info:
            require_api_key(x_api_key=None, db=db)
        assert exc_info.value.status_code == 401
        assert exc_info.value.code == 'api_key_required'

    def test_invalid_key_raises_401(self) -> None:
        from app.services.auth_dependency_service import require_api_key
        db = MagicMock()
        with patch('app.services.api_key_service.ApiKeyService.verify_key', return_value=None):
            with pytest.raises(AppError) as exc_info:
                require_api_key(x_api_key='cfa_bad', db=db)
        assert exc_info.value.status_code == 401
        assert exc_info.value.code == 'invalid_api_key'

    def test_valid_key_returns_identity(self) -> None:
        from app.services.auth_dependency_service import ApiKeyIdentity, require_api_key
        db = MagicMock()
        key_id = uuid.uuid4()
        mock_key = MagicMock()
        mock_key.id = key_id
        mock_key.name = 'Press Org'
        with patch('app.services.api_key_service.ApiKeyService.verify_key', return_value=mock_key):
            with patch('app.services.api_key_service.ApiKeyService.record_usage'):
                identity = require_api_key(x_api_key='cfa_valid', db=db)
        assert isinstance(identity, ApiKeyIdentity)
        assert identity.api_key_id == key_id
        assert identity.name == 'Press Org'
