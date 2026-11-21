import { Router, type IRouter } from "express";
import { spawn } from "node:child_process";
import crypto from "node:crypto";
import { promises as fs } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { logger } from "../lib/logger";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const PYTHON_DIR = path.resolve(__dirname, "..", "python");
const DATA_DIR = path.resolve(__dirname, "../../data");
const PRESET_FILE = path.join(DATA_DIR, "schedule_sync_state.json");
const SCRIPT = path.join(PYTHON_DIR, "step1_apply_preset.py");

export const NHL_DEG1 = 88;
export const NHL_DEG1_SIGN = "28 GEMINI";
export const NHL_DEG1_ELEMENT = "AIR";

export type ScheduleGamePreview = {
  date: string;
  weekday: string;
  time: string;
  homeTeam: string;
  awayTeam: string;
  deg1: number;
  homeDeg2: string;
  awayDeg2: string;
  arenaDeg3: string;
  arena: string;
  tz: string;
  lat: string;
  lon: string;
  season: string;
  gameType: string;
  homeScore: string;
  awayScore: string;
  winner: string;
};

export type ScheduleSyncState = {
  startDate: string;
  endDate: string;
  utcControl: boolean;
  deg1: number;
  deg1Sign?: string;
  deg1Element?: string;
  deg2Mode?: "full" | "code";
  appliedAt: string | null;
  rowsWritten: number | null;
  message: string | null;
  games: ScheduleGamePreview[];
};

export const DEFAULT_SYNC: ScheduleSyncState = {
  startDate: "2026-11-20",
  endDate: "2026-11-21",
  utcControl: false,
  deg1: NHL_DEG1,
  deg1Sign: NHL_DEG1_SIGN,
  deg1Element: NHL_DEG1_ELEMENT,
  deg2Mode: "full",
  appliedAt: null,
  rowsWritten: null,
  message: "NHL-PLAYER-SIGNAL Ready • DEG1 = 88 (28 GEMINI / AIR) • 32 NHL Teams",
  games: [],
};

const router: IRouter = Router();

async function readState(): Promise<ScheduleSyncState> {
  try {
    const raw = await fs.readFile(PRESET_FILE, "utf-8");
    const parsed = JSON.parse(raw);
    return {
      ...DEFAULT_SYNC,
      ...parsed,
      deg1: NHL_DEG1,
      deg1Sign: NHL_DEG1_SIGN,
      deg1Element: NHL_DEG1_ELEMENT,
    };
  } catch {
    return { ...DEFAULT_SYNC };
  }
}

async function writeState(state: ScheduleSyncState): Promise<void> {
  await fs.mkdir(DATA_DIR, { recursive: true });
  const tmp = PRESET_FILE + ".tmp";
  await fs.writeFile(tmp, JSON.stringify(state, null, 2), "utf-8");
  await fs.rename(tmp, PRESET_FILE);
}

function runSyncScript(params: {
  startDate: string;
  endDate: string;
  utcControl: boolean;
  deg1: number;
  deg2Mode: "full" | "code";
}): Promise<{
  ok: boolean;
  rowsWritten: number | null;
  message: string | null;
  error: string | null;
  games: ScheduleGamePreview[];
  output: string;
}> {
  return new Promise((resolve) => {
    const args = [
      SCRIPT,
      "--start-date",
      params.startDate,
      "--end-date",
      params.endDate,
      "--utc-control",
      params.utcControl ? "1" : "0",
      "--deg1",
      String(params.deg1 || NHL_DEG1),
      "--deg2-mode",
      params.deg2Mode || "full",
    ];
    const child = spawn("python3", args, { env: process.env, cwd: PYTHON_DIR });
    let out = "";
    child.stdout.on("data", (d: Buffer) => (out += d.toString()));
    child.stderr.on("data", (d: Buffer) => (out += d.toString()));
    child.on("error", (err) =>
      resolve({
        ok: false,
        rowsWritten: null,
        message: null,
        error: `Failed to start python3: ${err.message}`,
        games: [],
        output: out,
      }),
    );
    child.on("close", (code) => {
      let parsed: {
        ok?: boolean;
        rowsWritten?: number | null;
        message?: string | null;
        error?: string | null;
        games?: ScheduleGamePreview[];
      } | null = null;
      for (const line of out.split(/\r?\n/).reverse()) {
        if (line.startsWith("__RESULT__ ")) {
          try {
            parsed = JSON.parse(line.slice("__RESULT__ ".length));
          } catch {
            /* ignore */
          }
          break;
        }
      }
      const ok = (code ?? -1) === 0 && !!parsed?.ok;
      resolve({
        ok,
        rowsWritten: parsed?.rowsWritten ?? null,
        message: parsed?.message ?? null,
        error: ok ? null : parsed?.error ?? `python3 exited with code ${code}`,
        games: parsed?.games ?? [],
        output: out,
      });
    });
  });
}

let applying = false;

router.get("/preset", async (_req, res): Promise<void> => {
  res.json({ current: await readState(), defaults: DEFAULT_SYNC });
});

