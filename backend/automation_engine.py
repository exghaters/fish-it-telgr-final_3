"""Fish It automation state machine (per user) — aligned with real @fish_it_bot flow.

Flow (VIP direct mode, i.e., DM ke @fish_it_bot):
  1. Send /mancing
  2. Wait for "SESI MANCING SELESAI!" message (up to vip_fish_seconds + buffer)
     - Parse result for gift rarity (SECRET / SECRET SHINY / CELESTIAL) and rare fish
     - Notify + log
  3. fish_since_sell += 1
  4. If fish_since_sell >= extract_sell_every_n_fish (default 3):
        a. If gift was detected this session: run inventory-favorite flow first
        b. Send /extract → click "Inventory" button → click green circle → wait EXTRACT BERHASIL
        c. Send /jual semua → wait KONFIRMASI → check rarity again
           - if gift in confirmation → click Batal → inventory-favorite → retry /jual semua
           - else → click "Ya, Jual Semua"
        d. Reset fish_since_sell
  5. Wait vip_gap_seconds, repeat

Flow (group mode):
  Similar but with extra Gabung click step + group_wait_seconds after join.

Verification detection is monitored continuously between steps.
"""
from __future__ import annotations

import asyncio
import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Optional

from deps import db
from models import AutomationConfig, AutomationState, EventDoc, Notification, utcnow_iso
from telegram_manager import UserTelegram, telegram_manager

log = logging.getLogger("automation_engine")


def _now() -> datetime:
    return datetime.now(timezone.utc)


