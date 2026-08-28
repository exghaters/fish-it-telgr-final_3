"""One-off cleanup: remove QA-created extra Telegram accounts for admin/user."""
import requests
from dotenv import dotenv_values

BASE = dotenv_values("/app/frontend/.env")["REACT_APP_BACKEND_URL"].rstrip("/")
API = f"{BASE}/api"

for creds in ({"email": "admin@fishit.app", "password": "Admin@Fishit2026"},
              {"email": "user@fishit.app", "password": "FishIt#2026"}):
    tok = requests.post(f"{API}/auth/login", json=creds, timeout=30).json()["access_token"]
    h = {"Authorization": f"Bearer {tok}"}
    accs = requests.get(f"{API}/telegram/accounts", headers=h, timeout=30).json()["accounts"]
    print(creds["email"], [a["label"] for a in accs])
    for a in accs[1:]:
        r = requests.delete(f"{API}/telegram/accounts/{a['id']}", headers=h, timeout=30)
        print("  deleted", a["label"], r.status_code)
    accs = requests.get(f"{API}/telegram/accounts", headers=h, timeout=30).json()
    print("  remaining:", [a["label"] for a in accs["accounts"]], "plan:", accs["plan"])
