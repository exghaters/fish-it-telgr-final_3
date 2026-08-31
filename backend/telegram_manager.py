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
import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from telethon import TelegramClient, events
from telethon.errors import SessionPasswordNeededError
from telethon.sessions import StringSession

from deps import db, fernet
from models import utcnow_iso

log = logging.getLogger("telegram_manager")

# --- Cross-process session ownership lease ---------------------------------
# Each backend process gets a unique instance id. A Telegram session (identified
# by its composite key user_id:account_id) may only be held live by ONE process
# at a time. This prevents the same auth key being connected from two IPs
# simultaneously (Telegram error: "authorization key was used under two
# different IP addresses simultaneously" / AUTH_KEY_DUPLICATED) when the app is
# scaled to multiple uvicorn workers/containers or during hot-reload overlap.
INSTANCE_ID = f"{os.getpid()}-{uuid.uuid4().hex[:8]}"
LEASE_TTL_SECONDS = 60          # a lease is stale (take-over allowed) after this
LEASE_HEARTBEAT_SECONDS = 20    # refresh interval while a client is live


class SessionLeaseUnavailable(RuntimeError):
    """Raised when another live process/worker owns this Telegram session."""


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
        self.allowed_chat_ids: set[int] = set()
        self._chat_id_cache: dict[str, int] = {}
        self._entity_cache: dict = {}

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
                "authorized": True,
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
                if self.allowed_chat_ids and event.chat_id not in self.allowed_chat_ids:
                    return
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

        client.add_event_handler(on_message, events.NewMessage(incoming=True))

        # Also listen for edits so button/state changes on same message reach us.
        async def on_edited(event):
            try:
                if self.allowed_chat_ids and event.chat_id not in self.allowed_chat_ids:
                    return
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

        client.add_event_handler(on_edited, events.MessageEdited(incoming=True))
        self._handler_installed = True

    async def _resolve_entity(self, chat):
        """Resolve @username / id / title to an entity, with dialog-cache fallback.

        Fixes 'The key is not registered in the system' (ResolveUsernameRequest) by
        falling back to the account's cached dialogs when direct resolve fails.
        """
        key = str(chat or "").strip().lower()
        if not key:
            return None
        if key in self._entity_cache:
            return self._entity_cache[key]
        await self.connect()
        raw = str(chat).strip()
        target = int(raw) if raw.lstrip("-").isdigit() else raw
        ent = None
        try:
            ent = await self.client.get_entity(target)
        except Exception:
            ent = None
        if ent is None:
            want = raw.lstrip("@").lower()
            want_id = int(raw) if raw.lstrip("-").isdigit() else None
            try:
                async for d in self.client.iter_dialogs():
                    e = d.entity
                    uname = (getattr(e, "username", "") or "").lower()
                    if want and uname == want:
                        ent = e
                        break
                    if want_id is not None:
                        try:
                            if await self.client.get_peer_id(e) == want_id:
                                ent = e
                                break
                        except Exception:
                            pass
            except Exception as exc:
                log.warning("dialog resolve %s failed: %s", chat, exc)
        if ent is not None:
            self._entity_cache[key] = ent
        return ent

    async def resolve_chat_id(self, chat) -> Optional[int]:
        """Resolve @username / id string to marked chat_id (cached)."""
        key = str(chat or "").strip().lower()
        if not key:
            return None
        if key in self._chat_id_cache:
            return self._chat_id_cache[key]
        ent = await self._resolve_entity(chat)
        if ent is None:
            log.warning("resolve_chat_id %s failed (not resolvable)", chat)
            return None
        try:
            cid = await self.client.get_peer_id(ent)
        except Exception as exc:
            log.warning("get_peer_id %s failed: %s", chat, exc)
            return None
        self._chat_id_cache[key] = cid
        return cid

    async def set_allowed_chats(self, chats: list) -> dict:
        """Whitelist chats for the event handlers. Returns {chat_id: name}."""
        mapping: dict[int, str] = {}
        for c in chats:
            cid = await self.resolve_chat_id(c)
            if cid is not None:
                mapping[cid] = str(c).strip()
        self.allowed_chat_ids = set(mapping.keys())
        return mapping

    async def send_command(self, chat: str, text: str):
        await self.connect()
        async with self.lock:
            dest = await self._resolve_entity(chat)
            msg = await self.client.send_message(dest or chat, text)
            return msg

    async def get_last_messages(self, chat: str, limit: int = 5):
        await self.connect()
        entity = await self._resolve_entity(chat)
        if entity is None:
            raise ValueError(f"Chat not found: {chat}")
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
    """Global registry of per-user Telethon clients (one live client per akey).

    A MongoDB lease (telegram_locks) guarantees that across multiple processes /
    uvicorn workers / containers only ONE process ever holds a live client for a
    given session key at a time.
    """

    def __init__(self):
        self.users: dict[str, UserTelegram] = {}
        self._locks: dict[str, asyncio.Lock] = {}
        self._heartbeat_task: Optional[asyncio.Task] = None

    def _lock(self, uid: str) -> asyncio.Lock:
        if uid not in self._locks:
            self._locks[uid] = asyncio.Lock()
        return self._locks[uid]

    # ---- Cross-process ownership lease ----
    async def _acquire_lease(self, akey: str) -> bool:
        """Atomically claim (or refresh) ownership of a session key.

        Succeeds if: no lease exists, WE already own it, or the current lease is
        stale (owner process died without releasing). Fails if another process
        holds a fresh lease.
        """
        now = datetime.now(timezone.utc)
        stale_before = (now - timedelta(seconds=LEASE_TTL_SECONDS)).isoformat()
        now_iso = now.isoformat()
        res = await db.telegram_locks.find_one_and_update(
            {"_id": akey,
             "$or": [{"owner": INSTANCE_ID}, {"heartbeat": {"$lt": stale_before}}]},
            {"$set": {"owner": INSTANCE_ID, "heartbeat": now_iso}},
        )
        if res is not None:
            return True
        # No matching doc: either it doesn't exist (we can insert) or a live
        # foreign owner holds it (insert will collide on the unique _id).
        try:
            await db.telegram_locks.insert_one(
                {"_id": akey, "owner": INSTANCE_ID, "heartbeat": now_iso})
            return True
        except Exception:
            return False

    async def _refresh_lease(self, akey: str):
        await db.telegram_locks.update_one(
            {"_id": akey, "owner": INSTANCE_ID},
            {"$set": {"heartbeat": datetime.now(timezone.utc).isoformat()}})

    async def _release_lease(self, akey: str):
        try:
            await db.telegram_locks.delete_one({"_id": akey, "owner": INSTANCE_ID})
        except Exception:
            pass

    async def _heartbeat_loop(self):
        while True:
            try:
                await asyncio.sleep(LEASE_HEARTBEAT_SECONDS)
                for akey, ut in list(self.users.items()):
                    if ut.client and ut.client.is_connected():
                        await self._refresh_lease(akey)
            except asyncio.CancelledError:
                break
            except Exception as exc:
                log.warning("lease heartbeat error: %s", exc)

    def start_heartbeat(self):
        if self._heartbeat_task is None or self._heartbeat_task.done():
            self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())

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

            # Claim exclusive ownership BEFORE opening any MTProto connection so
            # the same auth key can never be live in two processes at once.
            if not await self._acquire_lease(user_id):
                raise SessionLeaseUnavailable(
                    "Sesi Telegram ini sedang aktif di proses/perangkat lain. "
                    "Tunggu beberapa detik lalu coba lagi.")

            ut = UserTelegram(user_id, int(eff_api_id), eff_api_hash, session_str)
            ut.phone = doc.get("phone") if doc else None
            ut.display_name = doc.get("display_name") if doc else None
            authed = False
            try:
                await ut.connect()
                authed = await ut.is_authorized()
                if authed:
                    ut._install_default_handler()
            except Exception:
                await self._release_lease(user_id)
                raise
            self.users[user_id] = ut
            self.start_heartbeat()
            # Keep the persisted status flag in sync so /status is stable and
            # consistent across workers (and self-corrects if Telegram revoked
            # the session server-side).
            try:
                await db.telegram_sessions.update_one(
                    {"user_id": user_id}, {"$set": {"authorized": bool(authed)}})
            except Exception:
                pass
            return ut

    async def get_meta(self, user_id: str, rehydrate: bool = False) -> dict:
        doc = await db.telegram_sessions.find_one(
            {"user_id": user_id}, {"_id": 0, "api_hash_enc": 0}
        )
        # Status must NOT depend on holding a live client. On a multi-worker /
        # multi-replica deployment only ONE worker owns the live session, so
        # rehydrating a client here would (a) make status flip between
        # connected/not-connected depending on which worker answers, and (b) risk
        # a duplicate session ("authorization key used under two IPs"). We report
        # authorization from a persisted flag; if THIS worker happens to hold a
        # live authorized client we trust that. The flag self-corrects whenever a
        # worker actually connects the client (login / automation start).
        has_session = bool(doc and doc.get("session_enc"))
        authorized_flag = doc.get("authorized") if doc else None
        if authorized_flag is None:
            connected = has_session  # legacy sessions: a stored session == logged in
        else:
            connected = bool(authorized_flag)
        ut = self.users.get(user_id)
        if ut and ut.client and ut.client.is_connected():
            try:
                connected = await ut.client.is_user_authorized()
            except Exception:
                pass
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
        await self._release_lease(user_id)
        await db.telegram_sessions.delete_one({"user_id": user_id})

    async def shutdown(self):
        if self._heartbeat_task and not self._heartbeat_task.done():
            self._heartbeat_task.cancel()
        for akey, ut in list(self.users.items()):
            try:
                await ut.disconnect()
            except Exception:
                pass
            await self._release_lease(akey)
        self.users.clear()


telegram_manager = TelegramManager()
