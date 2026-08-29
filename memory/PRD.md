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

## Code Quality Pass — 2026-06 (safe-only)
- Frontend: removed production `console.error` (5 dashboard pages) → silent background-poll catches.
- Frontend: wrapped polling `load()` in `useCallback` (Status/Notifications/Activity/Admin) + fixed useEffect deps.
- Frontend: memoized AuthProvider context value (`useMemo`/`useCallback`) in `lib/auth.jsx`.
- Frontend: extracted inline Framer Motion prop objects to module constants in `Landing.jsx`.
- SKIPPED (would introduce bugs): Python `is`→`==` — all instances are `is None`/`is not None` (correct PEP8). craco console.warn is intentional platform build messaging.
- DEFERRED (risky, user chose "aman"): localStorage→cookie auth change; splitting `automation_engine.py` functions; splitting large components.

## Code Quality Pass #2 — 2026-06 (safe-only, report a778a06d)
- Added dev-only logger `src/lib/log.js` (`logError`) — errors observable in dev, silent in production build. Satisfies BOTH conflicting review reports (no prod console noise, no swallowed errors, no UX error banners on transient poll failures).
- Applied `logError` in catch blocks of Status/Notifications/Activity/Admin/TelegramSetup data loaders (replaced silent catches).
- Verified: testing_agent iteration_11 — frontend 100%, no console errors/white screens, both login flows OK.
- SKIPPED as false-positive/incorrect: Python `is`→`==` (all are `is None`/`is not None`, PEP8-correct); "undefined variables" (pyflakes clean, none found).
- DEFERRED per user "aman": localStorage→cookie, splitting automation_engine functions, splitting large components. Hook-dep "false positives" (module imports/globals/stable setters) left as-is.

## Feature: httpOnly Cookie Auth + Admin Delete User — 2026-06
- SECURITY: JWT moved from localStorage to httpOnly+Secure cookie. Backend sets cookie on login/register (`_set_auth_cookie`), `get_current_user` reads Authorization header first then `access_token` cookie fallback. New `POST /api/auth/logout` clears cookie. Frontend axios `withCredentials:true`, no token in localStorage (only non-sensitive user object cached).
- ADMIN: `DELETE /api/admin/users/{id}` — cascade deletes user-scoped data (telegram_accounts/config/state/sessions/events/notifications), blocks deleting own account (400). Admin UI: red trash button per row (data-testid=delete-user) with confirm + toast.
- Tests: updated 4 "requires-auth" tests to clear shared requests.Session cookie (login now sets a cookie). Backend 130/130 pytest pass. testing_agent iteration_12: backend 100% (9/9), frontend 100% (6/6).

## Security Hardening (post-audit) — 2026-06
- SEC-001 (CRITICAL): removed hardcoded admin password fallback from server.py (fail-fast on missing ADMIN_PASSWORD); seed_admin now rotates the hash when ADMIN_PASSWORD changes. Rotated to a strong random password stored in backend/.env (git-ignored) + /app/memory/test_credentials.md.
- SEC-002 (ReDoS): PUT /api/automation/config validates every *_pattern field — length cap 300, must compile, rejects nested-quantifier catastrophic patterns (400).
- Hardening: login brute-force lockout (5 fails/ip:email => 15min, 429) via login_attempts collection; JWT TTL 7 days (cookie max_age matched); token removed from login/register response body (httpOnly cookie only); register password min_length raised 6 -> 8.
- CORS explicit-origin fix DEFERRED until final deploy domain is known.
- Test suite updated (admin pwd from env, token read from login cookie): 139/139 pytest pass. testing_agent iteration_13: backend 17/17, frontend critical flows 100%.

## Operator/Joki Model Adjustments — 2026-06
- Public self-registration DISABLED: /register route + page removed, Login has no signup link. Backend register() returns 403 unless env ALLOW_PUBLIC_REGISTRATION=="true" (set true in preview .env for tests; leave OFF in production).
- Admin creates operator logins: POST /api/admin/users (admin-only, default role=user plan=elite). UI: "Buat Akun Operator" form on Admin page (data-testid create-user-card/new-user-email/new-user-password/create-user-submit).
- Per-account label (customer name): create prompts for label; rename via pencil button (data-testid account-rename) -> PATCH /api/telegram/accounts/{id}. Telegram accounts stay isolated per operator.
- Operators (elite) account cap raised 3 -> 100; list_accounts cap raised to 1000. Sidebar Pricing/Paket nav hidden (Admin kept).
- BUGFIX: ensure_default_account race (concurrent first-load created duplicate default accounts) -> deterministic id 'default-{user_id}' + unique-index guard; verified 24 concurrent requests => 1 account.
- Tests updated for new limits; 167/167 pytest pass. testing_agent iteration_14: frontend 100% critical flows, backend 100%.

## Gameplay Bug Fixes (group re-open, verify-resume, account session) — 2026-06
- Bug1 (group): "❌ PENDAFTARAN DIBATALKAN / Tidak ada peserta" now triggers auto re-open of /open_mancing@<bot> (new pendaftaran_cancelled_pattern + 'cancelled' rule in _cycle_group, 3s debounce).
- Bug2 (verify-resume): engine remembers the pending join deeplink (/start daftar2_...) or /mancing in self._pending_after_verify; re-issues it after verification finishes — both auto-verify success (_resend_pending_after_verify force) and manual-resume (_wait_for_any after _wait_for_pause, gated by _paused_for_verify). New registration_success_pattern clears pending to avoid double-send.
- Bug3 (account session): /telegram/status (get_meta rehydrate=True) now rehydrates the Telethon client from the stored encrypted session, so switching accounts / backend restart no longer forces a phone re-login for an already-connected account.
- Tests: new backend/tests/test_iter15_group_reopen_verify_resume.py (5 unit tests). Full suite 172 local / 175 with testing-agent API tests. testing_agent iteration_15: backend 100%, frontend 100%, no issues.
- NOTE: real-Telegram effects (green 'connected' after rehydrate, actual button clicks, Cloudflare verify) still require the user's real one-cycle confirmation — the test env has no live Telegram session.
