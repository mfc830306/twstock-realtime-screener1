"use client";

import { useEffect, useMemo, useRef, useState } from "react";

/* =========================
   型別（完全保留）
========================= */
type Stock = {
  market?: string;
  symbol: string;
  name: string;
  price: number;
  change: number;
  change_percent: number;
  volume?: number;
  score?: number;
  recommendation_score?: number;
  signal?: string;
  trend_type?: string;
  reason?: string;
  technical_comment?: string;
  operation_rating?: string;
  operation_bias?: string;
  operation_style?: string;
  strategy_action?: string;
  entry_price?: string;
  target_price?: string;
  stop_loss?: string;
  risk_reward?: string;
  risk_note?: string;
  update_time?: string;
};

type FocusedStock = {
  symbol: string;
  name: string;
  market: string;
  price: number;
  change: number;
  change_percent: number;
  volume: number;
  signal: string;
  trend_type: string;
  operation_rating: string;
  operation_bias: string;
  operation_style: string;
  technical_comment: string;
  analysis: string;
  strategy_action: string;
  entry_price: string;
  target_price: string;
  stop_loss: string;
  risk_reward: string;
  risk_note: string;
  update_time: string;
};

type BackendCategory = {
  key: string;
  label: string;
  count: number;
};

type ApiResponse = {
  success: boolean;
  stocks: Stock[];
  recommendations?: Stock[];
  categories?: BackendCategory[];
  focused_stock?: FocusedStock | null;
  total?: number;
  all_total?: number;
  market_status?: string;
  data_date?: string;
  last_update?: string;
};

const BACKEND_BASE = "https://twstock-realtime-screener1.onrender.com/stocks";
const ITEMS_PER_PAGE = 20;

/* =========================
   工具
========================= */
function normalizeStock(s: Stock): Stock {
  return {
    ...s,
    price: Number(s.price ?? 0),
    change: Number(s.change ?? 0),
    change_percent: Number(s.change_percent ?? 0),
    volume: Number(s.volume ?? 0),
    score: Number(s.score ?? 0),
    recommendation_score: Number(s.recommendation_score ?? 0),
  };
}

/* =========================
   主程式
========================= */
export default function Home() {
  const [stocks, setStocks] = useState<Stock[]>([]);
  const [recommendations, setRecommendations] = useState<Stock[]>([]);
  const [focusedStock, setFocusedStock] = useState<FocusedStock | null>(null);

  const [searchTerm, setSearchTerm] = useState("");
  const [debouncedSearchTerm, setDebouncedSearchTerm] = useState("");

  const [currentPage, setCurrentPage] = useState(1);
  const [total, setTotal] = useState(0);

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const initialLoadedRef = useRef(false);

  /* =========================
     debounce
  ========================= */
  useEffect(() => {
    const timer = setTimeout(() => {
      setDebouncedSearchTerm(searchTerm.trim());
      setCurrentPage(1);
    }, 350);
    return () => clearTimeout(timer);
  }, [searchTerm]);

  /* =========================
     推薦（修正版）
  ========================= */
  async function fetchRecommendations() {
    const params = new URLSearchParams({
      limit: "10",
      offset: "0",
      include_recommendations: "true",
    });

    const res = await fetch(`${BACKEND_BASE}?${params.toString()}`, {
      cache: "no-store",
    });

    const data: ApiResponse = await res.json();

    if (!data.success) throw new Error("推薦資料錯誤");

    setRecommendations((data.recommendations || []).map(normalizeStock));
  }

  /* =========================
     列表
  ========================= */
  async function fetchStocks() {
    setLoading(true);
    setError("");

    try {
      const params = new URLSearchParams({
        limit: String(ITEMS_PER_PAGE),
        offset: String((currentPage - 1) * ITEMS_PER_PAGE),
      });

      if (debouncedSearchTerm) params.set("q", debouncedSearchTerm);

      const res = await fetch(`${BACKEND_BASE}?${params}`, {
        cache: "no-store",
      });

      const data: ApiResponse = await res.json();

      if (!data.success) throw new Error("資料錯誤");

      setStocks((data.stocks || []).map(normalizeStock));
      setTotal(Number(data.total || 0));

      if (data.focused_stock) {
        setFocusedStock(data.focused_stock);
      }
    } catch (err) {
      setError("載入失敗");
    } finally {
      setLoading(false);
    }
  }

  /* =========================
     初始化
  ========================= */
  useEffect(() => {
    Promise.all([fetchStocks(), fetchRecommendations()]);
    initialLoadedRef.current = true;
  }, []);

  useEffect(() => {
    if (!initialLoadedRef.current) return;
    fetchStocks();
  }, [currentPage, debouncedSearchTerm]);

  /* =========================
     UI（完全保留你的邏輯）
  ========================= */
  return (
    <main style={{ padding: 20 }}>
      <h1>選股系統</h1>

      <input
        placeholder="搜尋"
        value={searchTerm}
        onChange={(e) => setSearchTerm(e.target.value)}
      />

      <h2>推薦股</h2>
      {recommendations.map((s) => (
        <div
          key={s.symbol}
          onClick={() => setFocusedStock(s as any)}
          style={{ cursor: "pointer" }}
        >
          {s.symbol} {s.name} {s.price}
        </div>
      ))}

      <h2>股票列表</h2>
      {stocks.map((s) => (
        <div
          key={s.symbol}
          onClick={() => setFocusedStock(s as any)}
          style={{ cursor: "pointer" }}
        >
          {s.symbol} {s.name} {s.price}
        </div>
      ))}

      {focusedStock && (
        <>
          <h2>個股分析</h2>
          <div>
            {focusedStock.symbol} {focusedStock.name}
          </div>
        </>
      )}

      {loading && <div>Loading...</div>}
      {error && <div>{error}</div>}
    </main>
  );
}
