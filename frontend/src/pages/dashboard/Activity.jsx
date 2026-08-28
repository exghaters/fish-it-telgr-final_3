import { useCallback, useEffect, useRef, useState } from "react";
import { ArrowsClockwise } from "@phosphor-icons/react";
import { Button } from "@/components/ui/button";
import api from "@/lib/api";

const KIND_STYLE = {
  info: "prefix-info",
  action: "prefix-info",
  "message-in": "prefix-info",
  "message-out": "prefix-info",
  click: "prefix-info",
  "fish-caught": "prefix-success",
  rare: "prefix-rare",
  gift: "prefix-gift",
  special: "prefix-gift",
  verification: "prefix-warn",
  error: "prefix-error",
  start: "prefix-success",
  stop: "prefix-warn",
  pause: "prefix-warn",
  resume: "prefix-info",
  sell: "prefix-success",
  extract: "prefix-success",
  favorite: "prefix-gift",
};

const LEVEL_LABEL = {
  info: "INFO",
  warn: "WARN",
  error: "ERR",
  success: "OK",
};

function formatTime(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  return d.toLocaleTimeString("id-ID", { hour12: false });
}

export default function Activity() {
  const [events, setEvents] = useState([]);
  const [filter, setFilter] = useState("");
  const [autoScroll, setAutoScroll] = useState(true);
  const scrollRef = useRef(null);

  const load = useCallback(async () => {
    try {
      const r = await api.get("/automation/events", { params: { limit: 200 } });
      setEvents((r.data.events || []).reverse());
    } catch { /* silent: background poll */ }
  }, []);

  useEffect(() => {
    load();
    const t = setInterval(load, 2500);
    return () => clearInterval(t);
  }, [load]);

  useEffect(() => {
    if (autoScroll && scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [events, autoScroll]);

  const filtered = filter
    ? events.filter(
        (e) =>
          e.kind === filter ||
          e.level === filter ||
          e.message.toLowerCase().includes(filter.toLowerCase())
      )
    : events;

  return (
    <div className="space-y-6" data-testid="activity-page">
      <div className="flex items-start justify-between flex-wrap gap-4">
        <div>
          <div className="text-xs uppercase tracking-widest text-pink-500 mb-2">Log</div>
          <h1 className="font-heading text-3xl md:text-4xl font-bold">Activity Log</h1>
          <p className="text-slate-400 mt-2">
            Real-time event stream dari automation engine (auto-refresh 2.5s).
          </p>
        </div>
        <div className="flex gap-2 items-center flex-wrap">
          <input
            data-testid="filter-input"
            placeholder="Filter kind/level/text..."
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            className="bg-[#05050A] border border-white/10 rounded-md px-3 py-2 text-sm font-mono placeholder:text-slate-600 focus:border-pink-500 outline-none"
          />
          <Button
            onClick={() => setAutoScroll((v) => !v)}
            variant="outline"
            className={`rounded-md border-white/10 ${autoScroll ? "text-pink-400" : ""}`}
          >
            {autoScroll ? "Auto-scroll ON" : "Auto-scroll OFF"}
          </Button>
          <Button
            onClick={load}
            variant="outline"
            className="rounded-md border-white/10"
            data-testid="refresh-activity"
          >
            <ArrowsClockwise size={14} className="mr-2" /> Refresh
          </Button>
        </div>
      </div>

      <div
        ref={scrollRef}
        className="terminal rounded-lg border border-white/10 p-4 h-[560px] overflow-y-auto"
        data-testid="activity-log"
      >
        {filtered.length === 0 && (
          <div className="text-slate-600 text-center py-16 font-mono text-sm">
            &gt; Belum ada aktivitas. Start automation untuk melihat log.
          </div>
        )}
        {filtered.map((e) => (
          <div key={e.id} className="flex gap-3 py-1 border-b border-white/[0.03]" data-testid="activity-row">
            <span className="text-slate-600 shrink-0">{formatTime(e.created_at)}</span>
            <span className={`shrink-0 uppercase font-semibold ${KIND_STYLE[e.kind] || "prefix-info"}`}>
              [{LEVEL_LABEL[e.level] || e.level || "INFO"}·{e.kind}]
            </span>
            <span className="text-slate-300 break-words min-w-0 flex-1">{e.message}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
