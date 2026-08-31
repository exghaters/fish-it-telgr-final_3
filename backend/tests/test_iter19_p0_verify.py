"""Quick P0 verification: admin guards + config reset via public URL."""
import os
import requests
import pytest
from dotenv import load_dotenv

load_dotenv('/app/backend/.env')
BASE = os.environ['REACT_APP_BACKEND_URL'].rstrip('/') if os.environ.get('REACT_APP_BACKEND_URL') else 'https://botcraft-telegram-1.preview.emergentagent.com'
ADMIN_EMAIL = 'admin@fishit.app'
ADMIN_PASS = os.environ.get('ADMIN_PASSWORD')


@pytest.fixture(scope='module')
def admin_session():
    s = requests.Session()
    r = s.post(f'{BASE}/api/auth/login', json={'email': ADMIN_EMAIL, 'password': ADMIN_PASS})
    assert r.status_code == 200, r.text
    return s


def _admin_id(sess):
    r = sess.get(f'{BASE}/api/admin/users')
    assert r.status_code == 200, r.text
    users = r.json()
    for u in users:
        if u['email'] == ADMIN_EMAIL:
            return u['id'], u
    raise AssertionError('admin not found')


def test_admin_is_active_true(admin_session):
    _, u = _admin_id(admin_session)
    assert u['is_active'] is True


def test_admin_cannot_be_deactivated(admin_session):
    aid, _ = _admin_id(admin_session)
    r = admin_session.put(f'{BASE}/api/admin/users/{aid}', json={'is_active': False})
    assert r.status_code == 400
    # blocked either by self-guard or admin-guard; both are acceptable
    assert 'tidak bisa' in r.json().get('detail', '').lower()


def test_admin_cannot_be_deleted(admin_session):
    aid, _ = _admin_id(admin_session)
    r = admin_session.delete(f'{BASE}/api/admin/users/{aid}')
    assert r.status_code == 400
    assert 'tidak bisa' in r.json().get('detail', '').lower()


def test_admin_can_still_login():
    s = requests.Session()
    r = s.post(f'{BASE}/api/auth/login', json={'email': ADMIN_EMAIL, 'password': ADMIN_PASS})
    assert r.status_code == 200


def test_config_reset_returns_defaults(admin_session):
    r = admin_session.post(f'{BASE}/api/automation/config/reset')
    assert r.status_code == 200, r.text
    cfg = r.json()
    assert cfg.get('mode') == 'vip_direct'
    assert cfg.get('open_command') == '/mancing'
    assert cfg.get('bot_username') == '@fish_it_bot'

    # verify persisted
    r2 = admin_session.get(f'{BASE}/api/automation/config')
    assert r2.status_code == 200
    c2 = r2.json()
    assert c2.get('mode') == 'vip_direct'
    assert c2.get('bot_username') == '@fish_it_bot'
