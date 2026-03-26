"use client";
import { useEffect, useState } from "react";

export default function Home() {
  const API = "https://twstock-realtime-screener1.onrender.com";

  const [stocks, setStocks] = useState<any[]>([]);
  const [top, setTop] = useState<any[]>([]);
  const [search, setSearch] = useState("");

  useEffect(() => {
    fetch(`${API}/stocks`)
      .then(res => res.json())
      .then(data => {
        setStocks(data.stocks);

        const sorted = [...data.stocks].sort((a, b) => b.score - a.score);
        setTop(sorted.slice(0, 10));
      });
  }, []);

  const filtered = stocks.filter(s =>
    s.name.includes(search) || s.symbol.includes(search)
  );

  return (
    <div style={{ background: "#0b1f3a", color: "white", minHeight: "100vh", padding: 20 }}>
      <h1 style={{ fontSize: 28 }}>台股選股系統</h1>

      <input
        placeholder="搜尋股票..."
        value={search}
        onChange={(e) => setSearch(e.target.value)}
        style={{ padding: 10, width: "100%", marginBottom: 20 }}
      />

      <div style={{ display: "flex", gap: 20 }}>

        {/* 左 */}
        <div style={{ width: "30%" }}>
          <h2>🔥 TOP10</h2>
          {top.map((s, i) => (
            <div key={i} style={{ marginBottom: 10 }}>
              {s.symbol} {s.name} ({s.score})
            </div>
          ))}
        </div>

        {/* 右 */}
        <div style={{ width: "70%" }}>
          <h2>全部股票 ({filtered.length})</h2>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(4,1fr)", gap: 10 }}>
            {filtered.map((s, i) => (
              <div key={i} style={{ background: "#132b4f", padding: 10 }}>
                <div>{s.symbol}</div>
                <div>{s.name}</div>
                <div>{s.price}</div>
                <div>{s.change_percent}%</div>
              </div>
            ))}
          </div>
        </div>

      </div>
    </div>
  );
}
