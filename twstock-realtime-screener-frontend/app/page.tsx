"use client";

import { useEffect, useMemo, useState } from "react";

type Stock = {
  symbol: string;
  name: string;
  price: number;
  change_percent: number;
  volume?: number;
  score?: number;
  signal?: string;
  reason?: string;
  entry_price?: string;
  target_price?: string;
  stop_loss?: string;
};

const BACKEND_URL = "https://twstock-realtime-screener1.onrender.com/stocks";

export default function Home() {
  const [stocks, setStocks] = useState<Stock[]>([]);
  const [topStocks, setTopStocks] = useState<Stock[]>([]);
  const [search, setSearch] = useState("");
  const [priceFilter, setPriceFilter] = useState("all");
  const [sortType, setSortType] = useState("score");

  useEffect(() => {
    fetch(BACKEND_URL)
      .then((res) => res.json())
      .then((data) => {
        setStocks(data.stocks || []);
        setTopStocks(data.top_recommendations || []);
      });
  }, []);

  // 價格分類
  const filteredStocks = useMemo(() => {
    let result = [...stocks];

    if (priceFilter !== "all") {
      const [min, max] = priceFilter.split("-").map(Number);
      result = result.filter(
        (s) => s.price >= min && s.price <= max
      );
    }

    if (search) {
      result = result.filter(
        (s) =>
          s.symbol.includes(search) ||
          s.name.includes(search)
      );
    }

    if (sortType === "up") {
      result.sort((a, b) => b.change_percent - a.change_percent);
    } else if (sortType === "down") {
      result.sort((a, b) => a.change_percent - b.change_percent);
    } else {
      result.sort((a, b) => (b.score || 0) - (a.score || 0));
    }

    return result;
  }, [stocks, search, priceFilter, sortType]);

  const categories = [
    { label: "全部", value: "all" },
    { label: "0-50", value: "0-50" },
    { label: "50-100", value: "50-100" },
    { label: "100-200", value: "100-200" },
    { label: "200-500", value: "200-500" },
    { label: "500+", value: "500-99999" },
  ];

  return (
    <div className="bg-[#0f172a] text-white min-h-screen p-4">
      {/* 標題 */}
      <h1 className="text-2xl font-bold mb-4 text-center">
        台股即時選股系統
      </h1>

      {/* 上方區塊 */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4">
        {/* 左：分類 */}
        <div className="bg-[#1e293b] p-4 rounded-xl">
          <h2 className="mb-3 font-bold">價格分類</h2>

          <div className="flex flex-wrap gap-2 mb-3">
            {categories.map((c) => (
              <button
                key={c.value}
                onClick={() => setPriceFilter(c.value)}
                className={`px-3 py-1 rounded ${
                  priceFilter === c.value
                    ? "bg-blue-500"
                    : "bg-gray-600"
                }`}
              >
                {c.label}
              </button>
            ))}
          </div>

          {/* 搜尋 */}
          <input
            type="text"
            placeholder="搜尋股票..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full p-2 rounded text-black"
          />

          {/* 排序 */}
          <div className="flex gap-2 mt-3">
            <button onClick={() => setSortType("score")} className="bg-gray-600 px-3 py-1 rounded">
              推薦
            </button>
            <button onClick={() => setSortType("up")} className="bg-gray-600 px-3 py-1 rounded">
              漲幅
            </button>
            <button onClick={() => setSortType("down")} className="bg-gray-600 px-3 py-1 rounded">
              跌幅
            </button>
          </div>
        </div>

        {/* 右：推薦 */}
        <div className="bg-[#1e293b] p-4 rounded-xl">
          <h2 className="mb-3 font-bold">🔥 推薦10檔</h2>

          <div className="space-y-3 max-h-[400px] overflow-y-auto">
            {topStocks.map((s) => (
              <div key={s.symbol} className="bg-[#334155] p-3 rounded">
                <div className="flex justify-between">
                  <div>
                    {s.symbol} {s.name}
                  </div>
                  <div className="text-yellow-300">
                    {s.score}
                  </div>
                </div>

                <div className="text-sm text-gray-300 mt-1">
                  {s.reason}
                </div>

                <div className="text-xs mt-1 text-gray-400">
                  進場: {s.entry_price} ｜ 目標: {s.target_price} ｜ 停損: {s.stop_loss}
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* 股票列表 */}
      <div className="bg-[#1e293b] p-4 rounded-xl overflow-x-auto">
        <h2 className="mb-3 font-bold">股票列表 ({filteredStocks.length})</h2>

        <div className="min-w-[900px]">
          {/* 表頭 */}
          <div className="grid grid-cols-6 bg-gray-700 p-2 rounded text-center">
            <div>代號</div>
            <div>名稱</div>
            <div>股價</div>
            <div>漲跌%</div>
            <div>成交量</div>
            <div>分數</div>
          </div>

          {/* 資料 */}
          {filteredStocks.map((s) => (
            <div
              key={s.symbol}
              className="grid grid-cols-6 border-b border-gray-700 p-2 text-center items-center"
            >
              <div>{s.symbol}</div>
              <div>{s.name}</div>
              <div>{s.price}</div>
              <div
                className={
                  s.change_percent > 0
                    ? "text-red-400"
                    : "text-green-400"
                }
              >
                {s.change_percent}%
              </div>
              <div>{s.volume}</div>
              <div className="text-yellow-300">{s.score}</div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
