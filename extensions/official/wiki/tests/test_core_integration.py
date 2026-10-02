"""The wiki through Veles' core: recall (with subprojects and turns), self-doc,
subproject clustering, the REPL's /save and /wiki, and the agent write guard on
wiki tools. Moved from Veles' own suite when the wiki left the core (1.2.3)."""

from __future__ import annotations

from pathlib import Path

from _veles_module_wiki.wiki import Wiki
from veles.core.memory.router import MemoryRouter
from veles.core.project import init_project
from veles.core.subproject import init_subproject


def _wiki_project(path: Path, name: str = "root"):
    return init_project(path / name, name=name, layout="llm-wiki")


# ---------- recall over subprojects ----------


def test_recall_includes_subproject_hits(tmp_path: Path) -> None:
    parent = _wiki_project(tmp_path)
    child = init_subproject(parent, "frontend")
    # Seed pages: parent has nothing matching, child has a page on "auth".
    Wiki(child.wiki_root).write_page(
        slug="auth", title="Auth flow", category="concepts", content="OAuth pkce details"
    )
    hits = MemoryRouter(parent).recall("OAuth pkce")
    assert any(h.rel_path.startswith("frontend:") for h in hits)
    sub_hit = next(h for h in hits if h.rel_path.startswith("frontend:"))
    assert sub_hit.title.startswith("[frontend]")


def test_recall_caps_total_hits(tmp_path: Path) -> None:
    parent = _wiki_project(tmp_path)
    child = init_subproject(parent, "frontend")
    parent_wiki = Wiki(parent.wiki_root)
    child_wiki = Wiki(child.wiki_root)
    for i in range(5):
        parent_wiki.write_page(
            slug=f"p{i}", title=f"Parent {i}", category="concepts", content="auth flow"
        )
        child_wiki.write_page(
            slug=f"c{i}", title=f"Child {i}", category="concepts", content="auth flow"
        )
    hits = MemoryRouter(parent).recall("auth flow", limit=5)
    assert len(hits) <= 5


def _seed(project, pages: list[tuple[str, str, str, str]]) -> None:
    wiki = Wiki(project.wiki_root)
    for category, slug, title, content in pages:
        wiki.write_page(category=category, slug=slug, title=title, content=content)


def test_recall_returns_pages_matching_query(tmp_path: Path) -> None:
    project = _wiki_project(tmp_path)
    _seed(
        project,
        [
            ("concepts", "llm-wiki", "LLM Wiki", "Karpathy three-layer pattern: sources, wiki."),
            ("entities", "anthropic", "Anthropic", "AI safety company building Claude."),
            ("concepts", "tokens", "Token Budget", "TokenBudget tracks cumulative LLM cost."),
        ],
    )
    paths = [h.rel_path for h in MemoryRouter(project).recall("Karpathy three-layer")]
    assert "wiki/concepts/llm-wiki.md" in paths


def test_recall_respects_limit(tmp_path: Path) -> None:
    project = _wiki_project(tmp_path)
    _seed(
        project,
        [
            ("concepts", f"page-{i}", f"Page {i}", f"Repeats keyword karpathy {i} times.")
            for i in range(8)
        ],
    )
    assert len(MemoryRouter(project).recall("karpathy", limit=3)) <= 3


def test_run_prompt_carries_matching_wiki_pages(tmp_path: Path) -> None:
    import argparse

    from veles.runtime.prompt import system_prompt_from_args

    project = _wiki_project(tmp_path)
    _seed(project, [("concepts", "karpathy-wiki", "Karpathy Wiki", "Three-layer LLM Wiki.")])
    args = argparse.Namespace(
        prompt="Karpathy three-layer wiki", no_agents_md=False, no_index=False, provider="x"
    )
    prompt = system_prompt_from_args(args, project)
    assert prompt is not None
    assert "<memory-context>" in prompt
    assert "wiki/concepts/karpathy-wiki.md" in prompt


def test_recall_without_store_is_wiki_only(tmp_path: Path) -> None:
    project = _wiki_project(tmp_path)
    Wiki(project.wiki_root).write_page(
        category="concepts", slug="alpha", title="Alpha", content="alpha topic body"
    )
    out = MemoryRouter(project).recall("alpha", limit=5)
    assert any(h.rel_path == "wiki/concepts/alpha.md" for h in out)
    assert not any(h.rel_path.startswith("turn:") for h in out)


