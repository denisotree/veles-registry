"""Supermemory memory provider module for Veles.

Supermemory (`supermemory.ai`) is a search-over-memories API. Same
lazy-import + soft-degradation contract as the other external memory
provider modules — this module has no hard dependency on `supermemory`
at import time.

The Supermemory Python SDK exposes `Supermemory(api_key).search(q=...)`
in current versions. We duck-type the call so a small SDK rename
doesn't kill us — anything returning a list (or a dict with results/
items/memories) is unpacked into RecallHit.

Configuration (`~/.veles/config.toml` or project `config.toml`):

    [memory.external.supermemory]
    api_key = "..."
    user_id = "your-user-id" # optional; included if set
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
    name: str = "supermemory"

    def recall(self, query: str, *, limit: int) -> list[RecallHit]:
        try:
            from supermemory import Supermemory  # type: ignore[import-not-found]
        except ImportError:
            warn_once("supermemory not installed; skipping Supermemory recall")
            return []
        try:
            client = Supermemory(api_key=self.api_key)
        except Exception as exc:
            warn_once(f"Supermemory client init failed: {type(exc).__name__}: {exc}")
            return []
        response = self._search(client, query, limit)
        if response is None:
            return []
        return [_to_recall_hit(item) for item in _iter_items(response)]

    def _search(self, client: Any, query: str, limit: int) -> Any | None:
        """Run client.search with `q=` first, fall back to `query=` for SDK
        versions that renamed the argument. Any other failure → None (caller
        skips the recall)."""
        base: dict[str, Any] = {"limit": limit}
        if self.user_id:
            base["user_id"] = self.user_id
        for keyword in ("q", "query"):
            try:
                return client.search(**{keyword: query, **base})
            except TypeError:
                continue  # try next keyword
            except Exception as exc:
                warn_once(f"Supermemory recall failed: {type(exc).__name__}: {exc}")
                return None
        warn_once("Supermemory.search rejected both `q=` and `query=`; SDK changed shape")
        return None


def _iter_items(response: Any) -> list[dict[str, Any]]:
    if isinstance(response, list):
        return [r for r in response if isinstance(r, dict)]
    if isinstance(response, dict):
        for key in ("results", "memories", "items", "documents"):
            v = response.get(key)
            if isinstance(v, list):
                return [r for r in v if isinstance(r, dict)]
    return []


def _to_recall_hit(item: dict[str, Any]) -> RecallHit:
    mem_id = str(item.get("id") or item.get("memory_id") or "supermemory:unknown")
    content = str(item.get("content") or item.get("memory") or item.get("text") or "")
    summary = ellipsize(content, _SUMMARY_CAP)
    title = str(item.get("title") or mem_id)
    score = float(item.get("score", 0.0) or 0.0)
    return RecallHit(
        rel_path=f"supermemory:{mem_id}",
        title=f"[supermemory] {title}",
        summary=summary or "(no summary)",
        score=score,
    )


def _build(cfg: dict[str, Any]) -> SupermemoryProvider | None:
    api_key = cfg.get("api_key")
    if not api_key:
        return None
    return SupermemoryProvider(
        api_key=str(api_key),
        user_id=str(cfg["user_id"]) if cfg.get("user_id") else None,
    )


def register(api) -> None:  # noqa: ANN001 — ModuleAPI
    api.add_memory_provider("supermemory", _build)


__all__ = ["SupermemoryProvider"]
