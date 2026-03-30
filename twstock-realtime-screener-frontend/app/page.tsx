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
];

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
  if (change > 0) return "text-red-500";
  if (change < 0) return "text-green-500";
  return "text-slate-300";
}

function getSignalDot(status?: string) {
  if (!status) return "bg-slate-500";
  if (status.includes("開盤")) return "bg-green-500";
  if (status.includes("收盤")) return "bg-red-500";
  return "bg-yellow-500";
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

  const totalPages = Math.max(1, Math.ceil(filteredStocks.length / PAGE_SIZE));

  const pagedStocks = useMemo(() => {
    const start = (currentPage - 1) * PAGE_SIZE;
    return filteredStocks.slice(start, start + PAGE_SIZE);
  }, [filteredStocks, currentPage]);

  const recommendedStocks = useMemo(() => {
    return [...stocks]
      .filter((s) => matchMarket(s, selectedMarket))
      .sort((a, b) => safeNumber(b.score) - safeNumber(a.score))
      .slice(0, 10);
  }, [stocks, selectedMarket]);

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

  const pageNumbers = useMemo(() => {
    const pages: number[] = [];
    const start = Math.max(1, currentPage - 3);
    const end = Math.min(totalPages, currentPage + 3);
    for (let i = start; i <= end; i++) pages.push(i);
    return pages;
  }, [currentPage, totalPages]);

  return (
    <main className="min-h-screen bg-slate-950 text-white">
      <div className="mx-auto max-w-7xl px-4 py-5 md:px-6">
        <div className="mb-5 rounded-2xl border border-slate-800 bg-slate-900 p-4 shadow-lg">
          <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
            <div className="flex flex-wrap items-center gap-4 text-sm">
              <div className="flex items-center gap-2">
                <span
                  className={`inline-block h-3 w-3 rounded-full ${getSignalDot(
                    marketStatus
                  )}`}
                />
                <span className="text-slate-300">市場狀態：</span>
                <span className="font-semibold text-white">
                  {marketStatus || "-"}
                </span>
              </div>

              <div>
                <span className="text-slate-300">資料日期：</span>
                <span className="font-semibold text-white">
                  {dataDate || "-"}
                </span>
              </div>

              <div>
                <span className="text-slate-300">最後更新：</span>
                <span className="font-semibold text-white">
                  {lastUpdate || "-"}
                </span>
              </div>
            </div>

            <button
              onClick={fetchStocks}
              className="rounded-xl bg-blue-600 px-4 py-2 text-sm font-semibold hover:bg-blue-500"
            >
              重新整理
            </button>
          </div>
        </div>

        <div className="grid gap-5 lg:grid-cols-[320px_minmax(0,1fr)]">
          <aside className="space-y-5">
            <section className="rounded-2xl border border-slate-800 bg-slate-900 p-4 shadow-lg">
              <h2 className="mb-3 text-lg font-bold">篩選與分類</h2>

              <div className="mb-4">
                <label className="mb-2 block text-sm text-slate-300">市場分類</label>
                <div className="grid grid-cols-2 gap-2">
                  {marketTabs.map((tab) => {
                    const active = selectedMarket === tab.key;
                    return (
                      <button
                        key={tab.key}
                        onClick={() => setSelectedMarket(tab.key)}
                        className={`rounded-xl border px-3 py-2 text-sm font-semibold transition ${
                          active
                            ? "border-blue-500 bg-blue-600 text-white"
                            : "border-slate-700 bg-slate-950 text-slate-200 hover:border-slate-500"
                        }`}
                      >
                        {tab.label} ({marketCounts[tab.key] || 0})
                      </button>
                    );
                  })}
                </div>
              </div>

              <div className="mb-4">
                <label className="mb-2 block text-sm text-slate-300">搜尋股票</label>
                <input
                  type="text"
                  value={searchTerm}
                  onChange={(e) => setSearchTerm(e.target.value)}
                  placeholder="輸入代號或名稱"
                  className="w-full rounded-xl border border-slate-700 bg-slate-950 px-3 py-2 text-white outline-none placeholder:text-slate-500 focus:border-blue-500"
                />
              </div>

              <div className="mb-4">
                <label className="mb-2 block text-sm text-slate-300">排序方式</label>
                <select
                  value={sortType}
                  onChange={(e) =>
                    setSortType(
                      e.target.value as "score" | "up" | "down" | "volume"
                    )
                  }
                  className="w-full rounded-xl border border-slate-700 bg-slate-950 px-3 py-2 text-white outline-none focus:border-blue-500"
                >
                  <option value="score">推薦分數</option>
                  <option value="up">漲幅 % 由高到低</option>
                  <option value="down">跌幅 % 由低到高</option>
                  <option value="volume">成交量由高到低</option>
                </select>
              </div>

              <div>
                <label className="mb-2 block text-sm text-slate-300">股價分類</label>
                <div className="grid grid-cols-2 gap-2">
                  {priceRanges.map((range) => {
                    const active = selectedCategory === range.key;
                    return (
                      <button
                        key={range.key}
                        onClick={() => setSelectedCategory(range.key)}
                        className={`rounded-xl border px-3 py-2 text-sm font-semibold transition ${
                          active
                            ? "border-blue-500 bg-blue-600 text-white"
                            : "border-slate-700 bg-slate-950 text-slate-200 hover:border-slate-500"
                        }`}
                      >
                        {range.label} ({categoryCounts[range.key] || 0})
                      </button>
                    );
                  })}
                </div>
              </div>
            </section>

            <section className="rounded-2xl border border-slate-800 bg-slate-900 p-4 shadow-lg">
              <h2 className="mb-3 text-lg font-bold">
                推薦 10 檔
                {selectedMarket === "tse"
                  ? "（上市）"
                  : selectedMarket === "otc"
                  ? "（上櫃）"
                  : selectedMarket === "etf"
                  ? "（ETF）"
                  : ""}
              </h2>

              <div className="space-y-3">
                {recommendedStocks.map((stock, idx) => {
                  const change = safeNumber(stock.change);
                  const changePercent = safeNumber(stock.change_percent);

                  return (
                    <div
                      key={`${stock.symbol}-${idx}`}
                      className="rounded-xl border border-slate-800 bg-slate-950 p-3"
                    >
                      <div className="mb-1 flex items-start justify-between gap-2">
                        <div>
                          <div className="font-bold">
                            {stock.symbol} {stock.name}
                          </div>
                          <div className="text-xs text-slate-400">
                            {isETFStock(stock)
                              ? "ETF"
                              : stock.market || "-"}
                          </div>
                        </div>

                        <div className="text-right">
                          <div className="font-bold">{stock.price}</div>
                          <div className={`text-sm font-semibold ${getChangeClass(change)}`}>
                            {change > 0 ? "+" : ""}
                            {change.toFixed(2)} / {changePercent > 0 ? "+" : ""}
                            {changePercent.toFixed(2)}%
                          </div>
                        </div>
                      </div>

                      <div className="mt-2 space-y-1 text-sm text-slate-300">
                        <div>進場價位：{stock.entry_price || "-"}</div>
                        <div>目標價位：{stock.target_price || "-"}</div>
                        <div>止損價位：{stock.stop_loss || "-"}</div>
                        <div>推薦原因：{stock.reason || "-"}</div>
                      </div>
                    </div>
                  );
                })}
              </div>
            </section>
          </aside>

          <section className="rounded-2xl border border-slate-800 bg-slate-900 p-4 shadow-lg">
            <div className="mb-4 flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
              <div>
                <h2 className="text-xl font-bold">
                  股票列表
                  {selectedMarket === "tse"
                    ? "（上市）"
                    : selectedMarket === "otc"
                    ? "（上櫃）"
                    : selectedMarket === "etf"
                    ? "（ETF）"
                    : ""}
                </h2>
                <div className="mt-1 text-sm text-slate-400">
                  共 {filteredStocks.length.toLocaleString("zh-TW")} 檔
                </div>
              </div>

              <div className="flex flex-wrap items-center gap-2">
                <button
                  onClick={() => goToPage(currentPage - 1)}
                  disabled={currentPage === 1}
                  className="rounded-xl border border-slate-700 px-3 py-2 text-sm disabled:cursor-not-allowed disabled:opacity-40"
                >
                  上一頁
                </button>

                <div className="flex items-center gap-1">
                  {pageNumbers.map((page) => (
                    <button
                      key={page}
                      onClick={() => goToPage(page)}
                      className={`min-w-[40px] rounded-xl px-3 py-2 text-sm font-semibold ${
                        currentPage === page
                          ? "bg-blue-600 text-white"
                          : "border border-slate-700 text-slate-200"
                      }`}
                    >
                      {page}
                    </button>
                  ))}
                </div>

                <button
                  onClick={() => goToPage(currentPage + 1)}
                  disabled={currentPage === totalPages}
                  className="rounded-xl border border-slate-700 px-3 py-2 text-sm disabled:cursor-not-allowed disabled:opacity-40"
                >
                  下一頁
                </button>

                <div className="ml-1 flex items-center gap-2">
                  <input
                    type="number"
                    min={1}
                    max={totalPages}
                    value={jumpPage}
                    onChange={(e) => setJumpPage(e.target.value)}
                    placeholder="頁碼"
                    className="w-20 rounded-xl border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-white outline-none focus:border-blue-500"
                  />
                  <button
                    onClick={handleJumpPage}
                    className="rounded-xl bg-blue-600 px-3 py-2 text-sm font-semibold hover:bg-blue-500"
                  >
                    跳頁
                  </button>
                </div>
              </div>
            </div>

            {loading ? (
              <div className="rounded-xl border border-slate-800 bg-slate-950 p-6 text-center text-slate-300">
                載入中...
              </div>
            ) : error ? (
              <div className="rounded-xl border border-red-900 bg-red-950/40 p-6 text-center text-red-300">
                {error}
              </div>
            ) : pagedStocks.length === 0 ? (
              <div className="rounded-xl border border-slate-800 bg-slate-950 p-6 text-center text-slate-300">
                查無符合條件的股票
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="min-w-full text-sm">
                  <thead>
                    <tr className="border-b border-slate-800 text-slate-300">
                      <th className="px-3 py-3 text-left">股票</th>
                      <th className="px-3 py-3 text-right">價格</th>
                      <th className="px-3 py-3 text-right">漲跌</th>
                      <th className="px-3 py-3 text-right">漲跌幅%</th>
                      <th className="px-3 py-3 text-right">成交量</th>
                      <th className="px-3 py-3 text-right">分數</th>
                      <th className="px-3 py-3 text-left">訊號</th>
                    </tr>
                  </thead>
                  <tbody>
                    {pagedStocks.map((stock) => {
                      const change = safeNumber(stock.change);
                      const changePercent = safeNumber(stock.change_percent);

                      return (
                        <tr
                          key={stock.symbol}
                          className="border-b border-slate-800/80 hover:bg-slate-800/40"
                        >
                          <td className="px-3 py-3">
                            <div className="font-semibold text-white">
                              {stock.symbol} {stock.name}
                            </div>
                            <div className="text-xs text-slate-400">
                              {isETFStock(stock) ? "ETF" : stock.market || "-"}
                            </div>
                          </td>

                          <td className="px-3 py-3 text-right font-semibold">
                            {stock.price}
                          </td>

                          <td
                            className={`px-3 py-3 text-right font-semibold ${getChangeClass(
                              change
                            )}`}
                          >
                            {change > 0 ? "+" : ""}
                            {change.toFixed(2)}
                          </td>

                          <td
                            className={`px-3 py-3 text-right font-semibold ${getChangeClass(
                              change
                            )}`}
                          >
                            {changePercent > 0 ? "+" : ""}
                            {changePercent.toFixed(2)}%
                          </td>

                          <td className="px-3 py-3 text-right text-slate-300">
                            {formatVolume(stock.volume)}
                          </td>

                          <td className="px-3 py-3 text-right text-slate-300">
                            {safeNumber(stock.score)}
                          </td>

                          <td className="px-3 py-3 text-left">
                            <span className="rounded-lg bg-slate-800 px-2 py-1 text-xs text-slate-200">
                              {stock.signal || "-"}
                            </span>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}

            <div className="mt-4 flex flex-col gap-2 text-sm text-slate-400 md:flex-row md:items-center md:justify-between">
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
