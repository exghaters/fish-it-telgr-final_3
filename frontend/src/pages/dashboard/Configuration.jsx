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

export default function Configuration() {
  const [cfg, setCfg] = useState(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api.get("/automation/config").then((r) => setCfg(r.data));
  }, []);

  const update = (k, v) => setCfg((c) => ({ ...c, [k]: v }));

  const save = async () => {
    setBusy(true);
    try {
      await api.put("/automation/config", cfg);
      toast.success("Konfigurasi tersimpan");
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Gagal simpan");
    } finally {
      setBusy(false);
    }
  };

  if (!cfg) return <div className="text-slate-500">Memuat...</div>;

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
          <Field label="Perintah Favorite (gunakan {n} untuk posisi)">
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
