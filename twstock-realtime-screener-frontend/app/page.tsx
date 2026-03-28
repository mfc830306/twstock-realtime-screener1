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

  useEffect(() => {
    fetch(BACKEND_URL)
      .then((res) => res.json())
      .then((data) => {
        setStocks(data.stocks || []);
      })
      .catch((err) => {
        console.error("讀取股票資料失敗:", err);
        setStocks([]);
      })
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    setCurrentPage(1);
  }, [selectedCategory, searchTerm]);

  const getCategoryStocks = (categoryKey: string) => {
    switch (categoryKey) {
      case "all":
        return stocks;
      case "etf":
        return stocks.filter((s) => s.category === "etf" || s.market === "ETF");
      case "0-10":
        return stocks.filter((s) => s.category !== "etf" && s.price >= 0 && s.price < 10);
      case "10-20":
        return stocks.filter((s) => s.category !== "etf" && s.price >= 10 && s.price < 20);
      case "20-50":
        return stocks.filter((s) => s.category !== "etf" && s.price >= 20 && s.price < 50);
      case "50-100":
        return stocks.filter((s) => s.category !== "etf" && s.price >= 50 && s.price < 100);
      case "100-200":
        return stocks.filter((s) => s.category !== "etf" && s.price >= 100 && s.price < 200);
      case "200-500":
        return stocks.filter((s) => s.category !== "etf" && s.price >= 200 && s.price < 500);
      case "500-1000":
        return stocks.filter((s) => s.category !== "etf" && s.price >= 500 && s.price < 1000);
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
    } else if (rankType === "volume") {
      arr.sort((a, b) => (b.volume || 0) - (a.volume || 0));
    }

    return arr;
  }, [filteredStocks, rankType]);

  const totalPages = Math.max(1, Math.ceil(sortedStocks.length / PAGE_SIZE));
  const pagedStocks = sortedStocks.slice(
    (currentPage - 1) * PAGE_SIZE,
    currentPage * PAGE_SIZE
  );

  const pageNumbers = useMemo(() => {
    const pages: number[] = [];
    const start = Math.max(1, currentPage - 2);
    const end = Math.min(totalPages, currentPage + 2);
    for (let i = start; i <= end; i++) pages.push(i);
    return pages;
  }, [currentPage, totalPages]);

  return (
    <main className="min-h-screen bg-[#031b3d] text-white px-4 py-6">
      <div className="mx-auto max-w-7xl">
        <h1 className="text-3xl font-bold mb-6">台股分類瀏覽</h1>

        <div className="grid grid-cols-1 xl:grid-cols-[320px_1fr] gap-6">
          <div className="space-y-6">
            <section className="rounded-2xl border border-blue-900 bg-[#062a57] p-4 shadow-lg">
              <h2 className="text-2xl font-bold mb-4">價格分類 / 篩選</h2>

              <div className="space-y-3">
                {PRICE_CATEGORIES.map((category) => (
                  <button
                    key={category.key}
                    onClick={() => setSelectedCategory(category.key)}
                    className={`w-full rounded-2xl border px-4 py-3 text-left transition ${
                      selectedCategory === category.key
                        ? "border-blue-400 bg-blue-800"
                        : "border-blue-900 bg-white/5 hover:bg-white/10"
                    }`}
                  >
                    <div className="flex items-center justify-between">
                      <span className="font-semibold">{category.label}</span>
                      <span className="text-blue-200">({categoryCounts[category.key] || 0})</span>
                    </div>
                  </button>
                ))}
              </div>

              <div className="mt-6 border-t border-blue-900 pt-4">
                <input
                  type="text"
                  placeholder="搜尋股票代號 / 名稱"
                  value={searchTerm}
                  onChange={(e) => setSearchTerm(e.target.value)}
                  className="w-full rounded-xl border border-blue-700 bg-[#0a356d] px-4 py-3 outline-none placeholder:text-blue-200"
                />
              </div>

              <div className="mt-4 flex flex-wrap gap-2">
                <button
                  onClick={() => setRankType("up")}
                  className={`rounded-xl px-3 py-2 text-sm ${
                    rankType === "up" ? "bg-blue-600" : "bg-white/10"
                  }`}
                >
                  漲幅排序
                </button>
                <button
                  onClick={() => setRankType("down")}
                  className={`rounded-xl px-3 py-2 text-sm ${
                    rankType === "down" ? "bg-blue-600" : "bg-white/10"
                  }`}
                >
                  跌幅排序
                </button>
                <button
                  onClick={() => setRankType("volume")}
                  className={`rounded-xl px-3 py-2 text-sm ${
                    rankType === "volume" ? "bg-blue-600" : "bg-white/10"
                  }`}
                >
                  成交量排序
                </button>
              </div>
            </section>

            <section className="rounded-2xl border border-blue-900 bg-[#062a57] p-4 shadow-lg">
              <h2 className="text-2xl font-bold mb-4">推薦 10 檔</h2>

              <div className="space-y-3">
                {recommendedStocks.map((stock) => (
                  <div
                    key={stock.symbol}
                    className="rounded-xl border border-blue-900 bg-white/5 p-3"
                  >
                    <div className="flex items-center justify-between">
                      <div>
                        <div className="font-bold">
                          {stock.symbol} {stock.name}
                        </div>
                        <div className="text-sm text-blue-200">
                          {stock.market} / 分數 {stock.score ?? 0}
                        </div>
                      </div>
                      <div
                        className={
                          stock.change_percent >= 0 ? "text-red-400" : "text-green-400"
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

          <section className="rounded-2xl border border-blue-900 bg-[#062a57] p-4 shadow-lg overflow-hidden">
            <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
              <h2 className="text-2xl font-bold">
                股票列表
                <span className="ml-3 text-base font-normal text-blue-200">
                  共 {sortedStocks.length} 檔
                </span>
              </h2>
            </div>

            {loading ? (
              <div className="py-10 text-center text-blue-200">載入中...</div>
            ) : pagedStocks.length === 0 ? (
              <div className="py-10 text-center text-blue-200">查無資料</div>
            ) : (
              <>
                <div className="overflow-x-auto">
                  <table className="w-full min-w-[1100px] border-collapse">
                    <thead>
                      <tr className="border-b border-blue-900 text-left text-blue-200">
                        <th className="px-3 py-3">代號</th>
                        <th className="px-3 py-3">名稱</th>
                        <th className="px-3 py-3">市場</th>
                        <th className="px-3 py-3">價格</th>
                        <th className="px-3 py-3">漲跌</th>
                        <th className="px-3 py-3">漲跌幅</th>
                        <th className="px-3 py-3">成交量</th>
                        <th className="px-3 py-3">訊號</th>
                        <th className="px-3 py-3">推薦分數</th>
                        <th className="px-3 py-3">進場價</th>
                        <th className="px-3 py-3">目標價</th>
                        <th className="px-3 py-3">停損價</th>
                      </tr>
                    </thead>
                    <tbody>
                      {pagedStocks.map((stock) => (
                        <tr
                          key={`${stock.market}-${stock.symbol}`}
                          className="border-b border-blue-950/70 hover:bg-white/5"
                        >
                          <td className="px-3 py-3 font-semibold">{stock.symbol}</td>
                          <td className="px-3 py-3">{stock.name}</td>
                          <td className="px-3 py-3">{stock.market}</td>
                          <td className="px-3 py-3">{stock.price}</td>
                          <td
                            className={`px-3 py-3 ${
                              stock.change >= 0 ? "text-red-400" : "text-green-400"
                            }`}
                          >
                            {stock.change >= 0 ? "+" : ""}
                            {stock.change}
                          </td>
                          <td
                            className={`px-3 py-3 ${
                              stock.change_percent >= 0
                                ? "text-red-400"
                                : "text-green-400"
                            }`}
                          >
                            {stock.change_percent >= 0 ? "+" : ""}
                            {stock.change_percent}%
                          </td>
                          <td className="px-3 py-3">
                            {(stock.volume || 0).toLocaleString()}
                          </td>
                          <td className="px-3 py-3">{stock.signal || "-"}</td>
                          <td className="px-3 py-3">{stock.score ?? 0}</td>
                          <td className="px-3 py-3">{stock.entry_price || "-"}</td>
                          <td className="px-3 py-3">{stock.target_price || "-"}</td>
                          <td className="px-3 py-3">{stock.stop_loss || "-"}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>

                <div className="mt-5 flex flex-wrap items-center justify-center gap-2">
                  <button
                    onClick={() => setCurrentPage((p) => Math.max(1, p - 1))}
                    disabled={currentPage === 1}
                    className="rounded-lg bg-white/10 px-3 py-2 disabled:opacity-40"
                  >
                    上一頁
                  </button>

                  {pageNumbers.map((page) => (
                    <button
                      key={page}
                      onClick={() => setCurrentPage(page)}
                      className={`rounded-lg px-3 py-2 ${
                        currentPage === page ? "bg-blue-600" : "bg-white/10"
                      }`}
                    >
                      {page}
                    </button>
                  ))}

                  <button
                    onClick={() => setCurrentPage((p) => Math.min(totalPages, p + 1))}
                    disabled={currentPage === totalPages}
                    className="rounded-lg bg-white/10 px-3 py-2 disabled:opacity-40"
                  >
                    下一頁
                  </button>
                </div>
              </>
            )}
          </section>
        </div>
      </div>
    </main>
  );
}
