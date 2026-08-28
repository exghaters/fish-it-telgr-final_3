"""Pydantic models & MongoDB helper for Fish It automation."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_id() -> str:
    return str(uuid.uuid4())


# ---------- User ----------
class User(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=new_id)
    email: EmailStr
    password_hash: str
    role: Literal["user", "admin"] = "user"
    plan: Literal["free", "basic", "pro", "elite"] = "free"
    is_active: bool = True
    created_at: str = Field(default_factory=utcnow_iso)


class UserPublic(BaseModel):
    id: str
    email: EmailStr
    role: str
    plan: str
    is_active: bool
    created_at: str


class RegisterInput(BaseModel):
    email: EmailStr
    password: str = Field(min_length=6, max_length=200)


class LoginInput(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserPublic


# ---------- Telegram Account (multi-account per user) ----------
class TelegramAccount(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=new_id)
    user_id: str
    label: str = "Akun"
    created_at: str = Field(default_factory=utcnow_iso)


class AccountCreateInput(BaseModel):
    label: str = Field(default="Akun", max_length=40)


# ---------- Telegram Session ----------
class TelegramSessionMeta(BaseModel):
    """Public metadata about a user's Telegram MTProto session (no secrets)."""
    connected: bool = False
    phone: Optional[str] = None
    display_name: Optional[str] = None
    api_id_set: bool = False
    last_error: Optional[str] = None
    updated_at: str = Field(default_factory=utcnow_iso)


class TelegramCredentialsInput(BaseModel):
    api_id: int
    api_hash: str = Field(min_length=8, max_length=128)


class TelegramSendCodeInput(BaseModel):
    phone: str = Field(pattern=r"^\+[1-9][0-9]{6,14}$")


class TelegramVerifyInput(BaseModel):
    code: str = Field(min_length=3, max_length=10)
    password: Optional[str] = None  # 2FA


# ---------- Automation Config ----------
class AutomationConfig(BaseModel):
    """User's Fish It automation configuration.

    Patterns/commands are configurable so user can adjust after inspecting real bot messages.
    """
    model_config = ConfigDict(extra="ignore")
    user_id: str

    mode: Literal["group", "vip_direct"] = "vip_direct"
    group_username: str = ""              # e.g. @fishitgroup (for group mode)
    bot_username: str = "@fish_it_bot"    # Fish It bot username

    # Commands (defaults for @fish_it_bot; editable in UI)
    open_command: str = "/mancing"
    group_open_command: str = "/open_mancing@fish_it_vip_bot"
    join_button_text: str = "Daftar Mancing"
    dm_confirm_command: str = "/start"
    extract_command: str = "/extract"
    extract_inventory_button_text: str = "Inventory"   # "[📦 Inventory (7)]"
    extract_all_button_emoji: str = "🟢"               # green circle = extract all artefak
    sell_command: str = "/jual semua"
    sell_confirm_button_text: str = "Ya, Jual Semua"
    sell_cancel_button_text: str = "Batal"
    inventory_command: str = "/inventory"
    favorite_command_template: str = "/favorite {n}"

    # Chat filter — engine ONLY reads messages from bot, group & these chats
    extra_allowed_chats: str = "@fish_it_vip_bot, @fish_it_vip3_bot, @fish_it_vip4_bot, @fish_it_vip5_bot"

    # Boost (optional, opt-in): send /boost in bot DM when trigger appears
    boost_enabled: bool = False
    boost_command: str = "/boost"
    boost_trigger_pattern: str = r"(AUTO MANCING DIMULAI)"
    boost_cooldown_seconds: int = 300

    # Group boost: send /boost_grup in group when its trigger appears
    group_boost_command: str = "/boost_grup"
    group_boost_trigger_pattern: str = r"(Boost Grup Berakhir|PERAHU SIAP BERANGKAT)"

    # Group flow (event-driven) patterns
    pendaftaran_open_pattern: str = r"(PENDAFTARAN DIBUKA)"
    waktu_habis_pattern: str = r"(WAKTU HABIS)"

    # Rare-fish protection: favorite before /jual semua so they are NOT sold.
    # Triggered when inventory rarity summary shows ✨/🌟/☀️ (secret_shiny/celestial/secret).
    protect_rarity_pattern: str = r"(secret[_ ]?shiny|celestial|secret)"
    rarity_summary_pattern: str = r"(✨|🌟|☀️)"
    protect_min_coins: int = 1000000
    inventory_max_pages: int = 11

    # Manual verification: type this keyword in the bot chat to resume automation
    resume_keyword: str = "dvk"

    # Cycle timing (seconds)
    group_wait_seconds: int = 60          # wait after Join
    group_fish_seconds: int = 180         # 3 minutes fishing
    vip_fish_seconds: int = 300           # 5 minutes VIP timeout
    vip_gap_seconds: int = 10             # jeda antar mancing VIP
    inventory_page_size: int = 20
    extract_sell_every_n_fish: int = 3

    # Detection patterns (regex, case-insensitive)
    session_done_pattern: str = r"(SESI MANCING SELESAI|mancing selesai|WAKTU HABIS)"
    pendaftaran_pattern: str = r"(PENDAFTARAN DIBUKA|Pendaftaran Berhasil)"
    gift_message_pattern: str = r"✨\s*(SECRET SHINY|SECRET|CELESTIAL|MYTHIC)\s*✨"
    already_fishing_pattern: str = r"(sedang memancing|masih memancing|sedang aktif|SEDANG MANCING)"
    extract_list_pattern: str = r"(Bisa di-extract|extract semua artefak|EXTRACT.*Inventory)"
    gift_rarity_pattern: str = r"(SECRET SHINY|SECRET|CELESTIAL|MYTHIC|Mythical)"
    rare_pattern: str = r"(legend|myth|epic|artefak)"
    inventory_full_pattern: str = r"(Inventory Penuh|inventory.*(penuh|full)|\d+/\d+\s*ikan|tas.*penuh)"
    verification_pattern: str = r"(🔒.*[Vv]erifikasi|verifikasi diperlukan|verify)"
    verification_button_text: str = "Verifikasi"
    inventory_next_button_text: str = "Next"
    extract_success_pattern: str = r"(EXTRACT BERHASIL|extract berhasil)"
    sell_confirm_pattern: str = r"(KONFIRMASI PENJUALAN|konfirmasi penjualan)"

    enabled: bool = False
    updated_at: str = Field(default_factory=utcnow_iso)


