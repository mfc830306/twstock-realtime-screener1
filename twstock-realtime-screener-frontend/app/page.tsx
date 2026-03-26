"use client";

import { useEffect, useMemo, useState } from "react";

type Stock = {
  symbol: string;
  name: string;
  market: string;
  price: number;
  change_percent: number;
  volume: number;
  score: number;
  prev_close: number;
  open: number;
  high: number;
  low: number;
  last_update: string;
  signal?: string;
  reason?: string;
  entry_price?: string;
  target_price?: string;
  stop_loss?: string;
};

const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE ||
  "https://twstock-realtime-screener1.onrender.com";

const PRICE_BUCKETS = [
  { key: "all", label: "全部股票" },
  { key: "lt10", label: "10元以下" },
  { key: "10_20", label: "10 ~ 20元" },
  { key: "20_50", label: "20 ~ 50元" },
  { key: "50_100", label: "50 ~ 100元" },
  { key: "100_200", label: "100 ~ 200元" },
  { key: "200_500", label: "200 ~ 500元" },
  { key: "500_1000", label: "500 ~ 1000元" },
  { key: "gte1000", label: "1000元以上" },
];

function formatVolume(value: number) {
  if (!value) return "0";
  return new Intl.NumberFormat("zh-TW").format(value);
}

function getBucketKey(price: number) {
  if (price < 10) return "lt10";
  if (price < 20) return "10_20";
  if (price < 50) return "20_50";
  if (price < 100) return "50_100";
  if (price < 200) return "100_200";
  if (price < 500) return "200_500";
  if (price < 1000) return "500_1000";
  return "gte1000";
}

