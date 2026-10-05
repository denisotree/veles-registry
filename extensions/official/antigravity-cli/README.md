# antigravity-cli

The Antigravity CLI (`agy`) as an LLM provider for Veles: run your agents on your
Google subscription.

## Install

Install agy and log in once:

```sh
curl -fsSL https://antigravity.google/cli/install.sh | bash
agy            # one interactive login
```

Then name the provider and Veles installs this module on the next run:

```toml
# .veles/config.toml
[engine]
provider = "antigravity-cli"
model = "gemini-3.8-flash-high"   # `veles models antigravity-cli` lists what your account has
```

`veles run --provider antigravity-cli …` works the same way. By hand:
`veles registry install antigravity-cli`.

## How it runs

agy is only the model. Veles starts it headless (`agy -p … --output-format stream-json`)
in a scratch workspace of its own outside your project, `~/.veles/tmp/agy/<project>-<pid>/`.
agy writes files in its workspace on its own, and it reads every `.agents/` from its
working directory up to the repository root — so it never runs inside the project, where
a cloned repo's own `.agents/` hooks and MCP servers would start.

When the agent needs tools, agy gets Veles' tools over MCP (the workspace's
`.agents/mcp_config.json`) and calls them as `veles/<tool>`; every call goes through
Veles' trust ladder. agy refuses MCP calls in headless mode, so this run uses
`--dangerously-skip-permissions` together with a gate: a PreToolUse hook in the
workspace's `.agents/hooks.json` (rewritten before every run) that allows only Veles'
MCP tools and denies everything else agy has — its shell, its file tools, other MCP
servers, subagents, the browser. A hook that fails makes agy deny the call. A plain chat
run keeps agy's own headless denials and the same gate.

agy keeps the tool schemas of the `veles` MCP server under
`~/.gemini/antigravity-cli/mcp/veles/`.
