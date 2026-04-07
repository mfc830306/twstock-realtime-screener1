"use client";

import { useEffect, useState } from "react";

const BACKEND_BASE = "https://twstock-realtime-screener1.onrender.com/stocks";

const ITEMS_PER_PAGE = 20;

export default function Home() {
  const [stocks, setStocks] = useState<any[]>([]);
  const [recommendations, setRecommendations] = useState<any[]>([]);
  const [categories, setCategories] = useState<any[]>([]);
  const [marketStatus, setMarketStatus] = useState("-");
  const [dataDate, setDataDate] = useState("-");
  const [lastUpdate, setLastUpdate] = useState("-");
  const [searchTerm, setSearchTerm] = useState("");
  const [selectedCategory, setSelectedCategory] = useState("all");
  const [rankType, setRankType] = useState("recommend");
  const [currentPage, setCurrentPage] = useState(1);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);

  // 🔥 核心：統一 API 請求
  async function fetchStocks() {
    setLoading(true);

    const params = new URLSearchParams({
      limit: ITEMS_PER_PAGE.toString(),
      offset: ((currentPage - 1) * ITEMS_PER_PAGE).toString(),
      category: selectedCategory,
      sort_by:
        rankType === "recommend"
          ? "recommendation_score"
          : rankType === "up"
          ? "change_percent"
          : "change_percent",
      sort_dir: rankType === "down" ? "asc" : "desc",
      q: searchTerm,
    });

    const res = await fetch(`${BACKEND_BASE}?${params}`, {
      cache: "no-store",
    });

    const data = await res.json();

    if (data.success) {
      setStocks(data.stocks || []);
      setRecommendations(data.recommendations || []);
      setCategories(data.categories || []);
      setMarketStatus(data.market_status || "-");
      setDataDate(data.data_date || "-");
      setLastUpdate(data.last_update || "-");
      setTotal(data.total || 0);
    }

    setLoading(false);
  }

  // 🔥 所有條件變動 → 打 API（不再前端算）
  useEffect(() => {
    fetchStocks();
  }, [currentPage, selectedCategory, rankType]);

  // 🔥 搜尋 debounce（關鍵）
  useEffect(() => {
    const timer = setTimeout(() => {
      setCurrentPage(1);
      fetchStocks();
    }, 400);

    return () => clearTimeout(timer);
  }, [searchTerm]);

  const totalPages = Math.ceil(total / ITEMS_PER_PAGE);

  // ================= UI完全不動 =================
  return (
    <main>
      {/* 你原本 UI 全部 그대로放這裡 */}
      {/* 👇只要把資料來源換成 stocks / recommendations */}

      {/* 範例 */}
      <div>市場狀態：{marketStatus}</div>
      <div>資料日期：{dataDate}</div>
      <div>更新時間：{lastUpdate}</div>

      <input
        value={searchTerm}
        onChange={(e) => setSearchTerm(e.target.value)}
      />

      <div>
        {stocks.map((s) => (
          <div key={s.symbol}>
            {s.symbol} {s.name} {s.price}
          </div>
        ))}
      </div>

      <div>
        第 {currentPage} / {totalPages}
      </div>

      <button onClick={() => setCurrentPage((p) => p - 1)}>上一頁</button>
      <button onClick={() => setCurrentPage((p) => p + 1)}>下一頁</button>
    </main>
  );
}
