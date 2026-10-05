"""agy's stream-json → a Veles response (fixtures recorded from agy 1.2.17)."""

from __future__ import annotations

import importlib
import json
from pathlib import Path

AgyStreamState = importlib.import_module("_veles_module_antigravity-cli._stream").AgyStreamState

_FIX = Path(__file__).parent / "fixtures"


def _events(name: str) -> list[dict]:
    lines = (_FIX / name).read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in lines if line.strip()]


def _replay(name: str):
    state = AgyStreamState()
    for event in _events(name):
        state.absorb(event)
    return state


def test_an_answer_and_its_usage() -> None:
    response = _replay("answer.jsonl").to_response(raw=None)
    assert response.text.startswith("The first line of `AGENTS.md`")
    assert response.finish_reason == "stop"
    assert response.usage.prompt_tokens == 62604 and response.usage.completion_tokens == 603
    assert response.usage.reasoning_tokens == 301


def test_text_deltas_stream_in_order() -> None:
    state = AgyStreamState()
    chunks = [state.absorb(event) for event in _events("answer.jsonl")]
    assert "".join(chunks) == "The first line of `AGENTS.md` is:\n\n```markdown\n# proj\n```\n" + (
        "\n`run_command` was denied.\n"
    )


def test_no_login_says_how_to_log_in() -> None:
    response = _replay("no_login.jsonl").to_response(raw=None)
    assert response.finish_reason == "error"
    assert "authentication failed" in response.text and "log in by running `agy`" in response.text


def test_a_service_error_is_an_error() -> None:
    response = _replay("unavailable.jsonl").to_response(raw=None)
    assert response.finish_reason == "error" and "503" in response.text
    assert "log in" not in response.text
