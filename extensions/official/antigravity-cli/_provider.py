"""agy as a CLI delegate. It runs in `<delegate dir>/agy/`, never the project root:
in headless mode agy writes files in its workspace on its own, and that workspace
must not be the user's project.

Veles' tools reach agy over MCP (the workspace's `.agents/mcp_config.json`). agy
denies every MCP call in headless mode, so the tool-aware build runs it with
`--dangerously-skip-permissions` and lets `_gate.py` — a PreToolUse hook in the
workspace's `.agents/hooks.json`, rewritten before every run — decide instead: Veles'
tools yes, agy's own tools no. The chat-only build keeps agy's own headless denials
and the same gate."""

from __future__ import annotations

import json
import shlex
import subprocess
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any

from veles.sdk.providers import (
    CLIProvider,
    Message,
    delegate_dir,
    format_messages_as_prompt,
    veles_mcp_server,
)

from ._stream import AgyStreamState

if TYPE_CHECKING:
    from veles.sdk import Project

_GATE = Path(__file__).with_name("_gate.py")


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


class AgyProvider(CLIProvider):
    name = "antigravity-cli"
    INSTALL_HINT = (
        "the Antigravity CLI (curl -fsSL https://antigravity.google/cli/install.sh | bash)"
    )

    def __init__(
        self,
        *,
        project: Project | None,
        with_veles_tools: bool = False,
        binary: str = "agy",
        timeout: float = 300.0,
    ) -> None:
        self._workspace = delegate_dir(project) / "agy" if project is not None else None
        tools_config: Path | None = None
        if with_veles_tools and project is not None and self._workspace is not None:
            tools_config = self._workspace / ".agents" / "mcp_config.json"
            _write_json(tools_config, {"mcpServers": {"veles": veles_mcp_server(project)}})
        super().__init__(binary=binary, timeout=timeout, extra_args=(), tools_config=tools_config)

    def _cwd(self) -> str | None:
        """The workspace, with the gate written fresh — every run goes through here."""
        if self._workspace is None:
            raise RuntimeError("antigravity-cli runs inside a Veles project")
        command = f"{shlex.quote(sys.executable)} {shlex.quote(str(_GATE))}"
        gate = {"matcher": "*", "hooks": [{"command": command, "timeout": 10}]}
        _write_json(
            self._workspace / ".agents" / "hooks.json", {"veles-gate": {"PreToolUse": [gate]}}
        )
        return str(self._workspace)

    def _build_cmd(self, messages: list[Message], model: str, *, stream: bool = True) -> list[str]:
        del stream  # always stream-json
        prompt = format_messages_as_prompt(messages)
        cmd = [self._binary, "-p", prompt, "--output-format", "stream-json"]
        if model:
            cmd += ["--model", model]
        if self.supports_tools:
            # agy soft-denies MCP calls headless; the workspace gate decides instead.
            cmd.append("--dangerously-skip-permissions")
        return cmd

    def _new_state(self) -> AgyStreamState:
        return AgyStreamState()

    def mcp_tool_name(self, name: str) -> str:
        return f"veles/{name}"  # agy calls it as call_mcp_tool(ServerName=veles, ToolName=name)

    def list_models(self) -> list[str]:
        out = subprocess.run(
            [self._binary, "models"], capture_output=True, text=True, timeout=60, check=True
        ).stdout
        return [line.split("\t", 1)[0].strip() for line in out.splitlines() if line.strip()]
