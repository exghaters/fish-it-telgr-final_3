"""Iteration 23 — group mode must register ONCE per registration message.

Real bug (screenshots): the "PENDAFTARAN DIBUKA" message edits its countdown
(60→59→…) every second — same message id — re-firing the pendaftaran match and
causing repeated /start deep-links ("✅ Sudah Terdaftar!" spam). We now dedupe on
the message id (a NEW round has a NEW id and IS joined again). This is robust
even if the WAKTU HABIS / session-done pattern fails to match.
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


def test_register_once_per_message_then_new_round():
    async def run():
        r, ut = _mk_runner()
        cfg = AutomationConfig(user_id="u1", mode="group",
                               group_username="@grp", bot_username="@fish_it_vip3_bot")
        join_calls = []

        async def fake_join(c, g, mid):
            join_calls.append(mid)
            return "deeplink"
        r._join_group_button = fake_join

        def wait_msg(mid):
            async def w(c, rules, timeout):
                return {"_matched": "pendaftaran", "message_id": mid}
            return w

        # 1st cycle: PENDAFTARAN msg 123 -> register.
        r._wait_for_any = wait_msg(123)
        await r._cycle_group(cfg)
        assert join_calls == [123]
        assert r._joined_message_id == 123

        # Same message id re-fires (countdown edit) -> must NOT re-register.
        await r._cycle_group(cfg)
        assert join_calls == [123], "must not double-register the same message"

        # NEW round = NEW message id -> registers again (even without a reset).
        r._wait_for_any = wait_msg(456)
        await r._cycle_group(cfg)
        assert join_calls == [123, 456]
        assert r._joined_message_id == 456
    asyncio.run(run())


def test_waktu_habis_and_session_done_reset_join_marker():
    async def run():
        r, ut = _mk_runner()
        cfg = AutomationConfig(user_id="u1", mode="group",
                               group_username="@grp", bot_username="@fish_it_vip3_bot")

        r._joined_message_id = 999

        async def wait_waktu(c, rules, timeout):
            return {"_matched": "waktu_habis", "message_id": 1}
        r._wait_for_any = wait_waktu
        await r._cycle_group(cfg)
        assert r._joined_message_id is None

        r._joined_message_id = 888
        r._process_session_result = AsyncMock()

        async def wait_done(c, rules, timeout):
            return {"_matched": "session_done", "message_id": 2, "text": "SESI SELESAI"}
        r._wait_for_any = wait_done
        await r._cycle_group(cfg)
        assert r._joined_message_id is None
    asyncio.run(run())
