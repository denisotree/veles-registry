"""Honcho memory provider module for Veles.

Honcho (`honcho.dev`) keeps conversation messages in a workspace, authored by
peers, and exposes a search over them. This wraps that search as a Veles
`MemoryProvider`. The SDK (`honcho-ai`, imported as `honcho`) is loaded
lazily — this module has no hard dependency on it at import time — and every
failure mode degrades to an empty recall with a warning on stderr.

Configuration (`~/.veles/config.toml` or project `config.toml`):

    [memory.external.honcho]
    api_key      = "..."
    workspace_id = "my-workspace"
    peer_id      = "your-peer-id"            # optional; only this peer's messages
    base_url     = "https://api.honcho.dev"  # optional; self-hosted Honcho
"""

from dataclasses import dataclass
from typing import Any

from veles.core.log_util import warn_once
from veles.core.memory.provider import RecallHit
from veles.core.text import ellipsize

_SUMMARY_CAP = 200
_MAX_LIMIT = 100  # the SDK validates 1 <= limit <= 100


@dataclass(slots=True)
class HonchoMemoryProvider:
    """Searches Honcho messages in `workspace_id`, scoped to `peer_id` when set."""

    api_key: str
    workspace_id: str
    peer_id: str | None = None
    base_url: str | None = None
    name: str = "honcho"

    def recall(self, query: str, *, limit: int) -> list[RecallHit]:
        try:
            from honcho import Honcho, Peer
        except ImportError:
            warn_once("honcho-ai not installed; skipping Honcho recall")
            return []
        try:
            client = Honcho(
                api_key=self.api_key, workspace_id=self.workspace_id, base_url=self.base_url
            )
            # Peer(...) is a local handle (no request); client.peer() would get-or-create.
            source = Peer(self.peer_id, client) if self.peer_id else client
            messages = source.search(query, limit=max(1, min(limit, _MAX_LIMIT)))
        except Exception as exc:
            warn_once(f"Honcho recall failed: {type(exc).__name__}: {exc}")
            return []
        return [_to_recall_hit(m) for m in messages]


def _to_recall_hit(message: Any) -> RecallHit:
    return RecallHit(
        rel_path=f"honcho:{message.id}",
        title=f"[honcho] {message.peer_id} in {message.session_id}",
        summary=ellipsize(message.content, _SUMMARY_CAP) or "(no summary)",
        ts=message.created_at.timestamp(),
    )


def _build(cfg: dict[str, Any]) -> HonchoMemoryProvider | None:
    api_key = cfg.get("api_key")
    workspace_id = cfg.get("workspace_id")
    if not (api_key and workspace_id):
        return None
    return HonchoMemoryProvider(
        api_key=str(api_key),
        workspace_id=str(workspace_id),
        peer_id=str(cfg["peer_id"]) if cfg.get("peer_id") else None,
        base_url=str(cfg["base_url"]) if cfg.get("base_url") else None,
    )


def register(api) -> None:  # noqa: ANN001 — ModuleAPI
    api.add_memory_provider("honcho", _build)


__all__ = ["HonchoMemoryProvider"]
