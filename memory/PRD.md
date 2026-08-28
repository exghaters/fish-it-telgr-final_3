# Fish It Autopilot — PRD

## Original Problem Statement
Rebuild of a buggy Telegram automation SaaS for the "Fish It" game. Reported bugs:
1. Engine spammed `/extract` + `/jual semua` while a fishing session was still running.
2. Activity Log too noisy — logged messages from every group, not just the target.
3. Chat filter should cover multiple VIP bots (only showed one).
4. Verification button (Mini App / Cloudflare) — best-effort auto + manual fallback.
5. Group "Daftar Mancing" join not working (wrong message_id from other groups).
6. NEW: optional `/boost` when "⛵️ PERAHU SIAP BERANGKAT" (group) or "AUTO MANCING DIMULAI!" (bot) appears; 5-min duration, opt-in.

## Architecture
- Backend: FastAPI (`/api` prefix), MongoDB (motor), Telethon MTProto per-user, JWT auth, Fernet-encrypted sessions.
- Frontend: React (CRA+craco, `@/` alias), Tailwind, shadcn/ui, phosphor icons.
- Engine: per-user `AutomationRunner` state machine (VIP direct + group modes).

## User Personas
- Fish It player wanting hands-free auto-mancing/extract/sell across their VIP bots.
- Admin managing users/plans.

## Core Requirements (static)
- Per-user Telegram login, configurable commands/patterns, activity log, notifications, plans, admin panel.

## Implemented (2026-08-28 rebuild)
- Restored full codebase into /app; regenerated secrets (Fernet/JWT), seeded admin.
- Chat filter: engine only reads bot + target group + `extra_allowed_chats` (defaults to the 4 VIP bots) → clean Activity Log, correct SESI SELESAI detection.
- Anti-spam: hard guard `_ensure_no_active_session`; on "KAMU SEDANG MANCING! Waktu berjalan: X detik" it computes remaining (duration − X) and WAITS instead of retrying.
- Optional auto `/boost` on trigger text with 5-min cooldown (opt-in switch).
- Group join via "Daftar Mancing" (deep-link or callback), scoped to filtered chat.
- Best-effort verification auto-click (pinned + recent), manual fallback + pause/resume.
- Added: `/api/automation/start` now requires a connected Telegram session (clear 400 instead of silent engine failure).
- Fixed backend shutdown CancelledError handling (found by testing).
- Tested: backend 29/29 live-API pass; frontend all nav + config persistence pass.

## Implemented (2026-08-28, iter 8)
- Multi-account Telegram per plan: Starter/free=1, Pro=1, Elite=3. Each account fully isolated (session, config, state, log, notif) via `X-Account-Id` header → composite key `user_id:account_id`. Endpoints: GET/POST/DELETE /api/telegram/accounts.
- Sidebar account switcher (native select + add button; disabled at plan limit).
- Plan gating: account limit enforced (4th → 403); Activity Log retention 7/30/90d by plan; auto-verify only Pro/Elite (free = manual, fail-safe to manual on error).
- FIX: telegram_manager `_resolve_entity` with iter_dialogs fallback — resolves the "The key is not registered in the system (ResolveUsernameRequest)" crash + empty chat-filter. resolve_chat_id/send_command/get_last_messages all route through it.
- Tests: backend 13/13 new + 36/36 regression pass; frontend switcher + regression pass.

## Implemented (2026-08-28, iter 9 — code quality)
- Applied SAFE code-quality fixes: removed hardcoded admin password from tests (now loads from backend/.env), added console.error to 6 silent catch blocks, stable list key in Landing demo.
- Intentionally skipped risky/over-engineering suggestions (httpOnly-cookie auth migration, large engine/Configuration refactors, hook-dep churn) to protect just-verified behavior.
- Updated 4 stale introspection/default-value tests to match current design. Full backend suite now 119/119 green; frontend regression 100%.

## Backlog / Next
- Forgot-password (needs email integration e.g. Resend, or admin reset).
- Per-plan "all VIP bots vs single" gating (currently config is free-form).


## Implemented (2026-08-28, iter 7)
- Extract/sell order corrected: STEP1 protect rare fish (/inventory → collect positions across all pages → ONE grouped `/favorite 5 56 110`, chunk 20) → STEP2 /extract → STEP3 /jual semua (verified by testing agent).
- Rare protection no longer skips coins-based protection when no rarity-emoji summary and protect_min_coins>0.
- Mobile dashboard sidebar is now a collapsible off-canvas drawer (hamburger toggle, overlay, auto-close on nav); top bar z-index fixed so the X closes it.
- Backend regression 7/7 pass.


## Implemented (2026-08-28, iter 10)
- VIP-bot gating by plan: Starter (free/basic) limited to single bot/group — extra_allowed_chats disabled in UI + forced empty on save; Pro/Elite unrestricted (deps.PLAN_LIMITS.vip_multi).
- Admin-driven password reset (user declined email/Resend): admin panel per-user Reset Password (key icon) -> POST /api/admin/users/{id}/reset-password (min 6, admin-only). Login shows "Lupa password? Hubungi admin".
- Group START kickstart: on Start in group mode, engine immediately sends /open_mancing@<bot> to the group; VIP already sends /mancing immediately.
- Verified: backend 130/130 pytest, frontend 100%.
