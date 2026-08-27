import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { Fish, ArrowRight } from "@phosphor-icons/react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useAuth } from "@/lib/auth.jsx";

export default function Login() {
  const { login } = useAuth();
  const nav = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    setLoading(true);
    try {
      await login(email, password);
      toast.success("Selamat datang kembali!");
      nav("/dashboard");
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Login gagal");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-[#05050A] grain flex items-center justify-center px-6">
      <div className="w-full max-w-md">
        <Link to="/" className="flex items-center gap-2 mb-10 justify-center" data-testid="login-back-home">
          <div className="w-9 h-9 rounded-full bg-gradient-to-br from-pink-500 to-yellow-500 flex items-center justify-center">
            <Fish size={20} weight="fill" className="text-black" />
          </div>
          <span className="font-heading font-bold text-lg tracking-tight">FISH IT / AUTOPILOT</span>
        </Link>

        <div className="border border-white/10 bg-[#0F0F16] rounded-lg p-8">
          <h1 className="font-heading text-3xl font-bold mb-2">Masuk</h1>
          <p className="text-slate-400 text-sm mb-8">
            Kelola automation Fish It Anda.
          </p>

          <form onSubmit={submit} className="space-y-5">
            <div>
              <Label htmlFor="email" className="text-slate-300 mb-2 block">Email</Label>
              <Input
                id="email"
                data-testid="login-email"
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
              <Label htmlFor="password" className="text-slate-300 mb-2 block">Password</Label>
              <Input
                id="password"
                data-testid="login-password"
                type="password"
                autoComplete="current-password"
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
              data-testid="login-submit"
              className="w-full bg-pink-500 hover:bg-pink-600 text-black font-bold h-11 rounded-md"
            >
              {loading ? "Memproses..." : "Masuk"} <ArrowRight size={16} className="ml-1" />
            </Button>
          </form>

          <p className="mt-6 text-sm text-slate-500 text-center">
            Belum punya akun?{" "}
            <Link to="/register" className="text-pink-500 hover:text-pink-400" data-testid="login-to-register">
              Daftar gratis
            </Link>
          </p>
        </div>
      </div>
    </div>
  );
}
