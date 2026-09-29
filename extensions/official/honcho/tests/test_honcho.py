"""Tests for the Honcho memory provider module."""

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import pytest


def _load():
    path = Path(__file__).resolve().parent.parent / "honcho.py"
    spec = importlib.util.spec_from_file_location("_veles_module_honcho", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _install_fake_honcho(monkeypatch: pytest.MonkeyPatch, search_result: Any) -> MagicMock:
    """Drop a fake `honcho_ai` module into sys.modules and return the Honcho
    class mock so the test can assert on call args."""
    fake_client = MagicMock()
    fake_client.search.return_value = search_result
    honcho_cls = MagicMock(return_value=fake_client)
    fake_mod = SimpleNamespace(Honcho=honcho_cls)
    monkeypatch.setitem(sys.modules, "honcho_ai", fake_mod)
    return honcho_cls


def test_recall_returns_hits(monkeypatch: pytest.MonkeyPatch) -> None:
    honcho = _load()
    _install_fake_honcho(
        monkeypatch,
        [
            {
                "id": "m1",
                "title": "Last conversation",
                "content": "agent discussed X",
                "score": 0.9,
            },
            {"id": "m2", "text": "earlier note", "score": 0.5},
        ],
    )
    p = honcho.HonchoMemoryProvider(api_key="key", app_id="app", user_id="u")
    hits = p.recall("X", limit=5)
    assert len(hits) == 2
    assert hits[0].rel_path == "honcho:m1"
    assert "Last conversation" in hits[0].title
    assert hits[0].score == 0.9


def test_handles_response_with_items_field(monkeypatch: pytest.MonkeyPatch) -> None:
    honcho = _load()
    _install_fake_honcho(
        monkeypatch,
        SimpleNamespace(items=[{"id": "m1", "text": "found"}]),
    )
    p = honcho.HonchoMemoryProvider(api_key="k", app_id="a", user_id="u")
    hits = p.recall("q", limit=5)
    assert len(hits) == 1


def test_no_sdk_returns_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    honcho = _load()
    monkeypatch.setitem(sys.modules, "honcho_ai", None)
    p = honcho.HonchoMemoryProvider(api_key="k", app_id="a", user_id="u")
    assert p.recall("q", limit=5) == []


def test_network_error_returns_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    honcho = _load()
    fake_client = MagicMock()
    fake_client.search.side_effect = RuntimeError("connection refused")
    monkeypatch.setitem(
        sys.modules, "honcho_ai", SimpleNamespace(Honcho=MagicMock(return_value=fake_client))
    )
    p = honcho.HonchoMemoryProvider(api_key="k", app_id="a", user_id="u")
    assert p.recall("q", limit=5) == []


def test_long_content_truncated(monkeypatch: pytest.MonkeyPatch) -> None:
    honcho = _load()
    _install_fake_honcho(monkeypatch, [{"id": "m1", "content": "x" * 1000}])
    p = honcho.HonchoMemoryProvider(api_key="k", app_id="a", user_id="u")
    hits = p.recall("q", limit=1)
    assert len(hits[0].summary) <= 200
    assert hits[0].summary.endswith("…")


def test_base_url_passed_to_client(monkeypatch: pytest.MonkeyPatch) -> None:
    honcho = _load()
    honcho_cls = _install_fake_honcho(monkeypatch, [])
    p = honcho.HonchoMemoryProvider(
        api_key="k", app_id="a", user_id="u", base_url="https://internal.honcho/"
    )
    p.recall("q", limit=1)
    call_kwargs = honcho_cls.call_args.kwargs
    assert call_kwargs.get("base_url") == "https://internal.honcho/"


# ---------- factory ----------


def test_build_with_complete_config_returns_provider() -> None:
    honcho = _load()
    p = honcho._build({"api_key": "k", "app_id": "a", "user_id": "u"})
    assert isinstance(p, honcho.HonchoMemoryProvider)
    assert p.app_id == "a"


def test_build_with_base_url() -> None:
    honcho = _load()
    p = honcho._build({"api_key": "k", "app_id": "a", "user_id": "u", "base_url": "https://x/"})
    assert p is not None
    assert p.base_url == "https://x/"


def test_build_missing_app_id_returns_none() -> None:
    honcho = _load()
    assert honcho._build({"api_key": "k", "user_id": "u"}) is None


def test_build_missing_api_key_returns_none() -> None:
    honcho = _load()
    assert honcho._build({"app_id": "a", "user_id": "u"}) is None


# ---------- register() ----------


def test_register_adds_honcho_provider() -> None:
    honcho = _load()
    added: list[tuple[str, Any]] = []

    class FakeApi:
        def add_memory_provider(self, name: str, factory: Any) -> None:
            added.append((name, factory))

    honcho.register(FakeApi())
    assert [name for name, _factory in added] == ["honcho"]
