"use client";

import { useEffect, useMemo, useState } from "react";

type Stock = {
  market?: string;
  symbol: string;
  name: string;
  price: number;
  change?: number;
  change_percent?: number;
  volume?: number;
  score?: number;
  signal?: string;
  reason?: string;
  entry_price?: string;
  target_price?: string;
  stop_loss?: string;
  update_time?: string;
};

type ApiResponse = {
  success?: boolean;
  market_status?: string;
  data_date?: string;
  last_update?: string;
  total?: number;
  stocks?: Stock[];
  message?: string;
};

const BACKEND_URL =
  process.env.NEXT_PUBLIC_BACKEND_URL ||
  "https://twstock-realtime-screener1.onrender.com/stocks";

const PAGE_SIZE = 20;

const marketTabs = [
  { key: "all", label: "全部" },
  { key: "tse", label: "上市" },
  { key: "otc", label: "上櫃" },
  { key: "etf", label: "ETF" },
] as const;

const priceRanges = [
  { key: "all", label: "全部" },
  { key: "0-10", label: "0~10" },
  { key: "10-20", label: "10~20" },
  { key: "20-50", label: "20~50" },
  { key: "50-100", label: "50~100" },
  { key: "100-200", label: "100~200" },
  { key: "200-500", label: "200~500" },
  { key: "500-1000", label: "500~1000" },
  { key: "1000+", label: "1000+" },
] as const;

type MarketTabKey = (typeof marketTabs)[number]["key"];

function safeNumber(value: unknown, fallback = 0) {
  const n = Number(value);
  return Number.isFinite(n) ? n : fallback;
}

function isETFStock(stock: Stock) {
  const symbol = String(stock.symbol || "").trim();
  const name = String(stock.name || "").trim();

  if (/^00\d+/.test(symbol)) return true;
  if (name.includes("ETF")) return true;
  if (name.includes("槓桿") || name.includes("反向")) return true;

  return false;
}

function matchMarket(stock: Stock, selectedMarket: MarketTabKey) {
  if (selectedMarket === "all") return true;

  const market = String(stock.market || "").trim();

  if (selectedMarket === "etf") {
    return isETFStock(stock);
  }

  if (selectedMarket === "tse") {
    return market === "上市" && !isETFStock(stock);
  }

  if (selectedMarket === "otc") {
    return market === "上櫃" && !isETFStock(stock);
  }

  return true;
}

function matchPriceCategory(price: number, category: string) {
  if (category === "all") return true;
  if (category === "0-10") return price >= 0 && price < 10;
  if (category === "10-20") return price >= 10 && price < 20;
  if (category === "20-50") return price >= 20 && price < 50;
  if (category === "50-100") return price >= 50 && price < 100;
  if (category === "100-200") return price >= 100 && price < 200;
  if (category === "200-500") return price >= 200 && price < 500;
  if (category === "500-1000") return price >= 500 && price < 1000;
  if (category === "1000+") return price >= 1000;
  return true;
}

function formatVolume(volume?: number) {
  const v = safeNumber(volume);
  if (v >= 100000000) return `${(v / 100000000).toFixed(2)} 億`;
  if (v >= 10000) return `${(v / 10000).toFixed(2)} 萬`;
  return v.toLocaleString("zh-TW");
}

function getChangeClass(change: number) {
  if (change > 0) return "change-up";
  if (change < 0) return "change-down";
  return "change-flat";
}

function getMarketStatusDotClass(status?: string) {
  if (!status) return "status-dot status-dot-neutral";
  if (status.includes("開盤")) return "status-dot status-dot-open";
  if (status.includes("收盤")) return "status-dot status-dot-close";
  return "status-dot status-dot-neutral";
}

