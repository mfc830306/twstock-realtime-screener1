"use client";

import { useEffect, useMemo, useState } from "react";

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

const BACKEND_URL =
  "https://twstock-realtime-screener1.onrender.com/stocks?limit=5000";

const PRICE_CATEGORIES = [
  { key: "all", label: "全部" },
  { key: "0-50", label: "0-50" },
  { key: "50-100", label: "50-100" },
  { key: "100-200", label: "100-200" },
  { key: "200-500", label: "200-500" },
  { key: "500+", label: "500+" },
] as const;

const MARKET_CATEGORIES = [
  { key: "all", label: "全部" },
  { key: "tse", label: "上市" },
  { key: "otc", label: "上櫃" },
  { key: "etf", label: "ETF" },
] as const;

type CategoryKey = (typeof PRICE_CATEGORIES)[number]["key"];
type MarketKey = (typeof MARKET_CATEGORIES)[number]["key"];
type RankType = "recommend" | "up" | "down";

const ITEMS_PER_PAGE = 20;

function getPriceCategory(price: number): CategoryKey {
  if (price < 50) return "0-50";
  if (price < 100) return "50-100";
  if (price < 200) return "100-200";
  if (price < 500) return "200-500";
  return "500+";
}

function formatNumber(num?: number) {
  if (num === undefined || num === null || Number.isNaN(num)) return "-";
  return num.toLocaleString("zh-TW");
}

function formatPrice(num?: number) {
  if (num === undefined || num === null || Number.isNaN(num)) return "-";
  return num.toLocaleString("zh-TW");
}

function formatSigned(num?: number, digits = 2) {
  if (num === undefined || num === null || Number.isNaN(num)) return "-";
  return `${num > 0 ? "+" : num < 0 ? "" : ""}${num.toFixed(digits)}`;
}

function formatDateString(dateText?: string) {
  if (!dateText || dateText === "-") return "-";
  const clean = String(dateText).replace(/\D/g, "");
  if (clean.length === 8) {
    return `${clean.slice(0, 4)}/${clean.slice(4, 6)}/${clean.slice(6, 8)}`;
  }
  return dateText;
}

function getMarketLightColor(status?: string) {
  if (!status) return "#f59e0b";
  if (status.includes("開盤")) return "#22c55e";
  if (status.includes("收盤")) return "#ef4444";
  return "#f59e0b";
}

function buildCategoryCounts(
  stocks: Stock[],
  backendCategories?: BackendCategory[]
): Record<CategoryKey, number> {
  const emptyCounts: Record<CategoryKey, number> = {
    all: stocks.length,
    "0-50": 0,
    "50-100": 0,
    "100-200": 0,
    "200-500": 0,
    "500+": 0,
  };

  if (!backendCategories || backendCategories.length === 0) {
    for (const stock of stocks) {
      emptyCounts[getPriceCategory(stock.price)] += 1;
    }
    return emptyCounts;
  }

  const backendMap = new Map<string, number>();
  for (const item of backendCategories) {
    backendMap.set(item.key, Number(item.count || 0));
  }

  return {
    all: stocks.length,
    "0-50":
      (backendMap.get("0-10") || 0) +
      (backendMap.get("10-20") || 0) +
      (backendMap.get("20-50") || 0),
    "50-100": backendMap.get("50-100") || 0,
    "100-200": backendMap.get("100-200") || 0,
    "200-500": backendMap.get("200-500") || 0,
    "500+":
      (backendMap.get("500-1000") || 0) +
      (backendMap.get("1000+") || 0),
  };
}

function normalizeStock(s: Stock): Stock {
  return {
    ...s,
    price: Number(s.price ?? 0),
    change: Number(s.change ?? 0),
    change_percent: Number(s.change_percent ?? 0),
    volume: Number(s.volume ?? 0),
    score: Number(s.score ?? 0),
    recommendation_score: Number(s.recommendation_score ?? 0),
  };
}

