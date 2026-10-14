"""Guard only forwards an explicit clearance and applies returned purification."""

from types import SimpleNamespace

import pytest
from ethos_aegis_sdk import AegisClient


@pytest.mark.parametrize(
    "verdict",
    [
        SimpleNamespace(is_sanctified=False, is_condemned=False, purified_payload=None),
        {"sanctified": False, "condemned": False},
        {"condemned": False},
        {"sanctified": True, "condemned": False, "sanitized": True},
    ],
)
def test_guard_rejects_uncleared_or_unusable_verdict(monkeypatch, verdict):
    client = AegisClient(transport="http")
    monkeypatch.setattr(client, "adjudicate", lambda *args: verdict)
    calls = []
    result = client.guard("raw", lambda msg: calls.append(msg) or "response")
    assert result.was_blocked and calls == []
    assert list(client.stream_guard("raw", lambda msg: calls.append(msg) or iter(["response"])))
    assert calls == []


def test_guard_forwards_purified_text_even_when_empty(monkeypatch):
    client = AegisClient(transport="http")
    monkeypatch.setattr(
        client,
        "adjudicate",
        lambda *args: {"sanctified": True, "condemned": False, "sanitized": True, "purified_payload": ""},
    )
    calls = []
    result = client.guard("raw", lambda msg: calls.append(msg) or "response")
    assert not result.was_blocked and calls == [""]


@pytest.mark.parametrize(
    "status,payload,expected",
    [
        (200, b'{"sanctified":true,"condemned":false}', True),
        (302, b'{"sanctified":true,"condemned":false}', False),
        (403, b'{"sanctified":true,"condemned":false}', False),
        (200, b"[]", False),
        (200, b"x" * 1_048_577, False),
    ],
)
def test_http_verdict_status_shape_and_size(monkeypatch, status, payload, expected):
    import http.client

    class Connection:
        def __init__(self, *args, **kwargs):
            self.status = status

        def request(self, method, path, body, headers):
            assert method == "POST" and path == "/v1/adjudicate"

        def getresponse(self):
            return self

        def read(self, limit):
            return payload[:limit]

        def close(self):
            pass

    monkeypatch.setattr(http.client, "HTTPConnection", Connection)
    client = AegisClient(transport="http")
    if expected:
        assert client.adjudicate("hello")["sanctified"] is True
    else:
        with pytest.raises(ValueError):
            client.adjudicate("hello")


def test_bearer_token_never_sent_to_nonloopback_plaintext():
    client = AegisClient(transport="http", server_url="http://example.test/v1/adjudicate", api_key="synthetic")
    with pytest.raises(ValueError, match="HTTPS"):
        client.adjudicate("hello")
