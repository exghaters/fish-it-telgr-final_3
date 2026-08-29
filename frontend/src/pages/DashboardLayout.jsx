import { NavLink, Outlet, useLocation } from "react-router-dom";
import { useEffect, useState } from "react";
import {
  Fish,
  Gauge,
  TelegramLogo,
  Sliders,
  ListBullets,
  Bell,
  UsersThree,
  SignOut,
  List,
  X,
  PencilSimple,
} from "@phosphor-icons/react";
import { useAuth } from "@/lib/auth.jsx";
import api from "@/lib/api";
import { toast } from "sonner";

const NAV = [
  { to: "/dashboard", label: "Status", icon: Gauge, testid: "nav-status" },
  { to: "/dashboard/telegram", label: "Telegram", icon: TelegramLogo, testid: "nav-telegram" },
  { to: "/dashboard/config", label: "Konfigurasi", icon: Sliders, testid: "nav-config" },
  { to: "/dashboard/activity", label: "Activity Log", icon: ListBullets, testid: "nav-activity" },
  { to: "/dashboard/notifications", label: "Notifikasi", icon: Bell, testid: "nav-notifications" },
];

const PLAN_UI = {
  free: { limit: 1, plan_label: "Starter" },
  basic: { limit: 1, plan_label: "Starter" },
  pro: { limit: 1, plan_label: "Pro" },
  elite: { limit: 100, plan_label: "Elite" },
};

