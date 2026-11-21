import { useState, useEffect } from "react";
import { Switch, Route } from "wouter";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { Toaster } from "@/components/ui/toaster";
import { TooltipProvider } from "@/components/ui/tooltip";
import { Users, ExternalLink, ChevronDown, ChevronUp } from "lucide-react";
import NotFound from "@/pages/not-found";
import NhlDashboardTab, { type PlayerDeg3Mode } from "./NhlDashboardTab";

const queryClient = new QueryClient({
  defaultOptions: { queries: { refetchOnWindowFocus: false } },
});

const INPUT_SHEET_URL = "https://docs.google.com/spreadsheets/d/1DIuN12_G3FRfCThsmhPvtq8nLnU2gJBd0H_635t39FE/edit";
const CALC_SHEET_URL = "https://docs.google.com/spreadsheets/d/16lAFg4a896jWHx4WeDxoLk_RQslyJAHZw51YmjjRABs/edit";

type ModeBenchRow = {
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

const INITIAL_MODE_BENCHMARKS: Record<PlayerDeg3Mode, ModeBenchRow> = {
  mode_c: {
    shortFa: "حالت C (برتر): DEG3 = شماره پیراهن (جایگزین)",
    formulaFa: "DEG1 = 88 | DEG2 = EnglishGem(Full_Name) mod 360 | DEG3 = Jersey_No mod 360",
    totPct: "61.4%",
    totRec: "135/220",
    vipPct: "65.8%",
    vipRec: "77/117",
    s2526: "51.1% (48/94)",
    s2627: "65.0% (13/20)",
    last50: "58.0% (29/50)",
    badge: "بهترین دقت کل، VIP و فصل جاری (پیشنهادی)",
  },
  mode_b: {
    shortFa: "حالت B: DEG3 = نام پیراهن + شماره پیراهن (جمع)",
    formulaFa: "DEG1 = 88 | DEG2 = EnglishGem(Full_Name) mod 360 | DEG3 = (EnglishGem(Jersey_Name) + Jersey_No) mod 360",
    totPct: "54.5%",
    totRec: "126/231",
    vipPct: "58.9%",
    vipRec: "76/129",
    s2526: "53.6% (60/112)",
    s2627: "44.4% (8/18)",
    last50: "54.0% (27/50)",
    badge: "مدل ترکیبی نام و شماره پیراهن",
  },
  mode_a: {
    shortFa: "حالت A: DEG3 = فقط نام روی پیراهن",
    formulaFa: "DEG1 = 88 | DEG2 = EnglishGem(Full_Name) mod 360 | DEG3 = EnglishGem(Jersey_Name) mod 360",
    totPct: "58.4%",
    totRec: "136/233",
    vipPct: "58.7%",
    vipRec: "74/126",
    s2526: "53.2% (50/94)",
    s2627: "35.7% (5/14)",
    last50: "50.0% (25/50)",
    badge: "مدل پایه بدون شماره پیراهن",
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
  const [benchMap, setBenchMap] = useState<Record<PlayerDeg3Mode, ModeBenchRow>>(INITIAL_MODE_BENCHMARKS);

  useEffect(() => {
    fetch("/player_modes_comparison.json")
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => {
        if (!d) return;
        setBenchMap((prev) => {
          const next = { ...prev };
          const modes: PlayerDeg3Mode[] = ["mode_c", "mode_b", "mode_a"];
          let bestKey: PlayerDeg3Mode = "mode_c";
          let bestPct = -1;
          for (const mk of modes) {
            const p = Number(d[mk]?.total_2427?.pct ?? -1);
            if (p > bestPct) {
              bestPct = p;
              bestKey = mk;
            }
          }
          for (const mk of modes) {
            const st = d[mk];
            if (!st) continue;
            const t = st.total_2427 ?? { w: 0, n: 0, pct: 0 };
            const v = st.vip_2427 ?? { w: 0, n: 0, pct: 0 };
            const s25 = st.s2526 ?? { w: 0, n: 0, pct: 0 };
            const s26 = st.s2627 ?? { w: 0, n: 0, pct: 0 };
            const l50 = st.last50 ?? { w: 0, n: 0, pct: 0 };
            const isBest = mk === bestKey;
            const baseTitle =
              mk === "mode_c"
                ? `حالت C${isBest ? " (برتر)" : ""}: DEG3 = شماره پیراهن (جایگزین)`
                : mk === "mode_b"
                  ? `حالت B${isBest ? " (برتر)" : ""}: DEG3 = نام پیراهن + شماره پیراهن (جمع)`
                  : `حالت A${isBest ? " (برتر)" : ""}: DEG3 = فقط نام روی پیراهن`;
            next[mk] = {
              ...prev[mk],
              shortFa: baseTitle,
              totPct: `${t.pct}%`,
              totRec: `${t.w}/${t.n}`,
              vipPct: `${v.pct}%`,
              vipRec: `${v.w}/${v.n}`,
              s2526: `${s25.pct}% (${s25.w}/${s25.n})`,
              s2627: `${s26.pct}% (${s26.w}/${s26.n})`,
              last50: `${l50.pct}% (${l50.w}/${l50.n})`,
              badge: isBest ? "بهترین دقت کل بدون آینده‌نگری (پیشنهادی)" : prev[mk].badge,
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
            <div className="flex items-center gap-3 mb-2">
              <div className="h-10 w-10 rounded-lg bg-sky-700 text-white flex items-center justify-center shadow-sm">
                <Users className="h-5 w-5" />
              </div>
              <h1
                className="text-xl md:text-2xl font-extrabold tracking-tight text-slate-900"
                data-testid="text-dashboard-title"
              >
                داشبورد سیگنال هوشمند بازیکنان NHL • محاسبات نجومی و المنتی ترکیب بازیکنان (DEG1 = 88)
              </h1>
            </div>
            <p className="text-slate-600 text-xs md:text-sm max-w-4xl leading-relaxed">
              محاسبه روزانه بر اساس ۱۳ بازیکن اصلی فعال هر تیم (۱۲ اسکیت‌باز برتر به وزن زمان حضور روی یخ TOI + ۱ دروازه‌بان اصلی پیش از مسابقه و حذف خودکار مصدومان OUT/IR) زیر آسمان استادیوم میزبان • به همراه آزمایش هر ۳ فرمول <b>DEG3</b> (شماره پیراهن جایگزین، جمع نام و شماره پیراهن، و فقط نام پیراهن) بدون آینده‌نگری.
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-2" dir="rtl">
            <a
              href={INPUT_SHEET_URL}
              target="_blank"
              rel="noreferrer"
              data-testid="link-google-sheet-input"
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-emerald-600 hover:bg-emerald-700 text-white text-xs font-extrabold shadow-xs transition-colors"
            >
              <ExternalLink className="h-3.5 w-3.5" />
              شیت ورودی بازیکنان (NHL-PLAYERS-GEM • ۸۶۶ بازیکن)
            </a>
            <a
              href={CALC_SHEET_URL}
              target="_blank"
              rel="noreferrer"
              data-testid="link-google-sheet-calc"
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-white hover:bg-sky-50 text-sky-950 border border-sky-300 text-xs font-extrabold shadow-2xs transition-colors"
            >
              <ExternalLink className="h-3.5 w-3.5" />
              شیت محاسبات و مقایسه ۳ حالت DEG3
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
                <span>نتیجه آزمایش بدون آینده‌نگری (r.d &lt; g.d) برای نقش شماره پیراهن بازیکن در DEG3 (روی ۲۲٬۶۱۰ بازی NHL ۲۰۱۰ تا ۲۰۲۷ با DEG1=88):</span>
                <span className="font-mono text-[11px] text-emerald-800 bg-emerald-50 border border-emerald-200 px-2 py-0.5 rounded" dir="ltr">
                  {curInfo.formulaFa}
                </span>
              </div>
              <table className="w-full text-xs border-collapse font-mono tabular-nums text-right">
                <thead>
                  <tr className="bg-sky-100/80 text-sky-950 border-b border-sky-200 font-sans">
                    <th className="py-1.5 px-2.5">حالت فرمول DEG3 بازیکن</th>
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

        <NhlDashboardTab playerMode={playerMode} />

        <footer className="mt-10 pt-5 border-t border-border/50 text-center">
          <p className="text-xs text-muted-foreground font-mono uppercase tracking-widest">
            NHL Player Astrological &amp; Elemental Signal Dashboard (DEG1=88 • 12 Skaters + 1 Goalie • DEG3=Jersey Mode C/B/A)
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
        <Router />
        <Toaster />
      </TooltipProvider>
    </QueryClientProvider>
  );
}

export default App;
