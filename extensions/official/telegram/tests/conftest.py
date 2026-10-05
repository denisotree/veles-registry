"""Test harness for the Telegram channel module.

The module is loaded the way Veles loads an installed module (`load_module`), so
its files are importable as `_veles_module_telegram.<file>`, its `platform`
contribution is live and its `locales/` reach `t("telegram.…")` for every test.
Tests may use Veles internals for fixtures — they run against a pinned Veles in
registry CI.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

from veles.core.module_manifest import parse_manifest
from veles.core.modules import (
    ModuleHandle,
    ModuleRegistry,
    load_module,
    reset_module_registry,
    set_module_registry,
)

MODULE_DIR = Path(__file__).resolve().parent.parent


def _load() -> ModuleRegistry:
    registry = ModuleRegistry()
    text = (MODULE_DIR / "module.toml").read_text(encoding="utf-8")
    load_module(ModuleHandle("telegram", parse_manifest(text), MODULE_DIR), registry)
    return registry


# At import time: test modules import `_veles_module_telegram.*` at their top.
TELEGRAM_MODULES = _load()


@pytest.fixture(autouse=True)
def _telegram_environment(
    tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch
) -> Iterator[None]:
    """A fresh user home, the Telegram module loaded, embeddings and the model
    catalogue kept offline."""
    from veles.core import model_metadata
    from veles.modules.embedding import register_embedding_adapter, reset_embedding_adapter

    monkeypatch.setenv("VELES_USER_HOME", str(tmp_path_factory.mktemp("veles-user-home")))
    register_embedding_adapter(None)  # no live Ollama probe
    model_metadata._memo = {}
    token = set_module_registry(TELEGRAM_MODULES)
    try:
        yield
    finally:
        reset_module_registry(token)
        reset_embedding_adapter()
        model_metadata.reset_for_tests()


@pytest.fixture(autouse=True)
def _in_memory_keyring() -> Iterator[None]:
    """A working OS-keyring backend per test: headless CI has none, and a
    channel's secrets live there."""
    import keyring
    from keyring.backend import KeyringBackend
    from keyring.errors import PasswordDeleteError

    class _InMemory(KeyringBackend):
        priority = 1  # type: ignore[assignment]

        def __init__(self) -> None:
            super().__init__()
            self._data: dict[tuple[str, str], str] = {}

        def get_password(self, service: str, username: str) -> str | None:
            return self._data.get((service, username))

        def set_password(self, service: str, username: str, password: str) -> None:
            self._data[(service, username)] = password

        def delete_password(self, service: str, username: str) -> None:
            try:
                del self._data[(service, username)]
            except KeyError as exc:
                raise PasswordDeleteError("not found") from exc

    prev = keyring.get_keyring()
    keyring.set_keyring(_InMemory())
    try:
        yield
    finally:
        keyring.set_keyring(prev)
