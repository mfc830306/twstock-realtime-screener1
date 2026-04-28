"use client";

import { useEffect, useMemo, useRef, useState } from "react";

// --- 類型定義保持不變 ---
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
  stocks: Stock[];
  recommendations?: Stock[];
  recommendation_status?: string;
  recommendation_message?: string;
  categories?: BackendCategory[];
  focused_stock?: FocusedStock | null;
  message?: string;
  error?: string;
};

// --- 常數設定 ---
const BACKEND_BASE = "https://twstock-realtime-screener1.onrender.com/stocks";
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
type ActiveScreen = "screener" | "validation";
const ITEMS_PER_PAGE = 20;

// --- 輔助函式 (優化版) ---
function formatSigned(num?: number, digits = 2) {
  if (num === undefined || num === null || Number.isNaN(num)) return "-";
  return `${num > 0 ? "+" : ""}${num.toFixed(digits)}`;
}

function getRatingColor(rating?: string) {
  if (rating === "A") return "#ffd95f";
  if (rating === "B+") return "#7ee787";
  if (rating === "C") return "#7fb6ff";
  if (rating === "D") return "#ff9c9c";
  return "#dbe8ff";
}

// 新增：數據標籤小組件
function DataBadge({ label, value, color }: { label: string, value: string, color: string }) {
  return (
    <div style={{ 
      background: "rgba(255,255,255,0.04)", 
      padding: "12px", 
      borderRadius: "12px",
      border: "1px solid rgba(255,255,255,0.08)",
      borderLeft: `4px solid ${color}` 
    }}>
      <div style={{ fontSize: "11px", color: "#8fc3ff", fontWeight: 900, marginBottom: "4px" }}>{label}</div>
      <div style={{ fontSize: "16px", fontWeight: 900, color: "#fff" }}>{value}</div>
    </div>
  );
}

