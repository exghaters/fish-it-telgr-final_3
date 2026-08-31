"""Iteration 21 — editing a Telegram account's config must STOP that account's
automation (and keep it stopped; no auto-start), without touching other accounts.
"""
import asyncio
import os
from unittest.mock import AsyncMock

import pytest
import requests

from automation_engine import automation_engine


def _read_frontend_env():
    d = {}
    try:
        with open("/app/frontend/.env") as f:
            for line in f:
                if "=" in line and not line.strip().startswith("#"):
                    k, v = line.strip().split("=", 1)
                    d[k] = v
    except Exception:
        pass
    return d


BASE_URL = (os.environ.get("REACT_APP_BACKEND_URL")
            or _read_frontend_env().get("REACT_APP_BACKEND_URL", "")).rstrip("/")
assert BASE_URL, "REACT_APP_BACKEND_URL missing"


@pytest.fixture(scope="module")
def admin_session():
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login",
               json={"email": "admin@fishit.app", "password": "Surabaya818"})
    assert r.status_code == 200, f"admin login failed: {r.status_code} {r.text}"
    return s


def test_saving_config_forces_enabled_false(admin_session):
    cur = admin_session.get(f"{BASE_URL}/api/automation/config").json()
    cur["enabled"] = True  # pretend it was running
    r = admin_session.put(f"{BASE_URL}/api/automation/config", json=cur)
    assert r.status_code == 200, r.text
    assert r.json()["enabled"] is False, "PUT /config must force STOP (enabled=false)"
    again = admin_session.get(f"{BASE_URL}/api/automation/config").json()
    assert again["enabled"] is False, "config must stay STOP after save"


def test_stop_affects_only_target_account():
    async def run():
        eng = automation_engine
        rA = eng.get("test-acct-A")
        rB = eng.get("test-acct-B")
        rA._save_state = AsyncMock()
        rB._save_state = AsyncMock()
        rA._event = AsyncMock()
        rB._event = AsyncMock()
        rA._remove_resume_handler = AsyncMock()
        rB._remove_resume_handler = AsyncMock()

        async def loop(runner):
            while not runner.stop_flag.is_set():
                await asyncio.sleep(0.02)

        rA.stop_flag.clear()
        rB.stop_flag.clear()
        rA.task = asyncio.create_task(loop(rA))
        rB.task = asyncio.create_task(loop(rB))
        await asyncio.sleep(0.05)
        assert rA.is_running() and rB.is_running()

        await eng.stop("test-acct-A")
        assert not rA.is_running(), "target account must stop"
        assert rB.is_running(), "other account must keep running"

        rB.stop_flag.set()
        try:
            await asyncio.wait_for(rB.task, timeout=2)
        except Exception:
            pass
        eng.runners.pop("test-acct-A", None)
        eng.runners.pop("test-acct-B", None)

    asyncio.run(run())
