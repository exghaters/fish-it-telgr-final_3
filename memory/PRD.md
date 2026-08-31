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

## Fixes batch (admin lockout, verify scoping, account delete) — 2026-06
- Admin lockout: restored admin is_active=true; admin_routes.update_user now blocks deactivating your own account (400) and the last active admin (400). (testing_agent iter16, 179/179)
- Verification scoping: engine only treats a message as "verifikasi diperlukan" when it comes from the configured Fish It bot(s) (bot_username + extra_allowed_chats via allowed_bot_ids in _wait_for_any; from_target gate in _wait_for_message). Stops scheduled-message/other bots from triggering verification.
- Account delete: added sidebar trash button (data-testid=account-delete) -> DELETE /telegram/accounts/{id}; backend logs out Telethon session (client.log_out + disconnect) and deletes telegram_sessions doc + account-scoped data; blocks deleting last account. (testing_agent iter17, 182/182, frontend 100%)
- resume_keyword already case-insensitive (dvk/Dvk/DVK). Inter-action gap tunable via cfg.vip_gap_seconds.
- STILL NEEDS USER INPUT: exact "boost error" text/logs; what "st" should do; real-Telegram one-cycle confirmation for spam/join/verify. "2 IP" session error = Telegram invalidates a session used from 2 IPs at once (don't use the same account on phone while automation runs; re-login the account).

## Boost destination + VIP verify-resume — 2026-06
- Boost: "⛵️ PERAHU SIAP BERANGKAT" now sends cfg.boost_command to cfg.bot_username (DM) instead of the group (user wanted boost at the configured bot). Cooldown kept.
- VIP verify-resume: _wait_for_message now calls _resend_pending_after_verify() after resume, so after manual verify the VIP flow re-issues /mancing (previously only the group flow did).
- Tests: iter15 now 7 unit tests (incl. boost). Full suite 184/184. testing_agent iter18: backend 100%, no issues.
- OPEN: "st" typed in bot/group triggers /open|/mancing (needs investigation — engine may react to outgoing user messages); Configuration page simplification requested (many fields -> group into Basic/Advanced) — pending.

## Fix: status Telegram flip-flop / minta nomor HP terus (2026-06, iter24)
- GEJALA (produksi botcraft-telegram-1.emergent.host, multi-worker): akun Telegram bergantian "Session aktif" ↔ "Belum terhubung / Setup diperlukan", selalu minta nomor HP.
- ROOT CAUSE: get_meta(rehydrate=True) membuat client hidup tiap polling status. Di multi-worker hanya 1 worker pemegang lease/koneksi → worker lain gagal rehydrate → lapor "belum terhubung". Rehydrate per-status juga berisiko duplicate session (2-IP).
- FIX (telegram_manager.py): status TIDAK lagi membuat client. get_meta membaca flag `authorized` yang dipersist di telegram_sessions. _persist_session set authorized=True saat login sukses; get_or_create sinkronkan authorized True/False saat client benar-benar connect (self-correct bila session dicabut server-side). Legacy doc (ada session_enc, belum ada flag) dianggap authorized=True agar akun lama tidak diminta login ulang.
- Tests: test_iter24_status_stable.py (db di-mock, unit). Full suite 203 passed. (Tanpa testing_agent atas permintaan user.)
- CATATAN: fix ada di kode preview; user perlu REDEPLOY ke produksi agar berlaku di botcraft-telegram-1.emergent.host.


- User konfirmasi alur benar (screenshot): klik "Daftar Mancing" = kirim /start daftar2_<idgrup> ke bot dari deep-link tombol (mis. @fish_it_vip3_bot) → bot balas "Pendaftaran Berhasil". Sudah sesuai fix iter22.
- BUG baru dari screenshot: /start terkirim berulang ("Sudah Terdaftar!" berkali-kali) karena pesan "PENDAFTARAN DIBUKA" meng-edit countdown tiap detik → memicu klik ulang.
- FIX: flag _joined_round di AutomationRunner. _cycle_group 'pendaftaran' skip jika sudah join ronde ini; di-set True setelah join sukses; di-reset saat waktu_habis / cancelled / session_done.
- CLEANUP DB: hapus 510 akun auto-test (pattern test_/regtest_/tg_/iter2_/empty_/uitest_/tgstat_) + cascade data (telegram_sessions 42, automation_configs 212, automation_state 41, events 168). Penyebab: >500 user test membuat admin@fishit.app hilang dari GET /admin/users (limit 500 sort desc) → 5 test admin gagal. Setelah cleanup admin terlihat lagi. Disimpan: 3 admin (admin@, elite@, adolphineeee@) + user@fishit.app (seed test) + test1787811114@ + rufus@gmail + aada@gmail.
- Tests: test_iter23_register_once.py (3). Full suite 202 passed. testing_agent iteration_23: backend 100%, admin visible, 0 issue.


- BUKTI dari DB Activity Log akun "Rick" (@GCBLACKPEARL, grup VIP): 14:15:34 PENDAFTARAN DIBUKA → 14:15:54 "Tombol Daftar Mancing tidak ditemukan (~16s)" → reopen. Log dibanjiri pesan "Sisa waktu"/leaderboard pemain lain.
- ROOT CAUSE: (1) tombol join = URL DEEP-LINK (t.me/fish_it_vip_bot?start=daftar2_-100...) yang di grup ramai terdorong keluar dari window scan kecil (limit=12); (2) SEMUA pesan grup ditulis ke Activity Log/DB → banjir + membebani event loop.
- FIX _join_group_button: polling ~20s, scan iter_messages(limit=50), kenali join via start-deeplink yang menuju cfg.bot_username ATAU label mengandung daftar/mancing → kirim /start <param> ke bot + simpan sebagai _pending_after_verify (dikirim ulang setelah verifikasi). Deep-link ke bot lain (iklan) diabaikan.
- FIX _wait_for_any: hanya log message-in untuk chat bot ATAU pesan yang match pola (pendaftaran/cancelled/waktu_habis/session/inventory/verifikasi/registration/boost). Noise grup tidak lagi ditulis ke DB. Logika matching/boost/verifikasi tetap jalan penuh pada raw text.
- CATATAN: setelah klik deep-link, bot bisa minta VERIFIKASI (screenshot user) → alur verify pause/manual/resume yang sudah ada menangani ini; _pending_after_verify di-resend setelah resume.
- Tests: test_iter22_busy_group_join.py (3). Full suite 200 passed. testing_agent iteration_22: backend 100%, 0 issue.
- MASIH PERLU KONFIRMASI USER di grup nyata (klik deep-link → verifikasi → mancing).


- PUT /api/automation/config sekarang selalu memaksa enabled=false + automation_engine.stop(akey) SEBELUM simpan → automation tidak pernah jalan dengan config yang sedang diedit, dan tetap STOP setelah simpan (tanpa auto-start). Scoped ke akey (get_account_key) → hanya akun yang dipilih yang berhenti, akun lain tetap jalan.
- Frontend Configuration.jsx: saat halaman dibuka & config.enabled true → POST /automation/stop + toast; save() kirim enabled:false + toast "Automation dalam kondisi STOP — tekan Start". Banner peringatan amber (data-testid=config-edit-warning) selalu tampil.
- Tests: test_iter21_config_edit_stops.py (force enabled=false via API + isolasi stop hanya akun target). Full suite 197 passed. testing_agent iteration_21: backend 100%, frontend 100%, 0 issue.

## Investigasi "st" memicu /open atau /mancing (iter21)
- Satu-satunya handler pada pesan OUTGOING operator adalah resume-keyword handler (automation_engine.py ~L245): `if txt == keyword and pause_flag.is_set()`. EXACT match + hanya saat paused → tidak mungkin mengubah "st" jadi /open atau /mancing.
- Kemungkinan penyebab jika benar terjadi: Resume Keyword (Mode Lanjutan) di-set "st", ATAU laporan berasal dari perilaku game/bot lain. Perlu potongan Activity Log + isi Resume Keyword dari user untuk reproduksi pasti. BELUM ada perubahan kode untuk ini.


- ROOT CAUSE: Fish It meng-EDIT pesan "PENDAFTARAN DIBUKA" untuk menambahkan tombol + countdown SESAAT setelah teksnya muncul. Engine dulu langsung fetch sekali → tombol belum ada → "tidak ditemukan", lalu tetap menulis "ditekan" (log menyesatkan) dan menandai session aktif secara keliru → stuck di open mancing.
- FIX (automation_engine._join_group_button): sekarang polling ~16s (8x, jeda 2s), scan 12 pesan grup terbaru tiap percobaan, match teks tombol case-insensitive, dukung deep-link t.me/telegram.me/tg:// + klik inline. Return 'deeplink'|'clicked'|None.
- FIX (_cycle_group pendaftaran): hanya set session aktif + log "✅ ditekan" bila tombol BENAR ditekan; jika gagal → log warning + BUKA ULANG /open_mancing (bukan klaim sukses palsu).
- Password admin dirotasi ke pilihan user (di backend/.env + test_credentials.md); 5 file test yang hardcode password lama disinkronkan.
- Tests: tests/test_iter20_join_button_retry.py (retry-find + deeplink). Full suite 195 passed, 1 skipped. testing_agent iteration_20: backend 100%, admin login 200, 0 issue.
- MASIH PERLU KONFIRMASI USER di grup Fish It nyata (tombol benar tertekan end-to-end).
- (a) Configuration simplification COMPLETED: fixed a pre-existing JSX syntax error (unclosed `<>` fragment) that had broken the frontend compile. Simple mode shows only Target & Mode, Filter Chat & Boost, Auto-Start; `Mode Lanjutan` toggle (data-testid=advanced-mode-toggle) reveals technical sections (Perintah Bot, Timing, Deteksi Pola/Regex, Proteksi Ikan Langka, Grup & Verifikasi). `Reset ke rekomendasi` (data-testid=reset-config) -> POST /api/automation/config/reset returns recommended defaults.
- (a) Admin guards VERIFIED: startup self-heal forces admin is_active=true; PUT /admin/users/{id} blocks deactivating own/any admin (400); DELETE /admin/users/{id} blocks deleting any admin (400); admin login still 200.
- (b) Cross-process session lease ADDED (telegram_manager.py): MongoDB `telegram_locks` collection + per-process INSTANCE_ID. `get_or_create` acquires an exclusive lease (60s TTL, 20s heartbeat) BEFORE connecting any Telethon client, so the same session/auth key can never be live in two processes/uvicorn workers/containers at once — directly targets Telegram's "authorization key was used under two different IP addresses simultaneously" (AUTH_KEY_DUPLICATED). Stale leases (dead process) are auto-taken-over; logout/shutdown release the lease. Different account keys get independent leases -> two accounts run in parallel. Within one process the existing akey registry + per-key lock already guaranteed one client per account. Preview runs `--workers 1`.
- (c) open_mancing + verification CONFIRMED already correct: group mode sends /open_mancing then WAITS for "PENDAFTARAN DIBUKA" and clicks "Daftar Mancing" (deeplink /start or inline click); manual verification pauses, Status shows verification_url block + link, Notifications shows "Sudah Selesai — Resume Automation" button; resume reuses the existing client via get_or_create (no new session).
- Added explicit /dashboard/status route alias (was index-only).
- Tests: new backend/tests/test_iter19_session_lease.py (lease acquire/refresh/foreign-block/stale-takeover/release) + test_iter19_p0_verify.py (public-URL admin guards + config reset). Full suite 189/189 pytest. testing_agent iteration_19: backend 100% (189/189 + 5/5 P0), frontend 100% on testable P0 UI, zero issues.
- STILL NEEDS REAL-TELEGRAM USER CONFIRMATION: actual 2-IP prevention across live containers, real button clicks, real Cloudflare verify — cannot be validated without the user's live Telegram account.
