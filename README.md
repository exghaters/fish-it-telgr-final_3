# Fish It Automation Dashboard

Automation dashboard untuk mengoperasikan game Telegram **Fish It** memakai akun
Telegram personal (MTProto/Telethon). Model produk = **joki/operator**: admin
membuat akun operator, tiap operator mengelola beberapa akun Telegram pelanggan
yang terisolasi satu sama lain.

> ⚠️ Dokumen ini mencerminkan kode aktual per iterasi terakhir. Perbaikan
> automation terbaru ada di lingkungan preview/kode; **produksi harus di-redeploy**
> agar perubahan aktif.

---

## 1. Project Overview
- **Nama:** Fish It Automation Dashboard.
- **Fungsi utama:** login akun Telegram personal, membaca pesan/log bot Fish It,
  lalu menjalankan aksi (kirim command, klik tombol inline, ikuti deep-link)
  secara **event-driven** untuk otomasi mancing (private & group), boost,
  verifikasi, dan manajemen inventory.
- **Tujuan:** operator dapat menjalankan banyak akun Telegram pelanggan dari satu
  dashboard web tanpa harus memegang HP tiap pelanggan.
- **Gambaran singkat:** Frontend React → Backend FastAPI (`/api/*`) → Telegram
  Manager (Telethon) + Automation Engine → MongoDB.

## 2. Architecture
```
Frontend (React, CRACO)
        │  REST /api/*  (cookie httpOnly + Bearer)
        ▼
Backend API (FastAPI, server.py + *_routes.py)
        │
        ├── Telegram Manager (telegram_manager.py, Telethon)  ── satu client per akey
        │
        └── Automation Engine (automation_engine.py)          ── satu runner per akey
        │
        ▼
MongoDB (users, telegram_sessions, automation_configs, automation_state, events, …)
```
Satu **akun web** memiliki satu atau lebih **akun Telegram**. Tiap pasangan
`(web_user, telegram_account)` diidentifikasi oleh **akey** = `"{user_id}:{account_id}"`
dan memiliki config, session, state, runner, dan log sendiri.

## 3. Account & Session Model
- **Web account** (`users`): role `admin` atau `user` (operator). Auth JWT via
  cookie httpOnly (header `Authorization` diprioritaskan, cookie sebagai fallback).
- **Telegram account** (`telegram_accounts`): metadata akun Telegram milik satu
  operator (label pelanggan, dsb).
- **akey**: `"{web_user_id}:{telegram_account_id}"` — kunci isolasi untuk semua
  data & runtime.
- **Telegram session** (`telegram_sessions`): StringSession Telethon terenkripsi
  (Fernet), plus `phone`, `display_name`, `api_id`, `api_hash_enc`, dan flag
  `authorized`.
- **Telethon client**: satu `UserTelegram` per akey di registry proses.
- **Automation runner**: satu `AutomationRunner` per akey (asyncio task).
- **Isolasi**: registry & lock di-key per akey; runner & config per akey; query DB
  selalu di-scope `user_id == akey` (lihat `deps.get_account_key`).
- **Cegah duplicate session / lease**: `telegram_locks` menyimpan kepemilikan
  session per akey (`_id = akey`, `owner = INSTANCE_ID`, `heartbeat`). Sebelum
  membuka koneksi Telethon, `get_or_create` **mengklaim lease** (TTL 60s, refresh
  20s). Worker/replica lain tidak bisa membuka client untuk akey yang sama →
  mencegah error `AUTH_KEY_DUPLICATED` ("authorization key used under two IPs").
  Lease basi (proses mati) otomatis diambil-alih; dilepas saat logout/shutdown.
- **Status stabil**: cek status **tidak** menghidupkan client. `get_meta` membaca
  flag `authorized` dari DB, sehingga status konsisten di semua worker dan tidak
  meminta nomor HP berulang. Flag dikoreksi otomatis saat client benar-benar
  connect (login / start automation).

## 4. Telegram Automation Flow
Automation **event-driven**: menunggu pattern log Telegram, lalu bertindak.

**PRIVATE (`mode = vip_direct`)**
```
/mancing (open_command)
  → tunggu "AUTO MANCING DIMULAI"     → jika boost_enabled: /boost
  → monitor sesi
  → tunggu "SESI MANCING SELESAI" / "WAKTU HABIS" / hasil tangkapan
  → /mancing lagi (ulangi)
```

