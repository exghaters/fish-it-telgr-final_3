import { Link } from "react-router-dom";
import { motion } from "framer-motion";
import { Fish, Sparkle, Robot, Lightning, ShieldCheck, ArrowRight, Waveform, ClockCounterClockwise, Bell } from "@phosphor-icons/react";
import { Button } from "@/components/ui/button";

const features = [
  {
    icon: <Robot size={28} weight="duotone" />,
    title: "Automation Non-Stop",
    text: "Mancing 24/7 tanpa batas siklus. State machine cerdas menangani grup, VIP, extract & jual otomatis.",
  },
  {
    icon: <Sparkle size={28} weight="duotone" />,
    title: "Auto-Favorite Ikan Rare",
    text: "Secret, Secret Shiny, dan Celestial otomatis di-favoritkan sebelum dijual. Tidak ada yang hilang.",
  },
  {
    icon: <ShieldCheck size={28} weight="duotone" />,
    title: "Verifikasi Aman",
    text: "Deteksi 🔒 Verifikasi Diperlukan, coba selesaikan otomatis, fallback notifikasi bila CAPTCHA.",
  },
  {
    icon: <Waveform size={28} weight="duotone" />,
    title: "Panel Realtime",
    text: "Status, countdown siklus, aktivitas per-detik, dan notifikasi ikan langka langsung di dashboard.",
  },
  {
    icon: <Lightning size={28} weight="duotone" />,
    title: "Multi-User & Multi-Session",
    text: "Setiap akun Telegram punya session tersendiri, terenkripsi. Aman untuk paket langganan.",
  },
  {
    icon: <ClockCounterClockwise size={28} weight="duotone" />,
    title: "Pause & Resume",
    text: "Hentikan sementara kapan saja. Automation lanjut dari titik terakhir, tidak reset progress.",
  },
];

const tiers = [
  {
    name: "Starter",
    price: "Rp 0",
    period: "/free trial 3 hari",
    features: ["1 akun Telegram", "1 grup/bot", "Log 7 hari", "Verifikasi manual"],
    highlight: false,
  },
  {
    name: "Pro",
    price: "Rp 79k",
    period: "/bulan",
    features: [
      "1 akun Telegram",
      "Semua bot Fish It VIP",
      "Log 30 hari",
      "Auto verifikasi",
      "Priority support",
    ],
    highlight: true,
  },
  {
    name: "Elite",
    price: "Rp 199k",
    period: "/bulan",
    features: [
      "3 akun Telegram",
      "Semua bot Fish It VIP",
      "Log 90 hari",
      "Auto verifikasi",
      "Dedicated worker",
      "Bantuan setup 1-on-1",
    ],
    highlight: false,
  },
];

