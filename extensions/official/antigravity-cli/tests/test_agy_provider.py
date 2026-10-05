"""agy as a provider: a scratch workspace, headless stream-json, Veles' tools over
MCP behind a gate that denies agy every tool of its own."""

from __future__ import annotations

import importlib
import json
import subprocess
import sys
from pathlib import Path

from veles.core.project import init_project
from veles.sdk.providers import Message, ProviderContext, delegate_workspace

_PKG = "_veles_module_antigravity-cli"
SPEC = importlib.import_module(_PKG).SPEC
AgyProvider = importlib.import_module(f"{_PKG}._provider").AgyProvider
GATE = Path(importlib.import_module(f"{_PKG}._gate").__file__)


def _project(tmp_path: Path):
    return init_project(tmp_path / "p", name="p")


def test_agy_runs_in_a_workspace_outside_the_project(tmp_path: Path) -> None:
    """agy reads every `.agents/` from its working directory up to the repo root —
    inside the project it would start a cloned repo's MCP servers and hooks."""
    project = _project(tmp_path)
    prov = SPEC.build(ProviderContext(name="antigravity-cli", project=project))
    workspace = Path(prov._cwd())
    assert workspace == delegate_workspace(project, "agy")
    assert not workspace.is_relative_to(project.root)


def test_a_leftover_temp_name_never_blocks_the_gate(tmp_path: Path) -> None:
    """Two runs in one daemon write the gate at once; a fixed temp name collides."""
    project = _project(tmp_path)
    prov = SPEC.build(ProviderContext(name="antigravity-cli", project=project))
    (delegate_workspace(project, "agy") / ".agents" / "hooks.tmp").mkdir(parents=True)
    prov._cwd()
    assert (delegate_workspace(project, "agy") / ".agents" / "hooks.json").is_file()


def test_the_command_is_headless_stream_json(tmp_path: Path) -> None:
    prov = AgyProvider(project=_project(tmp_path))
    cmd = prov._build_cmd([Message(role="user", content="hi")], "gemini-3.8-flash-low")
    assert cmd[:2] == ["agy", "-p"] and cmd[cmd.index("--output-format") + 1] == "stream-json"
    assert cmd[cmd.index("--model") + 1] == "gemini-3.8-flash-low"
    assert "--dangerously-skip-permissions" not in cmd  # chat-only: agy's own headless denials


def test_the_tool_aware_build_wires_the_veles_server_behind_the_gate(tmp_path: Path) -> None:
    project = _project(tmp_path)
    prov = SPEC.build_tool_aware(ProviderContext(name="antigravity-cli", project=project))
    agents = delegate_workspace(project, "agy") / ".agents"
    config = json.loads((agents / "mcp_config.json").read_text(encoding="utf-8"))
    assert "veles" in config["mcpServers"] and prov.supports_tools
    cmd = prov._build_cmd([Message(role="user", content="hi")], "")
    assert "--dangerously-skip-permissions" in cmd and "--model" not in cmd
    assert prov.qualify_prompt("use read_file", ("read_file",)) == "use veles/read_file"


def test_the_gate_is_rewritten_before_every_run(tmp_path: Path) -> None:
    project = _project(tmp_path)
    prov = SPEC.build_tool_aware(ProviderContext(name="antigravity-cli", project=project))
    hooks = delegate_workspace(project, "agy") / ".agents" / "hooks.json"
    hooks.write_text("{}", encoding="utf-8")  # tampered or lost
    prov._cwd()
    command = json.loads(hooks.read_text(encoding="utf-8"))["veles-gate"]["PreToolUse"][0]
    assert command["matcher"] == "*" and str(GATE) in command["hooks"][0]["command"]


def _gate(call: dict) -> str:
    out = subprocess.run(
        [sys.executable, str(GATE)],
        input=json.dumps({"toolCall": call}),
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    return json.loads(out)["decision"]


def test_the_gate_lets_through_only_veles_tools() -> None:
    schemas = Path("~/.gemini/antigravity-cli/mcp/veles").expanduser()
    veles = {"ServerName": "veles", "ToolName": "read_file", "Arguments": {"path": "x"}}
    assert _gate({"name": "call_mcp_tool", "args": veles}) == "allow"
    assert _gate({"name": "view_file", "args": {"AbsolutePath": str(schemas / "a.json")}}) == (
        "allow"
    )
    other = {"ServerName": "context7", "ToolName": "q", "Arguments": {}}
    assert _gate({"name": "call_mcp_tool", "args": other}) == "deny"
    assert _gate({"name": "run_command", "args": {"CommandLine": "echo hi"}}) == "deny"
    assert _gate({"name": "write_to_file", "args": {"TargetFile": "x"}}) == "deny"
    escape = str(schemas / ".." / ".." / ".." / ".ssh" / "id_rsa")
    assert _gate({"name": "view_file", "args": {"AbsolutePath": escape}}) == "deny"


def test_models_come_from_agy_run_in_its_workspace(monkeypatch, tmp_path: Path) -> None:
    out = "gemini-3.8-flash-high\tGemini 3.8 Flash (High)\nclaude-sonnet-4-6\tClaude Sonnet 4.6\n"
    seen: list[str] = []

    def fake_run(cmd, **kw):
        assert cmd[-1] == "models"
        seen.append(kw.get("cwd"))
        return subprocess.CompletedProcess(cmd, 0, stdout=out, stderr="")

    project = _project(tmp_path)
    monkeypatch.setattr(subprocess, "run", fake_run)
    prov = AgyProvider(project=project)
    assert prov.list_models() == ["gemini-3.8-flash-high", "claude-sonnet-4-6"]
    assert seen == [str(delegate_workspace(project, "agy"))]
