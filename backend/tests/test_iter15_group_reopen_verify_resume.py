"""Iteration 15: group re-open on cancelled registration + resume flow after verification.

Covers the two real gameplay bugs:
1. "❌ PENDAFTARAN DIBATALKAN / Tidak ada peserta" -> engine auto re-sends /open_mancing.
2. After a verification, engine re-issues the pending join deeplink / /mancing command.
"""
import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from automation_engine import AutomationRunner
from models import AutomationConfig


class FakeUT:
    def __init__(self):
        self.sent = []
        self.event_queue = asyncio.Queue()
        self.client = MagicMock()

    async def send_command(self, chat, cmd):
        self.sent.append((chat, cmd))

    async def resolve_chat_id(self, uname):
        return {"@grp": -100123, "@fish_it_vip_bot": 555, "@bot": 555}.get(uname)


def _cfg(**over):
    base = dict(user_id="u1", mode="group", group_username="@grp",
                bot_username="@fish_it_vip_bot",
                group_open_command="/open_mancing@fish_it_vip_bot")
    base.update(over)
    return AutomationConfig(**base)


def _runner(ut):
    r = AutomationRunner("u1")
    r._get_client = AsyncMock(return_value=ut)
    r._save_state = AsyncMock()
    r._event = AsyncMock()
    r._notify = AsyncMock()
    r._drain_queue = AsyncMock()  # avoid db (loop-bound motor) across asyncio.run loops
    return r


def test_config_has_new_patterns():
    c = AutomationConfig(user_id="x")
    assert "DIBATALKAN" in c.pendaftaran_cancelled_pattern
    assert "Tidak ada peserta" in c.pendaftaran_cancelled_pattern
    assert "Terdaftar" in c.registration_success_pattern


def test_group_reopens_on_cancelled():
    async def run():
        ut = FakeUT()
        r = _runner(ut)
        r._group_kickstarted = True  # skip kickstart send
        cfg = _cfg()
        # Group emits the cancelled message
        await ut.event_queue.put({
            "text": "❌ PENDAFTARAN DIBATALKAN\nTidak ada peserta yang mendaftar.",
            "chat_id": -100123, "message_id": 1,
        })
        # asyncio.sleep(3) inside handler -> keep test snappy but real
        await asyncio.wait_for(r._cycle_group(cfg), timeout=15)
        assert ("@grp", "/open_mancing@fish_it_vip_bot") in ut.sent, ut.sent
    asyncio.run(run())


def test_resend_pending_after_verify_manual_resume():
    async def run():
        ut = FakeUT()
        r = _runner(ut)
        # Simulate a group deeplink join set the pending command + a verify pause
        r._pending_after_verify = ("@fish_it_vip_bot", "/start daftar2_-1001157311936")
        r._paused_for_verify = True
        await r._resend_pending_after_verify()  # not forced; gated on paused flag
        assert ("@fish_it_vip_bot", "/start daftar2_-1001157311936") in ut.sent
        # pending cleared so it is not sent twice
        assert r._pending_after_verify is None
        assert r._paused_for_verify is False
    asyncio.run(run())


def test_resend_pending_noop_when_not_paused_for_verify():
    async def run():
        ut = FakeUT()
        r = _runner(ut)
        r._pending_after_verify = ("@bot", "/mancing")
        r._paused_for_verify = False  # a normal (non-verify) resume
        await r._resend_pending_after_verify()
        assert ut.sent == []  # nothing re-issued
    asyncio.run(run())


def test_boost_perahu_sent_to_configured_bot():
    """PERAHU SIAP BERANGKAT -> /boost goes to the configured bot (not the group)."""
    async def run():
        ut = FakeUT()
        r = _runner(ut)
        cfg = _cfg(boost_enabled=True)
        await r._maybe_boost(cfg, {"text": "⛵️ PERAHU SIAP BERANGKAT!", "chat_id": -100123})
        assert (cfg.bot_username, cfg.boost_command) in ut.sent, ut.sent
    asyncio.run(run())


def test_boost_skipped_when_disabled():
    async def run():
        ut = FakeUT()
        r = _runner(ut)
        cfg = _cfg(boost_enabled=False)
        await r._maybe_boost(cfg, {"text": "⛵️ PERAHU SIAP BERANGKAT!", "chat_id": -100123})
        assert ut.sent == []
    asyncio.run(run())


def test_resend_pending_force_after_auto_verify():
    async def run():
        ut = FakeUT()
        r = _runner(ut)
        r._pending_after_verify = ("@bot", "/mancing")
        r._paused_for_verify = False
        await r._resend_pending_after_verify(force=True)  # auto-verify success path
        assert ("@bot", "/mancing") in ut.sent
        assert r._pending_after_verify is None
    asyncio.run(run())
