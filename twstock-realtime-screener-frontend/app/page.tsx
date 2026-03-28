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
  entry_price?: string;
  target_price?: string;
  stop_loss?: string;
  open?: number;
  high?: number;
  low?: number;
  prev_close?: number;
  reference_price?: number;
  update_time?: string;
};

type MarketResponse = {
  success: boolean;
  data_date: string;
  last_update: string;
  market_status: string;
  message: string;
  total: number;
  source_summary?: {
    twse_count?: number;
    tpex_count?: number;
  };
  stocks: Stock[];
};

type RealtimeResponse = {
  success: boolean;
  market_status: string;
  data_date: string;
  last_update: string;
  message: string;
  total: number;
  stocks: Stock[];
  ws_connected: boolean;
};

const BACKEND_URL =
  process.env.NEXT_PUBLIC_BACKEND_URL ||
  "https://twstock-realtime-screener1.onrender.com";

const CATEGORIES = [
  { key: "all", label: "全部股票" },
  { key: "0-10", label: "0 ~ 10" },
  { key: "10-20", label: "10 ~ 20" },
  { key: "20-50", label: "20 ~ 50" },
  { key: "50-100", label: "50 ~ 100" },
  { key: "100-200", label: "100 ~ 200" },
  { key: "200-500", label: "200 ~ 500" },
  { key: "500-1000", label: "500 ~ 1000" },
  { key: "1000+", label: "1000 以上" },
];

const SORT_OPTIONS = [
  { key: "score", label: "推薦分數" },
  { key: "up", label: "漲幅" },
  { key: "down", label: "跌幅" },
  { key: "volume", label: "成交量" },
] as const;

