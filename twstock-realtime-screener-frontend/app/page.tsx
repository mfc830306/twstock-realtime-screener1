"use client";

import { useEffect, useState, useMemo } from "react";

type Stock = {
  market: string;
  symbol: string;
  name: string;
  price: number;
  change: number;
  change_percent: number;
  volume: number;
  score: number;
};

const BACKEND_URL = "https://twstock-realtime-screener1.onrender.com/stocks";

export default function Page() {
  const [stocks, setStocks] = useState<Stock[]>([]);
  const [recommend, setRecommend] = useState<Stock[]>([]);
  const [category, setCategory] = useState("all");
  const [search, setSearch] = useState("");

  useEffect(() => {
    fetch(BACKEND_URL)
      .then(res => res.json())
      .then(data => {
        setStocks(data.stocks || []);
        setRecommend(data.recommend || []);
      });
  }, []);

  // 🔥 價格分類
  const filteredStocks = useMemo(() => {
    let list = stocks;

    if (category !== "all") {
      const [min, max] = category.split("-").map(Number);
      list = list.filter(s => s.price >= min && s.price < max);
    }

    if (search) {
      list = list.filter(s =>
        s.symbol.includes(search) || s.name.includes(search)
      );
    }

    return list;
  }, [stocks, category, search]);

  return (
    <div>
      {/* 🔍 搜尋 */}
      <input
        placeholder="搜尋股票"
        value={search}
        onChange={(e) => setSearch(e.target.value)}
      />

      {/* 📊 價格分類 */}
      <div>
        {["all", "0-10", "10-50", "50-100", "100-200", "200-500", "500-1000"].map(c => (
          <button key={c} onClick={() => setCategory(c)}>
            {c}
          </button>
        ))}
      </div>

      {/* ⭐ 推薦 */}
      <h3>推薦10檔</h3>
      <div>
        {recommend.map(s => (
          <div key={s.symbol}>
            {s.symbol} {s.name} {s.price} ({s.change_percent}%)
          </div>
        ))}
      </div>

      {/* 📋 股票列表 */}
      <h3>股票列表</h3>
      <div>
        {filteredStocks.map(s => (
          <div key={s.symbol}>
            [{s.market}] {s.symbol} {s.name} {s.price} ({s.change_percent}%)
          </div>
        ))}
      </div>
    </div>
  );
}
