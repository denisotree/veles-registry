"""Supermemory memory provider module for Veles.

Supermemory (`supermemory.ai`) is a search-over-memories API. This wraps
`Supermemory.search.memories(...)` (`POST /v4/search`, the low-latency memory
search) behind Veles's `MemoryProvider` protocol. The SDK is imported lazily —
this module has no hard dependency on `supermemory` at import time — and every
failure mode degrades to an empty recall with a warning on stderr.

Configuration (`~/.veles/config.toml` or project `config.toml`):

    [memory.external.supermemory]
    api_key  = "..."
    user_id  = "your-user-id"   # optional; sent as the search's container_tag
    base_url = "https://api.supermemory.ai"   # optional
"""

from dataclasses import dataclass
from typing import Any

from veles.core.log_util import warn_once
from veles.core.memory.provider import RecallHit
from veles.core.text import ellipsize

_SUMMARY_CAP = 200


@dataclass(slots=True)
class SupermemoryProvider:
    api_key: str
    user_id: str | None = None
    base_url: str | None = None
    name: str = "supermemory"

    def recall(self, query: str, *, limit: int) -> list[RecallHit]:
        try:
            from supermemory import Supermemory
        except ImportError:
            warn_once("supermemory not installed; skipping Supermemory recall")
            return []
        kwargs: dict[str, Any] = {"q": query, "limit": limit}
        if self.user_id:
            kwargs["container_tag"] = self.user_id
        try:
            client = Supermemory(api_key=self.api_key, base_url=self.base_url)
            response = client.search.memories(**kwargs)
        except Exception as exc:
            warn_once(f"Supermemory recall failed: {type(exc).__name__}: {exc}")
            return []
        return [_to_recall_hit(r) for r in response.results]


def _to_recall_hit(result: Any) -> RecallHit:
    # A memory result carries `memory`; a document-chunk result carries `chunk`.
    content = result.memory or result.chunk or ""
    return RecallHit(
        rel_path=f"supermemory:{result.id}",
        title=f"[supermemory] {result.id}",
        summary=ellipsize(content, _SUMMARY_CAP) or "(no summary)",
        score=float(result.similarity),
    )


def _build(cfg: dict[str, Any]) -> SupermemoryProvider | None:
    api_key = cfg.get("api_key")
    if not api_key:
        return None
    return SupermemoryProvider(
        api_key=str(api_key),
        user_id=str(cfg["user_id"]) if cfg.get("user_id") else None,
        base_url=str(cfg["base_url"]) if cfg.get("base_url") else None,
    )


def register(api) -> None:  # noqa: ANN001 — ModuleAPI
    api.add_memory_provider("supermemory", _build)


__all__ = ["SupermemoryProvider"]
