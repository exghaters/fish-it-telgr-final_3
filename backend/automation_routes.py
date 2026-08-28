"""Automation control + config + events + notifications endpoints."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query

from automation_engine import automation_engine
from deps import db, get_account_key, get_current_user, plan_limits
from models import AutomationConfig, AutomationState, utcnow_iso
from telegram_manager import telegram_manager

router = APIRouter(prefix="/api/automation", tags=["automation"])


@router.get("/config", response_model=AutomationConfig)
async def get_config(akey: str = Depends(get_account_key)):
    doc = await db.automation_configs.find_one({"user_id": akey}, {"_id": 0})
    if not doc:
        cfg = AutomationConfig(user_id=akey)
        await db.automation_configs.insert_one(cfg.model_dump())
        return cfg
    return AutomationConfig(**doc)


@router.put("/config", response_model=AutomationConfig)
async def update_config(body: AutomationConfig, akey: str = Depends(get_account_key),
                        user: dict = Depends(get_current_user)):
    body.user_id = akey
    body.updated_at = utcnow_iso()
    # Plan gating: only Pro/Elite may add extra VIP bots/chats (multi-bot).
    # Starter is limited to a single bot/group target.
    if not plan_limits(user.get("plan"))["vip_multi"]:
        body.extra_allowed_chats = ""
    await db.automation_configs.update_one(
        {"user_id": akey}, {"$set": body.model_dump()}, upsert=True)
    return body


@router.get("/status", response_model=AutomationState)
async def get_status(akey: str = Depends(get_account_key)):
    runner = automation_engine.get(akey)
    doc = await db.automation_state.find_one({"user_id": akey}, {"_id": 0})
    if doc:
        return AutomationState(**doc)
    return runner.state


@router.post("/start")
async def start(akey: str = Depends(get_account_key)):
    cfg = await db.automation_configs.find_one({"user_id": akey})
    if not cfg or (not cfg.get("group_username") and not cfg.get("bot_username")):
        raise HTTPException(status_code=400,
                            detail="Konfigurasi group/bot username wajib diisi dulu")
    try:
        ut = await telegram_manager.get_or_create(akey)
        connected = await ut.is_authorized()
    except Exception:
        connected = False
    if not connected:
        raise HTTPException(
            status_code=400,
            detail="Hubungkan akun Telegram dulu di menu Telegram sebelum Start")
    await db.automation_configs.update_one(
        {"user_id": akey}, {"$set": {"enabled": True, "updated_at": utcnow_iso()}})
    await automation_engine.start(akey)
    return {"ok": True}


@router.post("/stop")
async def stop(akey: str = Depends(get_account_key)):
    await automation_engine.stop(akey)
    await db.automation_configs.update_one(
        {"user_id": akey}, {"$set": {"enabled": False, "updated_at": utcnow_iso()}})
    return {"ok": True}


@router.post("/pause")
async def pause(akey: str = Depends(get_account_key)):
    await automation_engine.pause(akey, reason="Paused by user")
    return {"ok": True}


@router.post("/resume")
async def resume(akey: str = Depends(get_account_key)):
    await automation_engine.resume(akey)
    return {"ok": True}


@router.get("/events")
async def events(
    limit: int = Query(100, le=500),
    kind: str = "",
    akey: str = Depends(get_account_key),
    user: dict = Depends(get_current_user),
):
    q = {"user_id": akey}
    if kind:
        q["kind"] = kind
    days = plan_limits(user.get("plan"))["log_days"]
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    q["created_at"] = {"$gte": cutoff}
    docs = await db.events.find(q, {"_id": 0}).sort("created_at", -1).limit(limit).to_list(limit)
    return {"events": docs, "log_days": days}


@router.get("/notifications")
async def notifications(
    limit: int = Query(50, le=200),
    unread_only: bool = False,
    akey: str = Depends(get_account_key),
):
    q = {"user_id": akey}
    if unread_only:
        q["read"] = False
    docs = await db.notifications.find(q, {"_id": 0}).sort("created_at", -1).limit(limit).to_list(limit)
    unread = await db.notifications.count_documents({"user_id": akey, "read": False})
    return {"notifications": docs, "unread_count": unread}


@router.post("/notifications/{notif_id}/read")
async def mark_read(notif_id: str, akey: str = Depends(get_account_key)):
    res = await db.notifications.update_one(
        {"id": notif_id, "user_id": akey}, {"$set": {"read": True}})
    return {"ok": res.matched_count > 0}


@router.post("/notifications/read-all")
async def mark_all_read(akey: str = Depends(get_account_key)):
    await db.notifications.update_many(
        {"user_id": akey, "read": False}, {"$set": {"read": True}})
    return {"ok": True}
