"""M204 Phase 2: async-by-context `wiki_add`.

Under a chat/daemon context (origin set) a recursive `wiki_add` must NOT run
inline — it submits a STRUCTURED one-shot job (`kind="ingest"`, `once:+0s`,
`deliver_to=<concrete origin>`) and returns immediately. (The daemon's
notify/resume of such a job is tested in Veles.)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from _veles_module_wiki.tools import wiki_add
from veles.core.context import (
    reset_active_project,
    reset_origin,
    set_active_project,
    set_origin,
)
from veles.core.orchestration.delegation import (
    reset_subagent_factory,
    set_subagent_factory,
)
from veles.core.project import init_project


@dataclass
class _Recorder:
    built: list[Any] = field(default_factory=list)

    def factory(self, *, system_prompt: str, tools: list[str]):
        @dataclass
        class _StubAgent:
            system_prompt: str
            tools: list[str]

            def run(self, prompt: str, **_kw: Any):
                @dataclass
                class _RR:
                    text: str = "ok"
                    session_id: str | None = "w1"
                    usage: Any = None

                return _RR()

        a = _StubAgent(system_prompt=system_prompt, tools=list(tools))
        self.built.append(a)
        return a


def _project(tmp_path: Path):
    return init_project(tmp_path / "proj", name="bg", layout="llm-wiki")


def test_recursive_with_origin_submits_structured_job(tmp_path: Path) -> None:
    project = _project(tmp_path)
    ptok = set_active_project(project)
    otok = set_origin("telegram:12345")
    rec = _Recorder()
    ftok = set_subagent_factory(rec.factory)
    try:
        docs = tmp_path / "docs"
        docs.mkdir()
        (docs / "a.md").write_text("a", encoding="utf-8")
        out = wiki_add(str(docs), recursive=True)
        assert "background" in out.lower()
        assert rec.built == []  # nothing ran inline

        from veles.core.jobs_store import JobsStore

        store = JobsStore(project.memory_db_path)
        jobs = [store.get_job(j.id) for j in store.list_jobs()]
        store.close()
        assert len(jobs) == 1
        job = jobs[0]
        assert job is not None
        assert job.kind == "ingest"
        assert job.schedule.kind == "once"
        assert job.deliver_to == "telegram:12345"  # CONCRETE origin, never "origin"
        assert job.params is not None
        assert job.params["source"] == str(docs)
        assert job.params["resume_depth"] == 0
    finally:
        reset_subagent_factory(ftok)
        reset_origin(otok)
        reset_active_project(ptok)


def test_recursive_without_origin_runs_inline(tmp_path: Path) -> None:
    project = _project(tmp_path)
    ptok = set_active_project(project)
    rec = _Recorder()
    ftok = set_subagent_factory(rec.factory)
    try:
        docs = tmp_path / "docs"
        docs.mkdir()
        (docs / "a.md").write_text("a", encoding="utf-8")
        wiki_add(str(docs), recursive=True)
        assert len(rec.built) == 1  # ran inline (REPL path)
    finally:
        reset_subagent_factory(ftok)
        reset_active_project(ptok)


def test_single_file_with_origin_stays_inline(tmp_path: Path) -> None:
    project = _project(tmp_path)
    ptok = set_active_project(project)
    otok = set_origin("telegram:12345")
    rec = _Recorder()
    ftok = set_subagent_factory(rec.factory)
    try:
        f = tmp_path / "a.md"
        f.write_text("a", encoding="utf-8")
        wiki_add(str(f))
        assert len(rec.built) == 1  # single file is fast — no background job
    finally:
        reset_subagent_factory(ftok)
        reset_origin(otok)
        reset_active_project(ptok)
