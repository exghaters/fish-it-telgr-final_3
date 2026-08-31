"""iter15 targeted tests:
- new AutomationConfig fields (pendaftaran_cancelled_pattern, registration_success_pattern) default + PUT/GET round-trip
- multi-account /api/telegram/status per-account isolation & rehydrate path (no 500)
"""
import os
import uuid
import requests
import pytest


def _read_frontend_env():
    d = {}
    try:
        with open("/app/frontend/.env") as f:
            for line in f:
                if "=" in line and not line.strip().startswith("#"):
                    k, v = line.strip().split("=", 1)
                    d[k] = v
    except Exception:
        pass
    return d


BASE_URL = (os.environ.get("REACT_APP_BACKEND_URL")
            or _read_frontend_env().get("REACT_APP_BACKEND_URL", "")).rstrip("/")
assert BASE_URL, "REACT_APP_BACKEND_URL missing"
ADMIN_EMAIL = "admin@fishit.app"
ADMIN_PASSWORD = "Surabaya818"


@pytest.fixture(scope="module")
def admin_session():
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login",
               json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    assert r.status_code == 200, f"admin login failed: {r.status_code} {r.text}"
    return s


class TestConfigNewFields:
    def test_get_config_has_new_fields_and_defaults(self, admin_session):
        r = admin_session.get(f"{BASE_URL}/api/automation/config")
        assert r.status_code == 200, r.text
        data = r.json()
        assert "pendaftaran_cancelled_pattern" in data
        assert "registration_success_pattern" in data
        # defaults must include the substrings the engine relies on
        cancelled = data["pendaftaran_cancelled_pattern"] or ""
        success = data["registration_success_pattern"] or ""
        assert "DIBATALKAN" in cancelled or "dibatalkan" in cancelled.lower()
        assert "peserta" in cancelled.lower()
        assert "terdaftar" in success.lower()

    def test_put_config_roundtrip_new_fields(self, admin_session):
        # Get current
        cur = admin_session.get(f"{BASE_URL}/api/automation/config").json()
        marker = uuid.uuid4().hex[:8]
        new_cancelled = cur.get("pendaftaran_cancelled_pattern", "") + f"|MARKER_{marker}"
        new_success = cur.get("registration_success_pattern", "") + f"|OK_{marker}"
        payload = dict(cur)
        payload["pendaftaran_cancelled_pattern"] = new_cancelled
        payload["registration_success_pattern"] = new_success
        r = admin_session.put(f"{BASE_URL}/api/automation/config", json=payload)
        assert r.status_code == 200, r.text
        # GET again and verify persisted
        r2 = admin_session.get(f"{BASE_URL}/api/automation/config")
        assert r2.status_code == 200
        got = r2.json()
        assert f"MARKER_{marker}" in got["pendaftaran_cancelled_pattern"]
        assert f"OK_{marker}" in got["registration_success_pattern"]
        # restore
        restore = dict(got)
        restore["pendaftaran_cancelled_pattern"] = cur.get("pendaftaran_cancelled_pattern", "")
        restore["registration_success_pattern"] = cur.get("registration_success_pattern", "")
        admin_session.put(f"{BASE_URL}/api/automation/config", json=restore)


class TestMultiAccountStatus:
    def test_status_per_account_isolation(self, admin_session):
        # List existing accounts
        r = admin_session.get(f"{BASE_URL}/api/telegram/accounts")
        assert r.status_code == 200, r.text
        data = r.json()
        accounts = data.get("accounts") if isinstance(data, dict) else data
        assert isinstance(accounts, list) and len(accounts) >= 1, "need >=1 pre-existing account"

        # Create a 2nd throwaway account
        created = admin_session.post(f"{BASE_URL}/api/telegram/accounts",
                                     json={"label": "TEST_Iter15_Customer"})
        assert created.status_code in (200, 201), created.text
        new_acc = created.json()
        new_id = new_acc.get("id") or new_acc.get("_id")
        assert new_id, f"missing id in {new_acc}"

        try:
            existing_id = accounts[0]["id"]
            # Call status for account A
            ra = admin_session.get(f"{BASE_URL}/api/telegram/status",
                                    headers={"X-Account-Id": existing_id})
            assert ra.status_code == 200, ra.text
            da = ra.json()
            assert "connected" in da
            # Call status for account B (new one, no session)
            rb = admin_session.get(f"{BASE_URL}/api/telegram/status",
                                    headers={"X-Account-Id": new_id})
            assert rb.status_code == 200, rb.text
            db = rb.json()
            assert "connected" in db
            # New account without a session must gracefully be connected=false
            assert db["connected"] is False

            # Switch back and forth - no 500, results consistent
            ra2 = admin_session.get(f"{BASE_URL}/api/telegram/status",
                                     headers={"X-Account-Id": existing_id})
            assert ra2.status_code == 200
            assert ra2.json().get("connected") == da.get("connected")

            rb2 = admin_session.get(f"{BASE_URL}/api/telegram/status",
                                     headers={"X-Account-Id": new_id})
            assert rb2.status_code == 200
            assert rb2.json().get("connected") is False
        finally:
            # Clean up: delete only the throwaway account we created
            d = admin_session.delete(f"{BASE_URL}/api/telegram/accounts/{new_id}")
            assert d.status_code in (200, 204), d.text
