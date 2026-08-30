"""Iter16: admin deactivation guards + admin can still deactivate non-admin users."""
import os
import uuid
import requests
import pytest
from pathlib import Path


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

ADMIN_EMAIL = "admin@fishit.app"
ADMIN_PW = "Lpwa*PN7uCy5%wWRK@r9l%Q#"


def _login(session: requests.Session, email: str, pw: str):
    r = session.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": pw})
    return r


@pytest.fixture(scope="module")
def admin_session():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    r = _login(s, ADMIN_EMAIL, ADMIN_PW)
    assert r.status_code == 200, f"admin login failed: {r.status_code} {r.text}"
    data = r.json()
    assert data["user"]["is_active"] is True
    assert data["user"]["role"] == "admin"
    s.admin_id = data["user"]["id"]  # type: ignore[attr-defined]
    return s


def test_admin_login_works(admin_session):
    assert admin_session.admin_id  # type: ignore[attr-defined]


def test_admin_cannot_deactivate_self(admin_session):
    admin_id = admin_session.admin_id  # type: ignore[attr-defined]
    r = admin_session.put(f"{BASE_URL}/api/admin/users/{admin_id}", json={"is_active": False})
    assert r.status_code == 400, f"expected 400 got {r.status_code}: {r.text}"
    body = r.json()
    msg = (body.get("detail") or body.get("message") or "").lower()
    assert "sendiri" in msg or "own" in msg or "self" in msg, f"unexpected msg: {body}"

    # verify admin still active + can login
    fresh = requests.Session()
    fresh.headers.update({"Content-Type": "application/json"})
    r2 = _login(fresh, ADMIN_EMAIL, ADMIN_PW)
    assert r2.status_code == 200
    assert r2.json()["user"]["is_active"] is True


def test_admin_cannot_deactivate_last_active_admin(admin_session):
    """Since admin@fishit.app is the only admin, deactivating any admin id
    (here self-id) must be blocked. Self-guard fires first (400)."""
    admin_id = admin_session.admin_id  # type: ignore[attr-defined]
    r = admin_session.put(f"{BASE_URL}/api/admin/users/{admin_id}", json={"is_active": False})
    assert r.status_code == 400


def test_admin_can_deactivate_and_reactivate_non_admin_user(admin_session):
    # Create throwaway user
    email = f"deact_probe_{uuid.uuid4().hex[:8]}@fishit.app"
    pw = "DeactProbe12"
    created = admin_session.post(f"{BASE_URL}/api/admin/users",
                                 json={"email": email, "password": pw, "role": "user"})
    assert created.status_code == 200, created.text
    uid = created.json()["id"]
    try:
        # Confirm login works first
        s1 = requests.Session()
        s1.headers.update({"Content-Type": "application/json"})
        r_ok = _login(s1, email, pw)
        assert r_ok.status_code == 200, r_ok.text

        # Deactivate
        r_d = admin_session.put(f"{BASE_URL}/api/admin/users/{uid}", json={"is_active": False})
        assert r_d.status_code == 200, r_d.text
        assert r_d.json()["is_active"] is False

        # Login now rejected with 403 (dinonaktifkan)
        s2 = requests.Session()
        s2.headers.update({"Content-Type": "application/json"})
        r_rej = _login(s2, email, pw)
        assert r_rej.status_code == 403, f"expected 403 got {r_rej.status_code}: {r_rej.text}"
        assert "dinonaktifkan" in r_rej.text.lower() or "deactiv" in r_rej.text.lower()

        # Re-activate
        r_a = admin_session.put(f"{BASE_URL}/api/admin/users/{uid}", json={"is_active": True})
        assert r_a.status_code == 200
        assert r_a.json()["is_active"] is True

        # Login works again
        s3 = requests.Session()
        s3.headers.update({"Content-Type": "application/json"})
        r_ok2 = _login(s3, email, pw)
        assert r_ok2.status_code == 200
    finally:
        admin_session.delete(f"{BASE_URL}/api/admin/users/{uid}")
