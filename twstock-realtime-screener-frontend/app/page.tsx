"use client";

import { useEffect, useMemo, useState } from "react";

type StockResult = {
  symbol: string;
  name: string;
  price: number;
  change_percent: number;
  volume: number;
  ma5: number;
  ma20: number;
  score: number;
  trend: string;
  entry_range: string;
  take_profit: number;
  stop_loss: number;
  reason: string;
};

const API_BASE = "https://twstock-realtime-screener1.onrender.com";

export default function Home() {
  const [stockInput, setStockInput] = useState("2330,2317,2454");
  const [results, setResults] = useState<StockResult[]>([]);
  const [loading, setLoading] = useState(false);
  const [loadingAll, setLoadingAll] = useState(false);
  const [error, setError] = useState("");
  const [tab, setTab] = useState<"全部" | "強勢" | "中性" | "弱勢">("全部");
  const [marketCount, setMarketCount] = useState(0);
  const [returnedCount, setReturnedCount] = useState(0);

  const parseStocks = () => {
    return stockInput
      .split(/[\s,，]+/)
      .map((s) => s.trim())
      .filter(Boolean);
  };

  const top10 = useMemo(() => {
    return [...results].sort((a, b) => b.score - a.score).slice(0, 10);
  }, [results]);

  const filteredResults = useMemo(() => {
    if (tab === "全部") return results;
    if (tab === "強勢") return results.filter((x) => x.trend.includes("強勢"));
    if (tab === "弱勢") return results.filter((x) => x.trend.includes("弱勢"));
    return results.filter(
      (x) =>
        x.trend.includes("中性") &&
        !x.trend.includes("強勢") &&
        !x.trend.includes("弱勢")
    );
  }, [results, tab]);

  const fetchScan = async () => {
    try {
      setLoading(true);
      setError("");
      setMarketCount(0);
      setReturnedCount(0);

      const stocks = parseStocks();
      if (!stocks.length) {
        setError("請輸入股票代號");
        setResults([]);
        return;
      }

      const res = await fetch(`${API_BASE}/scan`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ stocks }),
      });

      if (!res.ok) {
        throw new Error("掃描失敗");
      }

      const data = await res.json();
      setResults(Array.isArray(data) ? data : []);
      setTab("全部");
    } catch {
      setError("讀取資料失敗，請稍後再試");
      setResults([]);
    } finally {
      setLoading(false);
    }
  };

  const fetchScanAll = async () => {
    try {
      setLoadingAll(true);
      setError("");

      const res = await fetch(`${API_BASE}/scan_all?limit=2000`);
      if (!res.ok) {
        throw new Error("全台股掃描失敗");
      }

      const data = await res.json();
      setResults(Array.isArray(data?.results) ? data.results : []);
      setMarketCount(Number(data?.total_symbols || 0));
      setReturnedCount(Number(data?.returned_count || 0));
      setTab("全部");
    } catch {
      setError("全台股掃描失敗，請稍後再試");
      setResults([]);
      setMarketCount(0);
      setReturnedCount(0);
    } finally {
      setLoadingAll(false);
    }
  };

  useEffect(() => {
    fetchScan();
  }, []);

  const strongCount = results.filter((x) => x.trend.includes("強勢")).length;
  const weakCount = results.filter((x) => x.trend.includes("弱勢")).length;
  const neutralCount = results.filter(
    (x) =>
      x.trend.includes("中性") &&
      !x.trend.includes("強勢") &&
      !x.trend.includes("弱勢")
  ).length;

  return (
    <main className="page">
      <div className="container">
        <section className="hero">
          <div className="badge">台股智慧選股系統</div>
          <h1 className="title">TW Stock Realtime Screener</h1>
          <p className="subtitle">
            顯示推薦分數、進場區間、停損與出場價，快速找出較強勢個股。
          </p>

          <div className="searchRow">
            <input
              value={stockInput}
              onChange={(e) => setStockInput(e.target.value)}
              placeholder="例如：2330, 2317, 2454"
              className="input"
            />
            <button onClick={fetchScan} disabled={loading} className="btn btnBlue">
              {loading ? "掃描中..." : "掃描指定股票"}
            </button>
            <button onClick={fetchScanAll} disabled={loadingAll} className="btn btnDark">
              {loadingAll ? "掃描中..." : "顯示全部台股"}
            </button>
          </div>

          {marketCount > 0 ? (
            <div className="marketInfo">
              全市場股票總數：{marketCount} 檔　｜　目前成功載入：{returnedCount} 檔
            </div>
          ) : null}

          {error ? <div className="errorBox">{error}</div> : null}
        </section>

        <section className="summaryGrid">
          <SummaryCard title="掃描結果" value={`${results.length} 檔`} />
          <SummaryCard title="強勢股" value={`${strongCount} 檔`} />
          <SummaryCard title="中性股" value={`${neutralCount} 檔`} />
          <SummaryCard title="弱勢股" value={`${weakCount} 檔`} />
        </section>

        <section className="mainGrid">
          <div className="panel">
            <div className="panelHeader">
              <h2>推薦 Top 10</h2>
              <span>依分數排序</span>
            </div>

            <div className="topList">
              {top10.length === 0 ? (
                <div className="emptyBox">目前沒有資料</div>
              ) : (
                top10.map((stock, index) => (
                  <div className="topCard" key={`${stock.symbol}-${index}`}>
                    <div className="topCardHeader">
                      <div>
                        <div className="topName">
                          {index + 1}. {stock.name}
                        </div>
                        <div className="topSymbol">{stock.symbol}</div>
                      </div>
                      <div className="scoreBig">{stock.score}</div>
                    </div>
                    <div className="topCardFooter">
                      <span className={`trendBadge ${getTrendClass(stock.trend)}`}>
                        {stock.trend}
                      </span>
                      <span className="muted">現價 {stock.price}</span>
                    </div>
                  </div>
                ))
              )}
            </div>
          </div>

          <div className="panel panelWide">
            <div className="panelHeader panelHeaderWrap">
              <h2>選股結果</h2>
              <div className="tabs">
                {(["全部", "強勢", "中性", "弱勢"] as const).map((item) => (
                  <button
                    key={item}
                    onClick={() => setTab(item)}
                    className={`tabBtn ${tab === item ? "tabBtnActive" : ""}`}
                  >
                    {item}
                  </button>
                ))}
              </div>
            </div>

            {filteredResults.length === 0 ? (
              <div className="emptyBox">沒有符合條件的資料</div>
            ) : (
              <div className="cardGrid">
                {filteredResults.map((stock) => (
                  <div className="stockCard" key={stock.symbol}>
                    <div className="stockHeader">
                      <div>
                        <div className="stockName">{stock.name}</div>
                        <div className="stockSymbol">{stock.symbol}</div>
                      </div>
                      <span className={`trendBadge ${getTrendClass(stock.trend)}`}>
                        {stock.trend}
                      </span>
                    </div>

                    <div className="metricGrid">
                      <MetricBox label="現價" value={`${stock.price}`} />
                      <MetricBox label="推薦分數" value={`${stock.score}`} />
                      <MetricBox label="漲跌幅" value={`${stock.change_percent}%`} />
                      <MetricBox label="成交量" value={formatNumber(stock.volume)} />
                    </div>

                    <div className="strategyList">
                      <StrategyRow label="進場區間" value={stock.entry_range} />
                      <StrategyRow label="出場價" value={`${stock.take_profit}`} />
                      <StrategyRow label="停損價" value={`${stock.stop_loss}`} />
                      <StrategyRow label="MA5 / MA20" value={`${stock.ma5} / ${stock.ma20}`} />
                    </div>

                    <div className="reasonBox">
                      <div className="reasonTitle">判斷原因</div>
                      <div className="reasonText">{stock.reason}</div>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </section>
      </div>
    </main>
  );
}

function SummaryCard({ title, value }: { title: string; value: string }) {
  return (
    <div className="summaryCard">
      <div className="summaryTitle">{title}</div>
      <div className="summaryValue">{value}</div>
    </div>
  );
}

function MetricBox({ label, value }: { label: string; value: string }) {
  return (
    <div className="metricBox">
      <div className="metricLabel">{label}</div>
      <div className="metricValue">{value}</div>
    </div>
  );
}

function StrategyRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="strategyRow">
      <span className="strategyLabel">{label}</span>
      <span className="strategyValue">{value}</span>
    </div>
  );
}

function getTrendClass(trend: string) {
  if (trend.includes("強勢")) return "trendStrong";
  if (trend.includes("弱勢")) return "trendWeak";
  return "trendNeutral";
}

function formatNumber(value: number) {
  return new Intl.NumberFormat("zh-TW").format(value);
}