def test_recall_with_wiki_and_turns_caps_at_limit(tmp_path: Path) -> None:
    from veles.core.memory import SessionStore
    from veles.core.provider import Message

    project = _wiki_project(tmp_path)
    wiki = Wiki(project.wiki_root)
    for i in range(10):
        wiki.write_page(
            category="concepts", slug=f"w{i}", title=f"W{i}", content="overflowtoken body"
        )
    store = SessionStore(project.memory_db_path)
    try:
        sid = store.create_session()
        for i in range(10):
            store.append_turn(sid, Message(role="user", content=f"overflowtoken turn {i}"))
        out = MemoryRouter(project, store=store).recall("overflowtoken", limit=3)
    finally:
        store.close()
    assert len(out) == 3


# ---------- tools and system prompt ----------


def test_wiki_tools_in_the_agent_registry(tmp_path: Path) -> None:
    from types import SimpleNamespace

    from veles.runtime.registry import RUN_TOOLS, load_skills

    project = _wiki_project(tmp_path, "w")
    provider = SimpleNamespace(name="stub", supports_tools=True)
    names = set(load_skills(project, RUN_TOOLS, provider=provider, model="m").list_names())
    assert {"wiki_search", "wiki_write_page"} <= names


def test_tool_set_is_engine_bound() -> None:
    from veles.core.contributions import ToolSet, contributions

    sets = [c.obj for c in contributions("tool") if c.name == "wiki"]
    assert len(sets) == 1 and isinstance(sets[0], ToolSet) and sets[0].engine == "wiki"
    assert {"wiki_search", "wiki_write_page"} <= set(sets[0].tools)


def test_prompt_injects_the_index(tmp_path: Path) -> None:
    from veles.runtime.prompt import build_run_system_prompt

    project = _wiki_project(tmp_path, "w")
    (project.root / "INDEX.md").write_text(
        "# INDEX\n\n- [page](wiki/concepts/page.md)\n", encoding="utf-8"
    )
    prompt = build_run_system_prompt(project, prompt="anything")
    assert prompt is not None
    assert "Knowledge base index" in prompt and "wiki/concepts/page.md" in prompt


def test_workspace_block_lists_root_and_wiki_tree(tmp_path: Path) -> None:
    """The model must SEE the real folder names (the fix for guessing at
    `-- Daily --/` and wrongly concluding nothing exists)."""
    from veles.runtime.prompt import build_run_system_prompt

    project = _wiki_project(tmp_path, "w")
    (project.root / "-- Daily --").mkdir()
    (project.root / "-- Daily --" / "daily-log.md").write_text("x", encoding="utf-8")
    (project.root / "wiki" / "concepts").mkdir(parents=True, exist_ok=True)
    (project.root / "wiki" / "concepts" / "mde.md").write_text("x", encoding="utf-8")
    prompt = build_run_system_prompt(project, prompt="migrate diaries")
    assert prompt is not None
    assert "<workspace>" in prompt
    assert "-- Daily --/" in prompt
    assert "Current wiki structure" in prompt and "mde.md" in prompt
    assert ".veles/" not in prompt


def test_llm_wiki_prompt_is_byte_identical_to_veles_1_2_1(tmp_path: Path, monkeypatch) -> None:
    """The stable prompt of an llm-wiki project is a cache prefix: moving the wiki
    blocks out of Veles must not change it by a byte (snapshot from Veles 1.2.1)."""
    import veles.runtime.prompt as prompt_mod

    monkeypatch.setattr(prompt_mod, "_runtime_clock_block", lambda: "<clock>")
    project = init_project(tmp_path / "llm-wiki", name="snap", layout="llm-wiki")
    (project.root / "notes.md").write_text("x")
    out = prompt_mod.build_run_system_prompt(project, prompt="")
    expected = (Path(__file__).parent / "fixtures" / "prompt-llm-wiki.txt").read_text(
        encoding="utf-8"
    )
    assert out is not None
    assert out.replace(str(project.root), "<ROOT>") == expected


def test_init_scaffolds_the_wiki_tree(tmp_path: Path) -> None:
    """The wiki sits in the project root, not under `.veles/`; raw sources live
    in top-level `sources/`, never as a wiki category (M203)."""
    project = _wiki_project(tmp_path, "w")
    for category in ("concepts", "entities", "queries"):
        assert (project.root / "wiki" / category).is_dir()
    assert (project.root / "sources").is_dir()
    assert not (project.root / "wiki" / "sources").exists()
    assert not (project.state_dir / "wiki").exists()


# ---------- REPL: /save and /wiki ----------


def _slash(tmp_path: Path):
    from veles.cli.repl.slash import build_default_registry
    from veles.cli.repl.slash.registry import SlashContext
    from veles.core.memory import SessionStore
    from veles.core.session_state import AppState

    project = _wiki_project(tmp_path, "proj")
    state = AppState(session_id=None, provider_name="stub", model="m")
    ctx = SlashContext(state=state, project=project, store=SessionStore(project.memory_db_path))
    return build_default_registry(project), ctx