function getPageNumbers(currentPage: number, totalPages: number): number[] {
  const pages: number[] = [];

  if (totalPages <= 7) {
    for (let i = 1; i <= totalPages; i++) pages.push(i);
    return pages;
  }

  const start = Math.max(1, currentPage - 2);
  const end = Math.min(totalPages, currentPage + 2);

  if (start > 1) pages.push(1);
  if (start > 2) pages.push(-1);

  for (let i = start; i <= end; i++) pages.push(i);

  if (end < totalPages - 1) pages.push(-2);
  if (end < totalPages) pages.push(totalPages);

  return pages;
}

function detectMarket(stock: Stock): "上市" | "上櫃" | "ETF" | "-" {
  const market = String(stock.market || "").trim();
  const symbol = String(stock.symbol || "").trim();
  const name = String(stock.name || "").trim();

  if (market === "ETF") return "ETF";
  if (/^00\d+/.test(symbol)) return "ETF";
  if (
    name.includes("ETF") ||
    name.includes("槓桿") ||
    name.includes("反向") ||
    name.includes("正2") ||
    name.includes("反1")
  ) {
    return "ETF";
  }

  if (market === "上市") return "上市";
  if (market === "上櫃") return "上櫃";

  return "-";
}

function matchMarket(stock: Stock, selectedMarket: MarketKey) {
  const market = detectMarket(stock);

  if (selectedMarket === "all") return true;
  if (selectedMarket === "tse") return market === "上市";
  if (selectedMarket === "otc") return market === "上櫃";
  if (selectedMarket === "etf") return market === "ETF";

  return true;
}

function getSelectedMarketLabel(selectedMarket: MarketKey) {
  if (selectedMarket === "tse") return "（上市）";
  if (selectedMarket === "otc") return "（上櫃）";
  if (selectedMarket === "etf") return "（ETF）";
  return "";
}