**GROUP (`mode = group`)**
```
/open_mancing@<bot> (group_open_command)
  → tunggu "PENDAFTARAN DIBUKA"
  → cari & klik tombol "Daftar Mancing"
  → tombol = deep-link t.me/<bot>?start=<payload> → kirim "/start <payload>" ke bot
  → tunggu "Sudah Terdaftar" / sesi dimulai
  → tunggu "WAKTU HABIS" / "SESI MANCING SELESAI"
  → /open_mancing lagi (ulangi)
```
Tombol join dicari dengan **polling ~20 detik** memindai s/d 50 pesan grup terbaru
(grup ramai sering menggeser pesan). Dedupe join memakai **message id**: countdown
"PENDAFTARAN DIBUKA" yang di-edit (60→59…) memakai id yang sama → tidak
mendaftar ulang; ronde baru = id baru → mendaftar lagi.

## 5. Verification Flow
```
Bot kirim "🔒 Verifikasi Diperlukan" (verification_pattern)
  → engine cari tombol (pinned + 20 pesan terakhir) yang match verification_button_text ("verifikasi")
  → klik tombol / invoke WebView (best-effort, hanya paket Pro/Elite; lainnya = manual)
  → tunggu ~30s pola sukses/AUTO MANCING → jika sukses: resend pending command otomatis
  → jika gagal / Cloudflare butuh interaksi: PAUSE + notifikasi + tombol "Resume" di dashboard
```
> Telethon **tidak** bisa menyelesaikan checkbox/puzzle Cloudflare. Untuk challenge
> nyata, verifikasi manual + resume adalah fallback yang didukung.

**DVK (resume keyword, default `dvk`)**: jika operator mengetik `dvk` di chat bot,
handler pesan keluar akan menganggap verifikasi selesai → resume state → engine
mengirim ulang command yang tertunda (mis. `/mancing`). Operator tidak perlu
mengetik `/mancing` manual.

## 6. Command `st`
`st` = force-restart / recovery. Jika operator mengetik `st` di chat bot:
- **PRIVATE:** kirim `/mancing` lagi → tunggu "AUTO MANCING DIMULAI" → (boost).
- **GROUP:** kirim `/open_mancing`, reset penanda join → tunggu "PENDAFTARAN
  DIBUKA" → klik "Daftar Mancing" → proses deep-link `/start`.
`st` selalu menghasilkan aksi (bukan no-op); antrian event basi di-drain dulu.

## 7. Event-Driven System
Telegram message/event/log adalah **source of truth**. Handler Telethon
(`NewMessage` + `MessageEdited`, incoming) mem-push ke antrian per akey; hanya chat
yang di-whitelist (bot + group + extra) yang diproses. Detector pattern (config,
case-insensitive) memetakan event → aksi berikut:

| Event pattern (default) | Aksi |
|---|---|
| `AUTO MANCING DIMULAI` | kirim `/boost` (jika boost aktif) |
| `PENDAFTARAN DIBUKA` | cari & klik tombol "Daftar Mancing" |
| `PENDAFTARAN DIBATALKAN` / tidak ada peserta | buka ulang `/open_mancing` |
| `SESI MANCING SELESAI` / hasil tangkapan | proses hasil → cycle berikutnya |
| `WAKTU HABIS` | buka registrasi lagi |
| `🔒 Verifikasi` | flow verifikasi (klik / pause) |
| inventory penuh | flow inventory existing |

Setiap `_wait_*` punya **timeout** & **retry terbatas**; tidak memakai fixed
`sleep` panjang untuk menggantikan deteksi event.

## 8. Inventory
> **Logic inventory sudah WORK 100% dan TIDAK diubah.** Bagian ini hanya
> mendokumentasikan perilaku yang ada.
- Deteksi **inventory full** via pattern (config) saat muncul di log bot.
- Saat penuh → jalankan flow inventory existing (scan → proteksi ikan langka →
  extract → sell) sesuai implementasi yang sudah ada.
- **Pagination**: kirim `/inventory` → tunggu message halaman → parse → klik
  tombol "Next" bila ada → tunggu halaman berikutnya (menunggu message, bukan
  `sleep`).
- Konfigurasi "clear inventory tiap N sesi" tetap tersedia (lihat Configuration).

## 9. Scheduler & Duplicate Prevention
- Automation bersifat event-driven; scheduler/loop hanya sebagai trigger/cek.
- **Group join** idempotent per ronde via `_joined_message_id` (satu registrasi
  per message id "PENDAFTARAN DIBUKA").
- Command tidak dikirim ulang saat pesan yang sama di-edit (countdown).
- `_drain_queue` membuang event basi sebelum aksi baru.
- **Catatan:** jika operator memakai fitur **Telegram Scheduled Message** bawaan
  Telegram untuk mengirim `/start payload` berkali-kali, itu berasal dari Telegram
  (bukan automation) dan harus dimatikan dari sisi akun Telegram — automation
  sendiri tidak menggandakan command.

