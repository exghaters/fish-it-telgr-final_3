import { useEffect, useState } from "react";
import { toast } from "sonner";
import { FloppyDisk, Sliders } from "@phosphor-icons/react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import api from "@/lib/api";
import { useAuth } from "@/lib/auth.jsx";

const VIP_MULTI_PLANS = ["pro", "elite"];

export default function Configuration() {
  const { user } = useAuth();
  const vipMulti = VIP_MULTI_PLANS.includes((user?.plan || "free").toLowerCase());
  const [cfg, setCfg] = useState(null);
  const [busy, setBusy] = useState(false);
  const [advanced, setAdvanced] = useState(false);
  const [autoStopped, setAutoStopped] = useState(false);

  useEffect(() => {
    (async () => {
      const r = await api.get("/automation/config");
      setCfg(r.data);
      // Opening the config of a RUNNING account must stop it first so we never
      // run against a half-edited config. Only this account is affected.
      if (r.data?.enabled) {
        try {
          await api.post("/automation/stop");
          setCfg((c) => ({ ...c, enabled: false }));
          setAutoStopped(true);
          toast.info("Automation akun ini dihentikan karena konfigurasi sedang dibuka. Tekan Start untuk menjalankan lagi.");
        } catch {
          /* ignore */
        }
      }
    })();
  }, []);

  const update = (k, v) => setCfg((c) => ({ ...c, [k]: v }));

  const save = async () => {
    setBusy(true);
    try {
      const r = await api.put("/automation/config", { ...cfg, enabled: false });
      setCfg(r.data);
      setAutoStopped(true);
      toast.success("Konfigurasi tersimpan. Automation dalam kondisi STOP — tekan Start untuk menjalankan.");
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Gagal simpan");
    } finally {
      setBusy(false);
    }
  };

  if (!cfg) return <div className="text-slate-500">Memuat...</div>;

  const resetConfig = async () => {
    if (!window.confirm("Reset semua pengaturan ke rekomendasi default?")) return;
    try {
      const r = await api.post("/automation/config/reset");
      setCfg(r.data);
      toast.success("Direset ke pengaturan rekomendasi");
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Gagal reset");
    }
  };

  return (
    <div className="space-y-8" data-testid="config-page">
      <div className="flex items-start justify-between flex-wrap gap-4">
        <div>
          <div className="text-xs uppercase tracking-widest text-pink-500 mb-2">Konfigurasi</div>
          <h1 className="font-heading text-3xl md:text-4xl font-bold">Automation Config</h1>
          <p className="text-slate-400 mt-2 max-w-2xl">
            Sesuaikan target grup/bot, mode, perintah, dan pola deteksi. Default sudah sesuai
            <span className="text-white"> @fish_it_bot</span>.
          </p>
        </div>
        <div className="flex items-center gap-3 flex-wrap">
          <label className="flex items-center gap-2 text-sm text-slate-300 cursor-pointer">
            <Switch checked={advanced} onCheckedChange={setAdvanced} data-testid="advanced-mode-toggle" />
            Mode Lanjutan
          </label>
          <Button
            onClick={resetConfig}
            variant="outline"
            data-testid="reset-config"
            className="rounded-md border-white/15 text-slate-300 hover:text-pink-400"
          >
            Reset ke rekomendasi
          </Button>
          <Button
            onClick={save}
            disabled={busy}
            data-testid="save-config"
            className="bg-pink-500 hover:bg-pink-600 text-black font-bold rounded-md glow-pink"
          >
            <FloppyDisk size={16} className="mr-2" />
            {busy ? "Menyimpan..." : "Simpan"}
          </Button>
        </div>
      </div>

      <div
        data-testid="config-edit-warning"
        className="flex items-start gap-3 rounded-lg border border-amber-500/30 bg-amber-500/10 px-4 py-3 text-sm text-amber-200"
      >
        <span className="mt-0.5">⚠️</span>
        <p>
          Mengedit konfigurasi akan <span className="font-semibold">menghentikan automation akun ini</span>.
          {autoStopped && " Automation sudah dihentikan."} Setelah menyimpan, buka halaman{" "}
          <span className="font-semibold">Status</span> dan tekan <span className="font-semibold">Start</span> untuk menjalankan kembali. Akun Telegram lain tidak terpengaruh.
        </p>
      </div>

      <Section title="Target & Mode" icon={<Sliders size={18} />}>
        <div className="grid md:grid-cols-2 gap-4">
          <Field label="Mode Automation">
            <Select value={cfg.mode} onValueChange={(v) => update("mode", v)}>
              <SelectTrigger data-testid="select-mode" className="bg-[#05050A] border-white/10">
                <SelectValue />
              </SelectTrigger>
              <SelectContent className="bg-[#0F0F16] border-white/10">
                <SelectItem value="vip_direct">VIP Direct (DM bot 5 menit)</SelectItem>
                <SelectItem value="group">Group (via grup + Daftar Mancing)</SelectItem>
              </SelectContent>
            </Select>
          </Field>
          <div />
          <Field label="Bot Fish It (username DM)">
            <Input
              data-testid="input-bot-username"
              value={cfg.bot_username || ""}
              onChange={(e) => update("bot_username", e.target.value)}
              placeholder="@fish_it_bot"
              className="bg-[#05050A] border-white/10 font-mono"
            />
          </Field>
          <Field label="Grup Target (untuk mode Group)">
            <Input
              data-testid="input-group-username"
              value={cfg.group_username || ""}
              onChange={(e) => update("group_username", e.target.value)}
              placeholder="@namagrup"
              className="bg-[#05050A] border-white/10 font-mono"
            />
          </Field>
        </div>
      </Section>

      {advanced && (<>
      <Section title="Perintah Bot">
        <div className="grid md:grid-cols-2 gap-4">
          <Field label="Perintah Buka Mancing (DM/VIP)">
            <Input
              data-testid="input-open-command"
              value={cfg.open_command}
              onChange={(e) => update("open_command", e.target.value)}
              className="bg-[#05050A] border-white/10 font-mono"
            />
          </Field>
          <Field label="Perintah Buka Mancing (Grup)">
            <Input
              data-testid="input-group-open-command"
              value={cfg.group_open_command}
              onChange={(e) => update("group_open_command", e.target.value)}
              className="bg-[#05050A] border-white/10 font-mono"
            />
          </Field>
          <Field label='Tombol "Daftar Mancing"'>
            <Input
              data-testid="input-join-button"
              value={cfg.join_button_text}
              onChange={(e) => update("join_button_text", e.target.value)}
              className="bg-[#05050A] border-white/10 font-mono"
            />
          </Field>
          <Field label='Perintah Konfirmasi di DM Bot ("/start")'>
            <Input
              value={cfg.dm_confirm_command}
              onChange={(e) => update("dm_confirm_command", e.target.value)}
              className="bg-[#05050A] border-white/10 font-mono"
            />
          </Field>
          <Field label="Perintah Extract">
            <Input
              value={cfg.extract_command}
              onChange={(e) => update("extract_command", e.target.value)}
              className="bg-[#05050A] border-white/10 font-mono"
            />
          </Field>
          <Field label="Perintah Jual">
            <Input
              value={cfg.sell_command}
              onChange={(e) => update("sell_command", e.target.value)}
              className="bg-[#05050A] border-white/10 font-mono"
            />
          </Field>
          <Field label='Tombol "Ya, Jual Semua"'>
            <Input
              value={cfg.sell_confirm_button_text}
              onChange={(e) => update("sell_confirm_button_text", e.target.value)}
              className="bg-[#05050A] border-white/10 font-mono"
            />
          </Field>
          <Field label='Tombol "Batal"'>
            <Input
              value={cfg.sell_cancel_button_text}
              onChange={(e) => update("sell_cancel_button_text", e.target.value)}
              className="bg-[#05050A] border-white/10 font-mono"
            />
          </Field>
          <Field label="Perintah Inventory">
            <Input
              value={cfg.inventory_command}
              onChange={(e) => update("inventory_command", e.target.value)}
              className="bg-[#05050A] border-white/10 font-mono"
            />
          </Field>
          <Field label="Perintah Favorite ({n} = nomor, bisa banyak)">
            <Input
              value={cfg.favorite_command_template}
              onChange={(e) => update("favorite_command_template", e.target.value)}
              className="bg-[#05050A] border-white/10 font-mono"
            />
          </Field>
        </div>
      </Section>

      <Section title="Timing (detik)">
        <div className="grid md:grid-cols-4 gap-4">
          <Field label="Wait setelah Join (Grup)">
            <Input
              type="number"
              value={cfg.group_wait_seconds}
              onChange={(e) => update("group_wait_seconds", parseInt(e.target.value) || 0)}
              className="bg-[#05050A] border-white/10 font-mono"
            />
          </Field>
          <Field label="Durasi Fishing (Grup)">
            <Input
              type="number"
              value={cfg.group_fish_seconds}
              onChange={(e) => update("group_fish_seconds", parseInt(e.target.value) || 0)}
              className="bg-[#05050A] border-white/10 font-mono"
            />
          </Field>
          <Field label="Durasi Fishing (VIP)">
            <Input
              type="number"
              value={cfg.vip_fish_seconds}
              onChange={(e) => update("vip_fish_seconds", parseInt(e.target.value) || 0)}
              className="bg-[#05050A] border-white/10 font-mono"
            />
          </Field>
          <Field label="Jeda antar VIP">
            <Input
              type="number"
              value={cfg.vip_gap_seconds}
              onChange={(e) => update("vip_gap_seconds", parseInt(e.target.value) || 0)}
              className="bg-[#05050A] border-white/10 font-mono"
            />
          </Field>
          <Field label="Sell tiap N fishing">
            <Input
              type="number"
              value={cfg.extract_sell_every_n_fish}
              onChange={(e) =>
                update("extract_sell_every_n_fish", parseInt(e.target.value) || 1)
              }
              className="bg-[#05050A] border-white/10 font-mono"
            />
          </Field>
          <Field label="Item per Halaman /inventory">
            <Input
              type="number"
              value={cfg.inventory_page_size}
              onChange={(e) => update("inventory_page_size", parseInt(e.target.value) || 20)}
              className="bg-[#05050A] border-white/10 font-mono"
            />
          </Field>
        </div>
      </Section>

      <Section title="Deteksi Pola (Regex)">
        <div className="grid md:grid-cols-2 gap-4">
          <Field label="Pattern Sesi Selesai" hint="Regex — case-insensitive">
            <Input
              value={cfg.session_done_pattern}
              onChange={(e) => update("session_done_pattern", e.target.value)}
              className="bg-[#05050A] border-white/10 font-mono text-xs"
            />
          </Field>
          <Field label="Pattern Pendaftaran Grup">
            <Input
              value={cfg.pendaftaran_pattern}
              onChange={(e) => update("pendaftaran_pattern", e.target.value)}
              className="bg-[#05050A] border-white/10 font-mono text-xs"
            />
          </Field>
          <Field label="Pattern Rarity Gift (di teks jual)">
            <Input
              value={cfg.gift_rarity_pattern}
              onChange={(e) => update("gift_rarity_pattern", e.target.value)}
              className="bg-[#05050A] border-white/10 font-mono text-xs"
            />
          </Field>
          <Field label="Pattern Gift Banner (✨ ... ✨)">
            <Input
              value={cfg.gift_message_pattern || ""}
              onChange={(e) => update("gift_message_pattern", e.target.value)}
              className="bg-[#05050A] border-white/10 font-mono text-xs"
            />
          </Field>
          <Field label="Pattern Rare Fish (log only)">
            <Input
              value={cfg.rare_pattern}
              onChange={(e) => update("rare_pattern", e.target.value)}
              className="bg-[#05050A] border-white/10 font-mono text-xs"
            />
          </Field>
          <Field label='Pattern "Sedang Memancing" (perpanjang menunggu)'>
            <Input
              value={cfg.already_fishing_pattern || ""}
              onChange={(e) => update("already_fishing_pattern", e.target.value)}
              className="bg-[#05050A] border-white/10 font-mono text-xs"
            />
          </Field>
          <Field label="Pattern Extract List (Bisa di-extract...)">
            <Input
              value={cfg.extract_list_pattern || ""}
              onChange={(e) => update("extract_list_pattern", e.target.value)}
              className="bg-[#05050A] border-white/10 font-mono text-xs"
            />
          </Field>
          <Field label="Pattern Verifikasi">
            <Input
              value={cfg.verification_pattern}
              onChange={(e) => update("verification_pattern", e.target.value)}
              className="bg-[#05050A] border-white/10 font-mono text-xs"
            />
          </Field>
          <Field label='Text Tombol "Verifikasi Sekarang"'>
            <Input
              value={cfg.verification_button_text}
              onChange={(e) => update("verification_button_text", e.target.value)}
              className="bg-[#05050A] border-white/10 font-mono"
            />
          </Field>
          <Field label='Text Tombol "Next" Inventory'>
            <Input
              value={cfg.inventory_next_button_text}
              onChange={(e) => update("inventory_next_button_text", e.target.value)}
              className="bg-[#05050A] border-white/10 font-mono"
            />
          </Field>
        </div>
      </Section>

      </>)}

      <Section title="Filter Chat & Boost">
        <div className="grid md:grid-cols-2 gap-4">
          <Field
            label="Chat Tambahan yang Dibaca (pisahkan koma)"
            hint={
              vipMulti
                ? "Engine HANYA membaca pesan dari Bot, Grup Target, dan daftar ini. Chat/grup lain diabaikan — Activity Log jadi bersih."
                : "Paket Starter dibatasi 1 bot/grup saja. Upgrade ke Pro/Elite untuk pakai banyak bot VIP di sini."
            }
          >
            <Input
              data-testid="input-extra-allowed-chats"
              value={vipMulti ? (cfg.extra_allowed_chats || "") : ""}
              onChange={(e) => update("extra_allowed_chats", e.target.value)}
              disabled={!vipMulti}
              placeholder={vipMulti ? "@fish_it_vip_bot, @fish_it_vip3_bot" : "Khusus Pro/Elite"}
              className="bg-[#05050A] border-white/10 font-mono text-xs disabled:opacity-50 disabled:cursor-not-allowed"
            />
          </Field>
          <Field label="Perintah Boost (DM Bot)">
            <Input
              data-testid="input-boost-command"
              value={cfg.boost_command || ""}
              onChange={(e) => update("boost_command", e.target.value)}
              placeholder="/boost"
              className="bg-[#05050A] border-white/10 font-mono"
            />
          </Field>
          <Field
            label="Trigger Boost DM (Regex)"
            hint='Kirim /boost ke bot saat teks ini muncul di DM bot: "AUTO MANCING DIMULAI!"'
          >
            <Input
              data-testid="input-boost-trigger"
              value={cfg.boost_trigger_pattern || ""}
              onChange={(e) => update("boost_trigger_pattern", e.target.value)}
              className="bg-[#05050A] border-white/10 font-mono text-xs"
            />
          </Field>
          <Field label="Perintah Boost Grup">
            <Input
              data-testid="input-group-boost-command"
              value={cfg.group_boost_command || ""}
              onChange={(e) => update("group_boost_command", e.target.value)}
              placeholder="/boost_grup"
              className="bg-[#05050A] border-white/10 font-mono"
            />
          </Field>
          <Field
            label="Trigger Boost Grup (Regex)"
            hint='Kirim /boost_grup ke grup saat teks ini muncul: "Boost Grup Berakhir!" / "PERAHU SIAP BERANGKAT"'
          >
            <Input
              data-testid="input-group-boost-trigger"
              value={cfg.group_boost_trigger_pattern || ""}
              onChange={(e) => update("group_boost_trigger_pattern", e.target.value)}
              className="bg-[#05050A] border-white/10 font-mono text-xs"
            />
          </Field>
          <Field label="Cooldown Boost (detik)" hint="Durasi boost ±5 menit — tidak dikirim ulang selama cooldown">
            <Input
              type="number"
              data-testid="input-boost-cooldown"
              value={cfg.boost_cooldown_seconds ?? 300}
              onChange={(e) => update("boost_cooldown_seconds", parseInt(e.target.value) || 300)}
              className="bg-[#05050A] border-white/10 font-mono"
            />
          </Field>
        </div>
        <div className="flex items-center gap-3 mt-6">
          <Switch
            checked={!!cfg.boost_enabled}
            onCheckedChange={(v) => update("boost_enabled", v)}
            data-testid="switch-boost-enabled"
          />
          <div>
            <div className="text-sm text-slate-200 font-medium">Auto /boost & /boost_grup</div>
            <div className="text-xs text-slate-500">
              Bila ON, engine kirim boost otomatis saat pattern trigger muncul (opsional).
            </div>
          </div>
        </div>
      </Section>

      {advanced && (<>
      <Section title="Proteksi Ikan Langka (sebelum Jual)">
        <p className="text-xs text-slate-500 mb-4">
          Sebelum <span className="text-white font-mono">/jual semua</span>, engine buka
          <span className="text-white font-mono"> /inventory</span> dan memfavoritkan ikan langka
          (secret / celestial / secret_shiny) atau ikan bernilai tinggi, lalu di-skip dari
          penjualan. Dicek per halaman sampai halaman terakhir.
        </p>
        <div className="grid md:grid-cols-2 gap-4">
          <Field
            label="Pattern Rarity Dilindungi (Regex)"
            hint="Ikan dengan rarity ini TIDAK akan dijual (difavoritkan dulu)."
          >
            <Input
              data-testid="input-protect-rarity"
              value={cfg.protect_rarity_pattern || ""}
              onChange={(e) => update("protect_rarity_pattern", e.target.value)}
              className="bg-[#05050A] border-white/10 font-mono text-xs"
            />
          </Field>
          <Field
            label="Emoji Ringkasan Rarity (Regex)"
            hint="Jika ini muncul di ringkasan /inventory (✨/🌟/☀️), engine scan & favorit ikan langka."
          >
            <Input
              data-testid="input-rarity-summary"
              value={cfg.rarity_summary_pattern || ""}
              onChange={(e) => update("rarity_summary_pattern", e.target.value)}
              className="bg-[#05050A] border-white/10 font-mono text-xs"
            />
          </Field>
          <Field label="Min Coins Dilindungi" hint="Ikan dengan coins ≥ nilai ini juga difavoritkan (mis. 1.000.000).">
            <Input
              type="number"
              data-testid="input-protect-min-coins"
              value={cfg.protect_min_coins ?? 1000000}
              onChange={(e) => update("protect_min_coins", parseInt(e.target.value) || 0)}
              className="bg-[#05050A] border-white/10 font-mono"
            />
          </Field>
          <Field label="Max Halaman /inventory di-scan">
            <Input
              type="number"
              data-testid="input-inventory-max-pages"
              value={cfg.inventory_max_pages ?? 11}
              onChange={(e) => update("inventory_max_pages", parseInt(e.target.value) || 11)}
              className="bg-[#05050A] border-white/10 font-mono"
            />
          </Field>
        </div>
      </Section>

      <Section title="Grup & Verifikasi">
        <div className="grid md:grid-cols-2 gap-4">
          <Field
            label='Pattern "PENDAFTARAN DIBUKA" (grup)'
            hint='Saat muncul di grup → langsung tekan "Daftar Mancing" (skip /open_mancing).'
          >
            <Input
              data-testid="input-pendaftaran-open"
              value={cfg.pendaftaran_open_pattern || ""}
              onChange={(e) => update("pendaftaran_open_pattern", e.target.value)}
              className="bg-[#05050A] border-white/10 font-mono text-xs"
            />
          </Field>
          <Field
            label='Pattern "WAKTU HABIS!" (grup)'
            hint="Saat muncul di grup → kirim /open_mancing@<bot> ke grup (bot disesuaikan dari 'Bot Fish It')."
          >
            <Input
              data-testid="input-waktu-habis"
              value={cfg.waktu_habis_pattern || ""}
              onChange={(e) => update("waktu_habis_pattern", e.target.value)}
              className="bg-[#05050A] border-white/10 font-mono text-xs"
            />
          </Field>
          <Field
            label="Keyword Resume Verifikasi"
            hint="Setelah verifikasi manual selesai, ketik keyword ini di chat bot untuk lanjut otomatis."
          >
            <Input
              data-testid="input-resume-keyword"
              value={cfg.resume_keyword || ""}
              onChange={(e) => update("resume_keyword", e.target.value)}
              placeholder="dvk"
              className="bg-[#05050A] border-white/10 font-mono"
            />
          </Field>
        </div>
      </Section>

      </>)}

      <Section title="Auto-Start">
        <div className="flex items-center gap-3">
          <Switch
            checked={cfg.enabled}
            onCheckedChange={(v) => update("enabled", v)}
            data-testid="switch-enabled"
          />
          <div>
            <div className="text-sm text-slate-200 font-medium">Enable Automation</div>
            <div className="text-xs text-slate-500">
              Bila ON, tombol Start akan mengaktifkan loop. Bila OFF, automation di-pause.
            </div>
          </div>
        </div>
      </Section>

      <div className="flex justify-end">
        <Button
          onClick={save}
          disabled={busy}
          className="bg-pink-500 hover:bg-pink-600 text-black font-bold rounded-md glow-pink"
        >
          <FloppyDisk size={16} className="mr-2" />
          Simpan Konfigurasi
        </Button>
      </div>
    </div>
  );
}

function Section({ title, icon, children }) {
  return (
    <div className="border border-white/10 bg-[#0F0F16] rounded-lg p-6">
      <div className="flex items-center gap-2 mb-6">
        {icon && <span className="text-pink-500">{icon}</span>}
        <h3 className="font-heading text-lg font-bold">{title}</h3>
      </div>
      {children}
    </div>
  );
}

function Field({ label, hint, children }) {
  return (
    <div>
      <Label className="text-slate-300 text-xs mb-2 block">{label}</Label>
      {children}
      {hint && <div className="text-[11px] text-slate-600 mt-1">{hint}</div>}
    </div>
  );
}
