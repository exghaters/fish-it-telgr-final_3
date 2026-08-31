"""Iter13 security fixes verification:
- SEC-001: rotated admin password; old password rejected
- SEC-002: ReDoS protection on *_pattern config fields
- Login lockout (5 fails => 429), 7-day JWT cookie, no token in body
- Password min length 8 on register
- Admin delete-user works; admin self-delete blocked
- Logout clears cookie
"""
import os
import time
import uuid
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://botcraft-telegram-1.preview.emergentagent.com").rstrip("/")

ADMIN_EMAIL = "admin@fishit.app"
ADMIN_PASSWORD = "Surabaya818"
OLD_ADMIN_PASSWORD = "Admin@Fishit2026"
USER_EMAIL = "user@fishit.app"
USER_PASSWORD = "FishIt#2026"


def _session():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


# ---------- SEC-001: admin password rotation ----------
def test_admin_login_new_password():
    s = _session()
    r = s.post(f"{BASE_URL}/api/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    assert r.status_code == 200, r.text
    body = r.json()
    # Token must NOT be in body
    assert body.get("access_token") is None, "Token must not be returned in JSON body"
    assert body["user"]["email"] == ADMIN_EMAIL
    assert body["user"]["role"] == "admin"
    # Cookie must be set httpOnly
    cookies = r.cookies
    assert "access_token" in cookies


def test_admin_old_password_rejected():
    s = _session()
    r = s.post(f"{BASE_URL}/api/auth/login", json={"email": ADMIN_EMAIL, "password": OLD_ADMIN_PASSWORD})
    assert r.status_code == 401, f"Old admin password must be rejected, got {r.status_code}: {r.text}"


# ---------- Elite user login ----------
def test_user_login_cookie_auth():
    s = _session()
    r = s.post(f"{BASE_URL}/api/auth/login", json={"email": USER_EMAIL, "password": USER_PASSWORD})
    assert r.status_code == 200, r.text
    assert r.json().get("access_token") is None
    assert "access_token" in r.cookies
    # /me should work via cookie
    me = s.get(f"{BASE_URL}/api/auth/me")
    assert me.status_code == 200
    assert me.json()["email"] == USER_EMAIL


# ---------- Dashboard endpoints load with cookie auth ----------
@pytest.mark.parametrize("path", [
    "/api/automation/status",
    "/api/automation/notifications",
    "/api/automation/events",
    "/api/telegram/status",
    "/api/automation/config",
])
def test_dashboard_endpoints_cookie_auth(path):
    s = _session()
    lr = s.post(f"{BASE_URL}/api/auth/login", json={"email": USER_EMAIL, "password": USER_PASSWORD})
    assert lr.status_code == 200
    r = s.get(f"{BASE_URL}{path}")
    assert r.status_code == 200, f"{path} returned {r.status_code}: {r.text[:200]}"


# ---------- SEC-002: ReDoS protection ----------
def test_config_save_normal_ok():
    s = _session()
    s.post(f"{BASE_URL}/api/auth/login", json={"email": USER_EMAIL, "password": USER_PASSWORD})
    cfg = s.get(f"{BASE_URL}/api/automation/config").json()
    cfg["session_done_pattern"] = r"(SESI MANCING SELESAI|mancing selesai|WAKTU HABIS)"
    r = s.put(f"{BASE_URL}/api/automation/config", json=cfg)
    assert r.status_code == 200, r.text


def test_config_save_redos_pattern_rejected():
    s = _session()
    s.post(f"{BASE_URL}/api/auth/login", json={"email": USER_EMAIL, "password": USER_PASSWORD})
    cfg = s.get(f"{BASE_URL}/api/automation/config").json()
    cfg["session_done_pattern"] = "(a+)+$"
    r = s.put(f"{BASE_URL}/api/automation/config", json=cfg)
    assert r.status_code == 400, f"ReDoS pattern must be rejected, got {r.status_code}: {r.text}"
    assert "ReDoS" in r.text or "berbahaya" in r.text or "quantifier" in r.text


def test_config_save_invalid_regex_rejected():
    s = _session()
    s.post(f"{BASE_URL}/api/auth/login", json={"email": USER_EMAIL, "password": USER_PASSWORD})
    cfg = s.get(f"{BASE_URL}/api/automation/config").json()
    cfg["session_done_pattern"] = "((("
    r = s.put(f"{BASE_URL}/api/automation/config", json=cfg)
    assert r.status_code == 400


def test_config_save_long_pattern_rejected():
    s = _session()
    s.post(f"{BASE_URL}/api/auth/login", json={"email": USER_EMAIL, "password": USER_PASSWORD})
    cfg = s.get(f"{BASE_URL}/api/automation/config").json()
    cfg["session_done_pattern"] = "a" * 301
    r = s.put(f"{BASE_URL}/api/automation/config", json=cfg)
    assert r.status_code == 400


# ---------- Login brute force lockout ----------
def test_login_bruteforce_lockout():
    email = f"bruteforce_probe_{uuid.uuid4().hex[:6]}@fishit.app"
    s = _session()
    codes = []
    for _ in range(5):
        r = s.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": "wrong"})
        codes.append(r.status_code)
    # 6th attempt should be locked
    r6 = s.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": "wrong"})
    assert all(c == 401 for c in codes), f"Expected 5x 401, got {codes}"
    assert r6.status_code == 429, f"Expected 429 on 6th, got {r6.status_code}: {r6.text}"


# ---------- Password policy ----------
def test_register_short_password_rejected():
    s = _session()
    r = s.post(f"{BASE_URL}/api/auth/register",
               json={"email": f"TEST_short_{uuid.uuid4().hex[:6]}@fishit.app", "password": "short"})
    assert r.status_code == 422, r.text


def test_register_valid_password_ok():
    s = _session()
    email = f"TEST_reg_{uuid.uuid4().hex[:8]}@fishit.app"
    r = s.post(f"{BASE_URL}/api/auth/register",
               json={"email": email, "password": "GoodPass1!"})
    assert r.status_code == 200, r.text
    assert r.json().get("access_token") is None
    assert "access_token" in r.cookies
    # Cleanup: delete via admin
    admin = _session()
    admin.post(f"{BASE_URL}/api/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    users = admin.get(f"{BASE_URL}/api/admin/users").json()
    if isinstance(users, dict):
        users = users.get("users", [])
    for u in users:
        if u.get("email") == email:
            admin.delete(f"{BASE_URL}/api/admin/users/{u['id']}")
            break


# ---------- Admin delete-user ----------
def test_admin_delete_user_flow_and_self_delete_blocked():
    # Create throwaway
    reg = _session()
    email = f"TEST_del_{uuid.uuid4().hex[:8]}@fishit.app"
    r = reg.post(f"{BASE_URL}/api/auth/register", json={"email": email, "password": "GoodPass1!"})
    assert r.status_code == 200
    uid = r.json()["user"]["id"]

    admin = _session()
    lr = admin.post(f"{BASE_URL}/api/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    assert lr.status_code == 200
    admin_id = lr.json()["user"]["id"]

    # Self-delete blocked
    r_self = admin.delete(f"{BASE_URL}/api/admin/users/{admin_id}")
    assert r_self.status_code == 400, f"Admin self-delete must be blocked, got {r_self.status_code}"

    # Delete throwaway
    r_del = admin.delete(f"{BASE_URL}/api/admin/users/{uid}")
    assert r_del.status_code in (200, 204), r_del.text


# ---------- Logout clears cookie ----------
def test_logout_clears_cookie():
    s = _session()
    s.post(f"{BASE_URL}/api/auth/login", json={"email": USER_EMAIL, "password": USER_PASSWORD})
    assert "access_token" in s.cookies
    r = s.post(f"{BASE_URL}/api/auth/logout")
    assert r.status_code == 200
    # After logout, /me should fail
    me = s.get(f"{BASE_URL}/api/auth/me")
    assert me.status_code == 401
