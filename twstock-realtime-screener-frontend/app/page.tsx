"use client";

import { useEffect, useMemo, useRef, useState } from "react";

// --- 1. 完整的型別定義 (保留你的原始設定) ---
type Stock = {
  market?: string; symbol: string; name: string; price: number;
  change: number; change_percent: number; volume?: number; score?: number;
  recommendation_score?: number; signal?: string; trend_type?: string;
  reason?: string; technical_comment?: string; operation_rating?: string;
  operation_bias?: string; operation_style?: string; strategy_action?: string;
  entry_price?: string; target_price?: string; stop_loss?: string;
  risk_reward?: string; risk_note?: string; update_time?: string;
};

type FocusedStock = {
  symbol: string; name: string; market: string; price: number;
  change: number; change_percent: number; volume: number; signal: string;
  trend_type: string; operation_rating: string; operation_bias: string;
  operation_style: string; technical_comment: string; analysis: string;
  strategy_action: string; entry_price: string; target_price: string;
  stop_loss: string; risk_reward: string; risk_note: string; update_time: string;
};

type ApiResponse = {
  success: boolean; market_status?: string; data_date?: string;
  last_update?: string; total?: number; all_total?: number;
  stocks: Stock[]; recommendations?: Stock[]; recommendation_status?: string;
  recommendation_message?: string; categories?: any[]; focused_stock?: FocusedStock | null;
};

// --- 2. 工具函式 ---
const BACKEND_BASE = "https://twstock-realtime-screener1.onrender.com/stocks";
const PRICE_CATEGORIES = [
  { key: "all", label: "全部" }, { key: "0-50", label: "0-50" },
  { key: "50-100", label: "50-100" }, { key: "100-200", label: "100-200" },
  { key: "200-500", label: "200-500" }, { key: "500+", label: "500+" }
] as const;

type CategoryKey = (typeof PRICE_CATEGORIES)[number]["key"];
function formatSigned(num?: number) {
  if (num === undefined || num === null) return "-";
  return `${num > 0 ? "+" : ""}${num.toFixed(2)}`;
}
function getRatingColor(rating?: string) {
  if (rating === "A") return "#ffd95f";
  if (rating === "B+") return "#7ee787";
  if (rating === "C") return "#7fb6ff";
  return "#dbe8ff";
}

// 數據標籤小組件
function DataBadge({ label, value, color }: { label: string, value: string, color: string }) {
  return (
    <div style={{ background: "rgba(255,255,255,0.03)", padding: "12px", borderRadius: "12px", border: "1px solid rgba(255,255,255,0.06)", borderLeft: `4px solid ${color}` }}>
      <div style={{ fontSize: "11px", color: "#8fc3ff", fontWeight: 900, marginBottom: "4px" }}>{label}</div>
      <div style={{ fontSize: "16px", fontWeight: 900, color: "#fff" }}>{value}</div>
    </div>
  );
}

