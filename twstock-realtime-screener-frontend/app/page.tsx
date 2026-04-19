"use client";

import { useEffect, useMemo, useRef, useState } from "react";

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
  trend_type?: string;
  reason?: string;
  technical_comment?: string;
  operation_rating?: string;
  operation_bias?: string;
  operation_style?: string;
  strategy_action?: string;
  entry_price?: string;
  target_price?: string;
  stop_loss?: string;
  risk_reward?: string;
  risk_note?: string;
  update_time?: string;
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
  all_total?: number;
  twse_total?: number;
  otc_total?: number;
  stocks: Stock[];
  recommendations?: Stock[];
  categories?: BackendCategory[];
  focused_stock?: FocusedStock | null;
  message?: string;
  error?: string;
  source_summary?: {
    twse_data_date?: string;
    tpex_data_date?: string;
  };
};

type ValidationRecord = {
  dataDate: string;
  lastUpdate: string;
  symbols: string[];
  recommendationCount: number;
  historicalKCount: number;
  strongRatingCount: number;
  validSignalCount: number;
  excludedSignalCount: number;
  averageScore: number;
  averageRiskReward: number;
  signalSummary: string[];
};

const BACKEND_BASE = "https://twstock-realtime-screener1.onrender.com/stocks";
const VALIDATION_STORAGE_KEY = "twstock-validation-history-v1";
const VALIDATION_SIGNALS = ["突破前夕", "量增轉強", "整理待發", "溫和轉強"];
const EXCLUDED_VALIDATION_SIGNALS = ["短線過熱", "偏弱觀察", "偏弱整理"];

const PRICE_CATEGORIES = [
  { key: "all", label: "全部" },
  { key: "0-50", label: "0-50" },
  { key: "50-100", label: "50-100" },
  { key: "100-200", label: "100-200" },
  { key: "200-500", label: "200-500" },
  { key: "500+", label: "500+" },
] as const;

type CategoryKey = (typeof PRICE_CATEGORIES)[number]["key"];
type RankType = "recommend" | "up" | "down";

const ITEMS_PER_PAGE = 20;

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

function stockToFocused(stock: Stock): FocusedStock {
  return {
    symbol: stock.symbol,
    name: stock.name,
    market: stock.market || "-",
    price: Number(stock.price || 0),
    change: Number(stock.change || 0),
    change_percent: Number(stock.change_percent || 0),
    volume: Number(stock.volume || 0),
    signal: stock.signal || "-",
    trend_type: stock.trend_type || "-",
    operation_rating: stock.operation_rating || "-",
    operation_bias: stock.operation_bias || "-",
    operation_style: stock.operation_style || "-",
    technical_comment: stock.technical_comment || stock.reason || "-",
    analysis: stock.reason || "-",
    strategy_action: stock.strategy_action || "-",
    entry_price: stock.entry_price || "-",
    target_price: stock.target_price || "-",
    stop_loss: stock.stop_loss || "-",
    risk_reward: stock.risk_reward || "-",
    risk_note: stock.risk_note || "-",
    update_time: stock.update_time || "-",
  };
}

function getRatingColor(rating?: string) {
  if (rating === "A") return "#ffd95f";
  if (rating === "B+") return "#7ee787";
  if (rating === "C") return "#7fb6ff";
  if (rating === "D") return "#ff9c9c";
  return "#dbe8ff";
}

function getCategoryQuery(category: CategoryKey): {
  market?: string;
  price_min?: number;
  price_max?: number;
} {
  switch (category) {
    case "0-50":
      return { price_max: 50 };
    case "50-100":
      return { price_min: 50, price_max: 100 };
    case "100-200":
      return { price_min: 100, price_max: 200 };
    case "200-500":
      return { price_min: 200, price_max: 500 };
    case "500+":
      return { price_min: 500 };
    default:
      return {};
  }
}

function getSortQuery(rankType: RankType): {
  sort_by: string;
  sort_dir: "asc" | "desc";
} {
  if (rankType === "up") return { sort_by: "change_percent", sort_dir: "desc" };
  if (rankType === "down") return { sort_by: "change_percent", sort_dir: "asc" };
  return { sort_by: "recommendation_score", sort_dir: "desc" };
}

function buildCategoryCountsFromBackend(
  backendCategories: BackendCategory[],
  allTotal: number
): Record<CategoryKey, number> {
  const backendMap = new Map<string, number>();
  for (const item of backendCategories || []) {
    backendMap.set(item.key, Number(item.count || 0));
  }
  return {
    all: allTotal,
    "0-50":
      (backendMap.get("0-10") || 0) +
      (backendMap.get("10-20") || 0) +
      (backendMap.get("20-50") || 0),
    "50-100": backendMap.get("50-100") || 0,
    "100-200": backendMap.get("100-200") || 0,
    "200-500": backendMap.get("200-500") || 0,
    "500+": (backendMap.get("500-1000") || 0) + (backendMap.get("1000+") || 0),
  };
}

function roundTo(num: number, digits = 2) {
  const factor = 10 ** digits;
  return Math.round(num * factor) / factor;
}

function parseRiskRewardValue(text?: string) {
  const match = String(text || "").match(/1\s*:\s*([0-9.]+)/);
  return match ? Number(match[1]) : 0;
}

