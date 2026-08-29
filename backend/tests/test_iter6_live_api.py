"""Iteration 6 — live API surface tests: auth, automation config CRUD, status/events/notifications,
start/stop, telegram status, admin endpoints."""
import os
import re
import time
import uuid
from pathlib import Path

import pytest
import requests
from dotenv import dotenv_values

frontend_env = dotenv_values("/app/frontend/.env")
base_url = os.environ.get("REACT_APP_BACKEND_URL") or frontend_env.get("REACT_APP_BACKEND_URL")
if not base_url:
    raise RuntimeError("REACT_APP_BACKEND_URL missing")
BASE_URL = base_url.rstrip("/")


@pytest.fixture(scope="session")
def creds():
    p = Path("/app/memory/test_credentials.md")
    if not p.exists():
        pytest.skip("missing test_credentials.md")
    c = p.read_text()
    e = re.search(r'(?im)^\s*(?:[-*]\s*)?(?:\*\*)?email(?:\*\*)?\s*:\s*`?([^`\s]+)', c)
    pw = re.search(r'(?im)^\s*(?:[-*]\s*)?(?:\*\*)?password(?:\*\*)?\s*:\s*`?([^`\s]+)', c)
    if not e or not pw:
        pytest.skip("no creds parsed")
    return {"email": e.group(1), "password": pw.group(1)}


@pytest.fixture(scope="module")
def client():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


@pytest.fixture(scope="module")
def admin_token(creds):
    r = requests.post(f"{BASE_URL}/api/auth/login", json=creds, timeout=30)
    if r.status_code != 200:
        pytest.fail(f"admin login failed {r.status_code}: {r.text[:300]}")
    tok = r.json().get("access_token")
    assert tok
    return tok


@pytest.fixture(scope="module")
def admin_client(admin_token):
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json",
                      "Authorization": f"Bearer {admin_token}"})
    return s


# ---------- health & auth ----------
class TestHealthAuth:
    def test_health(self, client):
        r = client.get(f"{BASE_URL}/api/health", timeout=30)
        assert r.status_code == 200, r.text[:300]
        assert r.json().get("status") in ("ok", "healthy", True) or r.json()

    def test_admin_login(self, creds, client):
        r = client.post(f"{BASE_URL}/api/auth/login", json=creds, timeout=30)
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        assert d["token_type"] == "bearer"
        assert d["user"]["email"] == creds["email"]
        assert d["user"]["role"] == "admin"
        assert isinstance(d["access_token"], str) and len(d["access_token"]) > 20

    def test_login_wrong_password(self, creds, client):
        r = client.post(f"{BASE_URL}/api/auth/login",
                        json={"email": creds["email"], "password": "WrongPass123"}, timeout=30)
        assert r.status_code == 401
        assert "detail" in r.json()

    def test_me(self, admin_client, creds):
        r = admin_client.get(f"{BASE_URL}/api/auth/me", timeout=30)
        assert r.status_code == 200, r.text[:300]
        assert r.json()["email"] == creds["email"]

    def test_me_no_token(self, client):
        client.cookies.clear()  # ensure no auth cookie leaks from earlier login
        r = client.get(f"{BASE_URL}/api/auth/me", timeout=30)
        assert r.status_code in (401, 403), r.status_code

    def test_me_bad_token(self, client):
        r = client.get(f"{BASE_URL}/api/auth/me",
                       headers={"Authorization": "Bearer garbage.token.xyz"}, timeout=30)
        assert r.status_code == 401, r.status_code

    def test_register_new_user_and_duplicate(self, client):
        email = f"TEST_iter6_{uuid.uuid4().hex[:8]}@example.com".lower()
        r = client.post(f"{BASE_URL}/api/auth/register",
                        json={"email": email, "password": "Passw0rd!"}, timeout=30)
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        assert d["user"]["email"] == email
        assert d["user"]["role"] == "user"
        assert d["user"]["plan"] == "free"
        tok = d["access_token"]
        # token works
        me = client.get(f"{BASE_URL}/api/auth/me",
                        headers={"Authorization": f"Bearer {tok}"}, timeout=30)
        assert me.status_code == 200
        assert me.json()["email"] == email
        # duplicate
        dup = client.post(f"{BASE_URL}/api/auth/register",
                          json={"email": email, "password": "Passw0rd!"}, timeout=30)
        assert dup.status_code == 400
        # short password rejected
        bad = client.post(f"{BASE_URL}/api/auth/register",
                          json={"email": f"TEST_x{uuid.uuid4().hex[:6]}@example.com", "password": "123"},
                          timeout=30)
        assert bad.status_code == 422, bad.status_code
        # invalid email
        bad2 = client.post(f"{BASE_URL}/api/auth/register",
                           json={"email": "not-an-email", "password": "Passw0rd!"}, timeout=30)
        assert bad2.status_code == 422


# ---------- automation config ----------
CONFIG_KEYS = ["boost_enabled", "boost_command", "boost_trigger_pattern",
               "boost_cooldown_seconds", "extra_allowed_chats", "join_button_text",
               "mode", "bot_username"]


