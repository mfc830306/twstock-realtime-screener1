"use client";

import { useEffect, useMemo, useState } from "react";

type Stock = {
  symbol: string;
  name: string;
  price: number;
  change: number;
  change_percent: number;
  volume?: number;
  score?: number;
  signal?: string;
  reason?: string;
  entry_price?: string;
  target_price?: string;
  stop_loss?: string;
};

const BACKEND_URL = "https://twstock-realtime-screener1.onrender.com/stocks";

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

function getCategory(price: number): CategoryKey {
  if (price < 50) return "0-50";
  if (price < 100) return "50-100";
  if (price < 200) return "100-200";
  if (price < 500) return "200-500";
  return "500+";
}

export default function Home() {
  const [stocks, setStocks] = useState<Stock[]>([]);
  const [search, setSearch] = useState("");
  const [category, setCategory] = useState<CategoryKey>("all");
  const [rank, setRank] = useState<RankType>("recommend");
  const [loading, setLoading] = useState(false);

  async function fetchStocks() {
    setLoading(true);
    const res = await fetch(BACKEND_URL);
    const data = await res.json();
    setStocks(data.stocks || []);
    setLoading(false);
  }

  useEffect(() => {
    fetchStocks();
  }, []);

  const filtered = useMemo(() => {
    let list = [...stocks];

    if (category !== "all") {
      list = list.filter((s) => getCategory(s.price) === category);
    }

    if (search) {
      list = list.filter(
        (s) =>
          s.symbol.includes(search) ||
          s.name.includes(search)
      );
    }

    if (rank === "up") list.sort((a, b) => b.change_percent - a.change_percent);
    if (rank === "down") list.sort((a, b) => a.change_percent - b.change_percent);
    if (rank === "recommend") list.sort((a, b) => (b.score || 0) - (a.score || 0));

    return list;
  }, [stocks, category, search, rank]);

  const recommend = [...stocks]
    .sort((a, b) => (b.score || 0) - (a.score || 0))
    .slice(0, 10);

  const count = (key: CategoryKey) =>
    key === "all"
      ? stocks.length
      : stocks.filter((s) => getCategory(s.price) === key).length;

  // ⭐ 重點：統一外框
  const panelStyle: React.CSSProperties = {
    background: "linear-gradient(180deg, #0d2f63 0%, #0a2a57 100%)",
    border: "1px solid rgba(80,140,220,0.22)",
    borderRadius: "22px",
    padding: "24px",
    minHeight: "595px",
    boxShadow: "0 10px 28px rgba(0,0,0,0.12)",
  };

  return (
    <main style={{ background: "#08264d", minHeight: "100vh", color: "#fff" }}>

      {/* Header */}
      <div style={{
        display: "flex",
        justifyContent: "space-between",
        padding: "16px 32px",
        borderBottom: "1px solid rgba(255,255,255,0.1)"
      }}>
        <div style={{ fontSize: 28, fontWeight: 900, color: "#5ea4ff" }}>
          TWSTOCK - 即時選股系統
        </div>

        <button
          onClick={fetchStocks}
          style={{
            background: "#3c7ff1",
            border: "none",
            padding: "10px 16px",
            borderRadius: 10,
            color: "#fff",
            fontWeight: 700
          }}
        >
          {loading ? "更新中..." : "更新"}
        </button>
      </div>

      <div style={{ maxWidth: 1400, margin: "0 auto", padding: 24 }}>

        {/* 上半區 */}
        <div style={{ display: "grid", gridTemplateColumns: "360px 1fr", gap: 20 }}>

          {/* 左 */}
          <div style={panelStyle}>
            <h2 style={{ fontSize: 24, fontWeight: 900, marginBottom: 18 }}>價格分類</h2>

            <div style={{ display: "flex", flexWrap: "wrap", gap: 10, marginBottom: 16 }}>
              {PRICE_CATEGORIES.map((c) => (
                <button
                  key={c.key}
                  onClick={() => setCategory(c.key)}
                  style={{
                    background: category === c.key ? "#5ea4ff" : "#1e4f93",
                    border: "none",
                    padding: "10px 14px",
                    borderRadius: 12,
                    color: "#fff",
                    fontWeight: 700
                  }}
                >
                  {c.label} ({count(c.key)})
                </button>
              ))}
            </div>

            <input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="搜尋股票"
              style={{
                width: "100%",
                padding: 12,
                borderRadius: 10,
                border: "none",
                marginBottom: 16
              }}
            />

            <div style={{ display: "flex", gap: 10 }}>
              <button onClick={() => setRank("recommend")}>推薦</button>
              <button onClick={() => setRank("up")}>漲幅</button>
              <button onClick={() => setRank("down")}>跌幅</button>
            </div>
          </div>

          {/* 右 */}
          <div style={panelStyle}>
            <h2 style={{ fontSize: 24, fontWeight: 900, marginBottom: 18 }}>🔥 推薦10檔</h2>

            {recommend.map((s) => {
              const color = s.change >= 0 ? "#ff8d8d" : "#7fc3ff";

              return (
                <div key={s.symbol} style={{ marginBottom: 16 }}>
                  <div style={{ fontSize: 20, fontWeight: 900 }}>
                    {s.symbol} {s.name}
                  </div>

                  <div style={{ display: "flex", gap: 12, color }}>
                    <span>漲跌 {s.change > 0 ? "+" : ""}{s.change}</span>
                    <span>漲跌% {s.change_percent > 0 ? "+" : ""}{s.change_percent}%</span>
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        {/* 下方表格 */}
        <div style={{ marginTop: 24, ...panelStyle }}>
          <h2 style={{ marginBottom: 16 }}>股票列表 ({filtered.length})</h2>

          <table style={{ width: "100%" }}>
            <thead>
              <tr>
                <th>代號</th>
                <th>名稱</th>
                <th>股價</th>
                <th>漲跌</th>
                <th>漲跌%</th>
                <th>成交量</th>
              </tr>
            </thead>

            <tbody>
              {filtered.map((s) => {
                const color = s.change >= 0 ? "#ff8d8d" : "#7fc3ff";

                return (
                  <tr key={s.symbol}>
                    <td>{s.symbol}</td>
                    <td>{s.name}</td>
                    <td>{s.price}</td>

                    <td style={{ color }}>
                      {s.change > 0 ? "+" : ""}{s.change}
                    </td>

                    <td style={{ color }}>
                      {s.change_percent > 0 ? "+" : ""}{s.change_percent}%
                    </td>

                    <td>{s.volume}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>

      </div>
    </main>
  );
}
