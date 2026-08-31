"""Iteration 20 — group "Daftar Mancing" button click is robust to the button
being attached a beat AFTER the PENDAFTARAN DIBUKA text (Fish It edits the
message). _join_group_button now polls/retries instead of giving up immediately.
"""
import asyncio
from unittest.mock import AsyncMock, MagicMock

from automation_engine import AutomationRunner
from models import AutomationConfig


class FakeBtn:
    def __init__(self, text, url=None):
        self.text = text
        self.url = url


class FakeMsg:
    def __init__(self, mid, rows):
        self.id = mid
        self.buttons = rows
        self.clicked = []

    async def click(self, text=None):
        self.clicked.append(text)
        return MagicMock(message="ok")


class FakeClient:
    """get_messages returns a no-button message first, then a message WITH the
    join button on the next attempt."""
    def __init__(self, sequence):
        self._seq = sequence
        self._i = 0

    async def get_messages(self, group, ids=None):
        m = self._seq[min(self._i, len(self._seq) - 1)]
        self._i += 1
        return m

    async def iter_messages(self, group, limit=12):
        return
        yield  # make it an async generator


class FakeUT:
    def __init__(self, client):
        self.client = client
        self.sent = []

    async def send_command(self, chat, text):
        self.sent.append((chat, text))

    async def resolve_chat_id(self, u):
        return -100123


def _cfg(**over):
    base = dict(user_id="u1", mode="group", group_username="@grp",
                bot_username="@fish_it_vip_bot",
                join_button_text="Daftar Mancing")
    base.update(over)
    return AutomationConfig(**base)


def _runner(ut):
    r = AutomationRunner("u1")
    r._get_client = AsyncMock(return_value=ut)
    r._event = AsyncMock()
    return r


def test_click_button_found_on_retry():
    async def run():
        no_btn = FakeMsg(10, None)
        with_btn = FakeMsg(10, [[FakeBtn("✅ Daftar Mancing")]])
        ut = FakeUT(FakeClient([no_btn, with_btn]))
        r = _runner(ut)
        method = await asyncio.wait_for(
            r._join_group_button(_cfg(), "@grp", 10), timeout=10)
        assert method == "clicked", method
        assert with_btn.clicked == ["✅ Daftar Mancing"], with_btn.clicked
    asyncio.run(run())


def test_join_via_deeplink_url_button():
    async def run():
        msg = FakeMsg(11, [[FakeBtn(
            "✅ Daftar Mancing",
            url="https://t.me/fish_it_vip_bot?start=daftar2_abc123")]])
        ut = FakeUT(FakeClient([msg]))
        r = _runner(ut)
        method = await asyncio.wait_for(
            r._join_group_button(_cfg(), "@grp", 11), timeout=10)
        assert method == "deeplink", method
        assert ("@fish_it_vip_bot", "/start daftar2_abc123") in ut.sent, ut.sent
    asyncio.run(run())
