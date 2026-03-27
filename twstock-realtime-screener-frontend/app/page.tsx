"use client";

import { useEffect, useMemo, useState } from "react";

type Stock = {
  symbol: string;
  name: string;
  price: number;
  change: number;
  change_percent: number;
  volume: number;
  score: number;
  signal: string;
  entry_price: string;
  target_price: string;
  stop_loss: string;
};

type ApiResponse = {
  success: boolean;
  market_status: string;
  data_date: string;
  last_update: string;
  total: number;
  stocks: Stock[];
  source: string;
  error?: string;
};

const BACKEND_URL = "https://你的-render-後端網址/stocks";
// 例：const BACKEND_URL = "https://tw-stock-backend.onrender.com/stocks";

const priceRanges = [
  { key: "ALL", label: "全部" },
  { key: "0-50", label: "0~50" },
  { key: "50-100", label: "50~100" },
  { key: "100-200", label: "100~200" },
  { key: "200+", label: "200+" },
];

function inRange(price: number, range: string) {
  if (range === "ALL") return true;
  if (range === "0-50") return price >= 0 && price < 50;
  if (range === "50-100") return price >= 50 && price < 100;
  if (range === "100-200") return price >= 100 && price < 200;
  if (range === "200+") return price >= 200;
  return true;
}

