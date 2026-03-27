"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

type Stock = {
  date: string;
  market: string;
  symbol: string;
  name: string;
  price: number;
  change: number;
  change_percent: number;
  volume: number;
  score: number;
  signal?: string;
  entry_price?: string;
  target_price?: string;
  stop_loss?: string;
};

type ApiResponse = {
  success: boolean;
  source?: string;
  market?: string;
  total?: number;
  stocks: Stock[];
  error?: string;
};

const API_BASE = "https://你的-render-後端網址.onrender.com";

const PRICE_RANGES = [
  { key: "0-50", label: "0 ~ 50", min: 0, max: 50 },
  { key: "50-100", label: "50 ~ 100", min: 50, max: 100 },
  { key: "100-200", label: "100 ~ 200", min: 100, max: 200 },
  { key: "200-500", label: "200 ~ 500", min: 200, max: 500 },
  { key: "500+", label: "500+", min: 500, max: 999999 },
];

function formatNumber(num: number) {
  return new Intl.NumberFormat("zh-TW").format(num);
}

function formatDateString(twDate: string) {
  if (!twDate) return "-";

  const value = String(twDate).trim();

  if (/^\d{7}$/.test(value)) {
    const rocYear = Number(value.slice(0, 3));
    const month = value.slice(3, 5);
    const day = value.slice(5, 7);
    const year = rocYear + 1911;
    return `${year}/${month}/${day}`;
  }

  if (/^\d{8}$/.test(value)) {
    const year = value.slice(0, 4);
    const month = value.slice(4, 6);
    const day = value.slice(6, 8);
    return `${year}/${month}/${day}`;
  }

  return value;
}

