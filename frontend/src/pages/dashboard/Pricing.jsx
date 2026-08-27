import { toast } from "sonner";
import { CheckCircle } from "@phosphor-icons/react";
import { Button } from "@/components/ui/button";
import { useAuth } from "@/lib/auth.jsx";

const TIERS = [
  {
    id: "free",
    name: "Starter",
    price: "Rp 0",
    period: "/free trial 3 hari",
    features: ["1 akun Telegram", "1 grup/bot", "Log 7 hari", "Verifikasi manual"],
  },
  {
    id: "pro",
    name: "Pro",
    price: "Rp 79.000",
    period: "/bulan",
    highlight: true,
    features: [
      "1 akun Telegram",
      "Semua bot Fish It VIP",
      "Log 30 hari",
      "Auto verifikasi",
      "Priority support",
    ],
  },
  {
    id: "elite",
    name: "Elite",
    price: "Rp 199.000",
    period: "/bulan",
    features: [
      "3 akun Telegram",
      "Semua bot Fish It VIP",
      "Log 90 hari",
      "Auto verifikasi",
      "Dedicated worker",
      "Bantuan setup 1-on-1",
    ],
  },
];

export default function Pricing() {
  const { user } = useAuth();

  const choose = (tier) => {
    toast.info("Pembayaran belum aktif — akan diintegrasikan dengan Stripe/Midtrans.", {
      description: `Paket dipilih: ${tier.name}`,
    });
  };

  return (
    <div className="space-y-8" data-testid="pricing-page">
      <div>
        <div className="text-xs uppercase tracking-widest text-cyan-400 mb-2">Paket & Langganan</div>
        <h1 className="font-heading text-3xl md:text-4xl font-bold">Pilih Paket Anda</h1>
        <p className="text-slate-400 mt-2 max-w-2xl">
          Paket saat ini:{" "}
          <span className="text-pink-500 font-bold uppercase" data-testid="current-plan">
            {user?.plan || "free"}
          </span>
          . Pembayaran akan diaktifkan setelah beta.
        </p>
      </div>

      <div className="grid md:grid-cols-3 gap-4">
        {TIERS.map((t) => (
          <div
            key={t.id}
            className={`p-8 rounded-lg border transition-transform hover:-translate-y-1 relative ${
              t.highlight
                ? "trace-border"
                : "border-white/10 bg-[#0F0F16] hover:border-white/20"
            }`}
            data-testid={`plan-${t.id}`}
          >
            {t.highlight && (
              <div className="absolute -top-3 left-6 bg-pink-500 text-black text-xs font-bold px-3 py-1 rounded-full">
                REKOMENDASI
              </div>
            )}
            {user?.plan === t.id && (
              <div className="absolute -top-3 right-6 bg-green-500 text-black text-xs font-bold px-3 py-1 rounded-full">
                AKTIF
              </div>
            )}
            <div className="font-heading text-2xl font-bold mb-2">{t.name}</div>
            <div className="flex items-baseline gap-1 mb-6">
              <span className="font-heading text-4xl font-bold">{t.price}</span>
              <span className="text-slate-500 text-sm">{t.period}</span>
            </div>
            <ul className="space-y-3 mb-8">
              {t.features.map((f) => (
                <li key={f} className="flex items-start gap-2 text-sm text-slate-400">
                  <CheckCircle size={16} weight="fill" className="text-pink-500 mt-0.5 shrink-0" />
                  <span>{f}</span>
                </li>
              ))}
            </ul>
            <Button
              onClick={() => choose(t)}
              disabled={user?.plan === t.id}
              data-testid={`plan-cta-${t.id}`}
              className={`w-full rounded-md ${
                t.highlight
                  ? "bg-pink-500 hover:bg-pink-600 text-black font-bold"
                  : "bg-white/5 hover:bg-white/10 text-white"
              }`}
            >
              {user?.plan === t.id ? "Paket Aktif" : `Pilih ${t.name}`}
            </Button>
          </div>
        ))}
      </div>

      <div className="text-xs text-slate-600 text-center pt-8 border-t border-white/5 font-mono">
        Payment gateway: Stripe / Midtrans — akan diaktifkan setelah beta selesai.
      </div>
    </div>
  );
}