export default function Home() {
  const [stocks, setStocks] = useState<Stock[]>([]);
  const [marketStatus, setMarketStatus] = useState("讀取中");
  const [lastUpdate, setLastUpdate] = useState("");
  const [dataDate, setDataDate] = useState("");
  const [source, setSource] = useState("");
  const [search, setSearch] = useState("1802");
  const [selectedRange, setSelectedRange] = useState("ALL");
  const [loading, setLoading] = useState(false);
  const [initialized, setInitialized] = useState(false);
  const [errorMsg, setErrorMsg] = useState("");

  const fetchStocks = async () => {
    try {
      setLoading(true);
      setErrorMsg("");

      const res = await fetch(BACKEND_URL, {
        method: "GET",
        cache: "no-store",
      });

      if (!res.ok) {
        throw new Error(`HTTP ${res.status}`);
      }

      const data: ApiResponse = await res.json();

      if (!data.success) {
        setStocks([]);
        setErrorMsg(data.error || "抓取資料失敗");
        return;
      }

      const list = Array.isArray(data.stocks) ? data.stocks : [];

      setStocks(list);
      setMarketStatus(data.market_status || "未知");
      setLastUpdate(data.last_update || "");
      setDataDate(data.data_date || "");
      setSource(data.source || "");
    } catch (error) {
      setStocks([]);
      setErrorMsg("無法連接後端，請檢查 Render 是否正常啟動，以及 BACKEND_URL 是否正確");
    } finally {
      setLoading(false);
      setInitialized(true);
    }
  };

  useEffect(() => {
    fetchStocks();

    const timer = setInterval(() => {
      fetchStocks();
    }, 30000);

    return () => clearInterval(timer);
  }, []);

  const filteredStocks = useMemo(() => {
    let result = [...stocks];

    result = result.filter((s) => inRange(s.price, selectedRange));

    const keyword = search.trim();
    if (keyword) {
      result = result.filter(
        (s) =>
          s.symbol.toLowerCase().includes(keyword.toLowerCase()) ||
          s.name.toLowerCase().includes(keyword.toLowerCase())
      );
    }

    result.sort((a, b) => b.score - a.score);
    return result;
  }, [stocks, selectedRange, search]);

  const top10 = useMemo(() => filteredStocks.slice(0, 10), [filteredStocks]);

  return (
    <main
      style={{
        minHeight: "100vh",
        background: "#031f36",
        color: "#ffffff",
        padding: "18px",
      }}
    >
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "240px 1fr",
          gap: "20px",
        }}
      >
        {/* 左側 */}
        <aside
          style={{
            borderRight: "1px solid rgba(255,255,255,0.08)",
            paddingRight: "18px",
          }}
        >
          <div
            style={{
              background: "#0b2b45",
              borderRadius: "16px",
              padding: "18px",
              marginBottom: "18px",
            }}
          >
            <div style={{ fontSize: "20px", fontWeight: 800 }}>台股智慧選股</div>
            <div style={{ marginTop: "6px", color: "#c8d7e6", fontSize: "14px" }}>
              盤中選股系統
            </div>
          </div>

          <div
            style={{
              background: "#0b2b45",
              borderRadius: "16px",
              padding: "18px",
              marginBottom: "18px",
            }}
          >
            <div style={{ marginBottom: "10px", color: "#d7e8f5" }}>狀態</div>
            <div style={{ fontSize: "28px", fontWeight: 800, marginBottom: "14px" }}>
              {marketStatus}
            </div>

            <div style={{ color: "#b7cadb", fontSize: "14px", marginBottom: "4px" }}>
              最後更新
            </div>
            <div style={{ fontWeight: 700, marginBottom: "14px" }}>
              {lastUpdate || "-"}
            </div>

            <div style={{ color: "#b7cadb", fontSize: "14px", marginBottom: "4px" }}>
              資料日期
            </div>
            <div style={{ fontWeight: 700, marginBottom: "14px" }}>
              {dataDate || "-"}
            </div>

            <div style={{ color: "#b7cadb", fontSize: "14px", marginBottom: "4px" }}>
              資料來源
            </div>
            <div style={{ fontWeight: 700 }}>
              {source || "-"}
            </div>
          </div>

          <div
            style={{
              background: "#0b2b45",
              borderRadius: "16px",
              padding: "18px",
              marginBottom: "18px",
            }}
          >
            <div style={{ marginBottom: "14px", fontWeight: 700 }}>價格分類</div>

            <div style={{ display: "grid", gap: "10px" }}>
              {priceRanges.map((item) => {
                const active = selectedRange === item.key;
                return (
                  <button
                    key={item.key}
                    onClick={() => setSelectedRange(item.key)}
                    style={{
                      border: "none",
                      borderRadius: "12px",
                      padding: "12px 14px",
                      textAlign: "left",
                      cursor: "pointer",
                      background: active ? "#18b9d4" : "#12395c",
                      color: "#fff",
                      fontWeight: 700,
                    }}
                  >
                    {item.label}
                  </button>
                );
              })}
            </div>
          </div>

          <div
            style={{
              background: "#0b2b45",
              borderRadius: "16px",
              padding: "18px",
            }}
          >
            <div style={{ color: "#b7cadb", fontSize: "14px", marginBottom: "6px" }}>
              目前區間
            </div>
            <div style={{ fontSize: "28px", fontWeight: 800, marginBottom: "14px" }}>
              {priceRanges.find((p) => p.key === selectedRange)?.label}
            </div>

            <div style={{ color: "#b7cadb", fontSize: "14px", marginBottom: "6px" }}>
              目前筆數
            </div>
            <div style={{ fontSize: "28px", fontWeight: 800 }}>
              {filteredStocks.length}
            </div>
          </div>
        </aside>

        {/* 右側 */}
        <section>
          <div
            style={{
              background: "#0b2b45",
              borderRadius: "18px",
              padding: "20px",
              marginBottom: "20px",
            }}
          >
            <div
              style={{
                display: "flex",
                justifyContent: "space-between",
                gap: "12px",
                alignItems: "center",
                flexWrap: "wrap",
              }}
            >
              <div>
                <div style={{ fontSize: "22px", fontWeight: 800 }}>股票列表</div>
                <div style={{ marginTop: "6px", fontSize: "14px", color: "#c1d5e6" }}>
                  盤中顯示準即時資料，13:30 後顯示當日收盤結果
                </div>
              </div>

              <div style={{ display: "flex", gap: "10px" }}>
                <input
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                  placeholder="輸入股票代號或名稱"
                  style={{
                    width: "250px",
                    background: "#0a2740",
                    color: "#fff",
                    border: "1px solid rgba(255,255,255,0.12)",
                    borderRadius: "12px",
                    padding: "12px 14px",
                    outline: "none",
                  }}
                />
                <button
                  onClick={fetchStocks}
                  style={{
                    border: "none",
                    borderRadius: "12px",
                    background: "#19c3de",
                    color: "#fff",
                    fontWeight: 800,
                    padding: "12px 18px",
                    cursor: "pointer",
                  }}
                >
                  立即更新
                </button>
              </div>
            </div>

            {loading && (
              <div
                style={{
                  marginTop: "14px",
                  background: "#10435c",
                  borderRadius: "12px",
                  padding: "12px 14px",
                  color: "#d8edf7",
                  fontSize: "14px",
                }}
              >
                資料更新中...
              </div>
            )}

            {!loading && errorMsg && (
              <div
                style={{
                  marginTop: "14px",
                  background: "#5a1f28",
                  borderRadius: "12px",
                  padding: "12px 14px",
                  color: "#ffd9df",
                  fontSize: "14px",
                }}
              >
                {errorMsg}
              </div>
            )}
          </div>

          <div
            style={{
              background: "#0b2b45",
              borderRadius: "18px",
              padding: "20px",
              marginBottom: "20px",
            }}
          >
            <div
              style={{
                display: "flex",
                justifyContent: "space-between",
                marginBottom: "14px",
                alignItems: "center",
              }}
            >
              <div style={{ fontSize: "18px", fontWeight: 800 }}>推薦前 10 檔</div>
              <div style={{ color: "#c1d5e6", fontSize: "14px" }}>依推薦分數排序</div>
            </div>

            {top10.length === 0 ? (
              <div
                style={{
                  background: "#16334b",
                  borderRadius: "12px",
                  padding: "16px",
                  color: "#d4e4f3",
                }}
              >
                {initialized ? "目前沒有符合條件的股票" : "載入中..."}
              </div>
            ) : (
              <div style={{ display: "grid", gap: "10px" }}>
                {top10.map((s) => (
                  <div
                    key={s.symbol}
                    style={{
                      background: "#16334b",
                      borderRadius: "12px",
                      padding: "14px 16px",
                    }}
                  >
                    <div style={{ fontWeight: 800, fontSize: "16px" }}>
                      {s.symbol} {s.name}
                    </div>
                    <div style={{ marginTop: "8px", color: "#d7e6f2", fontSize: "14px" }}>
                      價格 {s.price}　/　推薦分數 {s.score}　/　進場價 {s.entry_price}　/　出場價 {s.target_price}　/　停損價 {s.stop_loss}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>

          <div
            style={{
              background: "#0b2b45",
              borderRadius: "18px",
              overflowX: "auto",
            }}
          >
            <div
              style={{
                minWidth: "1250px",
              }}
            >
              <div
                style={{
                  display: "grid",
                  gridTemplateColumns:
                    "90px 120px 110px 110px 110px 140px 120px 160px 140px 140px",
                  background: "#113758",
                  padding: "14px 12px",
                  fontWeight: 800,
                }}
              >
                <div>代號</div>
                <div>名稱</div>
                <div>價格</div>
                <div>漲跌</div>
                <div>漲跌幅</div>
                <div>成交量</div>
                <div>推薦分數</div>
                <div>進場價</div>
                <div>出場價</div>
                <div>停損價</div>
              </div>

              {filteredStocks.length === 0 ? (
                <div
                  style={{
                    padding: "28px 16px",
                    color: "#d2e3f0",
                    textAlign: "center",
                  }}
                >
                  {initialized ? "沒有符合條件的資料" : "載入中..."}
                </div>
              ) : (
                filteredStocks.map((s) => (
                  <div
                    key={`${s.symbol}-${s.name}`}
                    style={{
                      display: "grid",
                      gridTemplateColumns:
                        "90px 120px 110px 110px 110px 140px 120px 160px 140px 140px",
                      padding: "14px 12px",
                      borderTop: "1px solid rgba(255,255,255,0.06)",
                      alignItems: "center",
                    }}
                  >
                    <div>{s.symbol}</div>
                    <div>{s.name}</div>
                    <div>{s.price}</div>
                    <div>{s.change}</div>
                    <div>{s.change_percent}%</div>
                    <div>{s.volume.toLocaleString()}</div>
                    <div>{s.score}</div>
                    <div>{s.entry_price}</div>
                    <div>{s.target_price}</div>
                    <div>{s.stop_loss}</div>
                  </div>
                ))
              )}
            </div>
          </div>
        </section>
      </div>
    </main>
  );
}
