"""Iteration 23 — group mode must register ONCE per round.

Real bug (screenshots): the "PENDAFTARAN DIBUKA" message edits its countdown
(60→59→…) every second, re-firing the pendaftaran match and causing repeated
/start deep-links ("✅ Sudah Terdaftar!" spam). Guarded by _joined_round.
"""
import asyncio
from unittest.mock import AsyncMock, MagicMock

from automation_engine import AutomationRunner
from models import AutomationConfig


def _mk_runner():
    r = AutomationRunner("u1")
    ut = MagicMock()
    ut.send_command = AsyncMock()
    r._get_client = AsyncMock(return_value=ut)
    r._save_state = AsyncMock()
    r._event = AsyncMock()
    r._drain_queue = AsyncMock()
    r._session_likely_running = MagicMock(return_value=False)
    r._group_kickstarted = True  # skip kickstart open
    return r, ut


def test_register_once_per_round_then_reopen():
    async def run():
        r, ut = _mk_runner()
        cfg = AutomationConfig(user_id="u1", mode="group",
                               group_username="@grp", bot_username="@fish_it_vip3_bot")
        join_calls = []

        async def fake_join(c, g, mid):
            join_calls.append(mid)
            return "deeplink"
        r._join_group_button = fake_join

        async def wait_pendaftaran(c, rules, timeout):
            return {"_matched": "pendaftaran", "message_id": 123}
        r._wait_for_any = wait_pendaftaran

        # 1st cycle registers.
        await r._cycle_group(cfg)
        assert join_calls == [123]
        assert r._joined_round is True

        # 2nd cycle: countdown edit re-fires pendaftaran -> must NOT re-register.
        await r._cycle_group(cfg)
        assert join_calls == [123], "should not double-register within a round"

        # WAKTU HABIS resets the round.
        async def wait_waktu(c, rules, timeout):
            return {"_matched": "waktu_habis", "message_id": 200}
        r._wait_for_any = wait_waktu
        await r._cycle_group(cfg)
        assert r._joined_round is False

        # New round -> registers again.
        r._wait_for_any = wait_pendaftaran
        await r._cycle_group(cfg)
        assert join_calls == [123, 123]
    asyncio.run(run())


def test_session_done_resets_round():
    async def run():
        r, ut = _mk_runner()
        cfg = AutomationConfig(user_id="u1", mode="group",
                               group_username="@grp", bot_username="@fish_it_vip3_bot")
        r._joined_round = True
        r._process_session_result = AsyncMock()

        async def wait_done(c, rules, timeout):
            return {"_matched": "session_done", "message_id": 5, "text": "SESI SELESAI"}
        r._wait_for_any = wait_done
        await r._cycle_group(cfg)
        assert r._joined_round is False
    asyncio.run(run())
