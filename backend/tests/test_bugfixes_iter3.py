"""Iteration 3: Verify algorithm rewrite for /mancing spam, extract confirmation,
sell rejection retry, and WebView-based auto-verification.

Focus: plumbing/introspection — cannot exercise real Telegram flow.
"""
from __future__ import annotations

import inspect
import os
import sys

import pytest
import requests

sys.path.insert(0, "/app/backend")

from dotenv import dotenv_values as _dv  # test-env resolution
_fe = _dv("/app/frontend/.env")
_bu = os.environ.get("REACT_APP_BACKEND_URL") or _fe.get("REACT_APP_BACKEND_URL")
if not _bu:
    raise RuntimeError("REACT_APP_BACKEND_URL missing from env and /app/frontend/.env")
BASE_URL = _bu.rstrip("/")


# --- Import check ---
def test_request_webview_import():
    """RequestWebViewRequest must be importable & referenced in automation_engine."""
    from telethon.tl.functions.messages import RequestWebViewRequest  # noqa
    import automation_engine as ae
    src = inspect.getsource(ae)
    assert "RequestWebViewRequest" in src


# --- AutomationRunner new attributes ---
class TestRunnerAttributes:
    def test_init_has_new_attributes(self):
        from automation_engine import AutomationRunner
        src = inspect.getsource(AutomationRunner.__init__)
        assert "_last_mancing_at" in src
        assert "_session_active" in src
        assert "None" in src  # _last_mancing_at initialized to None

    def test_has_session_likely_running_method(self):
        from automation_engine import AutomationRunner
        assert hasattr(AutomationRunner, "_session_likely_running")
        m = getattr(AutomationRunner, "_session_likely_running")
        assert callable(m)
        # Signature: takes cfg -> bool
        sig = inspect.signature(m)
        params = list(sig.parameters)
        assert "cfg" in params

    def test_has_process_session_result_method(self):
        from automation_engine import AutomationRunner
        assert hasattr(AutomationRunner, "_process_session_result")
        sig = inspect.signature(AutomationRunner._process_session_result)
        params = list(sig.parameters)
        assert "chat" in params and "cfg" in params and "result_msg" in params

    def test_do_sell_signature_has_mancing_retry(self):
        from automation_engine import AutomationRunner
        sig = inspect.signature(AutomationRunner._do_sell)
        params = sig.parameters
        assert "mancing_retry" in params, f"params={list(params)}"
        assert params["mancing_retry"].default == 0
        assert "retry_after_favorite" in params

    def test_handle_verification_still_exists(self):
        from automation_engine import AutomationRunner
        assert hasattr(AutomationRunner, "_handle_verification")

    def test_handle_verification_tries_webview_before_pause(self):
        from automation_engine import AutomationRunner
        src = inspect.getsource(AutomationRunner._handle_verification)
        assert "webview_invoked" in src, "must attempt webview invocation"
        assert "await btn.click()" in src or "RequestWebViewRequest" in src
        # 30s wait after invocation
        assert "30" in src
        # Pro/Elite get best-effort webview; Starter plans pause early (plan gating).
        # Both a webview attempt and a pause path must exist.
        assert "self.pause" in src


class TestVipCycleGating:
    def test_cycle_vip_gates_on_session_running(self):
        from automation_engine import AutomationRunner
        src = inspect.getsource(AutomationRunner._cycle_vip)
        assert "_session_likely_running" in src, \
            "cycle_vip must check _session_likely_running to avoid /mancing spam"
        assert "_last_mancing_at" in src

    def test_extract_and_sell_awaits_konfirmasi(self):
        from automation_engine import AutomationRunner
        src = inspect.getsource(AutomationRunner._extract_and_sell)
        # Must wait for KONFIRMASI artefak confirmation AFTER clicking green
        assert "KONFIRMASI" in src.upper() or "konfirmasi" in src.lower()
        # Should click "Ya" button on the confirmation
        assert "Ya" in src


# --- Regression: all existing endpoints ---
@pytest.fixture(scope="module")
def http():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


@pytest.fixture(scope="module")
def admin_token(http):
    r = http.post(f"{BASE_URL}/api/auth/login",
                  json={"email": "admin@fishit.app", "password": "Admin@Fishit2026"})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def auth_h(token):
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


class TestRegressionEndpoints:
    def test_health(self, http):
        assert http.get(f"{BASE_URL}/api/health").status_code == 200

    def test_admin_users(self, http, admin_token):
        r = http.get(f"{BASE_URL}/api/admin/users", headers=auth_h(admin_token))
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_admin_stats(self, http, admin_token):
        r = http.get(f"{BASE_URL}/api/admin/stats", headers=auth_h(admin_token))
        assert r.status_code == 200
        assert "total_users" in r.json()
