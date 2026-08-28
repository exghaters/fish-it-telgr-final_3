"""Seed/cleanup helper: insert 2 unread notifications for admin@fishit.app (UI regression test).

Usage:
    python seed_notifs_iter9.py seed
    python seed_notifs_iter9.py clean
"""
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv(Path(__file__).resolve().parents[1] / ".env")
MONGO_URL = os.environ["MONGO_URL"]
DB_NAME = os.environ["DB_NAME"]
TAG = "iter9-ui-notif"


def main():
    action = sys.argv[1] if len(sys.argv) > 1 else "seed"
    client = MongoClient(MONGO_URL)
    db = client[DB_NAME]
    user = db.users.find_one({"email": os.environ.get("ADMIN_EMAIL", "admin@fishit.app")})
    assert user, "admin user not found"
    uid = user["id"]
    acc = db.telegram_accounts.find_one({"user_id": uid})
    assert acc, "no telegram account for admin"
    akey = f"{uid}:{acc['id']}"  # notifications are account-scoped (get_account_key)
    if action == "clean":
        res = db.notifications.delete_many({"id": {"$regex": f"^{TAG}"}})
        print("deleted", res.deleted_count)
    else:
        docs = []
        for i in range(2):
            docs.append({
                "id": f"{TAG}-{uuid.uuid4()}",
                "user_id": akey,
                "title": f"TEST_ Notifikasi {i + 1}",
                "body": "Regression check iter9",
                "kind": "info",
                "read": False,
                "created_at": datetime.now(timezone.utc).isoformat(),
            })
        db.notifications.insert_many(docs)
        print("seeded", len(docs), "for", akey)
    client.close()


if __name__ == "__main__":
    main()
