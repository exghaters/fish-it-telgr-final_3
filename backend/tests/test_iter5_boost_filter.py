"""Iter5 tests: chat filter + boost + anti-spam plumbing verification."""
import os
import re
import uuid
import sys
import pytest
import requests

from dotenv import dotenv_values as _dv  # test-env resolution
_fe = _dv("/app/frontend/.env")
_bu = os.environ.get("REACT_APP_BACKEND_URL") or _fe.get("REACT_APP_BACKEND_URL")
if not _bu:
    raise RuntimeError("REACT_APP_BACKEND_URL missing from env and /app/frontend/.env")
BASE_URL = _bu.rstrip("/")

sys.path.insert(0, "/app/backend")


# ---------- API: config new fields ----------
class TestConfigNewFields:
    @pytest.fixture(scope="class")
    def token(self):
        # Register a fresh test user so we don't touch elite config
        email = f"TEST_iter5_boost_{uuid.uuid4().hex[:8]}@fishit.app"
        pwd = "TestPass@2026"
        requests.post(f"{BASE_URL}/api/auth/register", json={"email": email, "password": pwd})
        r = requests.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": pwd})
        assert r.status_code == 200, r.text
        return r.json()["access_token"]

    def test_get_config_defaults(self, token):
        r = requests.get(f"{BASE_URL}/api/automation/config",
                         headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200
        cfg = r.json()
        # New fields
        assert "extra_allowed_chats" in cfg
        assert "@fish_it_vip_bot" in cfg["extra_allowed_chats"]
        assert "@fish_it_vip3_bot" in cfg["extra_allowed_chats"]
        assert "@fish_it_vip4_bot" in cfg["extra_allowed_chats"]
        assert "@fish_it_vip5_bot" in cfg["extra_allowed_chats"]
        assert cfg["boost_enabled"] is False
        assert cfg["boost_command"] == "/boost"
        assert cfg["boost_cooldown_seconds"] == 300
        assert "AUTO MANCING DIMULAI" in cfg["boost_trigger_pattern"]
        assert "PERAHU SIAP BERANGKAT" in cfg["group_boost_trigger_pattern"]

    def test_put_persists_new_fields(self, token):
        headers = {"Authorization": f"Bearer {token}"}
        current = requests.get(f"{BASE_URL}/api/automation/config", headers=headers).json()
        current.update({
            "extra_allowed_chats": "@custom_bot, @another_chat",
            "boost_enabled": True,
            "boost_command": "/superboost",
            "boost_trigger_pattern": "(GO NOW|LAUNCH)",
            "boost_cooldown_seconds": 120,
        })
        r = requests.put(f"{BASE_URL}/api/automation/config", json=current, headers=headers)
        assert r.status_code == 200, r.text
        # Verify persistence via GET
        got = requests.get(f"{BASE_URL}/api/automation/config", headers=headers).json()
        # iter10: extra_allowed_chats is plan-gated (Starter/free forced to ""),
        # this fixture user is a fresh free-plan account.
        assert got["extra_allowed_chats"] == ""
        assert got["boost_enabled"] is True
        assert got["boost_command"] == "/superboost"
        assert got["boost_trigger_pattern"] == "(GO NOW|LAUNCH)"
        assert got["boost_cooldown_seconds"] == 120


# ---------- Source-level plumbing ----------
class TestEnginePlumbing:
    def test_regex_patterns(self):
        from automation_engine import FISHING_ACTIVE_RX, ELAPSED_RX
        assert FISHING_ACTIVE_RX.search("KAMU SEDANG MANCING!")
        assert FISHING_ACTIVE_RX.search("Kamu sedang memancing bro")
        m = ELAPSED_RX.search("KAMU SEDANG MANCING! Waktu berjalan: 235 detik")
        assert m and int(m.group(1)) == 235

    def test_runner_has_new_methods(self):
        from automation_engine import AutomationRunner
        for name in [
            "_apply_chat_filter", "_maybe_boost", "_register_active_session",
            "_estimate_remaining", "_ensure_no_active_session",
            "_session_likely_running", "_wait_for_message",
            "_extract_and_sell", "_do_sell", "_join_group_button",
        ]:
            assert hasattr(AutomationRunner, name), f"Missing method: {name}"

    def test_extract_and_sell_calls_ensure_no_active_session(self):
        """Source inspection: _extract_and_sell must call _ensure_no_active_session before extract."""
        import inspect
        from automation_engine import AutomationRunner
        src = inspect.getsource(AutomationRunner._extract_and_sell)
        # ensure guard exists BEFORE any extract_command send
        idx_ensure = src.find("_ensure_no_active_session")
        idx_extract = src.find("extract_command")
        assert idx_ensure != -1
        assert idx_extract != -1
        assert idx_ensure < idx_extract, "Guard must precede extract"

    def test_do_sell_waits_on_mancing(self):
        import inspect
        from automation_engine import AutomationRunner
        src = inspect.getsource(AutomationRunner._do_sell)
        assert "_register_active_session" in src
        assert "_sleep_seconds" in src
        assert "mancing_retry" in src
        assert "mancing_retry >= 2" in src

    def test_wait_for_message_uses_resolve_and_target_filter(self):
        import inspect
        from automation_engine import AutomationRunner
        src = inspect.getsource(AutomationRunner._wait_for_message)
        assert "resolve_chat_id" in src
        assert "from_target" in src

    def test_join_group_button_handles_deeplink(self):
        import inspect
        from automation_engine import AutomationRunner
        src = inspect.getsource(AutomationRunner._join_group_button)
        assert "t.me/" in src or "t\\.me" in src
        assert "/start" in src
        assert "msg.click" in src or "m.click" in src

    def test_cycle_group_pattern_is_pendaftaran_dibuka(self):
        import inspect
        from automation_engine import AutomationRunner
        src = inspect.getsource(AutomationRunner._cycle_group)
        # Event-driven group loop: patterns now come from config
        assert "pendaftaran_open_pattern" in src
        assert "waktu_habis_pattern" in src


class TestTelegramManagerPlumbing:
    def test_user_telegram_has_filter_attrs(self):
        from telegram_manager import UserTelegram
        ut = UserTelegram("uid", 1, "hash" * 3)
        assert hasattr(ut, "allowed_chat_ids")
        assert isinstance(ut.allowed_chat_ids, set)
        assert hasattr(ut, "resolve_chat_id")
        assert hasattr(ut, "set_allowed_chats")

    def test_handlers_use_incoming_and_filter(self):
        import inspect
        from telegram_manager import UserTelegram
        src = inspect.getsource(UserTelegram._install_default_handler)
        assert "incoming=True" in src
        assert "NewMessage" in src
        assert "MessageEdited" in src
        assert "allowed_chat_ids" in src
        # Filter check present in both handlers
        assert src.count("allowed_chat_ids and event.chat_id not in self.allowed_chat_ids") >= 2


class TestBoostTrigger:
    def test_default_boost_pattern_matches_both_triggers(self):
        pat = r"(PERAHU SIAP BERANGKAT|AUTO MANCING DIMULAI)"
        assert re.search(pat, "⛵ PERAHU SIAP BERANGKAT sekarang!", re.IGNORECASE)
        assert re.search(pat, "🎣 AUTO MANCING DIMULAI! Semoga hoki", re.IGNORECASE)
        assert not re.search(pat, "Random other text", re.IGNORECASE)