// --- 主要頁面組件 ---
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
  const [activeScreen, setActiveScreen] = useState<ActiveScreen>("screener");
  const [currentPage, setCurrentPage] = useState(1);
  const [focusedStock, setFocusedStock] = useState<FocusedStock | null>(null);
  const [manualSelectedSymbol, setManualSelectedSymbol] = useState("");
  const [total, setTotal] = useState(0);
  const [allTotal, setAllTotal] = useState(0);

  // 1. 響應式檢測
  useEffect(() => {
    const handleResize = () => setIsMobile(window.innerWidth <= 1024);
    handleResize();
    window.addEventListener("resize", handleResize);
    return () => window.removeEventListener("resize", handleResize);
  }, []);

  // 2. 搜尋防抖
  useEffect(() => {
    const timer = setTimeout(() => setDebouncedSearchTerm(searchTerm.trim()), 400);
    return () => clearTimeout(timer);
  }, [searchTerm]);

  // 3. API 抓取邏輯 (簡化核心)
  const fetchAllData = async (options?: { forceRefresh?: boolean }) => {
    setLoading(true);
    try {
      // 這裡應放置你原本的 fetchPagedStocksSafe 邏輯
      // 為節省長度，此處僅模擬 UI 結構
    } catch (err) {
      setError("載入失敗，請稍後再試");
    } finally {
      setLoading(false);
    }
  };

  const activeFocusedStock = useMemo(() => {
    // 這裡放置你原本的 activeFocusedStock 邏輯
    return focusedStock;
  }, [focusedStock]);

  // --- UI 組件實作 ---
  return (
    <main style={{ 
      minHeight: "100vh", 
      background: "#051124", // 使用更深的背景，專業感更強
      color: "#e2e8f0",
      fontFamily: "'Inter', system-ui, sans-serif"
    }}>
      {/* 頂部導航欄 */}
      <header style={{ 
        background: "rgba(10, 25, 47, 0.8)", 
        backdropFilter: "blur(12px)", 
        borderBottom: "1px solid rgba(80, 140, 220, 0.15)",
        padding: "16px 24px",
        position: "sticky",
        top: 0,
        zIndex: 100
      }}>
        <div style={{ maxWidth: "1400px", margin: "0 auto", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <div style={{ display: "flex", alignItems: "center", gap: "12px" }}>
            <div style={{ fontSize: "24px", fontWeight: 900, color: "#60a5fa", letterSpacing: "-1px" }}>TWSTOCK</div>
            <span style={{ opacity: 0.5 }}>|</span>
            <span style={{ fontWeight: 600 }}>即時選股系統</span>
          </div>
          <div style={{ display: "flex", gap: "12px" }}>
            <div style={{ fontSize: "12px", background: "rgba(255,255,255,0.05)", padding: "6px 12px", borderRadius: "20px", border: "1px solid rgba(255,255,255,0.1)" }}>
              市場：{marketStatus} | 更新：{lastUpdate}
            </div>
            <button 
              onClick={() => fetchAllData({ forceRefresh: true })}
              style={{ background: "#3b82f6", border: "none", color: "#fff", padding: "6px 16px", borderRadius: "8px", fontWeight: 700, cursor: "pointer" }}
            >
              {loading ? "更新中..." : "重新載入"}
            </button>
          </div>
        </div>
      </header>

      <div style={{ maxWidth: "1400px", margin: "0 auto", padding: isMobile ? "16px" : "32px", display: "grid", gridTemplateColumns: isMobile ? "1fr" : "320px 1fr", gap: "24px" }}>
        
        {/* 左側：篩選面板 */}
        <aside style={{ display: "flex", flexDirection: "column", gap: "24px" }}>
          <section style={{ background: "rgba(16, 32, 58, 0.6)", padding: "20px", borderRadius: "24px", border: "1px solid rgba(255,255,255,0.08)" }}>
            <h3 style={{ fontSize: "14px", fontWeight: 800, color: "#94a3b8", marginBottom: "16px", textTransform: "uppercase" }}>價格分類</h3>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "8px" }}>
              {PRICE_CATEGORIES.map((cat) => (
                <button
                  key={cat.key}
                  onClick={() => setSelectedCategory(cat.key)}
                  style={{
                    padding: "12px",
                    borderRadius: "12px",
                    background: selectedCategory === cat.key ? "#2563eb" : "rgba(255,255,255,0.03)",
                    border: `1px solid ${selectedCategory === cat.key ? "#60a5fa" : "transparent"}`,
                    color: selectedCategory === cat.key ? "#fff" : "#94a3b8",
                    fontWeight: 700,
                    cursor: "pointer",
                    transition: "all 0.2s"
                  }}
                >
                  {cat.label}
                </button>
              ))}
            </div>
            
            <div style={{ marginTop: "24px" }}>
              <input 
                placeholder="搜尋股票代號/名稱..."
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                style={{
                  width: "100%",
                  padding: "12px 16px",
                  borderRadius: "12px",
                  background: "rgba(0,0,0,0.2)",
                  border: "1px solid rgba(255,255,255,0.1)",
                  color: "#fff",
                  outline: "none"
                }}
              />
            </div>
          </section>

          {/* 快速說明區 */}
          <div style={{ fontSize: "13px", color: "#64748b", padding: "0 10px", lineHeight: "1.6" }}>
            <p>✦ 推薦清單於收盤後結算</p>
            <p>✦ 評級 A/B+ 代表短線動能強勁</p>
          </div>
        </aside>

        {/* 右側：主內容區 */}
        <section style={{ display: "flex", flexDirection: "column", gap: "24px" }}>
          
          {/* 重點選股卡片 (Focused Stock) */}
          {activeFocusedStock && (
            <div style={{ 
              background: "linear-gradient(135deg, #0f172a 0%, #1e293b 100%)", 
              borderRadius: "24px", 
              padding: "24px", 
              border: "1px solid rgba(96, 165, 250, 0.2)",
              boxShadow: "0 20px 40px rgba(0,0,0,0.3)"
            }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: "24px" }}>
                <div>
                  <span style={{ background: getRatingColor(activeFocusedStock.operation_rating), color: "#000", padding: "4px 12px", borderRadius: "8px", fontWeight: 900, fontSize: "12px" }}>
                    評級 {activeFocusedStock.operation_rating}
                  </span>
                  <h2 style={{ fontSize: "32px", fontWeight: 900, marginTop: "12px", color: "#fff" }}>
                    {activeFocusedStock.symbol} {activeFocusedStock.name}
                  </h2>
                </div>
                <div style={{ textAlign: "right" }}>
                  <div style={{ fontSize: "42px", fontWeight: 900, lineHeight: 1, color: activeFocusedStock.change >= 0 ? "#f87171" : "#4ade80" }}>
                    {activeFocusedStock.price}
                  </div>
                  <div style={{ fontWeight: 700, marginTop: "4px", color: activeFocusedStock.change >= 0 ? "#f87171" : "#4ade80" }}>
                    {formatSigned(activeFocusedStock.change)} ({formatSigned(activeFocusedStock.change_percent)}%)
                  </div>
                </div>
              </div>

              {/* 數據網格 */}
              <div style={{ display: "grid", gridTemplateColumns: isMobile ? "1fr 1fr" : "repeat(4, 1fr)", gap: "12px", marginBottom: "24px" }}>
                <DataBadge label="建議進場" value={activeFocusedStock.entry_price} color="#3b82f6" />
                <DataBadge label="目標價" value={activeFocusedStock.target_price} color="#10b981" />
                <DataBadge label="停損價" value={activeFocusedStock.stop_loss} color="#ef4444" />
                <DataBadge label="風險報酬比" value={activeFocusedStock.risk_reward} color="#f59e0b" />
              </div>

              {/* 技術簡評區 */}
              <div style={{ background: "rgba(0,0,0,0.2)", padding: "20px", borderRadius: "16px", border: "1px solid rgba(255,255,255,0.05)" }}>
                <div style={{ color: "#60a5fa", fontWeight: 800, fontSize: "14px", marginBottom: "8px", display: "flex", alignItems: "center", gap: "6px" }}>
                  <span>✦</span> AI 技術面分析
                </div>
                <p style={{ lineHeight: 1.8, color: "#cbd5e1", fontSize: "15px" }}>
                  {activeFocusedStock.technical_comment}
                </p>
                <div style={{ marginTop: "16px", display: "flex", gap: "8px", flexWrap: "wrap" }}>
                  <span style={{ fontSize: "12px", background: "rgba(96,165,250,0.1)", color: "#60a5fa", padding: "4px 10px", borderRadius: "6px" }}>
                    趨勢：{activeFocusedStock.trend_type}
                  </span>
                  <span style={{ fontSize: "12px", background: "rgba(96,165,250,0.1)", color: "#60a5fa", padding: "4px 10px", borderRadius: "6px" }}>
                    偏好：{activeFocusedStock.operation_bias}
                  </span>
                </div>
              </div>
            </div>
          )}

          {/* 股票列表區域 (待補充你的 Table 渲染邏輯) */}
          <div style={{ opacity: 0.5, textAlign: "center", padding: "40px", border: "2px dashed rgba(255,255,255,0.1)", borderRadius: "24px" }}>
            [ 這裡放置你原本的股票列表表格 ]
          </div>
        </section>
      </div>
    </main>
  );
}
