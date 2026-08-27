"""Backend API tests for Fish It Automation."""
import os
import uuid
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://botcraft-telegram-1.preview.emergentagent.com").rstrip("/")

ADMIN_EMAIL = "admin@fishit.app"
ADMIN_PASSWORD = "Admin@Fishit2026"


@pytest.fixture(scope="session")
def http():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


@pytest.fixture(scope="session")
def admin_token(http):
    r = http.post(f"{BASE_URL}/api/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


@pytest.fixture(scope="session")
def user_ctx(http):
    email = f"test_{uuid.uuid4().hex[:8]}@fishit.app"
    pw = "Testpass@123"
    r = http.post(f"{BASE_URL}/api/auth/register", json={"email": email, "password": pw})
    assert r.status_code == 200, r.text
    data = r.json()
    return {"email": email, "password": pw, "token": data["access_token"], "id": data["user"]["id"]}


def auth_h(token):
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


# ---------- Health ----------
def test_health(http):
    r = http.get(f"{BASE_URL}/api/health")
    assert r.status_code == 200
    assert r.json().get("ok") is True


# ---------- Auth ----------
class TestAuth:
    def test_register_and_login(self, http):
        email = f"regtest_{uuid.uuid4().hex[:8]}@fishit.app"
        pw = "Strongpass@1"
        r = http.post(f"{BASE_URL}/api/auth/register", json={"email": email, "password": pw})
        assert r.status_code == 200, r.text
        d = r.json()
        assert "access_token" in d and d["user"]["email"] == email
        assert d["user"]["role"] == "user"

        # Duplicate register
        r2 = http.post(f"{BASE_URL}/api/auth/register", json={"email": email, "password": pw})
        assert r2.status_code == 400

        # Login
        r3 = http.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": pw})
        assert r3.status_code == 200
        token = r3.json()["access_token"]

        # /me
        r4 = http.get(f"{BASE_URL}/api/auth/me", headers=auth_h(token))
        assert r4.status_code == 200
        assert r4.json()["email"] == email

    def test_login_invalid(self, http):
        r = http.post(f"{BASE_URL}/api/auth/login", json={"email": "nope@fishit.app", "password": "bad"})
        assert r.status_code == 401

    def test_me_requires_auth(self, http):
        r = http.get(f"{BASE_URL}/api/auth/me")
        assert r.status_code == 401


# ---------- Automation ----------
class TestAutomation:
    def test_get_config_default(self, http, user_ctx):
        r = http.get(f"{BASE_URL}/api/automation/config", headers=auth_h(user_ctx["token"]))
        assert r.status_code == 200, r.text
        cfg = r.json()
        assert cfg["mode"] == "vip_direct"
        assert cfg["bot_username"] == "@fish_it_bot"
        assert cfg["user_id"] == user_ctx["id"]

    def test_update_config(self, http, user_ctx):
        r = http.get(f"{BASE_URL}/api/automation/config", headers=auth_h(user_ctx["token"]))
        cfg = r.json()
        cfg["bot_username"] = "@my_test_bot"
        cfg["vip_gap_seconds"] = 15
        r2 = http.put(f"{BASE_URL}/api/automation/config", json=cfg, headers=auth_h(user_ctx["token"]))
        assert r2.status_code == 200, r2.text
        assert r2.json()["bot_username"] == "@my_test_bot"

        # verify persisted
        r3 = http.get(f"{BASE_URL}/api/automation/config", headers=auth_h(user_ctx["token"]))
        assert r3.json()["bot_username"] == "@my_test_bot"
        assert r3.json()["vip_gap_seconds"] == 15

    def test_status_default(self, http, user_ctx):
        r = http.get(f"{BASE_URL}/api/automation/status", headers=auth_h(user_ctx["token"]))
        assert r.status_code == 200
        assert r.json()["status"] in ("idle", "stopped")

    def test_start_stop(self, http, user_ctx):
        # Ensure bot_username present
        r = http.post(f"{BASE_URL}/api/automation/start", headers=auth_h(user_ctx["token"]))
        assert r.status_code == 200, r.text
        assert r.json()["ok"] is True

        r2 = http.post(f"{BASE_URL}/api/automation/stop", headers=auth_h(user_ctx["token"]))
        assert r2.status_code == 200

    def test_start_without_target_returns_400(self, http):
        # New user, clear bot_username to empty
        email = f"empty_{uuid.uuid4().hex[:8]}@fishit.app"
        pw = "Testpass@1"
        reg = http.post(f"{BASE_URL}/api/auth/register", json={"email": email, "password": pw}).json()
        tok = reg["access_token"]
        cfg = http.get(f"{BASE_URL}/api/automation/config", headers=auth_h(tok)).json()
        cfg["bot_username"] = ""
        cfg["group_username"] = ""
        http.put(f"{BASE_URL}/api/automation/config", json=cfg, headers=auth_h(tok))
        r = http.post(f"{BASE_URL}/api/automation/start", headers=auth_h(tok))
        assert r.status_code == 400, r.text

    def test_pause_resume(self, http, user_ctx):
        r = http.post(f"{BASE_URL}/api/automation/pause", headers=auth_h(user_ctx["token"]))
        assert r.status_code == 200
        r2 = http.post(f"{BASE_URL}/api/automation/resume", headers=auth_h(user_ctx["token"]))
        assert r2.status_code == 200

    def test_events(self, http, user_ctx):
        r = http.get(f"{BASE_URL}/api/automation/events", headers=auth_h(user_ctx["token"]))
        assert r.status_code == 200
        assert "events" in r.json()

    def test_notifications(self, http, user_ctx):
        r = http.get(f"{BASE_URL}/api/automation/notifications", headers=auth_h(user_ctx["token"]))
        assert r.status_code == 200
        data = r.json()
        assert "notifications" in data and "unread_count" in data

    def test_mark_all_read(self, http, user_ctx):
        r = http.post(f"{BASE_URL}/api/automation/notifications/read-all", headers=auth_h(user_ctx["token"]))
        assert r.status_code == 200


# ---------- Telegram ----------
class TestTelegram:
    def test_status(self, http, user_ctx):
        r = http.get(f"{BASE_URL}/api/telegram/status", headers=auth_h(user_ctx["token"]))
        assert r.status_code == 200
        d = r.json()
        assert d["connected"] is False

    def test_save_credentials(self, http, user_ctx):
        r = http.post(
            f"{BASE_URL}/api/telegram/credentials",
            json={"api_id": 123456, "api_hash": "abcdef1234567890abcdef1234567890"},
            headers=auth_h(user_ctx["token"]),
        )
        assert r.status_code == 200, r.text
        assert r.json()["ok"] is True

    def test_send_code_without_creds_fails(self, http):
        email = f"tg_{uuid.uuid4().hex[:8]}@fishit.app"
        reg = http.post(f"{BASE_URL}/api/auth/register", json={"email": email, "password": "Testpass@1"}).json()
        tok = reg["access_token"]
        r = http.post(
            f"{BASE_URL}/api/telegram/send-code",
            json={"phone": "+15551234567"},
            headers=auth_h(tok),
        )
        assert r.status_code == 400


# ---------- Admin ----------
class TestAdmin:
    def test_admin_list_users(self, http, admin_token):
        r = http.get(f"{BASE_URL}/api/admin/users", headers=auth_h(admin_token))
        assert r.status_code == 200
        arr = r.json()
        assert isinstance(arr, list) and len(arr) >= 1
        assert any(u["email"] == ADMIN_EMAIL for u in arr)

    def test_admin_stats(self, http, admin_token):
        r = http.get(f"{BASE_URL}/api/admin/stats", headers=auth_h(admin_token))
        assert r.status_code == 200
        d = r.json()
        assert "total_users" in d

    def test_admin_update_user(self, http, admin_token, user_ctx):
        r = http.put(
            f"{BASE_URL}/api/admin/users/{user_ctx['id']}",
            json={"plan": "pro"},
            headers=auth_h(admin_token),
        )
        assert r.status_code == 200, r.text
        assert r.json()["plan"] == "pro"

    def test_non_admin_forbidden(self, http, user_ctx):
        r = http.get(f"{BASE_URL}/api/admin/users", headers=auth_h(user_ctx["token"]))
        assert r.status_code == 403
