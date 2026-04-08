"use client";

import { useEffect, useMemo, useState } from "react";

type Stock = {
  market?: string;
  symbol: string;
  name: string;
  price: number;
  change: number;
  change_percent: number;
  volume?: number;
  score?: number;
  signal?: string;
  grade?: string;
  risk_reward_ratio?: string;
};

type CategoryItem = {
  key: string;
  label: string;
  count: number;
};

type ApiResponse = {
  success?: boolean;
  market_status?: string;
  data_date?: string;
  last_update?: string;
  total?: number;
  stocks?: Stock[];
  categories?: CategoryItem[];
  message?: string;
};

const BACKEND_URL = "https://twstock-realtime-screener1.onrender.com/stocks";
const PAGE_SIZE = 20;

function formatNumber(value: number | undefined | null, digits = 2) {
  const n = Number(value ?? 0);
  if (!Number.isFinite(n)) return "-";
  return n.toLocaleString("zh-TW", {
    minimumFractionDigits: 0,
    maximumFractionDigits: digits,
  });
}

function formatPrice(value: number | undefined | null) {
  const n = Number(value ?? 0);
  if (!Number.isFinite(n)) return "-";
  return n.toLocaleString("zh-TW", {
    minimumFractionDigits: n >= 100 ? 0 : 2,
    maximumFractionDigits: n >= 100 ? 1 : 2,
  });
}

function formatVolume(value: number | undefined | null) {
  const n = Number(value ?? 0);
  if (!Number.isFinite(n)) return "-";
  return n.toLocaleString("zh-TW");
}

function getPriceCategory(price: number) {
  if (price < 10) return "0-10";
  if (price < 20) return "10-20";
  if (price < 50) return "20-50";
  if (price < 100) return "50-100";
  if (price < 200) return "100-200";
  if (price < 500) return "200-500";
  if (price < 1000) return "500-1000";
  return "1000+";
}

function buildCategories(stocks: Stock[]): CategoryItem[] {
  const order = [
    "all",
    "0-10",
    "10-20",
    "20-50",
    "50-100",
    "100-200",
    "200-500",
    "500-1000",
    "1000+",
  ];

  const labels: Record<string, string> = {
    all: "全部",
    "0-10": "0-10",
    "10-20": "10-20",
    "20-50": "20-50",
    "50-100": "50-100",
    "100-200": "100-200",
    "200-500": "200-500",
    "500-1000": "500-1000",
    "1000+": "1000+",
  };

  const counter: Record<string, number> = {
    all: stocks.length,
    "0-10": 0,
    "10-20": 0,
    "20-50": 0,
    "50-100": 0,
    "100-200": 0,
    "200-500": 0,
    "500-1000": 0,
    "1000+": 0,
  };

  for (const stock of stocks) {
    const key = getPriceCategory(Number(stock.price || 0));
    counter[key] += 1;
  }

  return order.map((key) => ({
    key,
    label: labels[key],
    count: counter[key] || 0,
  }));
}

