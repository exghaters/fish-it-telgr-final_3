"""iter17: DELETE /api/telegram/accounts/{id} — deletes a non-last account,
blocks deleting the last one, and removes any telegram_sessions doc for that akey.
"""
import os
import uuid
import requests
import pytest
from pathlib import Path
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

load_dotenv("/app/backend/.env")


def _read_frontend_env():
    env = {}
    p = Path("/app/frontend/.env")
    if p.exists():
        for line in p.read_text().splitlines():
            if "=" in line and not line.strip().startswith("#"):
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip()
    return env


BASE_URL = (os.environ.get("REACT_APP_BACKEND_URL")
            or _read_frontend_env().get("REACT_APP_BACKEND_URL", "")).rstrip("/")
assert BASE_URL, "REACT_APP_BACKEND_URL missing"
API = f"{BASE_URL}/api"

ELITE_EMAIL = "user@fishit.app"
ELITE_PW = "FishIt#2026"


@pytest.fixture(scope="module")
def elite_client():
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": ELITE_EMAIL, "password": ELITE_PW})
    assert r.status_code == 200, r.text
    return s


def _list_accounts(client):
    r = client.get(f"{API}/telegram/accounts")
    assert r.status_code == 200, r.text
    return r.json()["accounts"]


def _create_account(client, label):
    r = client.post(f"{API}/telegram/accounts", json={"label": label})
    assert r.status_code == 200, r.text
    return r.json()


def test_delete_non_last_account_ok(elite_client):
    label = f"TEST_del_{uuid.uuid4().hex[:6]}"
    acc = _create_account(elite_client, label)
    aid = acc["id"]
    accts = _list_accounts(elite_client)
    assert any(a["id"] == aid for a in accts)
    assert len(accts) >= 2

    r = elite_client.delete(f"{API}/telegram/accounts/{aid}")
    assert r.status_code == 200, r.text
    assert r.json().get("ok") is True

    accts_after = _list_accounts(elite_client)
    assert not any(a["id"] == aid for a in accts_after)


def test_cannot_delete_last_account(elite_client):
    # Make sure we have only 1 by iteratively deleting any TEST_ extras first
    accts = _list_accounts(elite_client)
    for a in accts:
        if len(accts) <= 1:
            break
        if a["label"].startswith("TEST_"):
            elite_client.delete(f"{API}/telegram/accounts/{a['id']}")
            accts = _list_accounts(elite_client)
    accts = _list_accounts(elite_client)
    # If still >1, delete non-active TEST_ or skip
    if len(accts) > 1:
        # Delete extras that are NOT the first ("Rick"/main) — safe if labeled TEST_
        for a in accts[1:]:
            if a["label"].startswith("TEST_"):
                elite_client.delete(f"{API}/telegram/accounts/{a['id']}")
    accts = _list_accounts(elite_client)
    if len(accts) != 1:
        pytest.skip(f"Cannot reach single-account state safely (have {len(accts)}); skipping last-delete test to avoid touching prod-like accounts")
    last_id = accts[0]["id"]
    r = elite_client.delete(f"{API}/telegram/accounts/{last_id}")
    assert r.status_code == 400
    assert "Minimal harus ada 1 akun" in r.text
    # still present
    assert any(a["id"] == last_id for a in _list_accounts(elite_client))


def test_delete_removes_telegram_sessions_doc(elite_client):
    from pymongo import MongoClient
    mongo_url = os.environ["MONGO_URL"]
    db_name = os.environ["DB_NAME"]
    mc = MongoClient(mongo_url)
    db = mc[db_name]

    # get user id
    me = elite_client.get(f"{API}/auth/me").json()
    uid = me["id"]

    label = f"TEST_sess_{uuid.uuid4().hex[:6]}"
    acc = _create_account(elite_client, label)
    aid = acc["id"]
    akey = f"{uid}:{aid}"

    db.telegram_sessions.update_one(
        {"user_id": akey},
        {"$set": {"user_id": akey, "api_id": 12345, "api_hash_enc": "fake"}},
        upsert=True,
    )
    assert db.telegram_sessions.find_one({"user_id": akey}) is not None

    r = elite_client.delete(f"{API}/telegram/accounts/{aid}")
    assert r.status_code == 200

    doc = db.telegram_sessions.find_one({"user_id": akey})
    assert doc is None, "telegram_sessions doc should be removed after delete"
    mc.close()