## 10. Configuration (Dashboard)
Halaman **Konfigurasi** (mode Sederhana + toggle **Mode Lanjutan**, tombol **Reset
ke rekomendasi**):
- Mode `private (vip_direct)` / `group`, target bot & group.
- `open_command` (private), `group_open_command` (group), `join_button_text`.
- Auto boost on/off (`boost_enabled`) + pola trigger boost.
- Pola deteksi (regex) event (Mode Lanjutan).
- Timing (`vip_fish_seconds`, `group_fish_seconds`, `vip_gap_seconds`).
- Verifikasi: `resume_keyword` (dvk), `verification_button_text`.
- Inventory: interval "clear tiap N sesi" (konfigurasi dipertahankan).
> Membuka/menyimpan konfigurasi akun yang sedang jalan akan **menghentikan
> automation akun itu** (bukan akun lain); operator harus menekan **Start** lagi.

## 11. Database (MongoDB)
| Collection | Fungsi |
|---|---|
| `users` | akun web (admin/operator), plan, hash password |
| `telegram_accounts` | metadata akun Telegram per operator |
| `telegram_sessions` | session Telethon terenkripsi + flag `authorized` (key: akey) |
| `telegram_locks` | lease kepemilikan session per akey (cegah duplicate) |
| `automation_configs` | konfigurasi automation per akey |
| `automation_state` | state runtime (status, countdown, verification_url) per akey |
| `events` | log Activity (message-in/out, click, verification, dsb) |
| `notifications` | notifikasi dashboard (mis. butuh verifikasi manual) |
| `login_attempts` | catatan rate-limit / lockout login |
> Tidak menyimpan/menampilkan credential mentah; session & api_hash dienkripsi.

## 12. Environment Variables (nama saja, tanpa nilai)
Backend (`backend/.env`):
```
MONGO_URL=
DB_NAME=
CORS_ORIGINS=
JWT_SECRET=
SESSION_FERNET_KEY=
ADMIN_EMAIL=
ADMIN_PASSWORD=
ALLOW_PUBLIC_REGISTRATION=
```
Frontend (`frontend/.env`):
```
REACT_APP_BACKEND_URL=
WDS_SOCKET_PORT=
ENABLE_HEALTH_CHECK=
```
Telegram API ID / API Hash / phone / OTP / 2FA diberikan per akun oleh
operator/pelanggan melalui halaman Telegram Setup (tidak disimpan di .env).

## 13. Local Development
```bash
# Backend
cd backend
pip install -r requirements.txt
# service dijalankan via supervisor (0.0.0.0:8001), jangan start uvicorn manual

# Frontend
cd frontend
yarn install
# service via supervisor (port 3000)

# Restart bila ubah .env / dependency
sudo supervisorctl restart backend
sudo supervisorctl restart frontend

# Test backend
cd backend && python -m pytest tests/ -q
```

## 14. Production / Deployment
- Backend disarankan **1 worker uvicorn** untuk kepemilikan session Telegram paling
  bersih. Jika terpaksa multi-worker/replica, `telegram_locks` (session lease)
  menjamin hanya satu proses memegang client per akey, dan status dibaca dari flag
  DB (tidak flip-flop).
- Pastikan tidak ada dua instance memakai session yang sama secara bersamaan
  (lease mencegah ini secara internal; hindari juga menjalankan salinan lokal
  dengan session produksi).
- Routing: semua endpoint backend berprefix `/api`. Frontend memakai
  `REACT_APP_BACKEND_URL`.
- Setelah perubahan kode, **Deploy/Redeploy** agar produksi memakai versi terbaru.

## 15. Testing
Test suite: `backend/tests/` (pytest, `-n 2 loadscope`). Cakupan a.l.:
- P0 & regression API, auth cookie, admin guards (`test_iter19_p0_verify`, `backend_test`).
- Session lease cross-process (`test_iter19_session_lease`).
- Multi-account isolation & plan limit (`test_iter8_multiaccount`).
- Group join tombol/retry & grup ramai (`test_iter20`, `test_iter22`).
- Register sekali per ronde (`test_iter23`).
- Status Telegram stabil (`test_iter24`).
- `st`/`dvk` trigger (`test_iter25`).
- Config-edit auto-stop (`test_iter21`), boost/verify (`test_iter5`, `test_iter15`, `test_iter18`).

**Hasil FINAL yang dijalankan:** `206 passed, 1 skipped, 0 failed`.