export default function DashboardLayout() {
  const { user, logout } = useAuth();
  const [unread, setUnread] = useState(0);
  const [open, setOpen] = useState(false);
  const [accounts, setAccounts] = useState([]);
  const [accInfo, setAccInfo] = useState(
    () => PLAN_UI[(user?.plan || "free").toLowerCase()] || PLAN_UI.free
  );
  const [activeAcc, setActiveAcc] = useState(localStorage.getItem("fishit_account") || "");
  const location = useLocation();

  useEffect(() => {
    setOpen(false);
  }, [location.pathname]);

  useEffect(() => {
    api
      .get("/telegram/accounts")
      .then((r) => {
        const list = r.data.accounts || [];
        setAccounts(list);
        setAccInfo({ limit: r.data.limit, plan_label: r.data.plan_label });
        let sel = localStorage.getItem("fishit_account");
        if (!sel || !list.find((a) => a.id === sel)) {
          sel = list[0]?.id || "";
          if (sel) localStorage.setItem("fishit_account", sel);
        }
        setActiveAcc(sel);
      })
      .catch(() => {});
  }, []);

  const switchAcc = (id) => {
    if (!id || id === activeAcc) return;
    localStorage.setItem("fishit_account", id);
    window.location.reload();
  };

  const addAcc = async () => {
    const label = window.prompt("Label akun (nama pelanggan, mis. 'Budi - 0812xxx'):", `Akun ${accounts.length + 1}`);
    if (label === null) return;
    try {
      const r = await api.post("/telegram/accounts", { label: label.trim() || `Akun ${accounts.length + 1}` });
      localStorage.setItem("fishit_account", r.data.id);
      toast.success("Akun Telegram baru dibuat");
      window.location.reload();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Tidak bisa menambah akun");
    }
  };

  const renameAcc = async () => {
    const current = accounts.find((a) => a.id === activeAcc);
    if (!current) return;
    const label = window.prompt("Ubah label akun (nama pelanggan):", current.label);
    if (label === null || !label.trim()) return;
    try {
      await api.patch(`/telegram/accounts/${activeAcc}`, { label: label.trim() });
      setAccounts((prev) => prev.map((a) => (a.id === activeAcc ? { ...a, label: label.trim() } : a)));
      toast.success("Label akun diperbarui");
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Gagal mengubah label");
    }
  };

  useEffect(() => {
    const load = () => {
      api
        .get("/automation/notifications", { params: { limit: 1 } })
        .then((r) => setUnread(r.data.unread_count || 0))
        .catch(() => {});
    };
    load();
    const t = setInterval(load, 15000);
    return () => clearInterval(t);
  }, [location.pathname]);

  return (
    <div className="min-h-screen bg-[#05050A] text-slate-100 flex">
      {/* Mobile top bar */}
      <div className="md:hidden fixed top-0 inset-x-0 z-[60] h-14 bg-[#08080F] border-b border-white/5 flex items-center justify-between px-4">
        <div className="flex items-center gap-2">
          <div className="w-7 h-7 rounded-full bg-gradient-to-br from-pink-500 to-yellow-500 flex items-center justify-center">
            <Fish size={14} weight="fill" className="text-black" />
          </div>
          <span className="font-heading font-bold text-sm tracking-tight">FISH IT</span>
        </div>
        <button
          onClick={() => setOpen((v) => !v)}
          data-testid="mobile-menu-toggle"
          className="p-2 rounded-md text-slate-300 hover:bg-white/5 transition-colors"
          aria-label="Menu"
        >
          {open ? <X size={22} /> : <List size={22} />}
        </button>
      </div>

      {/* Overlay (mobile) */}
      {open && (
        <div
          onClick={() => setOpen(false)}
          data-testid="mobile-overlay"
          className="md:hidden fixed inset-0 z-40 bg-black/60 backdrop-blur-sm"
        />
      )}

      {/* Sidebar */}
      <aside
        className={`w-64 shrink-0 border-r border-white/5 bg-[#08080F] flex flex-col fixed md:static inset-y-0 left-0 z-50 transform transition-transform duration-300 md:translate-x-0 ${
          open ? "translate-x-0" : "-translate-x-full"
        }`}
      >
        <div className="p-6 border-b border-white/5">
          <div className="flex items-center gap-2">
            <div className="w-8 h-8 rounded-full bg-gradient-to-br from-pink-500 to-yellow-500 flex items-center justify-center">
              <Fish size={16} weight="fill" className="text-black" />
            </div>
            <div>
              <div className="font-heading font-bold text-sm tracking-tight">FISH IT</div>
              <div className="text-[10px] uppercase tracking-widest text-slate-500">Autopilot</div>
            </div>
          </div>
        </div>
        {/* Account switcher (multi-account per plan) */}
        <div className="px-3 py-3 border-b border-white/5" data-testid="account-switcher-box">
          <div className="text-[10px] uppercase tracking-widest text-slate-600 mb-1.5 flex items-center justify-between">
            <span>Akun Telegram</span>
            <span className="text-slate-500 normal-case tracking-normal font-mono">
              {accounts.length}/{accInfo.limit}
            </span>
          </div>
          <div className="flex items-center gap-1.5">
            <select
              value={activeAcc}
              onChange={(e) => switchAcc(e.target.value)}
              data-testid="account-switcher"
              className="flex-1 min-w-0 bg-[#05050A] border border-white/10 rounded-md text-sm px-2 py-2 text-slate-200 focus:border-pink-500 outline-none"
            >
              {accounts.map((a) => (
                <option key={a.id} value={a.id}>
                  {a.label}
                  {a.connected ? " · ✓" : " · —"}
                </option>
              ))}
            </select>
            <button
              onClick={renameAcc}
              data-testid="account-rename"
              title="Ubah label / nama pelanggan"
              className="shrink-0 p-2 rounded-md border border-white/10 text-slate-400 hover:text-pink-400 hover:border-pink-500/40 transition-colors"
            >
              <PencilSimple size={14} />
            </button>
          </div>
          <button
            onClick={addAcc}
            disabled={accounts.length >= accInfo.limit}
            data-testid="account-add"
            className="mt-2 w-full text-xs px-2 py-1.5 rounded-md border border-pink-500/30 text-pink-400 hover:bg-pink-500/10 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
            title={accounts.length >= accInfo.limit ? `Paket ${accInfo.plan_label} maksimal ${accInfo.limit} akun` : ""}
          >
            + Tambah akun ({accInfo.plan_label})
          </button>
        </div>
        <nav className="flex-1 p-3 space-y-1">
          {NAV.map((n) => (
            <NavLink
              key={n.to}
              to={n.to}
              end={n.to === "/dashboard"}
              data-testid={n.testid}
              className={({ isActive }) =>
                `flex items-center gap-3 px-3 py-2.5 rounded-md text-sm transition-colors ${
                  isActive
                    ? "bg-pink-500/10 text-pink-400 border border-pink-500/20"
                    : "text-slate-400 hover:text-white hover:bg-white/5 border border-transparent"
                }`
              }
            >
              <n.icon size={18} weight="duotone" />
              <span>{n.label}</span>
              {n.to === "/dashboard/notifications" && unread > 0 && (
                <span className="ml-auto bg-pink-500 text-black text-[10px] font-bold px-1.5 py-0.5 rounded-full min-w-[18px] text-center" data-testid="nav-unread-badge">
                  {unread}
                </span>
              )}
            </NavLink>
          ))}
          {user?.role === "admin" && (
            <>
              <div className="text-[10px] uppercase tracking-widest text-slate-600 px-3 pt-6 pb-2">
                Admin
              </div>
              <NavLink
                to="/dashboard/admin"
                data-testid="nav-admin"
                className={({ isActive }) =>
                  `flex items-center gap-3 px-3 py-2.5 rounded-md text-sm transition-colors ${
                    isActive
                      ? "bg-yellow-500/10 text-yellow-400 border border-yellow-500/20"
                      : "text-slate-400 hover:text-white hover:bg-white/5 border border-transparent"
                  }`
                }
              >
                <UsersThree size={18} weight="duotone" />
                <span>Kelola User</span>
              </NavLink>
            </>
          )}
        </nav>
        <div className="p-4 border-t border-white/5">
          <div className="flex items-center gap-3 mb-3">
            <div className="w-8 h-8 rounded-full bg-pink-500/20 border border-pink-500/40 flex items-center justify-center text-pink-400 text-xs font-bold">
              {user?.email?.[0]?.toUpperCase()}
            </div>
            <div className="min-w-0 flex-1">
              <div className="text-xs font-semibold truncate" data-testid="sidebar-user-email">{user?.email}</div>
              <div className="text-[10px] text-slate-500 uppercase tracking-wider">
                {user?.role} · {user?.plan}
              </div>
            </div>
          </div>
          <button
            onClick={logout}
            data-testid="sidebar-logout"
            className="w-full flex items-center gap-2 text-sm text-slate-400 hover:text-white px-3 py-2 rounded-md hover:bg-white/5 transition-colors"
          >
            <SignOut size={16} />
            <span>Keluar</span>
          </button>
        </div>
      </aside>

      {/* Main */}
      <main className="flex-1 min-w-0 overflow-y-auto pt-14 md:pt-0">
        <div className="p-5 md:p-8 max-w-6xl">
          <Outlet />
        </div>
      </main>
    </div>
  );
}
