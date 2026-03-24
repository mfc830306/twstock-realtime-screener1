"use client";

import { useMemo, useState } from "react";

type StockItem = {
  symbol: string;
  name?: string;
  price: number;
  change_percent?: number;
  volume?: number;
  ma5?: number;
  ma20?: number;
  signal: string;
  reason?: string;
  score?: number;
  entry_price?: number;
  stop_loss?: number;
  target_price?: number;
};

const API_URL = "https://twstock-realtime-screener1.onrender.com/scan";

export default function Home() {
  const [stocks, setStocks] = useState("");
  const [results, setResults] = useState<StockItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [activeTab, setActiveTab] = useState("全部");

  const handleScan = async () => {
    try {
      setLoading(true);
      setError("");

      const symbols = stocks.trim()
        ? stocks
            .split(",")
            .map((s) => s.trim())
            .filter(Boolean)
        : [];

      const response = await fetch(API_URL, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ symbols }),
      });

      if (!response.ok) {
        throw new Error(`API 錯誤：${response.status}`);
      }

      const data = await response.json();
      setResults(Array.isArray(data) ? data : []);
    } catch (err: any) {
      setError(err?.message || "系統發生錯誤");
      setResults([]);
    } finally {
      setLoading(false);
    }
  };

  const filteredResults = useMemo(() => {
    if (activeTab === "全部") return results;
    return results.filter((item) => item.signal === activeTab);
  }, [results, activeTab]);

  const stats = useMemo(() => {
    const total = results.length;
    const strong = results.filter((r) => r.signal === "強勢多方").length;
    const watch = results.filter((r) => r.signal === "偏多觀察").length;
    const neutral = results.filter(
      (r) => r.signal !== "強勢多方" && r.signal !== "偏多觀察"
    ).length;

    return { total, strong, watch, neutral };
  }, [results]);

  const getSignalStyle = (signal: string): React.CSSProperties => {
    if (signal === "強勢多方") {
      return {
        background: "#FEE2E2",
        color: "#B91C1C",
        border: "1px solid #FECACA",
      };
    }

    if (signal === "偏多觀察") {
      return {
        background: "#FEF3C7",
        color: "#92400E",
        border: "1px solid #FDE68A",
      };
    }

    return {
      background: "#E5E7EB",
      color: "#374151",
      border: "1px solid #D1D5DB",
    };
  };

  return (
    <main style={styles.page}>
      <div style={styles.container}>
        <section style={styles.heroCard}>
          <div style={styles.heroTop}>
            <div>
              <div style={styles.badge}>TW STOCK SCREENER</div>
              <h1 style={styles.title}>台股選股系統</h1>
              <p style={styles.subtitle}>
                可輸入指定股票代碼分析；若留空，系統會自動掃描預設股票池並回傳推薦結果。
              </p>
            </div>
          </div>

          <div style={styles.searchWrap}>
            <input
              value={stocks}
              onChange={(e) => setStocks(e.target.value)}
              placeholder="輸入股票代碼，例如：2330,2317,2454；留空可跑系統推薦"
              style={styles.input}
            />
            <button
              onClick={handleScan}
              disabled={loading}
              style={loading ? styles.buttonDisabled : styles.button}
            >
              {loading ? "掃描中..." : "開始選股"}
            </button>
          </div>

          <div style={styles.tip}>
            常用測試：2330,2317,2454,2303,2603,1301,1802
          </div>
        </section>

        <section style={styles.statsGrid}>
          <StatCard label="總結果數" value={stats.total} />
          <StatCard label="強勢多方" value={stats.strong} />
          <StatCard label="偏多觀察" value={stats.watch} />
          <StatCard label="其他/中性" value={stats.neutral} />
        </section>

        <section style={styles.panel}>
          <div style={styles.panelHeader}>
            <div>
              <h2 style={styles.panelTitle}>掃描結果</h2>
              <p style={styles.panelSubtitle}>依訊號分類檢視個股資訊</p>
            </div>

            <div style={styles.tabs}>
              {["全部", "強勢多方", "偏多觀察", "中性"].map((tab) => (
                <button
                  key={tab}
                  onClick={() => setActiveTab(tab)}
                  style={{
                    ...styles.tab,
                    ...(activeTab === tab ? styles.tabActive : {}),
                  }}
                >
                  {tab}
                </button>
              ))}
            </div>
          </div>

          {error ? <div style={styles.errorBox}>{error}</div> : null}

          {!loading && filteredResults.length === 0 ? (
            <div style={styles.emptyBox}>
              尚未產生結果，請輸入代碼後開始掃描，或直接留空讓系統推薦。
            </div>
          ) : null}

          {loading ? (
            <div style={styles.emptyBox}>資料載入中...</div>
          ) : null}

          {!loading && filteredResults.length > 0 ? (
            <div style={styles.tableOuter}>
              <table style={styles.table}>
                <thead>
                  <tr>
                    <th style={styles.th}>代碼</th>
                    <th style={styles.th}>名稱</th>
                    <th style={styles.th}>現價</th>
                    <th style={styles.th}>漲跌幅</th>
                    <th style={styles.th}>訊號</th>
                    <th style={styles.th}>進場</th>
                    <th style={styles.th}>停損</th>
                    <th style={styles.th}>出場</th>
                    <th style={styles.th}>原因</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredResults.map((s, i) => {
                    const entry =
                      s.entry_price ?? (typeof s.price === "number" ? s.price : 0);
                    const stop =
                      s.stop_loss ??
                      (typeof s.price === "number"
                        ? Number((s.price * 0.97).toFixed(2))
                        : 0);
                    const target =
                      s.target_price ??
                      (typeof s.price === "number"
                        ? Number((s.price * 1.05).toFixed(2))
                        : 0);

                    return (
                      <tr key={`${s.symbol}-${i}`}>
                        <td style={styles.td}>{s.symbol}</td>
                        <td style={styles.td}>{s.name || "-"}</td>
                        <td style={styles.td}>{s.price ?? "-"}</td>
                        <td
                          style={{
                            ...styles.td,
                            color:
                              typeof s.change_percent === "number"
                                ? s.change_percent > 0
                                  ? "#DC2626"
                                  : s.change_percent < 0
                                  ? "#2563EB"
                                  : "#111827"
                                : "#6B7280",
                            fontWeight: 700,
                          }}
                        >
                          {typeof s.change_percent === "number"
                            ? `${s.change_percent}%`
                            : "-"}
                        </td>
                        <td style={styles.td}>
                          <span style={{ ...styles.signalPill, ...getSignalStyle(s.signal) }}>
                            {s.signal}
                          </span>
                        </td>
                        <td style={styles.td}>{entry}</td>
                        <td style={{ ...styles.td, color: "#DC2626", fontWeight: 700 }}>
                          {stop}
                        </td>
                        <td style={{ ...styles.td, color: "#059669", fontWeight: 700 }}>
                          {target}
                        </td>
                        <td style={{ ...styles.td, minWidth: 220 }}>
                          {s.reason || "-"}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          ) : null}
        </section>
      </div>
    </main>
  );
}

function StatCard({ label, value }: { label: string; value: number }) {
  return (
    <div style={styles.statCard}>
      <div style={styles.statLabel}>{label}</div>
      <div style={styles.statValue}>{value}</div>
    </div>
  );
}

const styles: Record<string, React.CSSProperties> = {
  page: {
    minHeight: "100vh",
    background:
      "linear-gradient(180deg, #F3F6FB 0%, #F8FAFC 35%, #EEF2F7 100%)",
    padding: "32px 16px 60px",
    fontFamily:
      'Arial, "Noto Sans TC", "Microsoft JhengHei", sans-serif',
    color: "#111827",
  },
  container: {
    maxWidth: "1280px",
    margin: "0 auto",
  },
  heroCard: {
    background: "rgba(255,255,255,0.95)",
    border: "1px solid #E5E7EB",
    borderRadius: "28px",
    padding: "28px",
    boxShadow: "0 16px 40px rgba(15, 23, 42, 0.08)",
    marginBottom: "22px",
  },
  heroTop: {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "flex-start",
    gap: "16px",
    marginBottom: "20px",
    flexWrap: "wrap",
  },
  badge: {
    display: "inline-block",
    background: "#EEF2FF",
    color: "#4338CA",
    borderRadius: "999px",
    padding: "6px 12px",
    fontSize: "12px",
    fontWeight: 800,
    letterSpacing: "0.4px",
    marginBottom: "12px",
  },
  title: {
    fontSize: "40px",
    lineHeight: 1.15,
    margin: 0,
    fontWeight: 900,
  },
  subtitle: {
    marginTop: "12px",
    color: "#4B5563",
    fontSize: "16px",
    lineHeight: 1.8,
    maxWidth: "760px",
  },
  searchWrap: {
    display: "flex",
    gap: "12px",
    flexWrap: "wrap",
    alignItems: "center",
  },
  input: {
    flex: 1,
    minWidth: "320px",
    height: "54px",
    borderRadius: "16px",
    border: "1px solid #D1D5DB",
    padding: "0 18px",
    fontSize: "16px",
    outline: "none",
    background: "#FFFFFF",
  },
  button: {
    height: "54px",
    border: "none",
    borderRadius: "16px",
    padding: "0 22px",
    background: "linear-gradient(135deg, #111827 0%, #1F2937 100%)",
    color: "#FFFFFF",
    fontSize: "16px",
    fontWeight: 800,
    cursor: "pointer",
    boxShadow: "0 10px 24px rgba(17, 24, 39, 0.18)",
  },
  buttonDisabled: {
    height: "54px",
    border: "none",
    borderRadius: "16px",
    padding: "0 22px",
    background: "#9CA3AF",
    color: "#FFFFFF",
    fontSize: "16px",
    fontWeight: 800,
    cursor: "not-allowed",
  },
  tip: {
    marginTop: "14px",
    color: "#6B7280",
    fontSize: "13px",
  },
  statsGrid: {
    display: "grid",
    gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))",
    gap: "14px",
    marginBottom: "22px",
  },
  statCard: {
    background: "#FFFFFF",
    border: "1px solid #E5E7EB",
    borderRadius: "22px",
    padding: "22px",
    boxShadow: "0 10px 24px rgba(15, 23, 42, 0.05)",
  },
  statLabel: {
    fontSize: "14px",
    color: "#6B7280",
    marginBottom: "10px",
  },
  statValue: {
    fontSize: "32px",
    fontWeight: 900,
    color: "#111827",
  },
  panel: {
    background: "#FFFFFF",
    border: "1px solid #E5E7EB",
    borderRadius: "28px",
    padding: "24px",
    boxShadow: "0 16px 40px rgba(15, 23, 42, 0.06)",
  },
  panelHeader: {
    display: "flex",
    justifyContent: "space-between",
    gap: "16px",
    alignItems: "center",
    flexWrap: "wrap",
    marginBottom: "18px",
  },
  panelTitle: {
    margin: 0,
    fontSize: "28px",
    fontWeight: 900,
  },
  panelSubtitle: {
    margin: "6px 0 0",
    color: "#6B7280",
    fontSize: "14px",
  },
  tabs: {
    display: "flex",
    gap: "8px",
    flexWrap: "wrap",
  },
  tab: {
    border: "1px solid #D1D5DB",
    background: "#F9FAFB",
    color: "#374151",
    borderRadius: "999px",
    padding: "10px 16px",
    fontSize: "14px",
    fontWeight: 800,
    cursor: "pointer",
  },
  tabActive: {
    background: "#111827",
    color: "#FFFFFF",
    border: "1px solid #111827",
  },
  errorBox: {
    borderRadius: "16px",
    background: "#FEF2F2",
    color: "#B91C1C",
    border: "1px solid #FECACA",
    padding: "14px 16px",
    marginBottom: "14px",
    fontWeight: 700,
  },
  emptyBox: {
    borderRadius: "18px",
    border: "1px dashed #CBD5E1",
    background: "#F8FAFC",
    color: "#64748B",
    padding: "42px 16px",
    textAlign: "center",
    fontSize: "15px",
  },
  tableOuter: {
    overflowX: "auto",
    borderRadius: "20px",
    border: "1px solid #E5E7EB",
  },
  table: {
    width: "100%",
    borderCollapse: "collapse",
    minWidth: "980px",
    background: "#FFFFFF",
  },
  th: {
    textAlign: "left",
    padding: "14px 14px",
    background: "#F8FAFC",
    borderBottom: "1px solid #E5E7EB",
    fontSize: "13px",
    fontWeight: 900,
    color: "#374151",
    whiteSpace: "nowrap",
  },
  td: {
    padding: "14px 14px",
    borderBottom: "1px solid #F1F5F9",
    fontSize: "14px",
    color: "#111827",
    verticalAlign: "top",
  },
  signalPill: {
    display: "inline-block",
    padding: "6px 10px",
    borderRadius: "999px",
    fontSize: "12px",
    fontWeight: 900,
    whiteSpace: "nowrap",
  },
};
