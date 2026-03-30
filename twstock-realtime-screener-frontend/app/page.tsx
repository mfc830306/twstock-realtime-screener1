"use client";

import { useEffect, useMemo, useState } from "react";

/* ─── Types ──────────────────────────────────────────────── */
type Stock = {
  market?: string;
  symbol: string;
  name: string;
  price: number;
  change: number;
  change_percent: number;
  volume?: number;
  score?: number;
  recommendation_score?: number;
  signal?: string;
  reason?: string;
  entry_price?: string;
  target_price?: string;
  stop_loss?: string;
};

type BackendCategory = {
  key: string;
  label: string;
  count: number;
};

type ApiResponse = {
  success: boolean;
  market_status?: string;
  data_date?: string;
  last_update?: string;
  total?: number;
  stocks: Stock[];
  recommendations?: Stock[];
  categories?: BackendCategory[];
  message?: string;
  source_summary?: {
    twse_data_date?: string;
    tpex_data_date?: string;
  };
};

/* ─── Constants ──────────────────────────────────────────── */
const BACKEND_URL =
  "https://twstock-realtime-screener1.onrender.com/stocks?limit=5000";

const PRICE_CATEGORIES = [
  { key: "all",     label: "全部" },
  { key: "0-50",    label: "0 ~ 50 元" },
  { key: "50-100",  label: "50 ~ 100 元" },
  { key: "100-200", label: "100 ~ 200 元" },
  { key: "200-500", label: "200 ~ 500 元" },
  { key: "500+",    label: "500 元以上" },
] as const;

type CategoryKey = (typeof PRICE_CATEGORIES)[number]["key"];
type RankType = "recommend" | "up" | "down";

/* ─── Helpers ────────────────────────────────────────────── */
function getPriceCategory(price: number): CategoryKey {
  if (price < 50)  return "0-50";
  if (price < 100) return "50-100";
  if (price < 200) return "100-200";
  if (price < 500) return "200-500";
  return "500+";
}

function fmtNum(n?: number) {
  if (n === undefined || n === null || Number.isNaN(n)) return "-";
  return n.toLocaleString("zh-TW");
}

function fmtPrice(n?: number) {
  if (n === undefined || n === null || Number.isNaN(n)) return "-";
  return n.toLocaleString("zh-TW");
}

function fmtSigned(n?: number, digits = 2) {
  if (n === undefined || n === null || Number.isNaN(n)) return "-";
  return `${n > 0 ? "+" : ""}${n.toFixed(digits)}`;
}

function fmtDate(s?: string) {
  if (!s || s === "-") return "-";
  const c = String(s).replace(/\D/g, "");
  if (c.length === 8)
    return `${c.slice(0, 4)}/${c.slice(4, 6)}/${c.slice(6, 8)}`;
  return s;
}

function marketColor(status?: string) {
  if (!status) return "var(--yellow)";
  if (status.includes("開盤")) return "var(--green)";
  if (status.includes("收盤")) return "var(--red)";
  return "var(--yellow)";
}

function buildCounts(
  stocks: Stock[],
  backend?: BackendCategory[]
): Record<CategoryKey, number> {
  const base: Record<CategoryKey, number> = {
    all: stocks.length, "0-50": 0, "50-100": 0,
    "100-200": 0, "200-500": 0, "500+": 0,
  };
  if (!backend?.length) {
    for (const s of stocks) base[getPriceCategory(s.price)] += 1;
    return base;
  }
  const m = new Map(backend.map((b) => [b.key, Number(b.count || 0)]));
  return {
    all: stocks.length,
    "0-50":    (m.get("0-10") || 0) + (m.get("10-20") || 0) + (m.get("20-50") || 0),
    "50-100":  m.get("50-100") || 0,
    "100-200": m.get("100-200") || 0,
    "200-500": m.get("200-500") || 0,
    "500+":    (m.get("500-1000") || 0) + (m.get("1000+") || 0),
  };
}

function normalize(s: Stock): Stock {
  return {
    ...s,
    price:              Number(s.price ?? 0),
    change:             Number(s.change ?? 0),
    change_percent:     Number(s.change_percent ?? 0),
    volume:             Number(s.volume ?? 0),
    score:              Number(s.score ?? 0),
    recommendation_score: Number(s.recommendation_score ?? 0),
  };
}

