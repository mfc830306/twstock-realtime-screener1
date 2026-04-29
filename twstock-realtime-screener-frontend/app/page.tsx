"use client";

import { useEffect, useMemo, useRef, useState, useCallback } from "react";

// --- Types (整合後端對接) ---
type Stock = {
  market?: string; symbol: string; name: string; price: number;
  change: number; change_percent: number; volume?: number; score?: number;
  recommendation_score?: number; signal?: string; trend_type?: string;
  reason?: string; technical_comment?: string; operation_rating?: string;
  operation_bias?: string; operation_style?: string; strategy_action?: string;
  entry_price?: string; target_price?: string; stop_loss?: string;
  risk_reward?: string; risk_note?: string; update_time?: string;
  book_selection_score?: number; book_market_regime?: string;
};

type FocusedStock = Stock & { analysis?: string };

type BackendCategory = { key: string; label: string; count: number };

type ApiResponse = {
  success: boolean; market_status?: string; data_date?: string; last_update?: string;
  total?: number; stocks: Stock[]; recommendations?: Stock[];
  categories?: BackendCategory[]; focused_stock?: FocusedStock | null;
};

// --- 常數 ---
const BACKEND_BASE = "https://twstock-realtime-screener1.onrender.com/stocks";
const PRICE_CATEGORIES = [
  { key: "all", label: "全部" }, { key: "0-50", label: "0-50" },
  { key: "50-100", label: "50-100" }, { key: "100-200", label: "100-200" },
  { key: "200-500", label: "200-500" }, { key: "500+", label: "500+" },
] as const;

// --- 優化組件 ---
const Badge = ({ children, type }: { children: any, type: string }) => {
  const colors: any = {
    "A": { bg: "rgba(255, 217, 95, 0.2)", text: "#ffd95f", border: "#ffd95f" },
    "B+": { bg: "rgba(126, 231, 135, 0.2)", text: "#7ee787", border: "#7ee787" },
    "C": { bg: "rgba(127, 182, 255, 0.2)", text: "#7fb6ff", border: "#7fb6ff" },
    "default": { bg: "rgba(255,255,255,0.1)", text: "#fff", border: "transparent" }
  };
  const theme = colors[type] || colors.default;
  return (
    <span style={{ 
      background: theme.bg, color: theme.text, border: `1px solid ${theme.border}`,
      padding: "2px 8px", borderRadius: "6px", fontSize: "12px", fontWeight: 800 
    }}>{children}</span>
  );
};

const Metric = ({ label, value, color }: { label: string, value: string, color: string }) => (
  <div style={{ background: "rgba(255,255,255,0.03)", padding: "16px", borderRadius: "16px", border: "1px solid rgba(255,255,255,0.06)" }}>
    <div style={{ fontSize: "12px", color: "#94a3b8", fontWeight: 600, marginBottom: "4px" }}>{label}</div>
    <div style={{ fontSize: "20px", fontWeight: 900, color: color }}>{value}</div>
  </div>
);

