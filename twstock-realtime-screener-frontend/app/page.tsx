"use client";

import { useEffect, useMemo, useState } from "react";

type Stock = {
  market: string;
  symbol: string;
  name: string;
  price: number;
  change: number;
  change_percent: number;
  volume: number;
  score: number;
};

type ApiResponse = {
  success?: boolean;
  total?: number;
  stocks?: Stock[];
  recommend?: Stock[];
  update_time?: string;
  error?: string;
};

const BACKEND_URL = "https://twstock-realtime-screener1.onrender.com/stocks";

const PRICE_CATEGORIES = [
  { key: "all", label: "全部" },
  { key: "0-10", label: "0-10" },
  { key: "10-50", label: "10-50" },
  { key: "50-100", label: "50-100" },
  { key: "100-200", label: "100-200" },
  { key: "200-500", label: "200-500" },
  { key: "500-1000", label: "500-1000" },
  { key: "1000+", label: "1000+" },
];

export default function Page() {
  const [stocks, setStocks] = useState<Stock[]>([]);
  const [recommend, setRecommend] = useState<Stock[]>([]);
  const [searchTerm, setSearchTerm] = useState("");
  const [selectedCategory, setSelectedCategory] = useState("all");
  const [loading, setLoading] = useState(true);
  const [errorMsg, setErrorMsg] = useState("");
  const [updateTime, setUpdateTime] = useState("");

  useEffect(() => {
    let active = true;

    const fetchStocks = async () => {
      try {
        setLoading(true);
        setErrorMsg("");

        const res = await fetch(BACKEND_URL, {
          cache: "no-store",
        });

        const data: ApiResponse = await res.json();

        if (!active) return;

        if (!data.success) {
          setErrorMsg(data.error || "後端資料讀取失敗");
          setStocks([]);
          setRecommend([]);
          return;
        }

        const stockList = Array.isArray(data.stocks) ? data.stocks : [];
        const recommendList = Array.isArray(data.recommend) ? data.recommend : [];

        const onlyListedAndOTC = stockList.filter(
          (s) => s.market === "上市" || s.market === "上櫃"
        );

        const onlyListedAndOTCRecommend = recommendList.filter(
          (s) => s.market === "上市" || s.market === "上櫃"
        );

        setStocks(onlyListedAndOTC);
        setRecommend(onlyListedAndOTCRecommend);
        setUpdateTime(data.update_time || "");
      } catch (err) {
        if (!active) return;
        setErrorMsg("無法連線後端，請確認 Render 是否正常啟動");
        setStocks([]);
        setRecommend([]);
      } finally {
        if (active) setLoading(false);
      }
    };

    fetchStocks();

    const timer = setInterval(fetchStocks, 20000);
    return () => {
      active = false;
      clearInterval(timer);
    };
  }, []);

  const filteredStocks = useMemo(() => {
    let result = [...stocks];

    if (selectedCategory !== "all") {
      if (selectedCategory === "1000+") {
        result = result.filter((s) => s.price >= 1000);
      } else {
        const [min, max] = selectedCategory.split("-").map(Number);
        result = result.filter((s) => s.price >= min && s.price < max);
      }
    }

    if (searchTerm.trim()) {
      const keyword = searchTerm.trim().toLowerCase();
      result = result.filter(
        (s) =>
          s.symbol.toLowerCase().includes(keyword) ||
          s.name.toLowerCase().includes(keyword)
      );
    }

    result.sort((a, b) => b.change_percent - a.change_percent);

    return result;
  }, [stocks, selectedCategory, searchTerm]);

  const categoryCounts = useMemo(() => {
    const counts: Record<string, number> = {};

    for (const cat of PRICE_CATEGORIES) {
      if (cat.key === "all") {
        counts[cat.key] = stocks.length;
      } else if (cat.key === "1000+") {
        counts[cat.key] = stocks.filter((s) => s.price >= 1000).length;
      } else {
        const [min, max] = cat.key.split("-").map(Number);
        counts[cat.key] = stocks.filter((s) => s.price >= min && s.price < max).length;
      }
    }

    return counts;
  }, [stocks]);

  const top10 = useMemo(() => {
    if (recommend.length > 0) return recommend.slice(0, 10);
    return [...stocks].sort((a, b) => b.score - a.score).slice(0, 10);
  }, [recommend, stocks]);

  const getChangeColor = (value: number) => {
    if (value > 0) return "#ff6b6b";
    if (value < 0) return "#4da3ff";
    return "#d6e4ff";
  };

  const getChangePrefix = (value: number) => {
    if (value > 0) return "+";
    return "";
  };

  return (
    <main style={styles.page}>
      <div style={styles.container}>
        <section style={styles.headerCard}>
          <div style={styles.headerTopRow}>
            <div>
              <h1 style={styles.title}>台股即時選股系統</h1>
              <p style={styles.subtitle}>上市 / 上櫃 即時篩選、價格分類、推薦排序</p>
            </div>

            <div style={styles.statusWrap}>
              <div style={styles.statusItem}>
                <span style={styles.statusLabel}>更新時間</span>
                <span style={styles.statusValue}>
                  {updateTime || (loading ? "讀取中..." : "--")}
                </span>
              </div>
            </div>
          </div>

          <div style={styles.searchRow}>
            <input
              type="text"
              placeholder="搜尋股票代號 / 名稱"
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              style={styles.searchInput}
            />
          </div>
        </section>

        {errorMsg ? (
          <div style={styles.errorBox}>{errorMsg}</div>
        ) : null}

        <section style={styles.topGrid}>
          <div style={styles.card}>
            <div style={styles.cardHeader}>
              <h2 style={styles.cardTitle}>股價分類</h2>
              <span style={styles.cardHint}>共 {filteredStocks.length} 檔</span>
            </div>

            <div style={styles.categoryGrid}>
              {PRICE_CATEGORIES.map((cat) => {
                const active = selectedCategory === cat.key;
                return (
                  <button
                    key={cat.key}
                    onClick={() => setSelectedCategory(cat.key)}
                    style={{
                      ...styles.categoryButton,
                      ...(active ? styles.categoryButtonActive : {}),
                    }}
                  >
                    <span>{cat.label}</span>
                    <span style={styles.categoryCount}>({categoryCounts[cat.key] || 0})</span>
                  </button>
                );
              })}
            </div>
          </div>

          <div style={styles.card}>
            <div style={styles.cardHeader}>
              <h2 style={styles.cardTitle}>推薦 10 檔</h2>
              <span style={styles.cardHint}>依分數排序</span>
            </div>

            <div style={styles.recommendList}>
              {top10.map((s, index) => (
                <div key={`${s.symbol}-${index}`} style={styles.recommendItem}>
                  <div style={styles.recommendLeft}>
                    <div style={styles.rankBadge}>{index + 1}</div>
                    <div>
                      <div style={styles.stockMainRow}>
                        <span style={styles.stockSymbol}>{s.symbol}</span>
                        <span style={styles.stockName}>{s.name}</span>
                      </div>
                      <div style={styles.stockSubRow}>
                        <span style={styles.marketTag}>{s.market}</span>
                        <span>成交量 {formatVolume(s.volume)}</span>
                      </div>
                    </div>
                  </div>

                  <div style={styles.recommendRight}>
                    <div style={styles.priceText}>{formatPrice(s.price)}</div>
                    <div
                      style={{
                        ...styles.changeText,
                        color: getChangeColor(s.change_percent),
                      }}
                    >
                      {getChangePrefix(s.change)}
                      {formatPrice(s.change)} / {getChangePrefix(s.change_percent)}
                      {s.change_percent.toFixed(2)}%
                    </div>
                  </div>
                </div>
              ))}

              {!loading && top10.length === 0 ? (
                <div style={styles.emptyText}>目前沒有推薦資料</div>
              ) : null}
            </div>
          </div>
        </section>

        <section style={styles.card}>
          <div style={styles.cardHeader}>
            <h2 style={styles.cardTitle}>股票列表</h2>
            <span style={styles.cardHint}>
              {loading ? "資料載入中..." : `共 ${filteredStocks.length} 檔`}
            </span>
          </div>

          <div style={styles.tableWrap}>
            <table style={styles.table}>
              <thead>
                <tr>
                  <th style={styles.th}>市場</th>
                  <th style={styles.th}>代號</th>
                  <th style={styles.thLeft}>名稱</th>
                  <th style={styles.th}>股價</th>
                  <th style={styles.th}>漲跌</th>
                  <th style={styles.th}>漲跌幅</th>
                  <th style={styles.th}>成交量</th>
                  <th style={styles.th}>分數</th>
                </tr>
              </thead>
              <tbody>
                {filteredStocks.map((s) => (
                  <tr key={`${s.market}-${s.symbol}`} style={styles.tr}>
                    <td style={styles.td}>
                      <span style={styles.marketTag}>{s.market}</span>
                    </td>
                    <td style={styles.tdStrong}>{s.symbol}</td>
                    <td style={styles.tdLeft}>{s.name}</td>
                    <td style={styles.td}>{formatPrice(s.price)}</td>
                    <td
                      style={{
                        ...styles.td,
                        color: getChangeColor(s.change),
                      }}
                    >
                      {getChangePrefix(s.change)}
                      {formatPrice(s.change)}
                    </td>
                    <td
                      style={{
                        ...styles.td,
                        color: getChangeColor(s.change_percent),
                      }}
                    >
                      {getChangePrefix(s.change_percent)}
                      {s.change_percent.toFixed(2)}%
                    </td>
                    <td style={styles.td}>{formatVolume(s.volume)}</td>
                    <td style={styles.td}>{s.score?.toFixed(2) ?? "--"}</td>
                  </tr>
                ))}

                {!loading && filteredStocks.length === 0 ? (
                  <tr>
                    <td colSpan={8} style={styles.emptyTd}>
                      查無符合條件的股票
                    </td>
                  </tr>
                ) : null}
              </tbody>
            </table>
          </div>
        </section>
      </div>
    </main>
  );
}