export default function Home() {
  const [stocks, setStocks] = useState<Stock[]>([]);
  const [recommendations, setRecommendations] = useState<Stock[]>([]);
  const [backendCategories, setBackendCategories] = useState<BackendCategory[]>(
    []
  );
  const [marketStatus, setMarketStatus] = useState("-");
  const [dataDate, setDataDate] = useState("-");
  const [lastUpdate, setLastUpdate] = useState("-");
  const [searchTerm, setSearchTerm] = useState("");
  const [selectedMarket, setSelectedMarket] = useState<MarketKey>("all");
  const [selectedCategory, setSelectedCategory] =
    useState<CategoryKey>("all");
  const [rankType, setRankType] = useState<RankType>("recommend");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [isMobile, setIsMobile] = useState(false);
  const [currentPage, setCurrentPage] = useState(1);

  async function fetchStocks() {
    try {
      setLoading(true);
      setError("");

      const res = await fetch(BACKEND_URL, { cache: "no-store" });
      const data: ApiResponse = await res.json();

      if (!data.success) {
        throw new Error(data.message || "取得資料失敗");
      }

      const safeStocks = (data.stocks || []).map(normalizeStock);
      const safeRecommendations = (data.recommendations || []).map(normalizeStock);

      setStocks(safeStocks);
      setRecommendations(safeRecommendations);
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
    const timer = setInterval(fetchStocks, 120000);
    return () => clearInterval(timer);
  }, []);

  useEffect(() => {
    const handleResize = () => {
      setIsMobile(window.innerWidth <= 900);
    };

    handleResize();
    window.addEventListener("resize", handleResize);
    return () => window.removeEventListener("resize", handleResize);
  }, []);

  const marketCounts = useMemo(() => {
    const tse = stocks.filter((stock) => detectMarket(stock) === "上市").length;
    const otc = stocks.filter((stock) => detectMarket(stock) === "上櫃").length;
    const etf = stocks.filter((stock) => detectMarket(stock) === "ETF").length;

    return {
      all: stocks.length,
      tse,
      otc,
      etf,
    };
  }, [stocks]);

  const marketFilteredStocks = useMemo(() => {
    return stocks.filter((stock) => matchMarket(stock, selectedMarket));
  }, [stocks, selectedMarket]);

  const categoryCounts = useMemo(() => {
    if (selectedMarket === "all") {
      return buildCategoryCounts(stocks, backendCategories);
    }
    return buildCategoryCounts(marketFilteredStocks, []);
  }, [stocks, backendCategories, selectedMarket, marketFilteredStocks]);

  const filteredStocks = useMemo(() => {
    let result = [...marketFilteredStocks];

    if (selectedCategory !== "all") {
      result = result.filter(
        (stock) => getPriceCategory(stock.price) === selectedCategory
      );
    }

    if (searchTerm.trim()) {
      const keyword = searchTerm.trim().toLowerCase();
      result = result.filter(
        (stock) =>
          stock.symbol.toLowerCase().includes(keyword) ||
          stock.name.toLowerCase().includes(keyword)
      );
    }

    if (rankType === "up") {
      result.sort((a, b) => b.change_percent - a.change_percent);
    } else if (rankType === "down") {
      result.sort((a, b) => a.change_percent - b.change_percent);
    } else {
      result.sort(
        (a, b) =>
          (b.recommendation_score || b.score || 0) -
          (a.recommendation_score || a.score || 0)
      );
    }

    return result;
  }, [marketFilteredStocks, selectedCategory, searchTerm, rankType]);

  useEffect(() => {
    setCurrentPage(1);
  }, [searchTerm, selectedCategory, selectedMarket, rankType]);

  const totalPages = Math.max(1, Math.ceil(filteredStocks.length / ITEMS_PER_PAGE));

  useEffect(() => {
    if (currentPage > totalPages) {
      setCurrentPage(totalPages);
    }
  }, [currentPage, totalPages]);

  const pagedStocks = useMemo(() => {
    const start = (currentPage - 1) * ITEMS_PER_PAGE;
    const end = start + ITEMS_PER_PAGE;
    return filteredStocks.slice(start, end);
  }, [filteredStocks, currentPage]);

  const pageNumbers = useMemo(() => {
    return getPageNumbers(currentPage, totalPages);
  }, [currentPage, totalPages]);

  const recommendedStocks = useMemo(() => {
    const source =
      recommendations.length > 0 ? recommendations : stocks;

    return [...source]
      .filter((stock) => matchMarket(stock, selectedMarket))
      .sort(
        (a, b) =>
          (b.recommendation_score || b.score || 0) -
          (a.recommendation_score || a.score || 0)
      )
      .slice(0, 10);
  }, [stocks, recommendations, selectedMarket]);

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
          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: "14px",
              flexWrap: "wrap",
            }}
          >
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
            <div
              style={{
                fontSize: isMobile ? "20px" : "24px",
                opacity: 0.95,
                fontWeight: 700,
              }}
            >
              - 即時選股系統
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
              <span>上市：{formatNumber(marketCounts.tse)}</span>
              <span>上櫃：{formatNumber(marketCounts.otc)}</span>
              <span>ETF：{formatNumber(marketCounts.etf)}</span>
            </div>

            <button
              onClick={fetchStocks}
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
            gridTemplateColumns: isMobile
              ? "1fr"
              : "minmax(300px, 375px) minmax(0, 1fr)",
            gap: "20px",
            alignItems: "start",
            marginBottom: "22px",
          }}
        >
          <div style={panelStyle}>
            <h2 style={{ fontSize: "24px", fontWeight: 900, marginBottom: "18px" }}>
              價格分類
            </h2>

            <div style={{ marginBottom: "20px" }}>
              <div
                style={{
                  fontSize: "15px",
                  fontWeight: 800,
                  color: "#dbe8ff",
                  marginBottom: "10px",
                }}
              >
                市場分類
              </div>

              <div
                style={{
                  display: "flex",
                  flexWrap: "wrap",
                  gap: "12px",
                  marginBottom: "18px",
                }}
              >
                {MARKET_CATEGORIES.map((item) => {
                  const active = selectedMarket === item.key;
                  const count =
                    item.key === "all"
                      ? marketCounts.all
                      : item.key === "tse"
                      ? marketCounts.tse
                      : item.key === "otc"
                      ? marketCounts.otc
                      : marketCounts.etf;

                  return (
                    <button
                      key={item.key}
                      onClick={() => setSelectedMarket(item.key)}
                      style={{
                        minWidth: isMobile ? "calc(50% - 6px)" : "118px",
                        border: "none",
                        borderRadius: "14px",
                        padding: "14px 14px",
                        fontSize: "15px",
                        fontWeight: 800,
                        cursor: "pointer",
                        color: "#fff",
                        background: active
                          ? "linear-gradient(180deg, #61a8ff 0%, #3e7fe0 100%)"
                          : "linear-gradient(180deg, #2a67b8 0%, #1e4f93 100%)",
                        boxShadow: active
                          ? "0 8px 22px rgba(80, 150, 255, 0.22)"
                          : "none",
                      }}
                    >
                      {item.label} ({count})
                    </button>
                  );
                })}
              </div>
            </div>

            <div
              style={{
                display: "flex",
                flexWrap: "wrap",
                gap: "12px",
                marginBottom: "20px",
              }}
            >
              {PRICE_CATEGORIES.map((item) => {
                const active = selectedCategory === item.key;
                return (
                  <button
                    key={item.key}
                    onClick={() => setSelectedCategory(item.key)}
                    style={{
                      minWidth: isMobile ? "calc(50% - 6px)" : "118px",
                      border: "none",
                      borderRadius: "14px",
                      padding: "14px 14px",
                      fontSize: "15px",
                      fontWeight: 800,
                      cursor: "pointer",
                      color: "#fff",
                      background: active
                        ? "linear-gradient(180deg, #61a8ff 0%, #3e7fe0 100%)"
                        : "linear-gradient(180deg, #2a67b8 0%, #1e4f93 100%)",
                      boxShadow: active
                        ? "0 8px 22px rgba(80, 150, 255, 0.22)"
                        : "none",
                    }}
                  >
                    {item.label} ({categoryCounts[item.key]})
                  </button>
                );
              })}
            </div>

            <input
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
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

            <div style={{ display: "flex", gap: "12px", flexWrap: "wrap" }}>
              <button
                onClick={() => setRankType("recommend")}
                style={rankType === "recommend" ? activeActionBtn : normalActionBtn}
              >
                推薦
              </button>

              <button
                onClick={() => setRankType("up")}
                style={rankType === "up" ? activeActionBtn : normalActionBtn}
              >
                漲幅
              </button>

              <button
                onClick={() => setRankType("down")}
                style={rankType === "down" ? activeActionBtn : normalActionBtn}
              >
                跌幅
              </button>
            </div>
          </div>

          <div style={panelStyle}>
            <h2 style={{ fontSize: "24px", fontWeight: 900, marginBottom: "10px" }}>
              🔥 推薦10檔{getSelectedMarketLabel(selectedMarket)}
            </h2>

            <div
              style={{
                maxHeight: isMobile ? "none" : "470px",
                overflowY: isMobile ? "visible" : "auto",
                paddingRight: isMobile ? "0" : "6px",
              }}
            >
              {recommendedStocks.map((stock) => {
                const isUp = stock.change >= 0;
                const changeColor = isUp ? "#ff4d4f" : "#00c853";
                const marketLabel = detectMarket(stock);

                return (
                  <div
                    key={stock.symbol}
                    style={{
                      background: "rgba(40, 87, 150, 0.45)",
                      border: "1px solid rgba(86, 145, 228, 0.22)",
                      borderRadius: "18px",
                      padding: "16px 18px",
                      marginBottom: "12px",
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
                            marginBottom: "10px",
                            color: "#7fb6ff",
                          }}
                        >
                          {stock.symbol} {stock.name}
                        </div>

                        <div
                          style={{
                            display: "flex",
                            gap: "14px",
                            flexWrap: "wrap",
                            alignItems: "center",
                            marginBottom: "8px",
                          }}
                        >
                          <span
                            style={{
                              background: "rgba(255, 107, 107, 0.12)",
                              border: "1px solid rgba(255, 107, 107, 0.28)",
                              borderRadius: "999px",
                              padding: "5px 10px",
                              fontSize: "14px",
                              fontWeight: 700,
                              color: "#ff9c9c",
                            }}
                          >
                            {stock.signal || "強勢多方"}
                          </span>

                          <span
                            style={{
                              background: "rgba(94, 164, 255, 0.12)",
                              border: "1px solid rgba(94, 164, 255, 0.28)",
                              borderRadius: "999px",
                              padding: "5px 10px",
                              fontSize: "14px",
                              fontWeight: 700,
                              color: "#b9d7ff",
                            }}
                          >
                            {marketLabel}
                          </span>

                          <span style={{ fontWeight: 700, color: "#dce9ff" }}>
                            股價 {formatPrice(stock.price)}
                          </span>

                          <span style={{ fontWeight: 900, color: changeColor }}>
                            漲跌 {formatSigned(stock.change)}
                          </span>

                          <span style={{ fontWeight: 900, color: changeColor }}>
                            漲跌% {formatSigned(stock.change_percent)}%
                          </span>
                        </div>
                      </div>

                      <div
                        style={{
                          color: "#ffd95f",
                          fontSize: "18px",
                          fontWeight: 900,
                          whiteSpace: "nowrap",
                        }}
                      >
                        分數 {stock.score ?? 0}
                      </div>
                    </div>

                    <div
                      style={{
                        color: "#dbe8ff",
                        lineHeight: 1.8,
                        fontSize: "15px",
                        marginBottom: "10px",
                      }}
                    >
                      {stock.reason ||
                        "股價維持開高走高格局，收盤於當日高檔附近，買盤承接力道偏強，漲幅擴大且動能明確，屬盤面強勢表態個股，成交量明顯放大。"}
                    </div>

                    <div
                      style={{
                        display: "flex",
                        gap: "16px",
                        flexWrap: "wrap",
                        alignItems: "center",
                        color: "#9fc3f6",
                        fontWeight: 800,
                        fontSize: "15px",
                      }}
                    >
                      <span>進場：{stock.entry_price || "-"}</span>
                      <span>目標：{stock.target_price || "-"}</span>
                      <span>停損：{stock.stop_loss || "-"}</span>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        </section>

        <section
          style={{
            background: "linear-gradient(180deg, #0d2f63 0%, #0a2a57 100%)",
            border: "1px solid rgba(80, 140, 220, 0.22)",
            borderRadius: "22px",
            padding: isMobile ? "16px" : "20px",
            boxShadow: "0 10px 28px rgba(0,0,0,0.12)",
          }}
        >
          <div
            style={{
              display: "flex",
              justifyContent: "space-between",
              alignItems: isMobile ? "flex-start" : "center",
              gap: "12px",
              marginBottom: "16px",
              flexDirection: isMobile ? "column" : "row",
            }}
          >
            <h2 style={{ fontSize: "22px", fontWeight: 900, margin: 0 }}>
              股票列表{getSelectedMarketLabel(selectedMarket)} ({filteredStocks.length})
            </h2>

            <div
              style={{
                color: "#cfe2ff",
                fontSize: "14px",
                fontWeight: 700,
              }}
            >
              第 {currentPage} / {totalPages} 頁，每頁 {ITEMS_PER_PAGE} 檔
            </div>
          </div>

          <div
            style={{
              overflowX: "auto",
              borderRadius: "18px",
            }}
          >
            <table
              style={{
                width: "100%",
                borderCollapse: "collapse",
                minWidth: "1180px",
              }}
            >
              <thead>
                <tr
                  style={{
                    background: "linear-gradient(180deg, #3570bd 0%, #285d9f 100%)",
                  }}
                >
                  <th style={thStyle}>代號</th>
                  <th style={thStyle}>名稱</th>
                  <th style={thStyle}>市場</th>
                  <th style={thStyle}>股價</th>
                  <th style={thStyle}>漲跌</th>
                  <th style={thStyle}>漲跌%</th>
                  <th style={thStyle}>成交量</th>
                  <th style={thStyle}>分數</th>
                </tr>
              </thead>

              <tbody>
                {pagedStocks.map((stock) => {
                  const isUp = stock.change >= 0;
                  const color = isUp ? "#ff4d4f" : "#00c853";
                  const marketLabel = detectMarket(stock);

                  return (
                    <tr
                      key={`${stock.symbol}-${marketLabel}`}
                      style={{
                        borderBottom: "1px solid rgba(255,255,255,0.08)",
                        background: "rgba(8, 36, 76, 0.55)",
                      }}
                    >
                      <td style={tdStyle}>{stock.symbol}</td>
                      <td style={tdStyle}>{stock.name}</td>
                      <td style={tdStyle}>{marketLabel}</td>
                      <td style={tdStyle}>{formatPrice(stock.price)}</td>

                      <td style={tdStyle}>
                        <div style={{ color, fontWeight: 900, fontSize: "18px" }}>
                          {formatSigned(stock.change)}
                        </div>
                      </td>

                      <td style={tdStyle}>
                        <div style={{ color, fontWeight: 800, fontSize: "15px" }}>
                          {formatSigned(stock.change_percent)}%
                        </div>
                      </td>

                      <td style={tdStyle}>{formatNumber(stock.volume)}</td>
                      <td style={tdStyle}>{stock.score ?? 0}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>

          {totalPages > 1 && (
            <div
              style={{
                marginTop: "18px",
                display: "flex",
                justifyContent: "center",
                alignItems: "center",
                gap: "8px",
                flexWrap: "wrap",
              }}
            >
              <button
                onClick={() => setCurrentPage((p) => Math.max(1, p - 1))}
                disabled={currentPage === 1}
                style={{
                  ...pageBtnStyle,
                  opacity: currentPage === 1 ? 0.45 : 1,
                  cursor: currentPage === 1 ? "not-allowed" : "pointer",
                }}
              >
                上一頁
              </button>

              {pageNumbers.map((page, idx) => {
                if (page < 0) {
                  return (
                    <span
                      key={`ellipsis-${idx}`}
                      style={{
                        color: "#d9e7ff",
                        padding: "0 4px",
                        fontWeight: 800,
                      }}
                    >
                      ...
                    </span>
                  );
                }

                const active = currentPage === page;
                return (
                  <button
                    key={page}
                    onClick={() => setCurrentPage(page)}
                    style={{
                      ...pageBtnStyle,
                      background: active
                        ? "linear-gradient(180deg, #61a8ff 0%, #3e7fe0 100%)"
                        : "#184889",
                      boxShadow: active
                        ? "0 8px 22px rgba(80, 150, 255, 0.22)"
                        : "none",
                    }}
                  >
                    {page}
                  </button>
                );
              })}

              <button
                onClick={() => setCurrentPage((p) => Math.min(totalPages, p + 1))}
                disabled={currentPage === totalPages}
                style={{
                  ...pageBtnStyle,
                  opacity: currentPage === totalPages ? 0.45 : 1,
                  cursor:
                    currentPage === totalPages ? "not-allowed" : "pointer",
                }}
              >
                下一頁
              </button>
            </div>
          )}
        </section>
      </div>
    </main>
  );
}

const activeActionBtn: React.CSSProperties = {
  border: "none",
  borderRadius: "14px",
  padding: "12px 16px",
  fontSize: "15px",
  fontWeight: 800,
  cursor: "pointer",
  color: "#fff",
  background: "linear-gradient(180deg, #61a8ff 0%, #3e7fe0 100%)",
};

const normalActionBtn: React.CSSProperties = {
  border: "none",
  borderRadius: "14px",
  padding: "12px 16px",
  fontSize: "15px",
  fontWeight: 800,
  cursor: "pointer",
  color: "#fff",
  background: "#184889",
};

const pageBtnStyle: React.CSSProperties = {
  border: "none",
  borderRadius: "12px",
  padding: "10px 14px",
  minWidth: "44px",
  fontSize: "14px",
  fontWeight: 800,
  color: "#fff",
  background: "#184889",
};

const thStyle: React.CSSProperties = {
  padding: "16px 14px",
  textAlign: "center",
  color: "#ffffff",
  fontSize: "16px",
  fontWeight: 800,
};

const tdStyle: React.CSSProperties = {
  padding: "18px 14px",
  textAlign: "center",
  color: "#ffffff",
  fontSize: "15px",
  fontWeight: 700,
};