export default function HomePage() {
  const [stocks, setStocks] = useState<Stock[]>([]);
  const [loading, setLoading] = useState(false);
  const [activeRange, setActiveRange] = useState("50-100");
  const [searchText, setSearchText] = useState("");
  const [lastUpdated, setLastUpdated] = useState("");
  const [apiSource, setApiSource] = useState("TWSE");
  const [apiMarket, setApiMarket] = useState("上市");
  const [error, setError] = useState("");

  const selectedRange = useMemo(() => {
    return PRICE_RANGES.find((item) => item.key === activeRange) || PRICE_RANGES[1];
  }, [activeRange]);

  const fetchStocks = useCallback(async () => {
    try {
      setLoading(true);
      setError("");

      const url = `${API_BASE}/stocks?min_price=${selectedRange.min}&max_price=${selectedRange.max}`;

      const res = await fetch(url, {
        method: "GET",
        cache: "no-store",
      });

      if (!res.ok) {
        throw new Error(`HTTP ${res.status}`);
      }

      const data: ApiResponse = await res.json();

      if (!data.success) {
        throw new Error(data.error || "後端回傳失敗");
      }

      setStocks(Array.isArray(data.stocks) ? data.stocks : []);
      setApiSource(data.source || "TWSE");
      setApiMarket(data.market || "上市");
      setLastUpdated(
        new Date().toLocaleString("zh-TW", {
          hour12: false,
        })
      );
    } catch (err) {
      console.error("fetchStocks error:", err);
      setError("資料更新失敗，請稍後再試");
      setStocks([]);
    } finally {
      setLoading(false);
    }
  }, [selectedRange]);

  useEffect(() => {
    fetchStocks();

    const timer = setInterval(() => {
      fetchStocks();
    }, 10000);

    return () => clearInterval(timer);
  }, [fetchStocks]);

  const filteredStocks = useMemo(() => {
    const keyword = searchText.trim().toLowerCase();

    if (!keyword) return stocks;

    return stocks.filter((stock) => {
      return (
        stock.symbol.toLowerCase().includes(keyword) ||
        stock.name.toLowerCase().includes(keyword)
      );
    });
  }, [stocks, searchText]);

  const top10 = useMemo(() => {
    return [...filteredStocks].sort((a, b) => b.score - a.score).slice(0, 10);
  }, [filteredStocks]);

  return (
    <main className="min-h-screen bg-[#061a2b] text-white">
      <div className="mx-auto flex min-h-screen max-w-[1600px] gap-5 px-4 py-5">
        <aside className="w-[240px] shrink-0 rounded-2xl border border-white/10 bg-white/5 p-4 shadow-lg backdrop-blur">
          <div className="mb-4">
            <h1 className="text-xl font-bold tracking-wide">台股智慧選股</h1>
            <p className="mt-1 text-sm text-white/70">TWSE 上市股票</p>
          </div>

          <div className="mb-5 rounded-xl bg-white/5 p-3">
            <div className="text-sm text-white/70">資料來源</div>
            <div className="mt-1 font-semibold">
              {apiSource} / {apiMarket}
            </div>

            <div className="mt-3 text-sm text-white/70">最後更新</div>
            <div className="mt-1 text-sm">{lastUpdated || "尚未更新"}</div>

            <div className="mt-3 text-sm text-white/70">更新頻率</div>
            <div className="mt-1 text-sm">每 10 秒刷新一次</div>
          </div>

          <div>
            <div className="mb-3 text-sm font-semibold text-white/80">價格分類</div>

            <div className="space-y-2">
              {PRICE_RANGES.map((range) => {
                const isActive = activeRange === range.key;

                return (
                  <button
                    key={range.key}
                    onClick={() => setActiveRange(range.key)}
                    className={`w-full rounded-xl px-4 py-3 text-left text-sm font-medium transition ${
                      isActive
                        ? "bg-cyan-500 text-white shadow-md"
                        : "bg-white/5 text-white/85 hover:bg-white/10"
                    }`}
                  >
                    {range.label}
                  </button>
                );
              })}
            </div>
          </div>

          <div className="mt-5 rounded-xl bg-white/5 p-3 text-sm text-white/75">
            <div>目前區間：{selectedRange.label}</div>
            <div className="mt-2">目前筆數：{formatNumber(filteredStocks.length)}</div>
          </div>
        </aside>

        <section className="min-w-0 flex-1">
          <div className="mb-5 rounded-2xl border border-white/10 bg-white/5 p-4 shadow-lg backdrop-blur">
            <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
              <div>
                <h2 className="text-2xl font-bold">上市股票清單</h2>
                <p className="mt-1 text-sm text-white/70">
                  顯示收盤資料、推薦分數、進出場價位與停損價位
                </p>
              </div>

              <div className="flex w-full flex-col gap-3 sm:flex-row lg:w-auto">
                <input
                  type="text"
                  value={searchText}
                  onChange={(e) => setSearchText(e.target.value)}
                  placeholder="搜尋股票代號 / 名稱"
                  className="w-full rounded-xl border border-white/10 bg-[#0b2740] px-4 py-3 text-white outline-none placeholder:text-white/40 focus:border-cyan-400 sm:w-[300px]"
                />

                <button
                  onClick={fetchStocks}
                  className="rounded-xl bg-cyan-500 px-5 py-3 font-semibold text-white transition hover:bg-cyan-400"
                >
                  立即更新
                </button>
              </div>
            </div>

            {loading && (
              <div className="mt-4 rounded-xl bg-cyan-500/10 px-4 py-3 text-sm text-cyan-200">
                資料更新中...
              </div>
            )}

            {error && (
              <div className="mt-4 rounded-xl bg-red-500/10 px-4 py-3 text-sm text-red-200">
                {error}
              </div>
            )}
          </div>

          <div className="mb-5 rounded-2xl border border-white/10 bg-white/5 p-4 shadow-lg backdrop-blur">
            <div className="mb-4 flex items-center justify-between">
              <h3 className="text-lg font-bold">推薦前 10 檔</h3>
              <span className="text-sm text-white/60">依推薦分數排序</span>
            </div>

            <div className="grid grid-cols-1 gap-3 xl:grid-cols-2">
              {top10.length > 0 ? (
                top10.map((stock) => {
                  const isUp = stock.change_percent > 0;
                  const isDown = stock.change_percent < 0;

                  return (
                    <div
                      key={`top-${stock.symbol}`}
                      className="rounded-2xl border border-white/10 bg-[#0b2740] p-4"
                    >
                      <div className="flex items-start justify-between gap-3">
                        <div>
                          <div className="text-lg font-bold">
                            {stock.symbol} {stock.name}
                          </div>
                          <div className="mt-1 text-sm text-white/60">
                            資料日期：{formatDateString(stock.date)}
                          </div>
                        </div>
                        <div className="rounded-xl bg-cyan-500/15 px-3 py-2 text-sm font-semibold text-cyan-200">
                          分數 {stock.score}
                        </div>
                      </div>

                      <div className="mt-4 grid grid-cols-2 gap-3 text-sm md:grid-cols-4">
                        <div className="rounded-xl bg-white/5 p-3">
                          <div className="text-white/60">收盤價</div>
                          <div className="mt-1 text-base font-bold">{stock.price}</div>
                        </div>

                        <div className="rounded-xl bg-white/5 p-3">
                          <div className="text-white/60">漲跌幅</div>
                          <div
                            className={`mt-1 text-base font-bold ${
                              isUp
                                ? "text-emerald-400"
                                : isDown
                                ? "text-rose-400"
                                : "text-white"
                            }`}
                          >
                            {stock.change_percent > 0 ? "+" : ""}
                            {stock.change_percent}%
                          </div>
                        </div>

                        <div className="rounded-xl bg-white/5 p-3">
                          <div className="text-white/60">進場價</div>
                          <div className="mt-1 font-semibold">{stock.entry_price || "-"}</div>
                        </div>

                        <div className="rounded-xl bg-white/5 p-3">
                          <div className="text-white/60">停損價</div>
                          <div className="mt-1 font-semibold">{stock.stop_loss || "-"}</div>
                        </div>
                      </div>
                    </div>
                  );
                })
              ) : (
                <div className="rounded-xl bg-white/5 p-4 text-sm text-white/70">
                  目前沒有符合條件的股票
                </div>
              )}
            </div>
          </div>

          <div className="overflow-hidden rounded-2xl border border-white/10 bg-white/5 shadow-lg backdrop-blur">
            <div className="overflow-x-auto">
              <table className="min-w-full border-collapse">
                <thead className="bg-white/10 text-left text-sm text-white/80">
                  <tr>
                    <th className="px-4 py-4">代號</th>
                    <th className="px-4 py-4">名稱</th>
                    <th className="px-4 py-4">日期</th>
                    <th className="px-4 py-4">收盤價</th>
                    <th className="px-4 py-4">漲跌</th>
                    <th className="px-4 py-4">漲跌幅</th>
                    <th className="px-4 py-4">成交量</th>
                    <th className="px-4 py-4">推薦分數</th>
                    <th className="px-4 py-4">訊號</th>
                    <th className="px-4 py-4">進場價</th>
                    <th className="px-4 py-4">出場價</th>
                    <th className="px-4 py-4">停損價</th>
                  </tr>
                </thead>

                <tbody>
                  {filteredStocks.length > 0 ? (
                    filteredStocks.map((stock) => {
                      const isUp = stock.change_percent > 0;
                      const isDown = stock.change_percent < 0;

                      return (
                        <tr
                          key={stock.symbol}
                          className="border-t border-white/10 text-sm transition hover:bg-white/5"
                        >
                          <td className="px-4 py-4 font-bold">{stock.symbol}</td>
                          <td className="px-4 py-4">{stock.name}</td>
                          <td className="px-4 py-4 text-white/70">
                            {formatDateString(stock.date)}
                          </td>
                          <td className="px-4 py-4 font-semibold">{stock.price}</td>
                          <td
                            className={`px-4 py-4 font-semibold ${
                              stock.change > 0
                                ? "text-emerald-400"
                                : stock.change < 0
                                ? "text-rose-400"
                                : "text-white"
                            }`}
                          >
                            {stock.change > 0 ? "+" : ""}
                            {stock.change}
                          </td>
                          <td
                            className={`px-4 py-4 font-semibold ${
                              isUp
                                ? "text-emerald-400"
                                : isDown
                                ? "text-rose-400"
                                : "text-white"
                            }`}
                          >
                            {stock.change_percent > 0 ? "+" : ""}
                            {stock.change_percent}%
                          </td>
                          <td className="px-4 py-4">{formatNumber(stock.volume)}</td>
                          <td className="px-4 py-4">{stock.score}</td>
                          <td className="px-4 py-4">{stock.signal || "-"}</td>
                          <td className="px-4 py-4">{stock.entry_price || "-"}</td>
                          <td className="px-4 py-4">{stock.target_price || "-"}</td>
                          <td className="px-4 py-4">{stock.stop_loss || "-"}</td>
                        </tr>
                      );
                    })
                  ) : (
                    <tr>
                      <td colSpan={12} className="px-4 py-10 text-center text-white/60">
                        沒有符合條件的資料
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </section>
      </div>
    </main>
  );
}
