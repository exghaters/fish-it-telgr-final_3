"""Shared dependencies: Mongo, Fernet, JWT auth, current user."""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import jwt
from cryptography.fernet import Fernet
from dotenv import load_dotenv
from fastapi import Cookie, Depends, Header, HTTPException, status
from motor.motor_asyncio import AsyncIOMotorClient
from passlib.context import CryptContext
from pymongo.errors import DuplicateKeyError

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")

# --- Mongo ---
_mongo_url = os.environ["MONGO_URL"]
_client = AsyncIOMotorClient(_mongo_url)
db = _client[os.environ["DB_NAME"]]


def get_mongo_client() -> AsyncIOMotorClient:
    return _client


# --- Fernet for encrypting Telegram sessions ---
_fernet_key = os.environ["SESSION_FERNET_KEY"].encode()
fernet = Fernet(_fernet_key)


# --- Passwords ---
pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(plain: str) -> str:
    return pwd_ctx.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return pwd_ctx.verify(plain, hashed)
    except Exception:
        return False


# --- JWT ---
_JWT_SECRET = os.environ["JWT_SECRET"]
_JWT_ALG = "HS256"
_JWT_TTL_HOURS = 24 * 7


def create_access_token(user_id: str, role: str) -> str:
    payload = {
        "sub": user_id,
        "role": role,
        "iat": datetime.now(timezone.utc),
        "exp": datetime.now(timezone.utc) + timedelta(hours=_JWT_TTL_HOURS),
    }
    return jwt.encode(payload, _JWT_SECRET, algorithm=_JWT_ALG)


def decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, _JWT_SECRET, algorithms=[_JWT_ALG])
    except jwt.PyJWTError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid token: {e}",
        )


async def get_current_user(
    authorization: Optional[str] = Header(default=None),
    access_token: Optional[str] = Cookie(default=None),
) -> dict:
    token = None
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization.split(" ", 1)[1].strip()
    elif access_token:
        token = access_token
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing token",
        )
    payload = decode_token(token)
    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="Malformed token")
    user = await db.users.find_one({"id": user_id}, {"_id": 0})
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    if not user.get("is_active", True):
        raise HTTPException(status_code=403, detail="Account disabled")
    return user


async def get_current_admin(user: dict = Depends(get_current_user)) -> dict:
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin only")
    return user


# --- Plan limits & multi-account ---
PLAN_LIMITS = {
    "free":  {"accounts": 1, "log_days": 7,  "auto_verify": False, "vip_multi": False, "label": "Starter"},
    "basic": {"accounts": 1, "log_days": 7,  "auto_verify": False, "vip_multi": False, "label": "Starter"},
    "pro":   {"accounts": 1, "log_days": 30, "auto_verify": True,  "vip_multi": True,  "label": "Pro"},
    "elite": {"accounts": 100, "log_days": 90, "auto_verify": True,  "vip_multi": True,  "label": "Elite"},
}


def plan_limits(plan: Optional[str]) -> dict:
    return PLAN_LIMITS.get((plan or "free").lower(), PLAN_LIMITS["free"])


async def ensure_default_account(user_id: str) -> str:
    doc = await db.telegram_accounts.find_one({"user_id": user_id}, sort=[("created_at", 1)])
    if doc:
        return doc["id"]
    # Deterministic id so concurrent first-load requests can't create duplicates:
    # the unique index on `id` lets only one insert win; the rest are ignored.
    aid = f"default-{user_id}"
    try:
        await db.telegram_accounts.insert_one({
            "id": aid, "user_id": user_id, "label": "Akun 1",
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
    except DuplicateKeyError:
        pass
    doc = await db.telegram_accounts.find_one({"user_id": user_id}, sort=[("created_at", 1)])
    return doc["id"]


async def get_account_key(
    x_account_id: Optional[str] = Header(default=None),
    user: dict = Depends(get_current_user),
) -> str:
    """Composite runtime key 'user_id:account_id' scoping all TG/automation state."""
    uid = user["id"]
    if x_account_id:
        acc = await db.telegram_accounts.find_one({"id": x_account_id, "user_id": uid})
        if acc:
            return f"{uid}:{acc['id']}"
    aid = await ensure_default_account(uid)
    return f"{uid}:{aid}"
