"""Iter4 tests: Elite login, resume idempotency, notifications seeding + admin visibility."""
import os
import uuid
import pytest
import requests
from datetime import datetime, timezone
from pymongo import MongoClient

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "test_database")

ADMIN_EMAIL = "admin@fishit.app"
ADMIN_PASS = "Admin@Fishit2026"
ELITE_EMAIL = "elite@fishit.app"
ELITE_PASS = "Elite@Fishit2026"


@pytest.fixture(scope="module")
def s():
    return requests.Session()


@pytest.fixture(scope="module")
def elite_token(s):
    r = s.post(f"{BASE_URL}/api/auth/login",
               json={"email": ELITE_EMAIL, "password": ELITE_PASS})
    assert r.status_code == 200, f"Elite login failed: {r.status_code} {r.text}"
    data = r.json()
    assert "access_token" in data or "token" in data
    return data.get("access_token") or data.get("token"), data


@pytest.fixture(scope="module")
def admin_token(s):
    r = s.post(f"{BASE_URL}/api/auth/login",
               json={"email": ADMIN_EMAIL, "password": ADMIN_PASS})
    assert r.status_code == 200
    d = r.json()
    return d.get("access_token") or d.get("token")


# ---- Elite login & JWT plan ----

def test_elite_login_returns_plan_elite(elite_token):
    _, data = elite_token
    user = data.get("user") or {}
    assert user.get("plan") == "elite", f"Expected plan=elite, got: {user}"
    assert user.get("email") == ELITE_EMAIL


def test_elite_access_config(s, elite_token):
    token, _ = elite_token
    r = s.get(f"{BASE_URL}/api/automation/config",
              headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    assert "user_id" in r.json()


def test_elite_access_status(s, elite_token):
    token, _ = elite_token
    r = s.get(f"{BASE_URL}/api/automation/status",
              headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200


def test_elite_access_telegram_status(s, elite_token):
    token, _ = elite_token
    r = s.get(f"{BASE_URL}/api/telegram/status",
              headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200


def test_elite_access_notifications(s, elite_token):
    token, _ = elite_token
    r = s.get(f"{BASE_URL}/api/automation/notifications",
              headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    assert "notifications" in r.json()


# ---- Resume idempotency ----

def test_resume_idempotent_no_runner(s, elite_token):
    token, _ = elite_token
    r = s.post(f"{BASE_URL}/api/automation/resume",
               headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200, f"Resume failed: {r.status_code} {r.text}"
    assert r.json().get("ok") is True


def test_resume_twice_idempotent(s, elite_token):
    token, _ = elite_token
    for _ in range(2):
        r = s.post(f"{BASE_URL}/api/automation/resume",
                   headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200


# ---- Admin visibility ----

def test_admin_sees_elite_user(s, admin_token):
    r = s.get(f"{BASE_URL}/api/admin/users",
              headers={"Authorization": f"Bearer {admin_token}"})
    assert r.status_code == 200
    users = r.json()
    if isinstance(users, dict):
        users = users.get("users", [])
    elite = [u for u in users if u.get("email") == ELITE_EMAIL]
    assert len(elite) == 1, f"Elite user not found in admin list"
    assert elite[0].get("plan") == "elite"


# ---- Seed verification notification & test mark-read flow ----

@pytest.fixture(scope="module")
def seeded_notif(s, elite_token):
    token, data = elite_token
    user_id = data["user"]["id"]
    client = MongoClient(MONGO_URL)
    db = client[DB_NAME]
    notif = {
        "id": f"test-verify-{uuid.uuid4()}",
        "user_id": user_id,
        "title": "Verifikasi Diperlukan (TEST)",
        "body": "Silakan verifikasi captcha",
        "kind": "verification",
        "read": False,
        "action_url": "https://example.com/verify",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    db.notifications.insert_one(notif.copy())
    yield notif
    db.notifications.delete_one({"id": notif["id"]})
    client.close()


def test_seeded_notif_visible(s, elite_token, seeded_notif):
    token, _ = elite_token
    r = s.get(f"{BASE_URL}/api/automation/notifications",
              headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    ids = [n["id"] for n in r.json()["notifications"]]
    assert seeded_notif["id"] in ids


def test_mark_notif_read(s, elite_token, seeded_notif):
    token, _ = elite_token
    r = s.post(f"{BASE_URL}/api/automation/notifications/{seeded_notif['id']}/read",
               headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    assert r.json().get("ok") is True
    # verify persisted
    r2 = s.get(f"{BASE_URL}/api/automation/notifications",
               headers={"Authorization": f"Bearer {token}"})
    n = next((x for x in r2.json()["notifications"] if x["id"] == seeded_notif["id"]), None)
    assert n is not None and n["read"] is True
