"""Iteration 10: admin reset-password + VIP (extra_allowed_chats) plan gating."""
import os
import uuid

import pytest
import requests
from dotenv import dotenv_values

frontend_env = dotenv_values("/app/frontend/.env")
base_url = os.environ.get("REACT_APP_BACKEND_URL") or frontend_env.get("REACT_APP_BACKEND_URL")
if not base_url:
    raise RuntimeError("REACT_APP_BACKEND_URL missing")
BASE_URL = base_url.rstrip("/")

ADMIN = {"email": "admin@fishit.app", "password": dotenv_values("/app/backend/.env").get("ADMIN_PASSWORD")}
USER = {"email": "user@fishit.app", "password": "FishIt#2026"}


def login(email, password):
    r = requests.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": password}, timeout=30)
    return r


@pytest.fixture(scope="module")
def admin_token():
    r = login(**ADMIN)
    if r.status_code != 200:
        pytest.fail(f"Admin login failed {r.status_code}: {r.text[:300]}")
    return r.cookies["access_token"]


@pytest.fixture(scope="module")
def admin_h(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}


@pytest.fixture(scope="module")
def temp_user(admin_h):
    """Register a throwaway user; delete at teardown if endpoint exists."""
    email = f"test_iter10_{uuid.uuid4().hex[:8]}@example.com"
    pwd = "OldPass#123"
    r = requests.post(f"{BASE_URL}/api/auth/register",
                      json={"email": email, "password": pwd}, timeout=30)
    assert r.status_code in (200, 201), f"register failed {r.status_code}: {r.text[:300]}"
    data = r.json()
    token = r.cookies.get("access_token")
    users = requests.get(f"{BASE_URL}/api/admin/users", headers=admin_h, timeout=30).json()
    uid = data.get("user", {}).get("id") or next(
        (u["id"] for u in users if u["email"].lower() == email.lower()), None)
    assert uid, "temp user not found in admin list"
    email = data.get("user", {}).get("email", email)
    info = {"id": uid, "email": email, "password": pwd, "token": token}
    yield info
    requests.delete(f"{BASE_URL}/api/admin/users/{uid}", headers=admin_h, timeout=30)


# ---------- ADMIN RESET PASSWORD ----------
class TestAdminResetPassword:
    def test_short_password_422(self, admin_h, temp_user):
        r = requests.post(f"{BASE_URL}/api/admin/users/{temp_user['id']}/reset-password",
                          json={"new_password": "123"}, headers=admin_h, timeout=30)
        assert r.status_code == 422, r.text[:300]

    def test_non_admin_403(self, temp_user):
        h = {"Authorization": f"Bearer {temp_user['token']}"}
        r = requests.post(f"{BASE_URL}/api/admin/users/{temp_user['id']}/reset-password",
                          json={"new_password": "AnotherPass#1"}, headers=h, timeout=30)
        assert r.status_code == 403, f"expected 403 got {r.status_code}: {r.text[:300]}"

    def test_no_auth_401(self, temp_user):
        r = requests.post(f"{BASE_URL}/api/admin/users/{temp_user['id']}/reset-password",
                          json={"new_password": "AnotherPass#1"}, timeout=30)
        assert r.status_code == 401

    def test_unknown_user_404(self, admin_h):
        r = requests.post(f"{BASE_URL}/api/admin/users/{uuid.uuid4()}/reset-password",
                          json={"new_password": "AnotherPass#1"}, headers=admin_h, timeout=30)
        assert r.status_code == 404, r.text[:300]

    def test_reset_and_login(self, admin_h, temp_user):
        new_pwd = "ResetPass#456"
        r = requests.post(f"{BASE_URL}/api/admin/users/{temp_user['id']}/reset-password",
                          json={"new_password": new_pwd}, headers=admin_h, timeout=30)
        assert r.status_code == 200, r.text[:300]
        assert r.json().get("ok") is True
        # old password must fail
        old = login(temp_user["email"], temp_user["password"])
        assert old.status_code == 401, f"old password still works ({old.status_code})"
        # new password works
        new = login(temp_user["email"], new_pwd)
        assert new.status_code == 200, new.text[:300]
        assert new.cookies.get("access_token")
        body = new.json()
        assert body["user"]["email"] == temp_user["email"]
        temp_user["password"] = new_pwd


