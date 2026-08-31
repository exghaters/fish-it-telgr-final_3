"""Fish It Automation — FastAPI entry point.

- Registers all API routers under /api prefix.
- Seeds admin account on startup.
- Graceful shutdown for Telethon + Automation engine.
"""
from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from starlette.middleware.cors import CORSMiddleware

from admin_routes import router as admin_router
from auth_routes import router as auth_router
from automation_engine import automation_engine
from automation_routes import router as automation_router
from deps import db, hash_password, verify_password
from models import User, utcnow_iso
from telegram_manager import telegram_manager
from tg_routes import router as tg_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
log = logging.getLogger("server")


async def seed_admin():
    email = os.environ.get("ADMIN_EMAIL", "admin@fishit.app").lower()
    password = os.environ["ADMIN_PASSWORD"]  # required; no insecure source default
    existing = await db.users.find_one({"email": email})
    if existing:
        updates = {}
        if existing.get("role") != "admin":
            updates["role"] = "admin"
        if not existing.get("is_active", True):
            updates["is_active"] = True  # admin can never stay deactivated
        # .env is the source of truth: rotate the hash if the password changed.
        if not verify_password(password, existing["password_hash"]):
            updates["password_hash"] = hash_password(password)
        if updates:
            await db.users.update_one({"id": existing["id"]}, {"$set": updates})
            log.info("Updated admin user %s (%s)", email, ", ".join(updates.keys()))
        return
    admin = User(email=email, password_hash=hash_password(password), role="admin", plan="elite")
    await db.users.insert_one(admin.model_dump())
    log.info("Seeded admin user %s", email)


async def ensure_indexes():
    await db.users.create_index("email", unique=True)
    await db.users.create_index("id", unique=True)
    await db.automation_configs.create_index("user_id", unique=True)
    await db.automation_state.create_index("user_id", unique=True)
    await db.telegram_sessions.create_index("user_id", unique=True)
    await db.events.create_index([("user_id", 1), ("created_at", -1)])
    await db.notifications.create_index([("user_id", 1), ("created_at", -1)])
    await db.telegram_accounts.create_index([("user_id", 1), ("created_at", 1)])
    await db.telegram_accounts.create_index("id", unique=True)
    await db.login_attempts.create_index("identifier", unique=True)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    log.info("Fish It backend starting…")
    await ensure_indexes()
    await seed_admin()
    yield
    log.info("Fish It backend shutting down…")
    try:
        await automation_engine.shutdown()
    finally:
        await telegram_manager.shutdown()


app = FastAPI(lifespan=lifespan, title="Fish It Automation API")


app.add_middleware(
    CORSMiddleware,
    allow_origins=os.environ.get("CORS_ORIGINS", "*").split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
async def health():
    return {"ok": True, "ts": utcnow_iso()}


app.include_router(auth_router)
app.include_router(tg_router)
app.include_router(automation_router)
app.include_router(admin_router)