export default function Page() {
  const [allStocks, setAllStocks] = useState<Stock[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [keyword, setKeyword] = useState("");
  const [selectedBucket, setSelectedBucket] = useState("all");
  const [sortBy, setSortBy] = useState<"score" | "price" | "change_percent" | "volume">("score");
  const [sortDir, setSortDir] = useState<"asc" | "desc">("desc");

  useEffect(() => {
    let ignore = false;

    const fetchStocks = async () => {
      try {
        setLoading(true);
        setError("");

        const res = await fetch(`${API_BASE}/stocks`, {
          cache: "no-store",
        });

        const data = await res.json();

        if (!res.ok || !data.success) {
          throw new Error(data.message || "讀取股票資料失敗");
        }

        if (!ignore) {
          setAllStocks(data.stocks || []);
        }
      } catch (err: any) {
        if (!ignore) {
          setError(err?.message || "載入失敗");
          setAllStocks([]);
        }
      } finally {
        if (!ignore) {
          setLoading(false);
        }
      }
    };

    fetchStocks();
    return () => {
      ignore = true;
    };
  }, []);

  const bucketCounts = useMemo(() => {
    const counts: Record<string, number> = {
      all: allStocks.length,
      lt10: 0,
      "10_20": 0,
      "20_50": 0,
      "50_100": 0,
      "100_200": 0,
      "200_500": 0,
      "500_1000": 0,
      gte1000: 0,
    };

    for (const stock of allStocks) {
      const key = getBucketKey(stock.price);
      counts[key] += 1;
    }

    return counts;
  }, [allStocks]);

  const top10 = useMemo(() => {
    return [...allStocks].sort((a, b) => {
      if (b.score !== a.score) return b.score - a.score;
      if (b.change_percent !== a.change_percent) return b.change_percent - a.change_percent;
      return b.volume - a.volume;
    }).slice(0, 10);
  }, [allStocks]);

  const filteredStocks = useMemo(() => {
    let list = [...allStocks];

    if (selectedBucket !== "all") {
      list = list.filter((stock) => getBucketKey(stock.price) === selectedBucket);
    }

    const kw = keyword.trim().toLowerCase();
    if (kw) {
      list = list.filter(
        (stock) =>
          stock.symbol.toLowerCase().includes(kw) ||
          stock.name.toLowerCase().includes(kw)
      );
    }

    list.sort((a, b) => {
      const aValue = a[sortBy];
      const bValue = b[sortBy];

      if (sortDir === "asc") {
        return Number(aValue) - Number(bValue);
      }
      return Number(bValue) - Number(aValue);
    });

    return list;
  }, [allStocks, selectedBucket, keyword, sortBy, sortDir]);

  const toggleSort = (field: "score" | "price" | "change_percent" | "volume") => {
    if (sortBy === field) {
      setSortDir((prev) => (prev === "desc" ? "asc" : "desc"));
    } else {
      setSortBy(field);
      setSortDir("desc");
    }
  };

  return (
    <main className="min-h-screen bg-[#061a40] text-white">
      <div className="mx-auto max-w-[1600px] px-4 py-6 md:px-6">
        <div className="mb-6 rounded-3xl border border-white/10 bg-white/5 p-6 shadow-2xl backdrop-blur">
          <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
            <div>
              <h1 className="text-3xl font-bold tracking-tight">台股即時分類選股系統</h1>
              <p className="mt-2 text-sm text-blue-100/80">
                一次顯示全部台股，依股價分類、搜尋、排序，並提供推薦前10檔
              </p>
            </div>

            <div className="flex flex-col gap-3 sm:flex-row">
              <input
                value={keyword}
                onChange={(e) => setKeyword(e.target.value)}
                placeholder="搜尋股票代碼 / 名稱，例如 2330 或 台積電"
                className="w-full rounded-2xl border border-white/15 bg-[#0b245a] px-4 py-3 text-white outline-none placeholder:text-white/40 sm:w-[320px]"
              />

              <button
                onClick={() => window.location.reload()}
                className="rounded-2xl bg-blue-500 px-5 py-3 font-semibold text-white transition hover:bg-blue-400"
              >
                重新整理
              </button>
            </div>
          </div>

          <div className="mt-5 grid grid-cols-2 gap-3 md:grid-cols-4 xl:grid-cols-6">
            <div className="rounded-2xl bg-[#0b245a] p-4">
              <div className="text-sm text-blue-100/70">全部股票數</div>
              <div className="mt-2 text-2xl font-bold">{allStocks.length}</div>
            </div>
            <div className="rounded-2xl bg-[#0b245a] p-4">
              <div className="text-sm text-blue-100/70">目前分類</div>
              <div className="mt-2 text-lg font-bold">
                {PRICE_BUCKETS.find((b) => b.key === selectedBucket)?.label}
              </div>
            </div>
            <div className="rounded-2xl bg-[#0b245a] p-4">
              <div className="text-sm text-blue-100/70">篩選後數量</div>
              <div className="mt-2 text-2xl font-bold">{filteredStocks.length}</div>
            </div>
            <div className="rounded-2xl bg-[#0b245a] p-4">
              <div className="text-sm text-blue-100/70">排序欄位</div>
              <div className="mt-2 text-lg font-bold">
                {sortBy === "score"
                  ? "推薦分數"
                  : sortBy === "price"
                  ? "股價"
                  : sortBy === "change_percent"
                  ? "漲跌幅"
                  : "成交量"}
              </div>
            </div>
            <div className="rounded-2xl bg-[#0b245a] p-4">
              <div className="text-sm text-blue-100/70">排序方向</div>
              <div className="mt-2 text-lg font-bold">
                {sortDir === "desc" ? "高 → 低" : "低 → 高"}
              </div>
            </div>
            <div className="rounded-2xl bg-[#0b245a] p-4">
              <div className="text-sm text-blue-100/70">搜尋關鍵字</div>
              <div className="mt-2 truncate text-lg font-bold">
                {keyword.trim() || "無"}
              </div>
            </div>
          </div>
        </div>

        <section className="mb-6">
          <div className="mb-3 flex items-center justify-between">
            <h2 className="text-2xl font-bold">推薦前 10 檔</h2>
            <span className="text-sm text-blue-100/70">依分數、漲跌幅、成交量綜合排序</span>
          </div>

          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-5">
            {top10.map((stock) => (
              <div
                key={stock.symbol}
                className="rounded-3xl border border-white/10 bg-white/5 p-4 shadow-xl"
              >
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <div className="text-lg font-bold">
                      {stock.name}{" "}
                      <span className="text-sm font-medium text-blue-200">
                        {stock.symbol}
                      </span>
                    </div>
                    <div className="mt-1 text-xs text-blue-100/70">{stock.market}</div>
                  </div>
                  <div className="rounded-xl bg-emerald-500/20 px-3 py-1 text-sm font-bold text-emerald-300">
                    {stock.score} 分
                  </div>
                </div>

                <div className="mt-4 space-y-2 text-sm">
                  <div className="flex justify-between">
                    <span className="text-blue-100/70">現價</span>
                    <span className="font-semibold">{stock.price}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-blue-100/70">漲跌幅</span>
                    <span
                      className={`font-semibold ${
                        stock.change_percent >= 0 ? "text-red-300" : "text-green-300"
                      }`}
                    >
                      {stock.change_percent >= 0 ? "+" : ""}
                      {stock.change_percent}%
                    </span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-blue-100/70">進場價</span>
                    <span className="font-semibold">{stock.entry_price || "-"}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-blue-100/70">目標價</span>
                    <span className="font-semibold">{stock.target_price || "-"}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-blue-100/70">停損價</span>
                    <span className="font-semibold">{stock.stop_loss || "-"}</span>
                  </div>
                </div>

                <div className="mt-4 rounded-2xl bg-[#0b245a] p-3 text-sm text-blue-50/90">
                  <div className="mb-1 font-semibold">{stock.signal || "中性"}</div>
                  <div>{stock.reason || "暫無說明"}</div>
                </div>
              </div>
            ))}
          </div>
        </section>

        <div className="grid gap-6 xl:grid-cols-[280px_minmax(0,1fr)]">
          <aside className="rounded-3xl border border-white/10 bg-white/5 p-4 shadow-2xl">
            <div className="mb-4 text-xl font-bold">價格分類</div>
            <div className="space-y-3">
              {PRICE_BUCKETS.map((bucket) => {
                const active = selectedBucket === bucket.key;
                const count = bucketCounts[bucket.key] ?? 0;

                return (
                  <button
                    key={bucket.key}
                    onClick={() => setSelectedBucket(bucket.key)}
                    className={`flex w-full items-center justify-between rounded-2xl border px-4 py-3 text-left transition ${
                      active
                        ? "border-blue-400 bg-blue-500/20"
                        : "border-white/10 bg-[#0b245a] hover:border-blue-300/50 hover:bg-[#11306f]"
                    }`}
                  >
                    <span className="font-medium">{bucket.label}</span>
                    <span className="rounded-full bg-white/10 px-3 py-1 text-sm text-blue-100">
                      {count}
                    </span>
                  </button>
                );
              })}
            </div>
          </aside>

          <section className="rounded-3xl border border-white/10 bg-white/5 p-4 shadow-2xl">
            <div className="mb-4 flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
              <div>
                <h2 className="text-2xl font-bold">股票清單</h2>
                <p className="mt-1 text-sm text-blue-100/70">
                  可依推薦分數、股價、漲跌幅、成交量排序
                </p>
              </div>

              <div className="flex flex-wrap gap-2">
                <button
                  onClick={() => toggleSort("score")}
                  className="rounded-2xl bg-[#0b245a] px-4 py-2 text-sm font-medium hover:bg-[#11306f]"
                >
                  推薦分數 {sortBy === "score" ? (sortDir === "desc" ? "↓" : "↑") : ""}
                </button>
                <button
                  onClick={() => toggleSort("price")}
                  className="rounded-2xl bg-[#0b245a] px-4 py-2 text-sm font-medium hover:bg-[#11306f]"
                >
                  股價 {sortBy === "price" ? (sortDir === "desc" ? "↓" : "↑") : ""}
                </button>
                <button
                  onClick={() => toggleSort("change_percent")}
                  className="rounded-2xl bg-[#0b245a] px-4 py-2 text-sm font-medium hover:bg-[#11306f]"
                >
                  漲跌幅 {sortBy === "change_percent" ? (sortDir === "desc" ? "↓" : "↑") : ""}
                </button>
                <button
                  onClick={() => toggleSort("volume")}
                  className="rounded-2xl bg-[#0b245a] px-4 py-2 text-sm font-medium hover:bg-[#11306f]"
                >
                  成交量 {sortBy === "volume" ? (sortDir === "desc" ? "↓" : "↑") : ""}
                </button>
              </div>
            </div>

            {loading ? (
              <div className="rounded-3xl bg-[#0b245a] p-10 text-center text-lg font-medium">
                載入股票資料中...
              </div>
            ) : error ? (
              <div className="rounded-3xl bg-red-500/15 p-6 text-red-200">
                載入失敗：{error}
              </div>
            ) : filteredStocks.length === 0 ? (
              <div className="rounded-3xl bg-[#0b245a] p-10 text-center text-lg font-medium">
                查無符合條件的股票
              </div>
            ) : (
              <div className="overflow-x-auto rounded-3xl border border-white/10">
                <table className="min-w-full overflow-hidden">
                  <thead className="bg-[#0b245a] text-sm text-blue-100/85">
                    <tr>
                      <th className="px-4 py-4 text-left">代碼</th>
                      <th className="px-4 py-4 text-left">名稱</th>
                      <th className="px-4 py-4 text-left">市場</th>
                      <th className="px-4 py-4 text-right">現價</th>
                      <th className="px-4 py-4 text-right">漲跌幅</th>
                      <th className="px-4 py-4 text-right">成交量</th>
                      <th className="px-4 py-4 text-right">推薦分數</th>
                      <th className="px-4 py-4 text-left">訊號</th>
                      <th className="px-4 py-4 text-left">進場價</th>
                      <th className="px-4 py-4 text-left">目標價</th>
                      <th className="px-4 py-4 text-left">停損價</th>
                    </tr>
                  </thead>
                  <tbody>
                    {filteredStocks.map((stock, index) => (
                      <tr
                        key={`${stock.symbol}-${index}`}
                        className="border-t border-white/10 bg-white/0 text-sm hover:bg-white/5"
                      >
                        <td className="px-4 py-4 font-semibold text-blue-100">{stock.symbol}</td>
                        <td className="px-4 py-4 font-medium">{stock.name}</td>
                        <td className="px-4 py-4 text-blue-100/80">{stock.market}</td>
                        <td className="px-4 py-4 text-right font-semibold">{stock.price}</td>
                        <td
                          className={`px-4 py-4 text-right font-semibold ${
                            stock.change_percent >= 0 ? "text-red-300" : "text-green-300"
                          }`}
                        >
                          {stock.change_percent >= 0 ? "+" : ""}
                          {stock.change_percent}%
                        </td>
                        <td className="px-4 py-4 text-right">{formatVolume(stock.volume)}</td>
                        <td className="px-4 py-4 text-right">
                          <span className="rounded-xl bg-blue-500/20 px-3 py-1 font-bold text-blue-200">
                            {stock.score}
                          </span>
                        </td>
                        <td className="px-4 py-4">{stock.signal || "-"}</td>
                        <td className="px-4 py-4">{stock.entry_price || "-"}</td>
                        <td className="px-4 py-4">{stock.target_price || "-"}</td>
                        <td className="px-4 py-4">{stock.stop_loss || "-"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>
        </div>
      </div>
    </main>
  );
}
