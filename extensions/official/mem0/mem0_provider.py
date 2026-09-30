"""Mem0 memory provider module for Veles.

Mem0 (`mem0.ai`) stores entity-scoped memories with hybrid search. This wraps
`mem0.MemoryClient.search(...)` (platform API v3) behind Veles's
`MemoryProvider` protocol. The SDK (`mem0ai`) is imported lazily — this module
has no hard dependency on it at import time — and every failure mode degrades
to an empty recall with a warning on stderr.

Entity ids go through `filters` (the SDK rejects them at the top level). With
`agent_id` set the filter is `user_id OR agent_id`: Mem0 attributes each fact
to one speaker, so an AND of both would match nothing.

Telemetry: the mem0 SDK sends usage telemetry to PostHog unless
`MEM0_TELEMETRY` is false. Veles never phones home, so this adapter sets
`MEM0_TELEMETRY=False` (via `setdefault` — an explicit user setting wins)
before the lazy SDK import; the SDK reads the flag once, when
`mem0.memory.telemetry` is first imported. The SDK also keeps a small
`config.json` (an anonymous `user_id`); the adapter points `MEM0_DIR` at
`~/.veles/cache/mem0` (again via `setdefault`) so nothing lands in `~/.mem0`.

Every recall makes two requests: the SDK's `GET /v1/ping/` key check (the
client is built per recall) and the search itself.

Configuration — only the user config `~/.veles/config.toml` is read (a
project `config.toml` is not; never put API keys there):

    [memory.external.mem0]
    api_key  = "..."
    user_id  = "your-user-id"
    agent_id = "veles"     # optional; also recall this agent's memories
    host     = "https://api.mem0.ai"   # optional; self-hosted endpoint
"""

import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from veles.core.memory.provider import RecallHit

_SUMMARY_CAP = 200

# Local helpers: a module depends only on Veles's public API (`veles.core.memory.provider`).
_warned: set[str] = set()


def warn_once(msg: str) -> None:
    """Print `warning: <msg>` to stderr the first time this exact message is seen."""
    if msg not in _warned:
        _warned.add(msg)
        print(f"warning: {msg}", file=sys.stderr)


def ellipsize(text: str, cap: int) -> str:
    """`text` on one line, cut to `cap` characters with a trailing `…` when longer."""
    line = text.strip().replace("\n", " ")
    return line if len(line) <= cap else line[: cap - 1].rstrip() + "…"


@dataclass(slots=True)
class Mem0MemoryProvider:
    api_key: str
    user_id: str
    agent_id: str | None = None
    host: str | None = None
    name: str = "mem0"

    def recall(self, query: str, *, limit: int) -> list[RecallHit]:
        os.environ.setdefault("MEM0_TELEMETRY", "False")  # must precede the first mem0 import
        os.environ.setdefault("MEM0_DIR", str(_veles_home() / "cache" / "mem0"))
        try:
            from mem0 import MemoryClient
        except ImportError:
            warn_once("mem0ai not installed; skipping Mem0 recall")
            return []
        filters: dict[str, Any] = {"user_id": self.user_id}
        if self.agent_id:
            filters = {"OR": [filters, {"agent_id": self.agent_id}]}
        try:
            client = MemoryClient(api_key=self.api_key, host=self.host)
            response = client.search(query, filters=filters, top_k=limit)
            results = response.get("results") if isinstance(response, dict) else None
            return [_to_recall_hit(r) for r in results or [] if isinstance(r, dict)]
        except Exception as exc:  # an unexpected response shape too
            warn_once(f"Mem0 recall failed: {type(exc).__name__}: {exc}")
            return []


def _veles_home() -> Path:
    """`~/.veles`, or `VELES_USER_HOME` when set — where the SDK's own files go."""
    return Path(os.environ.get("VELES_USER_HOME") or Path.home() / ".veles")


def _to_recall_hit(item: dict[str, Any]) -> RecallHit:
    mem_id = str(item.get("id") or "unknown")
    return RecallHit(
        rel_path=f"mem0:{mem_id}",
        title=f"[mem0] {mem_id}",
        summary=ellipsize(str(item.get("memory") or ""), _SUMMARY_CAP) or "(no summary)",
        score=float(item.get("score") or 0.0),
    )


def _build(cfg: dict[str, Any]) -> Mem0MemoryProvider | None:
    api_key = cfg.get("api_key")
    user_id = cfg.get("user_id")
    if not (api_key and user_id):
        warn_once("[memory.external.mem0] needs api_key and user_id; Mem0 recall is off")
        return None
    return Mem0MemoryProvider(
        api_key=str(api_key),
        user_id=str(user_id),
        agent_id=str(cfg["agent_id"]) if cfg.get("agent_id") else None,
        host=str(cfg["host"]) if cfg.get("host") else None,
    )


def register(api) -> None:  # noqa: ANN001 — ModuleAPI
    api.add_memory_provider("mem0", _build)


__all__ = ["Mem0MemoryProvider"]
