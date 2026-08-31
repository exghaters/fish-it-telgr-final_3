"""Fish It automation state machine (per user) — aligned with real @fish_it_bot flow.

ALGORITHM (VIP direct mode):
  Bot auto-mancing = 5 minutes + 10s gap per session.
  1. Send /mancing ONCE (if session isn't already running)
  2. Wait 10s for bot to start auto-mancing
  3. Wait for "SESI MANCING SELESAI!" message (up to ~6 min)
  4. Scan for gift rarity and rare fish
  5. fish_since_sell += 1
  6. If fish_since_sell >= N (default 3): extract & sell (NEVER while session running)
  7. Wait vip_gap_seconds, then repeat step 1

CHAT FILTER:
  Engine ONLY reads messages from: bot_username, group_username, extra_allowed_chats.
  All other Telegram chats are ignored (no noise in Activity Log, no false
  "SESI SELESAI" from other people's messages in groups).

ANTI-SPAM:
  If bot replies "KAMU SEDANG MANCING! Waktu berjalan: X detik" the engine computes
  remaining session time (duration - X) and WAITS — it never retries immediately.

BOOST (optional):
  If boost_enabled, send /boost when "PERAHU SIAP BERANGKAT" (group) or
  "AUTO MANCING DIMULAI!" (bot) appears. Cooldown = boost_cooldown_seconds (~5 min).

Verification (best-effort):
  Detect "🔒 Verifikasi Diperlukan" → search pinned + last 20 messages for the button →
  click / WebView request via Telethon → wait 30s → if not verified, pause + notify.
"""
from __future__ import annotations

import asyncio
import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Optional

from telethon import events
from telethon.tl.functions.messages import RequestWebViewRequest

from deps import db
from models import AutomationConfig, AutomationState, EventDoc, Notification, utcnow_iso
from telegram_manager import UserTelegram, telegram_manager

log = logging.getLogger("automation_engine")

FISHING_ACTIVE_RX = re.compile(
    r"(KAMU SEDANG MANCING|[Kk]amu sedang memancing|sedang memancing|"
    r"selagi sesi mancing|Tunggu sesi selesai)",
    re.IGNORECASE,
)
ELAPSED_RX = re.compile(r"Waktu berjalan:\s*(\d+)\s*detik", re.IGNORECASE)
NO_EXTRACT_RX = re.compile(r"Tidak ada ikan", re.IGNORECASE)


def _now() -> datetime:
    return datetime.now(timezone.utc)


