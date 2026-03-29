"use client";

import { useEffect, useMemo, useState } from "react";

type Stock = {
  market?: string;
  symbol: string;
  name: string;
  price: number;
  change: number;
  change_percent: number;
  volume?: number;
  score?: number;
  signal?: string;
  reason?: string;
  entry_price?: string;
  target_price?: string;
  stop_loss?: string;
};

type ApiResponse = {
  success: boolean;
  market_status?: string;
  data_date?: string;
  last_update?: string;
  total?: number;
  stocks: Stock[];
  message?: string;
};

const BACKEND_URL = "https://twstock-realtime-screener1.onrender.com/stocks";

const PRICE_CATEGORIES = [
  { key: "all", label: "全部" },
  { key: "0-50", label: "0-50" },
  { key: "50-100", label: "50-100" },
  { key: "100-200", label: "100-200" },
  { key: "200-500", label: "200-500" },
  { key: "500+", label: "500+" },
] as const;

type CategoryKey = (typeof PRICE_CATEGORIES)[number]["key"];
type RankType = "recommend" | "up" | "down";

function getPriceCategory(price: number): CategoryKey {
  if (price < 50) return "0-50";
  if (price < 100) return "50-100";
  if (price < 200) return "100-200";
  if (price < 500) return "200-500";
  return "500+";
}

function formatNumber(num?: number) {
  if (num === undefined || num === null || Number.isNaN(num)) return "-";
  return num.toLocaleString("zh-TW");
}

function formatSigned(value?: number, digits = 2) {
  if (value === undefined || value === null || Number.isNaN(value)) return "-";
  return `${value > 0 ? "+" : ""}${value.toFixed(digits)}`;
}

