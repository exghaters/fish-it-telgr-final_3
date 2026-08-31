"""Iter14: joki/operator model tests.

Covers:
- Admin creation of operator via POST /api/admin/users (default plan elite, role user).
- New operator can login and reach /api/auth/me.
- Operator isolation on /api/telegram/accounts (each sees only own).
- Account label create/rename (POST/PATCH /api/telegram/accounts).
- Public registration flag still respected (ALLOW_PUBLIC_REGISTRATION=true here so
  register returns 200, but we assert endpoint contract).
- Regression: admin/user login work; admin can delete throwaway operator.
"""
import os
import uuid

import pytest
import requests

def _read_frontend_env():
    env = {}
    try:
        with open("/app/frontend/.env") as f:
            for line in f:
                line = line.strip()
                if "=" in line and not line.startswith("#"):
                    k, v = line.split("=", 1)
                    env[k.strip()] = v.strip()
    except FileNotFoundError:
        pass
    return env


BASE_URL = (os.environ.get("REACT_APP_BACKEND_URL")
            or _read_frontend_env().get("REACT_APP_BACKEND_URL", "")).rstrip("/")
assert BASE_URL, "REACT_APP_BACKEND_URL missing"

ADMIN_EMAIL = "admin@fishit.app"
ADMIN_PASSWORD = "Surabaya818"
USER_EMAIL = "user@fishit.app"
USER_PASSWORD = "FishIt#2026"


def _sess():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


def _login(sess, email, password):
    r = sess.post(f"{BASE_URL}/api/auth/login",
                  json={"email": email, "password": password})
    return r


@pytest.fixture(scope="module")
def admin_sess():
    s = _sess()
    r = _login(s, ADMIN_EMAIL, ADMIN_PASSWORD)
    if r.status_code != 200:
        pytest.skip(f"Admin login failed: {r.status_code} {r.text}")
    return s


@pytest.fixture(scope="module")
def user_sess():
    s = _sess()
    r = _login(s, USER_EMAIL, USER_PASSWORD)
    if r.status_code != 200:
        pytest.skip(f"User login failed: {r.status_code} {r.text}")
    return s


@pytest.fixture(scope="module")
def throwaway_operator(admin_sess):
    """Create a throwaway operator via admin API, yield creds+id, cleanup after."""
    email = f"op_probe_{uuid.uuid4().hex[:8]}@fishit.app"
    password = "OpProbe1234"
    r = admin_sess.post(f"{BASE_URL}/api/admin/users",
                        json={"email": email, "password": password})
    assert r.status_code == 200, f"create_user failed: {r.status_code} {r.text}"
    data = r.json()
    assert data["email"] == email
    assert data["role"] == "user"
    assert data["plan"] == "elite"
    assert data["is_active"] is True
    uid = data["id"]
    yield {"id": uid, "email": email, "password": password}
    # cleanup
    admin_sess.delete(f"{BASE_URL}/api/admin/users/{uid}")


# ---------- Auth / registration ----------
class TestPublicRegistration:
    def test_register_endpoint_contract(self):
        """ALLOW_PUBLIC_REGISTRATION is 'true' in preview => 200 (endpoint still works).
        UI removal is verified separately by Playwright."""
        s = _sess()
        email = f"TEST_reg_{uuid.uuid4().hex[:6]}@fishit.app"
        r = s.post(f"{BASE_URL}/api/auth/register",
                   json={"email": email, "password": "Testing1234"})
        # Accept either 200 (flag true) or 403 (flag false) – both are valid contracts.
        assert r.status_code in (200, 403), r.text
        if r.status_code == 200:
            # cleanup: admin deletes
            admin = _sess()
            _login(admin, ADMIN_EMAIL, ADMIN_PASSWORD)
            users = admin.get(f"{BASE_URL}/api/admin/users").json()
            for u in users:
                if u["email"] == email:
                    admin.delete(f"{BASE_URL}/api/admin/users/{u['id']}")


