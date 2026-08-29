"""Admin-only endpoints: manage users."""
from __future__ import annotations

import re

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr, Field

from deps import db, get_current_admin, hash_password
from models import AdminUpdateUserInput, User, UserPublic

router = APIRouter(prefix="/api/admin", tags=["admin"])


class ResetPasswordInput(BaseModel):
    new_password: str = Field(min_length=6, max_length=200)


class CreateUserInput(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=200)
    role: str = "user"
    plan: str = "elite"  # operators default to elite (many Telegram accounts)


def _public(u: dict) -> UserPublic:
    return UserPublic(
        id=u["id"],
        email=u["email"],
        role=u.get("role", "user"),
        plan=u.get("plan", "free"),
        is_active=u.get("is_active", True),
        created_at=u.get("created_at", ""),
    )


@router.get("/users", response_model=list[UserPublic])
async def list_users(_: dict = Depends(get_current_admin)):
    docs = await db.users.find({}, {"_id": 0, "password_hash": 0}).sort("created_at", -1).to_list(500)
    return [_public(d) for d in docs]


@router.post("/users", response_model=UserPublic)
async def create_user(body: CreateUserInput, _: dict = Depends(get_current_admin)):
    if await db.users.find_one({"email": body.email.lower()}):
        raise HTTPException(400, "Email sudah terdaftar")
    role = body.role if body.role in ("user", "admin") else "user"
    user = User(email=body.email.lower(), password_hash=hash_password(body.password),
                role=role, plan=body.plan)
    doc = user.model_dump()
    await db.users.insert_one(doc)
    return _public(doc)


@router.put("/users/{user_id}", response_model=UserPublic)
async def update_user(user_id: str, body: AdminUpdateUserInput,
                      _: dict = Depends(get_current_admin)):
    update = {k: v for k, v in body.model_dump().items() if v is not None}
    if not update:
        raise HTTPException(400, "Nothing to update")
    res = await db.users.find_one_and_update(
        {"id": user_id}, {"$set": update},
        return_document=True,
        projection={"_id": 0, "password_hash": 0},
    )
    if not res:
        raise HTTPException(404, "User not found")
    return _public(res)


@router.post("/users/{user_id}/reset-password")
async def reset_password(user_id: str, body: ResetPasswordInput,
                         _: dict = Depends(get_current_admin)):
    res = await db.users.update_one(
        {"id": user_id}, {"$set": {"password_hash": hash_password(body.new_password)}})
    if res.matched_count == 0:
        raise HTTPException(404, "User not found")
    return {"ok": True}


@router.delete("/users/{user_id}")
async def delete_user(user_id: str, admin: dict = Depends(get_current_admin)):
    if user_id == admin["id"]:
        raise HTTPException(400, "Tidak bisa menghapus akun sendiri")
    target = await db.users.find_one({"id": user_id}, {"_id": 0, "password_hash": 0})
    if not target:
        raise HTTPException(404, "User not found")
    await db.users.delete_one({"id": user_id})
    # Cascade delete all user-scoped data (supports both "uid" and "uid:account" keys).
    scope = {"$or": [{"user_id": user_id},
                     {"user_id": {"$regex": f"^{re.escape(user_id)}:"}}]}
    for coll in (db.automation_configs, db.automation_state, db.telegram_sessions,
                 db.events, db.notifications, db.telegram_accounts):
        await coll.delete_many(scope)
    return {"ok": True, "deleted": target.get("email")}


@router.get("/stats")
async def stats(_: dict = Depends(get_current_admin)):
    total = await db.users.count_documents({})
    active = await db.users.count_documents({"is_active": True})
    running = await db.automation_state.count_documents(
        {"status": {"$nin": ["idle", "stopped", "error"]}}
    )
    plans = {}
    async for u in db.users.aggregate([
        {"$group": {"_id": "$plan", "count": {"$sum": 1}}}
    ]):
        plans[u["_id"] or "free"] = u["count"]
    return {
        "total_users": total,
        "active_users": active,
        "running_bots": running,
        "plans": plans,
    }