router.post("/preset/apply", async (req, res): Promise<void> => {
  const b = (req.body ?? {}) as Record<string, unknown>;
  const startDate = String(b.startDate ?? "2026-11-20").trim();
  const endDate = String(b.endDate ?? startDate).trim();
  const utcControl = Boolean(b.utcControl);
  const deg1 = Number(b.deg1 ?? NHL_DEG1) || NHL_DEG1;
  const deg2Mode: "full" | "code" = b.deg2Mode === "code" ? "code" : "full";

  if (!/^\d{4}-\d{2}-\d{2}$/.test(startDate) || !/^\d{4}-\d{2}-\d{2}$/.test(endDate)) {
    res.status(400).json({ error: "startDate and endDate must be YYYY-MM-DD" });
    return;
  }
  if (applying) {
    res.status(409).json({ error: "A schedule sync is already in progress" });
    return;
  }
  applying = true;
  try {
    const result = await runSyncScript({ startDate, endDate, utcControl, deg1, deg2Mode });
    const prev = await readState();
    const state: ScheduleSyncState = {
      startDate,
      endDate,
      utcControl,
      deg1,
      deg1Sign: NHL_DEG1_SIGN,
      deg1Element: NHL_DEG1_ELEMENT,
      deg2Mode,
      appliedAt: result.ok ? new Date().toISOString() : prev.appliedAt,
      rowsWritten: result.rowsWritten,
      message: result.ok ? result.message : result.error,
      games: result.ok ? result.games : prev.games,
    };
    if (result.ok) await writeState(state);
    else logger.error({ output: result.output.slice(-2000) }, "Schedule sync failed");
    res.status(result.ok ? 200 : 500).json({
      ok: result.ok,
      current: state,
      error: result.error,
      log: result.output.split(/\r?\n/).filter(Boolean).slice(-40),
    });
  } finally {
    applying = false;
  }
});

// ---------------------------------------------------------------------------
// KALSHI NHL MONEYLINE (KXNHLGAME) AUTO-BETTING & LIVE MARKET ENGINE
// ---------------------------------------------------------------------------

const KALSHI_STATE_FILE = path.join(DATA_DIR, "kalshi_nhl_state.json");

export type KalshiCardOrderPlan = {
  gameNo: number;
  date: string;
  homeTeam: string;
  awayTeam: string;
  winnerTeam: string;
  winnerCode: string;
  ticker: string;
  enabled: boolean;
  stakeUsd: number;
  limitCents: number;
  contracts: number;
};

export type KalshiLedgerEntry = {
  orderId: string;
  ticker: string;
  date: string;
  winnerTeam: string;
  contracts: number;
  limitCents: number;
  estCostUsd: number;
  status: string;
  executedAt: string;
};

export type KalshiServerState = {
  keyId: string;
  privateKeyPem: string;
  env: "live" | "demo";
  defaultStakeUsd: number;
  vipStakeUsd: number;
  autoScheduleEnabled: boolean;
  autoScheduleTimeEt: string;
  savedPlans: Record<string, { updatedAt: string; orders: KalshiCardOrderPlan[] }>;
  ledger: Record<string, KalshiLedgerEntry>;
};

const DEFAULT_KALSHI_STATE: KalshiServerState = {
  keyId: process.env.KALSHI_API_KEY_ID ?? "",
  privateKeyPem: process.env.KALSHI_PRIVATE_KEY ?? "",
  env: "live",
  defaultStakeUsd: 3,
  vipStakeUsd: 6,
  autoScheduleEnabled: false,
  autoScheduleTimeEt: "11:00",
  savedPlans: {},
  ledger: {},
};

async function readKalshiState(): Promise<KalshiServerState> {
  try {
    const raw = await fs.readFile(KALSHI_STATE_FILE, "utf-8");
    const parsed = JSON.parse(raw);
    return {
      ...DEFAULT_KALSHI_STATE,
      ...parsed,
      savedPlans: parsed.savedPlans ?? {},
      ledger: parsed.ledger ?? {},
    };
  } catch {
    return { ...DEFAULT_KALSHI_STATE };
  }
}

async function writeKalshiState(st: KalshiServerState): Promise<void> {
  await fs.mkdir(DATA_DIR, { recursive: true });
  const tmp = KALSHI_STATE_FILE + ".tmp";
  await fs.writeFile(tmp, JSON.stringify(st, null, 2), "utf-8");
  await fs.rename(tmp, KALSHI_STATE_FILE);
}

function normalizePrivateKey(rawPem: string): string {
  const s = rawPem.trim().replace(/\\n/g, "\n");
  const isPkcs8 = s.includes("BEGIN PRIVATE KEY");
  const body = s
    .replace(/-----BEGIN [A-Z ]+-----/g, "")
    .replace(/-----END [A-Z ]+-----/g, "")
    .replace(/\s+/g, "");
  const lines = body.match(/.{1,64}/g) ?? [body];
  const tag = isPkcs8 ? "PRIVATE KEY" : "RSA PRIVATE KEY";
  return `-----BEGIN ${tag}-----\n${lines.join("\n")}\n-----END ${tag}-----`;
}

