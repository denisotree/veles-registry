"""Tests for the Supermemory memory provider module.

The recall tests drive the real `supermemory` SDK with only the HTTP transport
mocked (respx). They skip where the SDK isn't installed (e.g. registry
validation, which installs only Veles + pytest).
"""

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import pytest

BASE = "https://supermemory.test"


def _load():
    path = Path(__file__).resolve().parent.parent / "supermemory_provider.py"
    spec = importlib.util.spec_from_file_location("_veles_module_supermemory", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _respx():
    pytest.importorskip("supermemory")
    return pytest.importorskip("respx")


def _provider(mod, **kw: Any):
    return mod.SupermemoryProvider(api_key="k", base_url=BASE, **kw)


def test_memory_search_maps_results() -> None:
    respx = _respx()
    mod = _load()
    with respx.mock(assert_all_called=True) as router:
        search = router.post(f"{BASE}/v4/search").respond(
            json={
                "results": [
                    {"id": "s1", "memory": "long-term fact", "similarity": 0.95, "updatedAt": "t"},
                    {"id": "c1", "chunk": "w" * 1000, "similarity": 0.5, "updatedAt": "t"},
                ],
                "timing": 12,
                "total": 2,
            }
        )
        hits = _provider(mod, user_id="test-user").recall("fact", limit=3)
    request = search.calls.last.request
    assert json.loads(request.content) == {"q": "fact", "limit": 3, "containerTag": "test-user"}
    assert request.headers["Authorization"] == "Bearer k"
    assert [h.rel_path for h in hits] == ["supermemory:s1", "supermemory:c1"]
    assert hits[0].summary == "long-term fact"
    assert hits[0].score == 0.95
    assert len(hits[1].summary) <= 200 and hits[1].summary.endswith("…")


def test_no_user_id_sends_no_container_tag() -> None:
    respx = _respx()
    mod = _load()
    with respx.mock(assert_all_called=True) as router:
        search = router.post(f"{BASE}/v4/search").respond(
            json={"results": [], "timing": 1, "total": 0}
        )
        assert _provider(mod).recall("q", limit=1) == []
    assert json.loads(search.calls.last.request.content) == {"q": "q", "limit": 1}


def test_auth_error_returns_empty(capsys: pytest.CaptureFixture[str]) -> None:
    respx = _respx()
    mod = _load()
    with respx.mock as router:
        router.post(f"{BASE}/v4/search").respond(401, json={"error": "unauthorized"})
        assert _provider(mod).recall("q", limit=5) == []
    assert "Supermemory recall failed" in capsys.readouterr().err


def test_no_sdk_returns_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    mod = _load()
    monkeypatch.setitem(sys.modules, "supermemory", None)
    assert _provider(mod).recall("q", limit=5) == []


# ---------- factory ----------


def test_build_with_complete_config_returns_provider() -> None:
    mod = _load()
    p = mod._build({"api_key": "k", "user_id": "u", "base_url": "https://x"})
    assert isinstance(p, mod.SupermemoryProvider)
    assert (p.user_id, p.base_url) == ("u", "https://x")


def test_build_optional_keys_default_none() -> None:
    mod = _load()
    p = mod._build({"api_key": "k"})
    assert p is not None and p.user_id is None and p.base_url is None


def test_build_missing_api_key_returns_none() -> None:
    mod = _load()
    assert mod._build({"user_id": "u"}) is None


# ---------- register() ----------


def test_register_adds_supermemory_provider() -> None:
    mod = _load()
    added: list[str] = []

    class FakeApi:
        def add_memory_provider(self, name: str, factory: Any) -> None:
            added.append(name)

    mod.register(FakeApi())
    assert added == ["supermemory"]
