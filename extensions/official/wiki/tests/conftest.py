"""Test harness for the wiki module.

The module is loaded the way Veles loads an installed module (`load_module`), so
its files are importable as `_veles_module_wiki.<file>` and its contributions are
live for every test. The layouts of this registry (`../llm-wiki`, `../notes`) are
discoverable whatever user home a test picks, so `init_project(layout="llm-wiki")`
gives a project with the wiki engine on. Tests may use Veles internals for
fixtures — they run against a pinned Veles in registry CI.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

from veles.core.layout import clear_engine_cache
from veles.core.module_manifest import parse_manifest
from veles.core.modules import (
    ModuleHandle,
    ModuleRegistry,
    load_module,
    reset_module_registry,
    set_module_registry,
)

MODULE_DIR = Path(__file__).resolve().parent.parent
REGISTRY_EXTENSIONS = MODULE_DIR.parent  # holds llm-wiki/ and notes/


def _load() -> ModuleRegistry:
    registry = ModuleRegistry()
    text = (MODULE_DIR / "module.toml").read_text(encoding="utf-8")
    load_module(ModuleHandle("wiki", parse_manifest(text), MODULE_DIR), registry)
    return registry


# At import time: test modules import `_veles_module_wiki.*` at their top.
WIKI_MODULES = _load()


@pytest.fixture(autouse=True)
def _wiki_environment(
    tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch
) -> Iterator[None]:
    """A fresh user home, this registry's layouts on the search path, the wiki
    module loaded, embeddings and the model catalogue kept offline."""
    from veles.core import model_metadata
    from veles.core.layout import discovery
    from veles.modules.embedding import register_embedding_adapter, reset_embedding_adapter

    monkeypatch.setenv("VELES_USER_HOME", str(tmp_path_factory.mktemp("veles-user-home")))
    real_roots = discovery._search_roots
    monkeypatch.setattr(
        discovery,
        "_search_roots",
        lambda project: [*real_roots(project), ("user", REGISTRY_EXTENSIONS)],
    )
    register_embedding_adapter(None)  # no live Ollama probe
    model_metadata._memo = {}
    clear_engine_cache()
    token = set_module_registry(WIKI_MODULES)
    try:
        yield
    finally:
        reset_module_registry(token)
        clear_engine_cache()
        reset_embedding_adapter()
        model_metadata.reset_for_tests()
