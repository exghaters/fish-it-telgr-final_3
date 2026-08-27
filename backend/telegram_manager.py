"""Per-user Telethon MTProto client manager.

- Encrypts session strings with Fernet before persisting in MongoDB.
- Provides login flow (send code -> verify code + optional 2FA).
- Exposes helpers to send messages / click inline buttons.
- Owns real-time NewMessage event subscription piped to a queue.

NOTE: Runs one Uvicorn worker only (default). Do NOT scale to multiple workers
without a distributed session ownership lease.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Optional

from telethon import TelegramClient, events
from telethon.errors import SessionPasswordNeededError
from telethon.sessions import StringSession

from deps import db, fernet
from models import utcnow_iso

log = logging.getLogger("telegram_manager")


class UserTelegram:
    def __init__(self, user_id: str, api_id: int, api_hash: str, session_str: str = ""):
        self.user_id = user_id
        self.api_id = api_id
        self.api_hash = api_hash
        self.session = StringSession(session_str)
        self.client: Optional[TelegramClient] = None
        self.phone: Optional[str] = None
        self.phone_code_hash: Optional[str] = None
        self.display_name: Optional[str] = None
        self.lock = asyncio.Lock()
        self.event_queue: asyncio.Queue = asyncio.Queue(maxsize=1000)
        self._handler_installed = False

    async def connect(self):
        if self.client is None:
            self.client = TelegramClient(
                self.session,
                self.api_id,
                self.api_hash,
                auto_reconnect=True,
                connection_retries=10,
                retry_delay=2,
                request_retries=5,
                flood_sleep_threshold=60,
                sequential_updates=True,
            )
        if not self.client.is_connected():
            await self.client.connect()

    async def is_authorized(self) -> bool:
        await self.connect()
        try:
            return await self.client.is_user_authorized()
        except Exception:
            return False

    async def send_code(self, phone: str) -> str:
        await self.connect()
        sent = await self.client.send_code_request(phone)
        self.phone = phone
        self.phone_code_hash = sent.phone_code_hash
        return sent.phone_code_hash

    async def verify_code(self, code: str, password: Optional[str] = None) -> dict:
        """Returns {'ok': True} or {'two_fa_required': True}."""
        await self.connect()
        try:
            await self.client.sign_in(
                phone=self.phone,
                code=code,
                phone_code_hash=self.phone_code_hash,
            )
        except SessionPasswordNeededError:
            if not password:
                return {"two_fa_required": True}
            await self.client.sign_in(password=password)

        me = await self.client.get_me()
        self.display_name = (
            (me.first_name or "") + (" " + me.last_name if me.last_name else "")
        ).strip() or (me.username or self.phone or "")
        await self._persist_session()
        self._install_default_handler()
        return {"ok": True, "display_name": self.display_name}

    async def _persist_session(self):
        session_str = self.client.session.save()
        enc = fernet.encrypt(session_str.encode()).decode()
        await db.telegram_sessions.update_one(
            {"user_id": self.user_id},
            {"$set": {
                "user_id": self.user_id,
                "session_enc": enc,
                "phone": self.phone,
                "display_name": self.display_name,
                "api_id": self.api_id,
                "api_hash_enc": fernet.encrypt(self.api_hash.encode()).decode(),
                "updated_at": utcnow_iso(),
            }},
            upsert=True,
        )

    def _install_default_handler(self):
        if self._handler_installed:
            return
        client = self.client

        async def on_message(event):
            try:
                item = {
                    "type": "message",
                    "chat_id": event.chat_id,
                    "message_id": event.id,
                    "text": event.raw_text or "",
                    "is_reply": event.is_reply,
                    "date": event.date.isoformat() if event.date else None,
                }
                try:
                    self.event_queue.put_nowait(item)
                except asyncio.QueueFull:
                    # Drop oldest
                    try:
                        self.event_queue.get_nowait()
                    except Exception:
                        pass
                    self.event_queue.put_nowait(item)
            except Exception as exc:
                log.exception("handler error: %s", exc)

        client.add_event_handler(on_message, events.NewMessage())

        # Also listen for edits so button/state changes on same message reach us.
        async def on_edited(event):
            try:
                item = {
                    "type": "edited",
                    "chat_id": event.chat_id,
                    "message_id": event.id,
                    "text": event.raw_text or "",
                    "is_reply": event.is_reply,
                    "date": event.date.isoformat() if event.date else None,
                }
                try:
                    self.event_queue.put_nowait(item)
                except asyncio.QueueFull:
                    try:
                        self.event_queue.get_nowait()
                    except Exception:
                        pass
                    self.event_queue.put_nowait(item)
            except Exception as exc:
                log.exception("edit handler error: %s", exc)

        client.add_event_handler(on_edited, events.MessageEdited())
        self._handler_installed = True

    async def send_command(self, chat: str, text: str):
        await self.connect()
        async with self.lock:
            msg = await self.client.send_message(chat, text)
            return msg

    async def get_last_messages(self, chat: str, limit: int = 5):
        await self.connect()
        try:
            entity = await self.client.get_entity(chat)
        except Exception as exc:
            raise ValueError(f"Chat not found: {chat} ({exc})")
        msgs = []
        async for m in self.client.iter_messages(entity, limit=limit):
            msgs.append({
                "id": m.id,
                "text": m.raw_text or "",
                "date": m.date.isoformat() if m.date else None,
                "buttons": self._flatten_buttons(m),
            })
        return msgs

    @staticmethod
    def _flatten_buttons(msg):
        rows = getattr(msg, "buttons", None) or []
        out = []
        for r, row in enumerate(rows):
            for c, btn in enumerate(row):
                out.append({
                    "row": r,
                    "col": c,
                    "text": getattr(btn, "text", None),
                    "url": getattr(btn, "url", None),
                    "data": (btn.data.decode(errors="ignore") if getattr(btn, "data", None) else None),
                })
        return out

    async def click_button(self, chat: str, message_id: int, text: Optional[str] = None,
                           row: Optional[int] = None, col: Optional[int] = None) -> dict:
        await self.connect()
        async with self.lock:
            msg = await self.client.get_messages(chat, ids=message_id)
            if not msg:
                raise ValueError("Message not found")
            if text is not None:
                result = await msg.click(text=text)
            elif row is not None and col is not None:
                result = await msg.click(row, col)
            else:
                raise ValueError("Provide text or row+col")
            return {
                "message": getattr(result, "message", None),
                "alert": getattr(result, "alert", None),
                "url": getattr(result, "url", None),
            }

    async def find_button_url(self, chat: str, message_id: int, text: str) -> Optional[str]:
        await self.connect()
        msg = await self.client.get_messages(chat, ids=message_id)
        for row in getattr(msg, "buttons", None) or []:
            for btn in row:
                if getattr(btn, "text", "") == text and getattr(btn, "url", None):
                    return btn.url
        return None

    async def disconnect(self):
        if self.client and self.client.is_connected():
            await self.client.disconnect()


class TelegramManager:
    """Global registry of per-user Telethon clients."""

    def __init__(self):
        self.users: dict[str, UserTelegram] = {}
        self._locks: dict[str, asyncio.Lock] = {}

    def _lock(self, uid: str) -> asyncio.Lock:
        if uid not in self._locks:
            self._locks[uid] = asyncio.Lock()
        return self._locks[uid]

    async def get_or_create(
        self, user_id: str, api_id: Optional[int] = None, api_hash: Optional[str] = None
    ) -> UserTelegram:
        async with self._lock(user_id):
            if user_id in self.users:
                return self.users[user_id]

            doc = await db.telegram_sessions.find_one({"user_id": user_id})
            eff_api_id = api_id
            eff_api_hash = api_hash
            session_str = ""

            if doc:
                if not eff_api_id:
                    eff_api_id = doc.get("api_id")
                if not eff_api_hash and doc.get("api_hash_enc"):
                    eff_api_hash = fernet.decrypt(doc["api_hash_enc"].encode()).decode()
                if doc.get("session_enc"):
                    session_str = fernet.decrypt(doc["session_enc"].encode()).decode()

            if not eff_api_id or not eff_api_hash:
                raise ValueError("API ID / API Hash belum di-set")

            ut = UserTelegram(user_id, int(eff_api_id), eff_api_hash, session_str)
            ut.phone = doc.get("phone") if doc else None
            ut.display_name = doc.get("display_name") if doc else None
            await ut.connect()
            if await ut.is_authorized():
                ut._install_default_handler()
            self.users[user_id] = ut
            return ut

    async def get_meta(self, user_id: str) -> dict:
        doc = await db.telegram_sessions.find_one(
            {"user_id": user_id}, {"_id": 0, "session_enc": 0, "api_hash_enc": 0}
        )
        connected = False
        ut = self.users.get(user_id)
        if ut and ut.client and ut.client.is_connected():
            try:
                connected = await ut.client.is_user_authorized()
            except Exception:
                connected = False
        result = {
            "connected": connected,
            "phone": doc.get("phone") if doc else None,
            "display_name": doc.get("display_name") if doc else None,
            "api_id_set": bool(doc and doc.get("api_id")),
        }
        if doc and doc.get("updated_at"):
            result["updated_at"] = doc["updated_at"]
        return result

    async def logout(self, user_id: str):
        ut = self.users.pop(user_id, None)
        if ut:
            try:
                if ut.client:
                    await ut.client.log_out()
            except Exception:
                pass
            try:
                await ut.disconnect()
            except Exception:
                pass
        await db.telegram_sessions.delete_one({"user_id": user_id})

    async def shutdown(self):
        for ut in list(self.users.values()):
            try:
                await ut.disconnect()
            except Exception:
                pass
        self.users.clear()


telegram_manager = TelegramManager()
