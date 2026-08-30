"""Iter18: quick API regression - admin & elite login, config round-trip."""
import os
import re
import requests


def _load_backend_url():
    v = os.environ.get("REACT_APP_BACKEND_URL")
    if v:
        return v.rstrip("/")
    try:
        with open("/app/frontend/.env") as f:
            for line in f:
                m = re.match(r"REACT_APP_BACKEND_URL=(.+)", line.strip())
                if m:
                    return m.group(1).strip().rstrip("/")
    except FileNotFoundError:
        pass
    raise RuntimeError("REACT_APP_BACKEND_URL not configured")


BASE = _load_backend_url()

ADMIN_EMAIL = "admin@fishit.app"
ADMIN_PASSWORD = "Lpwa*PN7uCy5%wWRK@r9l%Q#"
ELITE_EMAIL = "user@fishit.app"
ELITE_PASSWORD = "FishIt#2026"


def _login(email, password):
    s = requests.Session()
    r = s.post(f"{BASE}/api/auth/login", json={"email": email, "password": password}, timeout=15)
    assert r.status_code == 200, f"login {email} => {r.status_code} {r.text}"
    return s


def test_admin_login():
    s = _login(ADMIN_EMAIL, ADMIN_PASSWORD)
    me = s.get(f"{BASE}/api/auth/me", timeout=10)
    assert me.status_code == 200
    data = me.json()
    assert data["email"] == ADMIN_EMAIL
    assert data["role"] == "admin"


def test_elite_login():
    s = _login(ELITE_EMAIL, ELITE_PASSWORD)
    me = s.get(f"{BASE}/api/auth/me", timeout=10)
    assert me.status_code == 200
    data = me.json()
    assert data["email"] == ELITE_EMAIL


def test_config_round_trip_has_boost_fields():
    s = _login(ELITE_EMAIL, ELITE_PASSWORD)
    r = s.get(f"{BASE}/api/automation/config", timeout=10)
    assert r.status_code == 200, r.text
    cfg = r.json()
    for f in ("boost_enabled", "boost_command", "group_boost_trigger_pattern", "bot_username"):
        assert f in cfg, f"missing field {f} in config: {list(cfg.keys())}"

    # PUT round-trip: toggle boost_enabled and set boost_command
    original_enabled = cfg.get("boost_enabled")
    original_cmd = cfg.get("boost_command")
    payload = dict(cfg)
    payload["boost_enabled"] = not bool(original_enabled)
    payload["boost_command"] = "/boost"
    payload["group_boost_trigger_pattern"] = "PERAHU SIAP BERANGKAT"
    put = s.put(f"{BASE}/api/automation/config", json=payload, timeout=10)
    assert put.status_code == 200, put.text
    updated = s.get(f"{BASE}/api/automation/config", timeout=10).json()
    assert updated["boost_enabled"] == (not bool(original_enabled))
    assert updated["boost_command"] == "/boost"
    assert updated["group_boost_trigger_pattern"] == "PERAHU SIAP BERANGKAT"

    # restore
    payload["boost_enabled"] = original_enabled
    payload["boost_command"] = original_cmd or "/boost"
    s.put(f"{BASE}/api/automation/config", json=payload, timeout=10)


def test_admin_create_and_delete_user():
    s = _login(ADMIN_EMAIL, ADMIN_PASSWORD)
    email = "TEST_iter18_tmp@fishit.app"
    # Cleanup pre-existing
    users = s.get(f"{BASE}/api/admin/users", timeout=10).json()
    for u in users:
        if u.get("email", "").lower() == email.lower():
            s.delete(f"{BASE}/api/admin/users/{u['id']}", timeout=10)

    reg = s.post(f"{BASE}/api/auth/register", json={"email": email, "password": "TmpPass#2026"}, timeout=15)
    # register may return 200/201 or already-exists
    assert reg.status_code in (200, 201), reg.text

    # register auto-logs-in as the newly created user - re-login as admin
    s = _login(ADMIN_EMAIL, ADMIN_PASSWORD)
    users = s.get(f"{BASE}/api/admin/users", timeout=10).json()
    target = next((u for u in users if u.get("email", "").lower() == email.lower()), None)
    assert target, "created user not found in admin list"

    dele = s.delete(f"{BASE}/api/admin/users/{target['id']}", timeout=10)
    assert dele.status_code in (200, 204), dele.text

    users2 = s.get(f"{BASE}/api/admin/users", timeout=10).json()
    assert not any(u.get("email", "").lower() == email.lower() for u in users2)
