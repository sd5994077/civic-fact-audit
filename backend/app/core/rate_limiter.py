import threading
import time
from collections import defaultdict, deque
from typing import Callable

from fastapi import Request

from app.core.errors import AppError

_WINDOW_SECONDS = 60

AUTH_LOGIN_LIMIT = 10
DUAL_CONTROL_TOKEN_LIMIT = 30
WRITE_STANDARD_LIMIT = 120
ADMIN_WRITE_LIMIT = 60


class SlidingWindowRateLimiter:
    """Thread-safe in-memory sliding window rate limiter.

    Tracks per-key request timestamps in a deque.  On each call, timestamps
    older than the window are evicted before the limit is checked.  Suitable
    for single-process deployments; replace backing store with Redis for
    multi-instance setups.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._windows: dict[str, deque[float]] = defaultdict(deque)

    def is_allowed(self, key: str, *, limit: int, window_seconds: int) -> tuple[bool, int]:
        now = time.monotonic()
        cutoff = now - window_seconds
        with self._lock:
            dq = self._windows[key]
            while dq and dq[0] <= cutoff:
                dq.popleft()
            if len(dq) >= limit:
                retry_after = max(1, int(dq[0] + window_seconds - now) + 1)
                return False, retry_after
            dq.append(now)
            return True, 0


_limiter = SlidingWindowRateLimiter()


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get('X-Forwarded-For')
    if forwarded:
        return forwarded.split(',')[0].strip()
    if request.client is not None:
        return request.client.host
    return 'unknown'


def ip_rate_limit(limit: int, *, endpoint_key: str, window_seconds: int = _WINDOW_SECONDS) -> Callable:
    """Return a FastAPI dependency that enforces per-IP sliding-window rate limiting.

    Usage::

        @router.post('/login')
        def login(
            ...,
            _rl: None = Depends(ip_rate_limit(AUTH_LOGIN_LIMIT, endpoint_key='auth_login')),
        ):
    """
    def dependency(request: Request) -> None:
        key = f'{endpoint_key}:{_client_ip(request)}'
        allowed, retry_after = _limiter.is_allowed(key, limit=limit, window_seconds=window_seconds)
        if not allowed:
            raise AppError(
                'rate_limit_exceeded',
                'Too many requests. Please slow down and try again.',
                status_code=429,
                details={'retry_after_seconds': retry_after},
            )
    return dependency
