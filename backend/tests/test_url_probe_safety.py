import httpx
import pytest

from app.services.source_service import SourceService


@pytest.fixture(autouse=True)
def mock_url_reachable() -> None:
    # Exercise the actual probe rather than conftest's attachment-test stub.
    pass


@pytest.mark.parametrize('url', [
    'http://127.0.0.1/', 'http://10.0.0.1/', 'http://169.254.169.254/',
    'http://[::1]/', 'http://localhost/', 'file:///etc/passwd',
])
def test_probe_never_requests_non_public_targets(monkeypatch, url: str) -> None:
    monkeypatch.setattr(httpx, 'Client', lambda **kwargs: pytest.fail('Blocked URL must not open a client'))
    assert SourceService.check_url_reachable(url)['status'] == 'error'


def test_probe_blocks_redirect_to_private_target_and_pins_dns(monkeypatch) -> None:
    monkeypatch.setattr('app.services.source_service.socket.getaddrinfo',
                        lambda *args, **kwargs: [(2, 1, 6, '', ('93.184.216.34', 443))])
    seen = []

    def handle(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(302, headers={'Location': 'http://127.0.0.1/internal'})

    client_type = httpx.Client
    monkeypatch.setattr(httpx, 'Client', lambda **kwargs: client_type(transport=httpx.MockTransport(handle), **kwargs))
    assert SourceService.check_url_reachable('https://example.com/record')['status'] == 'error'
    assert len(seen) == 1
    assert seen[0].url.host == '93.184.216.34'
    assert seen[0].headers['host'] == 'example.com'
    assert seen[0].extensions['sni_hostname'] == 'example.com'


def test_probe_rejects_mixed_public_private_dns(monkeypatch) -> None:
    monkeypatch.setattr('app.services.source_service.socket.getaddrinfo',
                        lambda *args, **kwargs: [(2, 1, 6, '', ('93.184.216.34', 443)), (2, 1, 6, '', ('10.0.0.1', 443))])
    monkeypatch.setattr(httpx, 'Client', lambda **kwargs: pytest.fail('Unsafe DNS must not open a client'))
    assert SourceService.check_url_reachable('https://example.com/record')['status'] == 'error'


def test_probe_revalidates_public_redirect_and_streams_get_fallback(monkeypatch) -> None:
    monkeypatch.setattr('app.services.source_service.socket.getaddrinfo',
                        lambda *args, **kwargs: [(2, 1, 6, '', ('93.184.216.34', 443))])
    seen = []

    class UnreadBody(httpx.SyncByteStream):
        def __iter__(self):
            pytest.fail('Reachability probe must not download the GET body')
            yield b''

    def handle(request: httpx.Request) -> httpx.Response:
        seen.append((request.method, request.url.path, request.headers['host']))
        if request.url.path == '/first':
            return httpx.Response(302, headers={'Location': 'https://record.example.com/second'})
        if request.method == 'HEAD':
            return httpx.Response(405)
        return httpx.Response(200, stream=UnreadBody())

    client_type = httpx.Client
    monkeypatch.setattr(httpx, 'Client', lambda **kwargs: client_type(transport=httpx.MockTransport(handle), **kwargs))
    assert SourceService.check_url_reachable('https://example.com/first')['status'] == 'ok'
    assert seen == [('HEAD', '/first', 'example.com'), ('HEAD', '/second', 'record.example.com'),
                    ('GET', '/second', 'record.example.com')]
