import { useEffect, useState } from "react";
import { Switch, Route, Router as WouterRouter } from "wouter";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { Toaster } from "@/components/ui/toaster";
import { TooltipProvider } from "@/components/ui/tooltip";
import { Users, ExternalLink, ChevronDown, ChevronUp } from "lucide-react";
import NotFound from "@/pages/not-found";
import NhlPlayerDashboardTab, { type PlayerDeg3Mode } from "./NhlPlayerDashboardTab";

const queryClient = new QueryClient({
  defaultOptions: { queries: { refetchOnWindowFocus: false } },
});

const ENV_INPUT_SHEET_ID = (import.meta.env.VITE_NHL_PLAYER_INPUT_SHEET_ID ?? "").trim();
const ENV_CALC_SHEET_ID = (import.meta.env.VITE_NHL_PLAYER_CALC_SHEET_ID ?? "").trim();

const DEFAULT_INPUT_URL = ENV_INPUT_SHEET_ID
  ? `https://docs.google.com/spreadsheets/d/${ENV_INPUT_SHEET_ID}/edit`
  : "/api/nhl/players-gem";
const DEFAULT_CALC_URL = ENV_CALC_SHEET_ID
  ? `https://docs.google.com/spreadsheets/d/${ENV_CALC_SHEET_ID}/edit`
  : "/api/nhl/sheet-backup?kind=calc";

type ModeBenchInfo = {
  shortFa: string;
  formulaFa: string;
  totPct: string;
  totRec: string;
  vipPct: string;
  vipRec: string;
  s2526: string;
  s2627: string;
  last50: string;
  badge: string;
};

const INITIAL_MODE_BENCHMARKS: Record<PlayerDeg3Mode, ModeBenchInfo> = {
  mode_c: {
    shortFa: "حالت C (اصلی): DEG3 = شماره پیراهن (جایگزین)",
    formulaFa: "DEG1 = 88 (28 GEMINI / AIR) | DEG2 = EnglishGem(Full_Name) mod 360 | DEG3 = Jersey_No mod 360",
    totPct: "57.0%",
    totRec: "126/221",
    vipPct: "59.1%",
    vipRec: "97/164",
    s2526: "47.9% (35/73)",
    s2627: "51.9% (14/27)",
    last50: "58.0% (29/50)",
    badge: "مدل پیش‌فرض حالت C (مستقل F1/F2/F3)",
  },
  mode_b: {
    shortFa: "حالت B: DEG3 = نام پیراهن + شماره پیراهن (جمع)",
    formulaFa: "DEG1 = 88 (28 GEMINI / AIR) | DEG2 = EnglishGem(Full_Name) mod 360 | DEG3 = (EnglishGem(Jersey_Name) + Jersey_No) mod 360",
    totPct: "59.8%",
    totRec: "134/224",
    vipPct: "59.3%",
    vipRec: "102/172",
    s2526: "56.3% (58/103)",
    s2627: "70.0% (14/20)",
    last50: "66.0% (33/50)",
    badge: "قوی‌ترین در فصل جاری ۲۰۲۶-۲۷ هاکی NHL",
  },
  mode_a: {
    shortFa: "حالت A: DEG3 = فقط نام روی پیراهن",
    formulaFa: "DEG1 = 88 (28 GEMINI / AIR) | DEG2 = EnglishGem(Full_Name) mod 360 | DEG3 = EnglishGem(Jersey_Name) mod 360",
    totPct: "59.0%",
    totRec: "124/210",
    vipPct: "64.0%",
    vipRec: "105/164",
    s2526: "57.1% (48/84)",
    s2627: "60.0% (18/30)",
    last50: "56.0% (28/50)",
    badge: "بالاترین دقت سطح ویژه VIP (۶۴٫۰٪)",
  },
};

