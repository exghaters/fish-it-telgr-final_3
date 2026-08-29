"""Iteration 8: multi-account isolation, plan limits, log retention."""
import os

import pytest
import requests
from dotenv import dotenv_values

frontend_env = dotenv_values("/app/frontend/.env")
base_url = os.environ.get("REACT_APP_BACKEND_URL") or frontend_env.get("REACT_APP_BACKEND_URL")
if not base_url:
    raise RuntimeError("REACT_APP_BACKEND_URL missing")
BASE_URL = base_url.rstrip("/")
API = f"{BASE_URL}/api"

ADMIN = {"email": "admin@fishit.app", "password": dotenv_values("/app/backend/.env").get("ADMIN_PASSWORD")}
USER = {"email": "user@fishit.app", "password": "FishIt#2026"}


def login(creds):
    r = requests.post(f"{API}/auth/login", json=creds, timeout=30)
    if r.status_code != 200:
        pytest.fail(f"login failed {r.status_code}: {r.text[:300]}")
    tok = r.cookies.get("access_token")
    assert tok, "no auth cookie set on login"
    return tok


@pytest.fixture(scope="module")
def admin_token():
    return login(ADMIN)


@pytest.fixture(scope="module")
def user_token():
    return login(USER)


def H(token, account_id=None):
    h = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    if account_id:
        h["X-Account-Id"] = account_id
    return h


@pytest.fixture(scope="module")
def cleanup(user_token):
    created = []
    yield created
    for aid in created:
        requests.delete(f"{API}/telegram/accounts/{aid}", headers=H(user_token), timeout=30)