function signKalshiRequest(privateKeyPem: string, timestampMs: string, method: string, pathWithoutQuery: string): string {
  const msg = `${timestampMs}${method.toUpperCase()}${pathWithoutQuery}`;
  const pem = normalizePrivateKey(privateKeyPem);
  const sig = crypto.sign("sha256", Buffer.from(msg, "utf-8"), {
    key: pem,
    padding: crypto.constants.RSA_PKCS1_PSS_PADDING,
    saltLength: crypto.constants.RSA_PSS_SALTLEN_DIGEST,
  });
  return sig.toString("base64");
}

function getKalshiBaseUrl(env: "live" | "demo"): string {
  return env === "demo" ? "https://demo-api.kalshi.co" : "https://api.elections.kalshi.com";
}

let nhlMarketCache: { fetchedAt: number; byTicker: Record<string, any> } = { fetchedAt: 0, byTicker: {} };

async function fetchOpenKalshiNhlMarkets(force = false): Promise<Record<string, any>> {
  const now = Date.now();
  if (!force && now - nhlMarketCache.fetchedAt < 20000 && Object.keys(nhlMarketCache.byTicker).length > 0) {
    return nhlMarketCache.byTicker;
  }
  try {
    const url = "https://api.elections.kalshi.com/trade-api/v2/markets?series_ticker=KXNHLGAME&status=open&limit=200";
    const resp = await fetch(url, { headers: { "User-Agent": "NHL-Player-Signal-Dashboard/1.0" } });
    if (!resp.ok) return nhlMarketCache.byTicker;
    const data = (await resp.json()) as { markets?: any[] };
    const map: Record<string, any> = {};
    for (const m of data.markets ?? []) {
      const yesAsk = Number(m.yes_ask_dollars ?? (m.yes_ask ? m.yes_ask / 100 : 0));
      const yesBid = Number(m.yes_bid_dollars ?? (m.yes_bid ? m.yes_bid / 100 : 0));
      const lastPrice = Number(m.last_price_dollars ?? (m.last_price ? m.last_price / 100 : 0));
      map[m.ticker] = {
        ticker: m.ticker,
        eventTicker: m.event_ticker,
        title: m.title,
        yesSubTitle: m.yes_sub_title,
        yesAsk,
        yesBid,
        lastPrice,
        yesAskCents: Math.round(yesAsk * 100),
        yesBidCents: Math.round(yesBid * 100),
        volume: m.volume_fp ?? m.volume ?? 0,
        status: m.status,
      };
    }
    nhlMarketCache = { fetchedAt: now, byTicker: map };
    return map;
  } catch {
    return nhlMarketCache.byTicker;
  }
}

router.get("/kalshi/nhl-markets", async (req, res): Promise<void> => {
  const force = req.query.force === "1";
  const markets = await fetchOpenKalshiNhlMarkets(force);
  res.json({ ok: true, series: "KXNHLGAME", deg1: NHL_DEG1, count: Object.keys(markets).length, markets });
});

router.get("/kalshi/markets", async (req, res): Promise<void> => {
  const force = req.query.force === "1";
  const markets = await fetchOpenKalshiNhlMarkets(force);
  res.json({ ok: true, series: "KXNHLGAME", deg1: NHL_DEG1, count: Object.keys(markets).length, markets });
});

router.get("/kalshi/state", async (_req, res): Promise<void> => {
  const st = await readKalshiState();
  res.json({
    ok: true,
    hasKey: Boolean(st.keyId && st.privateKeyPem),
    keyIdMasked: st.keyId ? `${st.keyId.slice(0, 6)}...${st.keyId.slice(-4)}` : "",
    env: st.env,
    defaultStakeUsd: st.defaultStakeUsd,
    vipStakeUsd: st.vipStakeUsd,
    autoScheduleEnabled: st.autoScheduleEnabled,
    autoScheduleTimeEt: st.autoScheduleTimeEt,
    savedPlans: st.savedPlans,
    ledger: st.ledger,
  });
});

router.post("/kalshi/config", async (req, res): Promise<void> => {
  const b = (req.body ?? {}) as Record<string, any>;
  const st = await readKalshiState();
  if (typeof b.keyId === "string" && b.keyId.trim() !== "") st.keyId = b.keyId.trim();
  if (typeof b.privateKeyPem === "string" && b.privateKeyPem.trim() !== "") st.privateKeyPem = b.privateKeyPem.trim();
  if (b.env === "live" || b.env === "demo") st.env = b.env;
  if (typeof b.defaultStakeUsd === "number" && b.defaultStakeUsd > 0) st.defaultStakeUsd = b.defaultStakeUsd;
  if (typeof b.vipStakeUsd === "number" && b.vipStakeUsd > 0) st.vipStakeUsd = b.vipStakeUsd;
  if (typeof b.autoScheduleEnabled === "boolean") st.autoScheduleEnabled = b.autoScheduleEnabled;
  if (typeof b.autoScheduleTimeEt === "string" && b.autoScheduleTimeEt.trim() !== "") st.autoScheduleTimeEt = b.autoScheduleTimeEt.trim();
  await writeKalshiState(st);
  res.json({
    ok: true,
    hasKey: Boolean(st.keyId && st.privateKeyPem),
    keyIdMasked: st.keyId ? `${st.keyId.slice(0, 6)}...${st.keyId.slice(-4)}` : "",
    env: st.env,
    defaultStakeUsd: st.defaultStakeUsd,
    vipStakeUsd: st.vipStakeUsd,
    autoScheduleEnabled: st.autoScheduleEnabled,
    autoScheduleTimeEt: st.autoScheduleTimeEt,
  });
});

