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

export default function Page() {
  const [stocks, setStocks] = useState<Stock[]>([]);
  const [loading, setLoading] = useState(true);
  const [bucket, setBucket] = useState("all");
  const [keyword, setKeyword] = useState("");

  useEffect(() => {
    fetch(`${API_BASE}/stocks`)
      .then((res) => res.json())
      .then((data) => {
        setStocks(data.stocks || []);
        setLoading(false);
      })
      .catch(() => setLoading(false));
  }, []);

  const filtered = useMemo(() => {
    return stocks.filter((s) => {
      const matchBucket = bucket === "all" || getBucket(s.price) === bucket;
      const matchKeyword =
        !keyword ||
        s.symbol.includes(keyword) ||
        s.name.includes(keyword);
      return matchBucket && matchKeyword;
    });
  }, [stocks, bucket, keyword]);

  const top10 = [...stocks].sort((a, b) => b.score - a.score).slice(0, 10);

  return (
    <main className="min-h-screen bg-[#061a40] text-white p-6">
      {/* 標題 */}
      <h1 className="text-3xl font-bold mb-4">台股分類選股系統</h1>

      {/* 搜尋 */}
      <div className="flex gap-2 mb-6">
        <input
          className="px-3 py-2 rounded bg-[#0b245a] text-white border border-white/20"
          placeholder="搜尋股票代碼 / 名稱"
          value={keyword}
          onChange={(e) => setKeyword(e.target.value)}
        />
        <button
          className="bg-blue-500 px-4 rounded"
          onClick={() => location.reload()}
        >
          重新整理
        </button>
      </div>

      {/* 分類 */}
      <div className="flex flex-wrap gap-2 mb-6">
        {PRICE_BUCKETS.map((b) => (
          <button
            key={b.key}
            onClick={() => setBucket(b.key)}
            className={`px-3 py-1 rounded ${
              bucket === b.key
                ? "bg-blue-500"
                : "bg-[#0b245a] hover:bg-[#11306f]"
            }`}
          >
            {b.label}
          </button>
        ))}
      </div>

      {/* 推薦 */}
      <div className="mb-8">
        <h2 className="text-xl mb-2">🔥 推薦前10</h2>
        <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
          {top10.map((s) => (
            <div key={s.symbol} className="bg-[#0b245a] p-3 rounded">
              <div className="font-bold">
                {s.name} ({s.symbol})
              </div>
              <div>價格: {s.price}</div>
              <div className={s.change_percent >= 0 ? "text-red-400" : "text-green-400"}>
                {s.change_percent}%
              </div>
              <div>分數: {s.score}</div>
              <div className="text-sm mt-1">進場: {s.entry_price}</div>
              <div className="text-sm">目標: {s.target_price}</div>
              <div className="text-sm">停損: {s.stop_loss}</div>
            </div>
          ))}
        </div>
      </div>

      {/* 表格 */}
      {loading ? (
        <div>載入中...</div>
      ) : (
        <table className="w-full text-sm">
          <thead className="bg-[#0b245a]">
            <tr>
              <th className="p-2 text-left">代碼</th>
              <th className="p-2 text-left">名稱</th>
              <th className="p-2">價格</th>
              <th className="p-2">漲跌%</th>
              <th className="p-2">量</th>
              <th className="p-2">分數</th>
              <th className="p-2">進場</th>
              <th className="p-2">目標</th>
              <th className="p-2">停損</th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((s) => (
              <tr key={s.symbol} className="border-b border-white/10">
                <td className="p-2">{s.symbol}</td>
                <td className="p-2">{s.name}</td>
                <td className="p-2 text-center">{s.price}</td>
                <td
                  className={`p-2 text-center ${
                    s.change_percent >= 0 ? "text-red-400" : "text-green-400"
                  }`}
                >
                  {s.change_percent}
                </td>
                <td className="p-2 text-center">{s.volume}</td>
                <td className="p-2 text-center">{s.score}</td>
                <td className="p-2 text-center">{s.entry_price}</td>
                <td className="p-2 text-center">{s.target_price}</td>
                <td className="p-2 text-center">{s.stop_loss}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </main>
  );
}
