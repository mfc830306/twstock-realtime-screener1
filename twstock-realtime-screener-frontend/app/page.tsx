"use client";
import { useEffect, useState } from "react";

export default function Home() {
  const API = "https://twstock-realtime-screener1.onrender.com";

  const [stocks, setStocks] = useState<any[]>([]);
  const [search, setSearch] = useState("");

  useEffect(() => {
    fetch(`${API}/stocks`)
      .then(res => res.json())
      .then(data => {
        console.log("API資料:", data);
        setStocks(data.stocks || []);
      })
      .catch(err => {
        console.error("錯誤:", err);
      });
  }, []);

  const filtered = stocks.filter(s =>
    s.name?.includes(search) || s.symbol?.includes(search)
  );

  return (
    <div style={{ background: "#0b1f3a", color: "white", minHeight: "100vh", padding: 20 }}>
      <h1>台股最穩版本</h1>

      <input
        placeholder="搜尋股票"
        value={search}
        onChange={(e) => setSearch(e.target.value)}
        style={{ padding: 10, width: "100%", marginBottom: 20 }}
      />

      <div>股票數量：{filtered.length}</div>

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
  );
}
