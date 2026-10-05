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
3. `veles registry validate .` — the same static checks CI runs. CI also runs
   `--run-code --install-requires`: it installs each module's `requires` (pinned to Veles's
   own versions) and runs its tests against the real SDK. Test-only dependencies CI provides
   are `pytest` and `respx`.
4. Open a pull request. A merge after review publishes it.

Rules:

- Licence must be permissive (Apache-2.0, MIT, BSD, ISC, MPL-2.0, …).
- A new version raises `version` in `extension.toml`.
- An extension kept in its own repository uses a `git` source pinned to a full commit SHA
  and the `sha256` of its files.
- No `__pycache__`, `*.pyc`, `.git` or symlinks in a payload.
- A module imports Veles only through `veles.sdk` (its tests may use anything). A module
  may span several files and import them relatively (`from .helpers import x`).
- An extension that needs another lists it as a full ref:
  `requires_extensions = ["public:official/wiki"]` — installing it installs both under one
  confirmation. A dependency is a module, a layout or a skill (not an `mcp` recipe), so a
  module can build on other modules and bring the skills it uses.
- A module may ship its own skills in `skills/<name>/SKILL.md`; they mount for every project
  that loads the module and are reviewed with the rest of its code.

To withdraw an extension, add `yanked = "reason"` to its `[extension]` table.

## Licence

Each extension carries its own licence in `extension.toml`.
