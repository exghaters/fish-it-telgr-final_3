import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import {
  Play,
  Stop,
  Pause,
  ArrowClockwise,
  Fish,
  Waveform,
  Warning,
  CheckCircle,
  Timer,
  LinkSimple,
} from "@phosphor-icons/react";
import { Button } from "@/components/ui/button";
import api from "@/lib/api";

const STATUS_STYLES = {
  idle: { color: "text-slate-400", bg: "bg-slate-500/10", border: "border-slate-500/30", dot: "bg-slate-500" },
  starting: { color: "text-cyan-400", bg: "bg-cyan-500/10", border: "border-cyan-500/30", dot: "bg-cyan-500" },
  opening: { color: "text-cyan-400", bg: "bg-cyan-500/10", border: "border-cyan-500/30", dot: "bg-cyan-500" },
  joining: { color: "text-cyan-400", bg: "bg-cyan-500/10", border: "border-cyan-500/30", dot: "bg-cyan-500" },
  waiting: { color: "text-yellow-400", bg: "bg-yellow-500/10", border: "border-yellow-500/30", dot: "bg-yellow-500" },
  fishing: { color: "text-green-400", bg: "bg-green-500/10", border: "border-green-500/30", dot: "bg-green-500" },
  extracting: { color: "text-pink-400", bg: "bg-pink-500/10", border: "border-pink-500/30", dot: "bg-pink-500" },
  selling: { color: "text-pink-400", bg: "bg-pink-500/10", border: "border-pink-500/30", dot: "bg-pink-500" },
  inventory: { color: "text-pink-400", bg: "bg-pink-500/10", border: "border-pink-500/30", dot: "bg-pink-500" },
  favoriting: { color: "text-pink-400", bg: "bg-pink-500/10", border: "border-pink-500/30", dot: "bg-pink-500" },
  verifying: { color: "text-orange-400", bg: "bg-orange-500/10", border: "border-orange-500/30", dot: "bg-orange-500" },
  paused: { color: "text-yellow-400", bg: "bg-yellow-500/10", border: "border-yellow-500/30", dot: "bg-yellow-500" },
  stopped: { color: "text-slate-500", bg: "bg-slate-500/10", border: "border-slate-500/30", dot: "bg-slate-500" },
  error: { color: "text-red-400", bg: "bg-red-500/10", border: "border-red-500/30", dot: "bg-red-500" },
};

const STATUS_LABEL = {
  idle: "Idle",
  starting: "Memulai",
  opening: "Membuka Mancing",
  joining: "Daftar Mancing",
  waiting: "Menunggu",
  fishing: "Mancing",
  extracting: "Extract",
  selling: "Menjual",
  inventory: "Buka Inventory",
  favoriting: "Favoritkan",
  verifying: "Verifikasi",
  paused: "Dijeda",
  stopped: "Berhenti",
  error: "Error",
};

