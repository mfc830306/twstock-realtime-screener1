"use client";

import { useEffect, useMemo, useState } from "react";

type StockResult = {
  symbol: string;
  name: string;
  price: number;
  change_percent: number;
  volume: number;
  ma5: number;
  ma20: number;
  score: number;
  trend: string;
  entry_range: string;
  take_profit: number;
  stop_loss: number;
  reason: string;
};

const API_BASE = "https://twstock-realtime-screener1.onrender.com";

function trendClass(trend: string) {
  if (trend.includes("強勢")) {
    return "bg-green-50 text-green-700 border-green-200";
  }
  if (trend.includes("弱勢")) {
    return "bg-red-50 text-red-700 border-red-200";
  }
  return "bg-yellow-50 text-yellow-700 border-yellow-200";
}

function scoreClass(score: number) {
  if (score >= 75) return "text-green-600";
  if (score >= 50) return "text-yellow-600";
  return "text-red-600";
}

function formatNumber(value: number) {
  return new Intl.NumberFormat("zh-TW").format(value);
}

export default function Home() {
  const [stockInput, setStockInput] = useState("2330,2317,2454");
  const [results, setResults] = useState<StockResult[]>([]);
  const [loading, setLoading] = useState(false);
  const [loadingAll, setLoadingAll] = useState(false);
  const [error, setError] = useState("");
  const [tab, setTab] = useState<"全部" | "強勢" | "中性" | "弱勢">("全部");

  const top10 = useMemo(() => {
    return [...results].sort((a, b) => b.score - a.score).slice(0, 10);
  }, [results]);

  const filteredResults = useMemo(() => {
    if (tab === "全部") return results;
    if (tab === "強勢") return results.filter((x) => x.trend.includes("強勢"));
    if (tab === "弱勢") return results.filter((x) => x.trend.includes("弱勢"));
    return results.filter(
      (x) => x.trend.includes("中性") && !x.trend.includes("強勢") && !x.trend.includes("弱勢")
    );
  }, [results, tab]);

  const parseStocks = () => {
    return stockInput
      .split(/[\s,，]+/)
      .map((s) => s.trim())
      .filter(Boolean);
  };

  const fetchScan = async () => {
    try {
      setLoading(true);
      setError("");

      const stocks = parseStocks();
      if (!stocks.length) {
        setError("請輸入股票代號");
        setResults([]);
        return;
      }

      const res = await fetch(`${API_BASE}/scan`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ stocks }),
      });

      if (!res.ok) {
        throw new Error("API error");
      }

      const data = await res.json();
      setResults(Array.isArray(data) ? data : []);
      setTab("全部");
    } catch (e) {
      setError("讀取資料失敗，請稍後再試");
      setResults([]);
    } finally {
      setLoading(false);
    }
  };

  const fetchScanAll = async () => {
    try {
      setLoadingAll(true);
      setError("");

      const res = await fetch(`${API_BASE}/scan_all?limit=30`);
      if (!res.ok) {
        throw new Error("API error");
      }

      const data = await res.json();
      setResults(Array.isArray(data) ? data : []);
      setTab("全部");
    } catch (e) {
      setError("全台股掃描失敗，請稍後再試");
      setResults([]);
    } finally {
      setLoadingAll(false);
    }
  };

  useEffect(() => {
    fetchScan();
  }, []);

  return (
    <div className="min-h-screen bg-slate-100">
      <div className="mx-auto max-w-7xl px-4 py-6 md:px-6">
        <div className="mb-6 rounded-3xl bg-white p-6 shadow-sm">
          <div className="flex flex-col gap-4">
            <div>
              <div className="mb-2 inline-block rounded-full bg-blue-50 px-3 py-1 text-sm font-medium text-blue-700">
                台股即時選股系統
              </div>
              <h1 className="text-3xl font-bold text-slate-900">TW Stock Realtime Screener</h1>
              <p className="mt-2 text-sm text-slate-500">
                顯示推薦分數、進場區間、停損與出場價
              </p>
            </div>

            <div className="flex flex-col gap-3 lg:flex-row">
              <input
                value={stockInput}
                onChange={(e) => setStockInput(e.target.value)}
                placeholder="例如：2330, 2317, 2454"
                className="w-full rounded-2xl border border-slate-300 px-4 py-3 text-slate-900 outline-none focus:border-blue-500"
              />
              <button
                onClick={fetchScan}
                disabled={loading}
                className="rounded-2xl bg-blue-600 px-5 py-3 font-medium text-white hover:bg-blue-700 disabled:opacity-60"
              >
                {loading ? "掃描中..." : "掃描指定股票"}
              </button>
              <button
                onClick={fetchScanAll}
                disabled={loadingAll}
                className="rounded-2xl bg-slate-900 px-5 py-3 font-medium text-white hover:bg-slate-800 disabled:opacity-60"
              >
                {loadingAll ? "掃描中..." : "全台股 Top 30"}
              </button>
            </div>

            {error ? (
              <div className="rounded-2xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
                {error}
              </div>
            ) : null}
          </div>
        </div>

        <div className="mb-6 grid grid-cols-2 gap-4 lg:grid-cols-4">
          <SummaryCard title="掃描結果" value={`${results.length} 檔`} />
          <SummaryCard title="強勢股" value={`${results.filter((x) => x.trend.includes("強勢")).length} 檔`} />
          <SummaryCard
            title="中性股"
            value={`${
              results.filter(
                (x) =>
                  x.trend.includes("中性") &&
                  !x.trend.includes("強勢") &&
                  !x.trend.includes("弱勢")
              ).length
            } 檔`}
          />
          <SummaryCard title="弱勢股" value={`${results.filter((x) => x.trend.includes("弱勢")).length} 檔`} />
        </div>

        <div className="grid gap-6 xl:grid-cols-3">
          <div className="rounded-3xl bg-white p-5 shadow-sm xl:col-span-1">
            <div className="mb-4 flex items-center justify-between">
              <h2 className="text-xl font-bold text-slate-900">推薦 Top 10</h2>
              <span className="text-sm text-slate-500">依分數排序</span>
            </div>

            <div className="space-y-3">
              {top10.length === 0 ? (
                <EmptyBox text="目前沒有資料" />
              ) : (
                top10.map((stock, index) => (
                  <div key={`${stock.symbol}-${index}`} className="rounded-2xl bg-slate-50 p-4">
                    <div className="mb-2 flex items-center justify-between">
                      <div>
                        <div className="font-bold text-slate-900">
                          {index + 1}. {stock.name}
                        </div>
                        <div className="text-sm text-slate-500">{stock.symbol}</div>
                      </div>
                      <div className={`text-xl font-bold ${scoreClass(stock.score)}`}>
                        {stock.score}
                      </div>
                    </div>
                    <div className="flex items-center justify-between">
                      <span className={`rounded-full border px-3 py-1 text-sm font-medium ${trendClass(stock.trend)}`}>
                        {stock.trend}
                      </span>
                      <span className="text-sm text-slate-500">現價 {stock.price}</span>
                    </div>
                  </div>
                ))
              )}
            </div>
          </div>

          <div className="rounded-3xl bg-white p-5 shadow-sm xl:col-span-2">
            <div className="mb-4 flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
              <h2 className="text-xl font-bold text-slate-900">選股結果</h2>
              <div className="flex flex-wrap gap-2">
                {(["全部", "強勢", "中性", "弱勢"] as const).map((item) => (
                  <button
                    key={item}
                    onClick={() => setTab(item)}
                    className={`rounded-full px-4 py-2 text-sm font-medium ${
                      tab === item
                        ? "bg-slate-900 text-white"
                        : "bg-slate-100 text-slate-700 hover:bg-slate-200"
                    }`}
                  >
                    {item}
                  </button>
                ))}
              </div>
            </div>

            {filteredResults.length === 0 ? (
              <EmptyBox text="沒有符合條件的資料" />
            ) : (
              <div className="grid gap-4 md:grid-cols-2">
                {filteredResults.map((stock) => (
                  <div key={stock.symbol} className="rounded-3xl border border-slate-200 p-5">
                    <div className="mb-4 flex items-start justify-between gap-3">
                      <div>
                        <div className="text-xl font-bold text-slate-900">{stock.name}</div>
                        <div className="text-sm text-slate-500">{stock.symbol}</div>
                      </div>
                      <span className={`rounded-full border px-3 py-1 text-sm font-medium ${trendClass(stock.trend)}`}>
                        {stock.trend}
                      </span>
                    </div>

                    <div className="mb-4 grid grid-cols-2 gap-3">
                      <MetricBox label="現價" value={`${stock.price}`} />
                      <MetricBox label="推薦分數" value={`${stock.score}`} valueClassName={scoreClass(stock.score)} />
                      <MetricBox
                        label="漲跌幅"
                        value={`${stock.change_percent}%`}
                        valueClassName={
                          stock.change_percent > 0
                            ? "text-green-600"
                            : stock.change_percent < 0
                            ? "text-red-600"
                            : "text-slate-900"
                        }
                      />
                      <MetricBox label="成交量" value={formatNumber(stock.volume)} />
                    </div>

                    <div className="mb-4 space-y-3">
                      <StrategyRow label="進場區間" value={stock.entry_range} />
                      <StrategyRow label="出場價" value={`${stock.take_profit}`} />
                      <StrategyRow label="停損價" value={`${stock.stop_loss}`} />
                      <StrategyRow label="MA5 / MA20" value={`${stock.ma5} / ${stock.ma20}`} />
                    </div>

                    <div className="rounded-2xl bg-slate-50 p-4">
                      <div className="mb-1 text-sm font-medium text-slate-700">判斷原因</div>
                      <div className="text-sm leading-6 text-slate-600 break-words">{stock.reason}</div>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

function SummaryCard({ title, value }: { title: string; value: string }) {
  return (
    <div className="rounded-3xl bg-white p-5 shadow-sm">
      <div className="text-sm text-slate-500">{title}</div>
      <div className="mt-2 text-3xl font-bold text-slate-900">{value}</div>
    </div>
  );
}

function MetricBox({
  label,
  value,
  valueClassName = "",
}: {
  label: string;
  value: string;
  valueClassName?: string;
}) {
  return (
    <div className="rounded-2xl bg-slate-50 p-3">
      <div className="text-xs text-slate-500">{label}</div>
      <div className={`mt-1 text-lg font-bold ${valueClassName}`}>{value}</div>
    </div>
  );
}

function StrategyRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between gap-3 rounded-2xl border border-slate-200 px-4 py-3">
      <span className="text-sm text-slate-500">{label}</span>
      <span className="text-right text-sm font-semibold text-slate-900 break-all">{value}</span>
    </div>
  );
}

function EmptyBox({ text }: { text: string }) {
  return (
    <div className="rounded-2xl border border-dashed border-slate-300 px-4 py-10 text-center text-slate-500">
      {text}
    </div>
  );
}
