"use client";
import { useState } from "react";

export default function Home() {
  const [stocks, setStocks] = useState("");
  const [results, setResults] = useState<any[]>([]);

  const fetchData = async () => {
    const res = await fetch(
      "https://twstock-realtime-screener1.onrender.com/scan",
      {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          symbols: stocks.trim() ? stocks.split(",") : [],
        }),
      }
    );

    const data = await res.json();
    setResults(data);
  };

  return (
    <div style={{ padding: 30 }}>
      <h1>🔥 台股選股系統（升級版）</h1>

      <input
        style={{ width: 300, padding: 10 }}
        placeholder="輸入股票代碼"
        value={stocks}
        onChange={(e) => setStocks(e.target.value)}
      />

      <button onClick={fetchData}>開始選股</button>

      <table border={1} style={{ marginTop: 20 }}>
        <thead>
          <tr>
            <th>代碼</th>
            <th>價格</th>
            <th>訊號</th>
            <th>進場</th>
            <th>停損</th>
            <th>出場</th>
          </tr>
        </thead>
        <tbody>
          {results.map((s, i) => {
            const entry = s.price;
            const stop = (s.price * 0.97).toFixed(2);
            const target = (s.price * 1.05).toFixed(2);

            return (
              <tr key={i}>
                <td>{s.symbol}</td>
                <td>{s.price}</td>
                <td>{s.signal}</td>
                <td>{entry}</td>
                <td style={{ color: "red" }}>{stop}</td>
                <td style={{ color: "green" }}>{target}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
