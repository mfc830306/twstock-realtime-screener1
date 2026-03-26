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
  prev_close?: number;
  open?: number;
  high?: number;
  low?: number;
  last_update?: string;
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
  { key: "all", label: "全部" },
  { key: "lt10", label: "<10" },
  { key: "10_20", label: "10-20" },
  { key: "20_50", label: "20-50" },
  { key: "50_100", label: "50-100" },
  { key: "100_200", label: "100-200" },
  { key: "200_500", label: "200-500" },
  { key: "500_1000", label: "500-1000" },
  { key: "gte1000", label: "1000+" },
];

function getBucket(price: number) {
  if (price < 10) return "lt10";
  if (price < 20) return "10_20";
  if (price < 50) return "20_50";
  if (price < 100) return "50_100";
  if (price < 200) return "100_200";
  if (price < 500) return "200_500";
  if (price < 1000) return "500_1000";
  return "gte1000";
}

function formatVolume(value: number) {
  return new Intl.NumberFormat("zh-TW").format(value || 0);
}

function formatChange(value: number) {
  return `${value >= 0 ? "+" : ""}${value.toFixed(2)}%`;
}

export default function Page() {
  const [stocks, setStocks] = useState<Stock[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [bucket, setBucket] = useState("all");
  const [keyword, setKeyword] = useState("");
  const [sortBy, setSortBy] = useState<"score" | "price" | "change_percent" | "volume">("score");
  const [sortDir, setSortDir] = useState<"asc" | "desc">("desc");

  useEffect(() => {
    const loadStocks = async () => {
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

        setStocks(Array.isArray(data.stocks) ? data.stocks : []);
      } catch (err: any) {
        setError(err?.message || "載入失敗");
        setStocks([]);
      } finally {
        setLoading(false);
      }
    };

    loadStocks();
  }, []);

  const bucketCounts = useMemo(() => {
    const counts: Record<string, number> = {
      all: stocks.length,
      lt10: 0,
      "10_20": 0,
      "20_50": 0,
      "50_100": 0,
      "100_200": 0,
      "200_500": 0,
      "500_1000": 0,
      gte1000: 0,
    };

    for (const stock of stocks) {
      counts[getBucket(stock.price)] += 1;
    }

    return counts;
  }, [stocks]);

  const top10 = useMemo(() => {
    return [...stocks]
      .sort((a, b) => {
        if (b.score !== a.score) return b.score - a.score;
        if (b.change_percent !== a.change_percent) return b.change_percent - a.change_percent;
        return b.volume - a.volume;
      })
      .slice(0, 10);
  }, [stocks]);

  const filtered = useMemo(() => {
    let result = [...stocks];

    if (bucket !== "all") {
      result = result.filter((s) => getBucket(s.price) === bucket);
    }

    const kw = keyword.trim().toLowerCase();
    if (kw) {
      result = result.filter(
        (s) =>
          s.symbol.toLowerCase().includes(kw) ||
          s.name.toLowerCase().includes(kw)
      );
    }

    result.sort((a, b) => {
      const av = Number(a[sortBy]);
      const bv = Number(b[sortBy]);
      return sortDir === "desc" ? bv - av : av - bv;
    });

    return result;
  }, [stocks, bucket, keyword, sortBy, sortDir]);

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
        <div className="mb-6 rounded-3xl border border-blue-300/20 bg-[#0a234f] p-6 shadow-2xl">
          <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
            <div>
              <h1 className="text-3xl font-bold text-white">台股分類選股系統</h1>
              <p className="mt-2 text-sm text-blue-100">
                顯示全部台股，依股價分類、搜尋與排序，並提供推薦前 10 檔
              </p>
            </div>

            <div className="flex flex-col gap-3 sm:flex-row">
              <input
                value={keyword}
                onChange={(e) => setKeyword(e.target.value)}
                placeholder="搜尋股票代碼 / 名稱，例如 2330 或 台積電"
                className="w-full rounded-2xl border border-blue-200/20 bg-[#12326d] px-4 py-3 text-white placeholder:text-blue-100/50 outline-none sm:w-[320px]"
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
            <div className="rounded-2xl bg-[#12326d] p-4">
              <div className="text-sm text-blue-100/80">全部股票數</div>
              <div className="mt-2 text-2xl font-bold text-white">{stocks.length}</div>
            </div>
            <div className="rounded-2xl bg-[#12326d] p-4">
              <div className="text-sm text-blue-100/80">目前分類</div>
              <div className="mt-2 text-lg font-bold text-white">
                {PRICE_BUCKETS.find((b) => b.key === bucket)?.label}
              </div>
            </div>
            <div className="rounded-2xl bg-[#12326d] p-4">
              <div className="text-sm text-blue-100/80">篩選後數量</div>
              <div className="mt-2 text-2xl font-bold text-white">{filtered.length}</div>
            </div>
            <div className="rounded-2xl bg-[#12326d] p-4">
              <div className="text-sm text-blue-100/80">排序欄位</div>
              <div className="mt-2 text-lg font-bold text-white">
                {sortBy === "score"
                  ? "推薦分數"
                  : sortBy === "price"
                  ? "股價"
                  : sortBy === "change_percent"
                  ? "漲跌幅"
                  : "成交量"}
              </div>
            </div>
            <div className="rounded-2xl bg-[#12326d] p-4">
              <div className="text-sm text-blue-100/80">排序方向</div>
              <div className="mt-2 text-lg font-bold text-white">
                {sortDir === "desc" ? "高 → 低" : "低 → 高"}
              </div>
            </div>
            <div className="rounded-2xl bg-[#12326d] p-4">
              <div className="text-sm text-blue-100/80">搜尋關鍵字</div>
              <div className="mt-2 truncate text-lg font-bold text-white">
                {keyword.trim() || "無"}
              </div>
            </div>
          </div>
        </div>

        <section className="mb-6">
          <div className="mb-3 flex items-center justify-between">
            <h2 className="text-2xl font-bold text-white">推薦前 10 檔</h2>
            <span className="text-sm text-blue-100">依分數、漲跌幅、成交量綜合排序</span>
          </div>

          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-5">
            {top10.map((s) => (
              <div
                key={s.symbol}
                className="rounded-3xl border border-blue-200/15 bg-[#0d2b61] p-4 shadow-xl"
              >
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <div className="text-lg font-bold text-white">
                      {s.name} <span className="text-sm text-blue-200">{s.symbol}</span>
                    </div>
                    <div className="mt-1 text-xs text-blue-100/80">{s.market}</div>
                  </div>
                  <div className="rounded-xl bg-emerald-500/20 px-3 py-1 text-sm font-bold text-emerald-300">
                    {s.score} 分
                  </div>
                </div>

                <div className="mt-4 space-y-2 text-sm text-white">
                  <div className="flex justify-between">
                    <span className="text-blue-100/80">現價</span>
                    <span className="font-semibold">{s.price}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-blue-100/80">漲跌幅</span>
                    <span className={s.change_percent >= 0 ? "font-semibold text-red-300" : "font-semibold text-green-300"}>
                      {formatChange(s.change_percent)}
                    </span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-blue-100/80">進場價</span>
                    <span className="font-semibold">{s.entry_price || "-"}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-blue-100/80">目標價</span>
                    <span className="font-semibold">{s.target_price || "-"}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-blue-100/80">停損價</span>
                    <span className="font-semibold">{s.stop_loss || "-"}</span>
                  </div>
                </div>

                <div className="mt-4 rounded-2xl bg-[#12326d] p-3 text-sm text-blue-50">
                  <div className="mb-1 font-semibold">{s.signal || "中性"}</div>
                  <div>{s.reason || "暫無說明"}</div>
                </div>
              </div>
            ))}
          </div>
        </section>

        <div className="grid gap-6 xl:grid-cols-[280px_minmax(0,1fr)]">
          <aside className="rounded-3xl border border-blue-300/20 bg-[#0a234f] p-4 shadow-2xl">
            <div className="mb-4 text-xl font-bold text-white">價格分類</div>
            <div className="space-y-3">
              {PRICE_BUCKETS.map((b) => {
                const active = bucket === b.key;
                return (
                  <button
                    key={b.key}
                    onClick={() => setBucket(b.key)}
                    className={`flex w-full items-center justify-between rounded-2xl border px-4 py-3 text-left transition ${
                      active
                        ? "border-blue-300 bg-blue-500/25 text-white"
                        : "border-blue-200/10 bg-[#12326d] text-white hover:border-blue-300/50 hover:bg-[#184086]"
                    }`}
                  >
                    <span className="font-medium">{b.label}</span>
                    <span className="rounded-full bg-white/10 px-3 py-1 text-sm text-blue-100">
                      {bucketCounts[b.key] ?? 0}
                    </span>
                  </button>
                );
              })}
            </div>
          </aside>

          <section className="rounded-3xl border border-blue-300/20 bg-[#0a234f] p-4 shadow-2xl">
            <div className="mb-4 flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
              <div>
                <h2 className="text-2xl font-bold text-white">股票清單</h2>
                <p className="mt-1 text-sm text-blue-100">
                  可依推薦分數、股價、漲跌幅、成交量排序
                </p>
              </div>

              <div className="flex flex-wrap gap-2">
                <button
                  onClick={() => toggleSort("score")}
                  className="rounded-2xl bg-[#12326d] px-4 py-2 text-sm font-medium text-white hover:bg-[#184086]"
                >
                  推薦分數 {sortBy === "score" ? (sortDir === "desc" ? "↓" : "↑") : ""}
                </button>
                <button
                  onClick={() => toggleSort("price")}
                  className="rounded-2xl bg-[#12326d] px-4 py-2 text-sm font-medium text-white hover:bg-[#184086]"
                >
                  股價 {sortBy === "price" ? (sortDir === "desc" ? "↓" : "↑") : ""}
                </button>
                <button
                  onClick={() => toggleSort("change_percent")}
                  className="rounded-2xl bg-[#12326d] px-4 py-2 text-sm font-medium text-white hover:bg-[#184086]"
                >
                  漲跌幅 {sortBy === "change_percent" ? (sortDir === "desc" ? "↓" : "↑") : ""}
                </button>
                <button
                  onClick={() => toggleSort("volume")}
                  className="rounded-2xl bg-[#12326d] px-4 py-2 text-sm font-medium text-white hover:bg-[#184086]"
                >
                  成交量 {sortBy === "volume" ? (sortDir === "desc" ? "↓" : "↑") : ""}
                </button>
              </div>
            </div>

            {loading ? (
              <div className="rounded-3xl bg-[#12326d] p-10 text-center text-lg font-medium text-white">
                載入股票資料中...
              </div>
            ) : error ? (
              <div className="rounded-3xl bg-red-500/15 p-6 text-red-200">
                載入失敗：{error}
              </div>
            ) : filtered.length === 0 ? (
              <div className="rounded-3xl bg-[#12326d] p-10 text-center text-lg font-medium text-white">
                查無符合條件的股票
              </div>
            ) : (
              <div className="overflow-x-auto rounded-3xl border border-blue-200/15">
                <table className="min-w-full text-sm text-white">
                  <thead className="bg-[#12326d] text-blue-50">
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
                    {filtered.map((s, i) => (
                      <tr
                        key={`${s.symbol}-${i}`}
                        className="border-t border-blue-200/10 bg-[#0d2b61] hover:bg-[#143872]"
                      >
                        <td className="px-4 py-4 font-semibold text-blue-100">{s.symbol}</td>
                        <td className="px-4 py-4 font-medium text-white">{s.name}</td>
                        <td className="px-4 py-4 text-blue-100">{s.market}</td>
                        <td className="px-4 py-4 text-right font-semibold text-white">{s.price}</td>
                        <td
                          className={`px-4 py-4 text-right font-semibold ${
                            s.change_percent >= 0 ? "text-red-300" : "text-green-300"
                          }`}
                        >
                          {formatChange(s.change_percent)}
                        </td>
                        <td className="px-4 py-4 text-right text-white">{formatVolume(s.volume)}</td>
                        <td className="px-4 py-4 text-right">
                          <span className="rounded-xl bg-blue-500/20 px-3 py-1 font-bold text-blue-200">
                            {s.score}
                          </span>
                        </td>
                        <td className="px-4 py-4 text-white">{s.signal || "-"}</td>
                        <td className="px-4 py-4 text-white">{s.entry_price || "-"}</td>
                        <td className="px-4 py-4 text-white">{s.target_price || "-"}</td>
                        <td className="px-4 py-4 text-white">{s.stop_loss || "-"}</td>
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
