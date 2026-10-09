"""Probes for the send_message repeats issue. Not merged unless a fix follows."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import open_strix.app as app_mod
import pytest
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage


class FakeChannel:
    def __init__(self) -> None:
        self.sent: list[str] = []

    async def send(self, text: str) -> Any:
        self.sent.append(text)
        return type("Sent", (), {"id": 100 + len(self.sent)})()


class FakeClient:
    def __init__(self, channel: FakeChannel) -> None:
        self.channel = channel

    def is_ready(self) -> bool:
        return True

    def get_channel(self, _: int) -> FakeChannel:
        return self.channel

    async def fetch_channel(self, _: int) -> FakeChannel:
        return self.channel


def _wire(app: app_mod.OpenStrixApp, monkeypatch: pytest.MonkeyPatch) -> FakeChannel:
    channel = FakeChannel()
    # A stub client: the probe needs only get_channel and fetch_channel.
    app.discord_client = FakeClient(channel)  # ty: ignore[invalid-assignment]
    monkeypatch.setattr(app_mod.discord.abc, "Messageable", FakeChannel)
    return channel


@pytest.mark.asyncio
async def test_one_hooked_call_sends_once_and_logs_once(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    hook_dir = tmp_path / "skills" / "probe"
    hook_dir.mkdir(parents=True)
    (hook_dir / "hooks.json").write_text(
        json.dumps(
            {
                "hooks": [
                    {
                        "name": "probe",
                        "command": "sh -c 'cat; echo probe-ran >&2'",
                        "events": ["pre_tool_call"],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(app_mod, "create_deep_agent", lambda **_: None)
    app = app_mod.OpenStrixApp(tmp_path)
    channel = _wire(app, monkeypatch)
    tools = {t.name: t for t in app.hooks.wrap_tools(app._build_tools())}

    await tools["send_message"].ainvoke({"text": "hello", "channel_id": "123"})

    rows = [json.loads(line) for line in app.layout.events_log.read_text().splitlines()]
    assert channel.sent == ["hello"]
    assert [r["type"] for r in rows].count("hook_stderr") == 1


class ToolCallingFakeModel(GenericFakeChatModel):
    def bind_tools(self, tools: Any, **_: Any) -> ToolCallingFakeModel:
        return self


@pytest.mark.asyncio
async def test_parallel_identical_tool_calls_in_one_message(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    call = {
        "name": "send_message",
        "args": {"text": "hello", "channel_id": "123"},
        "type": "tool_call",
    }
    model = ToolCallingFakeModel(
        messages=iter(
            [
                AIMessage(content="", tool_calls=[{**call, "id": "c1"}, {**call, "id": "c2"}]),
                AIMessage(content="done"),
            ]
        )
    )
    monkeypatch.setattr(app_mod, "_build_chat_model", lambda *_, **__: model)
    app = app_mod.OpenStrixApp(tmp_path)
    channel = _wire(app, monkeypatch)
    agent = app._create_agent()

    await agent.ainvoke({"messages": [{"role": "user", "content": "say hello"}]})

    # Record the observed count in the issue; this probe documents behavior, it does not judge it.
    print(f"sends for two identical parallel tool calls: {len(channel.sent)}")
