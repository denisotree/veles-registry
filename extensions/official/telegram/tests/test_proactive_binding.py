"""M214/M278 — a proactive notice bound to a chat is where the chat's next
message continues (the daemon's binder + this gateway, end to end)."""

from __future__ import annotations

from pathlib import Path

import pytest

from _veles_module_telegram import TelegramGateway
from veles.core.memory import SessionStore
from veles.core.project import init_project
from veles.daemon.auth import TokenStore
from veles.daemon.background_ops import make_proactive_binder
from veles.daemon.channels import channel_session_map
from veles.daemon.state import DaemonState


@pytest.fixture()
def state(tmp_path: Path):
    project = init_project(tmp_path / "proj", name="proj")
    store = SessionStore(project.memory_db_path)
    st = DaemonState(
        project=project,
        store=store,
        token_store=TokenStore.load(),
        agent_factory=lambda *a, **kw: None,
        started_at=0.0,
    )
    yield st
    store.close()


async def test_the_chats_next_message_continues_the_bound_session(state):
    """After a notice is bound to chat 42, the gateway's next message from chat
    42 goes to that same session. The gateway gets the very map the daemon hands
    it (`start_channel_runners`). Pre-M278 the binder keyed "telegram:42" while
    the gateway reads "42", so this message started a fresh session with no
    record of the notice."""
    submitted: list[str | None] = []

    class _Client:
        async def submit_run(self, prompt, *, session_id=None, origin=None):
            submitted.append(session_id)
            return {"run_id": "r1", "session_id": session_id, "state": "running"}

        async def stream_events(self, run_id):
            yield {"type": "completed", "text": "ok", "session_id": submitted[-1]}

        async def submit_prompt_answer(self, run_id, prompt_id, choice):
            raise NotImplementedError

    await make_proactive_binder(state)("telegram:42", "⏰ standup at 10")

    gateway = TelegramGateway(
        bot_token="X",
        daemon_client=_Client(),
        session_map=channel_session_map(state, "telegram"),
    )

    async def _send(method, payload):
        return {"message_id": 1, "chat": payload.get("chat_id")}

    gateway._telegram_send = _send  # type: ignore[method-assign]
    await gateway._handle_update(
        {"update_id": 1, "message": {"chat": {"id": 42, "type": "private"}, "text": "moved?"}}
    )
    await gateway._flush_buffer("42")

    assert len(submitted) == 1 and submitted[0] is not None
    msgs = state.store.load_messages(submitted[0])
    assert any("standup at 10" in (m.content or "") for m in msgs)