router.post("/kalshi/balance", async (_req, res): Promise<void> => {
  const st = await readKalshiState();
  if (!st.keyId || !st.privateKeyPem) {
    res.status(400).json({ ok: false, error: "کلید API و Private Key هنوز وارد نشده است." });
    return;
  }
  try {
    const ts = String(Date.now());
    const apiPath = "/trade-api/v2/portfolio/balance";
    const sig = signKalshiRequest(st.privateKeyPem, ts, "GET", apiPath);
    const resp = await fetch(`${getKalshiBaseUrl(st.env)}${apiPath}`, {
      headers: {
        "KALSHI-ACCESS-KEY": st.keyId,
        "KALSHI-ACCESS-TIMESTAMP": ts,
        "KALSHI-ACCESS-SIGNATURE": sig,
      },
    });
    const text = await resp.text();
    let data: any = {};
    try { data = JSON.parse(text); } catch {}
    if (!resp.ok) {
      res.status(resp.status).json({ ok: false, error: data?.error?.message ?? data?.message ?? `HTTP ${resp.status}: ${text.slice(0, 200)}` });
      return;
    }
    const balCents = Number(data.balance ?? 0);
    const portCents = Number(data.portfolio_value ?? 0);
    res.json({
      ok: true,
      balanceUsd: (balCents / 100).toFixed(2),
      portfolioValueUsd: (portCents / 100).toFixed(2),
      raw: data,
    });
  } catch (e) {
    res.status(500).json({ ok: false, error: (e as Error).message });
  }
});

router.post("/kalshi/save-plan", async (req, res): Promise<void> => {
  const b = (req.body ?? {}) as { date?: string; orders?: KalshiCardOrderPlan[] };
  const date = String(b.date ?? "").trim();
  const orders = Array.isArray(b.orders) ? b.orders : [];
  if (!date) {
    res.status(400).json({ ok: false, error: "date is required" });
    return;
  }
  const st = await readKalshiState();
  st.savedPlans[date] = {
    updatedAt: new Date().toISOString(),
    orders,
  };
  await writeKalshiState(st);
  res.json({
    ok: true,
    date,
    savedCount: orders.filter((o) => o.enabled).length,
    updatedAt: st.savedPlans[date].updatedAt,
  });
});

