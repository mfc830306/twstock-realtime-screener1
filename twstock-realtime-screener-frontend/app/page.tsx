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
  last_fetch_time?: string;
  stocks?: Stock[];
  top_recommendations?: Stock[];
  message?: string;
};

const BACKEND_URL = "https://twstock-realtime-screener1.onrender.com/stocks";

const categories = [
  { label: "全部", value: "all" },
  { label: "0-50", value: "0-50" },
  { label: "50-100", value: "50-100" },
  { label: "100-200", value: "100-200" },
  { label: "200-500", value: "200-500" },
  { label: "500+", value: "500-999999" },
];

export default function Home() {
  const [stocks, setStocks] = useState<Stock[]>([]);
  const [topStocks, setTopStocks] = useState<Stock[]>([]);
  const [search, setSearch] = useState("");
  const [category, setCategory] = useState("all");
  const [sort, setSort] = useState<"score" | "up" | "down">("score");

  const [marketStatus, setMarketStatus] = useState("-");
  const [dataDate, setDataDate] = useState("-");
  const [lastUpdate, setLastUpdate] = useState("-");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    fetchData();
  }, []);

  async function fetchData() {
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
          : [...allStocks].sort((a, b) => (b.score || 0) - (a.score || 0)).slice(0, 10);

      setStocks(allStocks);
      setTopStocks(recommended);

      setMarketStatus(resolveMarketStatus(data.market_status));
      setDataDate(resolveDataDate(data.data_date, data.last_update, data.last_fetch_time));
      setLastUpdate(resolveLastUpdate(data.last_update, data.last_fetch_time));
    } catch (err: any) {
      setError(err?.message || "讀取失敗");
      setStocks([]);
      setTopStocks([]);
      setMarketStatus("-");
      setDataDate("-");
      setLastUpdate("-");
    } finally {
      setLoading(false);
    }
  }

  function resolveMarketStatus(value?: string) {
    if (value && value.trim()) return value.trim();
    return "資料同步中";
  }

  function resolveDataDate(value?: string, lastUpdateValue?: string, lastFetchValue?: string) {
    if (value && value.trim()) return value.trim();

    const raw = lastUpdateValue || lastFetchValue || "";
    const digits = raw.replace(/\D/g, "");
    if (digits.length >= 8) return digits.slice(0, 8);

    return "-";
  }

  function resolveLastUpdate(value?: string, lastFetchValue?: string) {
    const finalValue = value || lastFetchValue || "";
    return finalValue.trim() || "-";
  }

  function getCategoryCount(value: string) {
    if (value === "all") return stocks.length;
    const [min, max] = value.split("-").map(Number);
    return stocks.filter((s) => s.price >= min && s.price <= max).length;
  }

  const filtered = useMemo(() => {
    let result = [...stocks];

    if (category !== "all") {
      const [min, max] = category.split("-").map(Number);
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

    if (sort === "up") {
      result.sort((a, b) => (b.change_percent || 0) - (a.change_percent || 0));
    } else if (sort === "down") {
      result.sort((a, b) => (a.change_percent || 0) - (b.change_percent || 0));
    } else {
      result.sort((a, b) => (b.score || 0) - (a.score || 0));
    }

    return result;
  }, [stocks, search, category, sort]);

  function formatPrice(value?: number) {
    if (value === undefined || value === null || Number.isNaN(value)) return "-";
    return Number(value).toLocaleString("zh-TW", {
      minimumFractionDigits: value >= 100 ? 1 : 2,
      maximumFractionDigits: value >= 100 ? 1 : 2,
    });
  }

  function formatVolume(value?: number) {
    if (value === undefined || value === null || Number.isNaN(value)) return "-";
    return value.toLocaleString("zh-TW");
  }

  function getSignalClass(signal?: string) {
    if (!signal) return "signal-neutral";
    if (signal.includes("多")) return "signal-up";
    if (signal.includes("空")) return "signal-down";
    return "signal-neutral";
  }

  function getMarketStatusClass(status?: string) {
    if (!status) return "status-neutral";
    if (status.includes("收盤")) return "status-close";
    if (status.includes("盤中") || status.includes("交易中")) return "status-live";
    if (status.includes("非當日") || status.includes("同步")) return "status-neutral";
    return "status-neutral";
  }

  function getQuickReason(reason?: string) {
    if (!reason) return "暫無策略摘要";
    const cleaned = reason.replace(/。/g, "；");
    const first = cleaned.split("；").map((v) => v.trim()).filter(Boolean)[0];
    return first || reason;
  }

  return (
    <main className="page">
      <div className="top-header">
        <div className="top-header-inner">
          <div className="top-left">
            <span className="logo">TW/STOCK</span>
            <span className="divider">·</span>
            <span className="subtitle">即時選股系統</span>
          </div>

          <div className="top-right">
            <span className={`status-badge ${getMarketStatusClass(marketStatus)}`}>
              ● {marketStatus}
            </span>
            <span>資料日期：{dataDate}</span>
            <span>最後更新：{lastUpdate}</span>
            <button className="refresh-btn small" onClick={fetchData}>
              更新
            </button>
          </div>
        </div>
      </div>

      <div className="container">
        <div className="top-layout">
          <section className="panel left-panel">
            <div className="panel-head">
              <h2 className="panel-title">價格分類</h2>
            </div>

            <div className="category-list">
              {categories.map((c) => (
                <button
                  key={c.value}
                  className={`category-btn ${category === c.value ? "active" : ""}`}
                  onClick={() => setCategory(c.value)}
                >
                  {c.label} <span className="count">({getCategoryCount(c.value)})</span>
                </button>
              ))}
            </div>

            <div className="search-wrap">
              <input
                className="search-input"
                placeholder="搜尋股票代號 / 名稱"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
              />
            </div>

            <div className="sort-wrap">
              <button
                className={`sort-btn ${sort === "score" ? "active" : ""}`}
                onClick={() => setSort("score")}
              >
                推薦
              </button>
              <button
                className={`sort-btn ${sort === "up" ? "active" : ""}`}
                onClick={() => setSort("up")}
              >
                漲幅
              </button>
              <button
                className={`sort-btn ${sort === "down" ? "active" : ""}`}
                onClick={() => setSort("down")}
              >
                跌幅
              </button>
            </div>
          </section>

          <section className="panel right-panel">
            <div className="panel-head">
              <h2 className="panel-title">🔥 推薦10檔</h2>
            </div>

            {loading ? (
              <div className="status-box">資料載入中...</div>
            ) : topStocks.length === 0 ? (
              <div className="status-box">目前沒有推薦資料</div>
            ) : (
              <div className="recommend-list">
                {topStocks.slice(0, 10).map((s) => (
                  <article key={s.symbol} className="recommend-card">
                    <div className="recommend-top">
                      <div className="recommend-main">
                        <div className="recommend-title-row">
                          <span className="recommend-symbol">{s.symbol}</span>
                          <span className="recommend-name">{s.name}</span>
                        </div>

                        <div className="recommend-meta-row">
                          <span className={`signal-badge mini ${getSignalClass(s.signal)}`}>
                            {s.signal || "中性"}
                          </span>
                          <span className="meta-item">股價 {formatPrice(s.price)}</span>
                          <span className={`meta-item ${(s.change_percent || 0) >= 0 ? "text-up" : "text-down"}`}>
                            漲跌幅 {s.change_percent ?? 0}%
                          </span>
                        </div>
                      </div>

                      <div className="recommend-side">
                        <div className="recommend-score">分數 {s.score ?? "-"}</div>
                      </div>
                    </div>

                    <div className="strategy-line">
                      <span className="strategy-label">策略重點</span>
                      <span className="strategy-text">{getQuickReason(s.reason)}</span>
                    </div>

                    <div className="recommend-reason">
                      {s.reason || "暫無推薦原因"}
                    </div>

                    <div className="recommend-extra">
                      <div className="level-box">
                        <span className="level-label">進場</span>
                        <span className="level-value">{s.entry_price || "-"}</span>
                      </div>
                      <div className="level-box">
                        <span className="level-label">目標</span>
                        <span className="level-value">{s.target_price || "-"}</span>
                      </div>
                      <div className="level-box">
                        <span className="level-label">停損</span>
                        <span className="level-value">{s.stop_loss || "-"}</span>
                      </div>
                    </div>
                  </article>
                ))}
              </div>
            )}
          </section>
        </div>

        <section className="panel list-panel">
          <div className="list-head">
            <h2 className="panel-title">股票列表 ({filtered.length})</h2>
          </div>

          {loading && <div className="status-box">資料載入中...</div>}
          {!loading && error && <div className="status-box error-box">{error}</div>}
          {!loading && !error && filtered.length === 0 && (
            <div className="status-box">查無符合條件的股票</div>
          )}

          {!loading && !error && filtered.length > 0 && (
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
                      <td>{formatPrice(s.price)}</td>
                      <td className={(s.change_percent || 0) >= 0 ? "text-up" : "text-down"}>
                        {s.change_percent ?? 0}%
                      </td>
                      <td>{formatVolume(s.volume)}</td>
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