# --- Accounts listing / default creation ---
class TestAccountsList:
    def test_list_autocreates_default_and_plan_meta(self, admin_token):
        r = requests.get(f"{API}/telegram/accounts", headers=H(admin_token), timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["limit"] == 3
        assert d["plan"] == "elite"
        assert d["plan_label"] == "Elite"
        assert len(d["accounts"]) >= 1
        acc = d["accounts"][0]
        assert "id" in acc and "label" in acc
        assert "_id" not in acc
        assert isinstance(acc["connected"], bool)

    def test_requires_auth(self):
        r = requests.get(f"{API}/telegram/accounts", timeout=30)
        assert r.status_code == 401


# --- Plan limit enforcement + delete ---
class TestPlanLimit:
    def test_create_up_to_limit_then_403(self, user_token, cleanup):
        r = requests.get(f"{API}/telegram/accounts", headers=H(user_token), timeout=30)
        existing = r.json()["accounts"]
        limit = r.json()["limit"]
        assert limit == 3
        while len(existing) < limit:
            c = requests.post(f"{API}/telegram/accounts", headers=H(user_token),
                              json={"label": f"TEST_acct{len(existing)+1}"}, timeout=30)
            assert c.status_code == 200, c.text
            body = c.json()
            assert "id" in body
            cleanup.append(body["id"])
            existing = requests.get(f"{API}/telegram/accounts",
                                    headers=H(user_token), timeout=30).json()["accounts"]
        assert len(existing) == 3
        over = requests.post(f"{API}/telegram/accounts", headers=H(user_token),
                             json={"label": "TEST_overlimit"}, timeout=30)
        assert over.status_code == 403, over.text
        assert "Elite" in over.json()["detail"] or "akun" in over.json()["detail"].lower()

    def test_delete_account_and_verify_removal(self, user_token):
        c = requests.post(f"{API}/telegram/accounts", headers=H(user_token),
                          json={"label": "TEST_tmp"}, timeout=30)
        if c.status_code == 403:
            # at limit: delete one TEST_ account first then re-create
            accs = requests.get(f"{API}/telegram/accounts",
                                headers=H(user_token), timeout=30).json()["accounts"]
            victim = [a for a in accs if a["label"].startswith("TEST_")][0]
            d = requests.delete(f"{API}/telegram/accounts/{victim['id']}",
                                headers=H(user_token), timeout=30)
            assert d.status_code == 200, d.text
            after = requests.get(f"{API}/telegram/accounts",
                                 headers=H(user_token), timeout=30).json()["accounts"]
            assert victim["id"] not in [a["id"] for a in after]
            c = requests.post(f"{API}/telegram/accounts", headers=H(user_token),
                              json={"label": "TEST_tmp"}, timeout=30)
        assert c.status_code == 200, c.text
        aid = c.json()["id"]
        d = requests.delete(f"{API}/telegram/accounts/{aid}", headers=H(user_token), timeout=30)
        assert d.status_code == 200, d.text
        after = requests.get(f"{API}/telegram/accounts",
                             headers=H(user_token), timeout=30).json()["accounts"]
        assert aid not in [a["id"] for a in after]

    def test_delete_unknown_returns_404(self, user_token):
        d = requests.delete(f"{API}/telegram/accounts/does-not-exist",
                            headers=H(user_token), timeout=30)
        assert d.status_code == 404

    def test_cannot_delete_last_account(self, admin_token):
        accs = requests.get(f"{API}/telegram/accounts",
                            headers=H(admin_token), timeout=30).json()["accounts"]
        if len(accs) != 1:
            pytest.skip("admin has more than one account; last-account rule tested elsewhere")
        d = requests.delete(f"{API}/telegram/accounts/{accs[0]['id']}",
                            headers=H(admin_token), timeout=30)
        assert d.status_code == 400
        assert "1 akun" in d.json()["detail"]


# --- Isolation between accounts ---
class TestIsolation:
    @pytest.fixture(scope="class")
    def two_accounts(self, user_token):
        accs = requests.get(f"{API}/telegram/accounts",
                            headers=H(user_token), timeout=30).json()["accounts"]
        created = []
        while len(accs) < 2:
            c = requests.post(f"{API}/telegram/accounts", headers=H(user_token),
                              json={"label": "TEST_iso"}, timeout=30)
            assert c.status_code == 200, c.text
            created.append(c.json()["id"])
            accs = requests.get(f"{API}/telegram/accounts",
                                headers=H(user_token), timeout=30).json()["accounts"]
        yield accs[0]["id"], accs[1]["id"]
        for aid in created:
            requests.delete(f"{API}/telegram/accounts/{aid}",
                            headers=H(user_token), timeout=30)

    def test_config_isolated_per_account(self, user_token, two_accounts):
        a, b = two_accounts
        cfg_a = requests.get(f"{API}/automation/config", headers=H(user_token, a), timeout=30)
        assert cfg_a.status_code == 200, cfg_a.text
        cfg = cfg_a.json()
        cfg["bot_username"] = "@TEST_bot_account_A"
        p = requests.put(f"{API}/automation/config", headers=H(user_token, a),
                         json=cfg, timeout=30)
        assert p.status_code == 200, p.text
        # persisted for A
        again = requests.get(f"{API}/automation/config",
                             headers=H(user_token, a), timeout=30).json()
        assert again["bot_username"] == "@TEST_bot_account_A"
        assert again["user_id"].endswith(a)
        # not visible for B
        cfg_b = requests.get(f"{API}/automation/config",
                             headers=H(user_token, b), timeout=30).json()
        assert cfg_b["bot_username"] != "@TEST_bot_account_A"
        assert cfg_b["user_id"].endswith(b)

    def test_status_isolated_per_account(self, user_token, two_accounts):
        a, b = two_accounts
        sa = requests.get(f"{API}/automation/status", headers=H(user_token, a), timeout=30)
        sb = requests.get(f"{API}/automation/status", headers=H(user_token, b), timeout=30)
        assert sa.status_code == 200 and sb.status_code == 200
        assert "_id" not in sa.json()
        assert sa.json()["user_id"].endswith(a)
        assert sb.json()["user_id"].endswith(b)

    def test_events_isolated_per_account(self, user_token, two_accounts):
        a, b = two_accounts
        ea = requests.get(f"{API}/automation/events", headers=H(user_token, a), timeout=30)
        eb = requests.get(f"{API}/automation/events", headers=H(user_token, b), timeout=30)
        assert ea.status_code == 200 and eb.status_code == 200
        ids_a = {e["id"] for e in ea.json()["events"] if "id" in e}
        ids_b = {e["id"] for e in eb.json()["events"] if "id" in e}
        assert not (ids_a & ids_b)

    def test_unknown_account_id_falls_back_to_default(self, user_token, two_accounts):
        r = requests.get(f"{API}/automation/config",
                         headers=H(user_token, "bogus-account-id"), timeout=30)
        assert r.status_code == 200
        default_id = requests.get(f"{API}/telegram/accounts",
                                  headers=H(user_token), timeout=30).json()["accounts"][0]["id"]
        assert r.json()["user_id"].endswith(default_id)

    def test_cross_user_account_id_rejected(self, user_token, admin_token, two_accounts):
        """User A's account id must not scope admin's data."""
        a, _ = two_accounts
        r = requests.get(f"{API}/automation/config", headers=H(admin_token, a), timeout=30)
        assert r.status_code == 200
        assert not r.json()["user_id"].endswith(a), "cross-user account scoping leak"


# --- Log retention by plan ---
class TestLogRetention:
    def test_elite_log_days_90(self, admin_token):
        r = requests.get(f"{API}/automation/events", headers=H(admin_token), timeout=30)
        assert r.status_code == 200, r.text
        assert r.json()["log_days"] == 90

    def test_log_days_follows_plan_change(self, admin_token):
        """Temporarily set user@fishit.app to pro then free, verify log_days, revert."""
        users = requests.get(f"{API}/admin/users", headers=H(admin_token), timeout=30)
        assert users.status_code == 200, users.text
        payload = users.json()
        items = payload if isinstance(payload, list) else payload.get("users", [])
        target = next((u for u in items if u["email"] == USER["email"]), None)
        assert target, "seeded user not found"
        try:
            for plan, expected in (("pro", 30), ("free", 7), ("elite", 90)):
                up = requests.put(f"{API}/admin/users/{target['id']}",
                                  headers=H(admin_token), json={"plan": plan}, timeout=30)
                assert up.status_code == 200, up.text
                tok = login(USER)
                ev = requests.get(f"{API}/automation/events", headers=H(tok), timeout=30)
                assert ev.status_code == 200, ev.text
                assert ev.json()["log_days"] == expected, f"plan {plan}"
                acc = requests.get(f"{API}/telegram/accounts", headers=H(tok), timeout=30).json()
                assert acc["limit"] == (3 if plan == "elite" else 1)
        finally:
            requests.put(f"{API}/admin/users/{target['id']}",
                         headers=H(admin_token), json={"plan": "elite"}, timeout=30)
