import time

import pytest

from app.core.errors import AppError
from app.core.rate_limiter import SlidingWindowRateLimiter, ip_rate_limit


class TestSlidingWindowRateLimiter:
    def test_allows_requests_within_limit(self) -> None:
        rl = SlidingWindowRateLimiter()
        for _ in range(5):
            allowed, retry_after = rl.is_allowed('key', limit=5, window_seconds=60)
            assert allowed is True
            assert retry_after == 0

    def test_blocks_when_limit_exceeded(self) -> None:
        rl = SlidingWindowRateLimiter()
        for _ in range(3):
            rl.is_allowed('key', limit=3, window_seconds=60)
        allowed, retry_after = rl.is_allowed('key', limit=3, window_seconds=60)
        assert allowed is False
        assert retry_after >= 1

    def test_independent_keys_do_not_interfere(self) -> None:
        rl = SlidingWindowRateLimiter()
        for _ in range(3):
            rl.is_allowed('key_a', limit=3, window_seconds=60)
        allowed_a, _ = rl.is_allowed('key_a', limit=3, window_seconds=60)
        allowed_b, _ = rl.is_allowed('key_b', limit=3, window_seconds=60)
        assert allowed_a is False
        assert allowed_b is True

    def test_window_expiry_allows_new_requests(self) -> None:
        rl = SlidingWindowRateLimiter()
        for _ in range(3):
            rl.is_allowed('key', limit=3, window_seconds=1)
        blocked, _ = rl.is_allowed('key', limit=3, window_seconds=1)
        assert blocked is False
        time.sleep(1.1)
        allowed, _ = rl.is_allowed('key', limit=3, window_seconds=1)
        assert allowed is True

    def test_retry_after_is_positive(self) -> None:
        rl = SlidingWindowRateLimiter()
        for _ in range(2):
            rl.is_allowed('key', limit=2, window_seconds=60)
        _, retry_after = rl.is_allowed('key', limit=2, window_seconds=60)
        assert retry_after >= 1

    def test_exact_limit_boundary(self) -> None:
        rl = SlidingWindowRateLimiter()
        allowed_1, _ = rl.is_allowed('key', limit=1, window_seconds=60)
        allowed_2, _ = rl.is_allowed('key', limit=1, window_seconds=60)
        assert allowed_1 is True
        assert allowed_2 is False


class TestIpRateLimitDependency:
    def test_raises_app_error_when_limit_exceeded(self, monkeypatch) -> None:
        from unittest.mock import MagicMock

        import app.core.rate_limiter as rl_module

        monkeypatch.setattr(rl_module._limiter, 'is_allowed', lambda *_a, **_kw: (False, 5))

        request = MagicMock()
        request.headers = {}
        request.client = MagicMock()
        request.client.host = '1.2.3.4'

        dep = ip_rate_limit(10, endpoint_key='test_ep')
        with pytest.raises(AppError) as exc_info:
            dep(request)
        assert exc_info.value.status_code == 429
        assert exc_info.value.code == 'rate_limit_exceeded'
        assert exc_info.value.details['retry_after_seconds'] == 5

    def test_passes_when_allowed(self, monkeypatch) -> None:
        from unittest.mock import MagicMock

        import app.core.rate_limiter as rl_module

        monkeypatch.setattr(rl_module._limiter, 'is_allowed', lambda *_a, **_kw: (True, 0))

        request = MagicMock()
        request.headers = {}
        request.client = MagicMock()
        request.client.host = '1.2.3.4'

        dep = ip_rate_limit(10, endpoint_key='test_ep')
        dep(request)

    def test_uses_x_forwarded_for_header(self, monkeypatch) -> None:
        from unittest.mock import MagicMock

        import app.core.rate_limiter as rl_module

        seen_keys: list[str] = []

        def _capture(key: str, **kwargs):  # type: ignore[override]
            seen_keys.append(key)
            return (True, 0)

        monkeypatch.setattr(rl_module._limiter, 'is_allowed', _capture)

        request = MagicMock()
        request.headers = {'X-Forwarded-For': '10.0.0.1, 192.168.1.1'}
        request.client = MagicMock()
        request.client.host = '127.0.0.1'

        dep = ip_rate_limit(10, endpoint_key='fwd_test')
        dep(request)

        assert seen_keys[0].endswith('10.0.0.1')

    def test_falls_back_to_client_host_when_no_forwarded_header(self, monkeypatch) -> None:
        from unittest.mock import MagicMock

        import app.core.rate_limiter as rl_module

        seen_keys: list[str] = []

        def _capture(key: str, **kwargs):  # type: ignore[override]
            seen_keys.append(key)
            return (True, 0)

        monkeypatch.setattr(rl_module._limiter, 'is_allowed', _capture)

        request = MagicMock()
        request.headers = {}
        request.client = MagicMock()
        request.client.host = '5.5.5.5'

        dep = ip_rate_limit(10, endpoint_key='host_test')
        dep(request)

        assert seen_keys[0].endswith('5.5.5.5')
