"use client";

import { useEffect, useMemo, useState } from "react";

type Stock = {
  market?: string;
  symbol: string;
  name: string;
  price: number;
  change?: number;
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
  last_fetch_time?: string;
  total?: number;
  stocks?: Stock[];
  top_recommendations?: Stock[];
  message?: string;
};

const BACKEND_URL = "https://twstock-realtime-screener1.onrender.com/stocks";

export default function Home() {
  const [stocks, setStocks] = useState<Stock[]>([]);
  const [topStocks, setTopStocks] = useState<Stock[]>([]);
  const [searchTerm, setSearchTerm] = useState("");
  const [selectedCategory, setSelectedCategory] = useState("all");
  const [sortType, setSortType] = useState<"score" | "up" | "down">("score");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const [marketStatus, setMarketStatus] = useState("-");
  const [dataDate, setDataDate] = useState("-");
  const [lastUpdate, setLastUpdate] = useState("-");

  useEffect(() => {
    fetchStocks();
  }, []);

  async function fetchStocks() {
    try {
      setLoading(true);
      setError("");

      const res = await fetch(BACKEND_URL, { cache: "no-store" });
      const data: ApiResponse = await res.json();

      if (!res.ok || !data.success) {
        throw new Error(data.message || "資料讀取失敗");
      }

      const allStocks = Array.isArray(data.stocks) ? data.stocks : [];
      const recommended =
        Array.isArray(data.top_recommendations) && data.top_recommendations.length > 0
          ? data.top_recommendations
          : [...allStocks]
              .sort((a, b) => (b.score || 0) - (a.score || 0))
              .slice(0, 10);

      setStocks(allStocks);
      setTopStocks(recommended);

      setMarketStatus(data.market_status || "-");
      setDataDate(data.data_date || "-");
      setLastUpdate(data.last_update || data.last_fetch_time || "-");
    } catch (err: any) {
      setError(err?.message || "讀取資料失敗");
      setStocks([]);
      setTopStocks([]);
      setMarketStatus("-");
      setDataDate("-");
      setLastUpdate("-");
    } finally {
      setLoading(false);
    }
  }

  const categories = useMemo(
    () => [
      { label: "全部", value: "all" },
      { label: "0-50", value: "0-50" },
      { label: "50-100", value: "50-100" },
      { label: "100-200", value: "100-200" },
      { label: "200-500", value: "200-500" },
      { label: "500+", value: "500-999999" },
    ],
    []
  );

  function getCategoryCount(value: string) {
    if (value === "all") return stocks.length;
    const [min, max] = value.split("-").map(Number);
    return stocks.filter((s) => s.price >= min && s.price <= max).length;
  }

  const filteredStocks = useMemo(() => {
    let result = [...stocks];

    if (selectedCategory !== "all") {
      const [min, max] = selectedCategory.split("-").map(Number);
      result = result.filter((s) => s.price >= min && s.price <= max);
    }

    if (searchTerm.trim()) {
      const keyword = searchTerm.trim().toLowerCase();
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
  }, [stocks, selectedCategory, searchTerm, sortType]);

  function formatPrice(value?: number) {
    if (value === undefined || value === null || Number.isNaN(value)) return "-";
    return Number(value).toFixed(value >= 100 ? 1 : 2).replace(/\.00$/, "");
  }

  function formatVolume(value?: number) {
    if (value === undefined || value === null || Number.isNaN(value)) return "-";
    return value.toLocaleString();
  }

  function signalClass(signal?: string) {
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
            <span>市場狀態：{marketStatus}</span>
            <span>資料日期：{dataDate}</span>
            <span>最後更新：{lastUpdate}</span>
            <button className="refresh-btn" onClick={fetchStocks}>
              重新整理
            </button>
          </div>
        </header>

        <section className="top-layout">
          <div className="panel left-panel">
            <h2 className="panel-title">價格分類</h2>

            <div className="category-list">
              {categories.map((item) => (
                <button
                  key={item.value}
                  className={`category-btn ${
                    selectedCategory === item.value ? "active" : ""
                  }`}
                  onClick={() => setSelectedCategory(item.value)}
                >
                  {item.label} ({getCategoryCount(item.value)})
                </button>
              ))}
            </div>

            <div className="search-wrap">
              <input
                className="search-input"
                type="text"
                placeholder="搜尋股票代號 / 名稱"
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
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

            {loading ? (
              <div className="status-box">資料載入中...</div>
            ) : topStocks.length === 0 ? (
              <div className="status-box">目前沒有推薦資料</div>
            ) : (
              <div className="recommend-list">
                {topStocks.slice(0, 10).map((stock) => (
                  <div className="recommend-card" key={stock.symbol}>
                    <div className="recommend-top">
                      <div className="recommend-name">
                        <span className="recommend-symbol">{stock.symbol}</span>
                        <span>{stock.name}</span>
                      </div>
                      <div className="recommend-score">分數 {stock.score ?? "-"}</div>
                    </div>

                    <div className="recommend-meta">
                      <span className={`signal-badge ${signalClass(stock.signal)}`}>
                        {stock.signal || "中性"}
                      </span>
                      <span>股價 {formatPrice(stock.price)}</span>
                      <span
                        className={
                          (stock.change_percent || 0) >= 0 ? "text-up" : "text-down"
                        }
                      >
                        漲跌幅 {stock.change_percent ?? 0}%
                      </span>
                    </div>

                    <div className="recommend-reason">
                      {stock.reason || "暫無推薦原因"}
                    </div>

                    <div className="recommend-levels">
                      <span>進場：{stock.entry_price || "-"}</span>
                      <span>目標：{stock.target_price || "-"}</span>
                      <span>停損：{stock.stop_loss || "-"}</span>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </section>

        <section className="panel list-panel">
          <div className="list-header">
            <h2 className="panel-title">股票列表 ({filteredStocks.length})</h2>
          </div>

          {loading && <div className="status-box">資料載入中...</div>}
          {!loading && error && <div className="status-box error-box">{error}</div>}
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
                  {filteredStocks.map((stock) => (
                    <tr key={stock.symbol}>
                      <td>{stock.symbol}</td>
                      <td>{stock.name}</td>
                      <td>{formatPrice(stock.price)}</td>
                      <td
                        className={
                          (stock.change_percent || 0) >= 0 ? "text-up" : "text-down"
                        }
                      >
                        {stock.change_percent ?? 0}%
                      </td>
                      <td>{formatVolume(stock.volume)}</td>
                      <td className="score-cell">{stock.score ?? "-"}</td>
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