export default function Home() {
  const [stocks, setStocks] = useState<Stock[]>([]);
  const [marketStatus, setMarketStatus] = useState("");
  const [dataDate, setDataDate] = useState("");
  const [lastUpdate, setLastUpdate] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const [searchTerm, setSearchTerm] = useState("");
  const [selectedMarket, setSelectedMarket] = useState<MarketTabKey>("all");
  const [selectedCategory, setSelectedCategory] = useState("all");
  const [sortType, setSortType] = useState<"score" | "up" | "down" | "volume">(
    "score"
  );
  const [currentPage, setCurrentPage] = useState(1);
  const [jumpPage, setJumpPage] = useState("");

  async function fetchStocks() {
    try {
      setLoading(true);
      setError("");

      const res = await fetch(BACKEND_URL, { cache: "no-store" });
      const data: ApiResponse = await res.json();

      if (!res.ok || data.success === false) {
        throw new Error(data.message || "資料讀取失敗");
      }

      const normalized = (data.stocks || []).map((s) => ({
        ...s,
        price: safeNumber(s.price),
        change: safeNumber(s.change),
        change_percent: safeNumber(s.change_percent),
        volume: safeNumber(s.volume),
        score: safeNumber(s.score),
      }));

      setStocks(normalized);
      setMarketStatus(data.market_status || "");
      setDataDate(data.data_date || "");
      setLastUpdate(data.last_update || "");
    } catch (err) {
      console.error(err);
      setError(err instanceof Error ? err.message : "發生未知錯誤");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    fetchStocks();
    const timer = setInterval(fetchStocks, 60000);
    return () => clearInterval(timer);
  }, []);

  useEffect(() => {
    setCurrentPage(1);
  }, [searchTerm, selectedMarket, selectedCategory, sortType]);

  const marketCounts = useMemo(() => {
    return {
      all: stocks.length,
      tse: stocks.filter((s) => matchMarket(s, "tse")).length,
      otc: stocks.filter((s) => matchMarket(s, "otc")).length,
      etf: stocks.filter((s) => matchMarket(s, "etf")).length,
    };
  }, [stocks]);

  const categoryCounts = useMemo(() => {
    const baseList = stocks.filter((s) => matchMarket(s, selectedMarket));
    const result: Record<string, number> = {};

    for (const range of priceRanges) {
      result[range.key] = baseList.filter((s) =>
        matchPriceCategory(s.price, range.key)
      ).length;
    }

    return result;
  }, [stocks, selectedMarket]);

  const filteredStocks = useMemo(() => {
    const keyword = searchTerm.trim().toLowerCase();

    const list = stocks.filter((stock) => {
      const hitKeyword =
        !keyword ||
        stock.symbol.toLowerCase().includes(keyword) ||
        stock.name.toLowerCase().includes(keyword);

      const hitMarket = matchMarket(stock, selectedMarket);
      const hitCategory = matchPriceCategory(stock.price, selectedCategory);

      return hitKeyword && hitMarket && hitCategory;
    });

    const sorted = [...list].sort((a, b) => {
      if (sortType === "up") {
        return safeNumber(b.change_percent) - safeNumber(a.change_percent);
      }
      if (sortType === "down") {
        return safeNumber(a.change_percent) - safeNumber(b.change_percent);
      }
      if (sortType === "volume") {
        return safeNumber(b.volume) - safeNumber(a.volume);
      }
      return safeNumber(b.score) - safeNumber(a.score);
    });

    return sorted;
  }, [stocks, searchTerm, selectedMarket, selectedCategory, sortType]);

  const recommendedStocks = useMemo(() => {
    return [...stocks]
      .filter((s) => matchMarket(s, selectedMarket))
      .sort((a, b) => safeNumber(b.score) - safeNumber(a.score))
      .slice(0, 10);
  }, [stocks, selectedMarket]);

  const totalPages = Math.max(1, Math.ceil(filteredStocks.length / PAGE_SIZE));

  const pagedStocks = useMemo(() => {
    const start = (currentPage - 1) * PAGE_SIZE;
    return filteredStocks.slice(start, start + PAGE_SIZE);
  }, [filteredStocks, currentPage]);

  const pageNumbers = useMemo(() => {
    const pages: number[] = [];
    const start = Math.max(1, currentPage - 3);
    const end = Math.min(totalPages, currentPage + 3);
    for (let i = start; i <= end; i++) pages.push(i);
    return pages;
  }, [currentPage, totalPages]);

  function goToPage(page: number) {
    const next = Math.min(Math.max(page, 1), totalPages);
    setCurrentPage(next);
  }

  function handleJumpPage() {
    const page = Number(jumpPage);
    if (!Number.isFinite(page)) return;
    goToPage(page);
    setJumpPage("");
  }

  return (
    <main className="page-shell">
      <div className="page-wrap">
        <section className="top-bar">
          <div className="top-bar-left">
            <div className="status-line">
              <span className={getMarketStatusDotClass(marketStatus)} />
              <span className="label">市場狀態：</span>
              <span className="value">{marketStatus || "-"}</span>
            </div>
            <div className="status-line">
              <span className="label">資料日期：</span>
              <span className="value">{dataDate || "-"}</span>
            </div>
            <div className="status-line">
              <span className="label">最後更新：</span>
              <span className="value">{lastUpdate || "-"}</span>
            </div>
          </div>

          <button className="refresh-btn" onClick={fetchStocks}>
            重新整理
          </button>
        </section>

        <div className="content-grid">
          <aside className="left-column">
            <section className="panel">
              <h2 className="panel-title">篩選與分類</h2>

              <div className="field-block">
                <div className="field-label">市場分類</div>
                <div className="tab-grid">
                  {marketTabs.map((tab) => (
                    <button
                      key={tab.key}
                      onClick={() => setSelectedMarket(tab.key)}
                      className={
                        selectedMarket === tab.key
                          ? "tab-btn tab-btn-active"
                          : "tab-btn"
                      }
                    >
                      {tab.label} ({marketCounts[tab.key] || 0})
                    </button>
                  ))}
                </div>
              </div>

              <div className="field-block">
                <div className="field-label">搜尋股票</div>
                <input
                  className="control-input"
                  type="text"
                  value={searchTerm}
                  onChange={(e) => setSearchTerm(e.target.value)}
                  placeholder="輸入代號或名稱"
                />
              </div>

              <div className="field-block">
                <div className="field-label">排序方式</div>
                <select
                  className="control-input"
                  value={sortType}
                  onChange={(e) =>
                    setSortType(
                      e.target.value as "score" | "up" | "down" | "volume"
                    )
                  }
                >
                  <option value="score">推薦分數</option>
                  <option value="up">漲幅 % 由高到低</option>
                  <option value="down">跌幅 % 由低到高</option>
                  <option value="volume">成交量由高到低</option>
                </select>
              </div>

              <div className="field-block">
                <div className="field-label">股價分類</div>
                <div className="tab-grid">
                  {priceRanges.map((range) => (
                    <button
                      key={range.key}
                      onClick={() => setSelectedCategory(range.key)}
                      className={
                        selectedCategory === range.key
                          ? "tab-btn tab-btn-active"
                          : "tab-btn"
                      }
                    >
                      {range.label} ({categoryCounts[range.key] || 0})
                    </button>
                  ))}
                </div>
              </div>
            </section>

            <section className="panel">
              <h2 className="panel-title">
                推薦 10 檔
                {selectedMarket === "tse"
                  ? "（上市）"
                  : selectedMarket === "otc"
                  ? "（上櫃）"
                  : selectedMarket === "etf"
                  ? "（ETF）"
                  : ""}
              </h2>

              <div className="recommend-list">
                {recommendedStocks.map((stock, idx) => {
                  const change = safeNumber(stock.change);
                  const changePercent = safeNumber(stock.change_percent);

                  return (
                    <article className="recommend-card" key={`${stock.symbol}-${idx}`}>
                      <div className="recommend-top">
                        <div>
                          <div className="recommend-name">
                            {stock.symbol} {stock.name}
                          </div>
                          <div className="recommend-market">
                            {isETFStock(stock) ? "ETF" : stock.market || "-"}
                          </div>
                        </div>

                        <div className="recommend-price-box">
                          <div className="recommend-price">{stock.price}</div>
                          <div className={`recommend-change ${getChangeClass(change)}`}>
                            {change > 0 ? "+" : ""}
                            {change.toFixed(2)} / {changePercent > 0 ? "+" : ""}
                            {changePercent.toFixed(2)}%
                          </div>
                        </div>
                      </div>

                      <div className="recommend-info">
                        <div>進場價位：{stock.entry_price || "-"}</div>
                        <div>目標價位：{stock.target_price || "-"}</div>
                        <div>止損價位：{stock.stop_loss || "-"}</div>
                        <div>推薦原因：{stock.reason || "-"}</div>
                      </div>
                    </article>
                  );
                })}
              </div>
            </section>
          </aside>

          <section className="panel right-panel">
            <div className="list-header">
              <div>
                <h2 className="panel-title no-margin">
                  股票列表
                  {selectedMarket === "tse"
                    ? "（上市）"
                    : selectedMarket === "otc"
                    ? "（上櫃）"
                    : selectedMarket === "etf"
                    ? "（ETF）"
                    : ""}
                </h2>
                <div className="list-count">
                  共 {filteredStocks.length.toLocaleString("zh-TW")} 檔
                </div>
              </div>

              <div className="pager-toolbar">
                <button
                  className="pager-btn"
                  onClick={() => goToPage(currentPage - 1)}
                  disabled={currentPage === 1}
                >
                  上一頁
                </button>

                <div className="page-number-group">
                  {pageNumbers.map((page) => (
                    <button
                      key={page}
                      className={
                        currentPage === page
                          ? "page-number-btn page-number-btn-active"
                          : "page-number-btn"
                      }
                      onClick={() => goToPage(page)}
                    >
                      {page}
                    </button>
                  ))}
                </div>

                <button
                  className="pager-btn"
                  onClick={() => goToPage(currentPage + 1)}
                  disabled={currentPage === totalPages}
                >
                  下一頁
                </button>

                <div className="jump-box">
                  <input
                    className="jump-input"
                    type="number"
                    min={1}
                    max={totalPages}
                    value={jumpPage}
                    onChange={(e) => setJumpPage(e.target.value)}
                    placeholder="頁碼"
                  />
                  <button className="jump-btn" onClick={handleJumpPage}>
                    跳頁
                  </button>
                </div>
              </div>
            </div>

            {loading ? (
              <div className="empty-box">載入中...</div>
            ) : error ? (
              <div className="empty-box empty-box-error">{error}</div>
            ) : pagedStocks.length === 0 ? (
              <div className="empty-box">查無符合條件的股票</div>
            ) : (
              <div className="table-wrap">
                <table className="stock-table">
                  <thead>
                    <tr>
                      <th>股票</th>
                      <th className="text-right">價格</th>
                      <th className="text-right">漲跌</th>
                      <th className="text-right">漲跌幅%</th>
                      <th className="text-right">成交量</th>
                      <th className="text-right">分數</th>
                      <th>訊號</th>
                    </tr>
                  </thead>
                  <tbody>
                    {pagedStocks.map((stock) => {
                      const change = safeNumber(stock.change);
                      const changePercent = safeNumber(stock.change_percent);

                      return (
                        <tr key={stock.symbol}>
                          <td>
                            <div className="stock-name">
                              {stock.symbol} {stock.name}
                            </div>
                            <div className="stock-subtext">
                              {isETFStock(stock) ? "ETF" : stock.market || "-"}
                            </div>
                          </td>

                          <td className="text-right stock-price">{stock.price}</td>

                          <td className={`text-right ${getChangeClass(change)}`}>
                            {change > 0 ? "+" : ""}
                            {change.toFixed(2)}
                          </td>

                          <td className={`text-right ${getChangeClass(change)}`}>
                            {changePercent > 0 ? "+" : ""}
                            {changePercent.toFixed(2)}%
                          </td>

                          <td className="text-right muted-text">
                            {formatVolume(stock.volume)}
                          </td>

                          <td className="text-right muted-text">
                            {safeNumber(stock.score)}
                          </td>

                          <td>
                            <span className="signal-badge">{stock.signal || "-"}</span>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}

            <div className="list-footer">
              <div>
                第 {currentPage} / {totalPages} 頁
              </div>
              <div>每頁 {PAGE_SIZE} 檔</div>
            </div>
          </section>
        </div>
      </div>
    </main>
  );
}
