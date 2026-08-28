import { useEffect, useState } from "react";
import { toast } from "sonner";
import { UsersThree, ShieldCheck, ShieldSlash, Crown, Key } from "@phosphor-icons/react";
import { Button } from "@/components/ui/button";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import api from "@/lib/api";

export default function Admin() {
  const [users, setUsers] = useState([]);
  const [stats, setStats] = useState(null);

  const load = async () => {
    try {
      const [u, s] = await Promise.all([api.get("/admin/users"), api.get("/admin/stats")]);
      setUsers(u.data);
      setStats(s.data);
    } catch (e) { console.error("Gagal memuat data admin:", e); }
  };

  useEffect(() => {
    load();
    const t = setInterval(load, 10000);
    return () => clearInterval(t);
  }, []);

  const update = async (id, patch, msg) => {
    try {
      await api.put(`/admin/users/${id}`, patch);
      toast.success(msg);
      await load();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Gagal update");
    }
  };

  const resetPw = async (u) => {
    const np = window.prompt(`Set password baru untuk ${u.email} (min 6 karakter):`);
    if (np === null) return;
    if (np.length < 6) {
      toast.error("Password minimal 6 karakter");
      return;
    }
    try {
      await api.post(`/admin/users/${u.id}/reset-password`, { new_password: np });
      toast.success(`Password ${u.email} berhasil direset`);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Gagal reset password");
    }
  };

  return (
    <div className="space-y-8" data-testid="admin-page">
      <div>
        <div className="text-xs uppercase tracking-widest text-yellow-500 mb-2">Admin</div>
        <h1 className="font-heading text-3xl md:text-4xl font-bold flex items-center gap-3">
          <Crown size={32} weight="duotone" className="text-yellow-500" />
          Kelola User
        </h1>
      </div>

      {stats && (
        <div className="grid md:grid-cols-4 gap-4">
          <Stat label="Total User" value={stats.total_users} testid="stat-total" />
          <Stat label="User Aktif" value={stats.active_users} testid="stat-active" />
          <Stat label="Bot Berjalan" value={stats.running_bots} testid="stat-running" />
          <Stat
            label="Paket Populer"
            value={
              Object.entries(stats.plans || {})
                .sort((a, b) => b[1] - a[1])[0]?.[0] || "-"
            }
            testid="stat-plan"
          />
        </div>
      )}

      <div className="border border-white/10 bg-[#0F0F16] rounded-lg overflow-hidden">
        <div className="p-4 border-b border-white/5 flex items-center gap-2">
          <UsersThree size={18} className="text-yellow-500" />
          <span className="font-heading font-bold">User List</span>
          <span className="text-xs text-slate-500 ml-auto font-mono">{users.length} user</span>
        </div>
        <Table>
          <TableHeader>
            <TableRow className="border-white/5 hover:bg-transparent">
              <TableHead className="text-slate-400">Email</TableHead>
              <TableHead className="text-slate-400">Role</TableHead>
              <TableHead className="text-slate-400">Plan</TableHead>
              <TableHead className="text-slate-400">Status</TableHead>
              <TableHead className="text-slate-400 text-right">Aksi</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {users.map((u) => (
              <TableRow key={u.id} className="border-white/5 hover:bg-white/[0.02]" data-testid="user-row">
                <TableCell className="font-mono text-xs">{u.email}</TableCell>
                <TableCell>
                  <Select
                    value={u.role}
                    onValueChange={(v) => update(u.id, { role: v }, "Role diupdate")}
                  >
                    <SelectTrigger className="h-8 bg-[#05050A] border-white/10 w-28 text-xs">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent className="bg-[#0F0F16] border-white/10">
                      <SelectItem value="user">user</SelectItem>
                      <SelectItem value="admin">admin</SelectItem>
                    </SelectContent>
                  </Select>
                </TableCell>
                <TableCell>
                  <Select
                    value={u.plan}
                    onValueChange={(v) => update(u.id, { plan: v }, "Plan diupdate")}
                  >
                    <SelectTrigger className="h-8 bg-[#05050A] border-white/10 w-28 text-xs">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent className="bg-[#0F0F16] border-white/10">
                      <SelectItem value="free">free</SelectItem>
                      <SelectItem value="basic">basic</SelectItem>
                      <SelectItem value="pro">pro</SelectItem>
                      <SelectItem value="elite">elite</SelectItem>
                    </SelectContent>
                  </Select>
                </TableCell>
                <TableCell>
                  <span
                    className={`inline-flex items-center gap-1 text-xs px-2 py-0.5 rounded-full font-mono ${
                      u.is_active
                        ? "bg-green-500/10 text-green-400"
                        : "bg-red-500/10 text-red-400"
                    }`}
                  >
                    {u.is_active ? "aktif" : "disabled"}
                  </span>
                </TableCell>
                <TableCell className="text-right">
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => resetPw(u)}
                    className="h-8 rounded-md text-xs mr-2 border-blue-500/30 text-blue-400 hover:bg-blue-500/10"
                    data-testid="reset-password"
                    title="Reset password user"
                  >
                    <Key size={14} />
                  </Button>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() =>
                      update(
                        u.id,
                        { is_active: !u.is_active },
                        u.is_active ? "User dinonaktifkan" : "User diaktifkan"
                      )
                    }
                    className={`h-8 rounded-md text-xs ${
                      u.is_active
                        ? "border-red-500/30 text-red-400 hover:bg-red-500/10"
                        : "border-green-500/30 text-green-400 hover:bg-green-500/10"
                    }`}
                    data-testid="toggle-active"
                  >
                    {u.is_active ? <ShieldSlash size={14} /> : <ShieldCheck size={14} />}
                  </Button>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
    </div>
  );
}

function Stat({ label, value, testid }) {
  return (
    <div className="border border-white/10 bg-[#0F0F16] rounded-lg p-5" data-testid={testid}>
      <div className="text-xs text-slate-500 uppercase tracking-widest mb-2">{label}</div>
      <div className="font-heading text-3xl font-bold">{value}</div>
    </div>
  );
}
