# veles-registry

The official public registry of [Veles](https://github.com/denisotree/veles) extensions:
reviewed modules, skills, layout packs and MCP server recipes.

Every extension here was merged after review. `extensions/official/` is maintained by the
Veles author; `extensions/community/` holds reviewed contributions.

## Use

This registry is built into Veles as `public` — nothing to connect.

    veles registry update                # fetch the latest contents
    veles registry search [query] [--kind module|skill|layout|mcp]
    veles registry install <name>        # or public:<group>/<name>
    veles registry verify                # changed, yanked, removed or outdated installs

Installing always asks you to confirm. A module loads only while its files match what you
installed or approved.

## Contribute

1. Fork this repository.
2. `veles registry scaffold <module|skill|layout|mcp> <name> --group community --root .`
3. `veles registry validate .` — the same static checks CI runs (CI also runs `--run-code`).
   CI installs only Veles and pytest, never an extension's `requires`, so tests that drive
   a real SDK skip there. Run them locally with the SDK installed.
4. Open a pull request. A merge after review publishes it.

Rules:

- Licence must be permissive (Apache-2.0, MIT, BSD, ISC, MPL-2.0, …).
- A new version raises `version` in `extension.toml`.
- An extension kept in its own repository uses a `git` source pinned to a full commit SHA
  and the `sha256` of its files.
- No `__pycache__`, `*.pyc`, `.git` or symlinks in a payload.

To withdraw an extension, add `yanked = "reason"` to its `[extension]` table.

## Licence

Each extension carries its own licence in `extension.toml`.