function Home() {
  const [playerMode, setPlayerMode] = useState<PlayerDeg3Mode>(() => {
    try {
      const saved = window.localStorage.getItem("nhl_player_deg3_mode_v1");
      if (saved === "mode_c" || saved === "mode_b" || saved === "mode_a") return saved;
    } catch {}
    return "mode_c";
  });
  const [openBenchBar, setOpenBenchBar] = useState<boolean>(true);
  const [benchMap, setBenchMap] = useState<Record<PlayerDeg3Mode, ModeBenchInfo>>(INITIAL_MODE_BENCHMARKS);
  const [inputSheetUrl, setInputSheetUrl] = useState<string>(DEFAULT_INPUT_URL);
  const [calcSheetUrl, setCalcSheetUrl] = useState<string>(DEFAULT_CALC_URL);
  const [gemCount, setGemCount] = useState<number>(866);

  useEffect(() => {
    fetch("/api/nhl/config")
      .then((r) => (r.ok ? r.json() : null))
      .then((cfg) => {
        if (cfg?.ok) {
          if (cfg.inputSheetUrl) setInputSheetUrl(cfg.inputSheetUrl);
          if (cfg.calcSheetUrl) setCalcSheetUrl(cfg.calcSheetUrl);
        }
      })
      .catch(() => {});

    fetch("/nhl_players_gem.json")
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => {
        if (d?.playersCount) setGemCount(Number(d.playersCount));
      })
      .catch(() => {});

    fetch("/player_modes_comparison.json")
      .then((r) => (r.ok ? r.json() : null))
      .then((cmp) => {
        if (!cmp) return;
        setBenchMap((prev) => {
          const next = { ...prev };
          for (const mk of ["mode_c", "mode_b", "mode_a"] as PlayerDeg3Mode[]) {
            const st = cmp[mk];
            if (!st) continue;
            next[mk] = {
              ...prev[mk],
              totPct: `${st.total_2427?.pct ?? 0}%`,
              totRec: `${st.total_2427?.w ?? 0}/${st.total_2427?.n ?? 0}`,
              vipPct: `${st.vip_2427?.pct ?? 0}%`,
              vipRec: `${st.vip_2427?.w ?? 0}/${st.vip_2427?.n ?? 0}`,
              s2526: `${st.s2526?.pct ?? 0}% (${st.s2526?.w ?? 0}/${st.s2526?.n ?? 0})`,
              s2627: `${st.s2627?.pct ?? 0}% (${st.s2627?.w ?? 0}/${st.s2627?.n ?? 0})`,
              last50: `${st.last50?.pct ?? 0}% (${st.last50?.w ?? 0}/${st.last50?.n ?? 0})`,
            };
          }
          return next;
        });
      })
      .catch(() => {});
  }, []);

  const switchMode = (m: PlayerDeg3Mode) => {
    setPlayerMode(m);
    try {
      window.localStorage.setItem("nhl_player_deg3_mode_v1", m);
    } catch {}
  };

  const curInfo = benchMap[playerMode];

  return (
    <div className="min-h-[100dvh] w-full bg-background flex flex-col font-sans">
      <div className="flex-1 w-full max-w-6xl mx-auto px-4 py-8 md:py-10 flex flex-col">
        <header className="mb-5 flex flex-wrap items-start justify-between gap-4" dir="rtl">
          <div>
            <div className="flex flex-wrap items-center gap-3 mb-2">
              <div className="h-10 w-10 rounded-lg bg-sky-700 text-white flex items-center justify-center shadow-sm">
                <Users className="h-5 w-5" />
              </div>
              <h1
                className="text-xl md:text-2xl font-extrabold tracking-tight text-slate-900"
                data-testid="text-dashboard-title"
              >
                NHL-PLAYER-SIGNAL • داشبورد سیگنال هوشمند بازیکنان هاکی NHL
              </h1>
              <span
                className="px-2.5 py-1 rounded-full bg-sky-100 text-sky-950 border border-sky-300 text-xs font-mono font-extrabold"
                dir="ltr"
              >
                DEG1 = 88 (28 GEMINI • AIR)
              </span>
            </div>
            <p className="text-slate-600 text-xs md:text-sm max-w-4xl leading-relaxed">
              محاسبه روزانه برای <b>۳۲ تیم هاکی NHL</b> (شامل یوتا ماموت در Delta Center) بر اساس <b>۸ بازیکن اصلی فعال</b> هر تیم با وزن <b>میانگین زمان روی یخ (TOI)</b> و حذف خودکار مصدومان و محرومان (<b>OUT, IR, IR-LT, IR-NR, Suspension</b>) زیر آسمان استادیوم میزبان • با ثابت پایه <b>DEG1 = 88 (28 GEMINI / عنصر AIR)</b> و آزمایش هر ۳ فرمول <b>DEG3</b> بدون آینده‌نگری.
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-2" dir="rtl">
            <a
              href={inputSheetUrl}
              target="_blank"
              rel="noreferrer"
              data-testid="link-google-sheet-input"
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-emerald-600 hover:bg-emerald-700 text-white text-xs font-extrabold shadow-xs transition-colors"
            >
              <ExternalLink className="h-3.5 w-3.5" />
              شیت NHL-PLAYERS-GEM (۳۲ تیم • {gemCount.toLocaleString("fa-IR")} بازیکن)
            </a>
            <a
              href={calcSheetUrl}
              target="_blank"
              rel="noreferrer"
              data-testid="link-google-sheet-calc"
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-white hover:bg-sky-50 text-sky-950 border border-sky-300 text-xs font-extrabold shadow-2xs transition-colors"
            >
              <ExternalLink className="h-3.5 w-3.5" />
              شیت محاسبات NHL و مقایسه ۳ حالت DEG3 (پشتیبان JSON / Env)
            </a>
          </div>
        </header>

        {/* Top-Level 3-Mode DEG3 Switcher */}
        <div
          dir="rtl"
          className="mb-4 rounded-xl border-2 border-sky-300 bg-sky-50/90 p-2.5 shadow-xs space-y-2.5"
          data-testid="bar-player-deg3-modes"
        >
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div className="flex flex-wrap items-center gap-2">
              {(["mode_c", "mode_b", "mode_a"] as PlayerDeg3Mode[]).map((mk) => {
                const m = benchMap[mk];
                const active = playerMode === mk;
                return (
                  <button
                    key={mk}
                    type="button"
                    data-testid={`tab-player-${mk}`}
                    onClick={() => switchMode(mk)}
                    className={`px-3.5 py-2 rounded-lg text-xs font-extrabold transition-all ${
                      active
                        ? "bg-sky-700 text-white shadow-sm"
                        : "bg-white text-sky-950 hover:bg-sky-100 border border-sky-200"
                    }`}
                  >
                    {m.shortFa}
                  </button>
                );
              })}
            </div>

            <div className="flex items-center gap-2">
              <span className="px-2.5 py-1 rounded bg-white border border-sky-200 text-[11px] font-mono tabular-nums font-bold text-sky-900">
                دقت کل: {curInfo.totPct} ({curInfo.totRec}) • VIP: {curInfo.vipPct} • فصل جاری: {curInfo.s2627}
              </span>
              <button
                type="button"
                onClick={() => setOpenBenchBar((v) => !v)}
                className="px-2.5 py-1 rounded bg-white hover:bg-sky-100 border border-sky-300 text-sky-950 text-[11px] font-bold inline-flex items-center gap-1"
              >
                {openBenchBar ? "بستن جدول مقایسه ۳ حالت" : "مقایسه ۳ حالت DEG3"}
                {openBenchBar ? <ChevronUp className="h-3.5 w-3.5" /> : <ChevronDown className="h-3.5 w-3.5" />}
              </button>
            </div>
          </div>

          {openBenchBar && (
            <div className="bg-white rounded-lg border border-sky-200 p-3 overflow-x-auto">
              <div className="text-xs font-extrabold text-sky-950 mb-2 flex flex-wrap items-center justify-between gap-2">
                <span>نتیجه آزمایش بدون آینده‌نگری (r.d &lt; g.d) با وزن زمان روی یخ (TOI) و ثابت DEG1 = 88 (28 GEMINI) روی ۲۲٬۶۱۰ بازی هاکی NHL (۲۰۱۰ تا ۲۰۲۷):</span>
                <span className="font-mono text-[11px] text-emerald-800 bg-emerald-50 border border-emerald-200 px-2 py-0.5 rounded" dir="ltr">
                  {curInfo.formulaFa}
                </span>
              </div>
              <table className="w-full text-xs border-collapse font-mono tabular-nums text-right">
                <thead>
                  <tr className="bg-sky-100/80 text-sky-950 border-b border-sky-200 font-sans">
                    <th className="py-1.5 px-2.5">حالت فرمول DEG3 بازیکن (NHL)</th>
                    <th className="py-1.5 px-2.5">فرمول دقیق</th>
                    <th className="py-1.5 px-2.5">دقت کل (۲۰۲۴-۲۷)</th>
                    <th className="py-1.5 px-2.5">سطح ویژه VIP</th>
                    <th className="py-1.5 px-2.5">فصل ۲۰۲۵-۲۶</th>
                    <th className="py-1.5 px-2.5">فصل جاری ۲۰۲۶-۲۷</th>
                    <th className="py-1.5 px-2.5">۵۰ سیگنال اخیر</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-sky-100">
                  {(["mode_c", "mode_b", "mode_a"] as PlayerDeg3Mode[]).map((mk) => {
                    const m = benchMap[mk];
                    const isCur = playerMode === mk;
                    return (
                      <tr
                        key={mk}
                        onClick={() => switchMode(mk)}
                        className={`cursor-pointer transition-colors ${
                          isCur ? "bg-emerald-50/80 font-bold text-slate-950" : "hover:bg-sky-50/60 text-slate-700"
                        }`}
                      >
                        <td className="py-1.5 px-2.5 font-sans font-extrabold text-sky-950">
                          {isCur ? "✓ " : ""}{m.shortFa}
                        </td>
                        <td className="py-1.5 px-2.5 text-[11px]" dir="ltr">{m.formulaFa.split("|")[2]?.trim()}</td>
                        <td className="py-1.5 px-2.5 text-emerald-800 font-extrabold">{m.totPct} ({m.totRec})</td>
                        <td className="py-1.5 px-2.5 text-sky-900 font-extrabold">{m.vipPct} ({m.vipRec})</td>
                        <td className="py-1.5 px-2.5">{m.s2526}</td>
                        <td className="py-1.5 px-2.5 text-indigo-800 font-extrabold">{m.s2627}</td>
                        <td className="py-1.5 px-2.5">{m.last50}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>

        <NhlPlayerDashboardTab playerMode={playerMode} />

        <footer className="mt-10 pt-5 border-t border-border/50 text-center">
          <p className="text-xs text-muted-foreground font-mono uppercase tracking-widest">
            NHL-PLAYER-SIGNAL • 32 NHL Teams • DEG1 = 88 (28 GEMINI / AIR) • TOI-Weighted Active Lineups • Mode C/B/A
          </p>
        </footer>
      </div>
    </div>
  );
}

function Router() {
  return (
    <Switch>
      <Route path="/" component={Home} />
      <Route component={NotFound} />
    </Switch>
  );
}

function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <TooltipProvider>
        <WouterRouter base={import.meta.env.BASE_URL.replace(/\/$/, "")}>
          <Router />
        </WouterRouter>
        <Toaster />
      </TooltipProvider>
    </QueryClientProvider>
  );
}

export default App;
