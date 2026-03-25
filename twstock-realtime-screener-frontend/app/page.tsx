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

type PriceTab =
  | "全部"
  | "10元以下"
  | "10-30元"
  | "30-50元"
  | "50-100元"
  | "100-300元"
  | "300-500元"
  | "500元以上";

const API_BASE = "https://twstock-realtime-screener1.onrender.com";

export default function Home() {
  const [stockInput, setStockInput] = useState("2330,2317,2454");
  const [results, setResults] = useState<StockResult[]>([]);
  const [loading, setLoading] = useState(false);
  const [loadingAll, setLoadingAll] = useState(false);
  const [error, setError] = useState("");
  const [trendTab, setTrendTab] = useState<"全部" | "強勢" | "中性" | "弱勢">("全部");
  const [priceTab, setPriceTab] = useState<PriceTab>("全部");
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

  const filterByTrend = (data: StockResult[]) => {
    if (trendTab === "全部") return data;
    if (trendTab === "強勢") return data.filter((x) => x.trend.includes("強勢"));
    if (trendTab === "弱勢") return data.filter((x) => x.trend.includes("弱勢"));
    return data.filter(
      (x) =>
        x.trend.includes("中性") &&
        !x.trend.includes("強勢") &&
        !x.trend.includes("弱勢")
    );
  };

  const filterByPrice = (data: StockResult[]) => {
    switch (priceTab) {
      case "10元以下":
        return data.filter((x) => x.price < 10);
      case "10-30元":
        return data.filter((x) => x.price >= 10 && x.price < 30);
      case "30-50元":
        return data.filter((x) => x.price >= 30 && x.price < 50);
      case "50-100元":
        return data.filter((x) => x.price >= 50 && x.price < 100);
      case "100-300元":
        return data.filter((x) => x.price >= 100 && x.price < 300);
      case "300-500元":
        return data.filter((x) => x.price >= 300 && x.price < 500);
      case "500元以上":
        return data.filter((x) => x.price >= 500);
      default:
        return data;
    }
  };

  const filteredResults = useMemo(() => {
    const byTrend = filterByTrend(results);
    const byPrice = filterByPrice(byTrend);
    return byPrice.sort((a, b) => b.score - a.score);
  }, [results, trendTab, priceTab]);

  const priceCounts = useMemo(() => {
    return {
      全部: results.length,
      "10元以下": results.filter((x) => x.price < 10).length,
      "10-30元": results.filter((x) => x.price >= 10 && x.price < 30).length,
      "30-50元": results.filter((x) => x.price >= 30 && x.price < 50).length,
      "50-100元": results.filter((x) => x.price >= 50 && x.price < 100).length,
      "100-300元": results.filter((x) => x.price >= 100 && x.price < 300).length,
      "300-500元": results.filter((x) => x.price >= 300 && x.price < 500).length,
      "500元以上": results.filter((x) => x.price >= 500).length,
    };
  }, [results]);

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
      setTrendTab("全部");
      setPriceTab("全部");
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
      setTrendTab("全部");
      setPriceTab("全部");
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

  const priceTabs: PriceTab[] = [
    "全部",
    "10元以下",
    "10-30元",
    "30-50元",
    "50-100元",
    "100-300元",
    "300-500元",
    "500元以上",
  ];

  return (
    <main className="page">
      <div className="container">
        <section className="hero">
          <div className="badge">台股智慧選股系統</div>
          <h1 className="title">TW Stock Realtime Screener</h1>
          <p className="subtitle">
            依推薦分數、趨勢與股價區間分類檢視個股。
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

        <section className="pricePanel">
          <div className="panelHeader panelHeaderWrap">
            <h2>依股價分類檢視</h2>
            <div className="tabs">
              {priceTabs.map((item) => (
                <button
                  key={item}
                  onClick={() => setPriceTab(item)}
                  className={`tabBtn ${priceTab === item ? "tabBtnActive" : ""}`}
                >
                  {item}（{priceCounts[item]}）
                </button>
              ))}
            </div>
          </div>
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
                        <div className="topSymbol">
                          {stock.symbol}｜{stock.price} 元
                        </div>
                      </div>
                      <div className="scoreBig">{stock.score}</div>
                    </div>
                    <div className="topCardFooter">
                      <span className={`trendBadge ${getTrendClass(stock.trend)}`}>
                        {stock.trend}
                      </span>
                      <span className="muted">{stock.entry_range}</span>
                    </div>
                  </div>
                ))
              )}
            </div>
          </div>

          <div className="panel panelWide">
            <div className="panelHeader panelHeaderWrap">
              <h2>
                選股結果
                <span className="resultHint">目前分類：{priceTab}</span>
              </h2>
              <div className="tabs">
                {(["全部", "強勢", "中性", "弱勢"] as const).map((item) => (
                  <button
                    key={item}
                    onClick={() => setTrendTab(item)}
                    className={`tabBtn ${trendTab === item ? "tabBtnActive" : ""}`}
                  >
                    {item}
                  </button>
                ))}
              </div>
            </div>

            {filteredResults.length === 0 ? (
              <div className="emptyBox">這個價位區間目前沒有符合資料</div>
            ) : (
              <div className="cardGrid">
                {filteredResults.map((stock) => (
                  <div className="stockCard" key={stock.symbol}>
                    <div className="stockHeader">
                      <div>
                        <div className="stockName">{stock.name}</div>
                        <div className="stockSymbol">
                          {stock.symbol}｜股價 {stock.price} 元
                        </div>
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