/* ─── Inline styles (no separate CSS file needed) ───────── */
const S = {
  /* layout */
  page: {
    display: "grid" as const,
    gridTemplateRows: "50px 1fr",
    height: "100vh",
    overflow: "hidden",
    background: "var(--navy)",
    color: "var(--text)",
  },
  topbar: {
    display: "flex" as const,
    alignItems: "center" as const,
    justifyContent: "space-between" as const,
    padding: "0 24px",
    background: "var(--navy2)",
    borderBottom: "1px solid var(--border)",
    gap: "16px",
    flexShrink: 0,
  },
  body: {
    display: "grid" as const,
    gridTemplateColumns: "210px 1fr",
    overflow: "hidden",
    minHeight: 0,
  },
  sidebar: {
    background: "var(--navy2)",
    borderRight: "1px solid var(--border)",
    overflowY: "auto" as const,
    padding: "16px 0 24px",
  },
  main: {
    overflowY: "auto" as const,
    padding: "20px 24px 32px",
  },
  /* topbar elements */
  logo: {
    fontFamily: "var(--mono)",
    fontSize: "15px",
    fontWeight: 900,
    color: "var(--blue)",
    letterSpacing: "1px",
    flexShrink: 0,
  } as React.CSSProperties,
  logoSub: {
    fontFamily: "var(--sans)",
    fontSize: "13px",
    fontWeight: 400,
    color: "var(--text2)",
    marginLeft: "10px",
  },
  metaRow: {
    display: "flex" as const,
    alignItems: "center" as const,
    gap: "14px",
    fontSize: "12px",
    color: "var(--text2)",
    flexWrap: "wrap" as const,
  },
  marketPill: (color: string): React.CSSProperties => ({
    display: "flex",
    alignItems: "center",
    gap: "6px",
    padding: "4px 10px",
    borderRadius: "20px",
    background: color === "var(--green)" ? "var(--green-dim)" : "rgba(245,158,11,.12)",
    border: `1px solid ${color}40`,
    color,
    fontSize: "12px",
    fontWeight: 700,
  }),
  dot: (color: string): React.CSSProperties => ({
    width: "7px",
    height: "7px",
    borderRadius: "50%",
    background: color,
    flexShrink: 0,
  }),
  refreshBtn: (loading: boolean): React.CSSProperties => ({
    border: "1px solid var(--border2)",
    borderRadius: "var(--radius-sm)",
    padding: "6px 14px",
    background: "transparent",
    color: loading ? "var(--text3)" : "var(--blue)",
    fontSize: "12px",
    fontWeight: 700,
    cursor: loading ? "not-allowed" : "pointer",
    opacity: loading ? 0.6 : 1,
    transition: "all .15s",
  }),
  /* sidebar */
  sLabel: {
    fontSize: "10px",
    fontWeight: 700,
    letterSpacing: ".1em",
    textTransform: "uppercase" as const,
    color: "var(--text3)",
    padding: "0 14px",
    marginBottom: "8px",
    marginTop: "18px",
    display: "block" as const,
  },
  statGrid: {
    display: "grid" as const,
    gridTemplateColumns: "1fr 1fr",
    gap: "5px",
    padding: "0 10px",
  },
  statBox: (accent = false): React.CSSProperties => ({
    background: accent ? "var(--blue-dim)" : "var(--navy3)",
    border: `1px solid ${accent ? "rgba(94,164,255,.35)" : "var(--border)"}`,
    borderRadius: "var(--radius-sm)",
    padding: "8px",
    textAlign: "center",
    gridColumn: accent ? "1 / -1" : undefined,
  }),
  statVal: (accent = false): React.CSSProperties => ({
    fontFamily: "var(--mono)",
    fontSize: accent ? "20px" : "17px",
    fontWeight: 700,
    color: accent ? "var(--blue)" : "var(--text)",
    lineHeight: 1.2,
  }),
  statLabel: {
    fontSize: "10px",
    color: "var(--text2)",
    marginTop: "2px",
  },
  divider: {
    height: "1px",
    background: "var(--border)",
    margin: "12px 14px",
  },
  mktabs: {
    display: "flex" as const,
    gap: "4px",
    padding: "0 10px",
  },
  mktab: (on: boolean): React.CSSProperties => ({
    flex: 1,
    textAlign: "center",
    padding: "5px 0",
    borderRadius: "var(--radius-sm)",
    cursor: "pointer",
    fontSize: "11px",
    fontWeight: on ? 700 : 400,
    color: on ? "var(--blue)" : "var(--text2)",
    background: on ? "var(--blue-dim)" : "var(--navy3)",
    border: `1px solid ${on ? "var(--blue)" : "var(--border)"}`,
    transition: "all .12s",
  }),
  pfItem: (on: boolean): React.CSSProperties => ({
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    padding: "7px 10px",
    margin: "0 8px 1px",
    borderRadius: "var(--radius-sm)",
    cursor: "pointer",
    fontSize: "12px",
    fontWeight: on ? 700 : 400,
    color: on ? "var(--blue)" : "var(--text2)",
    background: on ? "var(--blue-dim)" : "transparent",
    border: "none",
    width: "calc(100% - 16px)",
    textAlign: "left" as const,
    transition: "all .12s",
  }),
  pfCnt: (on: boolean): React.CSSProperties => ({
    fontFamily: "var(--mono)",
    fontSize: "10px",
    color: on ? "var(--blue)" : "var(--text3)",
    background: "rgba(0,0,0,.2)",
    padding: "1px 6px",
    borderRadius: "10px",
  }),
  /* main */
  sectionHd: {
    fontSize: "11px",
    fontWeight: 700,
    letterSpacing: ".08em",
    textTransform: "uppercase" as const,
    color: "var(--text2)",
    marginBottom: "10px",
    display: "flex" as const,
    alignItems: "center" as const,
    gap: "8px",
  },
  recGrid: {
    display: "grid" as const,
    gridTemplateColumns: "repeat(5, 1fr)",
    gap: "8px",
    marginBottom: "24px",
  },
  recCard: {
    background: "var(--navy2)",
    border: "1px solid var(--border)",
    borderRadius: "var(--radius-md)",
    padding: "10px 12px",
    cursor: "pointer",
    transition: "transform .18s",
  },
  /* toolbar */
  toolbar: {
    display: "flex" as const,
    alignItems: "center" as const,
    gap: "8px",
    marginBottom: "12px",
    flexWrap: "wrap" as const,
  },
  sortBtn: (on: boolean): React.CSSProperties => ({
    padding: "6px 12px",
    borderRadius: "var(--radius-sm)",
    border: `1px solid ${on ? "var(--blue)" : "var(--border)"}`,
    background: on ? "var(--blue-dim)" : "transparent",
    color: on ? "var(--blue)" : "var(--text2)",
    fontSize: "12px",
    fontWeight: on ? 700 : 400,
    cursor: "pointer",
    transition: "all .12s",
  }),
  searchInput: {
    background: "var(--navy2)",
    border: "1px solid var(--border)",
    borderRadius: "var(--radius-sm)",
    padding: "6px 10px",
    color: "var(--text)",
    fontSize: "12px",
    outline: "none",
    width: "180px",
    transition: "border-color .12s",
  } as React.CSSProperties,
  tInfo: {
    marginLeft: "auto",
    fontSize: "12px",
    color: "var(--text2)",
  },
  /* table */
  th: {
    padding: "8px 12px",
    fontSize: "11px",
    fontWeight: 700,
    letterSpacing: ".05em",
    textTransform: "uppercase" as const,
    color: "var(--text3)",
    borderBottom: "1px solid var(--border)",
    background: "var(--navy2)",
    textAlign: "left" as const,
    whiteSpace: "nowrap" as const,
  },
  thR: {
    padding: "8px 12px",
    fontSize: "11px",
    fontWeight: 700,
    letterSpacing: ".05em",
    textTransform: "uppercase" as const,
    color: "var(--text3)",
    borderBottom: "1px solid var(--border)",
    background: "var(--navy2)",
    textAlign: "right" as const,
    whiteSpace: "nowrap" as const,
  },
  td: {
    padding: "10px 12px",
    fontSize: "13px",
    borderBottom: "1px solid rgba(80,140,220,.08)",
    verticalAlign: "middle" as const,
  },
  tdR: {
    padding: "10px 12px",
    fontSize: "13px",
    borderBottom: "1px solid rgba(80,140,220,.08)",
    verticalAlign: "middle" as const,
    textAlign: "right" as const,
  },
  /* error */
  error: {
    marginBottom: "16px",
    background: "var(--red-dim)",
    border: "1px solid rgba(248,81,73,.3)",
    color: "#ffd4d4",
    padding: "12px 16px",
    borderRadius: "var(--radius-md)",
    fontSize: "13px",
  },
};