function buildValidationRecord(
  source: Stock[],
  dataDate?: string,
  lastUpdate?: string
): ValidationRecord | null {
  if (!source.length) return null;

  const safeSource = source.map(normalizeStock);
  const signalCount = new Map<string, number>();
  for (const stock of safeSource) {
    const signal = stock.signal || "未分類";
    signalCount.set(signal, (signalCount.get(signal) || 0) + 1);
  }

  const scoreValues = safeSource.map((stock) => Number(stock.recommendation_score || stock.score || 0));
  const riskRewardValues = safeSource
    .map((stock) => parseRiskRewardValue(stock.risk_reward))
    .filter((value) => value > 0);

  return {
    dataDate: dataDate || "",
    lastUpdate: lastUpdate || "",
    symbols: safeSource.map((stock) => stock.symbol),
    recommendationCount: safeSource.length,
    historicalKCount: safeSource.filter((stock) => stock.analysis_source === "historical_k").length,
    strongRatingCount: safeSource.filter(
      (stock) => stock.operation_rating === "A" || stock.operation_rating === "B+"
    ).length,
    validSignalCount: safeSource.filter((stock) =>
      VALIDATION_SIGNALS.includes(stock.signal || "")
    ).length,
    excludedSignalCount: safeSource.filter((stock) =>
      EXCLUDED_VALIDATION_SIGNALS.includes(stock.signal || "")
    ).length,
    averageScore: roundTo(
      scoreValues.reduce((sum, value) => sum + value, 0) / Math.max(scoreValues.length, 1)
    ),
    averageRiskReward: roundTo(
      riskRewardValues.reduce((sum, value) => sum + value, 0) / Math.max(riskRewardValues.length, 1)
    ),
    signalSummary: Array.from(signalCount.entries())
      .sort((a, b) => b[1] - a[1])
      .slice(0, 3)
      .map(([signal, count]) => `${signal} ${count}檔`),
  };
}

