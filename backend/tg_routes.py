"""Telegram MTProto endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from deps import db, fernet, get_current_user
from models import (
    TelegramCredentialsInput,
    TelegramSendCodeInput,
    TelegramSessionMeta,
    TelegramVerifyInput,
    utcnow_iso,
)
from telegram_manager import telegram_manager

router = APIRouter(prefix="/api/telegram", tags=["telegram"])


@router.get("/status", response_model=TelegramSessionMeta)
async def status(user: dict = Depends(get_current_user)):
    meta = await telegram_manager.get_meta(user["id"])
    return TelegramSessionMeta(**meta)


@router.post("/credentials")
async def save_credentials(body: TelegramCredentialsInput, user: dict = Depends(get_current_user)):
    """Store api_id + api_hash (encrypted) — required before send-code."""
    enc = fernet.encrypt(body.api_hash.encode()).decode()
    await db.telegram_sessions.update_one(
        {"user_id": user["id"]},
        {"$set": {
            "user_id": user["id"],
            "api_id": body.api_id,
            "api_hash_enc": enc,
            "updated_at": utcnow_iso(),
        }},
        upsert=True,
    )
    return {"ok": True}


@router.post("/send-code")
async def send_code(body: TelegramSendCodeInput, user: dict = Depends(get_current_user)):
    doc = await db.telegram_sessions.find_one({"user_id": user["id"]})
    if not doc or not doc.get("api_id") or not doc.get("api_hash_enc"):
        raise HTTPException(status_code=400, detail="API ID / API Hash belum di-set")
    try:
        ut = await telegram_manager.get_or_create(user["id"])
        await ut.send_code(body.phone)
        return {"ok": True}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Gagal kirim kode: {exc}")


@router.post("/verify")
async def verify(body: TelegramVerifyInput, user: dict = Depends(get_current_user)):
    ut = telegram_manager.users.get(user["id"])
    if not ut or not ut.phone_code_hash:
        raise HTTPException(status_code=400, detail="Silakan minta kode dulu")
    try:
        res = await ut.verify_code(body.code, body.password)
        return res
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Verifikasi gagal: {exc}")


@router.post("/logout")
async def logout(user: dict = Depends(get_current_user)):
    await telegram_manager.logout(user["id"])
    return {"ok": True}


@router.get("/recent-messages")
async def recent_messages(chat: str, limit: int = 5, user: dict = Depends(get_current_user)):
    """Fetch recent messages from a target chat (inspection helper for config setup)."""
    ut = telegram_manager.users.get(user["id"])
    if not ut or not await ut.is_authorized():
        raise HTTPException(status_code=401, detail="Telegram belum login")
    try:
        return {"messages": await ut.get_last_messages(chat, min(limit, 20))}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))
