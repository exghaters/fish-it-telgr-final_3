import { useEffect, useState } from "react";
import { toast } from "sonner";
import { TelegramLogo, CheckCircle, SignOut, Key, PaperPlaneTilt } from "@phosphor-icons/react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import api from "@/lib/api";

export default function TelegramSetup() {
  const [status, setStatus] = useState(null);
  const [step, setStep] = useState("creds"); // creds | phone | code | done
  const [apiId, setApiId] = useState("");
  const [apiHash, setApiHash] = useState("");
  const [phone, setPhone] = useState("+62");
  const [code, setCode] = useState("");
  const [twoFa, setTwoFa] = useState("");
  const [twoFaRequired, setTwoFaRequired] = useState(false);
  const [busy, setBusy] = useState(false);

  const loadStatus = async () => {
    try {
      const r = await api.get("/telegram/status");
      setStatus(r.data);
      if (r.data.connected) setStep("done");
      else if (r.data.api_id_set) setStep("phone");
    } catch { /* silent */ }
  };

  useEffect(() => {
    loadStatus();
  }, []);

  const saveCreds = async (e) => {
    e.preventDefault();
    setBusy(true);
    try {
      await api.post("/telegram/credentials", { api_id: parseInt(apiId), api_hash: apiHash });
      toast.success("API credentials tersimpan (encrypted)");
      setStep("phone");
      await loadStatus();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Gagal simpan");
    } finally {
      setBusy(false);
    }
  };

  const sendCode = async (e) => {
    e.preventDefault();
    setBusy(true);
    try {
      await api.post("/telegram/send-code", { phone });
      toast.success("Kode dikirim ke Telegram Anda");
      setStep("code");
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Gagal kirim kode");
    } finally {
      setBusy(false);
    }
  };

  const verify = async (e) => {
    e.preventDefault();
    setBusy(true);
    try {
      const r = await api.post("/telegram/verify", { code, password: twoFa || undefined });
      if (r.data?.two_fa_required) {
        setTwoFaRequired(true);
        toast.info("Akun ini memakai 2FA. Masukkan password Telegram Anda.");
      } else {
        toast.success(`Terhubung sebagai ${r.data?.display_name || phone}`);
        setStep("done");
        await loadStatus();
      }
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Verifikasi gagal");
    } finally {
      setBusy(false);
    }
  };

  const logout = async () => {
    if (!confirm("Logout dan hapus session Telegram?")) return;
    setBusy(true);
    try {
      await api.post("/telegram/logout");
      toast.success("Session Telegram dihapus");
      setApiId("");
      setApiHash("");
      setPhone("+62");
      setCode("");
      setTwoFa("");
      setStep("creds");
      await loadStatus();
    } catch (e) {
      toast.error("Gagal logout");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-8" data-testid="telegram-page">
      <div>
        <div className="text-xs uppercase tracking-widest text-pink-500 mb-2">Setup</div>
        <h1 className="font-heading text-3xl md:text-4xl font-bold">Login Telegram</h1>
        <p className="text-slate-400 mt-2 max-w-2xl">
          Automation memakai akun Telegram pribadi Anda (MTProto). Session tersimpan
          <span className="text-white"> terenkripsi (Fernet)</span> — hanya server yang bisa decrypt.
        </p>
      </div>

      {/* Status card */}
      <div
        className={`rounded-lg p-6 border ${
          status?.connected
            ? "border-green-500/30 bg-green-500/5"
            : "border-white/10 bg-[#0F0F16]"
        }`}
        data-testid="telegram-status-card"
      >
        <div className="flex items-center justify-between flex-wrap gap-4">
          <div className="flex items-center gap-4">
            <div
              className={`w-12 h-12 rounded-full flex items-center justify-center ${
                status?.connected ? "bg-green-500/20" : "bg-slate-500/20"
              }`}
            >
              <TelegramLogo
                size={24}
                weight="duotone"
                className={status?.connected ? "text-green-400" : "text-slate-400"}
              />
            </div>
            <div>
              <div className="font-heading text-lg font-bold" data-testid="telegram-status-label">
                {status?.connected ? "Terhubung" : "Belum terhubung"}
              </div>
              <div className="text-sm text-slate-400 font-mono">
                {status?.display_name || status?.phone || "—"}
              </div>
            </div>
          </div>
          {status?.connected && (
            <Button
              onClick={logout}
              variant="outline"
              disabled={busy}
              data-testid="telegram-logout"
              className="border-red-500/40 text-red-400 hover:bg-red-500/10 rounded-md"
            >
              <SignOut size={16} className="mr-2" /> Logout Telegram
            </Button>
          )}
        </div>
      </div>

      {/* Steps */}
      {step === "creds" && (
        <form onSubmit={saveCreds} className="border border-white/10 bg-[#0F0F16] rounded-lg p-6 space-y-5" data-testid="step-creds">
          <div>
            <h2 className="font-heading text-xl font-bold flex items-center gap-2">
              <Key size={20} className="text-pink-500" />
              Step 1: API Credentials
            </h2>
            <p className="text-sm text-slate-400 mt-1">
              Dapatkan gratis di{" "}
              <a
                href="https://my.telegram.org"
                target="_blank"
                rel="noopener noreferrer"
                className="text-pink-500 underline"
              >
                my.telegram.org
              </a>{" "}
              → API development tools.
            </p>
          </div>
          <div>
            <Label className="text-slate-300 mb-2 block">API ID (angka)</Label>
            <Input
              data-testid="input-api-id"
              type="number"
              required
              value={apiId}
              onChange={(e) => setApiId(e.target.value)}
              placeholder="1234567"
              className="bg-[#05050A] border-white/10 focus:border-pink-500 font-mono"
            />
          </div>
          <div>
            <Label className="text-slate-300 mb-2 block">API Hash</Label>
            <Input
              data-testid="input-api-hash"
              type="text"
              required
              value={apiHash}
              onChange={(e) => setApiHash(e.target.value)}
              placeholder="abc123def456..."
              className="bg-[#05050A] border-white/10 focus:border-pink-500 font-mono"
            />
          </div>
          <Button
            type="submit"
            disabled={busy}
            data-testid="save-creds"
            className="bg-pink-500 hover:bg-pink-600 text-black font-bold rounded-md"
          >
            Simpan & Lanjut
          </Button>
        </form>
      )}

      {step === "phone" && (
        <form onSubmit={sendCode} className="border border-white/10 bg-[#0F0F16] rounded-lg p-6 space-y-5" data-testid="step-phone">
          <div>
            <h2 className="font-heading text-xl font-bold flex items-center gap-2">
              <PaperPlaneTilt size={20} className="text-pink-500" />
              Step 2: Kirim Kode
            </h2>
            <p className="text-sm text-slate-400 mt-1">
              Kode 5 digit akan dikirim ke aplikasi Telegram Anda.
            </p>
          </div>
          <div>
            <Label className="text-slate-300 mb-2 block">Nomor HP (format internasional +62...)</Label>
            <Input
              data-testid="input-phone"
              type="tel"
              required
              value={phone}
              onChange={(e) => setPhone(e.target.value)}
              placeholder="+628123456789"
              className="bg-[#05050A] border-white/10 focus:border-pink-500 font-mono"
            />
          </div>
          <div className="flex gap-2">
            <Button
              type="submit"
              disabled={busy}
              data-testid="send-code-btn"
              className="bg-pink-500 hover:bg-pink-600 text-black font-bold rounded-md"
            >
              {busy ? "Mengirim..." : "Kirim Kode"}
            </Button>
            <Button
              type="button"
              variant="outline"
              onClick={() => setStep("creds")}
              className="border-white/10 rounded-md"
            >
              Ubah API
            </Button>
          </div>
        </form>
      )}

      {step === "code" && (
        <form onSubmit={verify} className="border border-white/10 bg-[#0F0F16] rounded-lg p-6 space-y-5" data-testid="step-code">
          <div>
            <h2 className="font-heading text-xl font-bold flex items-center gap-2">
              <CheckCircle size={20} className="text-pink-500" />
              Step 3: Masukkan Kode
            </h2>
            <p className="text-sm text-slate-400 mt-1">
              Cek Telegram Anda — kode dari akun resmi Telegram.
            </p>
          </div>
          <div>
            <Label className="text-slate-300 mb-2 block">Kode 5 digit</Label>
            <Input
              data-testid="input-code"
              type="text"
              inputMode="numeric"
              required
              minLength={3}
              value={code}
              onChange={(e) => setCode(e.target.value)}
              placeholder="12345"
              className="bg-[#05050A] border-white/10 focus:border-pink-500 font-mono text-center text-2xl h-14"
            />
          </div>
          {twoFaRequired && (
            <div>
              <Label className="text-slate-300 mb-2 block">Password 2FA Telegram</Label>
              <Input
                data-testid="input-2fa"
                type="password"
                required
                value={twoFa}
                onChange={(e) => setTwoFa(e.target.value)}
                className="bg-[#05050A] border-white/10 focus:border-pink-500 font-mono"
              />
            </div>
          )}
          <div className="flex gap-2">
            <Button
              type="submit"
              disabled={busy}
              data-testid="verify-btn"
              className="bg-pink-500 hover:bg-pink-600 text-black font-bold rounded-md"
            >
              {busy ? "Verifikasi..." : "Verifikasi"}
            </Button>
            <Button
              type="button"
              variant="outline"
              onClick={() => setStep("phone")}
              className="border-white/10 rounded-md"
            >
              Kirim Ulang
            </Button>
          </div>
        </form>
      )}

      {step === "done" && (
        <div className="border border-green-500/30 bg-green-500/5 rounded-lg p-6 text-center" data-testid="step-done">
          <CheckCircle size={48} className="text-green-500 mx-auto mb-4" weight="duotone" />
          <div className="font-heading text-2xl font-bold mb-2">Siap!</div>
          <p className="text-slate-400 mb-6">
            Telegram terhubung. Lanjutkan konfigurasi bot & grup Fish It.
          </p>
        </div>
      )}
    </div>
  );
}
