"""The wiki tools go through Veles' write guard: they cannot take Veles' own state
in `.veles/`, write through a symlinked wiki dir, or repair links in pages the
guard refuses. (Moved from Veles' `test_agent_state_dir_guard.py`.)"""

from __future__ import annotations

from pathlib import Path

import _veles_module_wiki.tools as wt
import pytest
from _veles_module_wiki.wiki import Wiki
from veles.core.context import reset_active_project, set_active_project
from veles.core.project import init_project


@pytest.fixture()
def project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("VELES_TRUST_AUTO_ALLOW", raising=False)
    p = init_project(tmp_path / "proj", name="proj", layout="llm-wiki")
    token = set_active_project(p)
    yield p
    reset_active_project(token)


def _refused(msg: str) -> bool:
    return msg.startswith("<refused:") and "managed by Veles" in msg


def _page(project, rel: str = "wiki/concepts/a.md", body: str = "# A\n\nkeep me\n") -> Path:
    Wiki(project.wiki_root).ensure_layout()
    page = project.root / rel
    page.write_text(body, encoding="utf-8")
    return page


def test_wiki_rename_page_cannot_take_state_files(project) -> None:
    config = project.state_dir / "config.toml"
    config.write_text("[engine]\n", encoding="utf-8")
    msg = wt.wiki_rename_page(".veles/config.toml", "concepts", "stolen")
    assert msg.startswith("<"), msg
    assert config.read_text(encoding="utf-8") == "[engine]\n"
    assert not (project.root / "wiki" / "concepts" / "stolen.md").exists()


def test_wiki_rename_page_only_moves_wiki_pages(project) -> None:
    readme = project.root / "README.md"
    readme.write_text("# R\n", encoding="utf-8")
    assert wt.wiki_rename_page("README.md", "concepts", "r").startswith("<")
    assert readme.exists()


def test_wiki_rename_reports_pages_it_could_not_repair(project, monkeypatch) -> None:
    _page(project, "wiki/concepts/a.md", "# A\n")
    blocked = _page(project, "wiki/concepts/b.md", "# B\n\nsee [[a]]\n")
    real_guard = wt.guard_write
    monkeypatch.setattr(
        wt, "guard_write", lambda p, proj: "<refused>" if p == blocked else real_guard(p, proj)
    )
    msg = wt.wiki_rename_page("wiki/concepts/a.md", "concepts", "c")
    assert "1 page(s) skipped" in msg, msg
    assert "[[a]]" in blocked.read_text(encoding="utf-8")


@pytest.mark.parametrize(
    "spelling",
    [
        "wiki/concepts/a.md",
        "wiki//concepts/a.md",
        "wiki/./concepts/a.md",
        "./wiki/concepts/a.md",
        "WIKI/concepts/a.md",
        "wiki/Concepts/a.md",
    ],
)
def test_wiki_rename_onto_itself_is_a_noop(project, spelling: str) -> None:
    page = _page(project)
    if spelling != spelling.lower() and not (project.root / spelling).exists():
        pytest.skip("case-sensitive filesystem")
    msg = wt.wiki_rename_page(spelling, "concepts", "a")
    assert msg.startswith("<error:") and "same page" in msg, msg
    assert page.read_text(encoding="utf-8") == "# A\n\nkeep me\n"


def test_wiki_write_page_through_symlinked_wiki_dir_refused(project) -> None:
    import shutil

    wiki_dir = project.root / "wiki"
    if wiki_dir.exists():
        shutil.rmtree(wiki_dir)
    wiki_dir.symlink_to(project.state_dir, target_is_directory=True)
    (project.state_dir / "concepts").mkdir(exist_ok=True)
    msg = wt.wiki_write_page("concepts", "pwn", "Pwn", "x")
    assert _refused(msg), msg
    (project.root / "src.md").write_text("# Pwn\n", encoding="utf-8")
    msg = wt.wiki_ingest("src.md", category="concepts", slug="pwn")
    assert _refused(msg), msg
    assert not (project.state_dir / "concepts" / "pwn.md").exists()


def test_wiki_rename_link_repair_skips_guarded_pages(project, monkeypatch) -> None:
    """The link-rewrite loop runs every page it edits through the write guard."""
    _page(project, "wiki/concepts/old.md", "# Old\n")
    other = _page(project, "wiki/concepts/other.md", "see [[old]]\n")
    real_guard = wt.guard_write
    seen: list[Path] = []

    def spy(p, proj):
        seen.append(p)
        return "<refused: test>" if p.name == "other.md" else real_guard(p, proj)

    monkeypatch.setattr(wt, "guard_write", spy)
    assert wt.wiki_rename_page("wiki/concepts/old.md", "concepts", "new").startswith("renamed")
    assert other.read_text(encoding="utf-8") == "see [[old]]\n"
    assert any(p.name == "other.md" for p in seen)


def test_wiki_rename_under_symlinked_project_root_needs_no_confirm(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import veles.core.tools.builtin.fs_write_guard as g
    from veles.core.project import load_project

    real = init_project(tmp_path / "real", name="real", layout="llm-wiki")
    link = tmp_path / "link"
    link.symlink_to(real.root, target_is_directory=True)
    project = load_project(link)
    token = set_active_project(project)
    try:

        def no_confirm(*_a, **_k):
            raise AssertionError("in-project rename must not ask for confirmation")

        monkeypatch.setattr(g, "confirm_critical", no_confirm)
        _page(project, "wiki/concepts/a.md")
        msg = wt.wiki_rename_page("wiki/concepts/a.md", "concepts", "b")
        assert msg.startswith("renamed"), msg
        assert (real.root / "wiki" / "concepts" / "b.md").exists()
    finally:
        reset_active_project(token)
