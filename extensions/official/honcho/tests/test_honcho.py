"""Tests for the Honcho memory provider module.

The recall tests drive the real `honcho-ai` SDK with only the HTTP transport
mocked (respx). They skip where the SDK isn't installed (e.g. registry
validation, which installs only Veles + pytest).
"""

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import pytest

BASE = "https://honcho.test"


def _load():
    path = Path(__file__).resolve().parent.parent / "honcho_provider.py"
    spec = importlib.util.spec_from_file_location("_veles_module_honcho", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _respx():
    # `honcho.http` exists only in honcho-ai, not the unrelated `honcho` Procfile runner.
    pytest.importorskip("honcho.http")
    return pytest.importorskip("respx")


def _message(mid: str, content: str) -> dict[str, Any]:
    return {
        "id": mid,
        "content": content,
        "peer_id": "alice",
        "session_id": "s1",
        "workspace_id": "ws",
        "metadata": {},
        "created_at": "2026-09-01T10:00:00Z",
        "token_count": 3,
    }


def _provider(mod, **kw: Any):
    return mod.HonchoMemoryProvider(api_key="key", workspace_id="ws", base_url=BASE, **kw)


def test_workspace_search_maps_messages() -> None:
    respx = _respx()
    mod = _load()
    with respx.mock(assert_all_called=True) as router:
        router.post(f"{BASE}/v3/workspaces").respond(json={"id": "ws"})
        search = router.post(f"{BASE}/v3/workspaces/ws/search").respond(
            json=[_message("m1", "agent discussed X"), _message("m2", "y" * 1000)]
        )
        hits = _provider(mod).recall("X", limit=5)
    request = search.calls.last.request
    assert json.loads(request.content) == {"query": "X", "filters": None, "limit": 5}
    assert request.headers["Authorization"] == "Bearer key"
    assert [h.rel_path for h in hits] == ["honcho:m1", "honcho:m2"]
    assert hits[0].title == "[honcho] alice in s1"
    assert hits[0].summary == "agent discussed X"
    assert hits[0].ts is not None
    assert len(hits[1].summary) <= 200 and hits[1].summary.endswith("…")


def test_peer_scoped_search_uses_peer_route() -> None:
    respx = _respx()
    mod = _load()
    with respx.mock(assert_all_called=True) as router:
        router.post(f"{BASE}/v3/workspaces").respond(json={"id": "ws"})
        search = router.post(f"{BASE}/v3/workspaces/ws/peers/alice/search").respond(
            json=[_message("m1", "hello")]
        )
        hits = _provider(mod, peer_id="alice").recall("hi", limit=500)
    assert json.loads(search.calls.last.request.content)["limit"] == 100  # SDK max
    assert [h.rel_path for h in hits] == ["honcho:m1"]


def test_auth_error_returns_empty(capsys: pytest.CaptureFixture[str]) -> None:
    respx = _respx()
    mod = _load()
    with respx.mock as router:
        router.post(f"{BASE}/v3/workspaces").respond(401, json={"detail": "bad key"})
        assert _provider(mod).recall("q", limit=5) == []
    assert "Honcho recall failed" in capsys.readouterr().err


def test_unexpected_message_shape_returns_empty(capsys: pytest.CaptureFixture[str]) -> None:
    respx = _respx()
    mod = _load()
    broken = {k: v for k, v in _message("m1", "x").items() if k != "created_at"}
    with respx.mock as router:
        router.post(f"{BASE}/v3/workspaces").respond(json={"id": "ws"})
        router.post(f"{BASE}/v3/workspaces/ws/search").respond(json=[broken])
        assert _provider(mod).recall("q", limit=1) == []
    assert "Honcho recall failed" in capsys.readouterr().err


def test_no_sdk_returns_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    mod = _load()
    monkeypatch.setitem(sys.modules, "honcho", None)
    assert _provider(mod).recall("q", limit=5) == []


# ---------- factory ----------


def test_build_with_complete_config_returns_provider() -> None:
    mod = _load()
    p = mod._build({"api_key": "k", "workspace_id": "ws", "peer_id": "a", "base_url": "https://x/"})
    assert isinstance(p, mod.HonchoMemoryProvider)
    assert (p.workspace_id, p.peer_id, p.base_url) == ("ws", "a", "https://x/")


def test_build_peer_and_base_url_optional() -> None:
    mod = _load()
    p = mod._build({"api_key": "k", "workspace_id": "ws"})
    assert p is not None and p.peer_id is None and p.base_url is None


def test_build_missing_workspace_returns_none(capsys: pytest.CaptureFixture[str]) -> None:
    mod = _load()
    assert mod._build({"api_key": "k", "app_id": "a", "user_id": "u"}) is None
    assert mod._build({"api_key": "k", "app_id": "a", "user_id": "u"}) is None
    err = capsys.readouterr().err
    assert err.count("warning:") == 1  # built every turn: warn once
    assert "workspace_id" in err and "app_id" in err


def test_build_missing_api_key_returns_none() -> None:
    mod = _load()
    assert mod._build({"workspace_id": "ws"}) is None


# ---------- register() ----------


def test_register_adds_honcho_provider() -> None:
    mod = _load()
    added: list[str] = []

    class FakeApi:
        def add_memory_provider(self, name: str, factory: Any) -> None:
            added.append(name)

    mod.register(FakeApi())
    assert added == ["honcho"]
