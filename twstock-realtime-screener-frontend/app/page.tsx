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

type OverviewData = {
  top10: Stock[];
  gainers: Stock[];
  losers: Stock[];
  volumes: Stock[];
  last_update?: string;
};

const API = "https://twstock-realtime-screener1.onrender.com";

const PRICE_GROUPS = [
  { key: "all", label: "全部", min: undefined, max: undefined },
  { key: "p1", label: "10元以下", min: 0, max: 10 },
  { key: "p2", label: "10~30元", min: 10, max: 30 },
  { key: "p3", label: "30~50元", min: 30, max: 50 },
  { key: "p4", label: "50~100元", min: 50, max: 100 },
  { key: "p5", label: "100~200元", min: 100, max: 200 },
  { key: "p6", label: "200~500元", min: 200, max: 500 },
  { key: "p7", label: "500元以上", min: 500, max: undefined },
];

type RankTab = "up" | "down" | "volume";

function getTaipeiNowParts() {
  const now = new Date();
  const formatter = new Intl.DateTimeFormat("en-GB", {
    timeZone: "Asia/Taipei",
    hour12: false,
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });

  const parts = formatter.formatToParts(now);
  const get = (type: string) =>
    parts.find((p) => p.type === type)?.value || "00";

  return {
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
  const { hour } = getTaipeiNowParts();
  return hour < 9;
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

function formatNumber(value: number | undefined) {
  return Number(value || 0).toLocaleString();
}

function getPriceColor(value: number) {
  if (value > 0) return "#ff6b6b";
  if (value < 0) return "#4cd97b";
  return "#d8e1f0";
}

function getTickSize(price: number) {
  if (price < 10) return 0.01;
  if (price < 50) return 0.05;
  if (price < 100) return 0.1;
  if (price < 500) return 0.5;
  if (price < 1000) return 1;
  return 5;
}

function normalizeToTick(price: number) {
  const tick = getTickSize(price);
  return Math.round(price / tick) * tick;
}

function formatPrice(price: number | undefined) {
  const n = Number(price || 0);
  if (!n) return "--";
  return (Math.round(normalizeToTick(n) * 100) / 100).toString();
}

function getTradePlan(stock: Stock) {
  const price = Number(stock.price || 0);
  const prevClose = Number(stock.prev_close || 0);
  const open = Number(stock.open || 0);
  const high = Number(stock.high || 0);
  const low = Number(stock.low || 0);
  const cp = Number(stock.change_percent || 0);

  if (price <= 0) {
    return {
      entryMin: 0,
      entryMax: 0,
      target: 0,
      stopLoss: 0,
      signal: "觀望",
      reason: "目前無有效價格",
    };
  }

  const refBase = open > 0 ? open : prevClose > 0 ? prevClose : price;
  const intradayRange =
    high > 0 && low > 0 && high >= low ? Math.max(high - low, price * 0.02) : price * 0.02;

  let entryMin = price * 0.99;
  let entryMax = price * 1.01;
  let target = price + intradayRange * 0.8;
  let stopLoss = Math.max(price - intradayRange * 0.6, low > 0 ? low * 0.995 : price * 0.97);
  let signal = "中性";
  let reason = "以現價與日內波動估算";

  if (cp >= 3) {
    entryMin = Math.max(price * 0.985, refBase);
    entryMax = price * 1.005;
    target = price + intradayRange;
    stopLoss = Math.max(refBase * 0.99, price - intradayRange * 0.7);
    signal = "偏多";
    reason = "股價偏強，建議等小拉回分批布局";
  } else if (cp > 0) {
    entryMin = price * 0.985;
    entryMax = price * 1.005;
    target = price + intradayRange * 0.75;
    stopLoss = Math.max(price - intradayRange * 0.65, low > 0 ? low * 0.995 : price * 0.975);
    signal = "偏多";
    reason = "維持強勢，可用小區間進場";
  } else if (cp <= -3) {
    entryMin = price * 0.97;
    entryMax = price * 0.985;
    target = price + intradayRange * 0.6;
    stopLoss = price * 0.96;
    signal = "保守";
    reason = "跌幅較大，建議等待止穩再考慮";
  } else {
    entryMin = price * 0.98;
    entryMax = price * 1.0;
    target = price + intradayRange * 0.65;
    stopLoss = Math.max(price * 0.97, low > 0 ? low * 0.995 : price * 0.97);
    signal = "中性";
    reason = "震盪格局，建議靠近支撐再進";
  }

  return {
    entryMin: Math.round(normalizeToTick(entryMin) * 100) / 100,
    entryMax: Math.round(normalizeToTick(entryMax) * 100) / 100,
    target: Math.round(normalizeToTick(target) * 100) / 100,
    stopLoss: Math.round(normalizeToTick(stopLoss) * 100) / 100,
    signal,
    reason,
  };
}

export default function Home() {
  const [stocks, setStocks] = useState<Stock[]>([]);
  const [overview, setOverview] = useState<OverviewData>({
    top10: [],
    gainers: [],
    losers: [],
    volumes: [],
  });
  const [search, setSearch] = useState("");
  const [searchInput, setSearchInput] = useState("");
  const [selectedGroup, setSelectedGroup] = useState("all");
  const [loading, setLoading] = useState(true);
  const [stocksLoading, setStocksLoading] = useState(false);
  const [error, setError] = useState("");
  const [lastUpdated, setLastUpdated] = useState<string>("--");
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [marketMode, setMarketMode] = useState<"preopen" | "trading" | "closed">("trading");
  const [rankTab, setRankTab] = useState<RankTab>("up");

  const selectedPriceGroup = useMemo(
    () => PRICE_GROUPS.find((g) => g.key === selectedGroup) || PRICE_GROUPS[0],
    [selectedGroup]
  );

  const rankingList = useMemo(() => {
    if (rankTab === "up") return overview.gainers;
    if (rankTab === "down") return overview.losers;
    return overview.volumes;
  }, [overview, rankTab]);

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

    const loadOverview = async (silent = false) => {
      try {
        updateMarketMode();
        if (silent) setIsRefreshing(true);
        else setLoading(true);

        const res = await fetch(`${API}/market-overview?ts=${Date.now()}`, {
          cache: "no-store",
        });

        if (!res.ok) {
          throw new Error(`Overview API 錯誤：${res.status}`);
        }

        const data = await res.json();
        if (!mounted) return;

        setOverview({
          top10: Array.isArray(data.top10) ? data.top10 : [],
          gainers: Array.isArray(data.gainers) ? data.gainers : [],
          losers: Array.isArray(data.losers) ? data.losers : [],
          volumes: Array.isArray(data.volumes) ? data.volumes : [],
        });

        setLastUpdated(getDisplayTime());
        setError("");
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
      await loadOverview(false);

      if (!mounted) return;

      if (!isAfterCloseTime() && !isBeforeOpenTime()) {
        timer = setInterval(() => {
          if (isAfterCloseTime()) {
            if (timer) clearInterval(timer);
            setMarketMode("closed");
            setIsRefreshing(false);
            return;
          }
          loadOverview(true);
        }, 10000);
      }
    };

    init();

    return () => {
      mounted = false;
      if (timer) clearInterval(timer);
    };
  }, []);

  useEffect(() => {
    let mounted = true;

    const fetchFilteredStocks = async () => {
      try {
        setStocksLoading(true);
        setError("");

        const params = new URLSearchParams();

        if (selectedPriceGroup.min !== undefined) {
          params.set("min_price", String(selectedPriceGroup.min));
        }
        if (selectedPriceGroup.max !== undefined) {
          params.set("max_price", String(selectedPriceGroup.max));
        }
        if (search.trim()) {
          params.set("keyword", search.trim());
        }

        const url = `${API}/stocks?${params.toString()}&ts=${Date.now()}`;
        const res = await fetch(url, { cache: "no-store" });

        if (!res.ok) {
          throw new Error(`Stocks API 錯誤：${res.status}`);
        }

        const data = await res.json();
        if (!mounted) return;

        setStocks(Array.isArray(data.stocks) ? data.stocks : []);
      } catch (err: any) {
        if (!mounted) return;
        setError(err?.message || "載入失敗");
        setStocks([]);
      } finally {
        if (!mounted) return;
        setStocksLoading(false);
      }
    };

    fetchFilteredStocks();

    return () => {
      mounted = false;
    };
  }, [selectedPriceGroup, search]);

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
      : "盤中｜總覽每 10 秒更新";

  const marketModeColor =
    marketMode === "closed"
      ? "#ffd76a"
      : marketMode === "preopen"
      ? "#9fb4d6"
      : isRefreshing
      ? "#ffd76a"
      : "#4cd97b";

  const rankTitle =
    rankTab === "up" ? "📈 漲幅前 20" : rankTab === "down" ? "📉 跌幅前 20" : "📊 成交量前 20";

  return (
    <div
      style={{
        background: "linear-gradient(180deg, #07162b 0%, #0b1f3a 100%)",
        color: "white",
        minHeight: "100vh",
        padding: "24px",
      }}
    >
      <div style={{ maxWidth: 1600, margin: "0 auto" }}>
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
              先選價格區間，再搜尋股票 / 推薦TOP10 / 即時排行 / 進出場規劃
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
            <div style={{ fontSize: 12, marginTop: 4, color: marketModeColor }}>
              {marketModeText}
            </div>
          </div>
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
                  type="button"
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
                  {group.label}
                </button>
              );
            })}
          </div>
        </div>

        <div style={{ ...cardStyle, marginBottom: 20 }}>
          <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
            <input
              placeholder="先選價格區間，再搜尋股票代碼或名稱"
              value={searchInput}
              onChange={(e) => setSearchInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") setSearch(searchInput);
              }}
              style={{
                padding: "12px 14px",
                flex: 1,
                minWidth: 260,
                borderRadius: 10,
                border: "1px solid #28476f",
                background: "#0d2340",
                color: "white",
                outline: "none",
                fontSize: 15,
              }}
            />
            <button
              type="button"
              onClick={() => setSearch(searchInput)}
              style={{
                padding: "12px 18px",
                borderRadius: 10,
                background: "#2a62ff",
                color: "white",
                fontWeight: 700,
              }}
            >
              搜尋
            </button>
            <button
              type="button"
              onClick={() => {
                setSearchInput("");
                setSearch("");
              }}
              style={{
                padding: "12px 18px",
                borderRadius: 10,
                background: "#0d2340",
                color: "white",
                fontWeight: 700,
                border: "1px solid rgba(255,255,255,0.08)",
              }}
            >
              清除
            </button>
          </div>
        </div>

        <div
          style={{
            display: "grid",
            gridTemplateColumns: "320px 360px minmax(0, 1fr)",
            gap: 20,
            alignItems: "start",
          }}
        >
          <div style={cardStyle}>
            <h2 style={{ fontSize: 22, marginBottom: 14 }}>🔥 推薦 TOP10</h2>
            <div style={{ display: "grid", gap: 10 }}>
              {overview.top10.map((s, i) => {
                const cp = Number(s.change_percent) || 0;
                const plan = getTradePlan(s);

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
                    <div style={{ marginTop: 8, fontSize: 22, fontWeight: 700 }}>
                      {formatPrice(s.price)}
                    </div>
                    <div
                      style={{
                        marginTop: 4,
                        fontSize: 14,
                        color: getPriceColor(cp),
                        fontWeight: 700,
                      }}
                    >
                      {cp > 0 ? "+" : ""}
                      {cp}%
                    </div>
                    <div style={{ marginTop: 6, fontSize: 14, color: "#ffd76a" }}>
                      推薦分數：{s.score}
                    </div>
                    <div style={{ marginTop: 8, fontSize: 13, color: "#7fd0ff" }}>
                      進場：{formatPrice(plan.entryMin)} ~ {formatPrice(plan.entryMax)}
                    </div>
                    <div style={{ marginTop: 4, fontSize: 13, color: "#ffb86b" }}>
                      出場：{formatPrice(plan.target)}
                    </div>
                    <div style={{ marginTop: 4, fontSize: 13, color: "#7ee081" }}>
                      止損：{formatPrice(plan.stopLoss)}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>

          <div style={cardStyle}>
            <div style={{ display: "flex", gap: 8, marginBottom: 14, flexWrap: "wrap" }}>
              <button
                type="button"
                onClick={() => setRankTab("up")}
                style={{
                  padding: "10px 12px",
                  borderRadius: 10,
                  border: "none",
                  cursor: "pointer",
                  background: rankTab === "up" ? "#ff6b6b" : "#0d2340",
                  color: "white",
                  fontWeight: 700,
                }}
              >
                漲幅排行
              </button>
              <button
                type="button"
                onClick={() => setRankTab("down")}
                style={{
                  padding: "10px 12px",
                  borderRadius: 10,
                  border: "none",
                  cursor: "pointer",
                  background: rankTab === "down" ? "#4cd97b" : "#0d2340",
                  color: "white",
                  fontWeight: 700,
                }}
              >
                跌幅排行
              </button>
              <button
                type="button"
                onClick={() => setRankTab("volume")}
                style={{
                  padding: "10px 12px",
                  borderRadius: 10,
                  border: "none",
                  cursor: "pointer",
                  background: rankTab === "volume" ? "#2a62ff" : "#0d2340",
                  color: "white",
                  fontWeight: 700,
                }}
              >
                成交量排行
              </button>
            </div>

            <h2 style={{ fontSize: 22, marginBottom: 14 }}>{rankTitle}</h2>

            <div style={{ display: "grid", gap: 8 }}>
              {rankingList.map((s, i) => {
                const cp = Number(s.change_percent) || 0;
                return (
                  <div
                    key={`${rankTab}-${s.symbol}`}
                    style={{
                      display: "grid",
                      gridTemplateColumns: "36px 1fr auto",
                      gap: 10,
                      alignItems: "center",
                      background: "#0d2340",
                      borderRadius: 10,
                      padding: "10px 12px",
                    }}
                  >
                    <div style={{ color: "#9fb4d6", fontWeight: 700 }}>{i + 1}</div>
                    <div>
                      <div style={{ fontWeight: 700 }}>
                        {s.symbol} {s.name}
                      </div>
                      <div style={{ fontSize: 12, color: "#9fb4d6", marginTop: 2 }}>
                        價格 {formatPrice(s.price)}
                      </div>
                    </div>
                    <div
                      style={{
                        textAlign: "right",
                        fontWeight: 700,
                        color: rankTab === "volume" ? "#ffd76a" : getPriceColor(cp),
                      }}
                    >
                      {rankTab === "volume"
                        ? formatNumber(s.volume)
                        : `${cp > 0 ? "+" : ""}${cp}%`}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>

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
                區間股票 ({stocks.length})
              </h2>
              <div style={{ color: "#9fb4d6", fontSize: 14 }}>
                目前分類：{selectedPriceGroup.label}
                {search ? ` ｜ 搜尋：${search}` : ""}
              </div>
            </div>

            {loading && overview.top10.length === 0 && (
              <div style={{ padding: "30px 0", color: "#b8c7e0" }}>資料載入中...</div>
            )}

            {stocksLoading && (
              <div style={{ paddingBottom: 14, color: "#ffd76a", fontSize: 14 }}>
                區間資料載入中...
              </div>
            )}

            {error && (
              <div style={{ padding: "30px 0", color: "#ff9a9a" }}>
                載入失敗：{error}
              </div>
            )}

            {!error && !stocksLoading && stocks.length === 0 && (
              <div style={{ padding: "30px 0", color: "#b8c7e0" }}>
                找不到符合條件的股票
              </div>
            )}

            {!error && stocks.length > 0 && (
              <div
                style={{
                  display: "grid",
                  gridTemplateColumns: "repeat(auto-fill, minmax(280px, 1fr))",
                  gap: 14,
                }}
              >
                {stocks.map((s) => {
                  const cp = Number(s.change_percent) || 0;
                  const plan = getTradePlan(s);

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

                      <div style={{ fontSize: 26, fontWeight: 700, marginBottom: 8 }}>
                        {formatPrice(s.price)}
                      </div>

                      <div
                        style={{
                          color: getPriceColor(cp),
                          fontWeight: 700,
                          marginBottom: 10,
                          fontSize: 16,
                        }}
                      >
                        {cp > 0 ? "+" : ""}
                        {cp}%
                      </div>

                      <div style={{ display: "grid", gap: 4, fontSize: 13, color: "#9fb4d6" }}>
                        <div>昨收：{formatPrice(s.prev_close)}</div>
                        <div>開盤：{formatPrice(s.open)}</div>
                        <div>最高：{formatPrice(s.high)}</div>
                        <div>最低：{formatPrice(s.low)}</div>
                        <div>成交量：{formatNumber(s.volume)}</div>
                        <div>更新：{s.last_update || "--"}</div>
                      </div>

                      <div
                        style={{
                          marginTop: 12,
                          paddingTop: 10,
                          borderTop: "1px solid rgba(255,255,255,0.08)",
                          display: "grid",
                          gap: 6,
                        }}
                      >
                        <div style={{ fontSize: 13, color: "#ffd76a", fontWeight: 700 }}>
                          訊號：{plan.signal}
                        </div>
                        <div style={{ fontSize: 12, color: "#b8c7e0" }}>{plan.reason}</div>
                        <div style={{ fontSize: 13, color: "#7fd0ff" }}>
                          進場價位：{formatPrice(plan.entryMin)} ~ {formatPrice(plan.entryMax)}
                        </div>
                        <div style={{ fontSize: 13, color: "#ffb86b" }}>
                          出場價位：{formatPrice(plan.target)}
                        </div>
                        <div style={{ fontSize: 13, color: "#7ee081" }}>
                          止損價位：{formatPrice(plan.stopLoss)}
                        </div>
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
  );
}
