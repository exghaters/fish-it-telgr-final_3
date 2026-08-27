import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { Fish, ArrowRight } from "@phosphor-icons/react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useAuth } from "@/lib/auth.jsx";

export default function Register() {
  const { register } = useAuth();
  const nav = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    if (password.length < 6) {
      toast.error("Password minimal 6 karakter");
      return;
    }
    setLoading(true);
    try {
      await register(email, password);
      toast.success("Akun berhasil dibuat!");
      nav("/dashboard");
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Registrasi gagal");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-[#05050A] grain flex items-center justify-center px-6">
      <div className="w-full max-w-md">
        <Link to="/" className="flex items-center gap-2 mb-10 justify-center" data-testid="register-back-home">
          <div className="w-9 h-9 rounded-full bg-gradient-to-br from-pink-500 to-yellow-500 flex items-center justify-center">
            <Fish size={20} weight="fill" className="text-black" />
          </div>
          <span className="font-heading font-bold text-lg tracking-tight">FISH IT / AUTOPILOT</span>
        </Link>

        <div className="border border-white/10 bg-[#0F0F16] rounded-lg p-8">
          <h1 className="font-heading text-3xl font-bold mb-2">Daftar Gratis</h1>
          <p className="text-slate-400 text-sm mb-8">
            Mulai automation dalam 2 menit. Tidak butuh kartu kredit.
          </p>

          <form onSubmit={submit} className="space-y-5">
            <div>
              <Label htmlFor="email" className="text-slate-300 mb-2 block">Email</Label>
              <Input
                id="email"
                data-testid="register-email"
                type="email"
                autoComplete="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="you@example.com"
                className="bg-[#05050A] border-white/10 focus:border-pink-500 h-11"
              />
            </div>
            <div>
              <Label htmlFor="password" className="text-slate-300 mb-2 block">Password (min. 6 karakter)</Label>
              <Input
                id="password"
                data-testid="register-password"
                type="password"
                autoComplete="new-password"
                required
                minLength={6}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="bg-[#05050A] border-white/10 focus:border-pink-500 h-11"
              />
            </div>
            <Button
              type="submit"
              disabled={loading}
              data-testid="register-submit"
              className="w-full bg-pink-500 hover:bg-pink-600 text-black font-bold h-11 rounded-md"
            >
              {loading ? "Mendaftar..." : "Buat Akun"} <ArrowRight size={16} className="ml-1" />
            </Button>
          </form>

          <p className="mt-6 text-sm text-slate-500 text-center">
            Sudah punya akun?{" "}
            <Link to="/login" className="text-pink-500 hover:text-pink-400" data-testid="register-to-login">
              Masuk di sini
            </Link>
          </p>
        </div>
      </div>
    </div>
  );
}
