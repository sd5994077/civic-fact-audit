"""
Global pytest fixtures for the backend test suite.
"""
from unittest.mock import patch

import pytest


@pytest.fixture(autouse=True)
def mock_url_reachable():
    """
    Prevent live HTTP requests during tests.

    SourceService.check_url_reachable() fires a real HTTP probe when a source
    is attached via validate_source_admission().  Tests use synthetic / fake
    URLs that would 404 (or never resolve), so we stub the method to always
    return a reachable-ok result.

    Individual tests that specifically exercise URL-check behaviour should
    override this fixture with their own patch.
    """
    with patch(
        'app.services.source_service.SourceService.check_url_reachable',
        return_value={'status': 'ok', 'code': 200, 'message': 'URL is reachable.'},
    ):
        yield
