"""Iteration 2: Verify bug fixes for extract flow, /mancing spam, and verification pause.

These tests exercise:
  - New AutomationConfig fields (already_fishing_pattern, extract_list_pattern)
  - GET/PUT roundtrip persistence of new fields
  - AutomationRunner private attrs (_last_verification_at, _in_verification)
  - AutomationRunner._wait_for_message accepts extend_on_active kwarg
  - telegram_manager installs events.MessageEdited handler
"""
from __future__ import annotations

import inspect
import os
import sys
import uuid

import pytest
import requests

# Ensure backend package is importable for introspection tests
sys.path.insert(0, "/app/backend")

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")


# --- Fixtures ---
@pytest.fixture(scope="module")
def http():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


@pytest.fixture(scope="module")
def user_ctx(http):
    email = f"iter2_{uuid.uuid4().hex[:8]}@fishit.app"
    pw = "Testpass@123"
    r = http.post(f"{BASE_URL}/api/auth/register", json={"email": email, "password": pw})
    assert r.status_code == 200, r.text
    d = r.json()
    return {"email": email, "token": d["access_token"], "id": d["user"]["id"]}


def auth_h(token):
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


# --- Config new fields ---
class TestConfigNewFields:
    def test_defaults_present(self, http, user_ctx):
        r = http.get(f"{BASE_URL}/api/automation/config", headers=auth_h(user_ctx["token"]))
        assert r.status_code == 200, r.text
        cfg = r.json()
        assert "already_fishing_pattern" in cfg
        assert "extract_list_pattern" in cfg
        # default values
        assert cfg["already_fishing_pattern"] == r"(sedang memancing|masih memancing|sedang aktif)"
        assert cfg["extract_list_pattern"] == r"(Bisa di-extract|extract semua artefak|EXTRACT.*Inventory)"

    def test_default_patterns_functional(self, http, user_ctx):
        import re
        r = http.get(f"{BASE_URL}/api/automation/config", headers=auth_h(user_ctx["token"]))
        cfg = r.json()
        af = re.compile(cfg["already_fishing_pattern"], re.IGNORECASE)
        assert af.search("Kamu sedang memancing! Waktu berjalan: 42 detik")
        assert af.search("masih memancing bro")
        el = re.compile(cfg["extract_list_pattern"], re.IGNORECASE)
        assert el.search("Bisa di-extract sekarang")
        assert el.search("EXTRACT — Inventory list")

    def test_put_persists_new_fields(self, http, user_ctx):
        r = http.get(f"{BASE_URL}/api/automation/config", headers=auth_h(user_ctx["token"]))
        cfg = r.json()
        cfg["already_fishing_pattern"] = r"(sedang memancing|CUSTOM_ACTIVE)"
        cfg["extract_list_pattern"] = r"(CUSTOM_EXTRACT)"
        r2 = http.put(f"{BASE_URL}/api/automation/config", json=cfg, headers=auth_h(user_ctx["token"]))
        assert r2.status_code == 200, r2.text
        assert r2.json()["already_fishing_pattern"] == r"(sedang memancing|CUSTOM_ACTIVE)"
        assert r2.json()["extract_list_pattern"] == r"(CUSTOM_EXTRACT)"

        # verify persistence
        r3 = http.get(f"{BASE_URL}/api/automation/config", headers=auth_h(user_ctx["token"]))
        cfg3 = r3.json()
        assert cfg3["already_fishing_pattern"] == r"(sedang memancing|CUSTOM_ACTIVE)"
        assert cfg3["extract_list_pattern"] == r"(CUSTOM_EXTRACT)"


# --- Code plumbing / introspection ---
class TestAutomationRunnerPlumbing:
    def test_runner_attributes_set_in_init(self):
        from automation_engine import AutomationRunner
        src = inspect.getsource(AutomationRunner.__init__)
        assert "_last_verification_at" in src
        assert "_in_verification" in src

    def test_wait_for_message_has_extend_on_active_kwarg(self):
        from automation_engine import AutomationRunner
        sig = inspect.signature(AutomationRunner._wait_for_message)
        assert "extend_on_active" in sig.parameters, f"params={list(sig.parameters)}"
        p = sig.parameters["extend_on_active"]
        # Should be a keyword arg with a default (True or False both acceptable)
        assert p.default is not inspect.Parameter.empty

    def test_resume_clears_verification_state(self):
        from automation_engine import AutomationRunner
        src = inspect.getsource(AutomationRunner.resume)
        assert "_last_verification_at" in src
        assert "_in_verification" in src
        assert "verification_url" in src

    def test_handle_verification_no_click_and_debounce(self):
        from automation_engine import AutomationRunner
        src = inspect.getsource(AutomationRunner._handle_verification)
        # Must not perform auto-click on Mini App WebView (no invocation of button click helpers)
        assert "_click_button_in_message" not in src, "handle_verification must not click Mini App button"
        assert "await ut.click" not in src, "handle_verification must not perform button click"
        # Must have debounce via _last_verification_at
        assert "_last_verification_at" in src
        # Must pause user
        assert "self.pause" in src or "await self.pause" in src

    def test_cycle_vip_passes_extend_on_active(self):
        from automation_engine import AutomationRunner
        src = inspect.getsource(AutomationRunner._cycle_vip)
        assert "extend_on_active" in src

    def test_cycle_group_passes_extend_on_active(self):
        from automation_engine import AutomationRunner
        src = inspect.getsource(AutomationRunner._cycle_group)
        assert "extend_on_active" in src


class TestTelegramManagerHandlers:
    def test_message_edited_handler_installed(self):
        """Inspect UserTelegram._install_default_handler for MessageEdited registration."""
        from telegram_manager import UserTelegram
        src = inspect.getsource(UserTelegram._install_default_handler)
        assert "MessageEdited" in src, "events.MessageEdited handler must be installed"
        # And ensure NewMessage is still installed
        assert "NewMessage" in src

    def test_edited_handler_pushes_edited_type(self):
        from telegram_manager import UserTelegram
        src = inspect.getsource(UserTelegram._install_default_handler)
        assert '"edited"' in src or "'edited'" in src, "edited events should carry type='edited'"


# --- Regression ---
class TestRegression:
    def test_health(self, http):
        r = http.get(f"{BASE_URL}/api/health")
        assert r.status_code == 200
        assert r.json().get("ok") is True

    def test_admin_login(self, http):
        r = http.post(f"{BASE_URL}/api/auth/login",
                      json={"email": "admin@fishit.app", "password": "Admin@Fishit2026"})
        assert r.status_code == 200
        assert r.json()["user"]["role"] == "admin"

    def test_events_endpoint(self, http, user_ctx):
        r = http.get(f"{BASE_URL}/api/automation/events", headers=auth_h(user_ctx["token"]))
        assert r.status_code == 200
        assert "events" in r.json()

    def test_notifications_endpoint(self, http, user_ctx):
        r = http.get(f"{BASE_URL}/api/automation/notifications", headers=auth_h(user_ctx["token"]))
        assert r.status_code == 200
        d = r.json()
        assert "notifications" in d and "unread_count" in d

    def test_pause_resume(self, http, user_ctx):
        r1 = http.post(f"{BASE_URL}/api/automation/pause", headers=auth_h(user_ctx["token"]))
        assert r1.status_code == 200
        r2 = http.post(f"{BASE_URL}/api/automation/resume", headers=auth_h(user_ctx["token"]))
        assert r2.status_code == 200
