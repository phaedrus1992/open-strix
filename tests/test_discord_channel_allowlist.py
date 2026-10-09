from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import discord
import pytest

import open_strix.app as app_mod
from open_strix.config import RepoLayout, load_config

CHANNEL = "1488981977557237852"
OTHER_CHANNEL = "1488981977557237999"
THREAD = "1499999999999999001"
ALLOWED_DM_AUTHOR = "405754989940572171"
OTHER_AUTHOR = "405754989940572999"


class DummyAgent:
    async def ainvoke(self, _: dict[str, Any]) -> dict[str, Any]:
        return {"messages": []}


def _app(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, config: str) -> app_mod.OpenStrixApp:
    monkeypatch.setattr(app_mod, "create_deep_agent", lambda **_: DummyAgent())
    (tmp_path / "config.yaml").write_text(config, encoding="utf-8")
    return app_mod.OpenStrixApp(tmp_path)


def _config(tmp_path: Path, text: str):
    (tmp_path / "config.yaml").write_text(text, encoding="utf-8")
    return load_config(RepoLayout(home=tmp_path, state_dir_name="state"))


class FakeAuthor:
    bot = False

    def __init__(self, author_id: str) -> None:
        self.id = int(author_id)

    def __str__(self) -> str:
        return "someone"


def _message(channel: Any, author_id: str = OTHER_AUTHOR) -> SimpleNamespace:
    return SimpleNamespace(
        id=12345, content="hello", channel=channel, author=FakeAuthor(author_id), attachments=[],
    )


def _events(app: app_mod.OpenStrixApp, record_type: str) -> list[dict[str, Any]]:
    lines = app.layout.events_log.read_text(encoding="utf-8").splitlines()
    return [row for row in map(json.loads, lines) if row["type"] == record_type]


def test_allowlists_default_to_empty(tmp_path: Path) -> None:
    config = _config(tmp_path, "model: x\n")
    assert config.discord_channel_allowlist == frozenset()
    assert config.discord_dm_allowlist == frozenset()


def test_allowlists_accept_yaml_ints_and_strings(tmp_path: Path) -> None:
    config = _config(
        tmp_path,
        f"discord_channel_allowlist:\n  - {CHANNEL}\n  - ' {OTHER_CHANNEL} '\n"
        f"discord_dm_allowlist:\n  - '{ALLOWED_DM_AUTHOR}'\n",
    )
    assert config.discord_channel_allowlist == frozenset({CHANNEL, OTHER_CHANNEL})
    assert config.discord_dm_allowlist == frozenset({ALLOWED_DM_AUTHOR})


@pytest.mark.parametrize(
    "entry",
    ["abc", "'123'", "'99999999999999999999'", "true", "'１４８８９８１９７７５５７２３７８５２'"],
)
def test_malformed_channel_id_fails_with_key_and_value(tmp_path: Path, entry: str) -> None:
    with pytest.raises(ValueError, match="discord_channel_allowlist"):
        _config(tmp_path, f"discord_channel_allowlist:\n  - {entry}\n")


def test_non_list_allowlist_fails(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="must be a list"):
        _config(tmp_path, f"discord_channel_allowlist: '{CHANNEL}'\n")


def test_dm_allowlist_without_channel_allowlist_fails(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="discord_dm_allowlist"):
        _config(tmp_path, f"discord_dm_allowlist:\n  - {ALLOWED_DM_AUTHOR}\n")


@pytest.mark.parametrize(
    ("channel_id", "parent_id", "is_dm", "author_id", "expected"),
    [
        (CHANNEL, None, False, OTHER_AUTHOR, True),
        (OTHER_CHANNEL, None, False, OTHER_AUTHOR, False),
        (THREAD, CHANNEL, False, OTHER_AUTHOR, True),
        (THREAD, OTHER_CHANNEL, False, OTHER_AUTHOR, False),
        ("555", None, True, ALLOWED_DM_AUTHOR, True),
        ("555", None, True, OTHER_AUTHOR, False),
        ("555", None, True, None, False),
    ],
)
def test_gate_with_allowlist(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    channel_id: str,
    parent_id: str | None,
    is_dm: bool,
    author_id: str | None,
    expected: bool,
) -> None:
    app = _app(
        tmp_path,
        monkeypatch,
        f"discord_channel_allowlist:\n  - {CHANNEL}\n"
        f"discord_dm_allowlist:\n  - {ALLOWED_DM_AUTHOR}\n",
    )
    allowed = app.is_discord_channel_allowed(
        channel_id=channel_id, parent_id=parent_id, is_dm=is_dm, author_id=author_id,
    )
    assert allowed is expected


def test_gate_without_allowlist_allows_everything(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = _app(tmp_path, monkeypatch, "model: x\n")
    assert app.is_discord_channel_allowed(
        channel_id=OTHER_CHANNEL, parent_id=None, is_dm=False, author_id=None,
    )
    assert app.is_discord_channel_allowed(
        channel_id="555", parent_id=None, is_dm=True, author_id=OTHER_AUTHOR,
    )


@pytest.mark.asyncio
async def test_unlisted_channel_is_ignored_and_logged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = _app(tmp_path, monkeypatch, f"discord_channel_allowlist:\n  - {CHANNEL}\n")
    await app.handle_discord_message(_message(SimpleNamespace(id=int(OTHER_CHANNEL))))
    assert app.queue.empty()
    ignored = _events(app, "discord_message_ignored")
    assert [row["channel_id"] for row in ignored] == [OTHER_CHANNEL]
    assert _events(app, "discord_message") == []


@pytest.mark.asyncio
async def test_listed_channel_and_its_thread_are_queued(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = _app(tmp_path, monkeypatch, f"discord_channel_allowlist:\n  - {CHANNEL}\n")
    await app.handle_discord_message(_message(SimpleNamespace(id=int(CHANNEL))))
    await app.handle_discord_message(
        _message(SimpleNamespace(id=int(THREAD), parent_id=int(CHANNEL))),
    )
    assert app.queue.get_nowait().channel_id == CHANNEL
    assert app.queue.get_nowait().channel_id == THREAD


@pytest.mark.asyncio
async def test_dm_from_unlisted_author_is_ignored(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = _app(
        tmp_path,
        monkeypatch,
        f"discord_channel_allowlist:\n  - {CHANNEL}\n"
        f"discord_dm_allowlist:\n  - {ALLOWED_DM_AUTHOR}\n",
    )
    dm = SimpleNamespace(id=555, type=discord.ChannelType.private)
    await app.handle_discord_message(_message(dm, author_id=OTHER_AUTHOR))
    assert app.queue.empty()
    await app.handle_discord_message(_message(dm, author_id=ALLOWED_DM_AUTHOR))
    assert app.queue.get_nowait().author_id == ALLOWED_DM_AUTHOR


@pytest.mark.asyncio
async def test_scheduler_events_ignore_the_allowlist(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = _app(tmp_path, monkeypatch, f"discord_channel_allowlist:\n  - {CHANNEL}\n")
    await app._on_scheduler_fire(name="job", prompt="run", channel_id=OTHER_CHANNEL)
    assert app.queue.get_nowait().channel_id == OTHER_CHANNEL
