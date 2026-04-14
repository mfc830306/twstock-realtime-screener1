"use client";

import React, { useEffect, useMemo, useRef, useState } from "react";

const BACKEND_BASE =
  process.env.NEXT_PUBLIC_API_BASE_URL?.replace(/\/$/, "") + "/stocks" ||
  "http://localhost:8000/stocks";

const ITEMS_PER_PAGE = 20;

type RankType = "recommend" | "up" | "down";

type CategoryKey =
  | "all"
  | "0-10"
  | "10-20"
  | "20-50"
  | "50-100"
  | "100-200"
  | "200-500"
  | "500-1000"
  | "1000+";

type BackendCategory = {
  key: string;
  label: string;
  count: number;
};

type Stock = {
  market: string;
  symbol: string;
  name: string;
  price: number;
  change: number;
  change_percent: number;
  volume: number;
  score: number;
  recommendation_score: number;
  prev_close: number;
  open: number;
  high: number;
  low: number;
  update_time: string;
  category: string;
  signal: string;
  trend_type: string;
  reason: string;
  technical_comment: string;
  operation_rating: string;
  operation_bias: string;
  operation_style: string;
  strategy_action: string;
  entry_price: string;
  target_price: string;
  stop_loss: string;
  risk_reward: string;
  risk_note: string;
  analysis_source?: string;
};

type FocusedStock = {
  symbol: string;
  name: string;
  market: string;
  price: number;
  change: number;
  change_percent: number;
  volume: number;
  signal: string;
  trend_type: string;
  operation_rating: string;
  operation_bias: string;
  operation_style: string;
  technical_comment: string;
  analysis: string;
  strategy_action: string;
  entry_price: string;
  target_price: string;
  stop_loss: string;
  risk_reward: string;
  risk_note: string;
  update_time: string;
};

type ApiResponse = {
  success: boolean;
  error?: string;
  message?: string;
  total?: number;
  offset?: number;
  limit?: number;
  twse_total?: number;
  otc_total?: number;
  all_total?: number;
  market_status?: string;
  data_date?: string;
  last_update?: string;
  categories?: BackendCategory[];
  recommendations?: Stock[];
  focused_stock?: FocusedStock | null;
  stocks?: Stock[];
};

function useIsMobile(breakpoint = 900) {
  const [isMobile, setIsMobile] = useState(false);

  useEffect(() => {
    const update = () => setIsMobile(window.innerWidth <= breakpoint);
    update();
    window.addEventListener("resize", update);
    return () => window.removeEventListener("resize", update);
  }, [breakpoint]);

  return isMobile;
}

function normalizeStock(stock: Partial<Stock>): Stock {
  return {
    market: stock.market || "",
    symbol: stock.symbol || "",
    name: stock.name || "",
    price: Number(stock.price || 0),
    change: Number(stock.change || 0),
    change_percent: Number(stock.change_percent || 0),
    volume: Number(stock.volume || 0),
    score: Number(stock.score || 0),
    recommendation_score: Number(stock.recommendation_score || 0),
    prev_close: Number(stock.prev_close || 0),
    open: Number(stock.open || 0),
    high: Number(stock.high || 0),
    low: Number(stock.low || 0),
    update_time: stock.update_time || "",
    category: stock.category || "",
    signal: stock.signal || "",
    trend_type: stock.trend_type || "",
    reason: stock.reason || "",
    technical_comment: stock.technical_comment || "",
    operation_rating: stock.operation_rating || "",
    operation_bias: stock.operation_bias || "",
    operation_style: stock.operation_style || "",
    strategy_action: stock.strategy_action || "",
    entry_price: stock.entry_price || "",
    target_price: stock.target_price || "",
    stop_loss: stock.stop_loss || "",
    risk_reward: stock.risk_reward || "",
    risk_note: stock.risk_note || "",
    analysis_source: stock.analysis_source || "snapshot",
  };
}

function stockToFocused(stock: Stock): FocusedStock {
  return {
    symbol: stock.symbol,
    name: stock.name,
    market: stock.market,
    price: stock.price,
    change: stock.change,
    change_percent: stock.change_percent,
    volume: stock.volume,
    signal: stock.signal,
    trend_type: stock.trend_type,
    operation_rating: stock.operation_rating,
    operation_bias: stock.operation_bias,
    operation_style: stock.operation_style,
    technical_comment: stock.technical_comment,
    analysis: stock.reason,
    strategy_action: stock.strategy_action,
    entry_price: stock.entry_price,
    target_price: stock.target_price,
    stop_loss: stock.stop_loss,
    risk_reward: stock.risk_reward,
    risk_note: stock.risk_note,
    update_time: stock.update_time,
  };
}

function getMarketLightColor(status: string) {
  if (status === "開盤") return "#1de782";
  if (status === "收盤") return "#ffd24a";
  return "#9aa9c5";
}

function formatDateString(v: string) {
  if (!v) return "-";
  if (v.includes("/")) return v;
  if (v.length === 8) {
    return `${v.slice(0, 4)}/${v.slice(4, 6)}/${v.slice(6, 8)}`;
  }
  return v;
}

