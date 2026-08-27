import { NavLink, Outlet, useLocation } from "react-router-dom";
import { useEffect, useState } from "react";
import {
  Fish,
  Gauge,
  TelegramLogo,
  Sliders,
  ListBullets,
  Bell,
  Ticket,
  UsersThree,
  SignOut,
} from "@phosphor-icons/react";
import { useAuth } from "@/lib/auth.jsx";
import api from "@/lib/api";

const NAV = [
  { to: "/dashboard", label: "Status", icon: Gauge, testid: "nav-status" },
  { to: "/dashboard/telegram", label: "Telegram", icon: TelegramLogo, testid: "nav-telegram" },
  { to: "/dashboard/config", label: "Konfigurasi", icon: Sliders, testid: "nav-config" },
  { to: "/dashboard/activity", label: "Activity Log", icon: ListBullets, testid: "nav-activity" },
  { to: "/dashboard/notifications", label: "Notifikasi", icon: Bell, testid: "nav-notifications" },
  { to: "/dashboard/pricing", label: "Paket", icon: Ticket, testid: "nav-pricing" },
];

export default function DashboardLayout() {
  const { user, logout } = useAuth();
  const [unread, setUnread] = useState(0);
  const location = useLocation();

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
      {/* Sidebar */}
      <aside className="w-64 shrink-0 border-r border-white/5 bg-[#08080F] flex flex-col">
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
      <main className="flex-1 min-w-0 overflow-y-auto">
        <div className="p-8 max-w-6xl">
          <Outlet />
        </div>
      </main>
    </div>
  );
}
