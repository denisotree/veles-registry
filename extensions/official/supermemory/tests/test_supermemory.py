"""Tests for the Supermemory memory provider module."""

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import pytest


def _load():
    path = Path(__file__).resolve().parent.parent / "supermemory.py"
    spec = importlib.util.spec_from_file_location("_veles_module_supermemory", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _install_fake_supermemory(
    monkeypatch: pytest.MonkeyPatch,
    search_result: Any,
    *,
    accept_kw: str = "q",
) -> MagicMock:
    """Plant a fake `supermemory.Supermemory` whose .search accepts only
    the `accept_kw` keyword (`q` or `query`). Helps test the fallback."""
    fake_client = MagicMock()

    def _search(**kw: Any) -> Any:
        if accept_kw not in kw:
            raise TypeError(f"unexpected keyword in {sorted(kw)}")
        return search_result

    fake_client.search.side_effect = _search
    sm_cls = MagicMock(return_value=fake_client)
    monkeypatch.setitem(sys.modules, "supermemory", SimpleNamespace(Supermemory=sm_cls))
    return fake_client


def test_recall_returns_hits(monkeypatch: pytest.MonkeyPatch) -> None:
    supermemory = _load()
    _install_fake_supermemory(
        monkeypatch,
        {"results": [{"id": "s1", "content": "long-term fact", "score": 0.95}]},
    )
    p = supermemory.SupermemoryProvider(api_key="k")
    hits = p.recall("fact", limit=3)
    assert len(hits) == 1
    assert hits[0].rel_path == "supermemory:s1"
    assert "long-term fact" in hits[0].summary


def test_falls_back_from_q_to_query(monkeypatch: pytest.MonkeyPatch) -> None:
    """If the SDK rejects `q=`, retry with `query=`."""
    supermemory = _load()
    _install_fake_supermemory(
        monkeypatch,
        [{"id": "s1", "memory": "ok"}],
        accept_kw="query",
    )
    p = supermemory.SupermemoryProvider(api_key="k")
    hits = p.recall("test", limit=1)
    assert len(hits) == 1


def test_no_sdk_returns_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    supermemory = _load()
    monkeypatch.setitem(sys.modules, "supermemory", None)
    p = supermemory.SupermemoryProvider(api_key="k")
    assert p.recall("q", limit=5) == []


def test_handles_documents_key(monkeypatch: pytest.MonkeyPatch) -> None:
    supermemory = _load()
    _install_fake_supermemory(
        monkeypatch, {"documents": [{"id": "d1", "title": "doc", "content": "x"}]}
    )
    p = supermemory.SupermemoryProvider(api_key="k")
    assert len(p.recall("q", limit=1)) == 1


def test_user_id_passed_through(monkeypatch: pytest.MonkeyPatch) -> None:
    supermemory = _load()
    client = _install_fake_supermemory(monkeypatch, {"results": []})
    p = supermemory.SupermemoryProvider(api_key="k", user_id="test-user")
    p.recall("q", limit=1)
    kwargs = client.search.call_args.kwargs
    assert kwargs.get("user_id") == "test-user"


# ---------- factory ----------


def test_build_with_complete_config_returns_provider() -> None:
    supermemory = _load()
    p = supermemory._build({"api_key": "k", "user_id": "u"})
    assert isinstance(p, supermemory.SupermemoryProvider)
    assert p.user_id == "u"


def test_build_without_user_id_is_none() -> None:
    supermemory = _load()
    p = supermemory._build({"api_key": "k"})
    assert p is not None
    assert p.user_id is None


def test_build_missing_api_key_returns_none() -> None:
    supermemory = _load()
    assert supermemory._build({"user_id": "u"}) is None


# ---------- register() ----------


def test_register_adds_supermemory_provider() -> None:
    supermemory = _load()
    added: list[tuple[str, Any]] = []

    class FakeApi:
        def add_memory_provider(self, name: str, factory: Any) -> None:
            added.append((name, factory))

    supermemory.register(FakeApi())
    assert [name for name, _factory in added] == ["supermemory"]
