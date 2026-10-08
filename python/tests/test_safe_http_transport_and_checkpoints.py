"""HTTP transport and checkpoint filesystem security regression tests."""
from pathlib import Path
import pytest
from ethos_aegis.agent.adapters.generic_adapter import GenericAdapter
from ethos_aegis.harness.state import CheckpointStore
from ethos_aegis.security.http_transport import validate_http_base_url
from ethos_aegis.veriflow.ckan_adapter import CKANClient


@pytest.mark.parametrize("url", [
    "https://example.test/api", "https://example.test:8443/api",
    "http://localhost:11434/v1", "http://127.0.0.1:8080", "http://[::1]:8080",
])
def test_permitted_http_urls(url):
    assert validate_http_base_url(url) == url


@pytest.mark.parametrize("url", [
    "file:///etc/passwd", "ftp://example.test", "http://remote.example.test",
    "https://user:password@example.test", "https://example.test/?token=1",
    "https://example.test/#fragment", "https://example.test:invalid",
    "https://example.test\\@evil.test", "https://example.test\nHost: evil",
    "https://[malformed",
])
def test_disallowed_http_urls(url):
    with pytest.raises(ValueError):
        validate_http_base_url(url)


@pytest.mark.parametrize("factory", [GenericAdapter, CKANClient])
def test_adapters_reject_bad_schemes(factory):
    with pytest.raises(ValueError):
        factory(base_url="file:///etc/passwd")
    with pytest.raises(ValueError):
        factory(base_url="http://remote.example.test")


def test_checkpoint_traversal_denied(tmp_path: Path):
    store = CheckpointStore(tmp_path / "checkpoints")
    for invalid in ("../other", "nested/id", "", "a" * 129, ".hidden"):
        with pytest.raises(ValueError):
            store.load_latest(invalid)


def test_checkpoint_root_is_created(tmp_path: Path):
    store = CheckpointStore(tmp_path / "private")
    assert (tmp_path / "private").is_dir()
    assert store.list_sessions() == []