async function executeKalshiPlanOrders(
  date: string,
  orders: KalshiCardOrderPlan[],
  mode: "dry_run" | "live",
): Promise<{ ok: boolean; mode: string; results: any[]; summary: any; error?: string }> {
  const st = await readKalshiState();
  const enabledOrders = orders.filter((o) => o.enabled);
  const liveMarkets: Record<string, any> = await fetchOpenKalshiNhlMarkets(true);

  if (mode === "live" && (!st.keyId || !st.privateKeyPem)) {
    return {
      ok: false,
      mode,
      results: [],
      summary: {},
      error: "برای ارسال سفارش واقعی (Live)، ابتدا کلید KALSHI API Key ID و RSA Private Key را در تنظیمات Kalshi وارد و ذخیره کنید.",
    };
  }

  const results: any[] = [];
  let totalCostUsd = 0;
  let totalPotentialProfitUsd = 0;
  let sentCount = 0;

  for (const ord of enabledOrders) {
    const ledgerKey = `${date}:${ord.ticker}`;
    if (st.ledger[ledgerKey]) {
      results.push({
        gameNo: ord.gameNo,
        ticker: ord.ticker,
        winnerTeam: ord.winnerTeam,
        status: "ALREADY_EXECUTED",
        orderId: st.ledger[ledgerKey].orderId,
        contracts: st.ledger[ledgerKey].contracts,
        limitCents: st.ledger[ledgerKey].limitCents,
        estCostUsd: st.ledger[ledgerKey].estCostUsd,
        message: `قبلاً ثبت شده (Order ID: ${st.ledger[ledgerKey].orderId})`,
      });
      continue;
    }

    const mkt = liveMarkets[ord.ticker];
    const liveAskCents = mkt && mkt.yesAskCents > 0 ? mkt.yesAskCents : ord.limitCents || 55;
    const limitCents = Math.min(99, Math.max(1, ord.limitCents > 0 ? ord.limitCents : liveAskCents));
    const stakeUsd = Math.max(1, Number(ord.stakeUsd || st.defaultStakeUsd || 3));
    const contracts = Math.max(1, Math.floor((stakeUsd * 100) / limitCents));
    const estCostUsd = Number(((contracts * limitCents) / 100).toFixed(2));
    const potentialProfitUsd = Number(((contracts * (100 - limitCents)) / 100).toFixed(2));

    if (mode === "dry_run") {
      totalCostUsd += estCostUsd;
      totalPotentialProfitUsd += potentialProfitUsd;
      results.push({
        gameNo: ord.gameNo,
        ticker: ord.ticker,
        winnerTeam: ord.winnerTeam,
        marketFound: Boolean(mkt),
        status: mkt ? "DRY_RUN_READY" : "MARKET_NOT_OPEN_YET",
        contracts,
        limitCents,
        liveAskCents: mkt?.yesAskCents ?? null,
        liveBidCents: mkt?.yesBidCents ?? null,
        estCostUsd,
        potentialProfitUsd,
        message: mkt
          ? `آماده ارسال: خرید ${contracts} قرارداد YES @ ${limitCents}¢ (هزینه: $${estCostUsd} • سود خالص برد: +$${potentialProfitUsd})`
          : `بازار ${ord.ticker} هنوز در Kalshi باز نشده است (تخمین @ ${limitCents}¢)`,
      });
      continue;
    }

    try {
      const ts = String(Date.now());
      const orderPath = "/trade-api/v2/portfolio/events/orders";
      const sig = signKalshiRequest(st.privateKeyPem, ts, "POST", orderPath);
      const clientOrderId = `nhl-${date.replace(/-/g, "")}-${ord.gameNo}-${Date.now()}`;
      const v2Payload = {
        ticker: ord.ticker,
        side: "bid",
        count: `${contracts}.00`,
        price: (limitCents / 100).toFixed(4),
        time_in_force: "good_till_canceled",
        self_trade_prevention_type: "taker_at_cross",
        client_order_id: clientOrderId,
      };
      const resp = await fetch(`${getKalshiBaseUrl(st.env)}${orderPath}`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "KALSHI-ACCESS-KEY": st.keyId,
          "KALSHI-ACCESS-TIMESTAMP": ts,
          "KALSHI-ACCESS-SIGNATURE": sig,
        },
        body: JSON.stringify(v2Payload),
      });
      const respText = await resp.text();
      let respJson: any = {};
      try { respJson = JSON.parse(respText); } catch {}
      const orderObj = respJson?.order ?? respJson;
      const orderId = orderObj?.order_id;

      if ((resp.status === 201 || resp.status === 200) && orderId) {
        sentCount++;
        totalCostUsd += estCostUsd;
        totalPotentialProfitUsd += potentialProfitUsd;
        st.ledger[ledgerKey] = {
          orderId: String(orderId),
          ticker: ord.ticker,
          date,
          winnerTeam: ord.winnerTeam,
          contracts,
          limitCents,
          estCostUsd,
          status: String(orderObj?.status ?? "executed"),
          executedAt: new Date().toISOString(),
        };
        results.push({
          gameNo: ord.gameNo,
          ticker: ord.ticker,
          winnerTeam: ord.winnerTeam,
          status: "EXECUTED",
          orderId,
          contracts,
          limitCents,
          estCostUsd,
          potentialProfitUsd,
          message: `ثبت موفق در Kalshi ✓ (Order ID: ${orderId})`,
        });
      } else {
        results.push({
          gameNo: ord.gameNo,
          ticker: ord.ticker,
          winnerTeam: ord.winnerTeam,
          status: `ERROR_${resp.status}`,
          contracts,
          limitCents,
          estCostUsd,
          message: respJson?.error?.message ?? respJson?.message ?? respText.slice(0, 160),
        });
      }
    } catch (err) {
      results.push({
        gameNo: ord.gameNo,
        ticker: ord.ticker,
        winnerTeam: ord.winnerTeam,
        status: "NETWORK_ERROR",
        message: (err as Error).message,
      });
    }
  }

  if (mode === "live" && sentCount > 0) {
    await writeKalshiState(st);
  }

  return {
    ok: true,
    mode,
    results,
    summary: {
      date,
      totalCards: enabledOrders.length,
      sentCount,
      totalCostUsd: Number(totalCostUsd.toFixed(2)),
      totalPotentialProfitUsd: Number(totalPotentialProfitUsd.toFixed(2)),
    },
  };
}

router.post("/kalshi/execute", async (req, res): Promise<void> => {
  const b = (req.body ?? {}) as { date?: string; orders?: KalshiCardOrderPlan[]; mode?: "dry_run" | "live" };
  const date = String(b.date ?? "").trim();
  const mode = b.mode === "live" ? "live" : "dry_run";
  let orders = Array.isArray(b.orders) ? b.orders : [];
  if (orders.length === 0 && date) {
    const st = await readKalshiState();
    orders = st.savedPlans[date]?.orders ?? [];
  }
  const out = await executeKalshiPlanOrders(date, orders, mode);
  res.status(out.ok ? 200 : 400).json(out);
});

