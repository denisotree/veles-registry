"""The `telegram` platform spec: contributed by the module, builds a gateway from a
channel block (the `veles.sdk.channel_checks` kit), knows its own config keys."""

from __future__ import annotations

from pathlib import Path

from _veles_module_telegram import TELEGRAM_SPEC
from veles.sdk.channel_checks import check_builds_from_config, check_config_keys


def test_the_module_contributes_the_telegram_platform() -> None:
    from veles.core.platforms import get_platform

    assert get_platform("telegram") is TELEGRAM_SPEC


def test_builds_from_a_channel_block(tmp_path: Path) -> None:
    gw = check_builds_from_config(
        TELEGRAM_SPEC,
        config={"whitelist": ["@foo", 12345], "debounce_seconds": "2"},
        secrets={"bot_token": "tok"},
        session_dir=tmp_path,
    )
    assert gw.bot_token == "tok"
    assert gw.whitelist == ("@foo", "12345")


def test_a_legacy_chat_id_becomes_the_whitelist(tmp_path: Path) -> None:
    gw = check_builds_from_config(
        TELEGRAM_SPEC, config={"chat_id": "555"}, secrets={"bot_token": "t"}, session_dir=tmp_path
    )
    assert gw.whitelist == ("555",)


def test_its_config_keys_are_declared() -> None:
    check_config_keys(
        TELEGRAM_SPEC,
        {
            "enabled": True,
            "bot_token": "x",
            "whitelist": ["1"],
            "chat_id": "1",
            "debounce_seconds": 2,
            "forward_debounce_seconds": 4,
        },
    )