export default function Home() {
  const [marketStocks, setMarketStocks] = useState<Stock[]>([]);
  const [realtimeStocks, setRealtimeStocks] = useState<Stock[]>([]);
  const [searchTerm, setSearchTerm] = useState("");
  const [selectedCategory, setSelectedCategory] = useState("all");
  const [sortBy, setSortBy] = useState<"score" | "up" | "down" | "volume">("score");
  const [marketMeta, setMarketMeta] = useState<MarketResponse | null>(null);
  const [realtimeMeta, setRealtimeMeta] = useState<RealtimeResponse | null>(null);
  const [loading, setLoading] = useState(true);

  async function fetchMarket(category = selectedCategory, sort = sortBy, q = searchTerm) {
    const url = `${BACKEND_URL}/market?category=${encodeURIComponent(
      category
    )}&sort_by=${encodeURIComponent(sort)}&q=${encodeURIComponent(q)}&limit=5000`;

    const res = await fetch(url, { cache: "no-store" });
    const data: MarketResponse = await res.json();
    setMarketStocks(data.stocks || []);
    setMarketMeta(data);
  }

  async function fetchRealtime() {
    const res = await fetch(`${BACKEND_URL}/stocks`, { cache: "no-store" });
    const data: RealtimeResponse = await res.json();
    setRealtimeStocks(data.stocks || []);
    setRealtimeMeta(data);
  }

  async function loadAll() {
    try {
      setLoading(true);
      await Promise.all([fetchMarket("all", sortBy, searchTerm), fetchRealtime()]);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadAll();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    fetchMarket(selectedCategory, sortBy, searchTerm);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedCategory, sortBy]);

  useEffect(() => {
    const timer = setTimeout(() => {
      fetchMarket(selectedCategory, sortBy, searchTerm);
    }, 350);
    return () => clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchTerm]);

  useEffect(() => {
    const realtimeTimer = setInterval(() => {
      fetchRealtime();
    }, 15000);

    const marketTimer = setInterval(() => {
      fetchMarket(selectedCategory, sortBy, searchTerm);
    }, 60000);

    return () => {
      clearInterval(realtimeTimer);
      clearInterval(marketTimer);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedCategory, sortBy, searchTerm]);

  const realtimeMap = useMemo(() => {
    const map = new Map<string, Stock>();
    realtimeStocks.forEach((s) => map.set(s.symbol, s));
    return map;
  }, [realtimeStocks]);

  const mergedStocks = useMemo(() => {
    return marketStocks.map((stock) => {
      const rt = realtimeMap.get(stock.symbol);
      return rt
        ? {
            ...stock,
            ...rt,
            market: stock.market,
          }
        : stock;
    });
  }, [marketStocks, realtimeMap]);

  const topRecommended = useMemo(() => {
    return [...mergedStocks]
      .sort(
        (a, b) =>
          (b.score || 0) - (a.score || 0) ||
          (b.change_percent || 0) - (a.change_percent || 0) ||
          (b.volume || 0) - (a.volume || 0)
      )
      .slice(0, 10);
  }, [mergedStocks]);

  const statusText = realtimeMeta?.ws_connected
    ? "富邦即時連線中"
    : "即時連線未完成";

  const marketCount = marketMeta?.total || 0;
  const allCount = marketMeta?.total || 0;
  const twseCount = marketMeta?.source_summary?.twse_count || 0;
  const tpexCount = marketMeta?.source_summary?.tpex_count || 0;

  return (
    <main className="page-shell">
      <div className="page-header">
        <div>
          <h1>台股即時瀏覽系統</h1>
          <p>
            全市場瀏覽 + 富邦即時觀察股 + 推薦分數 + 進出場輔助
          </p>
        </div>

        <div className="header-badges">
          <span className="badge success">{statusText}</span>
          <span className="badge">
            市場資料：{marketMeta?.last_update || "載入中"}
          </span>
          <span className="badge">
            即時資料：{realtimeMeta?.last_update || "載入中"}
          </span>
        </div>
      </div>

      <section className="top-grid">
        <div className="panel controls-panel">
          <div className="panel-title-row">
            <h2>篩選與狀態</h2>
          </div>

          <div className="controls-grid">
            <div className="field">
              <label>搜尋股票</label>
              <input
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                placeholder="輸入股票代碼或名稱"
              />
            </div>

            <div className="field">
              <label>排序方式</label>
              <select
                value={sortBy}
                onChange={(e) =>
                  setSortBy(e.target.value as "score" | "up" | "down" | "volume")
                }
              >
                {SORT_OPTIONS.map((item) => (
                  <option key={item.key} value={item.key}>
                    {item.label}
                  </option>
                ))}
              </select>
            </div>
          </div>

          <div className="stats-row">
            <div className="stat-card">
              <span className="stat-label">目前列表</span>
              <strong>{marketCount}</strong>
            </div>
            <div className="stat-card">
              <span className="stat-label">上市</span>
              <strong>{twseCount}</strong>
            </div>
            <div className="stat-card">
              <span className="stat-label">上櫃</span>
              <strong>{tpexCount}</strong>
            </div>
            <div className="stat-card">
              <span className="stat-label">觀察股</span>
              <strong>{realtimeStocks.length}</strong>
            </div>
          </div>
        </div>

        <div className="panel">
          <div className="panel-title-row">
            <h2>推薦 10 檔</h2>
            <span className="mini-note">依推薦分數排序</span>
          </div>

          <div className="recommend-grid">
            {topRecommended.map((stock) => (
              <div key={stock.symbol} className="recommend-card">
                <div className="recommend-top">
                  <div>
                    <div className="symbol-line">
                      <strong>{stock.symbol}</strong>
                      <span>{stock.name}</span>
                    </div>
                    <div className="mini-note">{stock.market || "-"}</div>
                  </div>
                  <div className="score-pill">分數 {stock.score || 0}</div>
                </div>

                <div className="recommend-price">
                  <span className="price">${stock.price}</span>
                  <span
                    className={
                      (stock.change_percent || 0) >= 0 ? "change up" : "change down"
                    }
                  >
                    {stock.change_percent && stock.change_percent > 0 ? "+" : ""}
                    {stock.change_percent || 0}%
                  </span>
                </div>

                <div className="recommend-meta">
                  <span>訊號：{stock.signal || "-"}</span>
                  <span>進場：{stock.entry_price || "-"}</span>
                  <span>目標：{stock.target_price || "-"}</span>
                  <span>停損：{stock.stop_loss || "-"}</span>
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section className="content-grid">
        <aside className="panel sidebar">
          <div className="panel-title-row">
            <h2>價格分類</h2>
          </div>

          <div className="category-list">
            {CATEGORIES.map((item) => (
              <button
                key={item.key}
                className={selectedCategory === item.key ? "category active" : "category"}
                onClick={() => setSelectedCategory(item.key)}
              >
                <span>{item.label}</span>
                {item.key === "all" && <small>{allCount}</small>}
              </button>
            ))}
          </div>

          <div className="sidebar-note">
            <p>重新開網頁預設就是「全部股票」。</p>
            <p>手機版會自動改成上下排列，不會超出畫面。</p>
          </div>
        </aside>

        <section className="panel table-panel">
          <div className="panel-title-row">
            <h2>股票列表</h2>
            <div className="mini-note">
              {loading ? "載入中..." : `共 ${mergedStocks.length} 檔`}
            </div>
          </div>

          <div className="table-wrap">
            <table className="stock-table">
              <thead>
                <tr>
                  <th>市場</th>
                  <th>代碼</th>
                  <th>名稱</th>
                  <th>現價</th>
                  <th>漲跌幅</th>
                  <th>成交量</th>
                  <th>訊號</th>
                  <th>分數</th>
                  <th>進場價</th>
                  <th>目標價</th>
                  <th>停損價</th>
                </tr>
              </thead>
              <tbody>
                {mergedStocks.map((stock) => (
                  <tr key={`${stock.market}-${stock.symbol}`}>
                    <td>{stock.market || "-"}</td>
                    <td>{stock.symbol}</td>
                    <td>{stock.name}</td>
                    <td>{stock.price}</td>
                    <td
                      className={
                        (stock.change_percent || 0) >= 0 ? "change up" : "change down"
                      }
                    >
                      {(stock.change_percent || 0) > 0 ? "+" : ""}
                      {stock.change_percent || 0}%
                    </td>
                    <td>{stock.volume || 0}</td>
                    <td>{stock.signal || "-"}</td>
                    <td>{stock.score || 0}</td>
                    <td>{stock.entry_price || "-"}</td>
                    <td>{stock.target_price || "-"}</td>
                    <td>{stock.stop_loss || "-"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      </section>

      <section className="panel">
        <div className="panel-title-row">
          <h2>即時觀察股</h2>
          <span className="mini-note">
            富邦 WebSocket：{realtimeMeta?.ws_connected ? "已連線" : "未連線"}
          </span>
        </div>

        <div className="realtime-grid">
          {realtimeStocks.map((stock) => (
            <div key={stock.symbol} className="realtime-card">
              <div className="symbol-line">
                <strong>{stock.symbol}</strong>
                <span>{stock.name}</span>
              </div>

              <div className="recommend-price">
                <span className="price">${stock.price}</span>
                <span
                  className={
                    (stock.change_percent || 0) >= 0 ? "change up" : "change down"
                  }
                >
                  {(stock.change_percent || 0) > 0 ? "+" : ""}
                  {stock.change_percent || 0}%
                </span>
              </div>

              <div className="recommend-meta">
                <span>訊號：{stock.signal || "-"}</span>
                <span>成交量：{stock.volume || 0}</span>
                <span>進場：{stock.entry_price || "-"}</span>
                <span>目標：{stock.target_price || "-"}</span>
                <span>停損：{stock.stop_loss || "-"}</span>
              </div>
            </div>
          ))}
        </div>
      </section>
    </main>
  );
}
