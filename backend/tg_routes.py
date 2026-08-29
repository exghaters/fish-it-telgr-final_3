"""Telegram MTProto endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from automation_engine import automation_engine
from deps import (
    db,
    ensure_default_account,
    fernet,
    get_account_key,
    get_current_user,
    plan_limits,
)
from models import (
    AccountCreateInput,
    AccountUpdateInput,
    TelegramAccount,
    TelegramCredentialsInput,
    TelegramSendCodeInput,
    TelegramSessionMeta,
    TelegramVerifyInput,
    utcnow_iso,
)
from telegram_manager import telegram_manager

router = APIRouter(prefix="/api/telegram", tags=["telegram"])


# ---------- Accounts (multi-account per plan) ----------
@router.get("/accounts")
async def list_accounts(user: dict = Depends(get_current_user)):
    await ensure_default_account(user["id"])
    docs = await db.telegram_accounts.find(
        {"user_id": user["id"]}, {"_id": 0}).sort("created_at", 1).to_list(1000)
    limits = plan_limits(user.get("plan"))
    out = []
    for d in docs:
        akey = f"{user['id']}:{d['id']}"
        meta = await telegram_manager.get_meta(akey)
        out.append({**d, "connected": meta.get("connected", False),
                    "display_name": meta.get("display_name"),
                    "phone": meta.get("phone")})
    return {"accounts": out, "limit": limits["accounts"],
            "plan": (user.get("plan") or "free"), "plan_label": limits["label"]}


@router.post("/accounts")
async def create_account(body: AccountCreateInput, user: dict = Depends(get_current_user)):
    limits = plan_limits(user.get("plan"))
    count = await db.telegram_accounts.count_documents({"user_id": user["id"]})
    if count >= limits["accounts"]:
        raise HTTPException(
            status_code=403,
            detail=f"Paket {limits['label']} maksimal {limits['accounts']} akun Telegram. "
                   "Upgrade paket untuk menambah akun.")
    acc = TelegramAccount(user_id=user["id"], label=body.label or f"Akun {count + 1}")
    await db.telegram_accounts.insert_one(acc.model_dump())
    return acc.model_dump()


@router.patch("/accounts/{account_id}")
async def update_account(account_id: str, body: AccountUpdateInput,
                         user: dict = Depends(get_current_user)):
    label = body.label.strip()
    res = await db.telegram_accounts.update_one(
        {"id": account_id, "user_id": user["id"]}, {"$set": {"label": label}})
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Akun tidak ditemukan")
    return {"ok": True, "label": label}


@router.delete("/accounts/{account_id}")
async def delete_account(account_id: str, user: dict = Depends(get_current_user)):
    acc = await db.telegram_accounts.find_one({"id": account_id, "user_id": user["id"]})
    if not acc:
        raise HTTPException(status_code=404, detail="Akun tidak ditemukan")
    if await db.telegram_accounts.count_documents({"user_id": user["id"]}) <= 1:
        raise HTTPException(status_code=400, detail="Minimal harus ada 1 akun")
    akey = f"{user['id']}:{account_id}"
    try:
        await automation_engine.stop(akey)
    except Exception:
        pass
    try:
        await telegram_manager.logout(akey)
    except Exception:
        pass
    for coll in (db.automation_configs, db.automation_state, db.events, db.notifications):
        await coll.delete_many({"user_id": akey})
    await db.telegram_accounts.delete_one({"id": account_id, "user_id": user["id"]})
    return {"ok": True}


# ---------- Session (scoped to the selected account via X-Account-Id) ----------
@router.get("/status", response_model=TelegramSessionMeta)
async def status(akey: str = Depends(get_account_key)):
    meta = await telegram_manager.get_meta(akey)
    return TelegramSessionMeta(**meta)


@router.post("/credentials")
async def save_credentials(body: TelegramCredentialsInput, akey: str = Depends(get_account_key)):
    """Store api_id + api_hash (encrypted) — required before send-code."""
    enc = fernet.encrypt(body.api_hash.encode()).decode()
    await db.telegram_sessions.update_one(
        {"user_id": akey},
        {"$set": {"user_id": akey, "api_id": body.api_id,
                  "api_hash_enc": enc, "updated_at": utcnow_iso()}},
        upsert=True,
    )
    return {"ok": True}


@router.post("/send-code")
async def send_code(body: TelegramSendCodeInput, akey: str = Depends(get_account_key)):
    doc = await db.telegram_sessions.find_one({"user_id": akey})
    if not doc or not doc.get("api_id") or not doc.get("api_hash_enc"):
        raise HTTPException(status_code=400, detail="API ID / API Hash belum di-set")
    try:
        ut = await telegram_manager.get_or_create(akey)
        await ut.send_code(body.phone)
        return {"ok": True}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Gagal kirim kode: {exc}")


@router.post("/verify")
async def verify(body: TelegramVerifyInput, akey: str = Depends(get_account_key)):
    ut = telegram_manager.users.get(akey)
    if not ut or not ut.phone_code_hash:
        raise HTTPException(status_code=400, detail="Silakan minta kode dulu")
    try:
        return await ut.verify_code(body.code, body.password)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Verifikasi gagal: {exc}")


@router.post("/logout")
async def logout(akey: str = Depends(get_account_key)):
    await telegram_manager.logout(akey)
    return {"ok": True}


@router.get("/recent-messages")
async def recent_messages(chat: str, limit: int = 5, akey: str = Depends(get_account_key)):
    """Fetch recent messages from a target chat (inspection helper for config setup)."""
    ut = telegram_manager.users.get(akey)
    if not ut or not await ut.is_authorized():
        raise HTTPException(status_code=401, detail="Telegram belum login")
    try:
        return {"messages": await ut.get_last_messages(chat, min(limit, 20))}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))