class TestAutomationConfig:
    def test_get_config_has_required_fields(self, admin_client):
        r = admin_client.get(f"{BASE_URL}/api/automation/config", timeout=30)
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        for k in CONFIG_KEYS:
            assert k in d, f"missing {k}"
        assert "_id" not in d
        assert isinstance(d["boost_enabled"], bool)
        assert isinstance(d["boost_cooldown_seconds"], int)

    def test_config_requires_auth(self, client):
        client.cookies.clear()  # ensure no auth cookie leaks from earlier login
        r = client.get(f"{BASE_URL}/api/automation/config", timeout=30)
        assert r.status_code in (401, 403)

    def test_update_config_persists(self, admin_client):
        cur = admin_client.get(f"{BASE_URL}/api/automation/config", timeout=30).json()
        payload = dict(cur)
        payload.update({
            "boost_enabled": True,
            "boost_command": "/boost",
            "boost_trigger_pattern": r"(PERAHU SIAP BERANGKAT|AUTO MANCING DIMULAI|TEST_TRIGGER)",
            "boost_cooldown_seconds": 420,
            "extra_allowed_chats": "@fish_it_vip_bot, @fish_it_vip3_bot, @fish_it_vip4_bot, @fish_it_vip5_bot",
            "join_button_text": "Daftar Mancing",
            "mode": "vip_direct",
            "bot_username": "@fish_it_bot",
        })
        r = admin_client.put(f"{BASE_URL}/api/automation/config", json=payload, timeout=30)
        assert r.status_code == 200, r.text[:400]
        out = r.json()
        assert out["boost_enabled"] is True
        assert out["boost_cooldown_seconds"] == 420

        g = admin_client.get(f"{BASE_URL}/api/automation/config", timeout=30)
        assert g.status_code == 200
        saved = g.json()
        for k in ("boost_enabled", "boost_command", "boost_trigger_pattern",
                  "boost_cooldown_seconds", "extra_allowed_chats", "join_button_text",
                  "mode", "bot_username"):
            assert saved[k] == payload[k], f"{k} not persisted: {saved[k]!r}"

    def test_config_isolated_per_user(self, admin_client, client):
        email = f"TEST_iso_{uuid.uuid4().hex[:8]}@example.com"
        reg = client.post(f"{BASE_URL}/api/auth/register",
                          json={"email": email, "password": "Passw0rd!"}, timeout=30)
        assert reg.status_code == 200
        tok = reg.json()["access_token"]
        h = {"Authorization": f"Bearer {tok}", "Content-Type": "application/json"}
        r = requests.get(f"{BASE_URL}/api/automation/config", headers=h, timeout=30)
        assert r.status_code == 200
        fresh = r.json()
        # defaults for a brand new user
        assert fresh["boost_enabled"] is False
        assert "@fish_it_vip_bot" in fresh["extra_allowed_chats"]
        assert fresh["join_button_text"] == "Daftar Mancing"
        assert fresh["bot_username"] == "@fish_it_bot"

    def test_update_config_invalid_mode_rejected(self, admin_client):
        cur = admin_client.get(f"{BASE_URL}/api/automation/config", timeout=30).json()
        cur["mode"] = "nonsense_mode"
        r = admin_client.put(f"{BASE_URL}/api/automation/config", json=cur, timeout=30)
        assert r.status_code == 422, r.status_code


