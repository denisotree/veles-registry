"""agy's `--output-format stream-json` (agy 1.2.17): `init`, then `step_update`
events (`step_update.text_delta` carries the answer as it streams), then one
`result` (`status`, `response`, `error`, `usage`)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from veles.sdk.providers import ProviderResponse, TokenUsage


def _usage(raw: dict[str, Any]) -> TokenUsage:
    prompt = int(raw.get("input_tokens") or 0)
    out = int(raw.get("output_tokens") or 0)
    return TokenUsage(
        prompt_tokens=prompt,
        completion_tokens=out,
        total_tokens=int(raw.get("total_tokens") or prompt + out),
        cache_read_tokens=int(raw.get("cache_read_tokens") or 0),
        reasoning_tokens=int(raw.get("thinking_tokens") or 0),
    )


@dataclass
class AgyStreamState:
    final_text: str = ""
    fallback_text: str = ""
    usage: TokenUsage = field(default_factory=TokenUsage)
    error: str | None = None

    def absorb(self, event: dict[str, Any]) -> str:
        kind = event.get("event")
        if kind == "step_update":
            chunk = str((event.get("step_update") or {}).get("text_delta") or "")
            self.fallback_text += chunk
            return chunk
        if kind == "result":
            result = event.get("result") or {}
            self.final_text = str(result.get("response") or "")
            if result.get("usage"):
                self.usage = _usage(result["usage"])
            if result.get("status") == "ERROR":
                self.error = str(result.get("error") or "agy reported an error")
        return ""

    def to_response(self, *, raw: Any) -> ProviderResponse:
        text = self.final_text or self.fallback_text
        if self.error and not text:
            hint = " — log in by running `agy` once" if "authentic" in self.error.lower() else ""
            text = f"<agy error: {self.error}{hint}>"
        return ProviderResponse(
            text=text or None,
            tool_calls=[],
            usage=self.usage,
            finish_reason="error" if self.error else "stop",
            raw=raw,
        )