export default function Page() {
  const [stocks, setStocks] = useState<Stock[]>([]);
  const [categories, setCategories] = useState<CategoryItem[]>([]);
  const [marketStatus, setMarketStatus] = useState("-");
  const [dataDate, setDataDate] = useState("-");
  const [lastUpdate, setLastUpdate] = useState("-");
  const [selectedCategory, setSelectedCategory] = useState("all");
  const [searchTerm, setSearchTerm] = useState("");
  const [sortType, setSortType] = useState<"change_desc" | "change_asc" | "volume_desc" | "score_desc">("change_desc");
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(false);
  const [errorText, setErrorText] = useState("");

  const fetchStocks = async () => {
    try {
      setLoading(true);
      setErrorText("");

      const res = await fetch(BACKEND_URL, { cache: "no-store" });
      const data: ApiResponse = await res.json();

      const incomingStocks = Array.isArray(data.stocks) ? data.stocks : [];
      setStocks(incomingStocks);
      setCategories(
        Array.isArray(data.categories) && data.categories.length > 0
          ? [{ key: "all", label: "全部", count: incomingStocks.length }, ...data.categories.filter((c) => c.key !== "all")]
          : buildCategories(incomingStocks)
      );
      setMarketStatus(data.market_status || "-");
      setDataDate(data.data_date || "-");
      setLastUpdate(data.last_update || "-");
    } catch (error) {
      console.error(error);
      setErrorText("讀取資料失敗");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchStocks();
    const timer = setInterval(fetchStocks, 20000);
    return () => clearInterval(timer);
  }, []);

  useEffect(() => {
    setPage(1);
  }, [selectedCategory, searchTerm, sortType]);

  const filteredStocks = useMemo(() => {
    let result = [...stocks];

    if (selectedCategory !== "all") {
      result = result.filter((stock) => {
        const price = Number(stock.price || 0);
        return getPriceCategory(price) === selectedCategory;
      });
    }

    const keyword = searchTerm.trim().toLowerCase();
    if (keyword) {
      result = result.filter((stock) => {
        const symbol = String(stock.symbol || "").toLowerCase();
        const name = String(stock.name || "").toLowerCase();
        return symbol.includes(keyword) || name.includes(keyword);
      });
    }

    result.sort((a, b) => {
      if (sortType === "change_desc") {
        return Number(b.change_percent || 0) - Number(a.change_percent || 0);
      }
      if (sortType === "change_asc") {
        return Number(a.change_percent || 0) - Number(b.change_percent || 0);
      }
      if (sortType === "volume_desc") {
        return Number(b.volume || 0) - Number(a.volume || 0);
      }
      return Number(b.score || 0) - Number(a.score || 0);
    });

    return result;
  }, [stocks, selectedCategory, searchTerm, sortType]);

  const totalPages = Math.max(1, Math.ceil(filteredStocks.length / PAGE_SIZE));

  const pagedStocks = useMemo(() => {
    const start = (page - 1) * PAGE_SIZE;
    return filteredStocks.slice(start, start + PAGE_SIZE);
  }, [filteredStocks, page]);

  const recommendStocks = useMemo(() => {
    return [...stocks]
      .sort((a, b) => Number(b.score || 0) - Number(a.score || 0))
      .slice(0, 10);
  }, [stocks]);

  useEffect(() => {
    if (page > totalPages) {
      setPage(totalPages);
    }
  }, [page, totalPages]);

  return (
    <main className="page-wrap">
      <div className="page-inner">
        <section className="top-summary-card">
          <div className="summary-grid">
            <div className="summary-item">
              <div className="summary-label">市場狀態</div>
              <div className="summary-value">{marketStatus}</div>
            </div>
            <div className="summary-item">
              <div className="summary-label">資料日期</div>
              <div className="summary-value">{dataDate}</div>
            </div>
            <div className="summary-item">
              <div className="summary-label">最後更新</div>
              <div className="summary-value">{lastUpdate}</div>
            </div>
          </div>
        </section>

        <section className="top-panel-grid">
          <div className="panel-card">
            <div className="panel-title">股票分類</div>

            <div className="category-list">
              {categories.map((cat) => (
                <button
                  key={cat.key}
                  type="button"
                  className={`category-btn ${selectedCategory === cat.key ? "active" : ""}`}
                  onClick={() => setSelectedCategory(cat.key)}
                >
                  <span>{cat.label}</span>
                  <span className="category-count">({cat.count})</span>
                </button>
              ))}
            </div>

            <div className="filter-box">
              <input
                className="search-input"
                type="text"
                placeholder="搜尋股票代號 / 名稱"
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
              />

              <select
                className="sort-select"
                value={sortType}
                onChange={(e) => setSortType(e.target.value as "change_desc" | "change_asc" | "volume_desc" | "score_desc")}
              >
                <option value="change_desc">漲幅由大到小</option>
                <option value="change_asc">跌幅由大到小</option>
                <option value="volume_desc">成交量由大到小</option>
                <option value="score_desc">分數由大到小</option>
              </select>
            </div>
          </div>

          <div className="panel-card">
            <div className="panel-title">推薦 10 檔</div>

            <div className="recommend-list">
              {recommendStocks.map((stock, index) => {
                const up = Number(stock.change_percent || 0) >= 0;
                return (
                  <div key={`${stock.symbol}-${index}`} className="recommend-item">
                    <div className="recommend-top">
                      <div className="recommend-name-wrap">
                        <span className="recommend-symbol">{stock.symbol}</span>
                        <span className="recommend-name">{stock.name}</span>
                      </div>
                      <div className={`recommend-pct ${up ? "up" : "down"}`}>
                        {up ? "+" : ""}
                        {formatNumber(stock.change_percent)}%
                      </div>
                    </div>

                    <div className="recommend-sub">
                      <span>股價 {formatPrice(stock.price)}</span>
                      <span>分數 {formatNumber(stock.score)}</span>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        </section>

        <section className="table-card">
          <div className="table-header">
            <div className="table-title">股票列表 ({filteredStocks.length})</div>
            <div className="table-meta">
              {loading ? "資料更新中..." : errorText ? errorText : `第 ${page} / ${totalPages} 頁，每頁 ${PAGE_SIZE} 檔`}
            </div>
          </div>

          <div className="table-scroll">
            <table className="stock-table">
              <thead>
                <tr>
                  <th className="col-market">市場</th>
                  <th className="col-stock">股票代號 股票名稱</th>
                  <th className="col-price">股價</th>
                  <th className="col-change">漲跌</th>
                  <th className="col-change-pct">漲跌%</th>
                  <th className="col-volume">成交量</th>
                  <th className="col-signal">訊號</th>
                  <th className="col-grade">評級</th>
                  <th className="col-score">分數</th>
                  <th className="col-rr">風報比</th>
                </tr>
              </thead>

              <tbody>
                {pagedStocks.map((stock) => {
                  const isUp = Number(stock.change || 0) >= 0;
                  const isUpPct = Number(stock.change_percent || 0) >= 0;

                  return (
                    <tr key={`${stock.symbol}-${stock.name}`}>
                      <td className="col-market">{stock.market || "-"}</td>

                      <td className="col-stock">
                        <div className="stock-id-name">
                          <span className="stock-symbol">{stock.symbol}</span>
                          <span className="stock-name">{stock.name}</span>
                        </div>
                      </td>

                      <td className="col-price">{formatPrice(stock.price)}</td>

                      <td className={`col-change ${isUp ? "up" : "down"}`}>
                        {isUp ? "+" : ""}
                        {formatNumber(stock.change)}
                      </td>

                      <td className={`col-change-pct ${isUpPct ? "up" : "down"}`}>
                        {isUpPct ? "+" : ""}
                        {formatNumber(stock.change_percent)}%
                      </td>

                      <td className="col-volume">{formatVolume(stock.volume)}</td>
                      <td className="col-signal">{stock.signal || "-"}</td>
                      <td className="col-grade">{stock.grade || "-"}</td>
                      <td className="col-score">{formatNumber(stock.score)}</td>
                      <td className="col-rr">{stock.risk_reward_ratio || "-"}</td>
                    </tr>
                  );
                })}

                {pagedStocks.length === 0 && (
                  <tr>
                    <td colSpan={10} className="empty-row">
                      查無資料
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>

          <div className="pagination-bar">
            <button
              type="button"
              className="page-btn"
              disabled={page <= 1}
              onClick={() => setPage((prev) => Math.max(1, prev - 1))}
            >
              上一頁
            </button>

            <div className="page-number-group">
              {Array.from({ length: totalPages }, (_, i) => i + 1)
                .filter((p) => {
                  if (totalPages <= 10) return true;
                  return p === 1 || p === totalPages || Math.abs(p - page) <= 2;
                })
                .map((p, index, arr) => {
                  const prev = arr[index - 1];
                  const showDots = prev && p - prev > 1;

                  return (
                    <div key={p} style={{ display: "flex", alignItems: "center", gap: 8 }}>
                      {showDots && <span className="page-dots">...</span>}
                      <button
                        type="button"
                        className={`page-btn ${page === p ? "active" : ""}`}
                        onClick={() => setPage(p)}
                      >
                        {p}
                      </button>
                    </div>
                  );
                })}
            </div>

            <button
              type="button"
              className="page-btn"
              disabled={page >= totalPages}
              onClick={() => setPage((prev) => Math.min(totalPages, prev + 1))}
            >
              下一頁
            </button>
          </div>
        </section>
      </div>

      <style jsx>{`
        .page-wrap {
          width: 100%;
          min-height: 100vh;
          background: #08264d;
          padding: 12px;
          color: #ffffff;
        }

        .page-inner {
          width: 100%;
          max-width: 1600px;
          margin: 0 auto;
        }

        .top-summary-card,
        .panel-card,
        .table-card {
          background: #0d2d5b;
          border: 1px solid rgba(255, 255, 255, 0.08);
          border-radius: 18px;
          box-shadow: 0 8px 24px rgba(0, 0, 0, 0.18);
        }

        .top-summary-card {
          padding: 14px 16px;
          margin-bottom: 14px;
        }

        .summary-grid {
          display: grid;
          grid-template-columns: repeat(3, minmax(0, 1fr));
          gap: 12px;
        }

        .summary-item {
          background: rgba(255, 255, 255, 0.04);
          border-radius: 12px;
          padding: 12px 14px;
        }

        .summary-label {
          font-size: 12px;
          color: #b8cff5;
          margin-bottom: 6px;
        }

        .summary-value {
          font-size: 18px;
          font-weight: 700;
        }

        .top-panel-grid {
          display: grid;
          grid-template-columns: 360px minmax(0, 1fr);
          gap: 14px;
          margin-bottom: 14px;
        }

        .panel-card {
          padding: 14px;
        }

        .panel-title {
          font-size: 28px;
          font-weight: 800;
          margin-bottom: 12px;
        }

        .category-list {
          display: grid;
          grid-template-columns: repeat(2, minmax(0, 1fr));
          gap: 10px;
          margin-bottom: 14px;
        }

        .category-btn {
          border: none;
          border-radius: 12px;
          padding: 12px 10px;
          background: rgba(255, 255, 255, 0.06);
          color: #ffffff;
          cursor: pointer;
          font-size: 15px;
          font-weight: 700;
        }

        .category-btn.active {
          background: linear-gradient(180deg, #3a78c7 0%, #1d4f96 100%);
        }

        .category-count {
          margin-left: 4px;
          color: #d2e5ff;
        }

        .filter-box {
          display: flex;
          flex-direction: column;
          gap: 10px;
        }

        .search-input,
        .sort-select {
          width: 100%;
          height: 44px;
          border: 1px solid rgba(255, 255, 255, 0.14);
          border-radius: 12px;
          background: rgba(255, 255, 255, 0.06);
          color: #ffffff;
          padding: 0 12px;
          outline: none;
        }

        .sort-select option {
          color: #000000;
        }

        .recommend-list {
          display: flex;
          flex-direction: column;
          gap: 10px;
          max-height: 360px;
          overflow-y: auto;
          padding-right: 4px;
        }

        .recommend-item {
          background: rgba(255, 255, 255, 0.05);
          border-radius: 12px;
          padding: 12px;
        }

        .recommend-top {
          display: flex;
          align-items: center;
          justify-content: space-between;
          gap: 12px;
          margin-bottom: 8px;
        }

        .recommend-name-wrap {
          display: flex;
          align-items: center;
          gap: 8px;
          min-width: 0;
        }

        .recommend-symbol {
          font-weight: 800;
          color: #9fd0ff;
          flex: 0 0 auto;
        }

        .recommend-name {
          font-weight: 700;
          overflow: hidden;
          text-overflow: ellipsis;
          white-space: nowrap;
        }

        .recommend-sub {
          display: flex;
          gap: 14px;
          flex-wrap: wrap;
          color: #c5d8f7;
          font-size: 13px;
        }

        .table-card {
          padding: 14px;
        }

        .table-header {
          display: flex;
          align-items: center;
          justify-content: space-between;
          gap: 12px;
          margin-bottom: 12px;
        }

        .table-title {
          font-size: 18px;
          font-weight: 800;
        }

        .table-meta {
          font-size: 13px;
          color: #c7daf5;
        }

        .table-scroll {
          width: 100%;
          overflow-x: auto;
        }

        .stock-table {
          width: 100%;
          border-collapse: collapse;
          table-layout: fixed;
          min-width: 1120px;
          background: #0d2d5b;
          border-radius: 14px;
          overflow: hidden;
        }

        .stock-table thead th {
          background: linear-gradient(180deg, #3972be 0%, #27589c 100%);
          color: #ffffff;
          font-size: 13px;
          font-weight: 800;
          padding: 10px 8px;
          white-space: nowrap;
        }

        .stock-table tbody td {
          padding: 10px 8px;
          border-bottom: 1px solid rgba(255, 255, 255, 0.06);
          white-space: nowrap;
          font-size: 14px;
          font-weight: 700;
        }

        .stock-table tbody tr:hover {
          background: rgba(255, 255, 255, 0.03);
        }

        .col-market {
          width: 48px;
          text-align: center;
        }

        .col-stock {
          width: 190px;
          text-align: left;
        }

        .col-price {
          width: 70px;
          text-align: right;
        }

        .col-change {
          width: 76px;
          text-align: center;
        }

        .col-change-pct {
          width: 82px;
          text-align: center;
        }

        .col-volume {
          width: 92px;
          text-align: center;
        }

        .col-signal {
          width: 90px;
          text-align: center;
        }

        .col-grade {
          width: 70px;
          text-align: center;
        }

        .col-score {
          width: 78px;
          text-align: center;
        }

        .col-rr {
          width: 78px;
          text-align: center;
        }

        .stock-id-name {
          display: flex;
          align-items: center;
          gap: 8px;
          overflow: hidden;
          min-width: 0;
        }

        .stock-symbol {
          flex: 0 0 auto;
          font-weight: 800;
          color: #8fc4ff;
        }

        .stock-name {
          flex: 1 1 auto;
          overflow: hidden;
          text-overflow: ellipsis;
          white-space: nowrap;
        }

        .up {
          color: #ff5b6e;
        }

        .down {
          color: #57d38c;
        }

        .empty-row {
          text-align: center;
          padding: 24px 12px !important;
          color: #c7daf5;
        }

        .pagination-bar {
          margin-top: 14px;
          display: flex;
          align-items: center;
          justify-content: center;
          gap: 10px;
          flex-wrap: wrap;
        }

        .page-number-group {
          display: flex;
          align-items: center;
          gap: 8px;
          flex-wrap: wrap;
        }

        .page-btn {
          min-width: 42px;
          height: 38px;
          border: none;
          border-radius: 10px;
          padding: 0 12px;
          background: rgba(255, 255, 255, 0.08);
          color: #ffffff;
          font-weight: 700;
          cursor: pointer;
        }

        .page-btn.active {
          background: linear-gradient(180deg, #3a78c7 0%, #1d4f96 100%);
        }

        .page-btn:disabled {
          opacity: 0.45;
          cursor: not-allowed;
        }

        .page-dots {
          color: #c7daf5;
          font-weight: 700;
        }

        @media (max-width: 1100px) {
          .top-panel-grid {
            grid-template-columns: 1fr;
          }
        }

        @media (max-width: 768px) {
          .page-wrap {
            padding: 10px;
          }

          .summary-grid {
            grid-template-columns: 1fr;
          }

          .panel-title {
            font-size: 22px;
          }

          .category-list {
            grid-template-columns: repeat(2, minmax(0, 1fr));
          }

          .stock-table {
            min-width: 980px;
          }
        }
      `}</style>
    </main>
  );
}
