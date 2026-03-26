"use client";
import { useEffect, useState } from "react";

export default function Home() {
  const [stocks, setStocks] = useState<any[]>([]);
  const [filtered, setFiltered] = useState<any[]>([]);
  const [top, setTop] = useState<any[]>([]);
  const [priceFilter, setPriceFilter] = useState<string>("全部");
  const [search, setSearch] = useState("");

  const API = "https://你的render網址";

  useEffect(() => {
    fetch(`${API}/stocks?market=全部`)
      .then(res => res.json())
      .then(data => {
        setStocks(data.stocks || []);
        setFiltered(data.stocks || []);

        const sorted = [...(data.stocks || [])].sort((a, b) => (b.score || 0) - (a.score || 0));
        setTop(sorted.slice(0, 10));
      });
  }, []);

  useEffect(() => {
    let result = [...stocks];

    // 價位分類
    if (priceFilter !== "全部") {
      result = result.filter(s => {
        const p = s.price || 0;
        if (priceFilter === "10以下") return p < 10;
        if (priceFilter === "10-50") return p >= 10 && p < 50;
        if (priceFilter === "50-100") return p >= 50 && p < 100;
        if (priceFilter === "100-500") return p >= 100 && p < 500;
        if (priceFilter === "500以上") return p >= 500;
      });
    }

    // 搜尋
    if (search) {
      result = result.filter(s =>
        s.name?.includes(search) || s.symbol?.includes(search)
      );
    }

    setFiltered(result);
  }, [priceFilter, search, stocks]);

  return (
    <div style={{ background: "#0b1f3a", color: "white", minHeight: "100vh", padding: 20 }}>
      <h1 style={{ fontSize: 28, marginBottom: 20 }}>📊 台股即時選股系統</h1>

      {/* 搜尋 */}
      <input
        placeholder="輸入股票名稱或代號..."
        value={search}
        onChange={(e) => setSearch(e.target.value)}
        style={{
          padding: 10,
          width: "100%",
          marginBottom: 20,
          borderRadius: 8,
          border: "none"
        }}
      />

      {/* 價位分類 */}
      <div style={{ marginBottom: 20 }}>
        {["全部", "10以下", "10-50", "50-100", "100-500", "500以上"].map(p => (
          <button
            key={p}
            onClick={() => setPriceFilter(p)}
            style={{
              marginRight: 10,
              padding: "8px 12px",
              borderRadius: 6,
              border: "none",
              background: priceFilter === p ? "#3b82f6" : "#1e3a5f",
              color: "white",
              cursor: "pointer"
            }}
          >
            {p}
          </button>
        ))}
      </div>

      {/* 左右分欄 */}
      <div style={{ display: "flex", gap: 20 }}>
        
        {/* 左：推薦 */}
        <div style={{ width: "30%" }}>
          <h2>🔥 推薦TOP10</h2>
          {top.map((s, i) => (
            <div key={i} style={{
              background: "#132b4f",
              padding: 10,
              marginBottom: 10,
              borderRadius: 8
            }}>
              <div>{s.symbol} {s.name}</div>
              <div>價格：{s.price}</div>
              <div>分數：{s.score}</div>
              <div style={{ color: "#22c55e" }}>{s.signal}</div>
            </div>
          ))}
        </div>

        {/* 右：全部股票 */}
        <div style={{ width: "70%" }}>
          <h2>📈 全部股票 ({filtered.length})</h2>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 10 }}>
            {filtered.map((s, i) => (
              <div key={i} style={{
                background: "#132b4f",
                padding: 10,
                borderRadius: 8
              }}>
                <div>{s.symbol}</div>
                <div>{s.name}</div>
                <div>💰 {s.price}</div>
                <div style={{
                  color: s.change_percent > 0 ? "#22c55e" : "#ef4444"
                }}>
                  {s.change_percent}%
                </div>
              </div>
            ))}
          </div>
        </div>

      </div>
    </div>
  );
}