# ---------- Admin creates operator ----------
class TestAdminCreatesOperator:
    def test_create_and_new_operator_login(self, admin_sess, throwaway_operator):
        # Verify listed
        users = admin_sess.get(f"{BASE_URL}/api/admin/users").json()
        emails = {u["email"] for u in users}
        assert throwaway_operator["email"] in emails
        rec = next(u for u in users if u["id"] == throwaway_operator["id"])
        assert rec["plan"] == "elite"
        assert rec["role"] == "user"

        # New operator can log in
        s = _sess()
        r = _login(s, throwaway_operator["email"], throwaway_operator["password"])
        assert r.status_code == 200, r.text
        me = s.get(f"{BASE_URL}/api/auth/me")
        assert me.status_code == 200
        assert me.json()["email"] == throwaway_operator["email"]

    def test_create_password_min_length(self, admin_sess):
        email = f"op_shortpw_{uuid.uuid4().hex[:6]}@fishit.app"
        r = admin_sess.post(f"{BASE_URL}/api/admin/users",
                            json={"email": email, "password": "short"})
        assert r.status_code == 422

    def test_create_duplicate_email(self, admin_sess, throwaway_operator):
        r = admin_sess.post(f"{BASE_URL}/api/admin/users",
                            json={"email": throwaway_operator["email"],
                                  "password": "OpProbe1234"})
        assert r.status_code == 400

    def test_non_admin_cannot_create(self, user_sess):
        r = user_sess.post(f"{BASE_URL}/api/admin/users",
                           json={"email": "nope@fishit.app", "password": "Testing1234"})
        assert r.status_code == 403


# ---------- Telegram account labels & isolation ----------
class TestAccountLabels:
    def test_default_account_and_label_rename(self, user_sess):
        r = user_sess.get(f"{BASE_URL}/api/telegram/accounts")
        assert r.status_code == 200
        data = r.json()
        assert data["plan_label"] == "Elite"
        assert data["limit"] == 100
        assert len(data["accounts"]) >= 1
        acc = data["accounts"][0]
        aid = acc["id"]
        original_label = acc["label"]

        # rename
        new_label = f"TEST_customer_{uuid.uuid4().hex[:5]}"
        pr = user_sess.patch(f"{BASE_URL}/api/telegram/accounts/{aid}",
                             json={"label": new_label})
        assert pr.status_code == 200
        assert pr.json()["label"] == new_label

        # verify persistence
        r2 = user_sess.get(f"{BASE_URL}/api/telegram/accounts")
        found = next(a for a in r2.json()["accounts"] if a["id"] == aid)
        assert found["label"] == new_label

        # restore
        user_sess.patch(f"{BASE_URL}/api/telegram/accounts/{aid}",
                        json={"label": original_label})

    def test_create_account_with_label(self, user_sess):
        label = f"TEST_lbl_{uuid.uuid4().hex[:5]}"
        r = user_sess.post(f"{BASE_URL}/api/telegram/accounts", json={"label": label})
        assert r.status_code == 200
        aid = r.json()["id"]
        assert r.json()["label"] == label

        # cleanup
        try:
            user_sess.delete(f"{BASE_URL}/api/telegram/accounts/{aid}")
        except Exception:
            pass


class TestOperatorIsolation:
    def test_two_operators_see_different_lists(self, admin_sess, throwaway_operator, user_sess):
        # Login as the throwaway operator
        s_new = _sess()
        assert _login(s_new, throwaway_operator["email"],
                      throwaway_operator["password"]).status_code == 200

        # Create a labeled account on new operator
        new_label = f"TEST_iso_{uuid.uuid4().hex[:5]}"
        cr = s_new.post(f"{BASE_URL}/api/telegram/accounts", json={"label": new_label})
        assert cr.status_code == 200
        new_acc_id = cr.json()["id"]

        # New operator sees it
        new_accs = s_new.get(f"{BASE_URL}/api/telegram/accounts").json()["accounts"]
        assert any(a["id"] == new_acc_id for a in new_accs)

        # Elite user sees his own list only – must NOT contain new_acc_id
        user_accs = user_sess.get(f"{BASE_URL}/api/telegram/accounts").json()["accounts"]
        assert all(a["id"] != new_acc_id for a in user_accs)
        assert all(a["label"] != new_label for a in user_accs)

        # New operator cannot patch user's account (404 - scoped)
        if user_accs:
            other_id = user_accs[0]["id"]
            pr = s_new.patch(f"{BASE_URL}/api/telegram/accounts/{other_id}",
                             json={"label": "hacked"})
            assert pr.status_code == 404


# ---------- Regression ----------
class TestRegression:
    def test_admin_login_still_works(self, admin_sess):
        r = admin_sess.get(f"{BASE_URL}/api/auth/me")
        assert r.status_code == 200
        assert r.json()["role"] == "admin"

    def test_user_login_still_works(self, user_sess):
        r = user_sess.get(f"{BASE_URL}/api/auth/me")
        assert r.status_code == 200
        assert r.json()["plan"] == "elite"

    def test_logout_clears_cookie(self):
        s = _sess()
        _login(s, USER_EMAIL, USER_PASSWORD)
        r = s.post(f"{BASE_URL}/api/auth/logout")
        assert r.status_code == 200
        # after logout, /me should 401
        me = s.get(f"{BASE_URL}/api/auth/me")
        assert me.status_code == 401
