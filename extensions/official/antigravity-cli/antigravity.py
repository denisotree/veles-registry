"""Antigravity CLI (`agy`) as a Veles LLM provider — `antigravity-cli`."""

from __future__ import annotations

from veles.sdk.providers import ProviderContext, ProviderSpec

from ._provider import AgyProvider


def _build(ctx: ProviderContext) -> AgyProvider:
    return AgyProvider(project=ctx.project)


def _build_tool_aware(ctx: ProviderContext) -> AgyProvider:
    return AgyProvider(project=ctx.project, with_veles_tools=True)


SPEC = ProviderSpec(
    label="Antigravity CLI",
    tagline="Google subscription (agy)",
    build=_build,
    build_tool_aware=_build_tool_aware,
    wire="cli",
    model_list="live",
)


def register(api) -> None:
    api.contribute("provider", "antigravity-cli", SPEC)