class AutomationRunner:
    def __init__(self, user_id: str):
        self.user_id = user_id
        self.task: Optional[asyncio.Task] = None
        self.stop_flag = asyncio.Event()
        self.pause_flag = asyncio.Event()
        self.state = AutomationState(user_id=user_id)
        self._session_gift_detected = False
        self._session_gift_names: list[str] = []

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
        await self._save_state()
        await self._event("start", "info", "Automation dimulai")
        self.task = asyncio.create_task(self._run_forever())

    async def stop(self):
        self.stop_flag.set()
        self.pause_flag.clear()
        if self.task:
            try:
                await asyncio.wait_for(self.task, timeout=5)
            except Exception:
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
        await self._save_state()
        await self._event("resume", "info", "Resumed")

    # ---- Internal helpers ----
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

    async def _drain_queue(self):
        ut = await self._get_client()
        while True:
            try:
                ut.event_queue.get_nowait()
            except asyncio.QueueEmpty:
                break

    async def _wait_for_message(
        self,
        chat: str,
        patterns: list[str],
        timeout: int = 30,
        collect_text: bool = True,
    ) -> Optional[dict]:
        """Wait for a NewMessage from chat matching any regex pattern."""
        compiled = [re.compile(p, re.IGNORECASE) for p in patterns if p]
        ut = await self._get_client()
        deadline = _now() + timedelta(seconds=timeout)
        while _now() < deadline and not self.stop_flag.is_set():
            if self.pause_flag.is_set():
                await self._wait_for_pause()
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
            if collect_text and text:
                await self._event("message-in", "info", text[:300],
                                  meta={"message_id": item.get("message_id")})
            # Continuous verification check
            cfg = await self._load_config()
            if cfg.verification_pattern and re.search(
                cfg.verification_pattern, text, re.IGNORECASE
            ):
                await self._handle_verification(chat, item, cfg)
                continue
            for rx in compiled:
                if rx.search(text):
                    return item
        return None

    async def _click_button_in_message(
        self, chat: str, message_id: int, button_text: str
    ) -> bool:
        ut = await self._get_client()
        try:
            msg = await ut.client.get_messages(chat, ids=message_id)
            if not msg:
                return False
            for row in msg.buttons or []:
                for btn in row:
                    btext = (getattr(btn, "text", "") or "")
                    if button_text.lower() in btext.lower():
                        try:
                            await msg.click(text=btext)
                            await self._event("click", "info", f"Clicked '{btext}'")
                            return True
                        except Exception as exc:
                            await self._event("error", "warn", f"Click '{btext}' failed: {exc}")
                            return False
        except Exception as exc:
            await self._event("error", "warn", f"get_messages failed: {exc}")
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
                            await self._event("error", "warn", f"Emoji click failed: {exc}")
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
                        await self.pause("Telegram belum login — buka Setup Telegram")
                        await asyncio.sleep(5)
                        continue

                    self.state.mode = cfg.mode
                    self.state.cycle += 1
                    self.state.last_error = None
                    await self._save_state()

                    if cfg.mode == "group":
                        await self._cycle_group(cfg)
                    else:
                        await self._cycle_vip(cfg)

                    # Post-cycle: extract & sell every N fishing sessions
                    if self.state.fish_since_sell >= cfg.extract_sell_every_n_fish:
                        await self._extract_and_sell(cfg)

                    if cfg.mode == "vip_direct":
                        await self._sleep_seconds(cfg.vip_gap_seconds, "waiting")

                except Exception as exc:
                    log.exception("automation loop error")
                    self.state.status = "error"
                    self.state.last_error = str(exc)[:500]
                    await self._save_state()
                    await self._event("error", "error", f"Loop error: {exc}")
                    await asyncio.sleep(10)
        finally:
            if not self.stop_flag.is_set():
                self.state.status = "stopped"
            await self._save_state()

    # ---- One fishing session ----
    async def _cycle_vip(self, cfg: AutomationConfig):
        target = cfg.bot_username or cfg.group_username
        if not target:
            await self.pause("Bot username belum diset")
            return
        await self._do_fishing_session(cfg, target,
                                       wait_seconds=cfg.vip_fish_seconds + 60)

    async def _cycle_group(self, cfg: AutomationConfig):
        group = cfg.group_username
        bot = cfg.bot_username or "@fish_it_bot"
        if not group:
            await self.pause("Group username belum diset")
            return
        ut = await self._get_client()

        # 1) Open in group
        self.state.status = "opening"
        self.state.last_action_at = utcnow_iso()
        await self._save_state()
        await self._drain_queue()
        open_cmd = cfg.group_open_command or cfg.open_command
        await ut.send_command(group, open_cmd)
        await self._event("message-out", "info", f"Sent {open_cmd}",
                          meta={"chat": group})

        # 2) Wait for "PENDAFTARAN DIBUKA" in group, then click "Daftar Mancing"
        self.state.status = "joining"
        await self._save_state()
        pendaftaran = await self._wait_for_message(
            chat=group,
            patterns=[cfg.pendaftaran_pattern or r"PENDAFTARAN DIBUKA"],
            timeout=30,
        )
        if pendaftaran:
            await self._click_button_in_message(
                group, pendaftaran["message_id"], cfg.join_button_text
            )
        else:
            # Fallback: scan last messages for button
            await self._find_and_click_button(group, cfg.join_button_text, timeout=10)

        # 3) DM confirm: send /start in bot DM
        await asyncio.sleep(2)
        try:
            await ut.send_command(bot, cfg.dm_confirm_command)
            await self._event("message-out", "info",
                              f"Sent {cfg.dm_confirm_command} → {bot}")
        except Exception as exc:
            await self._event("error", "warn", f"DM confirm failed: {exc}")

        # 4) Wait for "Pendaftaran Berhasil" in bot DM
        await self._wait_for_message(
            chat=bot,
            patterns=[r"Pendaftaran Berhasil|sedang memancing"],
            timeout=15,
        )

        # 5) Wait pendaftaran window (~60s) + fishing (~3min); use combined timeout
        await self._sleep_seconds(cfg.group_wait_seconds, "waiting")
        if self.stop_flag.is_set():
            return

        # 6) Wait for SESI MANCING SELESAI in bot DM (fishing session running)
        self.state.status = "fishing"
        await self._save_state()
        result_msg = await self._wait_for_message(
            chat=bot,
            patterns=[cfg.session_done_pattern],
            timeout=cfg.group_fish_seconds + 60,
        )
        if not result_msg:
            await self._event("info", "warn",
                              "SESI MANCING SELESAI tidak terdeteksi (timeout)")
            return

        text = result_msg.get("text", "") or ""
        # Detect gift rarity — scan recent bot DM messages (gift banners are
        # separate messages before SESI MANCING SELESAI).
        await self._scan_recent_for_gift(bot, cfg)

        if cfg.rare_pattern:
            rares = re.findall(cfg.rare_pattern, text, flags=re.IGNORECASE)
            if rares:
                await self._event("rare", "info", f"Rare: {', '.join(set(rares))}")

        self.state.fish_caught += 1
        self.state.fish_since_sell += 1
        await self._event("fish-caught", "success",
                          "Group session selesai",
                          meta={"fish_since_sell": self.state.fish_since_sell})
        await self._save_state()

    async def _do_fishing_session(self, cfg: AutomationConfig, chat: str, wait_seconds: int):
        """Send /mancing, wait for SESI MANCING SELESAI, parse rarity, log."""
        ut = await self._get_client()
        self.state.status = "fishing"
        await self._save_state()
        self._session_gift_detected = False
        self._session_gift_names = []
        await self._drain_queue()
        await ut.send_command(chat, cfg.open_command)
        await self._event("message-out", "info", f"Sent {cfg.open_command}",
                          meta={"chat": chat})

        # Wait for SESI MANCING SELESAI
        result_msg = await self._wait_for_message(
            chat=chat,
            patterns=[cfg.session_done_pattern],
            timeout=wait_seconds,
        )
        if not result_msg:
            await self._event("info", "warn",
                              "Session done tidak terdeteksi (timeout)")
            return

        text = result_msg.get("text", "") or ""
        # Detect gift rarity from result AND scan recent messages (gift banners
        # come in a separate message before the summary).
        await self._scan_recent_for_gift(chat, cfg)

        # Rare fish notification (log only)
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
        """After fishing session, look back at recent bot messages for gift rarity headers.

        Gift messages come as SEPARATE messages (e.g. '✨ CELESTIAL ✨' with fish name
        below) BEFORE the 'SESI MANCING SELESAI' summary.
        """
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
                    # Try extract fish name (line after rarity header)
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

    async def _find_and_click_button(self, chat: str, text: str, timeout: int = 15) -> bool:
        ut = await self._get_client()
        deadline = _now() + timedelta(seconds=timeout)
        while _now() < deadline and not self.stop_flag.is_set():
            try:
                msgs = await ut.get_last_messages(chat, limit=5)
            except Exception:
                await asyncio.sleep(1)
                continue
            for m in msgs:
                for b in m.get("buttons", []):
                    if b.get("text") and text.lower() in b["text"].lower():
                        try:
                            await ut.click_button(chat, m["id"], text=b["text"])
                            return True
                        except Exception as exc:
                            await self._event("error", "warn", f"Click failed: {exc}")
            await asyncio.sleep(1)
        return False

    # ---- Extract & Sell ----
    async def _extract_and_sell(self, cfg: AutomationConfig):
        chat = cfg.bot_username or cfg.group_username
        if not chat:
            return
        ut = await self._get_client()

        # If gift detected during session, favorite first BEFORE extract/sell
        if self._session_gift_detected:
            await self._inventory_favorite(cfg, chat, self._session_gift_names)

        # 1) /extract → wait for materials → click Inventory button
        self.state.status = "extracting"
        await self._save_state()
        await self._drain_queue()
        await ut.send_command(chat, cfg.extract_command)
        await self._event("message-out", "info", f"Sent {cfg.extract_command}")

        materials_msg = await self._wait_for_message(
            chat, patterns=[r"EXTRACT.*MATERIALS|Punyamu"], timeout=15
        )
        if materials_msg:
            # Click the "📦 Inventory (N)" button
            clicked = await self._click_button_in_message(
                chat, materials_msg["message_id"], cfg.extract_inventory_button_text
            )
            if clicked:
                # Wait for extract list, then click green circle
                list_msg = await self._wait_for_message(
                    chat, patterns=[r"Bisa di-extract|extract semua artefak"], timeout=15
                )
                if list_msg:
                    ok = await self._click_button_by_emoji(
                        chat, list_msg["message_id"], cfg.extract_all_button_emoji
                    )
                    if ok:
                        await self._wait_for_message(
                            chat, patterns=[cfg.extract_success_pattern], timeout=15
                        )
                        await self._event("extract", "success", "Extract berhasil")
                    else:
                        await self._event("info", "warn", "Tombol 🟢 tidak ditemukan")
                else:
                    await self._event("info", "warn", "Extract list tidak muncul")
            else:
                await self._event("info", "warn",
                                  f"Button '{cfg.extract_inventory_button_text}' tidak ditemukan")
        else:
            await self._event("info", "warn", "Extract materials tidak muncul")

        # 2) /jual semua → confirm → check rarity → click Ya/Batal
        await self._do_sell(cfg, chat)
        self.state.fish_since_sell = 0
        await self._save_state()

    async def _do_sell(self, cfg: AutomationConfig, chat: str, retry_after_favorite: bool = False):
        ut = await self._get_client()
        self.state.status = "selling"
        await self._save_state()
        await self._drain_queue()
        await ut.send_command(chat, cfg.sell_command)
        await self._event("message-out", "info", f"Sent {cfg.sell_command}")

        confirm_msg = await self._wait_for_message(
            chat, patterns=[cfg.sell_confirm_pattern], timeout=15
        )
        if not confirm_msg:
            await self._event("info", "warn", "Konfirmasi penjualan tidak muncul")
            return

        text = confirm_msg.get("text", "") or ""
        has_gift = bool(cfg.gift_rarity_pattern and re.search(
            cfg.gift_rarity_pattern, text, re.IGNORECASE
        ))

        if has_gift and not retry_after_favorite:
            await self._event("gift", "warn",
                              "Gift terdeteksi di konfirmasi jual — batalkan & favoritkan dulu")
            await self._notify("gift", "Gift/Secret di konfirmasi jual",
                               "Automation membatalkan penjualan dan memfavoritkan dulu.")
            await self._click_button_in_message(
                chat, confirm_msg["message_id"], cfg.sell_cancel_button_text
            )
            gifts = re.findall(cfg.gift_rarity_pattern, text, flags=re.IGNORECASE)
            await self._inventory_favorite(cfg, chat, list(set(gifts)))
            # Retry sell
            await self._do_sell(cfg, chat, retry_after_favorite=True)
            return

        # Confirm sell
        ok = await self._click_button_in_message(
            chat, confirm_msg["message_id"], cfg.sell_confirm_button_text
        )
        if ok:
            await self._event("sell", "success", "Jual semua dikonfirmasi")
        else:
            await self._event("info", "warn",
                              f"Tombol '{cfg.sell_confirm_button_text}' tidak ditemukan")

    # ---- Inventory paging + favorite ----
    async def _inventory_favorite(
        self, cfg: AutomationConfig, chat: str, keywords: list[str]
    ):
        """Open /inventory, paginate, find items matching gift rarity, send /favorite <n>."""
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
        # Match rarity keywords on each page's line by line
        rarity_rx = re.compile("(" + "|".join(re.escape(k) for k in keywords) + ")",
                               re.IGNORECASE)

        while page <= max_pages and not self.stop_flag.is_set():
            inv_msg = await self._wait_for_message(
                chat, patterns=[r"Halaman:?\s*\d+|Inventory\s+\w+"], timeout=15
            )
            if not inv_msg:
                break
            text = inv_msg.get("text", "") or ""
            # Line pattern: "  5. 🐟 Nama\n     └ ... • rarity"
            lines = text.splitlines()
            positions_to_favorite = []
            current_num = None
            for line in lines:
                num_match = re.match(r"\s*(\d+)[\.\)]\s+", line)
                if num_match:
                    current_num = int(num_match.group(1))
                if current_num is not None and rarity_rx.search(line):
                    positions_to_favorite.append(current_num)
                    current_num = None  # Only favorite the header line's number

            positions_to_favorite = sorted(set(positions_to_favorite))
            for pos in positions_to_favorite:
                cmd = cfg.favorite_command_template.replace("{n}", str(pos))
                await ut.send_command(chat, cmd)
                await self._event("favorite", "success",
                                  f"Sent {cmd} (page {page})")
                favorited_any = True
                await asyncio.sleep(1)

            # If already found on this page, we may still page through in case of dupes
            # but for efficiency, stop after finding one match
            if favorited_any:
                break

            # Otherwise, click Next
            clicked = await self._click_button_in_message(
                chat, inv_msg["message_id"], cfg.inventory_next_button_text
            )
            if not clicked:
                await self._event("info", "warn", "Tombol Next tidak ditemukan")
                break
            page += 1
            await asyncio.sleep(1)

        if not favorited_any:
            await self._event("info", "warn",
                              f"Tidak menemukan gift ({', '.join(keywords)}) di /inventory")
            await self._notify("info", "Gift tidak ditemukan di inventory",
                               f"Cek /inventory manual untuk: {', '.join(keywords)}")
        self.state.status = "fishing"
        await self._save_state()

    # ---- Verification ----
    async def _handle_verification(self, chat: str, item: dict, cfg: AutomationConfig):
        ut = await self._get_client()
        self.state.status = "verifying"
        await self._save_state()
        await self._event("verification", "warn", "Verifikasi Diperlukan terdeteksi")

        url: Optional[str] = None
        try:
            msgs = await ut.get_last_messages(chat, limit=5)
            for m in msgs:
                for b in m.get("buttons", []):
                    btext = b.get("text") or ""
                    if cfg.verification_button_text.lower() in btext.lower():
                        if b.get("url"):
                            url = b["url"]
                            break
                        try:
                            res = await ut.click_button(chat, m["id"], text=btext)
                            url = res.get("url") or url
                        except Exception as exc:
                            await self._event("error", "warn", f"Verify click: {exc}")
                if url:
                    break
        except Exception as exc:
            await self._event("error", "warn", f"Verify inspect: {exc}")

        if url:
            self.state.verification_url = url
            await self._save_state()
            await self._notify(
                "verification", "🔒 Verifikasi Diperlukan",
                "Automation mendeteksi verifikasi. Silakan buka Mini App URL, "
                "selesaikan (kadang otomatis, kadang perlu centang 'I'm human'), lalu Resume.",
                action_url=url,
            )
            await self._event("verification", "warn", "Mini App URL siap dibuka",
                              meta={"url": url})

        # Try wait for auto-success (some verifications auto-complete)
        success = await self._wait_for_message(
            chat=chat,
            patterns=[r"(berhasil|sukses|verified|selesai|terverifikasi)"],
            timeout=60,
            collect_text=False,
        )
        if success:
            await self._event("verification", "success", "Verifikasi berhasil otomatis")
            self.state.verification_url = None
            self.state.status = "fishing"
            await self._save_state()
        else:
            await self.pause("Verifikasi butuh manual — buka URL Mini App lalu Resume")


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
