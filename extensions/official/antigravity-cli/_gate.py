"""agy's PreToolUse hook (the `hooks.json` of agy's workspace runs this file).

agy may call Veles' MCP tools and read their schemas, which agy keeps under
`~/.gemini/antigravity-cli/mcp/veles/`; every other tool — its shell, its file
tools, other MCP servers, subagents, the browser — is denied, so agy reaches the
project only through Veles and its trust ladder. A hook that fails makes agy deny
the call, so the gate fails closed.

Plain Python with no imports from Veles: agy runs it as a separate process.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

_SCHEMAS = Path("~/.gemini/antigravity-cli/mcp/veles")


def decide(call: dict) -> dict:
    name = call.get("name", "")
    args = call.get("args") or {}
    if name == "call_mcp_tool" and args.get("ServerName") == "veles":
        return {"decision": "allow"}
    if name == "view_file":
        # Resolved, so `mcp/veles/../../..` or a symlink can't step out.
        target = Path(str(args.get("AbsolutePath") or "/")).resolve()
        if target.parent == _SCHEMAS.expanduser().resolve():
            return {"decision": "allow"}
    return {"decision": "deny", "reason": "only the veles MCP tools are available here"}


if __name__ == "__main__":
    print(json.dumps(decide(json.load(sys.stdin).get("toolCall") or {})))
