"""Admin-only endpoints: manage users."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from deps import db, get_current_admin
from models import AdminUpdateUserInput, UserPublic

router = APIRouter(prefix="/api/admin", tags=["admin"])


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