export default function EnhancedScreener() {
  const [stocks, setStocks] = useState<Stock[]>([]);
  const [loading, setLoading] = useState(false);
  const [searchTerm, setSearchTerm] = useState("");
  const [selectedCategory, setSelectedCategory] = useState("all");
  const [focusedStock, setFocusedStock] = useState<FocusedStock | null>(null);
  const [marketInfo, setMarketInfo] = useState({ status: "-", update: "-", date: "-" });

  // 1. 核心 Fetch 邏輯 (整合你後端的分頁與篩選)
  const fetchData = useCallback(async (force = false) => {
    setLoading(true);
    try {
      const query = new URLSearchParams({
        limit: "50",
        price_range: selectedCategory,
        q: searchTerm,
        force_refresh: force ? "true" : "false"
      });
      const res = await fetch(`${BACKEND_BASE}?${query}`);
      const data: ApiResponse = await res.json();
      if (data.success) {
        setStocks(data.stocks);
        setMarketInfo({ status: data.market_status || "-", update: data.last_update || "-", date: data.data_date || "-" });
        if (data.focused_stock) setFocusedStock(data.focused_stock);
        else if (data.stocks.length > 0) setFocusedStock(data.stocks[0] as FocusedStock);
      }
    } catch (err) {
      console.error("Fetch failed", err);
    } finally {
      setLoading(false);
    }
  }, [selectedCategory, searchTerm]);

  useEffect(() => { fetchData(); }, [fetchData]);

  return (
    <div style={{ minHeight: "100vh", background: "#020617", color: "#f8fafc", fontFamily: "Inter, system-ui, sans-serif" }}>
      {/* Navbar */}
      <nav style={{ 
        height: "70px", borderBottom: "1px solid rgba(255,255,255,0.05)", display: "flex", 
        alignItems: "center", justifyContent: "space-between", padding: "0 40px",
        position: "sticky", top: 0, background: "rgba(2, 6, 23, 0.8)", backdropFilter: "blur(12px)", zIndex: 10 
      }}>
        <div style={{ display: "flex", alignItems: "center", gap: "15px" }}>
          <div style={{ background: "linear-gradient(135deg, #3b82f6, #2563eb)", width: "32px", height: "32px", borderRadius: "8px" }} />
          <h1 style={{ fontSize: "20px", fontWeight: 900, letterSpacing: "-0.5px" }}>TWSTOCK <span style={{ color: "#3b82f6" }}>PRO</span></h1>
        </div>
        <div style={{ display: "flex", gap: "20px", alignItems: "center", fontSize: "13px", color: "#64748b" }}>
          <span>市場狀態: <b style={{ color: "#10b981" }}>{marketInfo.status}</b></span>
          <span>更新: {marketInfo.update}</span>
          <button 
            onClick={() => fetchData(true)}
            style={{ background: "#1e293b", color: "#fff", border: "1px solid #334155", padding: "8px 16px", borderRadius: "8px", cursor: "pointer", fontWeight: 600 }}
          >
            {loading ? "更新中..." : "強制刷新"}
          </button>
        </div>
      </nav>

      <div style={{ maxWidth: "1400px", margin: "0 auto", padding: "30px", display: "grid", gridTemplateColumns: "300px 1fr", gap: "30px" }}>
        
        {/* Sidebar */}
        <aside style={{ display: "flex", flexDirection: "column", gap: "25px" }}>
          <div style={{ background: "#0f172a", padding: "20px", borderRadius: "20px", border: "1px solid rgba(255,255,255,0.05)" }}>
            <label style={{ fontSize: "12px", color: "#64748b", fontWeight: 800, textTransform: "uppercase", marginBottom: "15px", display: "block" }}>搜尋與篩選</label>
            <input 
              placeholder="輸入代碼或名稱..."
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              style={{ width: "100%", background: "#020617", border: "1px solid #1e293b", padding: "12px", borderRadius: "10px", color: "#fff", marginBottom: "15px" }}
            />
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "8px" }}>
              {PRICE_CATEGORIES.map(c => (
                <button 
                  key={c.key}
                  onClick={() => setSelectedCategory(c.key)}
                  style={{ 
                    padding: "10px", borderRadius: "8px", cursor: "pointer", fontSize: "13px", fontWeight: 600,
                    background: selectedCategory === c.key ? "#3b82f6" : "#1e293b",
                    border: "none", color: "#fff", transition: "0.2s"
                  }}
                >{c.label}</button>
              ))}
            </div>
          </div>
        </aside>

        {/* Main Content */}
        <main style={{ display: "flex", flexDirection: "column", gap: "30px" }}>
          
          {/* Focused Analysis Card */}
          {focusedStock && (
            <div style={{ 
              background: "linear-gradient(145deg, #0f172a 0%, #1e293b 100%)", padding: "30px", 
              borderRadius: "24px", border: "1px solid rgba(59, 130, 246, 0.2)", position: "relative",
              boxShadow: "0 20px 50px rgba(0,0,0,0.3)"
            }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: "25px" }}>
                <div>
                  <div style={{ display: "flex", alignItems: "center", gap: "10px", marginBottom: "8px" }}>
                    <Badge type={focusedStock.operation_rating || ""}>評級 {focusedStock.operation_rating}</Badge>
                    <span style={{ fontSize: "14px", color: "#64748b" }}>{focusedStock.market}</span>
                  </div>
                  <h2 style={{ fontSize: "36px", fontWeight: 900 }}>{focusedStock.symbol} {focusedStock.name}</h2>
                </div>
                <div style={{ textAlign: "right" }}>
                  <div style={{ fontSize: "42px", fontWeight: 900, color: focusedStock.change >= 0 ? "#f87171" : "#4ade80" }}>{focusedStock.price}</div>
                  <div style={{ fontWeight: 700, fontSize: "18px", color: focusedStock.change >= 0 ? "#f87171" : "#4ade80" }}>
                    {focusedStock.change > 0 ? "+" : ""}{focusedStock.change} ({focusedStock.change_percent}%)
                  </div>
                </div>
              </div>

              <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: "15px", marginBottom: "25px" }}>
                <Metric label="進場參考" value={focusedStock.entry_price || "-"} color="#3b82f6" />
                <Metric label="預期目標" value={focusedStock.target_price || "-"} color="#10b981" />
                <Metric label="防守停損" value={focusedStock.stop_loss || "-"} color="#ef4444" />
                <Metric label="風險報酬" value={focusedStock.risk_reward || "-"} color="#f59e0b" />
              </div>

              <div style={{ background: "rgba(0,0,0,0.2)", padding: "20px", borderRadius: "16px", border: "1px solid rgba(255,255,255,0.05)" }}>
                <div style={{ color: "#3b82f6", fontWeight: 800, fontSize: "14px", marginBottom: "10px" }}>✦ 技術面分析結論</div>
                <p style={{ lineHeight: "1.8", color: "#cbd5e1" }}>{focusedStock.technical_comment || focusedStock.reason}</p>
              </div>
            </div>
          )}

          {/* Table List */}
          <div style={{ background: "#0f172a", borderRadius: "24px", padding: "20px", border: "1px solid rgba(255,255,255,0.05)" }}>
            <table style={{ width: "100%", borderCollapse: "separate", borderSpacing: "0 8px" }}>
              <thead>
                <tr style={{ color: "#64748b", fontSize: "13px", textAlign: "left" }}>
                  <th style={{ padding: "10px 20px" }}>股票代號</th>
                  <th style={{ padding: "10px" }}>目前股價</th>
                  <th style={{ padding: "10px" }}>漲跌幅</th>
                  <th style={{ padding: "10px" }}>技術訊號</th>
                  <th style={{ padding: "10px" }}>更新時間</th>
                </tr>
              </thead>
              <tbody>
                {stocks.map((s) => (
                  <tr 
                    key={s.symbol} 
                    onClick={() => setFocusedStock(s as FocusedStock)}
                    style={{ 
                      cursor: "pointer", background: focusedStock?.symbol === s.symbol ? "rgba(59, 130, 246, 0.1)" : "rgba(255,255,255,0.02)",
                      transition: "0.2s"
                    }}
                  >
                    <td style={{ padding: "15px 20px", borderRadius: "12px 0 0 12px", fontWeight: 700 }}>{s.symbol} {s.name}</td>
                    <td style={{ padding: "15px", fontWeight: 800 }}>{s.price}</td>
                    <td style={{ padding: "15px", color: s.change >= 0 ? "#f87171" : "#4ade80", fontWeight: 700 }}>
                      {s.change > 0 ? "+" : ""}{s.change_percent}%
                    </td>
                    <td style={{ padding: "15px" }}>
                      <span style={{ fontSize: "13px", background: "rgba(255,255,255,0.05)", padding: "4px 10px", borderRadius: "6px" }}>{s.signal || "觀察"}</span>
                    </td>
                    <td style={{ padding: "15px", borderRadius: "0 12px 12px 0", fontSize: "12px", color: "#64748b" }}>{s.update_time}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </main>
      </div>
    </div>
  );
}