function formatPrice(value: number) {
  if (!Number.isFinite(value)) return "--";
  return value % 1 === 0 ? String(value) : value.toFixed(2);
}

function formatVolume(value: number) {
  if (!Number.isFinite(value)) return "--";
  return value.toLocaleString("zh-TW");
}

const styles: Record<string, React.CSSProperties> = {
  page: {
    minHeight: "100vh",
    background: "#08264d",
    color: "#ffffff",
    padding: "20px",
  },
  container: {
    width: "100%",
    maxWidth: "1440px",
    margin: "0 auto",
  },
  headerCard: {
    background: "rgba(255,255,255,0.06)",
    border: "1px solid rgba(255,255,255,0.12)",
    borderRadius: "16px",
    padding: "20px",
    marginBottom: "18px",
    boxShadow: "0 8px 24px rgba(0,0,0,0.15)",
  },
  headerTopRow: {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "flex-start",
    gap: "16px",
    flexWrap: "wrap",
  },
  title: {
    margin: 0,
    fontSize: "32px",
    fontWeight: 700,
    lineHeight: 1.2,
  },
  subtitle: {
    margin: "8px 0 0 0",
    color: "rgba(255,255,255,0.78)",
    fontSize: "14px",
  },
  statusWrap: {
    display: "flex",
    gap: "12px",
    flexWrap: "wrap",
  },
  statusItem: {
    minWidth: "220px",
    background: "rgba(255,255,255,0.06)",
    border: "1px solid rgba(255,255,255,0.1)",
    borderRadius: "12px",
    padding: "10px 14px",
    display: "flex",
    flexDirection: "column",
    gap: "4px",
  },
  statusLabel: {
    fontSize: "12px",
    color: "rgba(255,255,255,0.7)",
  },
  statusValue: {
    fontSize: "14px",
    fontWeight: 700,
  },
  searchRow: {
    marginTop: "18px",
  },
  searchInput: {
    width: "100%",
    height: "46px",
    borderRadius: "12px",
    border: "1px solid rgba(255,255,255,0.16)",
    outline: "none",
    background: "rgba(255,255,255,0.08)",
    color: "#ffffff",
    padding: "0 14px",
    fontSize: "15px",
  },
  errorBox: {
    background: "rgba(255, 77, 79, 0.16)",
    color: "#ffd6d6",
    border: "1px solid rgba(255, 99, 99, 0.35)",
    borderRadius: "12px",
    padding: "14px 16px",
    marginBottom: "18px",
  },
  topGrid: {
    display: "grid",
    gridTemplateColumns: "1fr 1fr",
    gap: "18px",
    marginBottom: "18px",
  },
  card: {
    background: "rgba(255,255,255,0.06)",
    border: "1px solid rgba(255,255,255,0.12)",
    borderRadius: "16px",
    padding: "18px",
    boxShadow: "0 8px 24px rgba(0,0,0,0.15)",
    marginBottom: "18px",
  },
  cardHeader: {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
    gap: "12px",
    marginBottom: "14px",
    flexWrap: "wrap",
  },
  cardTitle: {
    margin: 0,
    fontSize: "22px",
    fontWeight: 700,
  },
  cardHint: {
    fontSize: "13px",
    color: "rgba(255,255,255,0.72)",
  },
  categoryGrid: {
    display: "grid",
    gridTemplateColumns: "repeat(3, minmax(0, 1fr))",
    gap: "10px",
  },
  categoryButton: {
    height: "48px",
    borderRadius: "12px",
    border: "1px solid rgba(255,255,255,0.14)",
    background: "rgba(255,255,255,0.05)",
    color: "#ffffff",
    cursor: "pointer",
    fontSize: "15px",
    fontWeight: 700,
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    gap: "6px",
  },
  categoryButtonActive: {
    background: "linear-gradient(135deg, #1f7ae0, #2bb3ff)",
    border: "1px solid rgba(255,255,255,0.25)",
    color: "#ffffff",
  },
  categoryCount: {
    fontSize: "13px",
    opacity: 0.9,
  },
  recommendList: {
    display: "flex",
    flexDirection: "column",
    gap: "10px",
  },
  recommendItem: {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
    gap: "12px",
    padding: "12px 14px",
    borderRadius: "12px",
    background: "rgba(255,255,255,0.05)",
    border: "1px solid rgba(255,255,255,0.08)",
  },
  recommendLeft: {
    display: "flex",
    alignItems: "center",
    gap: "12px",
    minWidth: 0,
  },
  recommendRight: {
    textAlign: "right",
    flexShrink: 0,
  },
  rankBadge: {
    width: "30px",
    height: "30px",
    minWidth: "30px",
    borderRadius: "50%",
    background: "linear-gradient(135deg, #f8d568, #f2a93b)",
    color: "#08264d",
    fontWeight: 800,
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    fontSize: "14px",
  },
  stockMainRow: {
    display: "flex",
    alignItems: "center",
    gap: "8px",
    flexWrap: "wrap",
  },
  stockSubRow: {
    display: "flex",
    alignItems: "center",
    gap: "10px",
    marginTop: "4px",
    fontSize: "12px",
    color: "rgba(255,255,255,0.72)",
    flexWrap: "wrap",
  },
  stockSymbol: {
    fontSize: "16px",
    fontWeight: 800,
  },
  stockName: {
    fontSize: "15px",
    color: "#ffffff",
  },
  marketTag: {
    display: "inline-flex",
    alignItems: "center",
    justifyContent: "center",
    height: "22px",
    padding: "0 8px",
    borderRadius: "999px",
    background: "rgba(98, 177, 255, 0.18)",
    border: "1px solid rgba(98, 177, 255, 0.28)",
    color: "#9bd2ff",
    fontSize: "12px",
    fontWeight: 700,
  },
  priceText: {
    fontSize: "18px",
    fontWeight: 800,
  },
  changeText: {
    marginTop: "4px",
    fontSize: "14px",
    fontWeight: 700,
  },
  tableWrap: {
    width: "100%",
    overflowX: "auto",
    borderRadius: "12px",
  },
  table: {
    width: "100%",
    minWidth: "900px",
    borderCollapse: "collapse",
    overflow: "hidden",
  },
  th: {
    textAlign: "center",
    padding: "12px 10px",
    fontSize: "13px",
    color: "rgba(255,255,255,0.78)",
    borderBottom: "1px solid rgba(255,255,255,0.12)",
    whiteSpace: "nowrap",
  },
  thLeft: {
    textAlign: "left",
    padding: "12px 10px",
    fontSize: "13px",
    color: "rgba(255,255,255,0.78)",
    borderBottom: "1px solid rgba(255,255,255,0.12)",
    whiteSpace: "nowrap",
  },
  tr: {
    borderBottom: "1px solid rgba(255,255,255,0.08)",
  },
  td: {
    textAlign: "center",
    padding: "12px 10px",
    fontSize: "14px",
    whiteSpace: "nowrap",
  },
  tdStrong: {
    textAlign: "center",
    padding: "12px 10px",
    fontSize: "14px",
    fontWeight: 800,
    whiteSpace: "nowrap",
  },
  tdLeft: {
    textAlign: "left",
    padding: "12px 10px",
    fontSize: "14px",
    whiteSpace: "nowrap",
  },
  emptyTd: {
    textAlign: "center",
    padding: "28px 12px",
    color: "rgba(255,255,255,0.7)",
  },
  emptyText: {
    textAlign: "center",
    padding: "14px 0",
    color: "rgba(255,255,255,0.7)",
  },
};