export interface KalshiComboLegInput {
  gameNo: number;
  eventTicker: string;
  marketTicker: string;
  winnerTeam: string;
  yesAskCents: number;
  twinPct: number;
  agree: boolean;
}

router.post("/kalshi/combo", async (req, res): Promise<void> => {
  const b = (req.body ?? {}) as {
    date?: string;
    legs?: KalshiComboLegInput[];
    stakeUsd?: number;
    limitCents?: number;
    mode?: "dry_run" | "live";
  };
  const date = String(b.date ?? "").trim();
  const legs = Array.isArray(b.legs) ? b.legs : [];
  const mode = b.mode === "live" ? "live" : "dry_run";

  if (legs.length < 2 || legs.length > 4) {
    res.status(400).json({
      ok: false,
      error: "تعداد بازی‌های کمبو (Parlay) باید بین ۲ تا ۴ بازی باشد.",
    });
    return;
  }

  const probProduct = legs.reduce((acc, l) => {
    const p = Math.min(0.98, Math.max(0.02, (Number(l.yesAskCents) || 55) / 100));
    return acc * p;
  }, 1);
  const fairCents = Math.max(1, Math.min(95, Math.round(probProduct * 100)));
  const limitCents = Math.max(1, Math.min(98, Number(b.limitCents) > 0 ? Math.round(Number(b.limitCents)) : Math.min(95, fairCents + 1)));
  const stakeUsd = Math.max(1, Number(b.stakeUsd) || 4);
  const contracts = Math.max(1, Math.floor((stakeUsd * 100) / limitCents));
  const estCostUsd = Number(((contracts * limitCents) / 100).toFixed(2));
  const maxPayoutUsd = Number(contracts.toFixed(2));
  const potentialProfitUsd = Number((maxPayoutUsd - estCostUsd).toFixed(2));
  const multiplier = Number((100 / limitCents).toFixed(2));

  const mveMarketTicker = `KXMVE-NHL-${date.replace(/-/g, "")}-${legs.map((l) => l.marketTicker.split("-").pop()).join("-")}`;
  const mveEventTicker = `KXMVE-NHL-${date.replace(/-/g, "")}`;

  if (mode === "dry_run") {
    res.json({
      ok: true,
      mode: "dry_run",
      date,
      comboTicker: mveMarketTicker,
      comboEventTicker: mveEventTicker,
      mveCreated: false,
      mveLookupNote: "",
      legs,
      fairCents,
      limitCents,
      mveLiveAskCents: null,
      mveLiveBidCents: null,
      stakeUsd,
      contracts,
      estCostUsd,
      maxPayoutUsd,
      potentialProfitUsd,
      multiplier,
      message: `پیش‌نمایش کمبوی ${legs.length} بازی هاکی NHL آماده است • خرید ${contracts} قرارداد @ ${limitCents}¢ (ضریب ${multiplier}x • هزینه $${estCostUsd} • سود خالص برد: +$${potentialProfitUsd})`,
    });
    return;
  }

  const st = await readKalshiState();
  if (!st.keyId || !st.privateKeyPem) {
    res.status(400).json({ ok: false, error: "کلید Kalshi API در سرور تنظیم نشده است." });
    return;
  }

  try {
    const orderPath = "/trade-api/v2/portfolio/events/orders";
    const oTs = String(Date.now());
    const oSig = signKalshiRequest(st.privateKeyPem, oTs, "POST", orderPath);
    const clientOrderId = `nhl-combo-${date.replace(/-/g, "")}-${Date.now()}`;
    const v2Payload = {
      ticker: mveMarketTicker,
      side: "bid",
      count: `${contracts}.00`,
      price: (limitCents / 100).toFixed(4),
      time_in_force: "good_till_canceled",
      self_trade_prevention_type: "taker_at_cross",
      client_order_id: clientOrderId,
    };
    const oRes = await fetch(`${getKalshiBaseUrl(st.env)}${orderPath}`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "KALSHI-ACCESS-KEY": st.keyId,
        "KALSHI-ACCESS-TIMESTAMP": oTs,
        "KALSHI-ACCESS-SIGNATURE": oSig,
      },
      body: JSON.stringify(v2Payload),
    });
    const oTxt = await oRes.text();
    let oJson: any = {};
    try { oJson = JSON.parse(oTxt); } catch {}
    const orderObj = oJson?.order ?? oJson;
    const orderId = orderObj?.order_id;
    if ((oRes.status === 201 || oRes.status === 200) && orderId) {
      st.ledger[`${date}:COMBO:${mveMarketTicker}`] = {
        orderId: String(orderId),
        ticker: mveMarketTicker,
        date,
        winnerTeam: legs.map((l) => l.winnerTeam).join(" + "),
        contracts,
        limitCents,
        estCostUsd,
        status: "executed",
        executedAt: new Date().toISOString(),
      };
      await writeKalshiState(st);
      res.json({
        ok: true,
        mode: "live",
        status: "EXECUTED",
        orderId,
        comboTicker: mveMarketTicker,
        legs,
        contracts,
        limitCents,
        estCostUsd,
        maxPayoutUsd,
        potentialProfitUsd,
        multiplier,
        message: `سفارش کمبوی ${legs.length} بازی NHL با موفقیت در Kalshi ثبت شد ✓ (Order ID: ${orderId})`,
      });
      return;
    }
    res.json({
      ok: false,
      mode: "live",
      status: `ERROR_${oRes.status}`,
      comboTicker: mveMarketTicker,
      legs,
      contracts,
      limitCents,
      estCostUsd,
      maxPayoutUsd,
      potentialProfitUsd,
      multiplier,
      message: oJson?.error?.message ?? oJson?.message ?? oTxt.slice(0, 180),
    });
  } catch (err) {
    res.status(500).json({ ok: false, error: (err as Error).message });
  }
});

