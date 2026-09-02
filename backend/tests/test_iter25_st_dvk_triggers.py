"""Iteration 25 — 'st' force-restart and 'dvk' resume-continue triggers."""
import asyncio
from unittest.mock import AsyncMock, MagicMock

from automation_engine import AutomationRunner
from models import AutomationConfig


def _runner(cfg):
    r = AutomationRunner("u1")
    ut = MagicMock()
    ut.send_command = AsyncMock()
    r._get_client = AsyncMock(return_value=ut)
    r._load_config = AsyncMock(return_value=cfg)
    r._event = AsyncMock()
    r._drain_queue = AsyncMock()
    r.resume = AsyncMock()
    return r, ut


def test_st_force_restart_private():
    async def run():
        cfg = AutomationConfig(user_id="u1", mode="vip_direct",
                               bot_username="@fish_it_bot", open_command="/mancing")
        r, ut = _runner(cfg)
        await r._force_restart()
        ut.send_command.assert_awaited_with("@fish_it_bot", "/mancing")
        assert r._pending_after_verify == ("@fish_it_bot", "/mancing")
    asyncio.run(run())


def test_st_force_restart_group_resets_join_marker():
    async def run():
        cfg = AutomationConfig(user_id="u1", mode="group",
                               group_username="@grp",
                               group_open_command="/open_mancing@fish_it_vip_bot")
        r, ut = _runner(cfg)
        r._joined_message_id = 555  # pretend we had joined a prior round
        await r._force_restart()
        args = ut.send_command.await_args.args
        assert args[0] == "@grp"
        assert args[1].startswith("/open_mancing")
        assert r._joined_message_id is None
    asyncio.run(run())


def test_st_resumes_when_paused():
    async def run():
        cfg = AutomationConfig(user_id="u1", mode="vip_direct",
                               bot_username="@fish_it_bot", open_command="/mancing")
        r, ut = _runner(cfg)
        r.pause_flag.set()
        await r._force_restart()
        r.resume.assert_awaited()
    asyncio.run(run())
