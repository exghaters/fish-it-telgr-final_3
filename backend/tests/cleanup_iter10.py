"""Cleanup iter10 test artifacts: temp users + extra telegram account created in UI test."""
import asyncio
import os
import sys

sys.path.insert(0, "/app/backend")
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

load_dotenv("/app/backend/.env")


async def main():
    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = client[os.environ["DB_NAME"]]
    # temp users created by iter10 tests
    users = await db.users.find({"email": {"$regex": "^test_iter10_"}}, {"_id": 0, "id": 1, "email": 1}).to_list(100)
    for u in users:
        await db.automation_configs.delete_many({"user_id": {"$regex": f"^{u['id']}"}})
        await db.telegram_accounts.delete_many({"user_id": u["id"]})
        await db.users.delete_one({"id": u["id"]})
        print("deleted user", u["email"])
    # extra telegram account created for seeded elite user during UI switcher test
    seeded = await db.users.find_one({"email": "user@fishit.app"}, {"_id": 0, "id": 1})
    if seeded:
        accs = await db.telegram_accounts.find({"user_id": seeded["id"]}, {"_id": 0}).sort("created_at", 1).to_list(10)
        for a in accs[1:]:
            await db.telegram_accounts.delete_one({"id": a["id"]})
            await db.automation_configs.delete_many({"user_id": f"{seeded['id']}:{a['id']}"})
            print("deleted extra tg account", a["label"])
    client.close()


asyncio.run(main())