export default function Home() {
  const [stocks, setStocks] = useState<Stock[]>([]);
  const [marketStatus, setMarketStatus] = useState("");
  const [dataDate, setDataDate] = useState("");
  const [lastUpdate, setLastUpdate] = useState("");
  const [searchTerm, setSearchTerm] = useState("");
  const [selectedCategory, setSelectedCategory] = useState<CategoryKey>("all");
  const [rankType, setRankType] = useState<RankType>("recommend");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  async function fetchStocks() {
    try {
      setLoading(true);
      setError("");

      const res = await fetch(BACKEND_URL, { cache: "no-store" });
      const data: ApiResponse = await res.json();

      if (!data.success) {
        throw new Error(data.message || "取得資料失敗");
      }

      const safeStocks = (data.stocks || []).map((s) => ({
        ...s,
        change: Number(s.change ?? 0),
        change_percent: Number(s.change_percent ?? 0),
        price: Number(s.price ?? 0),
        volume: Number(s.volume ?? 0),
        score: Number(s.score ?? 0),
      }));

      setStocks(safeStocks);
      setMarketStatus(data.market_status || "");
      setDataDate(data.data_date || "");
      setLastUpdate(data.last_update || "");
    } catch (err) {
      setError(err instanceof Error ? err.message : "載入失敗");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    fetchStocks();
    const timer = setInterval(fetchStocks, 60000);
    return () => clearInterval(timer);
  }, []);

  const categoryCounts = useMemo(() => {
    const counts: Record<CategoryKey, number> = {
      all: stocks.length,
      "0-50": 0,
      "50-100": 0,
      "100-200": 0,
      "200-500": 0,
      "500+": 0,
    };

    for (const stock of stocks) {
      const key = getPriceCategory(stock.price);
      counts[key] += 1;
    }

    return counts;
  }, [stocks]);

  const filteredStocks = useMemo(() => {
    let result = [...stocks];

    if (selectedCategory !== "all") {
      result = result.filter((stock) => getPriceCategory(stock.price) === selectedCategory);
    }

    if (searchTerm.trim()) {
      const keyword = searchTerm.trim().toLowerCase();
      result = result.filter(
        (stock) =>
          stock.symbol.toLowerCase().includes(keyword) ||
          stock.name.toLowerCase().includes(keyword)
      );
    }

    if (rankType === "up") {
      result.sort((a, b) => b.change_percent - a.change_percent);
    } else if (rankType === "down") {
      result.sort((a, b) => a.change_percent - b.change_percent);
    } else {
      result.sort((a, b) => (b.score || 0) - (a.score || 0));
    }

    return result;
  }, [stocks, selectedCategory, searchTerm, rankType]);

  const recommendedStocks = useMemo(() => {
    return [...stocks]
      .sort((a, b) => (b.score || 0) - (a.score || 0))
      .slice(0, 10);
  }, [stocks]);

  return (
    <main
      style={{
        minHeight: "100vh",
        background: "linear-gradient(180deg, #08264d 0%, #0a2d5e 100%)",
        color: "#ffffff",
        padding: "24px",
      }}
    >
      <div style={{ maxWidth: "1400px", margin: "0 auto" }}>
        <div
          style={{
            background: "rgba(9, 36, 78, 0.9)",
            border: "1px solid rgba(80, 140, 220, 0.25)",
            borderRadius: "20px",
            padding: "18px 22px",
            marginBottom: "22px",
          }}
        >
          <div
            style={{
              display: "flex",
              flexWrap: "wrap",
              gap: "18px",
              fontSize: "15px",
              color: "#dbe9ff",
            }}
          >
            <div>
              <strong>市場狀態：</strong>{marketStatus || "-"}
            </div>
            <div>
              <strong>資料日期：</strong>{dataDate || "-"}
            </div>
            <div>
              <strong>最後更新：</strong>{lastUpdate || "-"}
            </div>
          </div>
        </div>

        {loading && (
          <div style={{ marginBottom: "16px", color: "#dbe9ff" }}>資料載入中...</div>
        )}

        {error && (
          <div
            style={{
              marginBottom: "16px",
              background: "rgba(255, 80, 80, 0.15)",
              border: "1px solid rgba(255, 120, 120, 0.35)",
              color: "#ffd4d4",
              padding: "12px 16px",
              borderRadius: "12px",
            }}
          >
            {error}
          </div>
        )}

        <section
          style={{
            display: "grid",
            gridTemplateColumns: "360px 1fr",
            gap: "22px",
            alignItems: "start",
            marginBottom: "22px",
          }}
        >
          <div
            style={{
              background: "linear-gradient(180deg, #0d2f63 0%, #0a2a57 100%)",
              border: "1px solid rgba(80, 140, 220, 0.22)",
              borderRadius: "22px",
              padding: "20px",
              minHeight: "590px",
            }}
          >
            <h2 style={{ fontSize: "22px", fontWeight: 800, marginBottom: "18px" }}>
              價格分類
            </h2>

            <div
              style={{
                display: "grid",
                gridTemplateColumns: "1fr 1fr",
                gap: "12px",
                marginBottom: "18px",
              }}
            >
              {PRICE_CATEGORIES.map((item) => {
                const active = selectedCategory === item.key;
                return (
                  <button
                    key={item.key}
                    onClick={() => setSelectedCategory(item.key)}
                    style={{
                      border: "none",
                      borderRadius: "14px",
                      padding: "14px 10px",
                      fontSize: "15px",
                      fontWeight: 800,
                      cursor: "pointer",
                      color: "#fff",
                      background: active
                        ? "linear-gradient(180deg, #61a8ff 0%, #3e7fe0 100%)"
                        : "linear-gradient(180deg, #2a67b8 0%, #1e4f93 100%)",
                      boxShadow: active
                        ? "0 8px 22px rgba(80, 150, 255, 0.25)"
                        : "none",
                    }}
                  >
                    {item.label} ({categoryCounts[item.key]})
                  </button>
                );
              })}
            </div>

            <input
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              placeholder="搜尋股票代號 / 名稱"
              style={{
                width: "100%",
                height: "48px",
                borderRadius: "14px",
                border: "none",
                outline: "none",
                padding: "0 16px",
                fontSize: "15px",
                marginBottom: "16px",
                background: "#e6edf7",
                color: "#123",
              }}
            />

            <div style={{ display: "flex", gap: "10px" }}>
              <button
                onClick={() => setRankType("recommend")}
                style={{
                  border: "none",
                  borderRadius: "14px",
                  padding: "12px 16px",
                  fontSize: "15px",
                  fontWeight: 800,
                  cursor: "pointer",
                  color: "#fff",
                  background:
                    rankType === "recommend"
                      ? "linear-gradient(180deg, #61a8ff 0%, #3e7fe0 100%)"
                      : "#184889",
                }}
              >
                推薦
              </button>

              <button
                onClick={() => setRankType("up")}
                style={{
                  border: "none",
                  borderRadius: "14px",
                  padding: "12px 16px",
                  fontSize: "15px",
                  fontWeight: 800,
                  cursor: "pointer",
                  color: "#fff",
                  background:
                    rankType === "up"
                      ? "linear-gradient(180deg, #61a8ff 0%, #3e7fe0 100%)"
                      : "#184889",
                }}
              >
                漲幅
              </button>

              <button
                onClick={() => setRankType("down")}
                style={{
                  border: "none",
                  borderRadius: "14px",
                  padding: "12px 16px",
                  fontSize: "15px",
                  fontWeight: 800,
                  cursor: "pointer",
                  color: "#fff",
                  background:
                    rankType === "down"
                      ? "linear-gradient(180deg, #61a8ff 0%, #3e7fe0 100%)"
                      : "#184889",
                }}
              >
                跌幅
              </button>
            </div>
          </div>

          <div
            style={{
              background: "linear-gradient(180deg, #0d2f63 0%, #0a2a57 100%)",
              border: "1px solid rgba(80, 140, 220, 0.22)",
              borderRadius: "22px",
              padding: "20px",
              minHeight: "590px",
            }}
          >
            <h2 style={{ fontSize: "22px", fontWeight: 800, marginBottom: "16px" }}>
              🔥 推薦10檔
            </h2>

            <div
              style={{
                maxHeight: "520px",
                overflowY: "auto",
                paddingRight: "6px",
              }}
            >
              {recommendedStocks.map((stock) => {
                const isUp = stock.change >= 0;
                const changeColor = isUp ? "#ff8d8d" : "#7fc3ff";

                return (
                  <div
                    key={stock.symbol}
                    style={{
                      background: "rgba(40, 87, 150, 0.45)",
                      border: "1px solid rgba(86, 145, 228, 0.22)",
                      borderRadius: "18px",
                      padding: "18px",
                      marginBottom: "14px",
                    }}
                  >
                    <div
                      style={{
                        display: "flex",
                        justifyContent: "space-between",
                        alignItems: "flex-start",
                        gap: "12px",
                        marginBottom: "10px",
                      }}
                    >
                      <div>
                        <div style={{ fontSize: "22px", fontWeight: 900, marginBottom: "6px" }}>
                          {stock.symbol} {stock.name}
                        </div>

                        <div
                          style={{
                            display: "flex",
                            gap: "14px",
                            flexWrap: "wrap",
                            alignItems: "center",
                          }}
                        >
                          <span
                            style={{
                              background: "rgba(255,255,255,0.08)",
                              borderRadius: "999px",
                              padding: "6px 10px",
                              fontSize: "14px",
                              fontWeight: 700,
                              color: "#ffd1d1",
                            }}
                          >
                            {stock.signal || "強勢多方"}
                          </span>

                          <span style={{ fontWeight: 700, color: "#dce9ff" }}>
                            股價 {stock.price}
                          </span>

                          <span style={{ fontWeight: 900, color: changeColor }}>
                            {formatSigned(stock.change)}　{formatSigned(stock.change_percent)}%
                          </span>
                        </div>
                      </div>

                      <div
                        style={{
                          color: "#ffd95f",
                          fontSize: "18px",
                          fontWeight: 900,
                          whiteSpace: "nowrap",
                        }}
                      >
                        分數 {stock.score ?? 0}
                      </div>
                    </div>

                    <div
                      style={{
                        background: "rgba(10, 37, 79, 0.6)",
                        borderRadius: "12px",
                        padding: "10px 12px",
                        marginBottom: "10px",
                        color: "#dbe8ff",
                        fontWeight: 700,
                        fontSize: "14px",
                      }}
                    >
                      策略重點　{stock.reason || "股價維持強勢、量能放大、短線表現活躍"}
                    </div>

                    <div
                      style={{
                        color: "#dbe8ff",
                        lineHeight: 1.8,
                        marginBottom: "12px",
                        fontSize: "15px",
                      }}
                    >
                      {stock.reason ||
                        "股價維持開高走高格局，收盤於當日高檔附近，顯示買盤承接力道偏強；漲幅明確擴大，屬盤面強勢表態個股，成交量明顯放大，代表市場關注度高。"}
                    </div>

                    <div
                      style={{
                        display: "grid",
                        gridTemplateColumns: "1fr 1fr 1fr",
                        gap: "12px",
                      }}
                    >
                      <div
                        style={{
                          background: "rgba(9, 36, 78, 0.8)",
                          borderRadius: "14px",
                          padding: "12px",
                        }}
                      >
                        <div style={{ color: "#aecdff", fontSize: "13px", marginBottom: "6px" }}>
                          進場
                        </div>
                        <div style={{ fontWeight: 900, fontSize: "16px" }}>
                          {stock.entry_price || "-"}
                        </div>
                      </div>

                      <div
                        style={{
                          background: "rgba(9, 36, 78, 0.8)",
                          borderRadius: "14px",
                          padding: "12px",
                        }}
                      >
                        <div style={{ color: "#aecdff", fontSize: "13px", marginBottom: "6px" }}>
                          目標
                        </div>
                        <div style={{ fontWeight: 900, fontSize: "16px" }}>
                          {stock.target_price || "-"}
                        </div>
                      </div>

                      <div
                        style={{
                          background: "rgba(9, 36, 78, 0.8)",
                          borderRadius: "14px",
                          padding: "12px",
                        }}
                      >
                        <div style={{ color: "#aecdff", fontSize: "13px", marginBottom: "6px" }}>
                          停損
                        </div>
                        <div style={{ fontWeight: 900, fontSize: "16px" }}>
                          {stock.stop_loss || "-"}
                        </div>
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        </section>

        <section
          style={{
            background: "linear-gradient(180deg, #0d2f63 0%, #0a2a57 100%)",
            border: "1px solid rgba(80, 140, 220, 0.22)",
            borderRadius: "22px",
            padding: "20px",
          }}
        >
          <h2 style={{ fontSize: "22px", fontWeight: 800, marginBottom: "16px" }}>
            股票列表 ({filteredStocks.length})
          </h2>

          <div
            style={{
              overflowX: "auto",
              borderRadius: "18px",
            }}
          >
            <table
              style={{
                width: "100%",
                borderCollapse: "collapse",
                minWidth: "980px",
                overflow: "hidden",
              }}
            >
              <thead>
                <tr
                  style={{
                    background: "linear-gradient(180deg, #3570bd 0%, #285d9f 100%)",
                  }}
                >
                  <th style={thStyle}>代號</th>
                  <th style={thStyle}>名稱</th>
                  <th style={thStyle}>股價</th>
                  <th style={thStyle}>漲跌</th>
                  <th style={thStyle}>成交量</th>
                  <th style={thStyle}>分數</th>
                </tr>
              </thead>

              <tbody>
                {filteredStocks.map((stock) => {
                  const isUp = stock.change >= 0;
                  const color = isUp ? "#ff8d8d" : "#7fc3ff";

                  return (
                    <tr
                      key={stock.symbol}
                      style={{
                        borderBottom: "1px solid rgba(255,255,255,0.08)",
                        background: "rgba(8, 36, 76, 0.55)",
                      }}
                    >
                      <td style={tdStyle}>{stock.symbol}</td>
                      <td style={tdStyle}>{stock.name}</td>
                      <td style={tdStyle}>{stock.price}</td>
                      <td style={tdStyle}>
                        <div style={{ color, fontWeight: 900, fontSize: "18px" }}>
                          {formatSigned(stock.change)}
                        </div>
                        <div style={{ color, fontWeight: 800, fontSize: "15px", marginTop: "4px" }}>
                          {formatSigned(stock.change_percent)}%
                        </div>
                      </td>
                      <td style={tdStyle}>{formatNumber(stock.volume)}</td>
                      <td style={tdStyle}>{stock.score ?? 0}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </section>
      </div>
    </main>
  );
}

const thStyle: React.CSSProperties = {
  padding: "16px 14px",
  textAlign: "center",
  color: "#ffffff",
  fontSize: "16px",
  fontWeight: 800,
};

const tdStyle: React.CSSProperties = {
  padding: "18px 14px",
  textAlign: "center",
  color: "#ffffff",
  fontSize: "15px",
  fontWeight: 700,
};