function formatDuration(sec) {
  if (!sec || sec < 0) return "00:00";
  const m = Math.floor(sec / 60);
  const s = sec % 60;
  return `${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
}

function formatSince(iso) {
  if (!iso) return "—";
  const then = new Date(iso).getTime();
  const diff = Math.floor((Date.now() - then) / 1000);
  if (diff < 60) return `${diff}s`;
  if (diff < 3600) return `${Math.floor(diff / 60)}m ${diff % 60}s`;
  return `${Math.floor(diff / 3600)}h ${Math.floor((diff % 3600) / 60)}m`;
}

export default function Status() {
  const [status, setStatus] = useState(null);
  const [tg, setTg] = useState(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      const [s, t] = await Promise.all([
        api.get("/automation/status"),
        api.get("/telegram/status"),
      ]);
      setStatus(s.data);
      setTg(t.data);
    } catch {
      /* silent: background poll */
    }
  }, []);

  useEffect(() => {
    load();
    const t = setInterval(load, 2000);
    return () => clearInterval(t);
  }, [load]);

  const act = async (path, msg) => {
    setBusy(true);
    try {
      await api.post(`/automation/${path}`);
      toast.success(msg);
      await load();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Gagal");
    } finally {
      setBusy(false);
    }
  };

  const s = status?.status || "idle";
  const style = STATUS_STYLES[s] || STATUS_STYLES.idle;
  const isActive = !["idle", "stopped", "paused", "error"].includes(s);

  return (
    <div className="space-y-8" data-testid="status-page">
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <div className="text-xs uppercase tracking-widest text-pink-500 mb-2">Dashboard</div>
          <h1 className="font-heading text-3xl md:text-4xl font-bold">Status Automation</h1>
        </div>
        <div className="flex gap-2 flex-wrap">
          {!isActive && s !== "paused" && (
            <Button
              onClick={() => act("start", "Automation dimulai")}
              disabled={busy}
              data-testid="btn-start"
              className="bg-pink-500 hover:bg-pink-600 text-black font-bold rounded-md glow-pink"
            >
              <Play size={16} weight="fill" className="mr-2" /> Start
            </Button>
          )}
          {isActive && (
            <Button
              onClick={() => act("pause", "Dijeda")}
              disabled={busy}
              data-testid="btn-pause"
              variant="outline"
              className="border-yellow-500/40 text-yellow-400 hover:bg-yellow-500/10 rounded-md"
            >
              <Pause size={16} className="mr-2" /> Pause
            </Button>
          )}
          {s === "paused" && (
            <Button
              onClick={() => act("resume", "Dilanjutkan")}
              disabled={busy}
              data-testid="btn-resume"
              className="bg-green-500 hover:bg-green-600 text-black font-bold rounded-md"
            >
              <ArrowClockwise size={16} className="mr-2" /> Resume
            </Button>
          )}
          {(isActive || s === "paused") && (
            <Button
              onClick={() => act("stop", "Automation dihentikan")}
              disabled={busy}
              data-testid="btn-stop"
              variant="outline"
              className="border-red-500/40 text-red-400 hover:bg-red-500/10 rounded-md"
            >
              <Stop size={16} weight="fill" className="mr-2" /> Stop
            </Button>
          )}
        </div>
      </div>

      {/* Big status card */}
      <div className={`trace-border rounded-xl p-8`} data-testid="status-card">
        <div className="flex items-start justify-between mb-6 flex-wrap gap-4">
          <div className="flex items-center gap-3">
            <span className={`w-3 h-3 rounded-full ${style.dot} ${isActive ? "dot-pulse" : ""}`} />
            <span className={`text-xs uppercase tracking-widest ${style.color} font-mono`}>
              {STATUS_LABEL[s] || s}
            </span>
          </div>
          <span className="text-xs text-slate-500 font-mono">
            {status?.mode === "vip_direct" ? "VIP DIRECT" : "GROUP"}
          </span>
        </div>
        <div className="grid md:grid-cols-4 gap-6">
          <div>
            <div className="text-xs text-slate-500 uppercase tracking-widest mb-2">Cycle</div>
            <div className="font-heading text-3xl font-bold" data-testid="status-cycle">
              #{status?.cycle ?? 0}
            </div>
          </div>
          <div>
            <div className="text-xs text-slate-500 uppercase tracking-widest mb-2">Ikan Tertangkap</div>
            <div className="font-heading text-3xl font-bold text-pink-500" data-testid="status-fish-caught">
              {status?.fish_caught ?? 0}
            </div>
          </div>
          <div>
            <div className="text-xs text-slate-500 uppercase tracking-widest mb-2">Uptime</div>
            <div className="font-heading text-3xl font-bold text-yellow-500" data-testid="status-uptime">
              {formatSince(status?.started_at)}
            </div>
          </div>
          <div>
            <div className="text-xs text-slate-500 uppercase tracking-widest mb-2">Countdown</div>
            <div className="font-mono text-3xl font-bold" data-testid="status-countdown">
              {formatDuration(status?.countdown_seconds || 0)}
            </div>
          </div>
        </div>

        {status?.last_error && (
          <div className="mt-6 flex items-start gap-2 p-4 rounded-md bg-red-500/10 border border-red-500/30 text-red-300 text-sm">
            <Warning size={18} className="mt-0.5 shrink-0" />
            <div data-testid="status-error">{status.last_error}</div>
          </div>
        )}
        {status?.verification_url && (
          <div className="mt-6 flex items-start gap-3 p-4 rounded-md bg-orange-500/10 border border-orange-500/30 text-orange-200 text-sm">
            <LinkSimple size={18} className="mt-0.5 shrink-0" />
            <div className="flex-1 min-w-0" data-testid="status-verification">
              <div className="font-semibold mb-1">Verifikasi Diperlukan</div>
              <div className="text-xs mb-2">Buka Mini App URL di bawah, selesaikan verifikasi, lalu klik Resume.</div>
              <a
                href={status.verification_url}
                target="_blank"
                rel="noopener noreferrer"
                className="text-orange-300 underline text-xs break-all"
                data-testid="verification-link"
              >
                {status.verification_url}
              </a>
            </div>
          </div>
        )}
      </div>

      {/* Sub cards */}
      <div className="grid md:grid-cols-3 gap-4">
        <SubCard
          icon={<Fish size={20} weight="duotone" />}
          label="Telegram"
          value={tg?.connected ? tg?.display_name || tg?.phone || "Terhubung" : "Belum terhubung"}
          sub={tg?.connected ? "Session aktif" : "Setup diperlukan"}
          ok={tg?.connected}
          testid="sub-telegram"
        />
        <SubCard
          icon={<Waveform size={20} weight="duotone" />}
          label="Sejak Sell Terakhir"
          value={`${status?.fish_since_sell ?? 0} sesi`}
          sub="Extract & jual tiap 3 sesi"
          ok
          testid="sub-fish-since-sell"
        />
        <SubCard
          icon={<Timer size={20} weight="duotone" />}
          label="Action Terakhir"
          value={formatSince(status?.last_action_at)}
          sub={status?.last_message || "—"}
          ok
          testid="sub-last-action"
        />
      </div>
    </div>
  );
}

function SubCard({ icon, label, value, sub, ok, testid }) {
  return (
    <div className="border border-white/10 bg-[#0F0F16] rounded-lg p-5" data-testid={testid}>
      <div className="flex items-center justify-between mb-3">
        <div className={ok ? "text-pink-400" : "text-slate-500"}>{icon}</div>
        {ok ? (
          <CheckCircle size={16} className="text-green-500" />
        ) : (
          <Warning size={16} className="text-yellow-500" />
        )}
      </div>
      <div className="text-xs text-slate-500 uppercase tracking-widest mb-1">{label}</div>
      <div className="font-heading text-lg font-bold truncate">{value}</div>
      <div className="text-xs text-slate-500 mt-1 truncate">{sub}</div>
    </div>
  );
}
