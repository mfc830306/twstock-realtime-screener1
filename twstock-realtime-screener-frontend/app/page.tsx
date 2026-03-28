"use client";

import { useEffect, useMemo, useState } from "react";

type Stock = {
  market: string;
  symbol: string;
  name: string;
  price: number;
  change: number;
  change_percent: number;
  volume?: number;
  score?: number;
  signal?: string;
  reason?: string;
  entry_price?: string;
  target_price?: string;
  stop_loss?: string;
  category?: "stock" | "etf";
};

const BACKEND_URL = "https://twstock-realtime-screener1.onrender.com/stocks";
const PAGE_SIZE = 20;

const PRICE_CATEGORIES = [
  { key: "all", label: "全部股票" },
  { key: "etf", label: "ETF" },
  { key: "0-10", label: "0 ~ 10" },
  { key: "10-20", label: "10 ~ 20" },
  { key: "20-50", label: "20 ~ 50" },
  { key: "50-100", label: "50 ~ 100" },
  { key: "100-200", label: "100 ~ 200" },
  { key: "200-500", label: "200 ~ 500" },
  { key: "500-1000", label: "500 ~ 1000" },
  { key: "1000+", label: "1000 以上" },
];

export default function Home() {
  const [stocks, setStocks] = useState<Stock[]>([]);
  const [searchTerm, setSearchTerm] = useState("");
  const [selectedCategory, setSelectedCategory] = useState("all");
  const [rankType, setRankType] = useState<"up" | "down" | "volume">("up");
  const [currentPage, setCurrentPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [errorText, setErrorText] = useState("");

  useEffect(() => {
    fetch(BACKEND_URL)
      .then((res) => res.json())
      .then((data) => {
        if (data?.success) {
          setStocks(data.stocks || []);
          setErrorText("");
        } else {
          setStocks([]);
          setErrorText("後端回傳失敗");
        }
      })
      .catch((err) => {
        console.error("讀取股票資料失敗:", err);
        setStocks([]);
        setErrorText("無法連線到後端，請稍後再試");
      })
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    setCurrentPage(1);
  }, [selectedCategory, searchTerm, rankType]);

  const getCategoryStocks = (categoryKey: string) => {
    switch (categoryKey) {
      case "all":
        return stocks;
      case "etf":
        return stocks.filter((s) => s.category === "etf" || s.market === "ETF");
      case "0-10":
        return stocks.filter(
          (s) => s.category !== "etf" && s.price >= 0 && s.price < 10
        );
      case "10-20":
        return stocks.filter(
          (s) => s.category !== "etf" && s.price >= 10 && s.price < 20
        );
      case "20-50":
        return stocks.filter(
          (s) => s.category !== "etf" && s.price >= 20 && s.price < 50
        );
      case "50-100":
        return stocks.filter(
          (s) => s.category !== "etf" && s.price >= 50 && s.price < 100
        );
      case "100-200":
        return stocks.filter(
          (s) => s.category !== "etf" && s.price >= 100 && s.price < 200
        );
      case "200-500":
        return stocks.filter(
          (s) => s.category !== "etf" && s.price >= 200 && s.price < 500
        );
      case "500-1000":
        return stocks.filter(
          (s) => s.category !== "etf" && s.price >= 500 && s.price < 1000
        );
      case "1000+":
        return stocks.filter((s) => s.category !== "etf" && s.price >= 1000);
      default:
        return stocks;
    }
  };

  const categoryCounts = useMemo(() => {
    const counts: Record<string, number> = {};
    for (const category of PRICE_CATEGORIES) {
      counts[category.key] = getCategoryStocks(category.key).length;
    }
    return counts;
  }, [stocks]);

  const filteredStocks = useMemo(() => {
    let result = getCategoryStocks(selectedCategory);

    if (searchTerm.trim()) {
      const keyword = searchTerm.trim().toLowerCase();
      result = result.filter(
        (s) =>
          s.symbol.toLowerCase().includes(keyword) ||
          s.name.toLowerCase().includes(keyword)
      );
    }

    return result;
  }, [stocks, selectedCategory, searchTerm]);

  const recommendedStocks = useMemo(() => {
    const pool = stocks.filter((s) => s.category !== "etf");
    return [...pool]
      .sort((a, b) => (b.score || 0) - (a.score || 0))
      .slice(0, 10);
  }, [stocks]);

  const sortedStocks = useMemo(() => {
    const arr = [...filteredStocks];

    if (rankType === "up") {
      arr.sort((a, b) => b.change_percent - a.change_percent);
    } else if (rankType === "down") {
      arr.sort((a, b) => a.change_percent - b.change_percent);
    } else {
      arr.sort((a, b) => (b.volume || 0) - (a.volume || 0));
    }

    return arr;
  }, [filteredStocks, rankType]);

  const totalPages = Math.max(1, Math.ceil(sortedStocks.length / PAGE_SIZE));

  const pagedStocks = useMemo(() => {
    const start = (currentPage - 1) * PAGE_SIZE;
    return sortedStocks.slice(start, start + PAGE_SIZE);
  }, [sortedStocks, currentPage]);

  const pageNumbers = useMemo(() => {
    const pages: number[] = [];
    let start = Math.max(1, currentPage - 2);
    let end = Math.min(totalPages, currentPage + 2);

    if (currentPage <= 3) end = Math.min(totalPages, 5);
    if (currentPage >= totalPages - 2) start = Math.max(1, totalPages - 4);

    for (let i = start; i <= end; i++) {
      pages.push(i);
    }
    return pages;
  }, [currentPage, totalPages]);

  return (
    <main className="page">
      <div className="container">
        <header className="hero">
          <h1>台股分類瀏覽</h1>
          <p>上市 / 上櫃 / ETF　價格分類、搜尋、排序、推薦</p>
        </header>

        <div className="top-grid">
          <section className="panel left-panel">
            <h2>價格分類 / 篩選</h2>

            <div className="category-list">
              {PRICE_CATEGORIES.map((category) => (
                <button
                  key={category.key}
                  type="button"
                  onClick={() => setSelectedCategory(category.key)}
                  className={`category-btn ${
                    selectedCategory === category.key ? "active" : ""
                  }`}
                >
                  <span>{category.label}</span>
                  <span className="count">({categoryCounts[category.key] || 0})</span>
                </button>
              ))}
            </div>

            <div className="search-box">
              <input
                type="text"
                placeholder="搜尋股票代號 / 名稱"
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
              />
            </div>

            <div className="sort-row">
              <button
                type="button"
                className={rankType === "up" ? "sort-btn active" : "sort-btn"}
                onClick={() => setRankType("up")}
              >
                漲幅排序
              </button>
              <button
                type="button"
                className={rankType === "down" ? "sort-btn active" : "sort-btn"}
                onClick={() => setRankType("down")}
              >
                跌幅排序
              </button>
              <button
                type="button"
                className={rankType === "volume" ? "sort-btn active" : "sort-btn"}
                onClick={() => setRankType("volume")}
              >
                成交量排序
              </button>
            </div>
          </section>

          <section className="panel recommend-panel">
            <h2>推薦 10 檔</h2>

            <div className="recommend-list">
              {recommendedStocks.map((stock) => (
                <div key={stock.symbol} className="recommend-card">
                  <div className="recommend-top">
                    <div>
                      <div className="recommend-title">
                        {stock.symbol} {stock.name}
                      </div>
                      <div className="recommend-sub">
                        {stock.market} / 分數 {stock.score ?? 0}
                      </div>
                    </div>
                    <div
                      className={
                        stock.change_percent >= 0
                          ? "up-text recommend-change"
                          : "down-text recommend-change"
                      }
                    >
                      {stock.change_percent >= 0 ? "+" : ""}
                      {stock.change_percent}%
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </section>
        </div>

        <section className="panel list-panel">
          <div className="list-header">
            <div>
              <h2>股票列表</h2>
              <div className="list-subtitle">
                目前分類：{
                  PRICE_CATEGORIES.find((x) => x.key === selectedCategory)?.label
                }　/　共 {sortedStocks.length} 檔
              </div>
            </div>
          </div>

          {loading ? (
            <div className="status-box">資料載入中...</div>
          ) : errorText ? (
            <div className="status-box error">{errorText}</div>
          ) : pagedStocks.length === 0 ? (
            <div className="status-box">查無資料</div>
          ) : (
            <>
              <div className="table-wrap">
                <table className="stock-table">
                  <thead>
                    <tr>
                      <th>代號</th>
                      <th>名稱</th>
                      <th>市場</th>
                      <th>價格</th>
                      <th>漲跌</th>
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
                    {pagedStocks.map((stock) => (
                      <tr key={`${stock.market}-${stock.symbol}`}>
                        <td>{stock.symbol}</td>
                        <td>{stock.name}</td>
                        <td>{stock.market}</td>
                        <td>{stock.price}</td>
                        <td className={stock.change >= 0 ? "up-text" : "down-text"}>
                          {stock.change >= 0 ? "+" : ""}
                          {stock.change}
                        </td>
                        <td
                          className={
                            stock.change_percent >= 0 ? "up-text" : "down-text"
                          }
                        >
                          {stock.change_percent >= 0 ? "+" : ""}
                          {stock.change_percent}%
                        </td>
                        <td>{(stock.volume || 0).toLocaleString()}</td>
                        <td>{stock.signal || "-"}</td>
                        <td>{stock.score ?? 0}</td>
                        <td>{stock.entry_price || "-"}</td>
                        <td>{stock.target_price || "-"}</td>
                        <td>{stock.stop_loss || "-"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              <div className="pagination">
                <button
                  type="button"
                  onClick={() => setCurrentPage((p) => Math.max(1, p - 1))}
                  disabled={currentPage === 1}
                  className="page-btn"
                >
                  上一頁
                </button>

                {pageNumbers.map((page) => (
                  <button
                    key={page}
                    type="button"
                    onClick={() => setCurrentPage(page)}
                    className={currentPage === page ? "page-btn active" : "page-btn"}
                  >
                    {page}
                  </button>
                ))}

                <button
                  type="button"
                  onClick={() => setCurrentPage((p) => Math.min(totalPages, p + 1))}
                  disabled={currentPage === totalPages}
                  className="page-btn"
                >
                  下一頁
                </button>
              </div>
            </>
          )}
        </section>
      </div>
    </main>
  );
}