router.get("/kalshi/audit", async (_req, res): Promise<void> => {
  try {
    const st = await readKalshiState();
    if (!st.keyId || !st.privateKeyPem) {
      res.status(400).json({ ok: false, error: "No Kalshi key configured" });
      return;
    }
    const fetchKalshi = async (p: string) => {
      const ts = String(Date.now());
      const sig = signKalshiRequest(st.privateKeyPem, ts, "GET", p.split("?")[0]);
      const r = await fetch(`${getKalshiBaseUrl(st.env)}${p}`, {
        headers: {
          "KALSHI-ACCESS-KEY": st.keyId,
          "KALSHI-ACCESS-TIMESTAMP": ts,
          "KALSHI-ACCESS-SIGNATURE": sig,
        },
      });
      return await r.json();
    };
    const [settlements, fills, orders, balance] = await Promise.all([
      fetchKalshi("/trade-api/v2/portfolio/settlements?limit=50"),
      fetchKalshi("/trade-api/v2/portfolio/fills?limit=50"),
      fetchKalshi("/trade-api/v2/portfolio/orders?limit=50"),
      fetchKalshi("/trade-api/v2/portfolio/balance"),
    ]);
    res.json({ ok: true, balance, settlements, fills, orders });
  } catch (err) {
    res.status(500).json({ ok: false, error: (err as Error).message });
  }
});

// ---------------------------------------------------------------------------
// NHL-PLAYER-SIGNAL (DEG1 = 88 • 28 GEMINI / AIR) ENDPOINTS & LOCAL BACKUPS
// ---------------------------------------------------------------------------

async function resolveNhlPublicFile(filename: string): Promise<string> {
  const candidates = [
    path.resolve(__dirname, "../../calc-dashboard/public", filename),
    path.resolve(__dirname, "../../../calc-dashboard/public", filename),
    path.join(DATA_DIR, filename),
    path.join(PYTHON_DIR, filename),
  ];
  for (const p of candidates) {
    try {
      await fs.access(p);
      return p;
    } catch {}
  }
  return candidates[0];
}

function normalizeModeParam(raw: unknown): "mode_c" | "mode_b" | "mode_a" {
  const m = String(raw ?? "mode_c").trim().toLowerCase();
  if (m === "mode_a" || m === "mode_b" || m === "mode_c") return m;
  return "mode_c";
}

router.get("/nhl/config", async (_req, res): Promise<void> => {
  const inId = (process.env.NHL_PLAYER_INPUT_SHEET_ID ?? "").trim();
  const calcId = (process.env.NHL_PLAYER_CALC_SHEET_ID ?? "").trim();
  res.json({
    ok: true,
    league: "NHL",
    project: "NHL-PLAYER-SIGNAL",
    teamsCount: 32,
    deg1: NHL_DEG1,
    deg1Sign: NHL_DEG1_SIGN,
    deg1Element: NHL_DEG1_ELEMENT,
    excludedStatuses: ["OUT", "IR", "IR-LT", "IR-NR", "Suspension"],
    inputSheetId: inId || null,
    calcSheetId: calcId || null,
    inputSheetUrl: inId ? `https://docs.google.com/spreadsheets/d/${inId}/edit` : "/api/nhl/players-gem",
    calcSheetUrl: calcId ? `https://docs.google.com/spreadsheets/d/${calcId}/edit` : "/api/nhl/sheet-backup?kind=calc",
    usingLocalJsonBackup: !inId || !calcId,
  });
});

router.get("/predictions", async (req, res): Promise<void> => {
  try {
    const mode = normalizeModeParam(req.query.mode);
    const file = await resolveNhlPublicFile(`player_nhl_preds_${mode}.json`);
    const raw = await fs.readFile(file, "utf-8");
    res.setHeader("Content-Type", "application/json; charset=utf-8");
    res.send(raw);
  } catch (e) {
    res.status(500).json({ ok: false, deg1: NHL_DEG1, error: (e as Error).message, games: [] });
  }
});

