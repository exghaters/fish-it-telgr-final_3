import { useEffect, useState } from "react";
import { toast } from "sonner";
import {
  BellRinging,
  Sparkle,
  ShieldWarning,
  Fish,
  ArrowSquareOut,
  Check,
  CheckSquare,
  Play,
} from "@phosphor-icons/react";
import { Button } from "@/components/ui/button";
import api from "@/lib/api";

const KIND_ICONS = {
  gift: { i: Sparkle, c: "text-pink-500 bg-pink-500/10" },
  special: { i: Sparkle, c: "text-pink-500 bg-pink-500/10" },
  rare: { i: Fish, c: "text-yellow-500 bg-yellow-500/10" },
  verification: { i: ShieldWarning, c: "text-orange-500 bg-orange-500/10" },
  error: { i: ShieldWarning, c: "text-red-500 bg-red-500/10" },
  info: { i: BellRinging, c: "text-cyan-400 bg-cyan-500/10" },
};

function timeAgo(iso) {
  if (!iso) return "—";
  const diff = Math.floor((Date.now() - new Date(iso).getTime()) / 1000);
  if (diff < 60) return `${diff}s`;
  if (diff < 3600) return `${Math.floor(diff / 60)}m`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h`;
  return `${Math.floor(diff / 86400)}d`;
}

export default function Notifications() {
  const [list, setList] = useState([]);
  const [unread, setUnread] = useState(0);
  const [busy, setBusy] = useState(false);

  const load = async () => {
    try {
      const r = await api.get("/automation/notifications", { params: { limit: 100 } });
      setList(r.data.notifications || []);
      setUnread(r.data.unread_count || 0);
    } catch (e) { console.error("Gagal memuat notifikasi:", e); }
  };

  useEffect(() => {
    load();
    const t = setInterval(load, 5000);
    return () => clearInterval(t);
  }, []);

  const markRead = async (id) => {
    try {
      await api.post(`/automation/notifications/${id}/read`);
      await load();
    } catch (e) { console.error("Gagal menandai dibaca:", e); }
  };

  const resumeAndMarkRead = async (id) => {
    try {
      await api.post("/automation/resume");
      await api.post(`/automation/notifications/${id}/read`);
      toast.success("Verifikasi ditandai selesai — automation dilanjutkan");
      await load();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Gagal resume");
    }
  };

  const markAllRead = async () => {
    setBusy(true);
    try {
      await api.post("/automation/notifications/read-all");
      toast.success("Semua notifikasi ditandai dibaca");
      await load();
    } catch (e) {
      toast.error("Gagal");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-6" data-testid="notifications-page">
      <div className="flex items-start justify-between flex-wrap gap-4">
        <div>
          <div className="text-xs uppercase tracking-widest text-pink-500 mb-2">Inbox</div>
          <h1 className="font-heading text-3xl md:text-4xl font-bold flex items-center gap-3">
            Notifikasi
            {unread > 0 && (
              <span className="bg-pink-500 text-black text-sm font-bold px-2 py-0.5 rounded-full" data-testid="notif-unread-count">
                {unread}
              </span>
            )}
          </h1>
        </div>
        {unread > 0 && (
          <Button
            onClick={markAllRead}
            variant="outline"
            disabled={busy}
            data-testid="mark-all-read"
            className="border-white/10 rounded-md"
          >
            <CheckSquare size={16} className="mr-2" /> Tandai semua dibaca
          </Button>
        )}
      </div>

      <div className="space-y-3">
        {list.length === 0 && (
          <div className="text-slate-600 text-center py-16 border border-white/5 rounded-lg font-mono text-sm">
            Belum ada notifikasi.
          </div>
        )}
        {list.map((n) => {
          const meta = KIND_ICONS[n.kind] || KIND_ICONS.info;
          const Icon = meta.i;
          return (
            <div
              key={n.id}
              className={`border rounded-lg p-4 flex items-start gap-4 transition-colors ${
                n.read ? "border-white/5 bg-[#0F0F16]/50" : "border-pink-500/20 bg-[#0F0F16]"
              }`}
              data-testid="notif-row"
            >
              <div className={`w-10 h-10 shrink-0 rounded-full flex items-center justify-center ${meta.c}`}>
                <Icon size={20} weight="duotone" />
              </div>
              <div className="flex-1 min-w-0">
                <div className="flex items-center justify-between gap-3 mb-1">
                  <div className={`font-heading font-bold ${n.read ? "text-slate-400" : "text-white"}`}>
                    {n.title}
                  </div>
                  <span className="text-xs text-slate-500 font-mono shrink-0">
                    {timeAgo(n.created_at)}
                  </span>
                </div>
                {n.body && (
                  <div className="text-sm text-slate-400 leading-relaxed whitespace-pre-line break-words">
                    {n.body}
                  </div>
                )}
                {n.action_url && (
                  <a
                    href={n.action_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="inline-flex items-center gap-1 text-xs text-orange-400 hover:text-orange-300 mt-2 underline"
                    data-testid="notif-action-url"
                  >
                    Buka URL <ArrowSquareOut size={12} />
                  </a>
                )}
                {n.kind === "verification" && !n.read && (
                  <div className="mt-3">
                    <Button
                      onClick={() => resumeAndMarkRead(n.id)}
                      data-testid="notif-verify-done"
                      size="sm"
                      className="bg-green-500 hover:bg-green-600 text-black font-bold rounded-md h-8"
                    >
                      <Play size={14} weight="fill" className="mr-1" />
                      Sudah Selesai — Resume Automation
                    </Button>
                  </div>
                )}
              </div>
              {!n.read && (
                <button
                  onClick={() => markRead(n.id)}
                  className="text-slate-500 hover:text-white shrink-0 p-1"
                  title="Tandai dibaca"
                  data-testid="mark-read"
                >
                  <Check size={16} />
                </button>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
