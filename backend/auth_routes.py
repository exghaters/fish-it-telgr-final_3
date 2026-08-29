"""Auth endpoints: register, login, logout, me."""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response

from deps import create_access_token, db, get_current_user, hash_password, verify_password
from models import LoginInput, RegisterInput, TokenResponse, User, UserPublic

router = APIRouter(prefix="/api/auth", tags=["auth"])

# httpOnly cookie lifetime mirrors the JWT TTL (7 days).
COOKIE_MAX_AGE = 60 * 60 * 24 * 7

# Brute-force protection.
MAX_FAILED = 5
LOCKOUT_MINUTES = 15


def _set_auth_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key="access_token",
        value=token,
        httponly=True,
        secure=True,
        samesite="lax",
        max_age=COOKIE_MAX_AGE,
        path="/",
    )


def _public(u: dict) -> UserPublic:
    return UserPublic(
        id=u["id"],
        email=u["email"],
        role=u.get("role", "user"),
        plan=u.get("plan", "free"),
        is_active=u.get("is_active", True),
        created_at=u.get("created_at", ""),
    )


def _client_ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


async def _check_lockout(identifier: str) -> None:
    rec = await db.login_attempts.find_one({"identifier": identifier})
    if not rec or rec.get("count", 0) < MAX_FAILED:
        return
    locked_until = rec.get("locked_until")
    if not locked_until:
        return
    lu = datetime.fromisoformat(locked_until)
    now = datetime.now(timezone.utc)
    if lu > now:
        mins = int((lu - now).total_seconds()) // 60 + 1
        raise HTTPException(
            status_code=429,
            detail=f"Terlalu banyak percobaan gagal. Coba lagi dalam {mins} menit.",
        )


async def _record_failure(identifier: str) -> None:
    rec = await db.login_attempts.find_one({"identifier": identifier})
    count = (rec.get("count", 0) if rec else 0) + 1
    update = {
        "identifier": identifier,
        "count": count,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    if count >= MAX_FAILED:
        update["locked_until"] = (
            datetime.now(timezone.utc) + timedelta(minutes=LOCKOUT_MINUTES)
        ).isoformat()
    await db.login_attempts.update_one(
        {"identifier": identifier}, {"$set": update}, upsert=True)


async def _clear_failures(identifier: str) -> None:
    await db.login_attempts.delete_one({"identifier": identifier})


@router.post("/register", response_model=TokenResponse)
async def register(body: RegisterInput, response: Response):
    if os.environ.get("ALLOW_PUBLIC_REGISTRATION", "false").lower() != "true":
        raise HTTPException(
            status_code=403,
            detail="Pendaftaran publik dinonaktifkan. Hubungi admin untuk dibuatkan akun.")
    existing = await db.users.find_one({"email": body.email.lower()})
    if existing:
        raise HTTPException(status_code=400, detail="Email sudah terdaftar")
    user = User(
        email=body.email.lower(),
        password_hash=hash_password(body.password),
    )
    doc = user.model_dump()
    await db.users.insert_one(doc)
    token = create_access_token(user.id, user.role)
    _set_auth_cookie(response, token)
    return TokenResponse(user=_public(doc))


@router.post("/login", response_model=TokenResponse)
async def login(body: LoginInput, request: Request, response: Response):
    identifier = f"{_client_ip(request)}:{body.email.lower()}"
    await _check_lockout(identifier)
    user = await db.users.find_one({"email": body.email.lower()}, {"_id": 0})
    if not user or not verify_password(body.password, user["password_hash"]):
        await _record_failure(identifier)
        raise HTTPException(status_code=401, detail="Email atau password salah")
    if not user.get("is_active", True):
        raise HTTPException(status_code=403, detail="Akun dinonaktifkan")
    await _clear_failures(identifier)
    token = create_access_token(user["id"], user.get("role", "user"))
    _set_auth_cookie(response, token)
    return TokenResponse(user=_public(user))


@router.post("/logout")
async def logout(response: Response):
    response.delete_cookie("access_token", path="/")
    return {"ok": True}


@router.get("/me", response_model=UserPublic)
async def me(user: dict = Depends(get_current_user)):
    return _public(user)
