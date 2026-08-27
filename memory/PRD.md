# PRD — Fish It Automation Panel

## Original Problem Statement
Pengguna ingin membuat panel web (dashboard) untuk mengontrol automation game Telegram
"Fish It". Automation memakai akun Telegram pribadi (MTProto/Telethon). Rencana:
menjualnya sebagai layanan langganan.

## Personas
- **Solo Owner (default user)** — punya 1 akun Telegram, ingin mancing 24/7 tanpa nunggu.
- **Power User (Elite)** — punya 3+ akun, ingin dashboard admin & log panjang.
- **Admin (kami)** — kelola user, upgrade paket, aktivasi/blokir.

## Core Requirements (static)
1. Auth email/password + role (user/admin) + plan (free/basic/pro/elite).
2. Login Telegram MTProto per user (API ID/Hash + phone → code → 2FA).
3. Session Fernet-encrypted di MongoDB; 1 worker per akun.
4. State machine Fish It:
   - VIP Direct: `/mancing` → wait `SESI MANCING SELESAI` → jeda 10s.
   - Group: `/open_mancing@fish_it_vip_bot` → click **Daftar Mancing** → DM `/start` → wait 60s + 3min → SELESAI di DM.
   - Setiap N sesi: `/extract` → klik **Inventory** → klik **🟢** → `/jual semua` → klik **Ya Jual Semua** (batal bila deteksi gift).
   - Gift rarity `✨ SECRET/SECRET SHINY/CELESTIAL ✨` → `/inventory` paging → `/favorite <n>`.
   - Verifikasi `🔒` → auto-click "Verifikasi Sekarang" + notif Mini App URL → pause bila CAPTCHA.
5. Panel: landing, login/register, dashboard status realtime, telegram setup, konfigurasi, activity log, notifikasi, paket, admin.
6. Automation jalan tanpa batas siklus.

## What's Been Implemented (2026-02-27)
### Backend (`/app/backend/`)
- `server.py` — FastAPI, lifespan seed admin, indexes, routers `/api/{auth,telegram,automation,admin}`.
- `deps.py` — Mongo, Fernet, JWT (HS256), bcrypt, `get_current_user`, `get_current_admin`.
- `models.py` — User, AutomationConfig (with configurable commands & regex patterns), AutomationState, EventDoc, Notification, TelegramSessionMeta.
- `auth_routes.py` — register, login, me.
- `tg_routes.py` — Telegram credentials save, send-code, verify (with 2FA), status, logout, recent-messages.
- `automation_routes.py` — config GET/PUT, status, start/stop/pause/resume, events, notifications.
- `admin_routes.py` — users list/update, stats.
- `telegram_manager.py` — TelegramManager registry; UserTelegram wraps Telethon; encrypt session before persist.
- `automation_engine.py` — AutomationRunner per user; state machine with gift detection, extract-inventory-🟢 flow, sell confirm with gift-check, /inventory paging + /favorite, verification handler.

### Frontend (`/app/frontend/src/`)
- `App.js` — router + AuthProvider + Sonner.
- `lib/api.js`, `lib/auth.jsx` — axios interceptor + auth context.
- `pages/Landing.jsx` — marketing landing (hero, features, how-it-works, pricing, footer).
- `pages/Login.jsx`, `pages/Register.jsx`.
- `pages/DashboardLayout.jsx` — sidebar nav with unread badge + role-based admin link.
- `pages/dashboard/Status.jsx` — realtime status card (2s polling), Start/Stop/Pause/Resume, verification banner.
- `pages/dashboard/TelegramSetup.jsx` — 3-step wizard (creds → phone → code+2FA) + logout.
- `pages/dashboard/Configuration.jsx` — all config fields (mode, commands, timings, regex patterns), Switch enabled.
- `pages/dashboard/Activity.jsx` — terminal-style auto-scroll log with filter.
- `pages/dashboard/Notifications.jsx` — inbox with mark-read.
- `pages/dashboard/Pricing.jsx` — 3 tiers, current plan indicator.
- `pages/dashboard/Admin.jsx` — user table with role/plan/status update.

### Design
- Dark cyberpunk gaming SaaS (Void #05050A + Hot Pink #EC4899 + Cyber Yellow #EAB308).
- Fonts: Unbounded (headings), Outfit (body), JetBrains Mono (logs/api).
- Phosphor Icons.

### Testing
- Backend pytest: **20/20 pass**.
- Frontend flows: landing, register, login, dashboard nav, config CRUD, admin — all work.
- 1 bug fixed by testing agent: `/api/telegram/status` 500 when no session doc.

### Test credentials
Lihat `/app/memory/test_credentials.md`.

## Backlog / Prioritized
### P0 — Real integration validation (butuh user)
- Test real login Telegram MTProto dengan API ID/Hash + nomor asli.
- Test siklus grup nyata di grup Fish It untuk verifikasi selector tombol/pesan.
- Validate ✨ SECRET/SHINY/CELESTIAL detection dengan pesan bot real-time.

### P1 — Payment gateway
- Integrasi Stripe / Midtrans / Xendit untuk Rp 79k Pro & Rp 199k Elite.
- Webhook untuk auto-upgrade plan setelah bayar.

### P1 — Multi-Bot per user (Elite tier)
- Izinkan >1 target grup/bot per akun (queue).

### P2 — Analytics
- Grafik ikan per jam, coins earned, gift count.
- Export CSV log.

### P2 — Notifications push
- Telegram bot notif ke user tersendiri saat gift atau verifikasi.

### P2 — Session persistence resilience
- Setelah restart backend, resume automation yang sebelumnya running.
- Distributed lease untuk deploy multi-worker.

## Next Tasks
1. User provide real Telegram API ID/Hash + phone → uji login end-to-end.
2. User run 1 siklus mancing nyata → koreksi pola regex bila perlu.
3. Setelah stabil, integrasikan Stripe/Midtrans + upgrade flow.
