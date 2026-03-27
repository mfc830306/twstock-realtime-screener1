"use client";

import { useEffect, useMemo, useState } from "react";

type Stock = {
  symbol: string;
  name: string;
  price: number;
  change_percent: number;
  volume?: number;
  score?: number;
  prev_close?: number;
  open?: number;
  high?: number;
  low?: number;
  update_time?: string;
};

const BACKEND_URL = "https://twstock-realtime-screener1.onrender.com/stocks";

export default function Home() {
  const [stocks, setStocks] = useState<Stock[]>([]);
  const [searchTerm, setSearchTerm] = useState("");
  const [selectedCategory, setSelectedCategory] = useState("all");
  const [rankType, setRankType] = useState<"up" | "down" | "volume">("up");

  useEffect(() => {
    fetch(BACKEND_URL)
      .then((res) => res.json())
      .then((data) => setStocks(data.stocks || []));
  }, []);

  const isETF = (s: Stock) =>
    s.symbol.startsWith("00") || s.name.includes("ETF");

  const searched = useMemo(() => {
    if (!searchTerm) return stocks;
    return stocks.filter(
      (s) =>
        s.symbol.includes(searchTerm) ||
        s.name.includes(searchTerm)
    );
  }, [stocks, searchTerm]);

  const filterCategory = (s: Stock) => {
    if (selectedCategory === "etf") return isETF(s);
    if (selectedCategory === "under10") return !isETF(s) && s.price < 10;
    if (selectedCategory === "10to30") return !isETF(s) && s.price >= 10 && s.price < 30;
    if (selectedCategory === "30to50") return !isETF(s) && s.price >= 30 && s.price < 50;
    if (selectedCategory === "50to100") return !isETF(s) && s.price >= 50 && s.price < 100;
    if (selectedCategory === "100to200") return !isETF(s) && s.price >= 100 && s.price < 200;
    if (selectedCategory === "200to500") return !isETF(s) && s.price >= 200 && s.price < 500;
    if (selectedCategory === "over500") return !isETF(s) && s.price >= 500;
    return true;
  };

  const filteredStocks = useMemo(() => {
    return searched
      .filter(filterCategory)
      .sort((a, b) => (b.score || 0) - (a.score || 0))
      .slice(0, 10);
  }, [searched, selectedCategory]);

  const top10 = useMemo(() => {
    return [...stocks]
      .sort((a, b) => (b.score || 0) - (a.score || 0))
      .slice(0, 10);
  }, [stocks]);

  const ranked = useMemo(() => {
    const arr = [...stocks];
    if (rankType === "up") return arr.sort((a, b) => b.change_percent - a.change_percent);
    if (rankType === "down") return arr.sort((a, b) => a.change_percent - b.change_percent);
    return arr.sort((a, b) => (b.volume || 0) - (a.volume || 0));
  }, [stocks, rankType]);

  const categories = [
    { key: "all", label: "全部" },
    { key: "etf", label: "ETF" },
    { key: "under10", label: "10元以下" },
    { key: "10to30", label: "10~30元" },
    { key: "30to50", label: "30~50元" },
    { key: "50to100", label: "50~100元" },
    { key: "100to200", label: "100~200元" },
    { key: "200to500", label: "200~500元" },
    { key: "over500", label: "500元以上" },
  ];

  return (
    <div className="container">

      {/* 搜尋 */}
      <input
        className="search"
        placeholder="搜尋股票..."
        value={searchTerm}
        onChange={(e) => setSearchTerm(e.target.value)}
      />

      {/* 分類 */}
      <div className="filter-bar">
        {categories.map((c) => (
          <button
            key={c.key}
            className="filter-btn"
            onClick={() => setSelectedCategory(c.key)}
          >
            {c.label}
          </button>
        ))}
      </div>

      <div className="layout">

        {/* 🔥 TOP10 */}
        <div>
          <h3>🔥 推薦TOP10</h3>
          {top10.map((s, i) => (
            <div key={i} className="card">
              <div>{s.symbol} {s.name}</div>
              <div>{s.price}</div>
              <div>{s.change_percent}%</div>
              <div>分數：{s.score}</div>
            </div>
          ))}
        </div>

        {/* 📊 排行 */}
        <div>
          <h3>📊 排行榜</h3>
          <button onClick={() => setRankType("up")}>漲幅</button>
          <button onClick={() => setRankType("down")}>跌幅</button>
          <button onClick={() => setRankType("volume")}>成交量</button>

          {ranked.slice(0, 10).map((s, i) => (
            <div key={i} className="card">
              {i + 1}. {s.symbol} {s.name} {s.change_percent}%
            </div>
          ))}
        </div>

        {/* 📈 主區 */}
        <div>
          <h3>股票 ({selectedCategory})</h3>

          <div className="grid">
            {filteredStocks.map((s, i) => (
              <div key={i} className="card">
                <div>{s.symbol} {s.name}</div>
                <div>{s.price}</div>
                <div>{s.change_percent}%</div>

                <div>成交量：{(s.volume || 0).toLocaleString()}</div>
                <div>更新：{s.update_time || "--"}</div>
              </div>
            ))}
          </div>
        </div>

      </div>
    </div>
  );
}
