"use client";

import { useEffect, useMemo, useState } from "react";

type Stock = {
  symbol: string;
  name: string;
  price: number;
  change: number;
  change_percent: number;
  volume: number;
  score: number;
  signal: string;
  entry_price: string;
  target_price: string;
  stop_loss: string;
};

type ApiResponse = {
  success: boolean;
  market_status: string;
  data_date: string;
  last_update: string;
  total: number;
  stocks: Stock[];
  source: string;
};

const BACKEND_URL = "https://twstock-realtime-screener1.onrender.com/stocks";

const priceRanges = [
  { key: "ALL", label: "全部" },
  { key: "0-50", label: "0~50" },
  { key: "50-100", label: "50~100" },
  { key: "100-200", label: "100~200" },
  { key: "200+", label: "200+" },
];

function inRange(price: number, range: string) {
  if (range === "ALL") return true;
  if (range === "0-50") return price < 50;
  if (range === "50-100") return price >= 50 && price < 100;
  if (range === "100-200") return price >= 100 && price < 200;
  if (range === "200+") return price >= 200;
  return true;
}

export default function Home() {
  const [stocks, setStocks] = useState<Stock[]>([]);
  const [marketStatus, setMarketStatus] = useState("");
  const [lastUpdate, setLastUpdate] = useState("");
  const [dataDate, setDataDate] = useState("");
  const [search, setSearch] = useState("");
  const [selectedRange, setSelectedRange] = useState("ALL");
  const [loading, setLoading] = useState(false);

  const [isMobile, setIsMobile] = useState(false);

  useEffect(() => {
    const check = () => setIsMobile(window.innerWidth < 768);
    check();
    window.addEventListener("resize", check);
    return () => window.removeEventListener("resize", check);
  }, []);

  const fetchStocks = async () => {
    setLoading(true);
    try {
      const res = await fetch(BACKEND_URL, { cache: "no-store" });
      const data: ApiResponse = await res.json();

      if (data.success) {
        setStocks(data.stocks || []);
        setMarketStatus(data.market_status);
        setLastUpdate(data.last_update);
        setDataDate(data.data_date);
      }
    } catch {
      console.log("API error");
    }
    setLoading(false);
  };

  useEffect(() => {
    fetchStocks();
    const timer = setInterval(fetchStocks, 30000);
    return () => clearInterval(timer);
  }, []);

  const filteredStocks = useMemo(() => {
    let result = stocks.filter((s) => inRange(s.price, selectedRange));

    if (search.trim()) {
      result = result.filter(
        (s) =>
          s.symbol.includes(search) ||
          s.name.includes(search)
      );
    }

    return result.sort((a, b) => b.score - a.score);
  }, [stocks, selectedRange, search]);

  const top10 = filteredStocks.slice(0, 10);

  return (
    <main
      style={{
        minHeight: "100vh",
        background: "#031f36",
        color: "#fff",
        padding: "16px",
      }}
    >
      <div
        style={{
          display: "grid",
          gridTemplateColumns: isMobile ? "1fr" : "260px 1fr",
          gap: "20px",
        }}
      >
        {/* 左側 */}
        <aside>
          <div style={{ marginBottom: "20px" }}>
            <div style={{ fontSize: "20px", fontWeight: 800 }}>
              台股智慧選股
            </div>
          </div>

          <div style={{ marginBottom: "20px" }}>
            <div>狀態：{marketStatus}</div>
            <div>更新：{lastUpdate}</div>
            <div>日期：{dataDate}</div>
          </div>

          <div>
            {priceRanges.map((item) => (
              <button
                key={item.key}
                onClick={() => setSelectedRange(item.key)}
                style={{
                  display: "block",
                  width: "100%",
                  marginBottom: "10px",
                  padding: "10px",
                  background:
                    selectedRange === item.key ? "#18b9d4" : "#12395c",
                  color: "#fff",
                  border: "none",
                  borderRadius: "8px",
                }}
              >
                {item.label}
              </button>
            ))}
          </div>
        </aside>

        {/* 右側 */}
        <section>
          <div style={{ marginBottom: "20px" }}>
            <input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="搜尋股票"
              style={{
                padding: "10px",
                width: "260px",
                borderRadius: "8px",
                border: "none",
              }}
            />
          </div>

          {loading && <div style={{ marginBottom: "10px" }}>資料更新中...</div>}

          {/* 推薦 */}
          <div style={{ marginBottom: "20px" }}>
            <h3>推薦前10</h3>
            {top10.map((s) => (
              <div key={s.symbol}>
                {s.symbol} {s.name} - {s.price}
              </div>
            ))}
          </div>

          {/* 表格 */}
          <div style={{ overflowX: "auto" }}>
            <div style={{ minWidth: isMobile ? "700px" : "100%" }}>
              <div style={{ fontWeight: "bold", marginBottom: "10px" }}>
                股票列表（{filteredStocks.length}）
              </div>

              {filteredStocks.map((s) => (
                <div
                  key={s.symbol}
                  style={{
                    padding: "10px",
                    borderBottom: "1px solid #1a3b5d",
                  }}
                >
                  {s.symbol} {s.name}　
                  價格:{s.price}　
                  分數:{s.score}　
                  進場:{s.entry_price}　
                  出場:{s.target_price}　
                  停損:{s.stop_loss}
                </div>
              ))}
            </div>
          </div>
        </section>
      </div>
    </main>
  );
}