function formatPrice(v?: number) {
  const n = Number(v || 0);
  if (!Number.isFinite(n)) return "-";
  if (Math.abs(n - Math.round(n)) < 0.001) return String(Math.round(n));
  return n.toFixed(2);
}

function formatPct(v?: number) {
  const n = Number(v || 0);
  const sign = n > 0 ? "+" : "";
  return `${sign}${n.toFixed(2)}%`;
}

function formatSigned(v?: number) {
  const n = Number(v || 0);
  const sign = n > 0 ? "+" : "";
  return `${sign}${formatPrice(n)}`;
}

function formatVolume(v?: number) {
  const n = Number(v || 0);
  if (n >= 1000) return `${(n / 1000).toFixed(n >= 10000 ? 0 : 1)}K`;
  return String(Math.round(n));
}

function getSortQuery(rank: RankType) {
  if (rank === "up") return { sort_by: "change_percent", sort_dir: "desc" as const };
  if (rank === "down") return { sort_by: "change_percent", sort_dir: "asc" as const };
  return { sort_by: "recommendation_score", sort_dir: "desc" as const };
}

function getSignalBadge(signal: string) {
  const strong = ["突破前夕", "量增轉強"];
  const watch = ["整理待發", "溫和轉強"];
  const weak = ["偏弱觀察", "偏弱整理", "短線過熱"];

  if (strong.includes(signal)) {
    return {
      bg: "rgba(27, 194, 108, 0.18)",
      border: "1px solid rgba(72, 223, 140, 0.35)",
      color: "#7ff0b3",
    };
  }
  if (watch.includes(signal)) {
    return {
      bg: "rgba(78, 148, 255, 0.18)",
      border: "1px solid rgba(112, 172, 255, 0.35)",
      color: "#9fd0ff",
    };
  }
  if (weak.includes(signal)) {
    return {
      bg: "rgba(255, 171, 46, 0.16)",
      border: "1px solid rgba(255, 193, 88, 0.35)",
      color: "#ffd480",
    };
  }
  return {
    bg: "rgba(255,255,255,0.08)",
    border: "1px solid rgba(255,255,255,0.12)",
    color: "#d8e6ff",
  };
}

function getRatingStyle(rating: string) {
  if (rating === "A") {
    return { bg: "#24c36b", color: "#fff" };
  }
  if (rating === "B+") {
    return { bg: "#3f8cff", color: "#fff" };
  }
  if (rating === "C") {
    return { bg: "#8c97b5", color: "#fff" };
  }
  return { bg: "#ff8a3d", color: "#fff" };
}

function getPageNumbers(currentPage: number, totalPages: number) {
  const pages: number[] = [];
  const start = Math.max(1, currentPage - 2);
  const end = Math.min(totalPages, currentPage + 2);
  for (let i = start; i <= end; i += 1) pages.push(i);
  return pages;
}

function buildCategoryCountsFromBackend(
  backendCategories: BackendCategory[],
  allTotal: number
): Array<{ key: CategoryKey; label: string; count: number }> {
  const base: Array<{ key: CategoryKey; label: string; count: number }> = [
    { key: "all", label: "全部", count: allTotal || 0 },
    { key: "0-10", label: "0-10", count: 0 },
    { key: "10-20", label: "10-20", count: 0 },
    { key: "20-50", label: "20-50", count: 0 },
    { key: "50-100", label: "50-100", count: 0 },
    { key: "100-200", label: "100-200", count: 0 },
    { key: "200-500", label: "200-500", count: 0 },
    { key: "500-1000", label: "500-1000", count: 0 },
    { key: "1000+", label: "1000+", count: 0 },
  ];

  const map = new Map(backendCategories.map((c) => [c.key, c.count]));
  return base.map((item) => ({
    ...item,
    count: item.key === "all" ? item.count : Number(map.get(item.key) || 0),
  }));
}

function getCategoryQuery(category: CategoryKey) {
  if (category === "all") return {};
  const [minRaw, maxRaw] = category.split("-");
  if (category === "1000+") {
    return { price_min: 1000 };
  }
  return {
    price_min: Number(minRaw),
    price_max: Number(maxRaw),
  };
}