export default function Home() {
  // --- 3. 狀態管理 (找回你原本的靈魂) ---
  const [stocks, setStocks] = useState<Stock[]>([]);
  const [marketStatus, setMarketStatus] = useState("-");
  const [dataDate, setDataDate] = useState("-");
  const [lastUpdate, setLastUpdate] = useState("-");
  const [searchTerm, setSearchTerm] = useState("");
  const [selectedCategory, setSelectedCategory] = useState<CategoryKey>("all");
  const [loading, setLoading] = useState(false);
  const [isMobile, setIsMobile] = useState(false);
  const [focusedStock, setFocusedStock] = useState<FocusedStock | null>(null);
  const [recommendations, setRecommendations] = useState<Stock[]>([]);

  // 4. API 核心邏輯 (完整移植)
  const fetchData = async (force = false) => {
    setLoading(true);
    try {
      const params = new URLSearchParams({
        limit: "20",
        sort_by: "recommendation_score",
        sort_dir: "desc"
      });
      if (force) params.set("force_refresh", "true");
      if (searchTerm) params.set("q", searchTerm);
      
      const res = await fetch(`${BACKEND_BASE}?${params.toString()}`, { cache: "no-store" });
      const data: ApiResponse = await res.json();
      
      if (data.success) {
        setStocks(data.stocks || []);
        setMarketStatus(data.market_status || "-");
        setDataDate(data.data_date || "-");
        setLastUpdate(data.last_update || new Date().toLocaleTimeString());
        setRecommendations(data.recommendations?.slice(0, 10) || []);
        if (data.focused_stock) setFocusedStock(data.focused_stock);
        else if (data.stocks.length > 0) {
            // 預設抓第一檔作為顯示
            const s = data.stocks[0];
            setFocusedStock({ ...s, analysis: s.reason || "", technical_comment: s.technical_comment || s.reason || "" } as any);
        }
      }
    } catch (e) {
      console.error("Fetch Error:", e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
    const handleResize = () => setIsMobile(window.innerWidth <= 1024);
    window.addEventListener("resize", handleResize);
    handleResize();
    return () => window.removeEventListener("resize", handleResize);
  }, []);

  // 5. 畫面渲染 (新 UI 結構)
  return (
    <main style={{ minHeight: "100vh", background: "#051124", color: "#e2e8f0", fontFamily: "sans-serif" }}>
      {/* Header */}
      <header style={{ background: "rgba(10, 25, 47, 0.8)", backdropFilter: "blur(10px)", borderBottom: "1px solid rgba(80, 140, 220, 0.15)", padding: "14px 24px", position: "sticky", top: 0, zIndex: 100 }}>
        <div style={{ maxWidth: "1400px", margin: "0 auto", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <div style={{ display: "flex", alignItems: "center", gap: "12px" }}>
            <div style={{ fontSize: "22px", fontWeight: 900, color: "#60a5fa" }}>TWSTOCK</div>
            <span style={{ fontSize: "14px", fontWeight: 600 }}>即時選股系統</span>
          </div>
          <div style={{ display: "flex", gap: "10px", alignItems: "center" }}>
             <div style={{ fontSize: "12px", color: "#94a3b8" }}>{marketStatus} | {lastUpdate}</div>
             <button onClick={() => fetchData(true)} style={{ background: "#2563eb", color: "white", border: "none", padding: "8px 16px", borderRadius: "8px", fontWeight: 700, cursor: "pointer" }}>
               {loading ? "更新中" : "同步數據"}
             </button>
          </div>
        </div>
      </header>

      <div style={{ maxWidth: "1400px", margin: "0 auto", padding: isMobile ? "16px" : "24px", display: "grid", gridTemplateColumns: isMobile ? "1fr" : "300px 1fr", gap: "24px" }}>
        
        {/* 左側：篩選區 */}
        <aside style={{ display: "flex", flexDirection: "column", gap: "20px" }}>
          <div style={{ background: "#0f172a", padding: "20px", borderRadius: "20px", border: "1px solid rgba(255,255,255,0.05)" }}>
            <h3 style={{ fontSize: "12px", color: "#64748b", marginBottom: "12px", fontWeight: 800 }}>價格分類篩選</h3>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "8px" }}>
              {PRICE_CATEGORIES.map(cat => (
                <button key={cat.key} onClick={() => setSelectedCategory(cat.key)} style={{ padding: "10px", borderRadius: "10px", background: selectedCategory === cat.key ? "#2563eb" : "rgba(255,255,255,0.03)", border: "none", color: "#fff", cursor: "pointer", fontWeight: 600 }}>
                  {cat.label}
                </button>
              ))}
            </div>
            <input 
              placeholder="代號搜尋..." 
              value={searchTerm} 
              onChange={(e) => setSearchTerm(e.target.value)} 
              onKeyDown={(e) => e.key === 'Enter' && fetchData()}
              style={{ width: "100%", marginTop: "16px", padding: "12px", borderRadius: "10px", background: "#000", border: "1px solid #334155", color: "#fff" }} 
            />
          </div>

          <div style={{ background: "rgba(255,255,255,0.02)", padding: "16px", borderRadius: "15px" }}>
            <div style={{ fontSize: "13px", color: "#94a3b8", marginBottom: "10px", fontWeight: 700 }}>🔥 今日推薦</div>
            {recommendations.map(s => (
                <div key={s.symbol} onClick={() => setFocusedStock(s as any)} style={{ display: "flex", justifyContent: "space-between", padding: "8px 0", borderBottom: "1px solid rgba(255,255,255,0.05)", cursor: "pointer" }}>
                    <span style={{ fontSize: "14px" }}>{s.symbol} {s.name}</span>
                    <span style={{ color: s.change >= 0 ? "#f87171" : "#4ade80", fontWeight: 700 }}>{s.price}</span>
                </div>
            ))}
          </div>
        </aside>

        {/* 右側：主顯示區 */}
        <section style={{ display: "flex", flexDirection: "column", gap: "24px" }}>
          {focusedStock ? (
            <div style={{ background: "linear-gradient(135deg, #0f172a 0%, #1e293b 100%)", borderRadius: "24px", padding: "24px", border: "1px solid rgba(96, 165, 250, 0.2)" }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: "20px" }}>
                <div>
                  <span style={{ background: getRatingColor(focusedStock.operation_rating), color: "#000", padding: "4px 10px", borderRadius: "6px", fontWeight: 900, fontSize: "12px" }}>
                    評級 {focusedStock.operation_rating || "B"}
                  </span>
                  <h2 style={{ fontSize: "28px", fontWeight: 900, marginTop: "10px" }}>{focusedStock.symbol} {focusedStock.name}</h2>
                </div>
                <div style={{ textAlign: "right" }}>
                  <div style={{ fontSize: "36px", fontWeight: 900, color: focusedStock.change >= 0 ? "#f87171" : "#4ade80" }}>{focusedStock.price}</div>
                  <div style={{ color: focusedStock.change >= 0 ? "#f87171" : "#4ade80", fontWeight: 700 }}>{formatSigned(focusedStock.change)} ({formatSigned(focusedStock.change_percent)}%)</div>
                </div>
              </div>

              <div style={{ display: "grid", gridTemplateColumns: isMobile ? "1fr 1fr" : "repeat(4, 1fr)", gap: "10px", marginBottom: "20px" }}>
                <DataBadge label="建議進場" value={focusedStock.entry_price || "-"} color="#3b82f6" />
                <DataBadge label="目標價" value={focusedStock.target_price || "-"} color="#10b981" />
                <DataBadge label="停損價" value={focusedStock.stop_loss || "-"} color="#ef4444" />
                <DataBadge label="風報比" value={focusedStock.risk_reward || "-"} color="#f59e0b" />
              </div>

              <div style={{ background: "rgba(0,0,0,0.2)", padding: "16px", borderRadius: "12px", lineHeight: "1.7", fontSize: "15px", color: "#cbd5e1" }}>
                <div style={{ color: "#60a5fa", fontWeight: 800, marginBottom: "8px" }}>✦ AI 分析意見</div>
                {focusedStock.technical_comment}
              </div>
            </div>
          ) : (
            <div style={{ padding: "40px", textAlign: "center", color: "#64748b" }}>請選擇股票以查看分析</div>
          )}

          {/* 表格區 */}
          <div style={{ overflowX: "auto" }}>
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "14px" }}>
              <thead>
                <tr style={{ color: "#64748b", textAlign: "left", borderBottom: "1px solid #1e293b" }}>
                  <th style={{ padding: "12px" }}>股票</th>
                  <th style={{ padding: "12px" }}>現價</th>
                  <th style={{ padding: "12px" }}>漲跌</th>
                  <th style={{ padding: "12px" }}>漲幅%</th>
                  <th style={{ padding: "12px" }}>訊號</th>
                </tr>
              </thead>
              <tbody>
                {stocks.map(s => (
                  <tr key={s.symbol} onClick={() => setFocusedStock(s as any)} style={{ borderBottom: "1px solid #1e293b", cursor: "pointer" }}>
                    <td style={{ padding: "12px", fontWeight: 700 }}>{s.symbol} {s.name}</td>
                    <td style={{ padding: "12px" }}>{s.price}</td>
                    <td style={{ padding: "12px", color: s.change >= 0 ? "#f87171" : "#4ade80" }}>{formatSigned(s.change)}</td>
                    <td style={{ padding: "12px", color: s.change >= 0 ? "#f87171" : "#4ade80" }}>{formatSigned(s.change_percent)}%</td>
                    <td style={{ padding: "12px" }}>{s.signal || "持平"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      </div>
    </main>
  );
}