class AutomationRunner:
    def __init__(self, user_id: str):
        self.user_id = user_id
        self.task: Optional[asyncio.Task] = None
        self.stop_flag = asyncio.Event()
        self.pause_flag = asyncio.Event()
        self.state = AutomationState(user_id=user_id)
        # Tracking
        self._session_gift_detected = False
        self._session_gift_names: list[str] = []
        self._last_verification_at: Optional[datetime] = None
        self._in_verification = False
        self._last_mancing_at: Optional[datetime] = None
        self._session_active = False   # bot's fishing session is running
        self._last_boost_at: Optional[datetime] = None
        self._last_group_boost_at: Optional[datetime] = None
        self._chat_names: dict[int, str] = {}
        self._filter_key: Optional[str] = None
        self._resume_handler = None
        self._group_kickstarted = False
        # Command to re-issue after a verification completes (deeplink /start or /mancing)
        self._pending_after_verify: Optional[tuple] = None
        self._paused_for_verify = False

    def is_running(self) -> bool:
        return self.task is not None and not self.task.done()

    # ---- Public control ----
    async def start(self):
        if self.is_running():
            return
        self.stop_flag.clear()
        self.pause_flag.clear()
        self.state.status = "starting"
        self.state.started_at = utcnow_iso()
        self.state.cycle = 0
        self.state.fish_since_sell = 0
        self.state.last_error = None
        self._last_mancing_at = None
        self._session_active = False
        self._filter_key = None
        self._group_kickstarted = False
        await self._save_state()
        await self._event("start", "info", "Automation dimulai")
        self.task = asyncio.create_task(self._run_forever())
        await self._install_resume_handler()

    async def stop(self):
        self.stop_flag.set()
        self.pause_flag.clear()
        await self._remove_resume_handler()
        if self.task:
            try:
                await asyncio.wait_for(self.task, timeout=5)
            except (Exception, asyncio.CancelledError):
                pass
        self.state.status = "stopped"
        await self._save_state()
        await self._event("stop", "info", "Automation dihentikan")

    async def pause(self, reason: str = ""):
        self.pause_flag.set()
        self.state.status = "paused"
        if reason:
            self.state.last_message = reason
        await self._save_state()
        await self._event("pause", "warn", f"Paused: {reason}" if reason else "Paused")

    async def resume(self):
        self.pause_flag.clear()
        self.state.status = "idle"
        self.state.last_error = None
        self.state.verification_url = None
        self._last_verification_at = None
        self._in_verification = False
        await self._save_state()
        await self._event("resume", "info", "Resumed")

    # ---- Helpers ----
    async def _save_state(self):
        self.state.updated_at = utcnow_iso()
        await db.automation_state.update_one(
            {"user_id": self.user_id},
            {"$set": self.state.model_dump()},
            upsert=True,
        )

    async def _event(self, kind: str, level: str, message: str, meta: dict = None):
        ev = EventDoc(user_id=self.user_id, kind=kind, level=level, message=message,
                      meta=meta or {})
        await db.events.insert_one(ev.model_dump())

    async def _notify(self, kind: str, title: str, body: str = "", action_url: str = None):
        n = Notification(user_id=self.user_id, kind=kind, title=title, body=body,
                         action_url=action_url)
        await db.notifications.insert_one(n.model_dump())

    async def _load_config(self) -> AutomationConfig:
        doc = await db.automation_configs.find_one({"user_id": self.user_id}, {"_id": 0})
        if not doc:
            return AutomationConfig(user_id=self.user_id)
        return AutomationConfig(**doc)

    async def _get_client(self) -> UserTelegram:
        return await telegram_manager.get_or_create(self.user_id)

    async def _wait_for_pause(self):
        while self.pause_flag.is_set() and not self.stop_flag.is_set():
            await asyncio.sleep(0.5)

    def _chat_label(self, chat_id) -> str:
        return self._chat_names.get(chat_id, str(chat_id))

    # ---- Chat filter ----
    async def _apply_chat_filter(self, cfg: AutomationConfig):
        chats = [cfg.bot_username, cfg.group_username]
        chats += (cfg.extra_allowed_chats or "").split(",")
        chats = [c.strip() for c in chats if c and c.strip()]
        key = "|".join(sorted({c.lower() for c in chats}))
        if key == self._filter_key:
            return
        ut = await self._get_client()
        mapping = await ut.set_allowed_chats(chats)
        self._chat_names.update(mapping)
        self._filter_key = key
        names = ", ".join(mapping.values()) or "(kosong)"
        await self._event("info", "info", f"Filter chat aktif — hanya baca: {names}")

    # ---- Boost (DM + group) ----
    async def _maybe_boost(self, cfg: AutomationConfig, item: dict):
        if not cfg.boost_enabled:
            return
        text = item.get("text") or ""
        now = _now()
        cooldown = max(30, int(cfg.boost_cooldown_seconds or 300))
        ut = None
        # DM boost — e.g. "AUTO MANCING DIMULAI!" → /boost ke bot
        if cfg.boost_trigger_pattern and re.search(cfg.boost_trigger_pattern, text, re.IGNORECASE):
            if not (self._last_boost_at and (now - self._last_boost_at).total_seconds() < cooldown):
                dest = cfg.bot_username or self._chat_names.get(item.get("chat_id"))
                if dest:
                    self._last_boost_at = now
                    ut = ut or await self._get_client()
                    try:
                        await ut.send_command(dest, cfg.boost_command)
                        await self._event("message-out", "info",
                                          f"Sent {cfg.boost_command} → {dest} (boost)")
                    except Exception as exc:
                        await self._event("error", "warn", f"Boost gagal: {exc}")
        # Group boost — "Boost Grup Berakhir!"/"PERAHU SIAP BERANGKAT" → /boost_grup ke grup
        if cfg.group_boost_trigger_pattern and re.search(
            cfg.group_boost_trigger_pattern, text, re.IGNORECASE
        ):
            if not (self._last_group_boost_at and
                    (now - self._last_group_boost_at).total_seconds() < cooldown):
                # User wants the boost sent to the configured Fish It BOT (DM),
                # not the group, when "PERAHU SIAP BERANGKAT" appears.
                dest = cfg.bot_username or cfg.group_username
                if dest:
                    self._last_group_boost_at = now
                    ut = ut or await self._get_client()
                    try:
                        await ut.send_command(dest, cfg.boost_command)
                        await self._event("message-out", "info",
                                          f"Sent {cfg.boost_command} → {dest} (boost perahu)")
                    except Exception as exc:
                        await self._event("error", "warn", f"Boost gagal: {exc}")

    def _group_open_command(self, cfg: AutomationConfig) -> str:
        """Build /open_mancing@<bot> using the configured Bot Fish It username."""
        bot = (cfg.bot_username or "@fish_it_vip_bot").strip().lstrip("@")
        return f"/open_mancing@{bot}"

    # ---- Manual verification resume (type keyword in Telegram) ----
    async def _install_resume_handler(self):
        if self._resume_handler is not None:
            return
        try:
            ut = await self._get_client()
        except Exception:
            return
        cfg = await self._load_config()
        keyword = (cfg.resume_keyword or "dvk").strip().lower()
        runner = self

        async def _on_out(event):
            try:
                txt = (event.raw_text or "").strip().lower()
                if keyword and txt == keyword and runner.pause_flag.is_set():
                    await runner._event("resume", "info",
                                        f"Keyword '{keyword}' terdeteksi di Telegram — resume")
                    await runner.resume()
            except Exception:
                pass

        try:
            ut.client.add_event_handler(_on_out, events.NewMessage(outgoing=True))
            self._resume_handler = _on_out
        except Exception:
            self._resume_handler = None

    async def _remove_resume_handler(self):
        if self._resume_handler is None:
            return
        try:
            ut = await self._get_client()
            ut.client.remove_event_handler(self._resume_handler)
        except Exception:
            pass
        self._resume_handler = None

    # ---- Multi-chat event wait (group mode pump) ----
    async def _wait_for_any(self, cfg: AutomationConfig, rules: list,
                            timeout: int) -> Optional[dict]:
        ut = await self._get_client()
        group_id = await ut.resolve_chat_id(cfg.group_username) if cfg.group_username else None
        bot_id = await ut.resolve_chat_id(cfg.bot_username) if cfg.bot_username else None
        # Only these bot chats may trigger verification (avoids scheduled-message /
        # unrelated bots being read as "verifikasi diperlukan").
        allowed_bot_ids = set()
        if bot_id:
            allowed_bot_ids.add(bot_id)
        for _uname in (getattr(cfg, "extra_allowed_chats", None) or []):
            try:
                _cid = await ut.resolve_chat_id(_uname)
                if _cid:
                    allowed_bot_ids.add(_cid)
            except Exception:
                pass
        compiled = [(r["name"], re.compile(r["pattern"], re.IGNORECASE), r.get("chat", "any"))
                    for r in rules if r.get("pattern")]
        deadline = _now() + timedelta(seconds=timeout)
        while _now() < deadline and not self.stop_flag.is_set():
            if self.pause_flag.is_set():
                await self._wait_for_pause()
                await self._resend_pending_after_verify()
                continue
            try:
                item = await asyncio.wait_for(ut.event_queue.get(), timeout=1.0)
            except asyncio.TimeoutError:
                self.state.countdown_seconds = max(0, int((deadline - _now()).total_seconds()))
                await self._save_state()
                continue
            text = (item.get("text") or "").strip()
            chat_id = item.get("chat_id")
            if text:
                await self._event("message-in", "info",
                                  f"[{self._chat_label(chat_id)}] {text[:280]}",
                                  meta={"message_id": item.get("message_id"), "chat_id": chat_id})
            await self._maybe_boost(cfg, item)
            if (
                cfg.verification_pattern
                and isinstance(chat_id, int) and chat_id > 0
                and (not allowed_bot_ids or chat_id in allowed_bot_ids)
                and re.search(cfg.verification_pattern, text, re.IGNORECASE)
                and not self._in_verification
                and not self.pause_flag.is_set()
            ):
                self._in_verification = True
                try:
                    await self._handle_verification(cfg.bot_username or "", item, cfg)
                finally:
                    self._in_verification = False
                continue
            if (
                cfg.registration_success_pattern
                and re.search(cfg.registration_success_pattern, text, re.IGNORECASE)
            ):
                # Already registered → nothing pending to re-issue.
                self._pending_after_verify = None
                self._paused_for_verify = False
            for name, rx, chatsel in compiled:
                if chatsel == "group" and group_id is not None and chat_id != group_id:
                    continue
                if chatsel == "bot" and bot_id is not None and chat_id != bot_id:
                    continue
                if rx.search(text):
                    item["_matched"] = name
                    return item
        return None

    async def _resend_pending_after_verify(self, force: bool = False):
        """Re-issue the join deeplink / mancing command once a verification finished.

        The Fish It bot asks to '/daftar lagi' (or continue with /mancing) after a
        verification, so we replay the exact command that triggered it.
        """
        if self.stop_flag.is_set():
            return
        if not force and not self._paused_for_verify:
            return
        self._paused_for_verify = False
        pend = self._pending_after_verify
        self._pending_after_verify = None
        if not pend:
            return
        chat, command = pend
        try:
            ut = await self._get_client()
            await self._drain_queue()
            await ut.send_command(chat, command)
            await self._event("message-out", "info",
                              f"Verifikasi selesai → lanjut: {command} → {chat}")
        except Exception as exc:
            await self._event("error", "warn", f"Lanjut setelah verifikasi gagal: {exc}")

    async def _drain_queue(self):
        ut = await self._get_client()
        cfg = await self._load_config()
        while True:
            try:
                item = ut.event_queue.get_nowait()
            except asyncio.QueueEmpty:
                break
            try:
                await self._maybe_boost(cfg, item)
            except Exception:
                pass

    # ---- Session time tracking ----
    def _session_duration(self, cfg: AutomationConfig) -> int:
        return cfg.group_fish_seconds if cfg.mode == "group" else cfg.vip_fish_seconds

    def _register_active_session(self, cfg: AutomationConfig, text: str) -> int:
        """Parse 'Waktu berjalan: X detik' and sync session clock. Returns est. remaining s."""
        dur = self._session_duration(cfg)
        m = ELAPSED_RX.search(text)
        elapsed = int(m.group(1)) if m else None
        if elapsed is not None:
            self._last_mancing_at = _now() - timedelta(seconds=elapsed)
        elif not self._last_mancing_at:
            self._last_mancing_at = _now()
        self._session_active = True
        if elapsed is not None:
            return max(dur - elapsed, 30)
        return min(dur, 120)

    def _estimate_remaining(self, cfg: AutomationConfig) -> int:
        if not self._last_mancing_at:
            return 0
        dur = self._session_duration(cfg)
        elapsed = (_now() - self._last_mancing_at).total_seconds()
        return max(0, int(dur - elapsed))

    def _session_likely_running(self, cfg: AutomationConfig) -> bool:
        """True if bot's auto-mancing session is likely still running."""
        if not self._last_mancing_at:
            return False
        dur = self._session_duration(cfg)
        elapsed = (_now() - self._last_mancing_at).total_seconds()
        return elapsed < (dur - 30)

    async def _ensure_no_active_session(self, cfg: AutomationConfig, chat: str) -> bool:
        """HARD GUARD: wait until fishing session finished before extract/sell.

        Returns False if session may still be running → caller must SKIP.
        """
        if not (self._session_active or self._session_likely_running(cfg)):
            return True
        remaining = self._estimate_remaining(cfg)
        await self._event("info", "info",
                          f"Sesi mancing masih aktif (~{remaining}s) — tunggu selesai "
                          "sebelum extract/jual")
        done = await self._wait_for_message(
            chat, patterns=[cfg.session_done_pattern],
            timeout=remaining + 90, extend_on_active=True,
        )
        self._session_active = False
        if done:
            await self._process_session_result(chat, cfg, done)
            return True
        if self._session_likely_running(cfg):
            await self._event("info", "warn",
                              "Sesi belum selesai — extract/jual di-SKIP cycle ini "
                              "(anti-spam)")
            return False
        await self._event("info", "warn",
                          "Sesi tidak terdeteksi selesai — lanjut dengan hati-hati")
        return True

    # ---- Message waiting (chat-scoped) ----
    async def _wait_for_message(
        self,
        chat: str,
        patterns: list[str],
        timeout: int = 30,
        collect_text: bool = True,
        extend_on_active: bool = False,
    ) -> Optional[dict]:
        compiled = [re.compile(p, re.IGNORECASE) for p in patterns if p]
        ut = await self._get_client()
        cfg = await self._load_config()
        target_id = await ut.resolve_chat_id(chat) if chat else None
        deadline = _now() + timedelta(seconds=timeout)
        max_deadline = _now() + timedelta(
            seconds=timeout + self._session_duration(cfg) + 120)
        while _now() < deadline and not self.stop_flag.is_set():
            if self.pause_flag.is_set():
                await self._wait_for_pause()
                await self._resend_pending_after_verify()
                continue
            try:
                item = await asyncio.wait_for(ut.event_queue.get(), timeout=1.0)
            except asyncio.TimeoutError:
                self.state.countdown_seconds = max(
                    0, int((deadline - _now()).total_seconds())
                )
                await self._save_state()
                continue
            text = (item.get("text") or "").strip()
            chat_id = item.get("chat_id")
            from_target = target_id is None or chat_id == target_id
            if collect_text and text:
                await self._event(
                    "message-in", "info",
                    f"[{self._chat_label(chat_id)}] {text[:280]}",
                    meta={"message_id": item.get("message_id"),
                          "chat_id": chat_id,
                          "edited": item.get("type") == "edited"})
            await self._maybe_boost(cfg, item)
            # Verification only triggers from the target Fish It bot DM
            if (
                cfg.verification_pattern
                and isinstance(chat_id, int) and chat_id > 0
                and from_target
                and re.search(cfg.verification_pattern, text, re.IGNORECASE)
                and not self._in_verification
                and not self.pause_flag.is_set()
            ):
                self._in_verification = True
                try:
                    await self._handle_verification(chat, item, cfg)
                finally:
                    self._in_verification = False
                continue
            if not from_target:
                continue
            # "Kamu sedang memancing" → session active, extend by real remaining time
            if extend_on_active and FISHING_ACTIVE_RX.search(text):
                remaining = self._register_active_session(cfg, text)
                new_deadline = _now() + timedelta(seconds=remaining + 30)
                deadline = min(max(deadline, new_deadline), max_deadline)
                await self._event("info", "info",
                                  f"Sesi masih berjalan (~{remaining}s tersisa) — menunggu")
                continue
            for rx in compiled:
                if rx.search(text):
                    return item
        return None

    # ---- Button clicking ----
    async def _click_button_in_message(
        self, chat: str, message_id: int, button_text: str, scan_recent: int = 4
    ) -> bool:
        ut = await self._get_client()
        candidates = []
        try:
            msg = await ut.client.get_messages(chat, ids=message_id)
            if msg:
                candidates.append(msg)
        except Exception as exc:
            await self._event("error", "warn", f"get_messages failed: {exc}")
        if scan_recent:
            try:
                async for m in ut.client.iter_messages(chat, limit=scan_recent):
                    if m.id != message_id:
                        candidates.append(m)
            except Exception:
                pass
        available = []
        for msg in candidates:
            for row in getattr(msg, "buttons", None) or []:
                for btn in row:
                    btext = (getattr(btn, "text", "") or "")
                    available.append(btext)
                    if button_text.lower() in btext.lower():
                        try:
                            await msg.click(text=btext)
                            await self._event("click", "info", f"Clicked '{btext}'")
                            return True
                        except Exception as exc:
                            await self._event("error", "warn",
                                              f"Click '{btext}' failed: {exc}")
                            return False
        await self._event("info", "warn",
                          f"Button '{button_text}' not found. Available: {available[:8]}")
        return False

    async def _click_button_by_emoji(
        self, chat: str, message_id: int, emoji: str
    ) -> bool:
        ut = await self._get_client()
        try:
            msg = await ut.client.get_messages(chat, ids=message_id)
            if not msg:
                return False
            for row in msg.buttons or []:
                for btn in row:
                    btext = getattr(btn, "text", "") or ""
                    if emoji in btext:
                        try:
                            await msg.click(text=btext)
                            await self._event("click", "info", f"Clicked emoji {emoji}")
                            return True
                        except Exception as exc:
                            await self._event("error", "warn",
                                              f"Emoji click failed: {exc}")
                            return False
        except Exception as exc:
            await self._event("error", "warn", f"get_messages failed: {exc}")
        return False

    async def _sleep_seconds(self, seconds: int, status: str = None):
        if status:
            self.state.status = status
            await self._save_state()
        self.state.next_action_at = (_now() + timedelta(seconds=seconds)).isoformat()
        self.state.countdown_seconds = seconds
        await self._save_state()
        end = _now() + timedelta(seconds=seconds)
        while _now() < end and not self.stop_flag.is_set():
            if self.pause_flag.is_set():
                pause_start = _now()
                await self._wait_for_pause()
                end += _now() - pause_start
                continue
            remaining = int((end - _now()).total_seconds())
            self.state.countdown_seconds = max(0, remaining)
            await self._save_state()
            await asyncio.sleep(1)
        self.state.countdown_seconds = 0

    # ---- Main forever loop ----
    async def _run_forever(self):
        try:
            while not self.stop_flag.is_set():
                try:
                    cfg = await self._load_config()
                    if not cfg.enabled:
                        await self.pause("Automation disabled")
                        await asyncio.sleep(3)
                        continue

                    await self._wait_for_pause()
                    if self.stop_flag.is_set():
                        break

                    ut = await self._get_client()
                    if not await ut.is_authorized():
                        await self.pause("Telegram belum login")
                        await asyncio.sleep(5)
                        continue

                    try:
                        await self._apply_chat_filter(cfg)
                    except Exception as exc:
                        await self._event("error", "warn", f"Filter chat gagal: {exc}")

                    self.state.mode = cfg.mode
                    self.state.cycle += 1
                    self.state.last_error = None
                    await self._save_state()

                    if cfg.mode == "group":
                        await self._cycle_group(cfg)
                    else:
                        await self._cycle_vip(cfg)

                    if self.state.fish_since_sell >= cfg.extract_sell_every_n_fish:
                        await self._extract_and_sell(cfg)

                    await self._sleep_seconds(cfg.vip_gap_seconds, "waiting")

                except Exception as exc:
                    log.exception("automation loop error")
                    self.state.status = "error"
                    self.state.last_error = str(exc)[:500]
                    await self._save_state()
                    await self._event("error", "error", f"Loop error: {exc}")
                    await asyncio.sleep(15)
        finally:
            if not self.stop_flag.is_set():
                self.state.status = "stopped"
            await self._save_state()

    # ---- VIP cycle ----
    async def _cycle_vip(self, cfg: AutomationConfig):
        target = cfg.bot_username or cfg.group_username
        if not target:
            await self.pause("Bot username belum diset")
            return

        ut = await self._get_client()
        self._session_gift_detected = False
        self._session_gift_names = []

        # Only send /mancing if not already running
        if not self._session_likely_running(cfg):
            self.state.status = "fishing"
            self.state.last_action_at = utcnow_iso()
            await self._save_state()
            await self._drain_queue()
            await ut.send_command(target, cfg.open_command)
            # Remember so we can re-issue after a verification (bot: "lanjut /mancing")
            self._pending_after_verify = (target, cfg.open_command)
            await self._event("message-out", "info",
                              f"Sent {cfg.open_command}", meta={"chat": target})
            # Quick check: inventory penuh → jual dulu, jangan paksa mancing
            quick = await self._wait_for_message(
                target, patterns=[cfg.inventory_full_pattern], timeout=8)
            if quick:
                await self._event("info", "warn",
                                  "📦 Inventory penuh — extract & jual dulu sebelum lanjut")
                self._last_mancing_at = None
                self._session_active = False
                await self._extract_and_sell(cfg)
                self.state.fish_since_sell = 0
                await self._save_state()
                return
            self._last_mancing_at = _now()
            self._session_active = True
            # short delay before session actually starts
            await asyncio.sleep(5)
        else:
            elapsed = int((_now() - self._last_mancing_at).total_seconds())
            await self._event("info", "info",
                              f"Session masih running (~{elapsed}s) — skip send /mancing")
            self.state.status = "fishing"
            await self._save_state()

        # Wait for SESI MANCING SELESAI
        result_msg = await self._wait_for_message(
            chat=target,
            patterns=[cfg.session_done_pattern],
            timeout=cfg.vip_fish_seconds + 60,
            extend_on_active=True,
        )
        if not result_msg:
            await self._event("info", "warn",
                              "Session done tidak terdeteksi (timeout)")
            # Reset so next cycle will resend /mancing
            self._last_mancing_at = None
            self._session_active = False
            return

        self._session_active = False
        await self._process_session_result(target, cfg, result_msg)

    # ---- Group cycle ----
    async def _join_group_button(self, cfg: AutomationConfig, group: str,
                                 message_id: int) -> Optional[str]:
        """Click 'Daftar Mancing'. Returns 'deeplink' | 'clicked' | None.

        Fish It usually EDITS the "PENDAFTARAN DIBUKA" message to attach the
        join button + live countdown a beat after the text first arrives, so a
        single immediate fetch often sees no button. We poll for up to ~16s,
        re-scanning recent group messages until the button shows up.
        """
        ut = await self._get_client()
        want = (cfg.join_button_text or "").strip().lower()
        for attempt in range(8):
            if self.stop_flag.is_set():
                return None
            candidates = []
            try:
                msg = await ut.client.get_messages(group, ids=message_id)
                if msg:
                    candidates.append(msg)
            except Exception as exc:
                if attempt == 0:
                    await self._event("error", "warn", f"Get pesan pendaftaran gagal: {exc}")
            try:
                async for m in ut.client.iter_messages(group, limit=12):
                    if m and m.id != message_id:
                        candidates.append(m)
            except Exception:
                pass
            for m in candidates:
                if not m or not getattr(m, "buttons", None):
                    continue
                for row in m.buttons:
                    for btn in row:
                        btext = (getattr(btn, "text", "") or "").strip()
                        if want and want not in btext.lower():
                            continue
                        url = getattr(btn, "url", None)
                        if url:
                            dm = re.search(
                                r"t\.me/([A-Za-z0-9_]+)\?start=([\w\-=]+)", url)
                            if not dm:
                                dm = re.search(
                                    r"telegram\.me/([A-Za-z0-9_]+)\?start=([\w\-=]+)", url)
                            if not dm:
                                dm = re.search(
                                    r"tg://resolve\?domain=([A-Za-z0-9_]+)&start=([\w\-=]+)", url)
                            if dm:
                                bot_uname, param = dm.group(1), dm.group(2)
                                await ut.send_command(f"@{bot_uname}", f"/start {param}")
                                self._pending_after_verify = (f"@{bot_uname}", f"/start {param}")
                                await self._event(
                                    "click", "info",
                                    f"Join via deep-link: /start {param} → @{bot_uname}")
                                return "deeplink"
                            await self._event("info", "warn",
                                              f"Tombol join URL tidak dikenali: {url}")
                            continue
                        try:
                            await m.click(text=btext)
                            await self._event("click", "info",
                                              f"Clicked '{btext}' di grup")
                            return "clicked"
                        except Exception as exc:
                            await self._event("error", "warn", f"Klik join gagal: {exc}")
            await asyncio.sleep(2)
        await self._event("info", "warn",
                          f"Tombol '{cfg.join_button_text}' tidak ditemukan "
                          "di pesan pendaftaran (setelah menunggu ~16s)")
        return None

    async def _cycle_group(self, cfg: AutomationConfig):
        """Event-driven group mode.

        - "PENDAFTARAN DIBUKA" (grup)  → langsung klik "Daftar Mancing" (skip /open_mancing)
        - "WAKTU HABIS!"       (grup)  → kirim /open_mancing@<bot> ke grup
        - "SESI MANCING SELESAI" (bot) → hitung 1 sesi (extract/jual diatur loop utama)
        - "Inventory Penuh"      (bot) → extract & jual dulu
        Boost grup (/boost_grup) & DM boost ditangani _maybe_boost.
        """
        group = cfg.group_username
        bot = cfg.bot_username or "@fish_it_bot"
        if not group:
            await self.pause("Group username belum diset")
            return
        ut = await self._get_client()
        open_cmd = self._group_open_command(cfg)

        # Kickstart: on the first cycle after Start, langsung buka pendaftaran
        # (kirim /open_mancing@<bot> ke grup) tanpa menunggu event.
        if not self._group_kickstarted:
            self._group_kickstarted = True
            if not self._session_likely_running(cfg):
                self.state.status = "opening"
                await self._save_state()
                await self._drain_queue()
                try:
                    await ut.send_command(group, open_cmd)
                    await self._event("message-out", "info",
                                      f"START → Sent {open_cmd} → {group}")
                except Exception as exc:
                    await self._event("error", "warn", f"Open mancing gagal: {exc}")

        self.state.status = "waiting"
        await self._save_state()

        rules = [
            {"name": "pendaftaran", "pattern": cfg.pendaftaran_open_pattern, "chat": "group"},
            {"name": "cancelled", "pattern": cfg.pendaftaran_cancelled_pattern, "chat": "group"},
            {"name": "waktu_habis", "pattern": cfg.waktu_habis_pattern, "chat": "group"},
            {"name": "session_done", "pattern": cfg.session_done_pattern, "chat": "bot"},
            {"name": "inventory_full", "pattern": cfg.inventory_full_pattern, "chat": "bot"},
        ]
        ev = await self._wait_for_any(cfg, rules, timeout=cfg.group_fish_seconds + 180)
        if not ev or self.stop_flag.is_set():
            return
        name = ev.get("_matched")

        if name == "pendaftaran":
            self.state.status = "joining"
            await self._save_state()
            method = await self._join_group_button(cfg, group, ev["message_id"])
            if method:
                if method == "clicked" and cfg.dm_confirm_command:
                    try:
                        await ut.send_command(bot, cfg.dm_confirm_command)
                    except Exception:
                        pass
                self._last_mancing_at = _now()
                self._session_active = True
                await self._event("info", "info",
                                  "✅ 'Daftar Mancing' ditekan — menunggu sesi selesai")
            else:
                # Button never appeared/clickable: re-open so we get a fresh
                # PENDAFTARAN with a working button on the next cycle.
                self._session_active = False
                self.state.status = "opening"
                await self._save_state()
                await self._drain_queue()
                try:
                    await ut.send_command(group, open_cmd)
                    await self._event("message-out", "warn",
                                      f"Tombol belum bisa ditekan → buka ulang {open_cmd} → {group}")
                except Exception as exc:
                    await self._event("error", "warn", f"Buka ulang gagal: {exc}")

        elif name == "waktu_habis":
            self.state.status = "opening"
            await self._save_state()
            await self._drain_queue()
            await ut.send_command(group, open_cmd)
            await self._event("message-out", "info",
                              f"WAKTU HABIS → Sent {open_cmd} → {group}")

        elif name == "cancelled":
            # "❌ PENDAFTARAN DIBATALKAN / Tidak ada peserta" → buka ulang otomatis
            self.state.status = "opening"
            await self._save_state()
            await asyncio.sleep(3)  # jeda singkat agar tidak spam
            await self._drain_queue()
            await ut.send_command(group, open_cmd)
            await self._event("message-out", "info",
                              f"PENDAFTARAN DIBATALKAN → buka ulang {open_cmd} → {group}")

        elif name == "session_done":
            self._session_active = False
            await self._process_session_result(bot, cfg, ev)

        elif name == "inventory_full":
            await self._event("info", "warn",
                              "📦 Inventory penuh — extract & jual dulu")
            await self._extract_and_sell(cfg)
            self.state.fish_since_sell = 0
            await self._save_state()

    async def _process_session_result(self, chat: str, cfg: AutomationConfig, result_msg: dict):
        text = result_msg.get("text", "") or ""
        await self._scan_recent_for_gift(chat, cfg)
        if cfg.rare_pattern:
            rares = re.findall(cfg.rare_pattern, text, flags=re.IGNORECASE)
            if rares:
                await self._event("rare", "info", f"Rare: {', '.join(set(rares))}")
        self.state.fish_caught += 1
        self.state.fish_since_sell += 1
        await self._event("fish-caught", "success", "Session mancing selesai",
                          meta={"fish_since_sell": self.state.fish_since_sell})
        await self._save_state()

    async def _scan_recent_for_gift(self, chat: str, cfg: AutomationConfig, limit: int = 15):
        ut = await self._get_client()
        try:
            msgs = await ut.get_last_messages(chat, limit=limit)
        except Exception:
            return
        rx = re.compile(cfg.gift_message_pattern or cfg.gift_rarity_pattern,
                        re.IGNORECASE)
        for m in msgs:
            text = m.get("text", "") or ""
            match = rx.search(text)
            if match:
                rarity = match.group(1) if match.groups() else match.group(0)
                if rarity.upper() not in [g.upper() for g in self._session_gift_names]:
                    self._session_gift_detected = True
                    self._session_gift_names.append(rarity.upper())
                    lines = text.splitlines()
                    fish_name = ""
                    for i, ln in enumerate(lines):
                        if rx.search(ln) and i + 1 < len(lines):
                            fish_name = re.sub(r"[^\w\s\u00C0-\u017F\-]", "",
                                               lines[i + 1]).strip()[:80]
                            break
                    await self._event("gift", "success",
                                      f"✨ {rarity} ✨ {fish_name}".strip())
                    await self._notify(
                        "gift",
                        f"Ikan {rarity} didapat!",
                        (fish_name or text[:300]),
                    )

    # ---- Rare-fish protection (favorite before /jual semua) ----
    def _find_fish_to_favorite(self, text: str, cfg: AutomationConfig) -> list[int]:
        """Return inventory positions to favorite: rare rarity OR coins >= min."""
        rare_rx = re.compile(cfg.protect_rarity_pattern, re.IGNORECASE)
        coins_rx = re.compile(r"([\d.,]+)\s*coins", re.IGNORECASE)
        min_coins = int(cfg.protect_min_coins or 0)
        lines = text.splitlines()
        blocks: list[tuple[int, str]] = []
        cur_num: Optional[int] = None
        cur: list[str] = []
        for line in lines:
            m = re.match(r"\s*(\d+)[\.\)]\s+", line)
            if m:
                if cur_num is not None:
                    blocks.append((cur_num, " ".join(cur)))
                cur_num = int(m.group(1))
                cur = [line]
            elif cur_num is not None:
                cur.append(line)
        if cur_num is not None:
            blocks.append((cur_num, " ".join(cur)))
        result: list[int] = []
        for num, btext in blocks:
            is_rare = bool(rare_rx.search(btext))
            coins = 0
            cm = coins_rx.search(btext)
            if cm:
                digits = re.sub(r"[^\d]", "", cm.group(1))
                coins = int(digits) if digits else 0
            if is_rare or (min_coins and coins >= min_coins):
                result.append(num)
        return sorted(set(result))

    async def _protect_rare_fish(self, cfg: AutomationConfig, chat: str) -> int:
        """Do /inventory, scan pages, favorite rare/valuable fish so they aren't sold."""
        ut = await self._get_client()
        self.state.status = "inventory"
        await self._save_state()
        await self._drain_queue()
        await ut.send_command(chat, cfg.inventory_command)
        await self._event("message-out", "info",
                          f"Sent {cfg.inventory_command} (cek ikan langka sebelum jual)")

        summary_rx = (re.compile(cfg.rarity_summary_pattern, re.IGNORECASE)
                      if cfg.rarity_summary_pattern else None)
        rare_rx = re.compile(cfg.protect_rarity_pattern, re.IGNORECASE)
        inv_pat = r"Halaman:?\s*\d+|Slot terisi|Total (Nilai )?Inventory|Rarity:|Inventory\s+\w+"
        positions: list[int] = []
        seen: set[int] = set()
        max_pages = int(cfg.inventory_max_pages or 11)
        first = True
        for _ in range(max_pages):
            if self.stop_flag.is_set():
                break
            inv_msg = await self._wait_for_message(chat, patterns=[inv_pat], timeout=15)
            if not inv_msg:
                break
            text = inv_msg.get("text", "") or ""
            pm = re.search(r"Halaman:?\s*(\d+)\s*/\s*(\d+)", text)
            cur = int(pm.group(1)) if pm else None
            total = int(pm.group(2)) if pm else max_pages
            if first:
                first = False
                has_rare = (bool(summary_rx.search(text)) if summary_rx else True) \
                    or bool(rare_rx.search(text))
                if summary_rx and not has_rare and int(cfg.protect_min_coins or 0) <= 0:
                    await self._event("info", "info",
                                      "Tidak ada ikan langka (✨/🌟/☀️) — lanjut jual")
                    return 0
            if cur in seen:
                break
            if cur:
                seen.add(cur)
            # Kumpulkan dulu posisi ikan langka di halaman ini (jangan kirim /favorite dulu)
            found = self._find_fish_to_favorite(text, cfg)
            if found:
                positions.extend(found)
                await self._event("info", "info",
                                  f"Ikan langka/berharga di halaman {cur or '?'}: "
                                  + ", ".join("#" + str(n) for n in found))
            if cur and total and cur >= total:
                break
            clicked = await self._click_button_in_message(
                chat, inv_msg["message_id"], cfg.inventory_next_button_text)
            if not clicked:
                break
            await asyncio.sleep(1.5)

        positions = sorted(set(positions))
        if not positions:
            return 0
        # Setelah SEMUA halaman discan, kirim /favorite dengan SEMUA nomor sekaligus,
        # mis "/favorite 5 56 110" (di-chunk 20 nomor per perintah biar aman).
        chunk = 20
        for i in range(0, len(positions), chunk):
            group = positions[i:i + chunk]
            cmd = cfg.favorite_command_template.replace(
                "{n}", " ".join(str(n) for n in group))
            await ut.send_command(chat, cmd)
            await self._event("favorite", "success",
                              f"⭐ Sent {cmd} ({len(group)} ikan langka)")
            await asyncio.sleep(1.5)
        await self._event("info", "success",
                          f"Proteksi selesai — {len(positions)} ikan langka difavoritkan "
                          "sebelum /jual semua")
        await self._notify("gift", "Ikan langka dilindungi",
                           f"{len(positions)} ikan difavoritkan: "
                           + ", ".join("#" + str(n) for n in positions[:30]))
        return len(positions)

    # ---- Extract & Sell ----
    async def _extract_and_sell(self, cfg: AutomationConfig):
        chat = cfg.bot_username or cfg.group_username
        if not chat:
            return
        ut = await self._get_client()

        # HARD GUARD: never extract/sell while a fishing session is still running
        session_clear = await self._ensure_no_active_session(cfg, chat)
        if not session_clear or self.stop_flag.is_set():
            return

        # STEP 1: proteksi ikan langka DULU — /inventory lalu /favorite semua nomor sekaligus
        try:
            await self._protect_rare_fish(cfg, chat)
        except Exception as exc:
            await self._event("error", "warn", f"Proteksi ikan langka gagal: {exc}")

        # --- STEP 2: Extract flow (retry once if bot says still fishing) ---
        self.state.status = "extracting"
        await self._save_state()
        for attempt in range(2):
            await self._drain_queue()
            await ut.send_command(chat, cfg.extract_command)
            await self._event("message-out", "info", f"Sent {cfg.extract_command}")

            resp = await self._wait_for_message(
                chat,
                patterns=[r"EXTRACT.*MATERIALS|Punyamu|Tidak ada ikan|"
                          r"KAMU SEDANG MANCING|sedang memancing"],
                timeout=15,
            )
            if not resp:
                await self._event("info", "warn", "Extract: respon bot tidak muncul")
                break
            rtext = resp.get("text", "") or ""
            if NO_EXTRACT_RX.search(rtext):
                await self._event("info", "info",
                                  "Tidak ada artefak untuk di-extract — skip extract")
                break
            if FISHING_ACTIVE_RX.search(rtext):
                if attempt >= 1:
                    await self._event("info", "warn",
                                      "Extract ditolak 2x (sedang mancing) — skip")
                    break
                remaining = self._register_active_session(cfg, rtext)
                await self._event("info", "info",
                                  f"Extract ditolak — sesi masih jalan (~{remaining}s). "
                                  "TUNGGU, tidak retry langsung")
                await self._sleep_seconds(remaining + 15, "waiting")
                if self.stop_flag.is_set():
                    return
                done = await self._wait_for_message(
                    chat, patterns=[cfg.session_done_pattern], timeout=90,
                    extend_on_active=True)
                self._session_active = False
                if done:
                    await self._process_session_result(chat, cfg, done)
                continue

            # Materials message → click Inventory
            clicked = await self._click_button_in_message(
                chat, resp["message_id"], cfg.extract_inventory_button_text
            )
            if not clicked:
                await self._event("info", "warn",
                                  f"Button '{cfg.extract_inventory_button_text}' "
                                  "tidak ditemukan")
                break
            list_msg = await self._wait_for_message(
                chat,
                patterns=[cfg.extract_list_pattern or r"Bisa di-extract",
                          r"Tidak ada ikan"],
                timeout=15,
            )
            if list_msg and NO_EXTRACT_RX.search(list_msg.get("text", "") or ""):
                await self._event("info", "info", "Inventory extract kosong — skip")
                break
            target_msg_id = list_msg["message_id"] if list_msg else None
            if not target_msg_id:
                try:
                    recent = await ut.get_last_messages(chat, limit=3)
                    for m in recent:
                        for b in m.get("buttons", []):
                            if cfg.extract_all_button_emoji in (b.get("text") or ""):
                                target_msg_id = m["id"]
                                break
                        if target_msg_id:
                            break
                except Exception:
                    pass
            if not target_msg_id:
                await self._event("info", "warn", "Extract list tidak muncul")
                break
            ok = await self._click_button_by_emoji(
                chat, target_msg_id, cfg.extract_all_button_emoji
            )
            if not ok:
                await self._event("info", "warn", "Tombol 🟢 tidak ditemukan")
                break
            # "⚠ KONFIRMASI — 🟢 SEMUA ARTEFAK" → klik "✅ Ya, extract N ikan"
            confirm = await self._wait_for_message(
                chat,
                patterns=[r"KONFIRMASI.*ARTEFAK|SEMUA \d+ ikan itu HILANG"],
                timeout=10,
            )
            if confirm:
                await self._click_button_in_message(
                    chat, confirm["message_id"], "Ya"
                )
            await self._wait_for_message(
                chat, patterns=[cfg.extract_success_pattern], timeout=20
            )
            await self._event("extract", "success", "Extract berhasil")
            break

        # --- STEP 3: Sell flow — /jual semua (proteksi sudah di STEP 1) ---
        await self._do_sell(cfg, chat, protected=True)
        self.state.fish_since_sell = 0
        await self._save_state()

    async def _do_sell(self, cfg: AutomationConfig, chat: str,
                       retry_after_favorite: bool = False, mancing_retry: int = 0,
                       protected: bool = False):
        ut = await self._get_client()
        # ALWAYS /inventory & protect rare/valuable fish BEFORE /jual semua
        if not protected and not retry_after_favorite:
            try:
                await self._protect_rare_fish(cfg, chat)
            except Exception as exc:
                await self._event("error", "warn", f"Proteksi ikan langka gagal: {exc}")
            protected = True
        self.state.status = "selling"
        await self._save_state()
        await self._drain_queue()
        await ut.send_command(chat, cfg.sell_command)
        await self._event("message-out", "info", f"Sent {cfg.sell_command}")

        # Wait for either KONFIRMASI PENJUALAN or "KAMU SEDANG MANCING"
        resp = await self._wait_for_message(
            chat,
            patterns=[cfg.sell_confirm_pattern,
                      r"KAMU SEDANG MANCING|selagi sesi mancing|Tunggu sesi selesai"],
            timeout=15,
        )
        if not resp:
            await self._event("info", "warn", "Konfirmasi penjualan tidak muncul")
            return
        text = resp.get("text", "") or ""

        is_confirm = bool(re.search(cfg.sell_confirm_pattern, text, re.IGNORECASE))
        if not is_confirm and FISHING_ACTIVE_RX.search(text):
            if mancing_retry >= 2:
                await self._event("info", "warn",
                                  "Jual ditolak berkali-kali — skip cycle ini")
                return
            remaining = self._register_active_session(cfg, text)
            await self._event("info", "info",
                              f"Jual ditolak (sesi masih jalan, sisa ~{remaining}s). "
                              "TUNGGU sampai selesai — tidak retry langsung")
            await self._sleep_seconds(remaining + 15, "waiting")
            if self.stop_flag.is_set():
                return
            done = await self._wait_for_message(
                chat, patterns=[cfg.session_done_pattern], timeout=90,
                extend_on_active=True)
            self._session_active = False
            if done:
                await self._process_session_result(chat, cfg, done)
            await self._do_sell(cfg, chat, retry_after_favorite, mancing_retry + 1,
                                protected=protected)
            return

        if not is_confirm:
            await self._event("info", "warn", "Konfirmasi penjualan tidak muncul")
            return

        confirm_msg = resp
        has_gift = bool(cfg.gift_rarity_pattern and re.search(
            cfg.gift_rarity_pattern, text, re.IGNORECASE
        ))
        if has_gift and not retry_after_favorite:
            await self._event("gift", "warn",
                              "Gift terdeteksi di konfirmasi jual — batalkan & favoritkan")
            await self._notify("gift", "Gift di konfirmasi jual",
                               "Membatalkan penjualan & memfavoritkan dulu.")
            await self._click_button_in_message(
                chat, confirm_msg["message_id"], cfg.sell_cancel_button_text
            )
            gifts = re.findall(cfg.gift_rarity_pattern, text, flags=re.IGNORECASE)
            await self._inventory_favorite(cfg, chat, list(set(gifts)))
            await self._do_sell(cfg, chat, retry_after_favorite=True)
            return

        ok = await self._click_button_in_message(
            chat, confirm_msg["message_id"], cfg.sell_confirm_button_text
        )
        if ok:
            await self._event("sell", "success", "Jual semua dikonfirmasi")
        else:
            await self._event("info", "warn",
                              f"Tombol '{cfg.sell_confirm_button_text}' tidak ditemukan")

    # ---- Inventory favorite ----
    async def _inventory_favorite(
        self, cfg: AutomationConfig, chat: str, keywords: list[str]
    ):
        if not keywords:
            return
        ut = await self._get_client()
        self.state.status = "inventory"
        await self._save_state()
        await self._drain_queue()
        await ut.send_command(chat, cfg.inventory_command)
        await self._event("message-out", "info", f"Sent {cfg.inventory_command}")

        page = 1
        max_pages = 30
        favorited_any = False
        rarity_rx = re.compile("(" + "|".join(re.escape(k) for k in keywords) + ")",
                               re.IGNORECASE)

        while page <= max_pages and not self.stop_flag.is_set():
            inv_msg = await self._wait_for_message(
                chat, patterns=[r"Halaman:?\s*\d+|Inventory\s+\w+"], timeout=15
            )
            if not inv_msg:
                break
            text = inv_msg.get("text", "") or ""
            lines = text.splitlines()
            positions_to_favorite = []
            current_num = None
            for line in lines:
                num_match = re.match(r"\s*(\d+)[\.\)]\s+", line)
                if num_match:
                    current_num = int(num_match.group(1))
                if current_num is not None and rarity_rx.search(line):
                    positions_to_favorite.append(current_num)
                    current_num = None

            positions_to_favorite = sorted(set(positions_to_favorite))
            for pos in positions_to_favorite:
                cmd = cfg.favorite_command_template.replace("{n}", str(pos))
                await ut.send_command(chat, cmd)
                await self._event("favorite", "success",
                                  f"Sent {cmd} (page {page})")
                favorited_any = True
                await asyncio.sleep(1)

            if favorited_any:
                break
            clicked = await self._click_button_in_message(
                chat, inv_msg["message_id"], cfg.inventory_next_button_text
            )
            if not clicked:
                break
            page += 1
            await asyncio.sleep(1)

        if not favorited_any:
            await self._event("info", "warn",
                              f"Gift tidak ditemukan di /inventory: {', '.join(keywords)}")
        self.state.status = "fishing"
        await self._save_state()

    # ---- Verification (best-effort Mini App auto-verify) ----
    async def _handle_verification(self, chat: str, item: dict, cfg: AutomationConfig):
        """Best-effort auto-verify via button click / WebView request.

        Searches PINNED message + last 20 messages for the verification button.
        If Cloudflare needs real interaction (checkbox/puzzle) → pause + notify.
        """
        now_dt = _now()
        if self._last_verification_at and (
            now_dt - self._last_verification_at
        ).total_seconds() < 60:
            return
        self._last_verification_at = now_dt

        self.state.status = "verifying"
        await self._save_state()
        await self._event("verification", "warn", "🔒 Verifikasi Diperlukan terdeteksi")

        # Plan gating: only Pro/Elite get best-effort auto-verify; lower plans = manual only
        try:
            from deps import plan_limits
            uid = self.user_id.split(":", 1)[0]
            udoc = await db.users.find_one({"id": uid}, {"_id": 0, "plan": 1})
            auto_ok = plan_limits((udoc or {}).get("plan", "free"))["auto_verify"]
        except Exception:
            auto_ok = False  # fail-safe: on error require manual verify
        if not auto_ok:
            await self._notify(
                "verification", "🔒 Verifikasi Manual (paket Starter)",
                f"Paket kamu memakai verifikasi manual. Selesaikan verifikasi di Telegram, "
                f"lalu ketik '{cfg.resume_keyword}' di chat bot (atau Resume di dashboard).")
            self._paused_for_verify = True
            await self.pause(
                f"Verifikasi manual — ketik '{cfg.resume_keyword}' di bot / Resume")
            return

        ut = await self._get_client()
        url: Optional[str] = None
        webview_invoked = False

        # Collect candidates: pinned message first, then last 20 messages
        candidates = []
        try:
            from telethon.tl.types import InputMessagePinned
            pinned = await ut.client.get_messages(chat, ids=InputMessagePinned())
            if pinned:
                candidates.append(pinned)
        except Exception:
            pass
        try:
            async for m in ut.client.iter_messages(chat, limit=20):
                candidates.append(m)
        except Exception as exc:
            await self._event("error", "warn", f"Verify inspect: {exc}")

        try:
            done_outer = False
            for msg_obj in candidates:
                if done_outer:
                    break
                if not msg_obj or not getattr(msg_obj, "buttons", None):
                    continue
                for row in msg_obj.buttons:
                    if done_outer:
                        break
                    for btn in row:
                        btext = getattr(btn, "text", "") or ""
                        if cfg.verification_button_text.lower() not in btext.lower():
                            continue
                        try:
                            result = await btn.click()
                            webview_invoked = True
                            await self._event("click", "info",
                                              f"Tombol verifikasi ditekan: '{btext}'")
                            if hasattr(result, "url") and result.url:
                                url = result.url
                        except Exception as exc:
                            from telethon.tl.types import (
                                KeyboardButtonSimpleWebView, KeyboardButtonWebView,
                            )
                            if isinstance(btn, (KeyboardButtonWebView,
                                                KeyboardButtonSimpleWebView)):
                                try:
                                    r = await ut.client(RequestWebViewRequest(
                                        peer=await ut.client.get_input_entity(chat),
                                        bot=await ut.client.get_input_entity(chat),
                                        platform="android",
                                        url=btn.url,
                                    ))
                                    url = getattr(r, "url", btn.url)
                                    webview_invoked = True
                                    await self._event("click", "info",
                                                      "WebView request sent")
                                except Exception as inner:
                                    await self._event("error", "warn",
                                                      f"WebView invoke failed: {inner}")
                                    url = url or getattr(btn, "url", None)
                            elif getattr(btn, "url", None):
                                url = btn.url
                                await self._event("info", "info",
                                                  f"Tombol verifikasi = URL: {url}")
                            else:
                                await self._event("error", "warn",
                                                  f"Verify click err: {exc}")
                        done_outer = True
                        break
        except Exception as exc:
            await self._event("error", "warn", f"Verify flow error: {exc}")

        self.state.verification_url = url
        await self._save_state()

        if webview_invoked:
            # Wait up to 30s for auto-verify — success = new SESI SELESAI or explicit ok
            success = await self._wait_for_message(
                chat=chat,
                patterns=[cfg.session_done_pattern +
                          r"|berhasil|sukses|verified|terverifikasi|terdaftar|AUTO MANCING"],
                timeout=30,
                collect_text=False,
            )
            if success:
                await self._event("verification", "success",
                                  "Verifikasi bypass otomatis berhasil")
                self.state.verification_url = None
                self._last_verification_at = None
                await self._save_state()
                # Continue the flow the bot asked for ("/daftar lagi" or "/mancing")
                await self._resend_pending_after_verify(force=True)
                return

        body = (
            "Automation sudah mencoba pencet tombol verifikasi otomatis, tapi belum "
            "berhasil. Buka Mini App di Telegram, selesaikan Cloudflare, lalu ketik "
            f"'{cfg.resume_keyword}' di chat bot (atau klik Resume di dashboard) untuk lanjut."
        )
        if not url:
            body = (
                f"Buka chat {chat} di Telegram, klik '{cfg.verification_button_text}' "
                f"manual, selesaikan, lalu ketik '{cfg.resume_keyword}' di chat bot "
                "(atau Resume di dashboard)."
            )
        await self._notify("verification", "🔒 Verifikasi Diperlukan", body,
                           action_url=url)
        self._paused_for_verify = True
        await self.pause(
            f"Verifikasi manual — selesaikan lalu ketik '{cfg.resume_keyword}' di bot / Resume")


class AutomationEngine:
    def __init__(self):
        self.runners: dict[str, AutomationRunner] = {}

    def get(self, user_id: str) -> AutomationRunner:
        if user_id not in self.runners:
            self.runners[user_id] = AutomationRunner(user_id)
        return self.runners[user_id]

    async def start(self, user_id: str):
        await self.get(user_id).start()

    async def stop(self, user_id: str):
        if user_id in self.runners:
            await self.runners[user_id].stop()

    async def pause(self, user_id: str, reason: str = ""):
        if user_id in self.runners:
            await self.runners[user_id].pause(reason)

    async def resume(self, user_id: str):
        if user_id in self.runners:
            await self.runners[user_id].resume()

    async def shutdown(self):
        for r in list(self.runners.values()):
            try:
                await r.stop()
            except Exception:
                pass


automation_engine = AutomationEngine()