# ---------- VIP GATING (extra_allowed_chats) ----------
class TestVipGating:
    def _get_cfg(self, h):
        r = requests.get(f"{BASE_URL}/api/automation/config", headers=h, timeout=30)
        assert r.status_code == 200, r.text[:300]
        return r.json()

    def _put_cfg(self, h, cfg):
        r = requests.put(f"{BASE_URL}/api/automation/config", headers=h, json=cfg, timeout=30)
        assert r.status_code == 200, r.text[:300]
        return r.json()

    def test_free_plan_strips_extra_chats(self, admin_h, temp_user):
        # ensure plan free
        r = requests.put(f"{BASE_URL}/api/admin/users/{temp_user['id']}",
                         json={"plan": "free"}, headers=admin_h, timeout=30)
        assert r.status_code == 200, r.text[:300]
        assert r.json()["plan"] == "free"

        tok = login(temp_user["email"], temp_user["password"]).cookies["access_token"]
        h = {"Authorization": f"Bearer {tok}"}
        cfg = self._get_cfg(h)
        cfg["extra_allowed_chats"] = "@bot_a,@bot_b"
        saved = self._put_cfg(h, cfg)
        assert saved["extra_allowed_chats"] == "", saved["extra_allowed_chats"]
        # persisted as empty
        assert self._get_cfg(h)["extra_allowed_chats"] == ""

    def test_basic_plan_strips_extra_chats(self, admin_h, temp_user):
        requests.put(f"{BASE_URL}/api/admin/users/{temp_user['id']}",
                     json={"plan": "basic"}, headers=admin_h, timeout=30)
        tok = login(temp_user["email"], temp_user["password"]).cookies["access_token"]
        h = {"Authorization": f"Bearer {tok}"}
        cfg = self._get_cfg(h)
        cfg["extra_allowed_chats"] = "@bot_c"
        assert self._put_cfg(h, cfg)["extra_allowed_chats"] == ""

    def test_pro_plan_preserves_extra_chats(self, admin_h, temp_user):
        requests.put(f"{BASE_URL}/api/admin/users/{temp_user['id']}",
                     json={"plan": "pro"}, headers=admin_h, timeout=30)
        tok = login(temp_user["email"], temp_user["password"]).cookies["access_token"]
        h = {"Authorization": f"Bearer {tok}"}
        cfg = self._get_cfg(h)
        cfg["extra_allowed_chats"] = "@bot_x,@bot_y"
        saved = self._put_cfg(h, cfg)
        assert saved["extra_allowed_chats"] == "@bot_x,@bot_y"
        assert self._get_cfg(h)["extra_allowed_chats"] == "@bot_x,@bot_y"

    def test_elite_plan_preserves_extra_chats(self, admin_h, temp_user):
        requests.put(f"{BASE_URL}/api/admin/users/{temp_user['id']}",
                     json={"plan": "elite"}, headers=admin_h, timeout=30)
        tok = login(temp_user["email"], temp_user["password"]).cookies["access_token"]
        h = {"Authorization": f"Bearer {tok}"}
        cfg = self._get_cfg(h)
        cfg["extra_allowed_chats"] = "@elite_bot"
        assert self._put_cfg(h, cfg)["extra_allowed_chats"] == "@elite_bot"

    def test_seeded_elite_user_preserves_and_revert(self):
        tok = login(**USER).cookies["access_token"]
        h = {"Authorization": f"Bearer {tok}"}
        cfg = self._get_cfg(h)
        original = cfg.get("extra_allowed_chats", "")
        cfg["extra_allowed_chats"] = "@regression_bot"
        assert self._put_cfg(h, cfg)["extra_allowed_chats"] == "@regression_bot"
        cfg["extra_allowed_chats"] = original
        self._put_cfg(h, cfg)


# ---------- GROUP KICKSTART (static code assertions) ----------
class TestGroupKickstartCode:
    def test_engine_kickstart_present(self):
        src = open("/app/backend/automation_engine.py", encoding="utf-8").read()
        assert "self._group_kickstarted = False" in src
        assert "if not self._group_kickstarted:" in src
        assert "START → Sent" in src
        assert "def _group_open_command" in src
        assert '/open_mancing@' in src