# ---------- status / events / notifications / start-stop ----------
class TestAutomationRuntime:
    def test_status(self, admin_client):
        r = admin_client.get(f"{BASE_URL}/api/automation/status", timeout=30)
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        assert "status" in d and "cycle" in d and "fish_caught" in d
        assert "_id" not in d

    def test_events(self, admin_client):
        r = admin_client.get(f"{BASE_URL}/api/automation/events?limit=50", timeout=30)
        assert r.status_code == 200, r.text[:300]
        assert isinstance(r.json()["events"], list)

    def test_events_limit_validation(self, admin_client):
        r = admin_client.get(f"{BASE_URL}/api/automation/events?limit=9999", timeout=30)
        assert r.status_code == 422, r.status_code

    def test_notifications(self, admin_client):
        r = admin_client.get(f"{BASE_URL}/api/automation/notifications", timeout=30)
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        assert isinstance(d["notifications"], list)
        assert isinstance(d["unread_count"], int)

    def test_notifications_read_all(self, admin_client):
        r = admin_client.post(f"{BASE_URL}/api/automation/notifications/read-all", timeout=30)
        assert r.status_code == 200
        assert r.json()["ok"] is True
        g = admin_client.get(f"{BASE_URL}/api/automation/notifications", timeout=30).json()
        assert g["unread_count"] == 0

    def test_mark_read_unknown_id(self, admin_client):
        r = admin_client.post(f"{BASE_URL}/api/automation/notifications/{uuid.uuid4()}/read", timeout=30)
        assert r.status_code == 200
        assert r.json()["ok"] is False

    def test_start_without_usernames_returns_400(self, client):
        email = f"TEST_start_{uuid.uuid4().hex[:8]}@example.com"
        tok = client.post(f"{BASE_URL}/api/auth/register",
                          json={"email": email, "password": "Passw0rd!"},
                          timeout=30).json()["access_token"]
        h = {"Authorization": f"Bearer {tok}", "Content-Type": "application/json"}
        cfg = requests.get(f"{BASE_URL}/api/automation/config", headers=h, timeout=30).json()
        cfg["bot_username"] = ""
        cfg["group_username"] = ""
        up = requests.put(f"{BASE_URL}/api/automation/config", headers=h, json=cfg, timeout=30)
        assert up.status_code == 200
        r = requests.post(f"{BASE_URL}/api/automation/start", headers=h, timeout=60)
        assert r.status_code == 400, f"expected 400, got {r.status_code}: {r.text[:300]}"

    def test_start_with_bot_username_then_stop(self, admin_client):
        cfg = admin_client.get(f"{BASE_URL}/api/automation/config", timeout=30).json()
        cfg["bot_username"] = "@fish_it_bot"
        assert admin_client.put(f"{BASE_URL}/api/automation/config", json=cfg,
                                timeout=30).status_code == 200
        r = admin_client.post(f"{BASE_URL}/api/automation/start", timeout=90)
        assert r.status_code in (200, 400), r.text[:400]
        if r.status_code == 200:
            assert r.json()["ok"] is True
            time.sleep(2)
            st = admin_client.get(f"{BASE_URL}/api/automation/status", timeout=30)
            assert st.status_code == 200
        s = admin_client.post(f"{BASE_URL}/api/automation/stop", timeout=60)
        assert s.status_code == 200, s.text[:300]
        assert s.json()["ok"] is True
        after = admin_client.get(f"{BASE_URL}/api/automation/config", timeout=30).json()
        assert after["enabled"] is False

    def test_pause_resume_do_not_500(self, admin_client):
        for ep in ("pause", "resume"):
            r = admin_client.post(f"{BASE_URL}/api/automation/{ep}", timeout=60)
            assert r.status_code < 500, f"{ep} -> {r.status_code} {r.text[:200]}"


# ---------- telegram (metadata only, no real MTProto) ----------
class TestTelegram:
    def test_status(self, admin_client):
        r = admin_client.get(f"{BASE_URL}/api/telegram/status", timeout=30)
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        assert "connected" in d and "api_id_set" in d

    def test_status_requires_auth(self, client):
        client.cookies.clear()  # ensure no auth cookie leaks from earlier login
        r = client.get(f"{BASE_URL}/api/telegram/status", timeout=30)
        assert r.status_code in (401, 403)

    def test_send_code_without_creds_no_500(self, client):
        email = f"TEST_tg_{uuid.uuid4().hex[:8]}@example.com"
        tok = client.post(f"{BASE_URL}/api/auth/register",
                          json={"email": email, "password": "Passw0rd!"},
                          timeout=30).json()["access_token"]
        h = {"Authorization": f"Bearer {tok}", "Content-Type": "application/json"}
        r = requests.post(f"{BASE_URL}/api/telegram/send-code", headers=h,
                          json={"phone": "+15551234567"}, timeout=60)
        assert r.status_code < 500, f"{r.status_code}: {r.text[:300]}"

    def test_invalid_phone_format(self, admin_client):
        r = admin_client.post(f"{BASE_URL}/api/telegram/send-code",
                              json={"phone": "12345"}, timeout=30)
        assert r.status_code == 422


# ---------- admin ----------
class TestAdmin:
    def test_list_users(self, admin_client):
        r = admin_client.get(f"{BASE_URL}/api/admin/users", timeout=30)
        assert r.status_code == 200, r.text[:300]
        users = r.json()
        assert isinstance(users, list) and len(users) >= 1
        assert all("_id" not in u for u in users)
        assert all("password_hash" not in u for u in users)

    def test_stats(self, admin_client):
        r = admin_client.get(f"{BASE_URL}/api/admin/stats", timeout=30)
        assert r.status_code == 200, r.text[:300]
        assert isinstance(r.json(), dict)

    def test_non_admin_forbidden(self, client):
        email = f"TEST_nonadmin_{uuid.uuid4().hex[:8]}@example.com"
        tok = client.post(f"{BASE_URL}/api/auth/register",
                          json={"email": email, "password": "Passw0rd!"},
                          timeout=30).json()["access_token"]
        h = {"Authorization": f"Bearer {tok}"}
        r = requests.get(f"{BASE_URL}/api/admin/users", headers=h, timeout=30)
        assert r.status_code == 403, r.status_code

    def test_update_user_plan(self, admin_client, client):
        email = f"TEST_plan_{uuid.uuid4().hex[:8]}@example.com"
        uid = client.post(f"{BASE_URL}/api/auth/register",
                          json={"email": email, "password": "Passw0rd!"},
                          timeout=30).json()["user"]["id"]
        r = admin_client.put(f"{BASE_URL}/api/admin/users/{uid}", json={"plan": "pro"}, timeout=30)
        assert r.status_code == 200, r.text[:300]
        assert r.json()["plan"] == "pro"
        users = admin_client.get(f"{BASE_URL}/api/admin/users", timeout=30).json()
        found = [u for u in users if u["id"] == uid]
        assert found and found[0]["plan"] == "pro"
