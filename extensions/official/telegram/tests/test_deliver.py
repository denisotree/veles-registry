"""M165 — `TelegramGateway.deliver(...)` renders and sends to a chat (the
daemon's delivery router calls it for `deliver_to = "telegram:<chat>"`)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from _veles_module_telegram import TelegramGateway
from veles.core.chat_sessions import SessionMap


def _gateway(tmp_path: Path, sends: list[tuple[str, dict[str, Any]]]) -> TelegramGateway:
    async def stub_send(method: str, payload: dict[str, Any]) -> dict[str, Any]:
        sends.append((method, payload))
        return {"message_id": 1, "chat": payload.get("chat_id")}

    gateway = TelegramGateway(
        bot_token="X",
        daemon_client=object(),
        session_map=SessionMap.load(tmp_path / "tg-sessions.json"),
    )
    gateway._telegram_send = stub_send
    return gateway


async def test_gateway_deliver_renders_and_sends(tmp_path: Path) -> None:
    sends: list[tuple[str, dict[str, Any]]] = []
    await _gateway(tmp_path, sends).deliver("42", "**bold** reminder", None)

    assert len(sends) == 1
    method, payload = sends[0]
    assert method == "sendMessage"
    assert payload["chat_id"] == 42  # string target coerced to int
    assert "<b>bold</b>" in payload["text"]  # markdown rendered to telegram HTML


async def test_gateway_deliver_accepts_thread_id(tmp_path: Path) -> None:
    """thread_id is accepted (the deliverer signature) even though direct chats
    don't use forum topics — must not raise."""
    sends: list[tuple[str, dict[str, Any]]] = []
    await _gateway(tmp_path, sends).deliver("7", "hi", "topic-9")
    assert sends and sends[0][1]["chat_id"] == 7
