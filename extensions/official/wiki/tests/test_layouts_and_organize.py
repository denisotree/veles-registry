"""The registry's llm-wiki and notes layouts with the wiki engine: their organize
recipes resolve, `wiki_rename_page` repairs links, and the batch-add collector
skips dot-dirs. (Moved from Veles' own `test_organize.py`.)"""

from __future__ import annotations

from pathlib import Path

from veles.core.context import reset_active_project, set_active_project
from veles.core.project import init_project
from veles.modules.organize.dispatcher import resolve_operation


def test_llm_wiki_resolves_organize(tmp_path: Path) -> None:
    p = init_project(tmp_path / "w", name="w", layout="llm-wiki")
    resolved = resolve_operation(p, "organize")
    assert resolved is not None
    assert resolved.skill == "organize"
    assert "wiki" in resolved.body.lower()


def test_notes_resolves_organize(tmp_path: Path) -> None:
    p = init_project(tmp_path / "n", name="n", layout="notes")
    resolved = resolve_operation(p, "organize")
    assert resolved is not None
    assert "notes/" in resolved.body


def test_llm_wiki_declares_its_operations(tmp_path: Path) -> None:
    from veles.core.layout.discovery import find_layout

    pack = find_layout("llm-wiki", None)
    assert pack is not None
    assert {"ingest", "query", "lint", "organize"} <= {op.name for op in pack.manifest.operations}
    assert pack.manifest.engine_enabled("wiki")
    assert pack.manifest.context_file == "INDEX.md"
    assert pack.manifest.agents_md_template == "templates/AGENTS.md"


def test_llm_wiki_init_writes_its_agents_md_and_sources(tmp_path: Path) -> None:
    project = init_project(tmp_path / "p", name="p", layout="llm-wiki")
    assert (project.root / "sources").is_dir()
    agents = (project.root / "AGENTS.md").read_text(encoding="utf-8")
    assert agents.startswith("# p\n") and "wiki/" in agents and "{name}" not in agents


def test_structure_design_ships_with_llm_wiki(tmp_path: Path) -> None:
    """The structure_design skill designs a wiki structure from the user's
    description and scaffolds it — its tool budget must include the runtime
    category-declaration tool, and its body must NOT bake in a fixed schema."""
    from veles.core.skills import mount_layout_skills

    project = init_project(tmp_path / "w", name="w", layout="llm-wiki")
    by_name = {s.name: s for s in mount_layout_skills(project)}
    assert {"ingest", "query", "lint", "organize", "structure_design"} <= set(by_name)
    skill = by_name["structure_design"]
    assert "wiki_add_category" in skill.tools and "make_dir" in skill.tools
    assert {"data_type"} <= {p["name"] for p in skill.parameters}
    assert "hardcode" in skill.body.lower() and "{data_type}" in skill.body
    assert "wiki_write_page" in by_name["ingest"].tools


def test_wiki_rename_page_moves_and_repairs_links(tmp_path: Path) -> None:
    import _veles_module_wiki.tools as wt
    from _veles_module_wiki.wiki import Wiki

    project = init_project(tmp_path / "proj", name="proj", layout="llm-wiki")
    token = set_active_project(project)
    try:
        wiki = Wiki(project.wiki_root)
        wiki.write_page(category="queries", slug="old-note", title="Old Note", content="raw")
        wiki.write_page(
            category="concepts", slug="topic", title="Topic", content="See [[old-note]]."
        )
        msg = wt.wiki_rename_page("wiki/queries/old-note.md", "concepts", "new-note")
    finally:
        reset_active_project(token)
    assert "renamed" in msg
    assert (project.wiki_root / "wiki" / "concepts" / "new-note.md").is_file()
    assert not (project.wiki_root / "wiki" / "queries" / "old-note.md").exists()
    topic = (project.wiki_root / "wiki" / "concepts" / "topic.md").read_text(encoding="utf-8")
    assert "[[new-note]]" in topic and "[[old-note]]" not in topic


def test_rename_page_is_a_wiki_tool() -> None:
    from _veles_module_wiki import WIKI_TOOLS

    assert "wiki_rename_page" in WIKI_TOOLS


def test_batch_ingest_skips_dot_dirs(tmp_path: Path) -> None:
    from _veles_module_wiki.ingest import batch_ingest_files

    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "a.md").write_text("a", encoding="utf-8")
    (tmp_path / "docs" / "b.md").write_text("b", encoding="utf-8")
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "config.md").write_text("x", encoding="utf-8")
    (tmp_path / "notes.txt").write_text("t", encoding="utf-8")
    assert {p.name for p in batch_ingest_files(tmp_path, "*.md")} == {"a.md", "b.md"}


def test_fts_uses_the_shared_escaper() -> None:
    """Wiki is one of the recall streams — a long prompt must reach wiki pages
    through the same escaper turns and insights use."""
    from _veles_module_wiki.wiki import _fts_escape
    from veles.sdk.memory import escape_query

    assert _fts_escape is escape_query