export default function Home() {
  const [stocks, setStocks] = useState<Stock[]>([]);
  const [recommendations, setRecommendations] = useState<Stock[]>([]);
  const [backendCategories, setBackendCategories] = useState<BackendCategory[]>([]);
  const [marketStatus, setMarketStatus] = useState("-");
  const [dataDate, setDataDate] = useState("-");
  const [lastUpdate, setLastUpdate] = useState("-");
  const [searchTerm, setSearchTerm] = useState("");
  const [debouncedSearchTerm, setDebouncedSearchTerm] = useState("");
  const [selectedCategory, setSelectedCategory] = useState<CategoryKey>("all");
  const [rankType, setRankType] = useState<RankType>("recommend");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [isMobile, setIsMobile] = useState(false);
  const [currentPage, setCurrentPage] = useState(1);
  const [focusedStock, setFocusedStock] = useState<FocusedStock | null>(null);
  const [manualSelectedSymbol, setManualSelectedSymbol] = useState("");
  const [total, setTotal] = useState(0);
  const [allTotal, setAllTotal] = useState(0);
  const [showValidationPanel, setShowValidationPanel] = useState(false);
  const [validationHistory, setValidationHistory] = useState<ValidationRecord[]>([]);

  const initialLoadedRef = useRef(false);
  const pagedRequestIdRef = useRef(0);
  const recommendationsRequestIdRef = useRef(0);

  useEffect(() => {
    const timer = setTimeout(() => {
      setDebouncedSearchTerm(searchTerm.trim());
      setCurrentPage(1);
    }, 350);
    return () => clearTimeout(timer);
  }, [searchTerm]);

  useEffect(() => {
    const handleResize = () => setIsMobile(window.innerWidth <= 900);
    handleResize();
    window.addEventListener("resize", handleResize);
    return () => window.removeEventListener("resize", handleResize);
  }, []);

  async function fetchRecommendations() {
    const requestId = ++recommendationsRequestIdRef.current;
    const params = new URLSearchParams({
      limit: "30",
      offset: "0",
      sort_by: "recommendation_score",
      sort_dir: "desc",
    });
    const res = await fetch(`${BACKEND_BASE}?${params.toString()}`, { cache: "no-store" });
    const data: ApiResponse = await res.json();
    if (!data.success) throw new Error(data.error || data.message || "取得推薦資料失敗");

    const source = (data.recommendations?.length ? data.recommendations : data.stocks || []).map(
      normalizeStock
    );
    const safeRecommendations = source
      .filter((stock) => stock.market === "上市" || stock.market === "上櫃")
      .sort(
        (a, b) =>
          (b.recommendation_score || b.score || 0) - (a.recommendation_score || a.score || 0)
      )
      .slice(0, 10);
    if (requestId !== recommendationsRequestIdRef.current) return;
    setRecommendations(safeRecommendations);
  }

  async function fetchPagedStocks(
    override?: Partial<{
      category: CategoryKey;
      page: number;
      rank: RankType;
      keyword: string;
    }>,
    options?: {
      forceRefresh?: boolean;
      manageLoading?: boolean;
    }
  ) {
    const requestId = ++pagedRequestIdRef.current;
    const manageLoading = options?.manageLoading ?? true;

    if (manageLoading) setLoading(true);
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
      if (options?.forceRefresh) params.set("force_refresh", "true");
      if (categoryQuery.market) params.set("market", categoryQuery.market);
      if (categoryQuery.price_min !== undefined) {
        params.set("price_min", String(categoryQuery.price_min));
      }
      if (categoryQuery.price_max !== undefined) {
        params.set("price_max", String(categoryQuery.price_max));
      }

      const res = await fetch(`${BACKEND_BASE}?${params.toString()}`, { cache: "no-store" });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);

      const data: ApiResponse = await res.json();
      if (requestId !== pagedRequestIdRef.current) return;
      if (!data.success) throw new Error(data.error || data.message || "取得資料失敗");

      const safeStocks = (data.stocks || []).map(normalizeStock);
      setStocks(safeStocks);
      setTotal(Number(data.total || 0));

      if (data.all_total !== undefined) setAllTotal(Number(data.all_total));
      if (data.categories) setBackendCategories(data.categories);

      setMarketStatus(data.market_status || "-");
      setDataDate(
        data.data_date ||
          data.source_summary?.twse_data_date ||
          data.source_summary?.tpex_data_date ||
          "-"
      );
      setLastUpdate(data.last_update || new Date().toLocaleString("zh-TW"));

      if (data.focused_stock) {
        setFocusedStock(data.focused_stock);
      } else if (!manualSelectedSymbol && !keyword) {
        setFocusedStock(null);
      }
    } catch (err) {
      if (requestId !== pagedRequestIdRef.current) return;
      setError(err instanceof Error ? err.message : "載入失敗");
    } finally {
      if (manageLoading && requestId === pagedRequestIdRef.current) {
        setLoading(false);
      }
    }
  }

  async function fetchAllData(options?: { forceRefresh?: boolean }) {
    try {
      setLoading(true);
      setError("");
      await fetchPagedStocks(
        {
          category: selectedCategory,
          page: currentPage,
          rank: rankType,
          keyword: debouncedSearchTerm,
        },
        {
          forceRefresh: options?.forceRefresh,
          manageLoading: false,
        }
      );
      await fetchRecommendations();
      initialLoadedRef.current = true;
    } catch (err) {
      setError(err instanceof Error ? err.message : "載入失敗");
    } finally {
      setLoading(false);
    }
  }

  async function fetchRecommendationsSafe(options?: { forceRefresh?: boolean }) {
    const requestId = ++recommendationsRequestIdRef.current;

    try {
      const params = new URLSearchParams({
        limit: "30",
        offset: "0",
        sort_by: "recommendation_score",
        sort_dir: "desc",
      });
      if (options?.forceRefresh) params.set("force_refresh", "true");

      const res = await fetch(`${BACKEND_BASE}?${params.toString()}`, { cache: "no-store" });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);

      const data: ApiResponse = await res.json();
      if (!data.success) throw new Error(data.error || data.message || "載入失敗");

      const source = (data.recommendations?.length ? data.recommendations : data.stocks || []).map(
        normalizeStock
      );
      const safeRecommendations = source
        .filter((stock) => stock.market === "上市" || stock.market === "上櫃")
        .sort(
          (a, b) =>
            (b.recommendation_score || b.score || 0) - (a.recommendation_score || a.score || 0)
        )
        .slice(0, 10);

      if (requestId !== recommendationsRequestIdRef.current) return null;
      setRecommendations(safeRecommendations);
      return data;
    } catch (err) {
      if (requestId !== recommendationsRequestIdRef.current) return null;
      setError(err instanceof Error ? err.message : "載入失敗");
      return null;
    }
  }

  async function fetchPagedStocksSafe(
    override?: Partial<{
      category: CategoryKey;
      page: number;
      rank: RankType;
      keyword: string;
    }>,
    options?: {
      forceRefresh?: boolean;
      manageLoading?: boolean;
    }
  ) {
    const requestId = ++pagedRequestIdRef.current;
    const manageLoading = options?.manageLoading ?? true;

    if (manageLoading) setLoading(true);
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
      if (options?.forceRefresh) params.set("force_refresh", "true");
      if (categoryQuery.market) params.set("market", categoryQuery.market);
      if (categoryQuery.price_min !== undefined) {
        params.set("price_min", String(categoryQuery.price_min));
      }
      if (categoryQuery.price_max !== undefined) {
        params.set("price_max", String(categoryQuery.price_max));
      }

      const res = await fetch(`${BACKEND_BASE}?${params.toString()}`, { cache: "no-store" });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);

      const data: ApiResponse = await res.json();
      if (requestId !== pagedRequestIdRef.current) return null;
      if (!data.success) throw new Error(data.error || data.message || "載入失敗");

      const safeStocks = (data.stocks || []).map(normalizeStock);
      setStocks(safeStocks);
      setTotal(Number(data.total || 0));

      if (data.all_total !== undefined) setAllTotal(Number(data.all_total));
      if (data.categories) setBackendCategories(data.categories);
      if (data.recommendations?.length) {
        recommendationsRequestIdRef.current += 1;
        setRecommendations((data.recommendations || []).map(normalizeStock).slice(0, 10));
      }

      setMarketStatus(data.market_status || "-");
      setDataDate(
        data.data_date ||
          data.source_summary?.twse_data_date ||
          data.source_summary?.tpex_data_date ||
          "-"
      );
      setLastUpdate(data.last_update || new Date().toLocaleString("zh-TW"));

      if (data.focused_stock) {
        setFocusedStock(data.focused_stock);
      } else if (!manualSelectedSymbol && !keyword) {
        setFocusedStock(null);
      }

      return data;
    } catch (err) {
      if (requestId !== pagedRequestIdRef.current) return null;
      setError(err instanceof Error ? err.message : "載入失敗");
      return null;
    } finally {
      if (manageLoading && requestId === pagedRequestIdRef.current) {
        setLoading(false);
      }
    }
  }

  async function fetchAllDataSafe(options?: { forceRefresh?: boolean }) {
    setLoading(true);
    setError("");

    const data = await fetchPagedStocksSafe(
      {
        category: selectedCategory,
        page: currentPage,
        rank: rankType,
        keyword: debouncedSearchTerm,
      },
      {
        forceRefresh: options?.forceRefresh,
        manageLoading: false,
      }
    );

    if (!data?.recommendations?.length) {
      await fetchRecommendationsSafe({ forceRefresh: options?.forceRefresh });
    }

    initialLoadedRef.current = true;
    setLoading(false);
  }

  useEffect(() => {
    fetchAllDataSafe();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (!initialLoadedRef.current) return;
    fetchPagedStocksSafe({
      category: selectedCategory,
      page: currentPage,
      rank: rankType,
      keyword: debouncedSearchTerm,
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [currentPage, debouncedSearchTerm]);

  useEffect(() => {
    if (!initialLoadedRef.current) return;
    fetchRecommendationsSafe();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedCategory]);

  useEffect(() => {
    if (!initialLoadedRef.current) return;
    const timer = setInterval(() => {
      fetchPagedStocksSafe({
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
    return null;
  }, [manualSelectedSymbol, stocks, recommendations, focusedStock, debouncedSearchTerm]);

  const validationRecord = useMemo(
    () => buildValidationRecord(recommendations, dataDate, lastUpdate),
    [recommendations, dataDate, lastUpdate]
  );

  useEffect(() => {
    try {
      const raw = window.localStorage.getItem(VALIDATION_STORAGE_KEY);
      if (!raw) return;
      const parsed = JSON.parse(raw);
      if (Array.isArray(parsed)) {
        setValidationHistory(parsed);
      }
    } catch {
      setValidationHistory([]);
    }
  }, []);

  useEffect(() => {
    if (!validationRecord) return;

    setValidationHistory((prev) => {
      const next = [
        validationRecord,
        ...prev.filter((item) => item.dataDate !== validationRecord.dataDate),
      ].slice(0, 12);

      try {
        window.localStorage.setItem(VALIDATION_STORAGE_KEY, JSON.stringify(next));
      } catch {}

      return next;
    });
  }, [validationRecord]);

  const previousValidationRecord = useMemo(() => {
    if (!validationRecord) return null;
    return validationHistory.find((item) => item.dataDate !== validationRecord.dataDate) || null;
  }, [validationHistory, validationRecord]);

  const repeatedPickCount = useMemo(() => {
    if (!validationRecord || !previousValidationRecord) return 0;
    const previousSymbols = new Set(previousValidationRecord.symbols);
    return validationRecord.symbols.filter((symbol) => previousSymbols.has(symbol)).length;
  }, [previousValidationRecord, validationRecord]);

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
            </div>

            <button
              type="button"
              onClick={() => fetchAllDataSafe({ forceRefresh: true })}
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
            marginBottom: "22px",
          }}
        >
          <div style={panelStyle}>
            <div
              style={{
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
                gap: "12px",
                marginBottom: "18px",
              }}
            >
              <h2 style={{ fontSize: "24px", fontWeight: 900, margin: 0 }}>價格分類</h2>
              <button
                type="button"
                onClick={() => setShowValidationPanel((prev) => !prev)}
                style={{
                  border: "1px solid rgba(120, 205, 255, 0.28)",
                  borderRadius: "12px",
                  padding: "8px 12px",
                  background: showValidationPanel
                    ? "linear-gradient(180deg, rgba(106, 187, 255, 0.28) 0%, rgba(56, 116, 214, 0.38) 100%)"
                    : "rgba(255,255,255,0.05)",
                  color: "#e8f4ff",
                  fontWeight: 800,
                  fontSize: "13px",
                  cursor: "pointer",
                  whiteSpace: "nowrap",
                }}
              >
                {showValidationPanel ? "收起驗證" : "驗證紀錄"}
              </button>
            </div>

            {showValidationPanel && validationRecord && (
              <div
                style={{
                  marginBottom: "18px",
                  padding: "14px 14px 12px",
                  borderRadius: "16px",
                  background: "rgba(255,255,255,0.05)",
                  border: "1px solid rgba(130, 185, 255, 0.16)",
                }}
              >
                <div
                  style={{
                    display: "grid",
                    gridTemplateColumns: isMobile ? "1fr" : "1fr 1fr",
                    gap: "12px",
                    marginBottom: "12px",
                  }}
                >
                  <div
                    style={{
                      borderRadius: "14px",
                      padding: "12px",
                      background: "rgba(20, 58, 112, 0.58)",
                    }}
                  >
                    <div style={{ color: "#8fc3ff", fontSize: "13px", fontWeight: 900, marginBottom: "8px" }}>
                      紀錄摘要
                    </div>
                    <div style={{ color: "#dce9ff", lineHeight: 1.8, fontSize: "13px", fontWeight: 700 }}>
                      <div>資料日期：{formatDateString(validationRecord.dataDate)}</div>
                      <div>最後更新：{validationRecord.lastUpdate || "-"}</div>
                      <div>本次推薦：{validationRecord.recommendationCount} 檔</div>
                      <div>累積紀錄：{validationHistory.length} 次</div>
                    </div>
                  </div>

                  <div
                    style={{
                      borderRadius: "14px",
                      padding: "12px",
                      background: "rgba(20, 58, 112, 0.58)",
                    }}
                  >
                    <div style={{ color: "#8fc3ff", fontSize: "13px", fontWeight: 900, marginBottom: "8px" }}>
                      規則驗證
                    </div>
                    <div style={{ color: "#dce9ff", lineHeight: 1.8, fontSize: "13px", fontWeight: 700 }}>
                      <div>
                        歷史 K 驗證：{validationRecord.historicalKCount}/{validationRecord.recommendationCount}
                      </div>
                      <div>
                        強勢評級：{validationRecord.strongRatingCount}/{validationRecord.recommendationCount}
                      </div>
                      <div>
                        潛力訊號：{validationRecord.validSignalCount}/{validationRecord.recommendationCount}
                      </div>
                      <div>
                        過熱/偏弱排除：
                        {validationRecord.excludedSignalCount === 0
                          ? " 通過"
                          : ` ${validationRecord.excludedSignalCount} 檔需留意`}
                      </div>
                    </div>
                  </div>
                </div>

                <div
                  style={{
                    display: "grid",
                    gridTemplateColumns: isMobile ? "1fr" : "repeat(3, minmax(0,1fr))",
                    gap: "10px",
                    marginBottom: "12px",
                  }}
                >
                  <div
                    style={{
                      borderRadius: "12px",
                      padding: "10px 12px",
                      background: "rgba(255,255,255,0.04)",
                      border: "1px solid rgba(255,255,255,0.08)",
                    }}
                  >
                    <div style={{ color: "#93c8ff", fontSize: "12px", marginBottom: "6px", fontWeight: 700 }}>
                      平均分數
                    </div>
                    <div style={{ color: "#fff5b3", fontWeight: 900, fontSize: "18px" }}>
                      {validationRecord.averageScore.toFixed(2)}
                    </div>
                  </div>

                  <div
                    style={{
                      borderRadius: "12px",
                      padding: "10px 12px",
                      background: "rgba(255,255,255,0.04)",
                      border: "1px solid rgba(255,255,255,0.08)",
                    }}
                  >
                    <div style={{ color: "#93c8ff", fontSize: "12px", marginBottom: "6px", fontWeight: 700 }}>
                      平均風報比
                    </div>
                    <div style={{ color: "#fff5b3", fontWeight: 900, fontSize: "18px" }}>
                      {validationRecord.averageRiskReward > 0
                        ? `1:${validationRecord.averageRiskReward.toFixed(2)}`
                        : "-"}
                    </div>
                  </div>

                  <div
                    style={{
                      borderRadius: "12px",
                      padding: "10px 12px",
                      background: "rgba(255,255,255,0.04)",
                      border: "1px solid rgba(255,255,255,0.08)",
                    }}
                  >
                    <div style={{ color: "#93c8ff", fontSize: "12px", marginBottom: "6px", fontWeight: 700 }}>
                      與前次重複
                    </div>
                    <div style={{ color: "#fff5b3", fontWeight: 900, fontSize: "18px" }}>
                      {previousValidationRecord ? `${repeatedPickCount} 檔` : "尚無前次"}
                    </div>
                  </div>
                </div>

                <div style={{ color: "#9cccf9", fontSize: "12px", fontWeight: 800, marginBottom: "8px" }}>
                  本次主訊號
                </div>
                <div style={{ display: "flex", flexWrap: "wrap", gap: "8px", marginBottom: "10px" }}>
                  {validationRecord.signalSummary.map((item) => (
                    <span
                      key={item}
                      style={{
                        padding: "5px 10px",
                        borderRadius: "999px",
                        background: "rgba(98, 169, 255, 0.16)",
                        border: "1px solid rgba(98, 169, 255, 0.18)",
                        color: "#dbe9ff",
                        fontSize: "12px",
                        fontWeight: 800,
                      }}
                    >
                      {item}
                    </span>
                  ))}
                </div>

                <div style={{ color: "#9cccf9", fontSize: "12px", fontWeight: 800, marginBottom: "8px" }}>
                  最近紀錄
                </div>
                <div style={{ display: "flex", flexWrap: "wrap", gap: "8px" }}>
                  {validationHistory.slice(0, 4).map((item) => (
                    <span
                      key={`${item.dataDate}-${item.lastUpdate}`}
                      style={{
                        padding: "5px 10px",
                        borderRadius: "999px",
                        background: "rgba(255,255,255,0.05)",
                        border: "1px solid rgba(255,255,255,0.08)",
                        color: "#dbe9ff",
                        fontSize: "12px",
                        fontWeight: 700,
                      }}
                    >
                      {formatDateString(item.dataDate)} / {item.recommendationCount} 檔
                    </span>
                  ))}
                </div>
              </div>
            )}

            <div style={{ marginBottom: "20px" }}>
              <div style={{ display: "flex", flexWrap: "wrap", gap: "12px" }}>
                {PRICE_CATEGORIES.map((item) => {
                  const active = selectedCategory === item.key;
                  return (
                    <button
                      key={item.key}
                      type="button"
                      onClick={() => {
                        setSelectedCategory(item.key);
                        setManualSelectedSymbol("");
                        setCurrentPage(1);
                        fetchPagedStocksSafe({
                          category: item.key,
                          page: 1,
                          rank: rankType,
                          keyword: debouncedSearchTerm,
                        });
                      }}
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
                        boxShadow: active ? "0 8px 22px rgba(80, 150, 255, 0.22)" : "none",
                      }}
                    >
                      {item.label} ({categoryCounts[item.key] || 0})
                    </button>
                  );
                })}
              </div>
            </div>

            <input
              value={searchTerm}
              onChange={(e) => {
                setSearchTerm(e.target.value);
                setManualSelectedSymbol("");
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
                      fetchPagedStocksSafe({
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
                lineHeight: 1.8,
                fontSize: "14px",
              }}
            >
              <div style={{ fontWeight: 900, color: "#9fc3f6", marginBottom: "6px" }}>
                交易模式說明
              </div>
              <div>• 搜尋單一個股時，會自動顯示專業分析卡</div>
              <div>• 點擊推薦股或列表股，也可直接切換分析</div>
              <div>• A / B+ 偏強，C 觀察，D 保守控風險</div>
            </div>
          </div>

          <div style={panelStyle}>
            <h2 style={{ fontSize: "24px", fontWeight: 900, marginBottom: "10px" }}>🔥 推薦10檔</h2>

            <div
              style={{
                maxHeight: isMobile ? "none" : "470px",
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
                  const changeColor = isUp ? "#ff4d4f" : "#00c853";
                  const isSelected = activeFocusedStock?.symbol === stock.symbol;

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

                            {stock.operation_rating && (
                              <span
                                style={{
                                  background: "rgba(255,255,255,0.08)",
                                  borderRadius: "999px",
                                  padding: "5px 10px",
                                  fontSize: "14px",
                                  fontWeight: 800,
                                  color: getRatingColor(stock.operation_rating),
                                }}
                              >
                                評級 {stock.operation_rating}
                              </span>
                            )}

                            <span
                              style={{
                                background: "rgba(255,255,255,0.08)",
                                borderRadius: "999px",
                                padding: "5px 10px",
                                fontSize: "14px",
                                fontWeight: 800,
                                color: "#dbe8ff",
                              }}
                            >
                              {stock.market || "-"}
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
                        {stock.reason || "價格維持強勢結構，買盤承接力道偏強，屬盤面表態標的。"}
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
                        <span>風報比：{stock.risk_reward || "-"}</span>
                      </div>
                    </div>
                  );
                })
              )}
            </div>
          </div>
        </section>

        {activeFocusedStock && (
          <section
            style={{
              marginBottom: "22px",
              background: "linear-gradient(180deg, #102f63 0%, #0c2955 100%)",
              border: "1px solid rgba(100,160,255,0.25)",
              borderRadius: "22px",
              padding: isMobile ? "18px" : "24px",
              boxShadow: "0 10px 28px rgba(0,0,0,0.12)",
            }}
          >
            <div
              style={{
                display: "flex",
                justifyContent: "space-between",
                alignItems: isMobile ? "flex-start" : "center",
                gap: "12px",
                flexDirection: isMobile ? "column" : "row",
                marginBottom: "14px",
              }}
            >
              <div>
                <h2 style={{ fontSize: "24px", fontWeight: 900, margin: 0, marginBottom: "8px" }}>
                  📊 個股專業分析
                </h2>
                <div style={{ fontSize: isMobile ? "22px" : "26px", fontWeight: 900, color: "#7fb6ff" }}>
                  {activeFocusedStock.symbol} {activeFocusedStock.name}
                </div>
              </div>

              <div style={{ display: "flex", gap: "10px", flexWrap: "wrap", alignItems: "center" }}>
                <span style={analysisTagStyle}>{activeFocusedStock.market}</span>
                <span style={analysisTagStyle}>{activeFocusedStock.signal}</span>
                <span style={analysisTagStyle}>{activeFocusedStock.trend_type}</span>
                <span
                  style={{
                    ...analysisTagStyle,
                    color: getRatingColor(activeFocusedStock.operation_rating),
                    borderColor: "rgba(255,255,255,0.16)",
                  }}
                >
                  評級 {activeFocusedStock.operation_rating}
                </span>
              </div>
            </div>

            <div
              style={{
                display: "grid",
                gridTemplateColumns: isMobile ? "1fr" : "repeat(4, minmax(0,1fr))",
                gap: "12px",
                marginBottom: "16px",
              }}
            >
              <div style={metricCardStyle}>
                <div style={metricLabelStyle}>現價</div>
                <div style={metricValueStyle}>{formatPrice(activeFocusedStock.price)}</div>
              </div>
              <div style={metricCardStyle}>
                <div style={metricLabelStyle}>漲跌</div>
                <div
                  style={{
                    ...metricValueStyle,
                    color: activeFocusedStock.change >= 0 ? "#ff8b8b" : "#57e389",
                  }}
                >
                  {formatSigned(activeFocusedStock.change)}
                </div>
              </div>
              <div style={metricCardStyle}>
                <div style={metricLabelStyle}>漲跌%</div>
                <div
                  style={{
                    ...metricValueStyle,
                    color: activeFocusedStock.change_percent >= 0 ? "#ff8b8b" : "#57e389",
                  }}
                >
                  {formatSigned(activeFocusedStock.change_percent)}%
                </div>
              </div>
              <div style={metricCardStyle}>
                <div style={metricLabelStyle}>成交量</div>
                <div style={metricValueStyle}>{formatNumber(activeFocusedStock.volume)}</div>
              </div>
            </div>

            <div
              style={{
                display: "grid",
                gridTemplateColumns: isMobile ? "1fr" : "1fr 1fr",
                gap: "14px",
                marginBottom: "14px",
              }}
            >
              <div style={analysisBlockStyle}>
                <div style={analysisBlockTitleStyle}>操作方向</div>
                <div style={analysisBlockTextStyle}>
                  {activeFocusedStock.operation_bias} ｜ {activeFocusedStock.operation_style}
                </div>
              </div>
              <div style={analysisBlockStyle}>
                <div style={analysisBlockTitleStyle}>更新時間</div>
                <div style={analysisBlockTextStyle}>{activeFocusedStock.update_time || "-"}</div>
              </div>
            </div>

            <div style={analysisBlockStyle}>
              <div style={analysisBlockTitleStyle}>技術分析</div>
              <div style={analysisBlockTextStyle}>{activeFocusedStock.technical_comment}</div>
            </div>

            <div style={analysisBlockStyle}>
              <div style={analysisBlockTitleStyle}>分析結論</div>
              <div style={analysisBlockTextStyle}>{activeFocusedStock.analysis}</div>
            </div>

            <div style={analysisBlockStyle}>
              <div style={analysisBlockTitleStyle}>操作戰略</div>
              <div style={analysisBlockTextStyle}>{activeFocusedStock.strategy_action}</div>
            </div>

            <div
              style={{
                display: "grid",
                gridTemplateColumns: isMobile ? "1fr" : "repeat(4, minmax(0,1fr))",
                gap: "12px",
                marginTop: "16px",
              }}
            >
              {[
                { label: "建議進場", value: activeFocusedStock.entry_price },
                { label: "目標價", value: activeFocusedStock.target_price },
                { label: "停損價", value: activeFocusedStock.stop_loss },
                { label: "風報比", value: activeFocusedStock.risk_reward },
              ].map(({ label, value }) => (
                <div key={label} style={tradePlanCardStyle}>
                  <div style={tradePlanLabelStyle}>{label}</div>
                  <div style={tradePlanValueStyle}>{value || "-"}</div>
                </div>
              ))}
            </div>

            <div
              style={{
                marginTop: "16px",
                padding: "14px 16px",
                borderRadius: "16px",
                background: "rgba(255, 92, 92, 0.08)",
                border: "1px solid rgba(255, 120, 120, 0.18)",
                color: "#ffb4b4",
                lineHeight: 1.8,
                fontWeight: 700,
              }}
            >
              ⚠️ 風險提醒：{activeFocusedStock.risk_note || "-"}
            </div>
          </section>
        )}

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
              股票列表 ({total})
            </h2>
            <div style={{ color: "#cfe2ff", fontSize: "14px", fontWeight: 700 }}>
              第 {currentPage} / {totalPages} 頁，每頁 {ITEMS_PER_PAGE} 檔
            </div>
          </div>

          <div style={{ overflowX: "auto", borderRadius: "18px" }}>
            <table
              style={{
                width: "100%",
                borderCollapse: "collapse",
                tableLayout: "fixed",
              }}
            >
              <thead>
                <tr style={{ background: "linear-gradient(180deg, #3570bd 0%, #285d9f 100%)" }}>
                  <th style={thStyle}>市場</th>
                  <th style={thStyle}>代號</th>
                  <th style={{ ...thStyle, textAlign: "left" }}>名稱</th>
                  <th style={thStyle}>股價</th>
                  <th style={thStyle}>漲跌</th>
                  <th style={thStyle}>漲跌%</th>
                  <th style={thStyle}>成交量</th>
                  <th style={thStyle}>訊號</th>
                  <th style={thStyle}>評級</th>
                  <th style={thStyle}>分數</th>
                  <th style={thStyle}>風報比</th>
                </tr>
              </thead>

              <tbody>
                {stocks.map((stock) => {
                  const isUp = stock.change >= 0;
                  const color = isUp ? "#ff4d4f" : "#00c853";
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
                        height: "46px",
                        borderBottom: "1px solid rgba(255,255,255,0.06)",
                        background: isSelected
                          ? "rgba(22, 71, 134, 0.88)"
                          : "rgba(8, 36, 76, 0.55)",
                        cursor: "pointer",
                        transition: "0.18s ease",
                      }}
                    >
                      <td style={tdStyle}>{stock.market || "-"}</td>

                      <td style={tdStyle}>
                        <span
                          style={{
                            fontSize: "13px",
                            fontWeight: 900,
                            color: "#7fb6ff",
                          }}
                        >
                          {stock.symbol}
                        </span>
                      </td>

                      <td
                        style={{
                          ...tdStyle,
                          textAlign: "left",
                          overflow: "hidden",
                        }}
                        title={stock.name}
                      >
                        <span
                          style={{
                            display: "block",
                            overflow: "hidden",
                            textOverflow: "ellipsis",
                            whiteSpace: "nowrap",
                            fontWeight: 700,
                          }}
                        >
                          {stock.name}
                        </span>
                      </td>

                      <td style={tdStyle}>
                        <span style={{ fontWeight: 900 }}>{formatPrice(stock.price)}</span>
                      </td>

                      <td style={tdStyle}>
                        <span style={{ color, fontWeight: 900 }}>
                          {formatSigned(stock.change)}
                        </span>
                      </td>

                      <td style={tdStyle}>
                        <span style={{ color, fontWeight: 800 }}>
                          {formatSigned(stock.change_percent)}%
                        </span>
                      </td>

                      <td style={tdStyle}>{formatNumber(stock.volume)}</td>

                      <td style={tdStyle}>
                        <span
                          style={{
                            display: "inline-block",
                            maxWidth: "100%",
                            overflow: "hidden",
                            textOverflow: "ellipsis",
                            whiteSpace: "nowrap",
                            background: "rgba(255,255,255,0.08)",
                            padding: "3px 6px",
                            borderRadius: "999px",
                            fontSize: "10px",
                            fontWeight: 800,
                          }}
                          title={stock.signal || "-"}
                        >
                          {stock.signal || "-"}
                        </span>
                      </td>

                      <td
                        style={{
                          ...tdStyle,
                          color: getRatingColor(stock.operation_rating),
                          fontWeight: 900,
                        }}
                      >
                        {stock.operation_rating || "-"}
                      </td>

                      <td style={tdStyle}>{stock.score ?? 0}</td>

                      <td style={tdStyle}>{stock.risk_reward || "-"}</td>
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
                type="button"
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
                      style={{ color: "#d9e7ff", padding: "0 4px", fontWeight: 800 }}
                    >
                      ...
                    </span>
                  );
                }
                const active = currentPage === page;
                return (
                  <button
                    key={page}
                    type="button"
                    onClick={() => setCurrentPage(page)}
                    style={{
                      ...pageBtnStyle,
                      background: active
                        ? "linear-gradient(180deg, #61a8ff 0%, #3e7fe0 100%)"
                        : "#184889",
                      boxShadow: active ? "0 8px 22px rgba(80, 150, 255, 0.22)" : "none",
                    }}
                  >
                    {page}
                  </button>
                );
              })}

              <button
                type="button"
                onClick={() => setCurrentPage((p) => Math.min(totalPages, p + 1))}
                disabled={currentPage === totalPages}
                style={{
                  ...pageBtnStyle,
                  opacity: currentPage === totalPages ? 0.45 : 1,
                  cursor: currentPage === totalPages ? "not-allowed" : "pointer",
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
  padding: "8px 6px",
  textAlign: "center",
  color: "#ffffff",
  fontSize: "12px",
  fontWeight: 800,
  whiteSpace: "nowrap",
  lineHeight: 1.1,
};

const tdStyle: React.CSSProperties = {
  padding: "6px 6px",
  textAlign: "center",
  color: "#ffffff",
  fontSize: "12px",
  fontWeight: 700,
  verticalAlign: "middle",
  lineHeight: 1,
};

const analysisTagStyle: React.CSSProperties = {
  background: "rgba(255,255,255,0.08)",
  border: "1px solid rgba(255,255,255,0.1)",
  padding: "6px 10px",
  borderRadius: "999px",
  fontWeight: 800,
  color: "#dbe8ff",
  fontSize: "14px",
};

const metricCardStyle: React.CSSProperties = {
  background: "rgba(255,255,255,0.05)",
  border: "1px solid rgba(255,255,255,0.08)",
  borderRadius: "16px",
  padding: "14px 16px",
};

const metricLabelStyle: React.CSSProperties = {
  color: "#9fc3f6",
  fontSize: "13px",
  fontWeight: 700,
  marginBottom: "8px",
};

const metricValueStyle: React.CSSProperties = {
  color: "#ffffff",
  fontSize: "22px",
  fontWeight: 900,
};

const analysisBlockStyle: React.CSSProperties = {
  marginTop: "12px",
  padding: "14px 16px",
  borderRadius: "16px",
  background: "rgba(255,255,255,0.04)",
  border: "1px solid rgba(255,255,255,0.08)",
};

const analysisBlockTitleStyle: React.CSSProperties = {
  color: "#7fb6ff",
  fontSize: "15px",
  fontWeight: 900,
  marginBottom: "8px",
};

const analysisBlockTextStyle: React.CSSProperties = {
  color: "#dbe8ff",
  lineHeight: 1.85,
  fontSize: "15px",
  fontWeight: 700,
};

const tradePlanCardStyle: React.CSSProperties = {
  background: "linear-gradient(180deg, rgba(45,95,170,0.55) 0%, rgba(22,58,107,0.55) 100%)",
  border: "1px solid rgba(108,162,255,0.16)",
  borderRadius: "16px",
  padding: "14px 16px",
};

const tradePlanLabelStyle: React.CSSProperties = {
  color: "#9fc3f6",
  fontSize: "13px",
  fontWeight: 700,
  marginBottom: "8px",
};

const tradePlanValueStyle: React.CSSProperties = {
  color: "#ffffff",
  fontSize: "16px",
  fontWeight: 900,
  lineHeight: 1.6,
};
