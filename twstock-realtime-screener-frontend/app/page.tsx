"use client";
import { useEffect, useMemo, useState } from "react";

type Stock = {
  symbol: string;
  name: string;
  price: number;
  change_percent: number;
  volume: number;
  score: number;
  prev_close?: number;
  open?: number;
  high?: number;
  low?: number;
  last_update?: string;
};

const API = "https://twstock-realtime-screener1.onrender.com";

const PRICE_GROUPS = [
  { key: "all", label: "全部", min: -Infinity, max: Infinity },
  { key: "p1", label: "10元以下", min: 0, max: 10 },
  { key: "p2", label: "10~30元", min: 10, max: 30 },
  { key: "p3", label: "30~50元", min: 30, max: 50 },
  { key: "p4", label: "50~100元", min: 50, max: 100 },
  { key: "p5", label: "100~200元", min: 100, max: 200 },
  { key: "p6", label: "200~500元", min: 200, max: 500 },
  { key: "p7", label: "500元以上", min: 500, max: Infinity },
];

function getTaipeiNowParts() {
  const now = new Date();
  const formatter = new Intl.DateTimeFormat("en-GB", {
    timeZone: "Asia/Taipei",
    hour12: false,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });

  const parts = formatter.formatToParts(now);
  const get = (type: string) =>
    parts.find((p) => p.type === type)?.value || "00";

  return {
    year: Number(get("year")),
    month: Number(get("month")),
    day: Number(get("day")),
    hour: Number(get("hour")),
    minute: Number(get("minute")),
    second: Number(get("second")),
  };
}

function isAfterCloseTime() {
  const { hour, minute } = getTaipeiNowParts();
  return hour > 13 || (hour === 13 && minute >= 30);
}

function isBeforeOpenTime() {
  const { hour, minute } = getTaipeiNowParts();
  return hour < 9 || (hour === 8 && minute < 60);
}

function getDisplayTime() {
  return new Intl.DateTimeFormat("zh-TW", {
    timeZone: "Asia/Taipei",
    hour12: false,
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  }).format(new Date());
}

