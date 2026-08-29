"""Auth endpoints: register, login, logout, me."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response

from deps import create_access_token, db, get_current_user, hash_password, verify_password
from models import LoginInput, RegisterInput, TokenResponse, User, UserPublic

router = APIRouter(prefix="/api/auth", tags=["auth"])

# JWT lives 30 days; keep the httpOnly cookie in sync.
COOKIE_MAX_AGE = 60 * 60 * 24 * 30


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


@router.post("/register", response_model=TokenResponse)
async def register(body: RegisterInput, response: Response):
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
    return TokenResponse(access_token=token, user=_public(doc))


@router.post("/login", response_model=TokenResponse)
async def login(body: LoginInput, response: Response):
    user = await db.users.find_one({"email": body.email.lower()}, {"_id": 0})
    if not user or not verify_password(body.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Email atau password salah")
    if not user.get("is_active", True):
        raise HTTPException(status_code=403, detail="Akun dinonaktifkan")
    token = create_access_token(user["id"], user.get("role", "user"))
    _set_auth_cookie(response, token)
    return TokenResponse(access_token=token, user=_public(user))


@router.post("/logout")
async def logout(response: Response):
    response.delete_cookie("access_token", path="/")
    return {"ok": True}


@router.get("/me", response_model=UserPublic)
async def me(user: dict = Depends(get_current_user)):
    return _public(user)