export default function Landing() {
  return (
    <div className="min-h-screen bg-[#05050A] text-slate-50">
      {/* Nav */}
      <nav className="border-b border-white/5 backdrop-blur-md bg-black/40 sticky top-0 z-40">
        <div className="max-w-7xl mx-auto px-6 py-4 flex items-center justify-between">
          <Link to="/" className="flex items-center gap-2" data-testid="nav-logo">
            <div className="w-9 h-9 rounded-full bg-gradient-to-br from-pink-500 to-yellow-500 flex items-center justify-center">
              <Fish size={20} weight="fill" className="text-black" />
            </div>
            <span className="font-heading font-bold text-lg tracking-tight">FISH IT / AUTOPILOT</span>
          </Link>
          <div className="hidden md:flex items-center gap-8 text-sm text-slate-400">
            <a href="#features" className="hover:text-white transition-colors">Fitur</a>
            <a href="#pricing" className="hover:text-white transition-colors">Harga</a>
            <a href="#how" className="hover:text-white transition-colors">Cara Kerja</a>
          </div>
          <div className="flex items-center gap-3">
            <Link to="/login" data-testid="nav-login-btn">
              <Button variant="ghost" className="text-slate-300 hover:text-white">Masuk</Button>
            </Link>
            <Link to="/register" data-testid="nav-register-btn">
              <Button className="bg-pink-500 hover:bg-pink-600 text-black font-semibold rounded-full px-5">
                Mulai Gratis <ArrowRight size={16} className="ml-1" />
              </Button>
            </Link>
          </div>
        </div>
      </nav>

      {/* Hero */}
      <section className="relative overflow-hidden grain">
        <div className="max-w-7xl mx-auto px-6 pt-24 pb-32 grid lg:grid-cols-12 gap-12 items-center relative z-10">
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.6 }}
            className="lg:col-span-7"
          >
            <div className="inline-flex items-center gap-2 rounded-full border border-pink-500/30 bg-pink-500/10 px-4 py-1.5 mb-6">
              <span className="w-2 h-2 rounded-full bg-pink-500 dot-pulse" />
              <span className="text-xs uppercase tracking-widest text-pink-300">Sekarang Rilis Beta</span>
            </div>
            <h1 className="font-heading text-5xl md:text-6xl lg:text-7xl font-black leading-[0.95]">
              Auto-Pancing<br />
              <span className="text-pink-500">Fish It</span> yang<br />
              tidak pernah tidur.
            </h1>
            <p className="mt-8 text-lg text-slate-400 max-w-xl leading-relaxed">
              Panel kontrol untuk automation Telegram game <span className="text-white font-medium">Fish It</span>.
              Mancing tanpa henti, favoritkan Secret/Celestial otomatis, jual habis-habisan, dan pause aman
              saat verifikasi muncul.
            </p>
            <div className="mt-10 flex flex-wrap gap-4">
              <Link to="/register" data-testid="hero-cta-register">
                <Button className="bg-pink-500 hover:bg-pink-600 text-black font-bold rounded-full px-8 py-6 text-base glow-pink">
                  Mulai Automation Gratis <ArrowRight size={18} className="ml-2" />
                </Button>
              </Link>
              <a href="#how" data-testid="hero-cta-learn">
                <Button variant="outline" className="border-white/20 hover:border-pink-500 hover:text-pink-500 rounded-full px-8 py-6 text-base bg-transparent">
                  Cara Kerja
                </Button>
              </a>
            </div>
            <div className="mt-12 flex items-center gap-8 text-sm text-slate-500">
              <div>
                <div className="font-heading text-2xl font-bold text-white">24/7</div>
                <div>Non-stop siklus</div>
              </div>
              <div>
                <div className="font-heading text-2xl font-bold text-white">100%</div>
                <div>Session terenkripsi</div>
              </div>
              <div>
                <div className="font-heading text-2xl font-bold text-white">3</div>
                <div>Rarity gift auto-favorite</div>
              </div>
            </div>
          </motion.div>

          <motion.div
            initial={{ opacity: 0, x: 20 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ duration: 0.7, delay: 0.15 }}
            className="lg:col-span-5"
          >
            <div className="trace-border rounded-2xl p-6 relative">
              <div className="flex items-center justify-between mb-6">
                <div className="flex items-center gap-2">
                  <span className="w-2.5 h-2.5 rounded-full bg-green-500 dot-pulse" />
                  <span className="text-sm text-slate-400 font-mono">bot.status</span>
                </div>
                <span className="text-xs text-slate-500 font-mono">@fish_it_bot</span>
              </div>
              <div className="font-heading text-4xl font-bold mb-1">FISHING</div>
              <div className="text-sm text-pink-500 mb-6">Cycle #47 · Since 03:42:18</div>
              <div className="space-y-3 mb-6">
                {[
                  { k: "12:47", v: "SESI MANCING SELESAI", c: "text-green-500" },
                  { k: "12:47", v: "42 ikan · 999,801 coins", c: "text-slate-400" },
                  { k: "12:48", v: "/mancing", c: "text-cyan-400" },
                  { k: "12:48", v: "AUTO MANCING - 03:07", c: "text-yellow-500" },
                ].map((row, i) => (
                  <div key={i} className="flex gap-3 text-xs font-mono">
                    <span className="text-slate-600">{row.k}</span>
                    <span className={row.c}>{row.v}</span>
                  </div>
                ))}
              </div>
              <div className="border-t border-white/10 pt-4 flex items-center justify-between">
                <div className="flex items-center gap-2 text-xs text-slate-500">
                  <Bell size={14} />
                  <span>3 notifikasi rare</span>
                </div>
                <span className="text-xs text-pink-500 font-semibold">LIVE</span>
              </div>
            </div>
          </motion.div>
        </div>
      </section>

      {/* Features */}
      <section id="features" className="max-w-7xl mx-auto px-6 py-32">
        <div className="max-w-3xl">
          <div className="text-xs uppercase tracking-widest text-pink-500 mb-4">Fitur Inti</div>
          <h2 className="font-heading text-4xl md:text-5xl font-bold mb-6">
            Automation yang benar-benar<br />mengerti Fish It.
          </h2>
          <p className="text-slate-400 text-lg">
            Bukan sekadar loop /mancing. Sistem membaca hasil, deteksi rarity, extract Trisula,
            paginasi inventory untuk favoritkan Secret, dan pause aman saat verifikasi muncul.
          </p>
        </div>

        <div className="mt-16 grid md:grid-cols-2 lg:grid-cols-3 gap-4">
          {features.map((f, i) => (
            <motion.div
              key={f.title}
              initial={{ opacity: 0, y: 20 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true }}
              transition={{ delay: i * 0.05 }}
              className="p-6 rounded-lg border border-white/10 bg-[#0F0F16] hover:border-pink-500/40 hover:-translate-y-1 transition-transform"
            >
              <div className="text-pink-500 mb-4">{f.icon}</div>
              <div className="font-heading text-lg font-semibold mb-2">{f.title}</div>
              <p className="text-slate-400 text-sm leading-relaxed">{f.text}</p>
            </motion.div>
          ))}
        </div>
      </section>

      {/* How it works */}
      <section id="how" className="border-y border-white/5 bg-[#0A0A12]">
        <div className="max-w-7xl mx-auto px-6 py-32">
          <div className="text-xs uppercase tracking-widest text-yellow-500 mb-4">Cara Kerja</div>
          <h2 className="font-heading text-4xl md:text-5xl font-bold mb-16 max-w-2xl">
            4 langkah dari login ke ikan pertama.
          </h2>
          <div className="grid md:grid-cols-4 gap-6">
            {[
              { n: "01", t: "Daftar Akun", d: "Registrasi email + password. Gratis, tanpa kartu kredit." },
              { n: "02", t: "Login Telegram", d: "Masukkan API ID + Hash dari my.telegram.org, verifikasi via kode." },
              { n: "03", t: "Konfigurasi Bot", d: "Isi username bot / grup Fish It, atur mode (VIP direct / Grup)." },
              { n: "04", t: "Start & Santai", d: "Klik Start. Automation jalan tanpa batas. Pantau via dashboard." },
            ].map((s, i) => (
              <div key={s.n} className="relative">
                <div className="font-mono text-xs text-slate-600 mb-3">{s.n}</div>
                <div className="font-heading text-xl font-bold mb-2">{s.t}</div>
                <div className="text-slate-400 text-sm leading-relaxed">{s.d}</div>
                {i < 3 && (
                  <div className="hidden md:block absolute top-0 -right-3 text-slate-700">
                    <ArrowRight size={20} />
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Pricing */}
      <section id="pricing" className="max-w-7xl mx-auto px-6 py-32">
        <div className="text-xs uppercase tracking-widest text-cyan-400 mb-4">Harga</div>
        <h2 className="font-heading text-4xl md:text-5xl font-bold mb-4">
          Mulai gratis. Upgrade saat butuh.
        </h2>
        <p className="text-slate-400 text-lg mb-16 max-w-2xl">
          Harga jujur, tanpa biaya tersembunyi. Cancel kapan saja.
        </p>
        <div className="grid md:grid-cols-3 gap-4">
          {tiers.map((t, i) => (
            <div
              key={t.name}
              className={`p-8 rounded-lg border transition-transform hover:-translate-y-1 ${
                t.highlight
                  ? "trace-border relative"
                  : "border-white/10 bg-[#0F0F16] hover:border-white/20"
              }`}
              data-testid={`pricing-tier-${t.name.toLowerCase()}`}
            >
              {t.highlight && (
                <div className="absolute -top-3 left-6 bg-pink-500 text-black text-xs font-bold px-3 py-1 rounded-full">
                  POPULER
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
                    <span className="text-pink-500 mt-1">✓</span>
                    <span>{f}</span>
                  </li>
                ))}
              </ul>
              <Link to="/register" data-testid={`pricing-cta-${t.name.toLowerCase()}`}>
                <Button
                  className={`w-full rounded-full ${
                    t.highlight
                      ? "bg-pink-500 hover:bg-pink-600 text-black font-bold"
                      : "bg-white/5 hover:bg-white/10 text-white"
                  }`}
                >
                  Pilih {t.name}
                </Button>
              </Link>
            </div>
          ))}
        </div>
      </section>

      {/* Footer */}
      <footer className="border-t border-white/5 py-12">
        <div className="max-w-7xl mx-auto px-6 flex flex-wrap items-center justify-between gap-4">
          <div className="flex items-center gap-2 text-slate-500">
            <Fish size={16} />
            <span className="font-mono text-xs">© 2026 FISH IT AUTOPILOT · Personal use only</span>
          </div>
          <div className="text-xs text-slate-600 font-mono">
            Automation memakai akun Telegram pribadi. Bukan afiliasi Fish It.
          </div>
        </div>
      </footer>
    </div>
  );
}
