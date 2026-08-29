"""Iteration 7 — auth + automation config persistence regression."""
import os

import pytest
import requests
from dotenv import dotenv_values

frontend_env = dotenv_values("/app/frontend/.env")
base_url = os.environ.get("REACT_APP_BACKEND_URL") or frontend_env.get("REACT_APP_BACKEND_URL")
if not base_url:
    raise RuntimeError("REACT_APP_BACKEND_URL missing")
BASE_URL = base_url.rstrip("/")

ADMIN = {"email": "admin@fishit.app", "password": dotenv_values("/app/backend/.env").get("ADMIN_PASSWORD")}


@pytest.fixture(scope="module")
def client():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


@pytest.fixture(scope="module")
def token(client):
    r = client.post(f"{BASE_URL}/api/auth/login", json=ADMIN, timeout=30)
    if r.status_code != 200:
        pytest.fail(f"admin login failed {r.status_code}: {r.text[:300]}")
    tok = r.cookies.get("access_token")
    assert tok, "no auth cookie set on login"
    return tok


@pytest.fixture(scope="module")
def auth(client, token):
    client.headers.update({"Authorization": f"Bearer {token}"})
    return client


# --- auth ---
def test_login_bad_password(client):
    r = client.post(f"{BASE_URL}/api/auth/login",
                    json={"email": ADMIN["email"], "password": "wrong"}, timeout=30)
    assert r.status_code in (400, 401), r.text[:300]


def test_me(auth):
    r = auth.get(f"{BASE_URL}/api/auth/me", timeout=30)
    assert r.status_code == 200, r.text[:300]
    d = r.json()
    assert d["email"] == ADMIN["email"]
    assert "_id" not in d


# --- config GET/PUT persistence ---
def test_config_get(auth):
    r = auth.get(f"{BASE_URL}/api/automation/config", timeout=30)
    assert r.status_code == 200, r.text[:300]
    d = r.json()
    assert "_id" not in d
    for k in ("boost_enabled", "protect_min_coins", "favorite_command_template",
              "protect_rarity_pattern", "inventory_command", "sell_command"):
        assert k in d, f"missing {k}"


def test_config_put_persists(auth):
    orig = auth.get(f"{BASE_URL}/api/automation/config", timeout=30).json()
    new_boost = not bool(orig.get("boost_enabled"))
    new_min = int(orig.get("protect_min_coins") or 0) + 12345
    payload = dict(orig)
    payload.pop("_id", None)
    payload["boost_enabled"] = new_boost
    payload["protect_min_coins"] = new_min
    r = auth.put(f"{BASE_URL}/api/automation/config", json=payload, timeout=30)
    assert r.status_code == 200, r.text[:300]
    saved = r.json()
    assert saved["boost_enabled"] == new_boost
    assert saved["protect_min_coins"] == new_min
    # reload
    again = auth.get(f"{BASE_URL}/api/automation/config", timeout=30).json()
    assert again["boost_enabled"] == new_boost
    assert again["protect_min_coins"] == new_min
    # restore
    restore = dict(orig)
    restore.pop("_id", None)
    rr = auth.put(f"{BASE_URL}/api/automation/config", json=restore, timeout=30)
    assert rr.status_code == 200


def test_config_requires_auth(client):
    s = requests.Session()
    r = s.get(f"{BASE_URL}/api/automation/config", timeout=30)
    assert r.status_code in (401, 403), r.status_code


# --- dashboard endpoints used by layout ---
def test_notifications_endpoint(auth):
    r = auth.get(f"{BASE_URL}/api/automation/notifications", params={"limit": 1}, timeout=30)
    assert r.status_code == 200, r.text[:300]
    d = r.json()
    assert "unread_count" in d


def test_status_endpoint(auth):
    r = auth.get(f"{BASE_URL}/api/automation/status", timeout=30)
    assert r.status_code == 200, r.text[:300]
