"""Tests for the Mem0 memory provider module."""

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import pytest


def _load():
    path = Path(__file__).resolve().parent.parent / "mem0.py"
    spec = importlib.util.spec_from_file_location("_veles_module_mem0", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _install_fake_mem0(monkeypatch: pytest.MonkeyPatch, search_result: Any) -> MagicMock:
    fake_client = MagicMock()
    fake_client.search.return_value = search_result
    mem_cls = MagicMock(return_value=fake_client)
    fake_mod = SimpleNamespace(MemoryClient=mem_cls)
    monkeypatch.setitem(sys.modules, "mem0", fake_mod)
    return fake_client


def test_recall_returns_hits(monkeypatch: pytest.MonkeyPatch) -> None:
    mem0 = _load()
    _install_fake_mem0(
        monkeypatch,
        {"results": [{"id": "x1", "memory": "prefers concise responses", "score": 0.7}]},
    )
    p = mem0.Mem0MemoryProvider(api_key="k", user_id="test-user")
    hits = p.recall("preferences", limit=3)
    assert len(hits) == 1
    assert hits[0].rel_path == "mem0:x1"
    assert "concise" in hits[0].summary


def test_handles_bare_list(monkeypatch: pytest.MonkeyPatch) -> None:
    mem0 = _load()
    _install_fake_mem0(monkeypatch, [{"id": "y1", "memory": "stuff"}])
    p = mem0.Mem0MemoryProvider(api_key="k", user_id="u")
    assert len(p.recall("q", limit=1)) == 1


def test_no_sdk_returns_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    mem0 = _load()
    monkeypatch.setitem(sys.modules, "mem0", None)
    p = mem0.Mem0MemoryProvider(api_key="k", user_id="u")
    assert p.recall("q", limit=5) == []


def test_search_error_returns_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    mem0 = _load()
    fake_client = MagicMock()
    fake_client.search.side_effect = RuntimeError("connection refused")
    monkeypatch.setitem(
        sys.modules, "mem0", SimpleNamespace(MemoryClient=MagicMock(return_value=fake_client))
    )
    p = mem0.Mem0MemoryProvider(api_key="k", user_id="u")
    assert p.recall("q", limit=5) == []


def test_propagates_agent_id(monkeypatch: pytest.MonkeyPatch) -> None:
    mem0 = _load()
    client = _install_fake_mem0(monkeypatch, [])
    p = mem0.Mem0MemoryProvider(api_key="k", user_id="u", agent_id="veles")
    p.recall("q", limit=2)
    kwargs = client.search.call_args.kwargs
    assert kwargs.get("agent_id") == "veles"


def test_long_content_truncated(monkeypatch: pytest.MonkeyPatch) -> None:
    mem0 = _load()
    _install_fake_mem0(monkeypatch, [{"id": "m1", "memory": "x" * 1000}])
    p = mem0.Mem0MemoryProvider(api_key="k", user_id="u")
    hits = p.recall("q", limit=1)
    assert len(hits[0].summary) <= 200
    assert hits[0].summary.endswith("…")


# ---------- factory ----------


def test_build_with_complete_config_returns_provider() -> None:
    mem0 = _load()
    p = mem0._build({"api_key": "k", "user_id": "u", "agent_id": "veles"})
    assert isinstance(p, mem0.Mem0MemoryProvider)
    assert p.api_key == "k"
    assert p.user_id == "u"
    assert p.agent_id == "veles"


def test_build_without_agent_id_is_none() -> None:
    mem0 = _load()
    p = mem0._build({"api_key": "k", "user_id": "u"})
    assert p is not None
    assert p.agent_id is None


def test_build_missing_user_id_returns_none() -> None:
    mem0 = _load()
    assert mem0._build({"api_key": "k"}) is None


def test_build_missing_api_key_returns_none() -> None:
    mem0 = _load()
    assert mem0._build({"user_id": "u"}) is None


# ---------- register() ----------


def test_register_adds_mem0_provider() -> None:
    mem0 = _load()
    added: list[tuple[str, Any]] = []

    class FakeApi:
        def add_memory_provider(self, name: str, factory: Any) -> None:
            added.append((name, factory))

    mem0.register(FakeApi())
    assert [name for name, _factory in added] == ["mem0"]
