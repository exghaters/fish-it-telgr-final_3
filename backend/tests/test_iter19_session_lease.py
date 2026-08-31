"""Iteration 19 — cross-process Telegram session ownership lease.

Proves the fix for: "authorization key was used under two different IP addresses
simultaneously" (AUTH_KEY_DUPLICATED). Only ONE process may hold a live client
per session key (user_id:account_id) at a time; different keys are independent.
"""
import asyncio
import uuid
from datetime import datetime, timedelta, timezone

from deps import db
from telegram_manager import INSTANCE_ID, telegram_manager


def test_session_lease_cross_process():
    async def run():
        tm = telegram_manager
        k1 = f"test-lease:{uuid.uuid4().hex}"
        k2 = f"test-lease:{uuid.uuid4().hex}"
        await db.telegram_locks.delete_many({"_id": {"$in": [k1, k2]}})

        # 1. First claim succeeds.
        assert await tm._acquire_lease(k1) is True
        # 2. Re-claim by the SAME owner (poll/refresh) succeeds (no duplicate client).
        assert await tm._acquire_lease(k1) is True
        # 3. A DIFFERENT session key is independent -> parallel accounts OK.
        assert await tm._acquire_lease(k2) is True
        da = await db.telegram_locks.find_one({"_id": k1})
        dbb = await db.telegram_locks.find_one({"_id": k2})
        assert da["_id"] != dbb["_id"]
        assert da["owner"] == INSTANCE_ID and dbb["owner"] == INSTANCE_ID

        # 4. A fresh FOREIGN owner blocks us (would be a 2nd worker/container).
        await db.telegram_locks.update_one(
            {"_id": k1},
            {"$set": {"owner": "other-process",
                      "heartbeat": datetime.now(timezone.utc).isoformat()}})
        assert await tm._acquire_lease(k1) is False
        # k2 (our fresh lease) is unaffected -> two accounts run in parallel.
        assert await tm._acquire_lease(k2) is True

        # 5. A STALE foreign lease (dead process) can be taken over.
        stale = (datetime.now(timezone.utc) - timedelta(seconds=120)).isoformat()
        await db.telegram_locks.update_one(
            {"_id": k1}, {"$set": {"owner": "other-process", "heartbeat": stale}})
        assert await tm._acquire_lease(k1) is True
        doc = await db.telegram_locks.find_one({"_id": k1})
        assert doc["owner"] == INSTANCE_ID

        # 6. Release frees the lease.
        await tm._release_lease(k1)
        assert await db.telegram_locks.find_one({"_id": k1}) is None

        await db.telegram_locks.delete_many({"_id": {"$in": [k1, k2]}})

    asyncio.run(run())
