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

const BACKEND_URL = "https://twstock-realtime-screener1.onrender.com/stocks";

export default function Home() {
  const [stocks, setStocks] = useState<Stock[]>([]);
  const [topStocks, setTopStocks] = useState<Stock[]>([]);
  const [search, setSearch] = useState("");
  const [priceFilter, setPriceFilter] = useState("all");
  const [sortType, setSortType] = useState("score");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [lastUpdate, setLastUpdate] = useState("");

  useEffect(() => {
    fetchStocks();
  }, []);

  async function fetchStocks() {
    try {
      setLoading(true);
      setError("");

      const res = await fetch(BACKEND_URL, { cache: "no-store" });
      const data = await res.json();

      if (!data.success) {
        throw new Error(data.message || "資料讀取失敗");
      }

      setStocks(data.stocks || []);
      setTopStocks(data.top_recommendations || []);
      setLastUpdate(data.last_update || "");
    } catch (err: any) {
      setError(err?.message || "讀取失敗");
      setStocks([]);
      setTopStocks([]);
    } finally {
      setLoading(false);
    }
  }

  const categories = [
    { label: "全部", value: "all" },
    { label: "0-50", value: "0-50" },
    { label: "50-100", value: "50-100" },
    { label: "100-200", value: "100-200" },
    { label: "200-500", value: "200-500" },
    { label: "500+", value: "500-999999" },
  ];

  const filteredStocks = useMemo(() => {
    let result = [...stocks];

    if (priceFilter !== "all") {
      const [min, max] = priceFilter.split("-").map(Number);
      result = result.filter((s) => s.price >= min && s.price <= max);
    }

    if (search.trim()) {
      const keyword = search.trim().toLowerCase();
      result = result.filter(
        (s) =>
          s.symbol.toLowerCase().includes(keyword) ||
          s.name.toLowerCase().includes(keyword)
      );
    }

    if (sortType === "up") {
      result.sort((a, b) => (b.change_percent || 0) - (a.change_percent || 0));
    } else if (sortType === "down") {
      result.sort((a, b) => (a.change_percent || 0) - (b.change_percent || 0));
    } else {
      result.sort((a, b) => (b.score || 0) - (a.score || 0));
    }

    return result;
  }, [stocks, search, priceFilter, sortType]);

  function getCategoryCount(value: string) {
    if (value === "all") return stocks.length;
    const [min, max] = value.split("-").map(Number);
    return stocks.filter((s) => s.price >= min && s.price <= max).length;
  }

  function formatNumber(value?: number) {
    if (value === undefined || value === null) return "-";
    return value.toLocaleString();
  }

  function formatPrice(value?: number) {
    if (value === undefined || value === null) return "-";
    return Number(value).toFixed(value >= 100 ? 1 : 2).replace(/\.00$/, "");
  }

  function getSignalClass(signal?: string) {
    if (!signal) return "signal-neutral";
    if (signal.includes("多")) return "signal-up";
    if (signal.includes("空")) return "signal-down";
    return "signal-neutral";
  }

  return (
    <main className="page">
      <div className="container">
        <header className="page-header">
          <h1 className="title">台股即時選股系統</h1>
          <div className="header-meta">
            <span>資料更新：{lastUpdate || "—"}</span>
            <button className="refresh-btn" onClick={fetchStocks}>
              重新整理
            </button>
          </div>
        </header>

        <section className="top-layout">
          <div className="panel left-panel">
            <h2 className="panel-title">價格分類</h2>

            <div className="category-list">
              {categories.map((c) => (
                <button
                  key={c.value}
                  className={`category-btn ${priceFilter === c.value ? "active" : ""}`}
                  onClick={() => setPriceFilter(c.value)}
                >
                  {c.label} ({getCategoryCount(c.value)})
                </button>
              ))}
            </div>

            <div className="search-wrap">
              <input
                className="search-input"
                type="text"
                placeholder="搜尋股票代號 / 名稱"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
              />
            </div>

            <div className="sort-wrap">
              <button
                className={`sort-btn ${sortType === "score" ? "active" : ""}`}
                onClick={() => setSortType("score")}
              >
                推薦
              </button>
              <button
                className={`sort-btn ${sortType === "up" ? "active" : ""}`}
                onClick={() => setSortType("up")}
              >
                漲幅
              </button>
              <button
                className={`sort-btn ${sortType === "down" ? "active" : ""}`}
                onClick={() => setSortType("down")}
              >
                跌幅
              </button>
            </div>
          </div>

          <div className="panel right-panel">
            <h2 className="panel-title">🔥 推薦10檔</h2>

            <div className="recommend-list">
              {topStocks.length === 0 && !loading && (
                <div className="empty-box">目前沒有推薦資料</div>
              )}

              {topStocks.map((s) => (
                <div className="recommend-card" key={s.symbol}>
                  <div className="recommend-top">
                    <div className="recommend-name">
                      <span className="recommend-symbol">{s.symbol}</span>
                      <span>{s.name}</span>
                    </div>
                    <div className="recommend-score">分數 {s.score ?? "-"}</div>
                  </div>

                  <div className="recommend-meta">
                    <span className={`signal-badge ${getSignalClass(s.signal)}`}>
                      {s.signal || "中性"}
                    </span>
                    <span>股價 {formatPrice(s.price)}</span>
                    <span
                      className={
                        (s.change_percent || 0) >= 0 ? "text-up" : "text-down"
                      }
                    >
                      漲跌幅 {s.change_percent ?? 0}%
                    </span>
                  </div>

                  <div className="recommend-reason">{s.reason || "暫無推薦原因"}</div>

                  <div className="recommend-levels">
                    <span>進場：{s.entry_price || "-"}</span>
                    <span>目標：{s.target_price || "-"}</span>
                    <span>停損：{s.stop_loss || "-"}</span>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </section>

        <section className="panel list-panel">
          <div className="list-header">
            <h2 className="panel-title">股票列表 ({filteredStocks.length})</h2>
          </div>

          {loading && <div className="status-box">資料載入中...</div>}
          {error && !loading && <div className="status-box error-box">{error}</div>}
          {!loading && !error && filteredStocks.length === 0 && (
            <div className="status-box">查無符合條件的股票</div>
          )}

          {!loading && !error && filteredStocks.length > 0 && (
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
                  {filteredStocks.map((s) => (
                    <tr key={s.symbol}>
                      <td>{s.symbol}</td>
                      <td>{s.name}</td>
                      <td>{formatPrice(s.price)}</td>
                      <td className={(s.change_percent || 0) >= 0 ? "text-up" : "text-down"}>
                        {s.change_percent ?? 0}%
                      </td>
                      <td>{formatNumber(s.volume)}</td>
                      <td className="score-cell">{s.score ?? "-"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>
      </div>
    </main>
  );
}