# ---------- Runtime state ----------
class AutomationState(BaseModel):
    """Ephemeral runtime state exposed to the dashboard."""
    user_id: str
    status: Literal[
        "idle", "starting", "opening", "joining", "waiting", "fishing",
        "extracting", "selling", "inventory", "favoriting",
        "verifying", "paused", "stopped", "error"
    ] = "idle"
    mode: str = "group"
    cycle: int = 0
    fish_caught: int = 0
    fish_since_sell: int = 0
    started_at: Optional[str] = None
    last_action_at: Optional[str] = None
    next_action_at: Optional[str] = None
    countdown_seconds: int = 0
    last_message: str = ""
    last_error: Optional[str] = None
    verification_url: Optional[str] = None
    updated_at: str = Field(default_factory=utcnow_iso)


# ---------- Events / Notifications ----------
EventKind = Literal[
    "info", "action", "message-in", "message-out", "click",
    "fish-caught", "rare", "gift", "special", "verification",
    "error", "start", "stop", "pause", "resume", "sell", "extract", "favorite",
]


class EventDoc(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=new_id)
    user_id: str
    kind: EventKind
    level: Literal["info", "warn", "error", "success"] = "info"
    message: str
    meta: dict[str, Any] = Field(default_factory=dict)
    created_at: str = Field(default_factory=utcnow_iso)


class Notification(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=new_id)
    user_id: str
    title: str
    body: str = ""
    kind: Literal["rare", "gift", "special", "verification", "error", "info"] = "info"
    read: bool = False
    action_url: Optional[str] = None
    created_at: str = Field(default_factory=utcnow_iso)


# ---------- Admin ----------
class AdminUpdateUserInput(BaseModel):
    role: Optional[Literal["user", "admin"]] = None
    plan: Optional[Literal["free", "basic", "pro", "elite"]] = None
    is_active: Optional[bool] = None