## 16. Troubleshooting
| Symptom | Cause | Solution |
|---|---|---|
| Session collision / "authorization key used under two IPs" | dua proses memakai session sama | pakai 1 worker atau andalkan `telegram_locks` lease; jangan jalankan salinan dengan session yang sama |
| Duplicate `/start` / "Sudah Terdaftar" berulang | Telegram Scheduled Message user, atau edit countdown | dedupe `_joined_message_id` (otomatis); matikan Scheduled Message bawaan Telegram |
| Tombol "Daftar Mancing" tidak ketemu | grup ramai / tombol muncul via edit | engine polling ~20s & scan 50 pesan; redeploy bila produksi masih kode lama |
| Registration gagal | bot minta verifikasi setelah `/start` | selesaikan verifikasi lalu ketik `dvk` / klik Resume |
| Verifikasi pending | Cloudflare butuh interaksi manual | verifikasi manual di Telegram → `dvk` / Resume |
| Status flip-flop / minta nomor HP | rehydrate client saat polling di multi-worker (kode lama) | status kini baca flag DB (`get_meta`); redeploy produksi |
| Database connection failure | `MONGO_URL`/`DB_NAME` salah | perbaiki `.env`, restart backend |
| Backend restart | perubahan .env/dependency | `sudo supervisorctl restart backend`, cek `/var/log/supervisor/backend.*.log` |
| Session lease conflict | worker lain memegang lease fresh | tunggu TTL / stop instance lain; lease basi diambil-alih otomatis |

## 17. File Structure
```
/app
├── backend/
│   ├── server.py             # FastAPI app, startup, seed admin (+ self-heal), indexes
│   ├── deps.py               # Mongo client, Fernet, auth deps, get_account_key, plan_limits
│   ├── models.py             # Pydantic models (User, AutomationConfig, State, …)
│   ├── auth_routes.py        # login/register/logout (cookie + Bearer), rate limit
│   ├── admin_routes.py       # kelola operator; admin tak bisa dinonaktifkan/dihapus
│   ├── tg_routes.py          # Telegram: accounts, send-code, verify, status, logout
│   ├── automation_routes.py  # config (+reset), start/stop, status, events, notifications
│   ├── telegram_manager.py   # Telethon client registry, session lease, get_meta
│   ├── automation_engine.py  # runner per akey, event-driven flow (private/group/verify/st)
│   └── tests/                # pytest
├── frontend/src/
│   ├── App.js                # routing
│   ├── lib/ (api.js, auth.jsx, log.js)
│   └── pages/ (Landing, Login, DashboardLayout)
│       └── dashboard/ (Status, Configuration, TelegramSetup, Activity, Notifications, Admin, Pricing)
└── memory/ (PRD.md, CHANGELOG, test_credentials.md)
```

## 18. Security Notes
- Jangan commit secrets; semua via environment variables.
- Session Telegram & api_hash disimpan **terenkripsi** (Fernet `SESSION_FERNET_KEY`).
- Auth JWT (cookie httpOnly), password di-hash; min 8 karakter.
- Rate-limit / lockout login (`login_attempts`).
- Admin dilindungi: self-heal aktif saat startup, tidak bisa dinonaktifkan/dihapus.
- Registrasi publik dimatikan kecuali `ALLOW_PUBLIC_REGISTRATION` diaktifkan.
- Jangan expose credential/OTP/2FA/session/JWT/Mongo URL/Fernet key.

## 19. Current Limitations
- **Automated-test verified:** lease session, isolasi multi-account, logic join
  tombol (unit), register-once, status stabil, `st`/`dvk` handler, admin guards,
  config-edit-stop → `206 passed`.
- **Belum diverifikasi live di Telegram nyata:** klik tombol join & verifikasi di
  grup Fish It sungguhan, resume `dvk` end-to-end via app resmi, pencegahan 2-IP
  lintas container live, dan urutan `/mancing → AUTO MANCING → /boost` di sesi
  nyata. Butuh konfirmasi operator dengan akun Telegram aktif.
- Bukan klaim bebas bug; Cloudflare visual tetap perlu verifikasi manual.

## 20. Changelog (ringkas, terbaru)
- **Session isolation & lease:** `telegram_locks` mencegah duplicate client
  lintas worker; status dibaca dari flag `authorized` (tidak flip-flop / minta HP).
- **Group registration:** klik tombol "Daftar Mancing" via deep-link `/start`,
  scan 50 pesan (grup ramai), register sekali per ronde (dedupe message id).
- **Verification:** klik tombol "Verifikasi Sekarang" (best-effort) + pause/manual
  + resume; resend command tertunda setelah verifikasi.
- **`/dvk`:** resume + lanjut `/mancing` otomatis tanpa ketik manual.
- **`st`:** force-restart flow (private `/mancing`, group `/open_mancing`).
- **Duplicate prevention:** dedupe join per message id + drain antrian.
- **UI configuration:** mode Sederhana/Lanjutan + Reset; edit config auto-stop
  akun terkait.
- **Bug fixes:** admin tak bisa dinonaktifkan/dihapus; cleanup akun test.
