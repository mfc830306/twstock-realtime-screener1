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
  { key: "lt10", label: "10元以下" },
  { key: "10_20", label: "10-20元" },
  { key: "20_50", label: "20-50元" },
  { key: "50_100", label: "50-100元" },
  { key: "100_200", label: "100-200元" },
  { key: "200_500", label: "200-500元" },
  { key: "500_1000", label: "500-1000元" },
  { key: "gte1000", label: "1000元以上" },
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

  const filteredStocks = useMemo(() => {
    let list = [...stocks];

    if (bucket !== "all") {
      list = list.filter((s) => getBucket(s.price) === bucket);
    }

    const kw = keyword.trim().toLowerCase();
    if (kw) {
      list = list.filter(
        (s) =>
          s.symbol.toLowerCase().includes(kw) ||
          s.name.toLowerCase().includes(kw)
      );
    }

    list.sort((a, b) => {
      if (b.score !== a.score) return b.score - a.score;
      if (b.change_percent !== a.change_percent) return b.change_percent - a.change_percent;
      return b.volume - a.volume;
    });

    return list;
  }, [stocks, bucket, keyword]);

  const top10 = useMemo(() => filteredStocks.slice(0, 10), [filteredStocks]);

  return (
    <main className="min-h-screen bg-[#061a40] text-white">
      <div className="mx-auto max-w-[1400px] px-4 py-6">
        <h1 className="mb-2 text-3xl font-bold">台股分類選股系統</h1>
        <p className="mb-6 text-blue-100">
          顯示全部台股，依股價分類、搜尋，並提供推薦前 10 檔
        </p>

        <div className="mb-4 flex flex-col gap-3 md:flex-row">
          <input
            value={keyword}
            onChange={(e) => setKeyword(e.target.value)}
            placeholder="搜尋股票代碼 / 名稱，例如 2330 或 台積電"
            className="w-full rounded-lg border border-blue-300/20 bg-[#0c2a5c] px-4 py-3 text-white placeholder:text-blue-100/50 outline-none md:w-[360px]"
          />
          <button
            onClick={() => window.location.reload()}
            className="rounded-lg bg-blue-500 px-5 py-3 font-semibold text-white hover:bg-blue-400"
          >
            重新整理
          </button>
        </div>

        <div className="mb-6 flex flex-wrap gap-2">
          {PRICE_BUCKETS.map((b) => (
            <button
              key={b.key}
              onClick={() => setBucket(b.key)}
              className={`rounded-lg px-4 py-2 text-sm font-medium ${
                bucket === b.key
                  ? "bg-blue-500 text-white"
                  : "bg-[#0c2a5c] text-white hover:bg-[#133673]"
              }`}
            >
              {b.label}
            </button>
          ))}
        </div>

        <section className="mb-8">
          <h2 className="mb-3 text-2xl font-bold">推薦前 10 檔</h2>

          {loading ? (
            <div className="rounded-xl bg-[#0c2a5c] p-6">載入中...</div>
          ) : error ? (
            <div className="rounded-xl bg-red-500/20 p-6 text-red-200">
              載入失敗：{error}
            </div>
          ) : top10.length === 0 ? (
            <div className="rounded-xl bg-[#0c2a5c] p-6">目前沒有資料</div>
          ) : (
            <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-5">
              {top10.map((s) => (
                <div key={s.symbol} className="rounded-xl bg-[#0c2a5c] p-4">
                  <div className="mb-2 text-lg font-bold">
                    {s.name} <span className="text-blue-200">{s.symbol}</span>
                  </div>
                  <div className="space-y-1 text-sm">
                    <div>市場：{s.market}</div>
                    <div>現價：{s.price}</div>
                    <div className={s.change_percent >= 0 ? "text-red-300" : "text-green-300"}>
                      漲跌幅：{formatChange(s.change_percent)}
                    </div>
                    <div>成交量：{formatVolume(s.volume)}</div>
                    <div>推薦分數：{s.score}</div>
                    <div>訊號：{s.signal || "-"}</div>
                    <div>進場價：{s.entry_price || "-"}</div>
                    <div>目標價：{s.target_price || "-"}</div>
                    <div>停損價：{s.stop_loss || "-"}</div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </section>

        <section>
          <h2 className="mb-3 text-2xl font-bold">股票清單</h2>

          {loading ? (
            <div className="rounded-xl bg-[#0c2a5c] p-6">載入股票資料中...</div>
          ) : error ? (
            <div className="rounded-xl bg-red-500/20 p-6 text-red-200">
              載入失敗：{error}
            </div>
          ) : filteredStocks.length === 0 ? (
            <div className="rounded-xl bg-[#0c2a5c] p-6">查無符合條件的股票</div>
          ) : (
            <div className="overflow-x-auto rounded-xl bg-[#0c2a5c]">
              <table className="min-w-full text-sm text-white">
                <thead className="bg-[#12326d]">
                  <tr>
                    <th className="px-4 py-3 text-left">代碼</th>
                    <th className="px-4 py-3 text-left">名稱</th>
                    <th className="px-4 py-3 text-left">市場</th>
                    <th className="px-4 py-3 text-right">現價</th>
                    <th className="px-4 py-3 text-right">漲跌幅</th>
                    <th className="px-4 py-3 text-right">成交量</th>
                    <th className="px-4 py-3 text-right">分數</th>
                    <th className="px-4 py-3 text-left">訊號</th>
                    <th className="px-4 py-3 text-left">進場價</th>
                    <th className="px-4 py-3 text-left">目標價</th>
                    <th className="px-4 py-3 text-left">停損價</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredStocks.map((s, i) => (
                    <tr
                      key={`${s.symbol}-${i}`}
                      className="border-t border-blue-200/10 hover:bg-[#143872]"
                    >
                      <td className="px-4 py-3">{s.symbol}</td>
                      <td className="px-4 py-3">{s.name}</td>
                      <td className="px-4 py-3">{s.market}</td>
                      <td className="px-4 py-3 text-right">{s.price}</td>
                      <td
                        className={`px-4 py-3 text-right ${
                          s.change_percent >= 0 ? "text-red-300" : "text-green-300"
                        }`}
                      >
                        {formatChange(s.change_percent)}
                      </td>
                      <td className="px-4 py-3 text-right">{formatVolume(s.volume)}</td>
                      <td className="px-4 py-3 text-right">{s.score}</td>
                      <td className="px-4 py-3">{s.signal || "-"}</td>
                      <td className="px-4 py-3">{s.entry_price || "-"}</td>
                      <td className="px-4 py-3">{s.target_price || "-"}</td>
                      <td className="px-4 py-3">{s.stop_loss || "-"}</td>
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