export default function Page() {
  const isMobile = useIsMobile();
  const initialLoadedRef = useRef(false);

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const [stocks, setStocks] = useState<Stock[]>([]);
  const [recommendations, setRecommendations] = useState<Stock[]>([]);
  const [focusedStock, setFocusedStock] = useState<FocusedStock | null>(null);

  const [selectedCategory, setSelectedCategory] = useState<CategoryKey>("all");
  const [rankType, setRankType] = useState<RankType>("recommend");
  const [searchTerm, setSearchTerm] = useState("");
  const [debouncedSearchTerm, setDebouncedSearchTerm] = useState("");
  const [manualSelectedSymbol, setManualSelectedSymbol] = useState("");

  const [total, setTotal] = useState(0);
  const [allTotal, setAllTotal] = useState(0);
  const [currentPage, setCurrentPage] = useState(1);

  const [backendCategories, setBackendCategories] = useState<BackendCategory[]>([]);
  const [marketStatus, setMarketStatus] = useState("-");
  const [dataDate, setDataDate] = useState("-");
  const [lastUpdate, setLastUpdate] = useState("-");

  useEffect(() => {
    const timer = setTimeout(() => {
      setDebouncedSearchTerm(searchTerm.trim());
    }, 350);
    return () => clearTimeout(timer);
  }, [searchTerm]);

  async function fetchRecommendations() {
    const params = new URLSearchParams({
      limit: "120",
      offset: "0",
      sort_by: "recommendation_score",
      sort_dir: "desc",
    });

    const categoryQuery = getCategoryQuery(selectedCategory);
    if ("price_min" in categoryQuery && categoryQuery.price_min !== undefined) {
      params.set("price_min", String(categoryQuery.price_min));
    }
    if ("price_max" in categoryQuery && categoryQuery.price_max !== undefined) {
      params.set("price_max", String(categoryQuery.price_max));
    }

    const res = await fetch(`${BACKEND_BASE}?${params.toString()}`, { cache: "no-store" });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data: ApiResponse = await res.json();
    if (!data.success) throw new Error(data.error || data.message || "取得推薦資料失敗");

    const source = (data.recommendations?.length ? data.recommendations : data.stocks || []).map(normalizeStock);
    const safeRecommendations = source
      .filter((stock) => stock.market === "上市" || stock.market === "上櫃")
      .sort(
        (a, b) =>
          (b.recommendation_score || b.score || 0) - (a.recommendation_score || a.score || 0)
      )
      .slice(0, 10);

    setRecommendations(safeRecommendations);
  }

  async function fetchPagedStocks(
    override?: Partial<{
      category: CategoryKey;
      page: number;
      rank: RankType;
      keyword: string;
    }>
  ) {
    setLoading(true);
    setError("");

    try {
      const category = override?.category ?? selectedCategory;
      const page = override?.page ?? currentPage;
      const rank = override?.rank ?? rankType;
      const keyword = override?.keyword ?? debouncedSearchTerm;

      const categoryQuery = getCategoryQuery(category);
      const sortQuery = getSortQuery(rank);

      const params = new URLSearchParams({
        limit: String(ITEMS_PER_PAGE),
        offset: String((page - 1) * ITEMS_PER_PAGE),
        sort_by: sortQuery.sort_by,
        sort_dir: sortQuery.sort_dir,
      });

      if (keyword) params.set("q", keyword);
      if ("price_min" in categoryQuery && categoryQuery.price_min !== undefined) {
        params.set("price_min", String(categoryQuery.price_min));
      }
      if ("price_max" in categoryQuery && categoryQuery.price_max !== undefined) {
        params.set("price_max", String(categoryQuery.price_max));
      }

      const res = await fetch(`${BACKEND_BASE}?${params.toString()}`, { cache: "no-store" });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);

      const data: ApiResponse = await res.json();
      if (!data.success) throw new Error(data.error || data.message || "取得資料失敗");

      const safeStocks = (data.stocks || []).map(normalizeStock);
      setStocks(safeStocks);
      setTotal(Number(data.total || 0));

      if (data.all_total !== undefined) setAllTotal(Number(data.all_total));
      if (data.categories) setBackendCategories(data.categories);

      setMarketStatus(data.market_status || "-");
      setDataDate(data.data_date || "-");
      setLastUpdate(data.last_update || new Date().toLocaleString("zh-TW"));

      if (data.focused_stock) {
        setFocusedStock(data.focused_stock);
      } else if (!manualSelectedSymbol && !keyword) {
        setFocusedStock(null);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "載入失敗");
    } finally {
      setLoading(false);
    }
  }

  async function fetchAllData() {
    try {
      setLoading(true);
      setError("");
      await Promise.all([
        fetchRecommendations(),
        fetchPagedStocks({
          category: selectedCategory,
          page: currentPage,
          rank: rankType,
          keyword: debouncedSearchTerm,
        }),
      ]);
      initialLoadedRef.current = true;
    } catch (err) {
      setError(err instanceof Error ? err.message : "載入失敗");
      setLoading(false);
    }
  }

  useEffect(() => {
    fetchAllData();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (!initialLoadedRef.current) return;
    fetchPagedStocks({
      category: selectedCategory,
      page: currentPage,
      rank: rankType,
      keyword: debouncedSearchTerm,
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [currentPage, debouncedSearchTerm, rankType]);

  useEffect(() => {
    if (!initialLoadedRef.current) return;
    fetchRecommendations();
    fetchPagedStocks({
      category: selectedCategory,
      page: 1,
      rank: rankType,
      keyword: debouncedSearchTerm,
    });
    setCurrentPage(1);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedCategory]);

  useEffect(() => {
    if (!initialLoadedRef.current) return;
    const timer = setInterval(() => {
      fetchPagedStocks({
        category: selectedCategory,
        page: currentPage,
        rank: rankType,
        keyword: debouncedSearchTerm,
      });
    }, 120000);
    return () => clearInterval(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [currentPage, selectedCategory, rankType, debouncedSearchTerm]);

  const categoryCounts = useMemo(
    () => buildCategoryCountsFromBackend(backendCategories, allTotal),
    [backendCategories, allTotal]
  );

  const totalPages = Math.max(1, Math.ceil(total / ITEMS_PER_PAGE));

  useEffect(() => {
    if (currentPage > totalPages) setCurrentPage(totalPages);
  }, [currentPage, totalPages]);

  const pageNumbers = useMemo(
    () => getPageNumbers(currentPage, totalPages),
    [currentPage, totalPages]
  );

  const activeFocusedStock = useMemo(() => {
    if (manualSelectedSymbol) {
      const manualTarget =
        stocks.find((stock) => stock.symbol === manualSelectedSymbol) ||
        recommendations.find((stock) => stock.symbol === manualSelectedSymbol);
      if (manualTarget) return stockToFocused(manualTarget);
    }
    if (focusedStock) return focusedStock;
    if (debouncedSearchTerm && stocks.length === 1) return stockToFocused(stocks[0]);
    return recommendations[0] ? stockToFocused(recommendations[0]) : null;
  }, [manualSelectedSymbol, stocks, recommendations, focusedStock, debouncedSearchTerm]);

  const panelStyle: React.CSSProperties = {
    background: "linear-gradient(180deg, #0d2f63 0%, #0a2a57 100%)",
    border: "1px solid rgba(80, 140, 220, 0.22)",
    borderRadius: "22px",
    padding: isMobile ? "18px" : "24px",
    minHeight: isMobile ? "auto" : "540px",
    boxShadow: "0 10px 28px rgba(0,0,0,0.12)",
    overflow: "hidden",
  };

  const marketLightColor = getMarketLightColor(marketStatus);

  const normalActionBtn: React.CSSProperties = {
    border: "1px solid rgba(255,255,255,0.12)",
    borderRadius: "12px",
    padding: "10px 14px",
    background: "rgba(255,255,255,0.06)",
    color: "#dbe8ff",
    cursor: "pointer",
    fontWeight: 800,
    minWidth: "84px",
  };

  const activeActionBtn: React.CSSProperties = {
    ...normalActionBtn,
    background: "linear-gradient(180deg, #5aa5ff 0%, #3d81f3 100%)",
    color: "#ffffff",
    border: "1px solid rgba(120,180,255,0.45)",
    boxShadow: "0 6px 16px rgba(54, 119, 255, 0.22)",
  };

  return (
    <main
      style={{
        minHeight: "100vh",
        background: "linear-gradient(180deg, #08264d 0%, #0a2d5e 100%)",
        color: "#ffffff",
      }}
    >
      <div
        style={{
          width: "100%",
          borderBottom: "1px solid rgba(80, 140, 220, 0.15)",
          background: "rgba(7, 33, 70, 0.55)",
          backdropFilter: "blur(6px)",
        }}
      >
        <div
          style={{
            maxWidth: "1400px",
            margin: "0 auto",
            padding: isMobile ? "14px 16px" : "14px 36px",
            display: "flex",
            alignItems: isMobile ? "flex-start" : "center",
            justifyContent: "space-between",
            gap: "16px",
            flexWrap: "wrap",
            flexDirection: isMobile ? "column" : "row",
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: "14px", flexWrap: "wrap" }}>
            <div
              style={{
                fontSize: isMobile ? "28px" : "34px",
                fontWeight: 900,
                lineHeight: 1,
                letterSpacing: "1px",
                color: "#5ea4ff",
              }}
            >
              TWSTOCK
            </div>
            <div style={{ fontSize: isMobile ? "20px" : "24px", opacity: 0.95, fontWeight: 700 }}>
              - 2~4天短線潛力股系統
            </div>
          </div>

          <div
            style={{
              display: "flex",
              alignItems: isMobile ? "stretch" : "center",
              gap: "12px",
              flexWrap: "wrap",
              justifyContent: "flex-end",
              width: isMobile ? "100%" : "auto",
              flexDirection: isMobile ? "column" : "row",
            }}
          >
            <div
              style={{
                display: "flex",
                alignItems: "center",
                gap: "12px 18px",
                padding: "10px 16px",
                borderRadius: "14px",
                background: "rgba(255,255,255,0.04)",
                border: "1px solid rgba(255,255,255,0.08)",
                color: "#e8f1ff",
                fontSize: "14px",
                fontWeight: 700,
                flexWrap: "wrap",
                width: isMobile ? "100%" : "auto",
              }}
            >
              <span style={{ display: "flex", alignItems: "center", gap: "6px" }}>
                <span
                  style={{
                    width: "10px",
                    height: "10px",
                    borderRadius: "50%",
                    background: marketLightColor,
                    boxShadow: `0 0 6px ${marketLightColor}`,
                    display: "inline-block",
                  }}
                />
                市場狀態：{marketStatus}
              </span>
              <span>資料日期：{formatDateString(dataDate)}</span>
              <span>最後更新：{lastUpdate}</span>
            </div>

            <button
              type="button"
              onClick={fetchAllData}
              disabled={loading}
              style={{
                border: "none",
                borderRadius: "12px",
                padding: "10px 16px",
                background: "linear-gradient(180deg, #5aa5ff 0%, #3c7ff1 100%)",
                color: "#fff",
                fontWeight: 800,
                cursor: loading ? "not-allowed" : "pointer",
                opacity: loading ? 0.7 : 1,
                minWidth: "78px",
                width: isMobile ? "100%" : "auto",
              }}
            >
              {loading ? "更新中" : "更新"}
            </button>
          </div>
        </div>
      </div>

      <div
        style={{
          maxWidth: "1400px",
          margin: "0 auto",
          padding: isMobile ? "18px 16px 24px" : "26px 36px",
        }}
      >
        {error && (
          <div
            style={{
              marginBottom: "16px",
              background: "rgba(255, 80, 80, 0.15)",
              border: "1px solid rgba(255, 120, 120, 0.35)",
              color: "#ffd4d4",
              padding: "12px 16px",
              borderRadius: "12px",
            }}
          >
            {error}
          </div>
        )}

        <section
          style={{
            display: "grid",
            gridTemplateColumns: isMobile ? "1fr" : "minmax(320px, 390px) minmax(0, 1fr)",
            gap: "20px",
            alignItems: "start",
          }}
        >
          <div style={panelStyle}>
            <h2 style={{ fontSize: "24px", fontWeight: 900, marginBottom: "12px" }}>條件篩選</h2>

            <input
              value={searchTerm}
              onChange={(e) => {
                setSearchTerm(e.target.value);
                setManualSelectedSymbol("");
                setCurrentPage(1);
              }}
              placeholder="搜尋股票代號 / 名稱"
              style={{
                width: "100%",
                height: "46px",
                borderRadius: "14px",
                border: "none",
                outline: "none",
                padding: "0 16px",
                fontSize: "15px",
                marginBottom: "18px",
                background: "#e8edf5",
                color: "#123",
              }}
            />

            <div
              style={{
                display: "grid",
                gridTemplateColumns: isMobile ? "repeat(3, 1fr)" : "repeat(3, minmax(0, 1fr))",
                gap: "10px",
                marginBottom: "18px",
              }}
            >
              {categoryCounts.map((item) => (
                <button
                  key={item.key}
                  type="button"
                  onClick={() => {
                    setSelectedCategory(item.key);
                    setCurrentPage(1);
                  }}
                  style={selectedCategory === item.key ? activeActionBtn : normalActionBtn}
                >
                  <div style={{ fontSize: "13px", fontWeight: 900 }}>{item.label}</div>
                  <div style={{ fontSize: "12px", opacity: 0.9 }}>{item.count}</div>
                </button>
              ))}
            </div>

            <div style={{ display: "flex", gap: "12px", flexWrap: "wrap" }}>
              {(["recommend", "up", "down"] as RankType[]).map((r) => {
                const labels = { recommend: "推薦", up: "漲幅", down: "跌幅" };
                return (
                  <button
                    key={r}
                    type="button"
                    onClick={() => {
                      setRankType(r);
                      setCurrentPage(1);
                      fetchPagedStocks({
                        category: selectedCategory,
                        page: 1,
                        rank: r,
                        keyword: debouncedSearchTerm,
                      });
                    }}
                    style={rankType === r ? activeActionBtn : normalActionBtn}
                  >
                    {labels[r]}
                  </button>
                );
              })}
            </div>

            <div
              style={{
                marginTop: "18px",
                borderTop: "1px solid rgba(255,255,255,0.08)",
                paddingTop: "16px",
                color: "#d9e8ff",
                lineHeight: 1.85,
                fontSize: "14px",
              }}
            >
              <div style={{ fontWeight: 900, color: "#9fc3f6", marginBottom: "6px" }}>
                系統邏輯說明
              </div>
              <div>• 主攻 2～4 天短線潛力股，不追當天過熱股</div>
              <div>• 主要訊號：突破前夕、量增轉強、整理待發、溫和轉強</div>
              <div>• A / B+ 為主攻區，C 觀察，D 先避開</div>
            </div>
          </div>

          <div style={{ display: "grid", gap: "20px" }}>
            <div
              style={{
                display: "grid",
                gridTemplateColumns: isMobile ? "1fr" : "minmax(300px, 380px) minmax(0, 1fr)",
                gap: "20px",
                alignItems: "start",
              }}
            >
              <div style={panelStyle}>
                <h2 style={{ fontSize: "24px", fontWeight: 900, marginBottom: "10px" }}>🔥 推薦10檔</h2>

                <div
                  style={{
                    maxHeight: isMobile ? "none" : "560px",
                    overflowY: isMobile ? "visible" : "auto",
                    paddingRight: isMobile ? "0" : "6px",
                  }}
                >
                  {recommendations.length === 0 ? (
                    <div style={{ color: "#cfe2ff", padding: "16px 4px", fontWeight: 700 }}>
                      目前沒有可顯示的推薦資料
                    </div>
                  ) : (
                    recommendations.map((stock) => {
                      const isUp = stock.change >= 0;
                      const changeColor = isUp ? "#ff6b6b" : "#16d37d";
                      const isSelected = activeFocusedStock?.symbol === stock.symbol;
                      const badge = getSignalBadge(stock.signal);
                      const ratingStyle = getRatingStyle(stock.operation_rating);

                      return (
                        <div
                          key={stock.symbol}
                          onClick={() => {
                            setManualSelectedSymbol(stock.symbol);
                            setSearchTerm(stock.symbol);
                            setFocusedStock(stockToFocused(stock));
                          }}
                          style={{
                            background: isSelected
                              ? "rgba(71, 126, 214, 0.48)"
                              : "rgba(40, 87, 150, 0.45)",
                            border: isSelected
                              ? "1px solid rgba(120, 180, 255, 0.52)"
                              : "1px solid rgba(86, 145, 228, 0.22)",
                            borderRadius: "18px",
                            padding: "16px 18px",
                            marginBottom: "12px",
                            cursor: "pointer",
                            boxShadow: isSelected
                              ? "0 0 0 1px rgba(120,180,255,0.25), 0 12px 24px rgba(0,0,0,0.18)"
                              : "none",
                            transition: "0.2s ease",
                          }}
                        >
                          <div
                            style={{
                              display: "flex",
                              justifyContent: "space-between",
                              alignItems: "flex-start",
                              gap: "12px",
                              marginBottom: "10px",
                              flexDirection: isMobile ? "column" : "row",
                            }}
                          >
                            <div style={{ width: "100%" }}>
                              <div
                                style={{
                                  fontSize: isMobile ? "20px" : "22px",
                                  fontWeight: 900,
                                  marginBottom: "8px",
                                  color: "#7fb6ff",
                                }}
                              >
                                {stock.symbol} {stock.name}
                              </div>

                              <div style={{ display: "flex", gap: "8px", flexWrap: "wrap" }}>
                                <span
                                  style={{
                                    padding: "6px 10px",
                                    borderRadius: "999px",
                                    fontSize: "12px",
                                    fontWeight: 800,
                                    background: badge.bg,
                                    border: badge.border,
                                    color: badge.color,
                                  }}
                                >
                                  {stock.signal}
                                </span>

                                <span
                                  style={{
                                    padding: "6px 10px",
                                    borderRadius: "999px",
                                    fontSize: "12px",
                                    fontWeight: 900,
                                    background: ratingStyle.bg,
                                    color: ratingStyle.color,
                                  }}
                                >
                                  {stock.operation_rating}
                                </span>
                              </div>
                            </div>

                            <div style={{ textAlign: isMobile ? "left" : "right" }}>
                              <div style={{ fontSize: "24px", fontWeight: 900 }}>
                                {formatPrice(stock.price)}
                              </div>
                              <div
                                style={{
                                  fontSize: "16px",
                                  fontWeight: 900,
                                  color: changeColor,
                                }}
                              >
                                {formatSigned(stock.change)} / {formatPct(stock.change_percent)}
                              </div>
                            </div>
                          </div>

                          <div
                            style={{
                              display: "grid",
                              gridTemplateColumns: "repeat(2, minmax(0, 1fr))",
                              gap: "8px 12px",
                              fontSize: "13px",
                              color: "#dceaff",
                              marginBottom: "10px",
                            }}
                          >
                            <div>分數：{stock.recommendation_score}</div>
                            <div>量：{formatVolume(stock.volume)}</div>
                            <div>型態：{stock.trend_type}</div>
                            <div>來源：{stock.analysis_source || "-"}</div>
                          </div>

                          <div
                            style={{
                              color: "#d3e5ff",
                              fontSize: "13px",
                              lineHeight: 1.7,
                              opacity: 0.95,
                            }}
                          >
                            {stock.reason}
                          </div>
                        </div>
                      );
                    })
                  )}
                </div>
              </div>

              <div style={panelStyle}>
                <h2 style={{ fontSize: "24px", fontWeight: 900, marginBottom: "10px" }}>📌 專業分析卡</h2>

                {!activeFocusedStock ? (
                  <div style={{ color: "#cfe2ff", padding: "18px 4px", fontWeight: 700 }}>
                    點擊推薦股或下方股票列表，即可查看完整分析
                  </div>
                ) : (
                  <div>
                    <div
                      style={{
                        display: "flex",
                        justifyContent: "space-between",
                        gap: "16px",
                        flexDirection: isMobile ? "column" : "row",
                        marginBottom: "16px",
                      }}
                    >
                      <div>
                        <div style={{ fontSize: "28px", fontWeight: 900, color: "#8ec0ff" }}>
                          {activeFocusedStock.symbol} {activeFocusedStock.name}
                        </div>
                        <div style={{ marginTop: "8px", color: "#dbe9ff", fontWeight: 700 }}>
                          {activeFocusedStock.market}｜{activeFocusedStock.signal}｜{activeFocusedStock.trend_type}
                        </div>
                      </div>

                      <div style={{ textAlign: isMobile ? "left" : "right" }}>
                        <div style={{ fontSize: "34px", fontWeight: 900 }}>
                          {formatPrice(activeFocusedStock.price)}
                        </div>
                        <div
                          style={{
                            fontSize: "18px",
                            fontWeight: 900,
                            color: activeFocusedStock.change >= 0 ? "#ff6b6b" : "#16d37d",
                          }}
                        >
                          {formatSigned(activeFocusedStock.change)} /{" "}
                          {formatPct(activeFocusedStock.change_percent)}
                        </div>
                      </div>
                    </div>

                    <div
                      style={{
                        display: "grid",
                        gridTemplateColumns: isMobile ? "1fr" : "repeat(4, minmax(0, 1fr))",
                        gap: "12px",
                        marginBottom: "16px",
                      }}
                    >
                      {[
                        { label: "操作評級", value: activeFocusedStock.operation_rating },
                        { label: "操作方向", value: activeFocusedStock.operation_bias },
                        { label: "操作風格", value: activeFocusedStock.operation_style },
                        { label: "成交量", value: formatVolume(activeFocusedStock.volume) },
                      ].map((item) => (
                        <div
                          key={item.label}
                          style={{
                            padding: "14px 14px",
                            borderRadius: "16px",
                            background: "rgba(255,255,255,0.05)",
                            border: "1px solid rgba(255,255,255,0.08)",
                          }}
                        >
                          <div style={{ fontSize: "12px", color: "#a8c4ef", marginBottom: "6px" }}>
                            {item.label}
                          </div>
                          <div style={{ fontSize: "16px", fontWeight: 900 }}>{item.value || "-"}</div>
                        </div>
                      ))}
                    </div>

                    <div
                      style={{
                        marginBottom: "14px",
                        padding: "16px",
                        borderRadius: "18px",
                        background: "rgba(255,255,255,0.05)",
                        border: "1px solid rgba(255,255,255,0.08)",
                        color: "#e7f0ff",
                        lineHeight: 1.85,
                      }}
                    >
                      <div style={{ fontWeight: 900, color: "#9fc3f6", marginBottom: "8px" }}>
                        分析摘要
                      </div>
                      <div>{activeFocusedStock.analysis || "-"}</div>
                    </div>

                    <div
                      style={{
                        marginBottom: "14px",
                        padding: "16px",
                        borderRadius: "18px",
                        background: "rgba(255,255,255,0.05)",
                        border: "1px solid rgba(255,255,255,0.08)",
                        color: "#e7f0ff",
                        lineHeight: 1.8,
                      }}
                    >
                      <div style={{ fontWeight: 900, color: "#9fc3f6", marginBottom: "8px" }}>
                        技術面觀察
                      </div>
                      <div>{activeFocusedStock.technical_comment || "-"}</div>
                    </div>

                    <div
                      style={{
                        display: "grid",
                        gridTemplateColumns: isMobile ? "1fr" : "repeat(4, minmax(0, 1fr))",
                        gap: "12px",
                        marginBottom: "14px",
                      }}
                    >
                      {[
                        { label: "進場區間", value: activeFocusedStock.entry_price },
                        { label: "目標價", value: activeFocusedStock.target_price },
                        { label: "停損價", value: activeFocusedStock.stop_loss },
                        { label: "風報比", value: activeFocusedStock.risk_reward || "-" },
                      ].map((item) => (
                        <div
                          key={item.label}
                          style={{
                            padding: "16px",
                            borderRadius: "18px",
                            background: "rgba(255,255,255,0.05)",
                            border: "1px solid rgba(255,255,255,0.08)",
                          }}
                        >
                          <div style={{ fontSize: "12px", color: "#a8c4ef", marginBottom: "7px" }}>
                            {item.label}
                          </div>
                          <div style={{ fontSize: "16px", fontWeight: 900, color: "#ffffff" }}>
                            {item.value || "-"}
                          </div>
                        </div>
                      ))}
                    </div>

                    <div
                      style={{
                        marginBottom: "14px",
                        padding: "16px",
                        borderRadius: "18px",
                        background: "rgba(255,255,255,0.05)",
                        border: "1px solid rgba(255,255,255,0.08)",
                        color: "#e7f0ff",
                        lineHeight: 1.8,
                      }}
                    >
                      <div style={{ fontWeight: 900, color: "#9fc3f6", marginBottom: "8px" }}>
                        操作策略
                      </div>
                      <div>{activeFocusedStock.strategy_action || "-"}</div>
                    </div>

                    <div
                      style={{
                        padding: "16px",
                        borderRadius: "18px",
                        background: "rgba(255, 184, 77, 0.10)",
                        border: "1px solid rgba(255, 196, 104, 0.22)",
                        color: "#ffe3b0",
                        lineHeight: 1.8,
                      }}
                    >
                      <div style={{ fontWeight: 900, color: "#ffd27f", marginBottom: "8px" }}>
                        風險提醒
                      </div>
                      <div>{activeFocusedStock.risk_note || "-"}</div>
                    </div>

                    <div
                      style={{
                        marginTop: "12px",
                        color: "#a9c2e8",
                        fontSize: "13px",
                        textAlign: "right",
                      }}
                    >
                      更新時間：{activeFocusedStock.update_time || "-"}
                    </div>
                  </div>
                )}
              </div>
            </div>

            <div style={panelStyle}>
              <div
                style={{
                  display: "flex",
                  justifyContent: "space-between",
                  gap: "12px",
                  flexDirection: isMobile ? "column" : "row",
                  alignItems: isMobile ? "stretch" : "center",
                  marginBottom: "14px",
                }}
              >
                <h2 style={{ fontSize: "24px", fontWeight: 900, margin: 0 }}>📊 股票列表</h2>
                <div style={{ color: "#cfe2ff", fontWeight: 700 }}>
                  共 {total} 檔｜每頁 {ITEMS_PER_PAGE} 檔
                </div>
              </div>

              <div
                style={{
                  overflowX: "auto",
                  borderRadius: "16px",
                  border: "1px solid rgba(255,255,255,0.08)",
                }}
              >
                <table
                  style={{
                    width: "100%",
                    borderCollapse: "collapse",
                    minWidth: "980px",
                    background: "rgba(255,255,255,0.03)",
                  }}
                >
                  <thead>
                    <tr style={{ background: "rgba(255,255,255,0.06)" }}>
                      {[
                        "代號",
                        "名稱",
                        "現價",
                        "漲跌%",
                        "成交量",
                        "訊號",
                        "評級",
                        "推薦分數",
                        "操作",
                      ].map((text) => (
                        <th
                          key={text}
                          style={{
                            padding: "14px 12px",
                            textAlign: "left",
                            fontSize: "13px",
                            color: "#9fc3f6",
                            fontWeight: 900,
                            borderBottom: "1px solid rgba(255,255,255,0.08)",
                            whiteSpace: "nowrap",
                          }}
                        >
                          {text}
                        </th>
                      ))}
                    </tr>
                  </thead>

                  <tbody>
                    {stocks.length === 0 ? (
                      <tr>
                        <td
                          colSpan={9}
                          style={{
                            padding: "22px 16px",
                            textAlign: "center",
                            color: "#dce8ff",
                            fontWeight: 700,
                          }}
                        >
                          目前沒有符合條件的資料
                        </td>
                      </tr>
                    ) : (
                      stocks.map((stock) => {
                        const badge = getSignalBadge(stock.signal);
                        const ratingStyle = getRatingStyle(stock.operation_rating);
                        const isSelected = activeFocusedStock?.symbol === stock.symbol;

                        return (
                          <tr
                            key={stock.symbol}
                            onClick={() => {
                              setManualSelectedSymbol(stock.symbol);
                              setSearchTerm(stock.symbol);
                              setFocusedStock(stockToFocused(stock));
                            }}
                            style={{
                              cursor: "pointer",
                              background: isSelected ? "rgba(83, 143, 255, 0.12)" : "transparent",
                              borderBottom: "1px solid rgba(255,255,255,0.06)",
                            }}
                          >
                            <td style={{ padding: "14px 12px", fontWeight: 900, color: "#7fb6ff" }}>
                              {stock.symbol}
                            </td>
                            <td style={{ padding: "14px 12px", fontWeight: 700 }}>{stock.name}</td>
                            <td style={{ padding: "14px 12px", fontWeight: 900 }}>{formatPrice(stock.price)}</td>
                            <td
                              style={{
                                padding: "14px 12px",
                                fontWeight: 900,
                                color: stock.change_percent >= 0 ? "#ff6b6b" : "#16d37d",
                              }}
                            >
                              {formatPct(stock.change_percent)}
                            </td>
                            <td style={{ padding: "14px 12px" }}>{formatVolume(stock.volume)}</td>
                            <td style={{ padding: "14px 12px" }}>
                              <span
                                style={{
                                  padding: "6px 10px",
                                  borderRadius: "999px",
                                  fontSize: "12px",
                                  fontWeight: 800,
                                  background: badge.bg,
                                  border: badge.border,
                                  color: badge.color,
                                }}
                              >
                                {stock.signal}
                              </span>
                            </td>
                            <td style={{ padding: "14px 12px" }}>
                              <span
                                style={{
                                  padding: "6px 10px",
                                  borderRadius: "999px",
                                  fontSize: "12px",
                                  fontWeight: 900,
                                  background: ratingStyle.bg,
                                  color: ratingStyle.color,
                                }}
                              >
                                {stock.operation_rating}
                              </span>
                            </td>
                            <td style={{ padding: "14px 12px", fontWeight: 800 }}>
                              {stock.recommendation_score}
                            </td>
                            <td style={{ padding: "14px 12px", color: "#9fc3f6", fontWeight: 800 }}>
                              查看分析
                            </td>
                          </tr>
                        );
                      })
                    )}
                  </tbody>
                </table>
              </div>

              <div
                style={{
                  marginTop: "16px",
                  display: "flex",
                  justifyContent: "center",
                  gap: "8px",
                  flexWrap: "wrap",
                }}
              >
                <button
                  type="button"
                  onClick={() => setCurrentPage((p) => Math.max(1, p - 1))}
                  disabled={currentPage <= 1}
                  style={{
                    ...normalActionBtn,
                    opacity: currentPage <= 1 ? 0.5 : 1,
                    cursor: currentPage <= 1 ? "not-allowed" : "pointer",
                  }}
                >
                  上一頁
                </button>

                {pageNumbers.map((page) => (
                  <button
                    key={page}
                    type="button"
                    onClick={() => setCurrentPage(page)}
                    style={currentPage === page ? activeActionBtn : normalActionBtn}
                  >
                    {page}
                  </button>
                ))}

                <button
                  type="button"
                  onClick={() => setCurrentPage((p) => Math.min(totalPages, p + 1))}
                  disabled={currentPage >= totalPages}
                  style={{
                    ...normalActionBtn,
                    opacity: currentPage >= totalPages ? 0.5 : 1,
                    cursor: currentPage >= totalPages ? "not-allowed" : "pointer",
                  }}
                >
                  下一頁
                </button>
              </div>
            </div>
          </div>
        </section>
      </div>
    </main>
  );
}