router.get("/nhl/predictions", async (req, res): Promise<void> => {
  try {
    const mode = normalizeModeParam(req.query.mode);
    const file = await resolveNhlPublicFile(`player_nhl_preds_${mode}.json`);
    const raw = await fs.readFile(file, "utf-8");
    res.setHeader("Content-Type", "application/json; charset=utf-8");
    res.send(raw);
  } catch (e) {
    res.status(500).json({ ok: false, deg1: NHL_DEG1, error: (e as Error).message, games: [] });
  }
});

router.get("/nhl/history-pack", async (req, res): Promise<void> => {
  try {
    const mode = normalizeModeParam(req.query.mode);
    const file = await resolveNhlPublicFile(`player_nhl_hist_${mode}.json`);
    const raw = await fs.readFile(file, "utf-8");
    res.setHeader("Content-Type", "application/json; charset=utf-8");
    res.send(raw);
  } catch (e) {
    res.status(500).json({ ok: false, deg1: NHL_DEG1, error: (e as Error).message });
  }
});

router.get("/nhl/players-gem", async (_req, res): Promise<void> => {
  try {
    const file = await resolveNhlPublicFile("nhl_players_gem.json");
    const raw = await fs.readFile(file, "utf-8");
    res.setHeader("Content-Type", "application/json; charset=utf-8");
    res.send(raw);
  } catch (e) {
    res.status(500).json({ ok: false, deg1: NHL_DEG1, error: (e as Error).message });
  }
});

router.get("/nhl/teams-gem", async (_req, res): Promise<void> => {
  try {
    const file = await resolveNhlPublicFile("nhl_gem_sheet.json");
    const raw = await fs.readFile(file, "utf-8");
    res.setHeader("Content-Type", "application/json; charset=utf-8");
    res.send(raw);
  } catch (e) {
    res.status(500).json({ ok: false, deg1: NHL_DEG1, error: (e as Error).message });
  }
});

router.get("/nhl/sheet-backup", async (req, res): Promise<void> => {
  try {
    const kind = String(req.query.kind ?? "calc").toLowerCase() === "input" ? "input" : "calc";
    const fname = kind === "input" ? "nhl_sheet_input_backup.json" : "nhl_sheet_calc_backup.json";
    const file = await resolveNhlPublicFile(fname);
    const raw = await fs.readFile(file, "utf-8");
    res.setHeader("Content-Type", "application/json; charset=utf-8");
    res.send(raw);
  } catch (e) {
    res.status(500).json({ ok: false, deg1: NHL_DEG1, error: (e as Error).message });
  }
});

let nhlSyncing = false;

router.post("/nhl/sync", async (req, res): Promise<void> => {
  if (nhlSyncing) {
    res.status(409).json({ ok: false, error: "بروزرسانی نتایج واقعی هاکی NHL در حال انجام است." });
    return;
  }
  const b = (req.body ?? {}) as Record<string, unknown>;
  const startDate = typeof b.startDate === "string" ? b.startDate.trim() : "";
  const endDate = typeof b.endDate === "string" ? b.endDate.trim() : "";
  const targetDate = typeof b.targetDate === "string" ? b.targetDate.trim() : "";

  nhlSyncing = true;
  try {
    const scriptCandidates = [
      path.resolve(__dirname, "../../python/nhl_live_sync.py"),
      path.resolve(__dirname, "../python/nhl_live_sync.py"),
    ];
    let scriptPath = scriptCandidates[0];
    for (const sc of scriptCandidates) {
      try {
        await fs.access(sc);
        scriptPath = sc;
        break;
      } catch {}
    }
    const args = [scriptPath];
    if (/^\d{4}-\d{2}-\d{2}$/.test(startDate)) args.push("--start-date", startDate);
    if (/^\d{4}-\d{2}-\d{2}$/.test(endDate)) args.push("--end-date", endDate);
    if (/^\d{4}-\d{2}-\d{2}$/.test(targetDate)) args.push("--target-date", targetDate);

    const out = await new Promise<{ code: number; stdout: string }>((resolve) => {
      const child = spawn("python3", args, { env: process.env, cwd: path.dirname(scriptPath) });
      let buf = "";
      child.stdout.on("data", (d: Buffer) => (buf += d.toString()));
      child.stderr.on("data", (d: Buffer) => (buf += d.toString()));
      child.on("error", (err) => resolve({ code: -1, stdout: err.message }));
      child.on("close", (c) => resolve({ code: c ?? -1, stdout: buf }));
    });

    let parsed: any = null;
    for (const line of out.stdout.split(/\r?\n/).reverse()) {
      if (line.startsWith("__NHL_SYNC__ ")) {
        try {
          parsed = JSON.parse(line.slice("__NHL_SYNC__ ".length));
        } catch {}
        break;
      }
    }
    if (out.code === 0 && parsed?.ok) {
      res.json(parsed);
    } else {
      res.status(500).json({ ok: false, deg1: NHL_DEG1, error: out.stdout.slice(-600) || `Exited ${out.code}` });
    }
  } finally {
    nhlSyncing = false;
  }
});

export default router;