def test_save_writes_to_queries(tmp_path: Path) -> None:
    reg, ctx = _slash(tmp_path)
    ctx.state.last_assistant_text = "# Hello\n\nNote body."
    res = reg.dispatch("/save hello-note", ctx)
    assert res is not None and not res.is_error
    assert "wiki/queries/hello-note.md" in res.text
    body = Wiki(ctx.project.wiki_root).read_page("wiki/queries/hello-note.md")
    assert "Note body." in body


def test_wiki_command_is_listed_and_usage_on_no_args(tmp_path: Path) -> None:
    reg, ctx = _slash(tmp_path)
    help_text = reg.dispatch("/help", ctx)
    assert help_text is not None and "/wiki" in help_text.text
    res = reg.dispatch("/wiki", ctx)
    assert res is not None and res.is_error
    assert "add" in res.text and "query" in res.text


def test_wiki_add_and_query_queue_prompts(tmp_path: Path) -> None:
    reg, ctx = _slash(tmp_path)
    add = reg.dispatch("/wiki add https://example.com/post", ctx)
    assert add is not None and not add.is_error and add.submit_prompt is not None
    assert "https://example.com/post" in add.submit_prompt and "Ingest" in add.submit_prompt
    query = reg.dispatch("/wiki query what do we know about quokkas", ctx)
    assert query is not None and not query.is_error and query.submit_prompt is not None
    assert "quokkas" in query.submit_prompt and "wiki_search" in query.submit_prompt


def test_wiki_command_errors(tmp_path: Path) -> None:
    reg, ctx = _slash(tmp_path)
    for line in ("/wiki add", "/wiki query", "/wiki dance"):
        res = reg.dispatch(line, ctx)
        assert res is not None and res.is_error, line


def test_wiki_command_absent_on_a_bare_project(tmp_path: Path) -> None:
    from veles.cli.repl.slash import build_default_registry

    bare = init_project(tmp_path / "b", name="b", layout="bare")
    assert "/wiki" not in build_default_registry(bare).names()


# ---------- the delegated CLI's MCP child ----------


def test_mcp_child_lists_wiki_tools_when_installed(tmp_path: Path, monkeypatch) -> None:
    """A delegated claude-cli reaches the wiki tools through Veles' MCP child,
    which loads the installed (approved) wiki module itself."""
    import contextvars
    import io
    import json
    import shutil

    from veles.adapters.cli.mcp_server import main
    from veles.core.registry.gate import approve_module
    from veles.core.user_paths import user_modules_dir

    module_dir = Path(__file__).resolve().parent.parent
    installed = user_modules_dir() / "wiki"
    shutil.copytree(module_dir, installed, ignore=shutil.ignore_patterns("__pycache__", "tests"))
    approve_module(installed, name="wiki", project_root=None)
    project = _wiki_project(tmp_path, "proj")
    request = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/list"}) + "\n"
    monkeypatch.setattr("sys.stdin", io.StringIO(request))
    out = io.StringIO()
    monkeypatch.setattr("sys.stdout", out)
    contextvars.copy_context().run(main, ["--project-root", str(project.root)])
    names = {t["name"] for t in json.loads(out.getvalue().splitlines()[0])["result"]["tools"]}
    assert {"wiki_read_page", "wiki_write_page"} <= names


# ---------- curator ----------


def test_wiki_project_curates_into_wiki_pages(tmp_path: Path) -> None:
    from veles.runtime.learning import curation_plan

    plan = curation_plan(_wiki_project(tmp_path, "w"), "sess-1")
    assert "wiki_write_page" in plan.persist_steps
    assert "wiki_write_page" in plan.persist_tools


# ---------- self-doc ----------


def test_self_doc_counts_wiki_pages(tmp_path: Path) -> None:
    from veles.core.self_doc import generate_self_doc

    project = _wiki_project(tmp_path)
    Wiki(project.wiki_root).write_page(
        category="concepts", slug="alpha", title="Alpha", content="## Alpha\n\nHello."
    )
    assert generate_self_doc(project).wiki_page_count == 1


def test_self_doc_lands_in_the_wiki_once(tmp_path: Path) -> None:
    from veles.core.self_doc import read_self_doc, refresh_self_doc

    project = _wiki_project(tmp_path)
    rel = refresh_self_doc(project)
    refresh_self_doc(project)
    assert rel == "wiki/self-doc/overview.md"
    assert "# Self-Documentation" in (project.root / rel).read_text(encoding="utf-8")
    pages = [p for p in Wiki(project.wiki_root).list_pages() if p.category == "self-doc"]
    assert len(pages) == 1
    assert "# Self-Documentation" in (read_self_doc(project) or "")
