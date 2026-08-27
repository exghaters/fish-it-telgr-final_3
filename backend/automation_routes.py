"""Automation control + config + events + notifications endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from automation_engine import automation_engine
from deps import db, get_current_user
from models import AutomationConfig, AutomationState, utcnow_iso

router = APIRouter(prefix="/api/automation", tags=["automation"])


@router.get("/config", response_model=AutomationConfig)
async def get_config(user: dict = Depends(get_current_user)):
    doc = await db.automation_configs.find_one({"user_id": user["id"]}, {"_id": 0})
    if not doc:
        cfg = AutomationConfig(user_id=user["id"])
        await db.automation_configs.insert_one(cfg.model_dump())
        return cfg
    return AutomationConfig(**doc)


@router.put("/config", response_model=AutomationConfig)
async def update_config(body: AutomationConfig, user: dict = Depends(get_current_user)):
    body.user_id = user["id"]
    body.updated_at = utcnow_iso()
    await db.automation_configs.update_one(
        {"user_id": user["id"]},
        {"$set": body.model_dump()},
        upsert=True,
    )
    return body


@router.get("/status", response_model=AutomationState)
async def get_status(user: dict = Depends(get_current_user)):
    runner = automation_engine.get(user["id"])
    # Sync with DB (persisted state)
    doc = await db.automation_state.find_one({"user_id": user["id"]}, {"_id": 0})
    if doc:
        return AutomationState(**doc)
    return runner.state


@router.post("/start")
async def start(user: dict = Depends(get_current_user)):
    cfg = await db.automation_configs.find_one({"user_id": user["id"]})
    if not cfg or not cfg.get("group_username") and not cfg.get("bot_username"):
        raise HTTPException(status_code=400,
                            detail="Konfigurasi group/bot username wajib diisi dulu")
    # Ensure config.enabled = True
    await db.automation_configs.update_one(
        {"user_id": user["id"]}, {"$set": {"enabled": True, "updated_at": utcnow_iso()}}
    )
    await automation_engine.start(user["id"])
    return {"ok": True}


@router.post("/stop")
async def stop(user: dict = Depends(get_current_user)):
    await automation_engine.stop(user["id"])
    await db.automation_configs.update_one(
        {"user_id": user["id"]}, {"$set": {"enabled": False, "updated_at": utcnow_iso()}}
    )
    return {"ok": True}


@router.post("/pause")
async def pause(user: dict = Depends(get_current_user)):
    await automation_engine.pause(user["id"], reason="Paused by user")
    return {"ok": True}


@router.post("/resume")
async def resume(user: dict = Depends(get_current_user)):
    await automation_engine.resume(user["id"])
    return {"ok": True}


@router.get("/events")
async def events(
    limit: int = Query(100, le=500),
    kind: str = "",
    user: dict = Depends(get_current_user),
):
    q = {"user_id": user["id"]}
    if kind:
        q["kind"] = kind
    docs = await db.events.find(q, {"_id": 0}).sort("created_at", -1).limit(limit).to_list(limit)
    return {"events": docs}


@router.get("/notifications")
async def notifications(
    limit: int = Query(50, le=200),
    unread_only: bool = False,
    user: dict = Depends(get_current_user),
):
    q = {"user_id": user["id"]}
    if unread_only:
        q["read"] = False
    docs = await db.notifications.find(q, {"_id": 0}).sort("created_at", -1).limit(limit).to_list(limit)
    unread = await db.notifications.count_documents({"user_id": user["id"], "read": False})
    return {"notifications": docs, "unread_count": unread}


@router.post("/notifications/{notif_id}/read")
async def mark_read(notif_id: str, user: dict = Depends(get_current_user)):
    res = await db.notifications.update_one(
        {"id": notif_id, "user_id": user["id"]},
        {"$set": {"read": True}},
    )
    return {"ok": res.matched_count > 0}


@router.post("/notifications/read-all")
async def mark_all_read(user: dict = Depends(get_current_user)):
    await db.notifications.update_many(
        {"user_id": user["id"], "read": False}, {"$set": {"read": True}}
    )
    return {"ok": True}