export default function Home() {
  const [stocks, setStocks] = useState<Stock[]>([]);
  const [top, setTop] = useState<Stock[]>([]);
  const [search, setSearch] = useState("");
  const [selectedGroup, setSelectedGroup] = useState("all");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [lastUpdated, setLastUpdated] = useState<string>("--");
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [marketMode, setMarketMode] = useState<"preopen" | "trading" | "closed">("trading");

  useEffect(() => {
    let mounted = true;
    let timer: ReturnType<typeof setInterval> | null = null;

    const updateMarketMode = () => {
      if (isAfterCloseTime()) {
        setMarketMode("closed");
      } else if (isBeforeOpenTime()) {
        setMarketMode("preopen");
      } else {
        setMarketMode("trading");
      }
    };

    const loadStocks = async (silent = false) => {
      try {
        updateMarketMode();

        if (!silent) {
          setLoading(true);
        } else {
          setIsRefreshing(true);
        }

        const res = await fetch(`${API}/stocks?ts=${Date.now()}`, {
          cache: "no-store",
        });

        if (!res.ok) {
          throw new Error(`API 錯誤：${res.status}`);
        }

        const data = await res.json();
        const stockList: Stock[] = Array.isArray(data.stocks) ? data.stocks : [];

        if (!mounted) return;

        setStocks(stockList);

        const sortedTop = [...stockList]
          .filter((s) => Number(s.price) > 0)
          .sort((a, b) => (Number(b.score) || 0) - (Number(a.score) || 0))
          .slice(0, 10);

        setTop(sortedTop);
        setError("");
        setLastUpdated(getDisplayTime());
      } catch (err: any) {
        if (!mounted) return;
        setError(err?.message || "載入失敗");
      } finally {
        if (!mounted) return;
        setLoading(false);
        setIsRefreshing(false);
      }
    };

    const init = async () => {
      updateMarketMode();
      await loadStocks(false);

      if (!mounted) return;

      if (!isAfterCloseTime() && !isBeforeOpenTime()) {
        timer = setInterval(() => {
          if (isAfterCloseTime()) {
            if (timer) clearInterval(timer);
            setMarketMode("closed");
            setIsRefreshing(false);
            return;
          }
          loadStocks(true);
        }, 5000);
      }
    };

    init();

    return () => {
      mounted = false;
      if (timer) clearInterval(timer);
    };
  }, []);

  const groupCounts = useMemo(() => {
    const counts: Record<string, number> = {};

    for (const group of PRICE_GROUPS) {
      counts[group.key] = stocks.filter((s) => {
        const price = Number(s.price) || 0;
        if (group.key === "all") return price > 0;
        return price > group.min && price <= group.max;
      }).length;
    }

    return counts;
  }, [stocks]);

  const filtered = useMemo(() => {
    const group = PRICE_GROUPS.find((g) => g.key === selectedGroup) || PRICE_GROUPS[0];

    return stocks
      .filter((s) => {
        const price = Number(s.price) || 0;
        if (price <= 0) return false;

        const matchGroup =
          group.key === "all" ? true : price > group.min && price <= group.max;

        const keyword = search.trim();
        const matchSearch =
          keyword === "" ||
          s.name?.includes(keyword) ||
          s.symbol?.includes(keyword);

        return matchGroup && matchSearch;
      })
      .sort((a, b) => (Number(b.score) || 0) - (Number(a.score) || 0));
  }, [stocks, search, selectedGroup]);

  const cardStyle: React.CSSProperties = {
    background: "#132b4f",
    borderRadius: 14,
    padding: 14,
    boxShadow: "0 4px 14px rgba(0,0,0,0.2)",
    border: "1px solid rgba(255,255,255,0.06)",
  };

  const marketModeText =
    marketMode === "closed"
      ? "收盤後｜顯示尾盤結果"
      : marketMode === "preopen"
      ? "開盤前｜顯示前次收盤結果"
      : "盤中｜每 5 秒自動更新";

  const marketModeColor =
    marketMode === "closed"
      ? "#ffd76a"
      : marketMode === "preopen"
      ? "#9fb4d6"
      : isRefreshing
      ? "#ffd76a"
      : "#7ee081";

  return (
    <div
      style={{
        background: "linear-gradient(180deg, #07162b 0%, #0b1f3a 100%)",
        color: "white",
        minHeight: "100vh",
        padding: "24px",
      }}
    >
      <div style={{ maxWidth: 1500, margin: "0 auto" }}>
        <div
          style={{
            marginBottom: 24,
            display: "flex",
            justifyContent: "space-between",
            alignItems: "flex-end",
            gap: 12,
            flexWrap: "wrap",
          }}
        >
          <div>
            <h1 style={{ fontSize: 32, fontWeight: 700, marginBottom: 8 }}>
              台股選股系統
            </h1>
            <div style={{ color: "#b8c7e0", fontSize: 15 }}>
              全部股票 / 價格分類 / 推薦TOP10
            </div>
          </div>

          <div
            style={{
              background: "#132b4f",
              border: "1px solid rgba(255,255,255,0.06)",
              borderRadius: 12,
              padding: "10px 14px",
              minWidth: 240,
            }}
          >
            <div style={{ fontSize: 13, color: "#9fb4d6" }}>最後更新時間</div>
            <div style={{ fontSize: 18, fontWeight: 700, marginTop: 4 }}>
              {lastUpdated}
            </div>
            <div
              style={{
                fontSize: 12,
                marginTop: 4,
                color: marketModeColor,
              }}
            >
              {marketModeText}
            </div>
          </div>
        </div>

        <div style={{ ...cardStyle, marginBottom: 20 }}>
          <input
            placeholder="搜尋股票代碼或名稱，例如：2330 / 台積電"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            style={{
              padding: "12px 14px",
              width: "100%",
              borderRadius: 10,
              border: "1px solid #28476f",
              background: "#0d2340",
              color: "white",
              outline: "none",
              fontSize: 15,
            }}
          />
        </div>

        <div style={{ ...cardStyle, marginBottom: 20 }}>
          <h2 style={{ fontSize: 22, marginBottom: 14 }}>💰 價格分類</h2>
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(auto-fit, minmax(140px, 1fr))",
              gap: 10,
            }}
          >
            {PRICE_GROUPS.map((group) => {
              const active = selectedGroup === group.key;
              return (
                <button
                  key={group.key}
                  onClick={() => setSelectedGroup(group.key)}
                  style={{
                    background: active ? "#2a62ff" : "#0d2340",
                    color: "white",
                    border: active
                      ? "1px solid #4d7bff"
                      : "1px solid rgba(255,255,255,0.06)",
                    borderRadius: 10,
                    padding: "12px 14px",
                    cursor: "pointer",
                    textAlign: "left",
                    fontSize: 15,
                    fontWeight: active ? 700 : 500,
                  }}
                >
                  {group.label} ({groupCounts[group.key] || 0})
                </button>
              );
            })}
          </div>
        </div>

        <div style={{ display: "flex", gap: 20, alignItems: "flex-start" }}>
          <div style={{ width: "320px", flexShrink: 0 }}>
            <div style={{ ...cardStyle, marginBottom: 20 }}>
              <h2 style={{ fontSize: 22, marginBottom: 14 }}>🔥 推薦 TOP10</h2>
              <div style={{ display: "grid", gap: 10 }}>
                {top.map((s, i) => {
                  const up = Number(s.change_percent) >= 0;
                  return (
                    <div
                      key={`${s.symbol}-${i}`}
                      style={{
                        background: "#0d2340",
                        padding: 12,
                        borderRadius: 12,
                        border: "1px solid rgba(255,255,255,0.05)",
                      }}
                    >
                      <div style={{ fontSize: 13, color: "#9fb4d6", marginBottom: 6 }}>
                        #{i + 1}
                      </div>
                      <div style={{ fontSize: 16, fontWeight: 700 }}>
                        {s.symbol} {s.name}
                      </div>
                      <div style={{ marginTop: 6, fontSize: 14 }}>價格：{s.price}</div>
                      <div
                        style={{
                          marginTop: 4,
                          fontSize: 14,
                          color: up ? "#ff8080" : "#7ee081",
                        }}
                      >
                        漲跌幅：{s.change_percent}%
                      </div>
                      <div style={{ marginTop: 4, fontSize: 14, color: "#ffd76a" }}>
                        推薦分數：{s.score}
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          </div>

          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={cardStyle}>
              <div
                style={{
                  display: "flex",
                  justifyContent: "space-between",
                  alignItems: "center",
                  marginBottom: 18,
                  flexWrap: "wrap",
                  gap: 12,
                }}
              >
                <h2 style={{ fontSize: 24, margin: 0 }}>
                  全部股票 ({filtered.length})
                </h2>
                <div style={{ color: "#9fb4d6", fontSize: 14 }}>
                  目前分類：
                  {PRICE_GROUPS.find((g) => g.key === selectedGroup)?.label || "全部"}
                </div>
              </div>

              {loading && (
                <div style={{ padding: "30px 0", color: "#b8c7e0" }}>資料載入中...</div>
              )}

              {!loading && error && (
                <div style={{ padding: "30px 0", color: "#ff9a9a" }}>
                  載入失敗：{error}
                </div>
              )}

              {!loading && !error && filtered.length === 0 && (
                <div style={{ padding: "30px 0", color: "#b8c7e0" }}>
                  找不到符合條件的股票
                </div>
              )}

              {!loading && !error && filtered.length > 0 && (
                <div
                  style={{
                    display: "grid",
                    gridTemplateColumns: "repeat(auto-fill, minmax(220px, 1fr))",
                    gap: 14,
                  }}
                >
                  {filtered.map((s) => {
                    const up = Number(s.change_percent) >= 0;

                    return (
                      <div
                        key={s.symbol}
                        style={{
                          background: "#0d2340",
                          borderRadius: 14,
                          padding: 14,
                          border: "1px solid rgba(255,255,255,0.05)",
                        }}
                      >
                        <div
                          style={{
                            display: "flex",
                            justifyContent: "space-between",
                            alignItems: "center",
                            marginBottom: 10,
                          }}
                        >
                          <div style={{ fontSize: 18, fontWeight: 700 }}>{s.symbol}</div>
                          <div
                            style={{
                              fontSize: 13,
                              padding: "4px 8px",
                              borderRadius: 999,
                              background: "rgba(255,255,255,0.08)",
                              color: "#ffd76a",
                            }}
                          >
                            分數 {s.score}
                          </div>
                        </div>

                        <div style={{ fontSize: 16, marginBottom: 10 }}>{s.name}</div>

                        <div style={{ fontSize: 24, fontWeight: 700, marginBottom: 8 }}>
                          {s.price}
                        </div>

                        <div
                          style={{
                            color: up ? "#ff8080" : "#7ee081",
                            fontWeight: 600,
                            marginBottom: 8,
                          }}
                        >
                          {up ? "+" : ""}
                          {s.change_percent}%
                        </div>

                        <div style={{ fontSize: 13, color: "#9fb4d6" }}>
                          成交量：{Number(s.volume || 0).toLocaleString()}
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
