"use client";

import { useEffect, useMemo, useRef, useState } from "react";

type Stock = {
  symbol: string;
  name: string;
  price: number;
  change: number;
  change_percent: number;
  volume: number;
  score: number;
  date: string;
  entry_price?: string;
  target_price?: string;
  stop_loss?: string;
};

const API_BASE = "https://你的-render後端.onrender.com";

const PRICE_RANGES = [
  { key: "0-50", label: "0~50", min: 0, max: 50 },
  { key: "50-100", label: "50~100", min: 50, max: 100 },
  { key: "100-200", label: "100~200", min: 100, max: 200 },
  { key: "200+", label: "200+", min: 200, max: 999999 },
];

function getMarketMode() {
  const now = new Date();
  const time = now.getHours() * 60 + now.getMinutes();

  if (time >= 9 * 60 && time <= 13 * 60 + 30) {
    return "live";
  }
  return "close";
}

export default function Home() {
  const [stocks, setStocks] = useState<Stock[]>([]);
  const [activeRange, setActiveRange] = useState("50-100");
  const [marketMode, setMarketMode] = useState("close");
  const [lastUpdated, setLastUpdated] = useState("");
  const [loading, setLoading] = useState(false);

  const timerRef = useRef<NodeJS.Timeout | null>(null);

  const selectedRange = useMemo(() => {
    return PRICE_RANGES.find(r => r.key === activeRange)!;
  }, [activeRange]);

  const fetchStocks = async () => {
    try {
      setLoading(true);

      const mode = getMarketMode();
      setMarketMode(mode);

      const url = `${API_BASE}/stocks?min_price=${selectedRange.min}&max_price=${selectedRange.max}&t=${Date.now()}`;

      const res = await fetch(url, { cache: "no-store" });
      const data = await res.json();

      if (data.success) {
        setStocks(data.stocks || []);
        setLastUpdated(new Date().toLocaleTimeString("zh-TW"));
      }
    } catch (err) {
      console.error("更新失敗", err);
    } finally {
      setLoading(false);
    }
  };

  // 🔥 控制更新頻率（核心）
  useEffect(() => {
    fetchStocks();

    if (timerRef.current) clearInterval(timerRef.current);

    const mode = getMarketMode();

    const interval = mode === "live" ? 3000 : 60000;

    timerRef.current = setInterval(fetchStocks, interval);

    return () => {
      if (timerRef.current) clearInterval(timerRef.current);
    };
  }, [activeRange]);

  return (
    <main style={{ display: "flex", minHeight: "100vh", background: "#061a2b", color: "white" }}>
      
      {/* 左側 */}
      <div style={{ width: "220px", padding: "20px", borderRight: "1px solid #333" }}>
        <h2>台股分類</h2>

        <div style={{ marginTop: "20px" }}>
          {PRICE_RANGES.map(r => (
            <div
              key={r.key}
              onClick={() => setActiveRange(r.key)}
              style={{
                padding: "10px",
                marginBottom: "10px",
                background: activeRange === r.key ? "#00bcd4" : "#123",
                cursor: "pointer",
                borderRadius: "6px"
              }}
            >
              {r.label}
            </div>
          ))}
        </div>

        <div style={{ marginTop: "30px" }}>
          <div>狀態：</div>
          <div style={{ fontWeight: "bold", marginTop: "5px" }}>
            {marketMode === "live"
              ? "🟢 盤中（準即時）"
              : "🔴 收盤（官方）"}
          </div>

          <div style={{ marginTop: "15px" }}>
            更新時間：
            <div>{lastUpdated || "-"}</div>
          </div>
        </div>
      </div>

      {/* 右側 */}
      <div style={{ flex: 1, padding: "20px" }}>
        <h2>股票列表</h2>

        {loading && <div>更新中...</div>}

        <table style={{ width: "100%", marginTop: "20px", borderCollapse: "collapse" }}>
          <thead>
            <tr style={{ background: "#123" }}>
              <th>代號</th>
              <th>名稱</th>
              <th>價格</th>
              <th>漲跌%</th>
              <th>成交量</th>
              <th>進場</th>
              <th>出場</th>
              <th>停損</th>
            </tr>
          </thead>
          <tbody>
            {stocks.map(s => (
              <tr key={s.symbol} style={{ borderBottom: "1px solid #333" }}>
                <td>{s.symbol}</td>
                <td>{s.name}</td>
                <td>{s.price}</td>
                <td style={{ color: s.change_percent > 0 ? "lime" : "red" }}>
                  {s.change_percent}%
                </td>
                <td>{s.volume}</td>
                <td>{s.entry_price}</td>
                <td>{s.target_price}</td>
                <td>{s.stop_loss}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </main>
  );
}
