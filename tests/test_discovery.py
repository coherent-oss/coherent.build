import importlib.metadata

import pytest

import coherent.build.discovery as discovery


def test_python_requires_fallback_on_api_failure(monkeypatch):
    """
    When the GitHub API is unavailable (e.g., 429 rate limit or connection
    error), python_requires_supported falls back to coherent.build's own
    installed Requires-Python metadata.
    """
    monkeypatch.setattr(
        discovery.requests,
        'get',
        lambda *a, **kw: (_ for _ in ()).throw(Exception('service unavailable')),
    )
    result = discovery.python_requires_supported()
    expected = importlib.metadata.metadata('coherent.build')['Requires-Python']
    assert result == expected


def test_python_requires_fallback_on_unexpected_response(monkeypatch):
    """
    When the GitHub API returns an unexpected response (e.g., a dict instead
    of a list due to rate limiting), python_requires_supported falls back to
    coherent.build's own Requires-Python metadata.
    """

    class FakeResponse:
        def json(self):
            return {'message': 'API rate limit exceeded', 'documentation_url': '...'}

    monkeypatch.setattr(discovery.requests, 'get', lambda *a, **kw: FakeResponse())
    result = discovery.python_requires_supported()
    expected = importlib.metadata.metadata('coherent.build')['Requires-Python']
    assert result == expected
