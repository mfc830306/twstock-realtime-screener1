"use client";

import { useEffect, useMemo, useState } from "react";

type Stock = {
  symbol: string;
  name: string;
  price: number;
  change: number;
  change_percent: number;
  volume?: number;
  score?: number;
  recommendation_score?: number;
  signal?: string;
  reason?: string;
  entry_price?: string;
  target_price?: string;
  stop_loss?: string;
  category?: string;
};

const BACKEND_URL = "https://twstock-realtime-screener1.onrender.com/stocks";

export default function Home() {
  const [stocks, setStocks] = useState<Stock[]>([]);
  const [recommendations, setRecommendations] = useState<Stock[]>([]);
  const [categories, setCategories] = useState<any[]>([]);
  const [marketStatus, setMarketStatus] = useState("");
  const [dataDate, setDataDate] = useState("");
  const [lastUpdate, setLastUpdate] = useState("");

  // =========================
  // Fetch
  // =========================
  useEffect(() => {
    fetch(`${BACKEND_URL}?limit=5000`)
      .then((res) => res.json())
      .then((data) => {
        setStocks(data.stocks || []);
        setRecommendations(data.recommendations || []);
        setCategories(data.categories || []);
        setMarketStatus(data.market_status || "");
        setDataDate(data.data_date || "");
        setLastUpdate(data.last_update || "");
      });
  }, []);

  // =========================
  // 市場狀態顏色
  // =========================
  const marketColor = useMemo(() => {
    if (marketStatus === "開盤") return "#00c853"; // 綠
    if (marketStatus === "收盤") return "#ff1744"; // 紅
    return "#9e9e9e"; // 灰（休市）
  }, [marketStatus]);

  // =========================
  // 資料狀態文字
  // =========================
  const dataStatusText = useMemo(() => {
    if (marketStatus === "開盤") return "即時資料";
    if (marketStatus === "收盤") return "收盤資料";
    return "前一交易日資料";
  }, [marketStatus]);

  // =========================
  // UI
  // =========================
  return (
    <div style={{ padding: 20 }}>

      {/* ===== 市場狀態列 ===== */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: 20,
          marginBottom: 20,
          fontSize: 14,
        }}
      >
        {/* 狀態燈 */}
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <div
            style={{
              width: 10,
              height: 10,
              borderRadius: "50%",
              backgroundColor: marketColor,
            }}
          />
          <div>市場狀態：{marketStatus}</div>
        </div>

        <div>資料日期：{dataDate}</div>

        <div>最後更新：{lastUpdate}</div>

        <div style={{ color: "#888" }}>
          （{dataStatusText}）
        </div>
      </div>

      {/* ===== 推薦10檔 ===== */}
      <div style={{ marginBottom: 30 }}>
        <h3>推薦 10 檔</h3>

        {recommendations.map((stock, i) => (
          <div
            key={i}
            style={{
              border: "1px solid #ddd",
              padding: 10,
              marginBottom: 10,
            }}
          >
            <div>
              {stock.symbol} {stock.name}
            </div>

            <div>
              {stock.price}（{stock.change} / {stock.change_percent}%）
            </div>

            <div>訊號：{stock.signal}</div>

            <div style={{ fontSize: 13, lineHeight: 1.5 }}>
              {stock.reason}
            </div>

            <div>
              進場：{stock.entry_price}｜
              目標：{stock.target_price}｜
              停損：{stock.stop_loss}
            </div>
          </div>
        ))}
      </div>

      {/* ===== 股票列表 ===== */}
      <div>
        <h3>全部股票</h3>

        {stocks.map((stock, i) => (
          <div
            key={i}
            style={{
              borderBottom: "1px solid #eee",
              padding: "8px 0",
            }}
          >
            {stock.symbol} {stock.name}　
            {stock.price}（{stock.change} / {stock.change_percent}%）
          </div>
        ))}
      </div>
    </div>
  );
}
