"""Tests for the Mem0 memory provider module.

The recall tests drive the real `mem0ai` SDK with only the HTTP transport
mocked (respx). They skip where the SDK isn't installed (e.g. registry
validation, which installs only Veles + pytest).
"""

import importlib.util
import json
import os
import sys
from pathlib import Path
from typing import Any

import pytest

HOST = "https://mem0.test"


def _load():
    path = Path(__file__).resolve().parent.parent / "mem0_provider.py"
    spec = importlib.util.spec_from_file_location("_veles_module_mem0", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def requests_sent(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """PostHog (mem0 telemetry) sends over `requests`, which respx can't see —
    block and record every `requests` send instead."""
    requests = pytest.importorskip("requests")
    sent: list[str] = []

    def _send(self, request, **kwargs):  # noqa: ANN001
        sent.append(request.url)
        raise requests.ConnectionError("network disabled in tests")

    monkeypatch.setattr(requests.Session, "send", _send)
    return sent


@pytest.fixture
def respx(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, requests_sent: list[str]):
    # Skip without importing mem0: the adapter's own MEM0_TELEMETRY default must
    # be in place before the first import, so the test must not import it first.
    if importlib.util.find_spec("mem0") is None:
        pytest.skip("mem0ai not installed")
    # MEM0_TELEMETRY absent (restored after the test) so the adapter's default is
    # what's exercised; MEM0_DIR keeps the SDK's import-time makedirs off ~/.mem0.
    monkeypatch.setenv("MEM0_TELEMETRY", "unset")
    monkeypatch.delenv("MEM0_TELEMETRY")
    monkeypatch.setenv("MEM0_DIR", str(tmp_path / "mem0"))
    return pytest.importorskip("respx")


def _ping(router) -> None:
    router.get(f"{HOST}/v1/ping/").respond(
        json={"org_id": "o", "project_id": "p", "user_email": "u@example.com"}
    )


def test_search_sends_entity_ids_in_filters(respx) -> None:
    mod = _load()
    with respx.mock(assert_all_called=True) as router:
        _ping(router)
        search = router.post(f"{HOST}/v3/memories/search/").respond(
            json={
                "results": [
                    {"id": "x1", "memory": "prefers concise responses", "score": 0.7},
                    {"id": "x2", "memory": "z" * 1000, "score": 0.4},
                ]
            }
        )
        hits = mod.Mem0MemoryProvider(api_key="k", user_id="u", host=HOST).recall("prefs", limit=3)
    request = search.calls.last.request
    assert json.loads(request.content) == {
        "query": "prefs",
        "filters": {"user_id": "u"},
        "top_k": 3,
    }
    assert request.headers["Authorization"] == "Token k"
    assert [h.rel_path for h in hits] == ["mem0:x1", "mem0:x2"]
    assert hits[0].summary == "prefers concise responses"
    assert hits[0].score == 0.7
    assert len(hits[1].summary) <= 200 and hits[1].summary.endswith("…")


def test_agent_id_ors_into_filters(respx) -> None:
    mod = _load()
    with respx.mock(assert_all_called=True) as router:
        _ping(router)
        search = router.post(f"{HOST}/v3/memories/search/").respond(json={"results": []})
        p = mod.Mem0MemoryProvider(api_key="k", user_id="u", agent_id="veles", host=HOST)
        assert p.recall("q", limit=2) == []
    assert json.loads(search.calls.last.request.content)["filters"] == {
        "OR": [{"user_id": "u"}, {"agent_id": "veles"}]
    }


def test_auth_error_returns_empty(respx, capsys: pytest.CaptureFixture[str]) -> None:
    mod = _load()
    with respx.mock as router:
        router.get(f"{HOST}/v1/ping/").respond(401, json={"detail": "Invalid API key"})
        assert (
            mod.Mem0MemoryProvider(api_key="bad", user_id="u", host=HOST).recall("q", limit=5) == []
        )
    assert "Mem0 recall failed" in capsys.readouterr().err


def test_telemetry_disabled_and_nothing_sent(respx, requests_sent: list[str]) -> None:
    mod = _load()
    with respx.mock(assert_all_called=False) as router:
        _ping(router)
        router.post(f"{HOST}/v3/memories/search/").respond(json={"results": []})
        posthog = router.route(host="us.i.posthog.com")
        mod.Mem0MemoryProvider(api_key="k", user_id="u", host=HOST).recall("q", limit=1)
    from mem0.memory import telemetry

    assert telemetry.MEM0_TELEMETRY is False
    assert telemetry.client_telemetry.posthog is None
    assert not posthog.called
    assert requests_sent == []


def test_explicit_telemetry_setting_is_kept(monkeypatch: pytest.MonkeyPatch) -> None:
    mod = _load()
    monkeypatch.setenv("MEM0_TELEMETRY", "True")
    monkeypatch.setitem(sys.modules, "mem0", None)
    mod.Mem0MemoryProvider(api_key="k", user_id="u").recall("q", limit=1)
    assert os.environ["MEM0_TELEMETRY"] == "True"


def test_no_sdk_returns_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    mod = _load()
    monkeypatch.setitem(sys.modules, "mem0", None)
    assert mod.Mem0MemoryProvider(api_key="k", user_id="u").recall("q", limit=5) == []


# ---------- factory ----------


def test_build_with_complete_config_returns_provider() -> None:
    mod = _load()
    p = mod._build({"api_key": "k", "user_id": "u", "agent_id": "veles", "host": "https://h"})
    assert isinstance(p, mod.Mem0MemoryProvider)
    assert (p.api_key, p.user_id, p.agent_id, p.host) == ("k", "u", "veles", "https://h")


def test_build_optional_keys_default_none() -> None:
    mod = _load()
    p = mod._build({"api_key": "k", "user_id": "u"})
    assert p is not None and p.agent_id is None and p.host is None


def test_build_missing_user_id_returns_none() -> None:
    mod = _load()
    assert mod._build({"api_key": "k"}) is None


def test_build_missing_api_key_returns_none() -> None:
    mod = _load()
    assert mod._build({"user_id": "u"}) is None


# ---------- register() ----------


def test_register_adds_mem0_provider() -> None:
    mod = _load()
    added: list[str] = []

    class FakeApi:
        def add_memory_provider(self, name: str, factory: Any) -> None:
            added.append(name)

    mod.register(FakeApi())
    assert added == ["mem0"]
