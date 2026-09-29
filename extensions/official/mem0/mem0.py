"""Mem0 memory provider module for Veles.

Mem0 (`mem0.ai`) stores user-scoped memories with vector + metadata
search. This wraps `mem0ai.MemoryClient.search(...)` behind Veles's
`MemoryProvider` protocol. The SDK is imported lazily — this module
has no hard dependency on `mem0ai` at import time — and every failure
mode degrades silently to an empty recall.

Configuration (`~/.veles/config.toml` or project `config.toml`):

    [memory.external.mem0]
    api_key  = "..."
    user_id  = "your-user-id"
    agent_id = "veles"     # optional; identifies the calling agent
"""

from dataclasses import dataclass
from typing import Any

from veles.core.log_util import warn_once
from veles.core.memory.provider import RecallHit
from veles.core.text import ellipsize

_SUMMARY_CAP = 200


@dataclass(slots=True)
class Mem0MemoryProvider:
    api_key: str
    user_id: str
    agent_id: str | None = None
    name: str = "mem0"

    def recall(self, query: str, *, limit: int) -> list[RecallHit]:
        try:
            from mem0 import MemoryClient  # type: ignore[import-not-found]
        except ImportError:
            warn_once("mem0ai not installed; skipping Mem0 recall")
            return []
        try:
            client = MemoryClient(api_key=self.api_key)
            kwargs: dict[str, Any] = {"query": query, "user_id": self.user_id, "limit": limit}
            if self.agent_id:
                kwargs["agent_id"] = self.agent_id
            response = client.search(**kwargs)
        except Exception as exc:
            warn_once(f"Mem0 recall failed: {type(exc).__name__}: {exc}")
            return []
        return [_to_recall_hit(item) for item in _iter_items(response)]


def _iter_items(response: Any) -> list[dict[str, Any]]:
    """Mem0 historically returned `{results: [...]}` and is moving to a
    plain list. Handle both."""
    if isinstance(response, list):
        return [r for r in response if isinstance(r, dict)]
    if isinstance(response, dict):
        for key in ("results", "memories", "items"):
            v = response.get(key)
            if isinstance(v, list):
                return [r for r in v if isinstance(r, dict)]
    return []


def _to_recall_hit(item: dict[str, Any]) -> RecallHit:
    mem_id = str(item.get("id") or item.get("memory_id") or "mem0:unknown")
    memory = str(item.get("memory") or item.get("text") or "")
    summary = ellipsize(memory, _SUMMARY_CAP)
    score = float(item.get("score", 0.0) or 0.0)
    return RecallHit(
        rel_path=f"mem0:{mem_id}",
        title=f"[mem0] {mem_id}",
        summary=summary or "(no summary)",
        score=score,
    )


def _build(cfg: dict[str, Any]) -> Mem0MemoryProvider | None:
    api_key = cfg.get("api_key")
    user_id = cfg.get("user_id")
    if not (api_key and user_id):
        return None
    return Mem0MemoryProvider(
        api_key=str(api_key),
        user_id=str(user_id),
        agent_id=str(cfg["agent_id"]) if cfg.get("agent_id") else None,
    )


def register(api) -> None:  # noqa: ANN001 — ModuleAPI
    api.add_memory_provider("mem0", _build)


__all__ = ["Mem0MemoryProvider"]