/* ─── Sub-components ─────────────────────────────────────── */
function SectionLine() {
  return (
    <span
      style={{
        flex: 1,
        height: "1px",
        background: "var(--border)",
        display: "inline-block",
      }}
    />
  );
}

function ChangeColor(pct: number) {
  if (pct > 0) return "var(--red)";
  if (pct < 0) return "var(--green)";
  return "var(--text2)";
}

function ChangeArrow(pct: number) {
  if (pct > 0) return "▲";
  if (pct < 0) return "▼";
  return "—";
}

function ChangeBadge({ pct, ch }: { pct: number; ch: number }) {
  const color = ChangeColor(pct);
  const bg =
    pct > 0 ? "var(--red-dim)" : pct < 0 ? "var(--green-dim)" : "rgba(255,255,255,.06)";
  return (
    <span
      style={{
        display: "inline-block",
        padding: "2px 7px",
        borderRadius: "3px",
        fontSize: "11px",
        fontWeight: 700,
        color,
        background: bg,
        fontFamily: "var(--mono)",
      }}
    >
      {ChangeArrow(pct)} {fmtSigned(ch)} ({fmtSigned(pct)}%)
    </span>
  );
}

/* ─── Main component ─────────────────────────────────────── */
export default function Home() {
  const [stocks,            setStocks]            = useState<Stock[]>([]);
  const [recommendations,   setRecommendations]   = useState<Stock[]>([]);
  const [backendCategories, setBackendCategories] = useState<BackendCategory[]>([]);
  const [marketStatus,      setMarketStatus]      = useState("-");
  const [dataDate,          setDataDate]          = useState("-");
  const [lastUpdate,        setLastUpdate]        = useState("-");
  const [searchTerm,        setSearchTerm]        = useState("");
  const [selectedCategory,  setSelectedCategory]  = useState<CategoryKey>("all");
  const [rankType,          setRankType]          = useState<RankType>("recommend");
  const [loading,           setLoading]           = useState(false);
  const [error,             setError]             = useState("");
  const [mktFilter,         setMktFilter]         = useState("全部");

  async function fetchStocks() {
    try {
      setLoading(true);
      setError("");
      const res  = await fetch(BACKEND_URL, { cache: "no-store" });
      const data: ApiResponse = await res.json();
      if (!data.success) throw new Error(data.message || "取得資料失敗");

      setStocks((data.stocks || []).map(normalize));
      setRecommendations((data.recommendations || []).map(normalize));
      setBackendCategories(data.categories || []);
      setMarketStatus(data.market_status || "-");
      setDataDate(
        data.data_date ||
        data.source_summary?.twse_data_date ||
        data.source_summary?.tpex_data_date ||
        "-"
      );
      setLastUpdate(data.last_update || new Date().toLocaleString("zh-TW"));
    } catch (err) {
      setError(err instanceof Error ? err.message : "載入失敗");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    fetchStocks();
    const t = setInterval(fetchStocks, 120_000);
    return () => clearInterval(t);
  }, []);

  const counts = useMemo(
    () => buildCounts(stocks, backendCategories),
    [stocks, backendCategories]
  );

  const mktCounts = useMemo(() => {
    const twse = stocks.filter((s) => s.market === "twse").length;
    const tpex = stocks.filter((s) => s.market === "tpex").length;
    const etf  = stocks.filter((s) => s.symbol.startsWith("0")).length;
    return { twse, tpex, etf };
  }, [stocks]);

  const filteredStocks = useMemo(() => {
    let r = [...stocks];
    if (mktFilter === "上市") r = r.filter((s) => s.market === "twse");
    else if (mktFilter === "上櫃") r = r.filter((s) => s.market === "tpex");
    else if (mktFilter === "ETF")  r = r.filter((s) => s.symbol.startsWith("0"));
    if (selectedCategory !== "all")
      r = r.filter((s) => getPriceCategory(s.price) === selectedCategory);
    if (searchTerm.trim()) {
      const kw = searchTerm.trim().toLowerCase();
      r = r.filter(
        (s) =>
          s.symbol.toLowerCase().includes(kw) ||
          s.name.toLowerCase().includes(kw)
      );
    }
    if (rankType === "up")   r.sort((a, b) => b.change_percent - a.change_percent);
    else if (rankType === "down") r.sort((a, b) => a.change_percent - b.change_percent);
    else r.sort((a, b) => (b.recommendation_score || b.score || 0) - (a.recommendation_score || a.score || 0));
    return r;
  }, [stocks, selectedCategory, searchTerm, rankType, mktFilter]);

  const recommended = useMemo(() => {
    if (recommendations.length > 0) return recommendations.slice(0, 10);
    return [...stocks]
      .sort((a, b) => (b.recommendation_score || b.score || 0) - (a.recommendation_score || a.score || 0))
      .slice(0, 10);
  }, [stocks, recommendations]);

  const mktColor = marketColor(marketStatus);

  return (
    <div style={S.page}>
      {/* ── Topbar ── */}
      <header style={S.topbar}>
        <div style={{ display: "flex", alignItems: "center" }}>
          <span style={S.logo}>TWSTOCK</span>
          <span style={S.logoSub}>即時選股系統</span>
        </div>

        <div style={S.metaRow}>
          <div style={S.marketPill(mktColor)}>
            <span style={S.dot(mktColor)} />
            {marketStatus}
          </div>
          <span>資料日期：{fmtDate(dataDate)}</span>
          <span>最後更新：{lastUpdate}</span>
          <button
            onClick={fetchStocks}
            disabled={loading}
            style={S.refreshBtn(loading)}
          >
            {loading ? "更新中…" : "更新"}
          </button>
        </div>
      </header>

      {/* ── Body ── */}
      <div style={S.body}>
        {/* ── Sidebar ── */}
        <aside style={S.sidebar}>
          {/* Stat cards */}
          <span style={S.sLabel}>市場概況</span>
          <div style={S.statGrid}>
            <div style={S.statBox()}>
              <div style={S.statVal()}>{fmtNum(mktCounts.twse) || stocks.length}</div>
              <div style={S.statLabel}>上市</div>
            </div>
            <div style={S.statBox()}>
              <div style={S.statVal()}>{fmtNum(mktCounts.tpex)}</div>
              <div style={S.statLabel}>上櫃</div>
            </div>
            <div style={S.statBox()}>
              <div style={S.statVal()}>{fmtNum(mktCounts.etf)}</div>
              <div style={S.statLabel}>ETF</div>
            </div>
            <div style={S.statBox(true)}>
              <div style={S.statVal(true)}>{fmtNum(stocks.length)}</div>
              <div style={S.statLabel}>總檔數</div>
            </div>
          </div>

          <div style={S.divider} />

          {/* Market tabs */}
          <span style={{ ...S.sLabel, marginTop: 0 }}>市場</span>
          <div style={S.mktabs}>
            {["全部", "上市", "上櫃", "ETF"].map((t) => (
              <div
                key={t}
                style={S.mktab(mktFilter === t)}
                onClick={() => setMktFilter(t)}
              >
                {t}
              </div>
            ))}
          </div>

          <div style={S.divider} />

          {/* Price filter */}
          <span style={{ ...S.sLabel, marginTop: 0 }}>價格區間</span>
          {PRICE_CATEGORIES.map((cat) => {
            const on = selectedCategory === cat.key;
            return (
              <button
                key={cat.key}
                style={S.pfItem(on)}
                onClick={() => setSelectedCategory(cat.key)}
              >
                {cat.label}
                <span style={S.pfCnt(on)}>{counts[cat.key]}</span>
              </button>
            );
          })}
        </aside>

        {/* ── Main ── */}
        <main style={S.main}>
          {error && <div style={S.error}>{error}</div>}

          {/* Recommend */}
          <div style={S.sectionHd}>
            推薦 10 檔 <SectionLine />
          </div>
          <div style={S.recGrid}>
            {recommended.map((s) => {
              const color = ChangeColor(s.change_percent);
              return (
                <div key={s.symbol} style={S.recCard}>
                  <div style={{ fontFamily: "var(--mono)", fontSize: "11px", color: "var(--text3)" }}>
                    {s.symbol}
                  </div>
                  <div
                    style={{
                      fontSize: "12px",
                      fontWeight: 700,
                      color: "var(--text)",
                      margin: "2px 0 8px",
                      whiteSpace: "nowrap",
                      overflow: "hidden",
                      textOverflow: "ellipsis",
                    }}
                  >
                    {s.name}
                  </div>
                  <div
                    style={{
                      fontFamily: "var(--mono)",
                      fontSize: "15px",
                      fontWeight: 700,
                      color,
                      marginBottom: "5px",
                    }}
                  >
                    {fmtPrice(s.price)}
                  </div>
                  <ChangeBadge pct={s.change_percent} ch={s.change} />
                </div>
              );
            })}
          </div>

          {/* Toolbar */}
          <div style={S.toolbar}>
            {(["recommend", "up", "down"] as RankType[]).map((r) => {
              const labels = { recommend: "推薦排序", up: "▲ 漲幅", down: "▼ 跌幅" };
              return (
                <button
                  key={r}
                  style={S.sortBtn(rankType === r)}
                  onClick={() => setRankType(r)}
                >
                  {labels[r]}
                </button>
              );
            })}
            <input
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              placeholder="搜尋代號 / 名稱"
              style={S.searchInput}
            />
            <div style={S.tInfo}>
              分類：{PRICE_CATEGORIES.find((c) => c.key === selectedCategory)?.label} /{" "}
              共{" "}
              <span
                style={{
                  fontFamily: "var(--mono)",
                  color: "var(--blue)",
                  fontWeight: 700,
                }}
              >
                {filteredStocks.length}
              </span>{" "}
              檔
            </div>
          </div>

          {/* Table */}
          <div style={{ overflowX: "auto", borderRadius: "var(--radius-md)", border: "1px solid var(--border)" }}>
            <table style={{ width: "100%", minWidth: "820px" }}>
              <thead>
                <tr>
                  <th style={S.th}>代號</th>
                  <th style={S.th}>名稱</th>
                  <th style={S.thR}>股價</th>
                  <th style={S.thR}>漲跌 / 漲跌%</th>
                  <th style={S.thR}>成交量</th>
                  <th style={S.thR}>分數</th>
                  <th style={S.th}>進出場</th>
                </tr>
              </thead>
              <tbody>
                {filteredStocks.map((s) => {
                  const color = ChangeColor(s.change_percent);
                  return (
                    <tr
                      key={s.symbol}
                      style={{ transition: "background .1s", cursor: "pointer" }}
                      onMouseEnter={(e) =>
                        ((e.currentTarget as HTMLTableRowElement).style.background =
                          "var(--navy2)")
                      }
                      onMouseLeave={(e) =>
                        ((e.currentTarget as HTMLTableRowElement).style.background =
                          "transparent")
                      }
                    >
                      <td style={S.td}>
                        <span
                          style={{
                            fontFamily: "var(--mono)",
                            fontSize: "12px",
                            color: "var(--text2)",
                          }}
                        >
                          {s.symbol}
                        </span>
                      </td>
                      <td style={S.td}>
                        <span style={{ fontWeight: 700 }}>{s.name}</span>
                      </td>
                      <td style={S.tdR}>
                        <span
                          style={{
                            fontFamily: "var(--mono)",
                            fontSize: "14px",
                            fontWeight: 700,
                            color,
                          }}
                        >
                          {fmtPrice(s.price)}
                        </span>
                      </td>
                      <td style={S.tdR}>
                        <ChangeBadge pct={s.change_percent} ch={s.change} />
                      </td>
                      <td style={{ ...S.tdR, fontFamily: "var(--mono)", fontSize: "12px", color: "var(--text2)" }}>
                        {fmtNum(s.volume)}
                      </td>
                      <td style={S.tdR}>
                        <span
                          style={{
                            fontFamily: "var(--mono)",
                            fontSize: "12px",
                            color: "var(--yellow)",
                            fontWeight: 700,
                          }}
                        >
                          {s.score ?? 0}
                        </span>
                      </td>
                      <td style={S.td}>
                        {(s.entry_price || s.target_price || s.stop_loss) ? (
                          <span style={{ fontSize: "11px", color: "var(--text2)" }}>
                            進 {s.entry_price || "-"} ／
                            目 {s.target_price || "-"} ／
                            損 {s.stop_loss || "-"}
                          </span>
                        ) : (
                          <span style={{ fontSize: "11px", color: "var(--text3)" }}>—</span>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </main>
      </div>
    </div>
  );
}
