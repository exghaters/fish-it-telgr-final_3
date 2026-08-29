"""Iteration 12 tests: httpOnly cookie auth + admin delete user."""
import os
import uuid

import pytest
import requests
from dotenv import load_dotenv

load_dotenv("/app/frontend/.env")
BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")

ELITE_EMAIL = "user@fishit.app"
ELITE_PASS = "FishIt#2026"
ADMIN_EMAIL = "admin@fishit.app"
ADMIN_PASS = "Admin@Fishit2026"


# ---------- Cookie-based auth ----------

def test_login_sets_httponly_cookie_and_returns_token():
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login",
               json={"email": ELITE_EMAIL, "password": ELITE_PASS})
    assert r.status_code == 200, r.text
    body = r.json()
    assert "access_token" in body and body["user"]["email"] == ELITE_EMAIL
    # cookie set on session
    assert "access_token" in s.cookies.get_dict(), s.cookies.get_dict()
    # httpOnly + Secure attributes present in Set-Cookie
    set_cookie = r.headers.get("set-cookie", "")
    assert "httponly" in set_cookie.lower()
    assert "secure" in set_cookie.lower()


def test_me_works_with_cookie_only_no_header():
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login",
               json={"email": ELITE_EMAIL, "password": ELITE_PASS})
    assert r.status_code == 200
    # No Authorization header, rely only on cookie jar
    r2 = s.get(f"{BASE_URL}/api/auth/me")
    assert r2.status_code == 200
    assert r2.json()["email"] == ELITE_EMAIL


def test_me_no_cookie_no_header_returns_401():
    r = requests.get(f"{BASE_URL}/api/auth/me")
    assert r.status_code == 401


def test_logout_clears_cookie_and_me_returns_401():
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login",
               json={"email": ELITE_EMAIL, "password": ELITE_PASS})
    assert r.status_code == 200
    r2 = s.post(f"{BASE_URL}/api/auth/logout")
    assert r2.status_code == 200 and r2.json().get("ok") is True
    # Session cookie should now be cleared; /me must fail
    r3 = s.get(f"{BASE_URL}/api/auth/me")
    assert r3.status_code == 401


def test_header_bearer_still_works_as_fallback():
    r = requests.post(f"{BASE_URL}/api/auth/login",
                      json={"email": ELITE_EMAIL, "password": ELITE_PASS})
    assert r.status_code == 200
    token = r.json()["access_token"]
    r2 = requests.get(f"{BASE_URL}/api/auth/me",
                      headers={"Authorization": f"Bearer {token}"})
    assert r2.status_code == 200


# ---------- Admin delete-user ----------

@pytest.fixture
def admin_session():
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login",
               json={"email": ADMIN_EMAIL, "password": ADMIN_PASS})
    assert r.status_code == 200, r.text
    return s, r.json()["user"]["id"]


def test_admin_delete_throwaway_user(admin_session):
    admin_s, _ = admin_session
    # create throwaway user via register
    email = f"deltest_api_{uuid.uuid4().hex[:8]}@fishit.app"
    reg = requests.post(f"{BASE_URL}/api/auth/register",
                        json={"email": email, "password": "TempPass#123"})
    assert reg.status_code == 200, reg.text
    uid = reg.json()["user"]["id"]

    d = admin_s.delete(f"{BASE_URL}/api/admin/users/{uid}")
    assert d.status_code == 200, d.text
    assert d.json().get("ok") is True
    assert d.json().get("deleted") == email

    # verify gone: list users
    lst = admin_s.get(f"{BASE_URL}/api/admin/users")
    assert lst.status_code == 200
    emails = [u["email"] for u in lst.json()]
    assert email not in emails
    # seeded elite must still exist
    assert ELITE_EMAIL in emails
    assert ADMIN_EMAIL in emails


def test_admin_cannot_delete_self(admin_session):
    admin_s, admin_id = admin_session
    d = admin_s.delete(f"{BASE_URL}/api/admin/users/{admin_id}")
    assert d.status_code == 400


def test_admin_delete_nonexistent_returns_404(admin_session):
    admin_s, _ = admin_session
    d = admin_s.delete(f"{BASE_URL}/api/admin/users/nonexistent-uuid-xyz")
    assert d.status_code == 404


def test_non_admin_cannot_delete_user():
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login",
               json={"email": ELITE_EMAIL, "password": ELITE_PASS})
    assert r.status_code == 200
    d = s.delete(f"{BASE_URL}/api/admin/users/whatever")
    assert d.status_code == 403
