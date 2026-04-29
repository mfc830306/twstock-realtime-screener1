"use client";

import { useEffect, useState, useCallback } from "react";

// --- 類型定義 (保持不變) ---
type Stock = {
  market?: string; symbol: string; name: string; price: number;
  change: number; change_percent: number; volume?: number; 
  score?: number; recommendation_score?: number; 
  signal?: string; trend_type?: string; reason?: string; 
  technical_comment?: string; operation_rating?: string;
  operation_bias?: string; operation_style?: string; 
  strategy_action?: string; entry_price?: string; 
  target_price?: string; stop_loss?: string;
  risk_reward?: string; risk_note?: string; 
  update_time?: string; analysis_source?: string;
  book_selection_score?: number; book_market_regime?: string;
  book_selection_comment?: string;
};

type ApiResponse = {
  success: boolean; market_status?: string; data_date?: string; 
  last_update?: string; total?: number; all_total?: number;
  stocks: Stock[]; recommendations?: Stock[];
  categories?: { key: string; label: string; count: number }[];
  focused_stock?: Stock | null;
};

const BACKEND_BASE = "https://twstock-realtime-screener1.onrender.com/stocks";
const ITEMS_PER_PAGE = 20;

export default function PremiumScreener() {
  const [stocks, setStocks] = useState<Stock[]>([]);
  const [loading, setLoading] = useState(false);
  const [searchTerm, setSearchTerm] = useState("");
  const [selectedCategory, setSelectedCategory] = useState("all");
  const [currentPage, setCurrentPage] = useState(1);
  const [totalItems, setTotalItems] = useState(0);
  const [focusedStock, setFocusedStock] = useState<Stock | null>(null);
  const [marketInfo, setMarketInfo] = useState({ status: "-", update: "-", date: "-", total: 0 });

  const fetchData = useCallback(async (force = false) => {
    setLoading(true);
    try {
      const offset = (currentPage - 1) * ITEMS_PER_PAGE;
      const params = new URLSearchParams({
        limit: ITEMS_PER_PAGE.toString(),
        offset: offset.toString(),
        price_range: selectedCategory,
        q: searchTerm,
        sort_by: "recommendation_score",
        sort_dir: "desc"
      });
      if (force) params.set("force_refresh", "true");

      const res = await fetch(`${BACKEND_BASE}?${params.toString()}`);
      const data: ApiResponse = await res.json();
      
      if (data.success) {
        setStocks(data.stocks);
        setTotalItems(data.total || 0);
        setMarketInfo({
          status: data.market_status || "-",
          update: data.last_update || "-",
          date: data.data_date || "-",
          total: data.all_total || 0
        });
        if (data.focused_stock) setFocusedStock(data.focused_stock);
        else if (data.stocks.length > 0 && currentPage === 1) setFocusedStock(data.stocks[0]);
      }
    } catch (err) {
      console.error("API Error:", err);
    } finally {
      setLoading(false);
    }
  }, [currentPage, selectedCategory, searchTerm]);

  useEffect(() => { fetchData(); }, [fetchData]);

  // --- 質感輔助組件 ---
  const InfoTag = ({ label, value, highlight = false }: { label: string, value: any, highlight?: boolean }) => (
    <div style={{ display: "flex", flexDirection: "column", gap: "4px" }}>
      <div style={{ fontSize: "12px", color: "#a1a1aa", fontWeight: 500 }}>{label}</div>
      <div style={{ fontSize: "16px", fontWeight: 700, color: highlight ? "#fafafa" : "#e4e4e7" }}>{value || "-"}</div>
    </div>
  );

  return (
    // 使用更柔和的暗色系：背景 #09090b (Zinc-950)
    <div style={{ minHeight: "100vh", background: "#09090b", color: "#fafafa", fontFamily: "'Inter', -apple-system, BlinkMacSystemFont, sans-serif" }}>
      
      {/* 頂部導航：毛玻璃效果與細緻分隔線 */}
      <header style={{ 
        height: "64px", borderBottom: "1px solid #27272a", display: "flex", alignItems: "center", 
        justifyContent: "space-between", padding: "0 32px", background: "rgba(9, 9, 11, 0.7)", 
        backdropFilter: "blur(12px)", position: "sticky", top: 0, zIndex: 100 
      }}>
        <div style={{ display: "flex", alignItems: "center", gap: "12px" }}>
          <div style={{ width: "24px", height: "24px", background: "linear-gradient(135deg, #3b82f6, #60a5fa)", borderRadius: "6px" }} />
          <span style={{ fontWeight: 800, fontSize: "16px", letterSpacing: "0.5px" }}>TW STOCK SCREENER</span>
        </div>
        <div style={{ display: "flex", gap: "20px", alignItems: "center", fontSize: "13px" }}>
          <div style={{ display: "flex", gap: "8px", color: "#a1a1aa" }}>
            <span>{marketInfo.date}</span>
            <span>•</span>
            <span style={{ color: marketInfo.status.includes("開盤") ? "#10b981" : "#a1a1aa" }}>{marketInfo.status}</span>
          </div>
          <button onClick={() => fetchData(true)} style={{ 
            background: "#ffffff", color: "#09090b", border: "none", padding: "6px 16px", 
            borderRadius: "99px", cursor: "pointer", fontWeight: 600, fontSize: "13px", transition: "all 0.2s" 
          }}>
            {loading ? "同步中..." : "同步數據"}
          </button>
        </div>
      </header>

      <div style={{ maxWidth: "1400px", margin: "0 auto", padding: "32px", display: "grid", gridTemplateColumns: "260px 1fr", gap: "32px" }}>
        
        {/* 左側面板：極簡化，移除多餘框線 */}
        <aside style={{ display: "flex", flexDirection: "column", gap: "32px" }}>
          <div>
            <h3 style={{ fontSize: "12px", color: "#a1a1aa", fontWeight: 600, marginBottom: "16px", letterSpacing: "0.5px" }}>篩選條件</h3>
            <input 
              placeholder="搜尋代號或名稱..." 
              value={searchTerm} 
              onChange={e => { setSearchTerm(e.target.value); setCurrentPage(1); }}
              style={{ 
                width: "100%", background: "#18181b", border: "1px solid #27272a", padding: "12px 16px", 
                borderRadius: "12px", color: "#fafafa", marginBottom: "20px", outline: "none", fontSize: "14px",
                transition: "border-color 0.2s"
              }} 
              onFocus={(e) => e.target.style.borderColor = "#3b82f6"}
              onBlur={(e) => e.target.style.borderColor = "#27272a"}
            />
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "8px" }}>
              {["all", "0-50", "50-100", "100-200", "200-500", "500+"].map(cat => (
                <button key={cat} onClick={() => { setSelectedCategory(cat); setCurrentPage(1); }} style={{ 
                  padding: "10px", borderRadius: "8px", cursor: "pointer", fontSize: "13px", fontWeight: 500,
                  background: selectedCategory === cat ? "#3b82f6" : "#18181b",
                  color: selectedCategory === cat ? "#ffffff" : "#a1a1aa",
                  border: `1px solid ${selectedCategory === cat ? "#3b82f6" : "#27272a"}`,
                  transition: "all 0.2s"
                }}>
                  {cat === "all" ? "全部價格" : cat}
                </button>
              ))}
            </div>
          </div>

          <div style={{ padding: "20px", borderRadius: "16px", background: "linear-gradient(180deg, #18181b 0%, rgba(24,24,27,0) 100%)", border: "1px solid #27272a" }}>
            <div style={{ fontSize: "12px", color: "#a1a1aa", marginBottom: "8px" }}>符合策略標的</div>
            <div style={{ fontSize: "32px", fontWeight: 400, color: "#fafafa" }}>
              {totalItems} <span style={{ fontSize: "14px", color: "#52525b" }}>檔</span>
            </div>
          </div>
        </aside>

        {/* 右側主畫面 */}
        <main style={{ display: "flex", flexDirection: "column", gap: "32px" }}>
          
          {/* 重點展示卡片：移除生硬漸層，改用乾淨排版 */}
          {focusedStock && (
            <div style={{ background: "#18181b", padding: "32px", borderRadius: "24px", border: "1px solid #27272a" }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", borderBottom: "1px solid #27272a", paddingBottom: "24px", marginBottom: "24px" }}>
                <div>
                  <div style={{ display: "flex", gap: "8px", marginBottom: "12px" }}>
                    <span style={{ background: "rgba(250, 204, 21, 0.1)", color: "#facc15", padding: "4px 10px", borderRadius: "99px", fontSize: "12px", fontWeight: 600 }}>
                      評級 {focusedStock.operation_rating || "無"}
                    </span>
                    <span style={{ background: "#27272a", color: "#e4e4e7", padding: "4px 10px", borderRadius: "99px", fontSize: "12px", fontWeight: 500 }}>
                      {focusedStock.trend_type || "趨勢不明"}
                    </span>
                  </div>
                  <h2 style={{ fontSize: "32px", fontWeight: 700, letterSpacing: "-0.5px" }}>{focusedStock.symbol} {focusedStock.name}</h2>
                </div>
                <div style={{ textAlign: "right" }}>
                  <div style={{ fontSize: "40px", fontWeight: 700, color: focusedStock.change >= 0 ? "#ef4444" : "#10b981", lineHeight: 1 }}>
                    {focusedStock.price}
                  </div>
                  <div style={{ fontSize: "16px", fontWeight: 500, color: focusedStock.change >= 0 ? "#ef4444" : "#10b981", marginTop: "8px" }}>
                    {focusedStock.change > 0 ? "+" : ""}{focusedStock.change} ({focusedStock.change_percent}%)
                  </div>
                </div>
              </div>

              {/* 核心數據：改用無框線的整齊排列 */}
              <div style={{ display: "grid", gridTemplateColumns: "repeat(5, 1fr)", gap: "24px", marginBottom: "32px" }}>
                <InfoTag label="策略評分" value={focusedStock.book_selection_score} highlight />
                <InfoTag label="市場環境" value={focusedStock.book_market_regime} />
                <InfoTag label="進場價" value={focusedStock.entry_price} />
                <InfoTag label="目標價" value={focusedStock.target_price} />
                <InfoTag label="停損價" value={focusedStock.stop_loss} />
              </div>

              {/* AI 分析結論 */}
              <div style={{ background: "#09090b", padding: "20px 24px", borderRadius: "16px" }}>
                <div style={{ fontSize: "12px", color: "#a1a1aa", fontWeight: 600, marginBottom: "8px" }}>AI 策略解析</div>
                <p style={{ fontSize: "15px", lineHeight: "1.7", color: "#d4d4d8", margin: 0 }}>
                  {focusedStock.technical_comment || focusedStock.reason || "目前無詳細解析。"}
                </p>
              </div>
            </div>
          )}

          {/* 表格區塊：優化數字對齊與 Hover 質感 */}
          <div style={{ border: "1px solid #27272a", borderRadius: "16px", overflow: "hidden", background: "#18181b" }}>
            <table style={{ width: "100%", borderCollapse: "collapse" }}>
              <thead style={{ background: "#09090b", borderBottom: "1px solid #27272a" }}>
                <tr style={{ color: "#a1a1aa", fontSize: "13px", fontWeight: 500 }}>
                  <th style={{ padding: "16px 24px", textAlign: "left", width: "25%" }}>標的</th>
                  <th style={{ padding: "16px 24px", textAlign: "right" }}>現價</th>
                  <th style={{ padding: "16px 24px", textAlign: "right" }}>漲跌幅</th>
                  <th style={{ padding: "16px 24px", textAlign: "center" }}>策略評分</th>
                  <th style={{ padding: "16px 24px", textAlign: "center" }}>環境</th>
                  <th style={{ padding: "16px 24px", textAlign: "center" }}>訊號</th>
                </tr>
              </thead>
              <tbody style={{ fontSize: "14px" }}>
                {stocks.map(s => (
                  <tr 
                    key={s.symbol} 
                    onClick={() => setFocusedStock(s)} 
                    style={{ 
                      borderBottom: "1px solid #27272a", cursor: "pointer", 
                      background: focusedStock?.symbol === s.symbol ? "rgba(255,255,255,0.03)" : "transparent",
                      transition: "background 0.2s"
                    }}
                    onMouseEnter={(e) => e.currentTarget.style.background = "rgba(255,255,255,0.03)"}
                    onMouseLeave={(e) => e.currentTarget.style.background = focusedStock?.symbol === s.symbol ? "rgba(255,255,255,0.03)" : "transparent"}
                  >
                    <td style={{ padding: "16px 24px", fontWeight: 600, color: "#fafafa" }}>
                      {s.symbol} <span style={{ color: "#a1a1aa", fontWeight: 400, marginLeft: "4px" }}>{s.name}</span>
                    </td>
                    <td style={{ padding: "16px 24px", textAlign: "right", fontWeight: 500, color: "#fafafa" }}>{s.price}</td>
                    <td style={{ padding: "16px 24px", textAlign: "right", fontWeight: 500, color: s.change >= 0 ? "#ef4444" : "#10b981" }}>
                      {s.change > 0 ? "+" : ""}{s.change_percent}%
                    </td>
                    <td style={{ padding: "16px 24px", textAlign: "center", color: "#e4e4e7" }}>{s.book_selection_score || "-"}</td>
                    <td style={{ padding: "16px 24px", textAlign: "center", color: "#a1a1aa" }}>{s.book_market_regime || "-"}</td>
                    <td style={{ padding: "16px 24px", textAlign: "center" }}>
                      <span style={{ background: "#27272a", color: "#d4d4d8", padding: "4px 10px", borderRadius: "99px", fontSize: "12px" }}>
                        {s.signal || "-"}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>

            {/* 分頁器 */}
            <div style={{ padding: "16px 24px", display: "flex", justifyContent: "space-between", alignItems: "center", borderTop: "1px solid #27272a", background: "#09090b" }}>
              <span style={{ fontSize: "13px", color: "#a1a1aa" }}>
                顯示第 {(currentPage-1)*ITEMS_PER_PAGE+1} - {Math.min(currentPage*ITEMS_PER_PAGE, totalItems)} 筆，共 {totalItems} 筆
              </span>
              <div style={{ display: "flex", gap: "8px", alignItems: "center" }}>
                <button 
                  disabled={currentPage === 1} 
                  onClick={() => setCurrentPage(p => p - 1)} 
                  style={{ padding: "6px 12px", borderRadius: "8px", background: "transparent", color: currentPage === 1 ? "#52525b" : "#e4e4e7", border: `1px solid ${currentPage === 1 ? "#27272a" : "#3f3f46"}`, cursor: currentPage === 1 ? "not-allowed" : "pointer" }}
                >
                  上一頁
                </button>
                <span style={{ fontSize: "14px", fontWeight: 500, margin: "0 8px", color: "#fafafa" }}>{currentPage}</span>
                <button 
                  disabled={currentPage * ITEMS_PER_PAGE >= totalItems} 
                  onClick={() => setCurrentPage(p => p + 1)} 
                  style={{ padding: "6px 12px", borderRadius: "8px", background: "transparent", color: currentPage * ITEMS_PER_PAGE >= totalItems ? "#52525b" : "#e4e4e7", border: `1px solid ${currentPage * ITEMS_PER_PAGE >= totalItems ? "#27272a" : "#3f3f46"}`, cursor: currentPage * ITEMS_PER_PAGE >= totalItems ? "not-allowed" : "pointer" }}
                >
                  下一頁
                </button>
              </div>
            </div>
          </div>
        </main>
      </div>
    </div>
  );
}
