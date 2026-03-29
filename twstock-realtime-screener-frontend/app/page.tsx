"use client";

import { useEffect, useMemo, useState } from "react";

type Stock = {
  symbol: string;
  name: string;
  price: number;
  change_percent: number;
  volume?: number;
  score?: number;
  signal?: string;
  reason?: string;
  entry_price?: string;
  target_price?: string;
  stop_loss?: string;
};

type ApiResponse = {
  success: boolean;
  market_status?: string;
  data_date?: string;
  last_update?: string;
  stocks?: Stock[];
  top_recommendations?: Stock[];
};

const BACKEND_URL = "https://twstock-realtime-screener1.onrender.com/stocks";

export default function Home() {
  const [stocks, setStocks] = useState<Stock[]>([]);
  const [topStocks, setTopStocks] = useState<Stock[]>([]);
  const [search, setSearch] = useState("");
  const [category, setCategory] = useState("all");
  const [sort, setSort] = useState("score");

  const [marketStatus, setMarketStatus] = useState("-");
  const [dataDate, setDataDate] = useState("-");
  const [lastUpdate, setLastUpdate] = useState("-");

  useEffect(() => {
    fetchData();
  }, []);

  async function fetchData() {
    const res = await fetch(BACKEND_URL);
    const data: ApiResponse = await res.json();

    setStocks(data.stocks || []);
    setTopStocks(data.top_recommendations || []);
    setMarketStatus(data.market_status || "-");
    setDataDate(data.data_date || "-");
    setLastUpdate(data.last_update || "-");
  }

  const categories = [
    { label: "全部", value: "all" },
    { label: "0-50", value: "0-50" },
    { label: "50-100", value: "50-100" },
    { label: "100-200", value: "100-200" },
    { label: "200-500", value: "200-500" },
    { label: "500+", value: "500-999999" },
  ];

  const filtered = useMemo(() => {
    let result = [...stocks];

    if (category !== "all") {
      const [min, max] = category.split("-").map(Number);
      result = result.filter((s) => s.price >= min && s.price <= max);
    }

    if (search) {
      result = result.filter(
        (s) =>
          s.symbol.includes(search) ||
          s.name.includes(search)
      );
    }

    if (sort === "up") {
      result.sort((a, b) => b.change_percent - a.change_percent);
    } else if (sort === "down") {
      result.sort((a, b) => a.change_percent - b.change_percent);
    } else {
      result.sort((a, b) => (b.score || 0) - (a.score || 0));
    }

    return result;
  }, [stocks, search, category, sort]);

  return (
    <main className="page">

      {/* 🔥 最上方 Header（新增） */}
      <div className="top-header">
        <div className="top-header-inner">

          <div className="top-left">
            <span className="logo">TW/STOCK</span>
            <span className="divider">·</span>
            <span className="subtitle">即時選股系統</span>
          </div>

          <div className="top-right">
            <span className="status-badge">● {marketStatus}</span>
            <span>資料日期：{dataDate}</span>
            <span>最後更新：{lastUpdate}</span>
          </div>

        </div>
      </div>

      <div className="container">

        <h1 className="title">台股即時選股系統</h1>

        {/* 上方左右 */}
        <div className="top-layout">

          {/* 左 */}
          <div className="panel left-panel">
            <h2>價格分類</h2>

            <div className="category-list">
              {categories.map((c) => (
                <button
                  key={c.value}
                  className={`category-btn ${category === c.value ? "active" : ""}`}
                  onClick={() => setCategory(c.value)}
                >
                  {c.label}
                </button>
              ))}
            </div>

            <input
              className="search-input"
              placeholder="搜尋股票..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />

            <div className="sort-wrap">
              <button onClick={() => setSort("score")}>推薦</button>
              <button onClick={() => setSort("up")}>漲幅</button>
              <button onClick={() => setSort("down")}>跌幅</button>
            </div>
          </div>

          {/* 右 */}
          <div className="panel right-panel">
            <h2>🔥 推薦10檔</h2>

            <div className="recommend-list">
              {topStocks.map((s) => (
                <div key={s.symbol} className="recommend-card">
                  <div className="recommend-title">
                    {s.symbol} {s.name}（{s.score}）
                  </div>

                  <div className="recommend-reason">{s.reason}</div>

                  <div className="recommend-extra">
                    進場 {s.entry_price} ｜ 目標 {s.target_price} ｜ 停損 {s.stop_loss}
                  </div>
                </div>
              ))}
            </div>
          </div>

        </div>

        {/* 下方列表 */}
        <div className="panel list-panel">
          <h2>股票列表 ({filtered.length})</h2>

          <div className="table-wrap">
            <table className="stock-table">
              <thead>
                <tr>
                  <th>代號</th>
                  <th>名稱</th>
                  <th>股價</th>
                  <th>漲跌%</th>
                  <th>成交量</th>
                  <th>分數</th>
                </tr>
              </thead>

              <tbody>
                {filtered.map((s) => (
                  <tr key={s.symbol}>
                    <td>{s.symbol}</td>
                    <td>{s.name}</td>
                    <td>{s.price}</td>
                    <td>{s.change_percent}%</td>
                    <td>{s.volume}</td>
                    <td>{s.score}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

        </div>

      </div>
    </main>
  );
}
