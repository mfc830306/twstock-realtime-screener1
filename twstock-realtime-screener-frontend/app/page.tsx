"use client";

import { useEffect, useMemo, useRef, useState } from "react";

type Stock = {
  symbol: string;
  name: string;
  price: number;
  change: number;
  change_percent: number;
  volume: number;
  score: number;
  entry_price?: string;
  target_price?: string;
  stop_loss?: string;
};

type ApiResponse = {
  success: boolean;
  mode: "live" | "close";
  total: number;
  stocks: Stock[];
};

const API_BASE = "https://twstock-realtime-screener1.onrender.com";

const PRICE_RANGES = [
  { key: "0-50", label: "0~50", min: 0, max: 50 },
  { key: "50-100", label: "50~100", min: 50, max: 100 },
  { key: "100-200", label: "100~200", min: 100, max: 200 },
  { key: "200+", label: "200+", min: 200, max: 999999 },
];

function formatNumber(value: number) {
  return new Intl.NumberFormat("zh-TW").format(value);
}

function getModeText(mode: "live" | "close") {
  return mode === "live" ? "🟢 盤中（準即時）" : "🔴 收盤（官方）";
}

export default function HomePage() {
  const [stocks, setStocks] = useState<Stock[]>([]);
  const [activeRange, setActiveRange] = useState<string>("50-100");
  const [searchText, setSearchText] = useState<string>("");
  const [marketMode, setMarketMode] = useState<"live" | "close">("close");
  const [lastUpdated, setLastUpdated] = useState<string>("");
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string>("");

  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const selectedRange = useMemo(() => {
    return PRICE_RANGES.find((r) => r.key === activeRange) || PRICE_RANGES[1];
  }, [activeRange]);

  const fetchStocks = async () => {
    try {
      setLoading(true);
      setError("");

      const url = `${API_BASE}/stocks?min_price=${selectedRange.min}&max_price=${selectedRange.max}&t=${Date.now()}`;
      const res = await fetch(url, { cache: "no-store" });

      if (!res.ok) {
        throw new Error(`HTTP ${res.status}`);
      }

      const data: ApiResponse = await res.json();

      if (!data.success) {
        throw new Error("後端回傳失敗");
      }

      setStocks(Array.isArray(data.stocks) ? data.stocks : []);
      setMarketMode(data.mode || "close");
      setLastUpdated(
        new Date().toLocaleString("zh-TW", {
          hour12: false,
        })
      );
    } catch (err) {
      console.error("fetchStocks error:", err);
      setStocks([]);
      setError("資料更新失敗，請檢查後端 API");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchStocks();

    if (timerRef.current) {
      clearInterval(timerRef.current);
    }

    timerRef.current = setInterval(() => {
      fetchStocks();
    }, marketMode === "live" ? 3000 : 60000);

    return () => {
      if (timerRef.current) {
        clearInterval(timerRef.current);
      }
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeRange, marketMode]);

  const filteredStocks = useMemo(() => {
    const keyword = searchText.trim().toLowerCase();

    if (!keyword) return stocks;

    return stocks.filter((stock) => {
      return (
        stock.symbol.toLowerCase().includes(keyword) ||
        stock.name.toLowerCase().includes(keyword)
      );
    });
  }, [stocks, searchText]);

  const top10Stocks = useMemo(() => {
    return [...filteredStocks].sort((a, b) => b.score - a.score).slice(0, 10);
  }, [filteredStocks]);

  return (
    <main
      style={{
        minHeight: "100vh",
        background: "#061a2b",
        color: "#ffffff",
      }}
    >
      <div
        style={{
          display: "flex",
          gap: "20px",
          maxWidth: "1600px",
          margin: "0 auto",
          padding: "20px",
          minHeight: "100vh",
          boxSizing: "border-box",
        }}
      >
        {/* 左側欄 */}
        <aside
          style={{
            width: "240px",
            flexShrink: 0,
            borderRight: "1px solid rgba(255,255,255,0.12)",
            paddingRight: "20px",
          }}
        >
          <div
            style={{
              marginBottom: "20px",
              padding: "16px",
              borderRadius: "14px",
              background: "rgba(255,255,255,0.05)",
            }}
          >
            <div
              style={{
                fontSize: "24px",
                fontWeight: 700,
                marginBottom: "6px",
              }}
            >
              台股智慧選股
            </div>
            <div
              style={{
                fontSize: "14px",
                color: "rgba(255,255,255,0.7)",
              }}
            >
              盤中選股系統
            </div>
          </div>

          <div
            style={{
              marginBottom: "20px",
              padding: "16px",
              borderRadius: "14px",
              background: "rgba(255,255,255,0.05)",
              lineHeight: 1.8,
            }}
          >
            <div style={{ fontSize: "14px", color: "rgba(255,255,255,0.7)" }}>
              狀態
            </div>
            <div style={{ fontSize: "16px", fontWeight: 700 }}>
              {getModeText(marketMode)}
            </div>

            <div
              style={{
                marginTop: "12px",
                fontSize: "14px",
                color: "rgba(255,255,255,0.7)",
              }}
            >
              最後更新
            </div>
            <div style={{ fontSize: "14px" }}>{lastUpdated || "-"}</div>

            <div
              style={{
                marginTop: "12px",
                fontSize: "14px",
                color: "rgba(255,255,255,0.7)",
              }}
            >
              更新頻率
            </div>
            <div style={{ fontSize: "14px" }}>
              {marketMode === "live" ? "每 3 秒" : "每 60 秒"}
            </div>
          </div>

          <div
            style={{
              marginBottom: "20px",
              padding: "16px",
              borderRadius: "14px",
              background: "rgba(255,255,255,0.05)",
            }}
          >
            <div
              style={{
                fontSize: "15px",
                fontWeight: 700,
                marginBottom: "12px",
              }}
            >
              價格分類
            </div>

            {PRICE_RANGES.map((range) => {
              const active = range.key === activeRange;

              return (
                <button
                  key={range.key}
                  onClick={() => setActiveRange(range.key)}
                  style={{
                    width: "100%",
                    textAlign: "left",
                    padding: "12px 14px",
                    marginBottom: "10px",
                    border: "none",
                    borderRadius: "10px",
                    background: active ? "#00bcd4" : "#12304a",
                    color: "#ffffff",
                    cursor: "pointer",
                    fontSize: "14px",
                    fontWeight: active ? 700 : 500,
                  }}
                >
                  {range.label}
                </button>
              );
            })}
          </div>

          <div
            style={{
              padding: "16px",
              borderRadius: "14px",
              background: "rgba(255,255,255,0.05)",
              lineHeight: 1.8,
            }}
          >
            <div style={{ fontSize: "14px", color: "rgba(255,255,255,0.7)" }}>
              目前區間
            </div>
            <div>{selectedRange.label}</div>

            <div
              style={{
                marginTop: "12px",
                fontSize: "14px",
                color: "rgba(255,255,255,0.7)",
              }}
            >
              目前筆數
            </div>
            <div>{formatNumber(filteredStocks.length)}</div>
          </div>
        </aside>

        {/* 右側主內容 */}
        <section
          style={{
            flex: 1,
            minWidth: 0,
          }}
        >
          {/* 頂部工具列 */}
          <div
            style={{
              marginBottom: "20px",
              padding: "18px",
              borderRadius: "16px",
              background: "rgba(255,255,255,0.05)",
            }}
          >
            <div
              style={{
                display: "flex",
                gap: "12px",
                justifyContent: "space-between",
                alignItems: "center",
                flexWrap: "wrap",
              }}
            >
              <div>
                <div
                  style={{
                    fontSize: "28px",
                    fontWeight: 700,
                    marginBottom: "6px",
                  }}
                >
                  股票列表
                </div>
                <div
                  style={{
                    fontSize: "14px",
                    color: "rgba(255,255,255,0.7)",
                  }}
                >
                  盤中顯示準即時資料，13:30 後顯示收盤結果
                </div>
              </div>

              <div
                style={{
                  display: "flex",
                  gap: "10px",
                  flexWrap: "wrap",
                }}
              >
                <input
                  value={searchText}
                  onChange={(e) => setSearchText(e.target.value)}
                  placeholder="搜尋股票代號 / 名稱"
                  style={{
                    width: "280px",
                    maxWidth: "100%",
                    padding: "12px 14px",
                    borderRadius: "10px",
                    border: "1px solid rgba(255,255,255,0.12)",
                    background: "#0b2740",
                    color: "#fff",
                    outline: "none",
                  }}
                />

                <button
                  onClick={fetchStocks}
                  style={{
                    padding: "12px 16px",
                    borderRadius: "10px",
                    border: "none",
                    background: "#00bcd4",
                    color: "#fff",
                    cursor: "pointer",
                    fontWeight: 700,
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
                  padding: "10px 12px",
                  borderRadius: "10px",
                  background: "rgba(0,188,212,0.12)",
                  color: "#9eeaf5",
                  fontSize: "14px",
                }}
              >
                資料更新中...
              </div>
            )}

            {error && (
              <div
                style={{
                  marginTop: "14px",
                  padding: "10px 12px",
                  borderRadius: "10px",
                  background: "rgba(255,80,80,0.12)",
                  color: "#ffb3b3",
                  fontSize: "14px",
                }}
              >
                {error}
              </div>
            )}
          </div>

          {/* 推薦前10 */}
          <div
            style={{
              marginBottom: "20px",
              padding: "18px",
              borderRadius: "16px",
              background: "rgba(255,255,255,0.05)",
            }}
          >
            <div
              style={{
                display: "flex",
                justifyContent: "space-between",
                alignItems: "center",
                marginBottom: "14px",
                gap: "10px",
                flexWrap: "wrap",
              }}
            >
              <div style={{ fontSize: "20px", fontWeight: 700 }}>推薦前 10 檔</div>
              <div style={{ fontSize: "13px", color: "rgba(255,255,255,0.6)" }}>
                依推薦分數排序
              </div>
            </div>

            {top10Stocks.length === 0 ? (
              <div
                style={{
                  padding: "16px",
                  borderRadius: "12px",
                  background: "rgba(255,255,255,0.04)",
                  color: "rgba(255,255,255,0.7)",
                }}
              >
                目前沒有符合條件的股票
              </div>
            ) : (
              <div
                style={{
                  display: "grid",
                  gridTemplateColumns: "repeat(2, minmax(0, 1fr))",
                  gap: "12px",
                }}
              >
                {top10Stocks.map((stock) => {
                  const up = stock.change_percent > 0;
                  const down = stock.change_percent < 0;

                  return (
                    <div
                      key={`top-${stock.symbol}`}
                      style={{
                        background: "#0b2740",
                        borderRadius: "14px",
                        padding: "16px",
                      }}
                    >
                      <div
                        style={{
                          display: "flex",
                          justifyContent: "space-between",
                          gap: "12px",
                          marginBottom: "12px",
                        }}
                      >
                        <div>
                          <div style={{ fontSize: "18px", fontWeight: 700 }}>
                            {stock.symbol} {stock.name}
                          </div>
                          <div
                            style={{
                              marginTop: "4px",
                              fontSize: "13px",
                              color: "rgba(255,255,255,0.65)",
                            }}
                          >
                            推薦分數：{stock.score.toFixed(2)}
                          </div>
                        </div>

                        <div
                          style={{
                            alignSelf: "flex-start",
                            padding: "6px 10px",
                            borderRadius: "8px",
                            background: "rgba(0,188,212,0.15)",
                            color: "#9eeaf5",
                            fontSize: "13px",
                            fontWeight: 700,
                          }}
                        >
                          TOP
                        </div>
                      </div>

                      <div
                        style={{
                          display: "grid",
                          gridTemplateColumns: "repeat(4, minmax(0, 1fr))",
                          gap: "10px",
                        }}
                      >
                        <div
                          style={{
                            background: "rgba(255,255,255,0.05)",
                            borderRadius: "10px",
                            padding: "10px",
                          }}
                        >
                          <div style={{ fontSize: "12px", color: "rgba(255,255,255,0.6)" }}>
                            價格
                          </div>
                          <div style={{ marginTop: "4px", fontWeight: 700 }}>{stock.price}</div>
                        </div>

                        <div
                          style={{
                            background: "rgba(255,255,255,0.05)",
                            borderRadius: "10px",
                            padding: "10px",
                          }}
                        >
                          <div style={{ fontSize: "12px", color: "rgba(255,255,255,0.6)" }}>
                            漲跌幅
                          </div>
                          <div
                            style={{
                              marginTop: "4px",
                              fontWeight: 700,
                              color: up ? "#00e676" : down ? "#ff6b6b" : "#ffffff",
                            }}
                          >
                            {stock.change_percent > 0 ? "+" : ""}
                            {stock.change_percent}%
                          </div>
                        </div>

                        <div
                          style={{
                            background: "rgba(255,255,255,0.05)",
                            borderRadius: "10px",
                            padding: "10px",
                          }}
                        >
                          <div style={{ fontSize: "12px", color: "rgba(255,255,255,0.6)" }}>
                            進場
                          </div>
                          <div style={{ marginTop: "4px", fontWeight: 700 }}>
                            {stock.entry_price || "-"}
                          </div>
                        </div>

                        <div
                          style={{
                            background: "rgba(255,255,255,0.05)",
                            borderRadius: "10px",
                            padding: "10px",
                          }}
                        >
                          <div style={{ fontSize: "12px", color: "rgba(255,255,255,0.6)" }}>
                            停損
                          </div>
                          <div style={{ marginTop: "4px", fontWeight: 700 }}>
                            {stock.stop_loss || "-"}
                          </div>
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>

          {/* 表格 */}
          <div
            style={{
              borderRadius: "16px",
              background: "rgba(255,255,255,0.05)",
              overflow: "hidden",
            }}
          >
            <div
              style={{
                overflowX: "auto",
              }}
            >
              <table
                style={{
                  width: "100%",
                  borderCollapse: "collapse",
                  minWidth: "1100px",
                }}
              >
                <thead>
                  <tr
                    style={{
                      background: "#12304a",
                      textAlign: "left",
                    }}
                  >
                    {[
                      "代號",
                      "名稱",
                      "價格",
                      "漲跌",
                      "漲跌幅",
                      "成交量",
                      "推薦分數",
                      "進場價",
                      "出場價",
                      "停損價",
                    ].map((title) => (
                      <th
                        key={title}
                        style={{
                          padding: "14px 12px",
                          fontSize: "14px",
                          color: "rgba(255,255,255,0.9)",
                          whiteSpace: "nowrap",
                        }}
                      >
                        {title}
                      </th>
                    ))}
                  </tr>
                </thead>

                <tbody>
                  {filteredStocks.length === 0 ? (
                    <tr>
                      <td
                        colSpan={10}
                        style={{
                          padding: "28px 12px",
                          textAlign: "center",
                          color: "rgba(255,255,255,0.65)",
                        }}
                      >
                        沒有符合條件的資料
                      </td>
                    </tr>
                  ) : (
                    filteredStocks.map((stock) => {
                      const up = stock.change_percent > 0;
                      const down = stock.change_percent < 0;

                      return (
                        <tr
                          key={stock.symbol}
                          style={{
                            borderTop: "1px solid rgba(255,255,255,0.08)",
                          }}
                        >
                          <td style={{ padding: "12px", fontWeight: 700 }}>{stock.symbol}</td>
                          <td style={{ padding: "12px" }}>{stock.name}</td>
                          <td style={{ padding: "12px", fontWeight: 700 }}>{stock.price}</td>
                          <td
                            style={{
                              padding: "12px",
                              color: stock.change > 0 ? "#00e676" : stock.change < 0 ? "#ff6b6b" : "#ffffff",
                              fontWeight: 700,
                            }}
                          >
                            {stock.change > 0 ? "+" : ""}
                            {stock.change}
                          </td>
                          <td
                            style={{
                              padding: "12px",
                              color: up ? "#00e676" : down ? "#ff6b6b" : "#ffffff",
                              fontWeight: 700,
                            }}
                          >
                            {stock.change_percent > 0 ? "+" : ""}
                            {stock.change_percent}%
                          </td>
                          <td style={{ padding: "12px" }}>{formatNumber(stock.volume)}</td>
                          <td style={{ padding: "12px" }}>{stock.score.toFixed(2)}</td>
                          <td style={{ padding: "12px" }}>{stock.entry_price || "-"}</td>
                          <td style={{ padding: "12px" }}>{stock.target_price || "-"}</td>
                          <td style={{ padding: "12px" }}>{stock.stop_loss || "-"}</td>
                        </tr>
                      );
                    })
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </section>
      </div>
    </main>
  );
}
