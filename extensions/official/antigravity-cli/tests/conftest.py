"""Test harness for the antigravity-cli provider module.

The module is loaded the way Veles loads an installed module (`load_module`), so
its files are importable as `_veles_module_antigravity-cli.<file>` — not a valid
identifier, so tests reach them through `importlib.import_module` — and its
`provider` contribution is live for every test. Tests may use Veles internals for
fixtures — they run against a pinned Veles in registry CI.
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
    load_module(ModuleHandle("antigravity-cli", parse_manifest(text), MODULE_DIR), registry)
    return registry


# At import time: test modules import `_veles_module_antigravity-cli.*` at their top.
AGY_MODULES = _load()


@pytest.fixture(autouse=True)
def _agy_environment(
    tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch
) -> Iterator[None]:
    """A fresh user home and the module loaded."""
    monkeypatch.setenv("VELES_USER_HOME", str(tmp_path_factory.mktemp("veles-user-home")))
    token = set_module_registry(AGY_MODULES)
    try:
        yield
    finally:
        reset_module_registry(token)
