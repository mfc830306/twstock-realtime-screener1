"use client";

import { useEffect, useMemo, useState } from "react";

type Stock = {
  symbol: string;
  name: string;
  market: string;
  price: number;
  change_percent: number;
  volume: number;
  score: number;
  signal?: string;
  reason?: string;
  entry_price?: string;
  target_price?: string;
  stop_loss?: string;
};

const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE ||
  "https://twstock-realtime-screener1.onrender.com";

const BUCKETS = [
  { key: "all", label: "全部" },
  { key: "lt10", label: "10元以下" },
  { key: "10_20", label: "10-20元" },
  { key: "20_50", label: "20-50元" },
  { key: "50_100", label: "50-100元" },
  { key: "100_200", label: "100-200元" },
  { key: "200_500", label: "200-500元" },
  { key: "500_1000", label: "500-1000元" },
  { key: "gte1000", label: "1000元以上" },
];

function getBucket(price: number) {
  if (price < 10) return "lt10";
  if (price < 20) return "10_20";
  if (price < 50) return "20_50";
  if (price < 100) return "50_100";
  if (price < 200) return "100_200";
  if (price < 500) return "200_500";
  if (price < 1000) return "500_1000";
  return "gte1000";
}

function formatPercent(value: number) {
  return `${value >= 0 ? "+" : ""}${value.toFixed(2)}%`;
}

function formatVolume(value: number) {
  return new Intl.NumberFormat("zh-TW").format(value || 0);
}

export default function Page() {
  const [stocks, setStocks] = useState<Stock[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [bucket, setBucket] = useState("all");
  const [keyword, setKeyword] = useState("");

  useEffect(() => {
    const loadStocks = async () => {
      try {
        setLoading(true);
        setError("");

        const res = await fetch(`${API_BASE}/stocks`, { cache: "no-store" });
        const data = await res.json();

        if (!res.ok || !data.success) {
          throw new Error(data.message || "讀取股票資料失敗");
        }

        setStocks(Array.isArray(data.stocks) ? data.stocks : []);
      } catch (err: any) {
        setError(err?.message || "載入失敗");
        setStocks([]);
      } finally {
        setLoading(false);
      }
    };

    loadStocks();
  }, []);

  const filteredStocks = useMemo(() => {
    const kw = keyword.trim().toLowerCase();

    return [...stocks]
      .filter((s) => {
        const bucketOk = bucket === "all" || getBucket(s.price) === bucket;
        const keywordOk =
          !kw ||
          s.symbol.toLowerCase().includes(kw) ||
          s.name.toLowerCase().includes(kw);

        return bucketOk && keywordOk;
      })
      .sort((a, b) => {
        if (b.score !== a.score) return b.score - a.score;
        if (b.change_percent !== a.change_percent) {
          return b.change_percent - a.change_percent;
        }
        return b.volume - a.volume;
      });
  }, [stocks, bucket, keyword]);

  const top10 = useMemo(() => filteredStocks.slice(0, 10), [filteredStocks]);

  const totalCount = stocks.length;
  const bucketCount = filteredStocks.length;

  return (
    <div className="page">
      <div className="container">
        <section className="hero">
          <div className="badge">TW STOCK</div>
          <h1 className="title">台股分類選股系統</h1>
          <p className="subtitle">
            顯示全部台股，依價格分類、搜尋與推薦前 10 檔
          </p>
          <div className="marketInfo">
            全部股票：{totalCount} 檔　/　目前篩選：{bucketCount} 檔
          </div>

          <div className="searchRow">
            <input
              className="input"
              placeholder="搜尋股票代碼 / 名稱，例如 2330 或 台積電"
              value={keyword}
              onChange={(e) => setKeyword(e.target.value)}
            />
            <button
              className="btn btnBlue"
              onClick={() => window.location.reload()}
              disabled={loading}
            >
              重新整理
            </button>
            <button
              className="btn btnDark"
              onClick={() => {
                setKeyword("");
                setBucket("all");
              }}
              disabled={loading}
            >
              清除篩選
            </button>
          </div>

          {error ? <div className="errorBox">載入失敗：{error}</div> : null}
        </section>

        <section className="summaryGrid">
          <div className="summaryCard">
            <div className="summaryTitle">全部股票數</div>
            <div className="summaryValue">{totalCount}</div>
          </div>
          <div className="summaryCard">
            <div className="summaryTitle">目前分類</div>
            <div className="summaryValue" style={{ fontSize: 24 }}>
              {BUCKETS.find((b) => b.key === bucket)?.label ?? "全部"}
            </div>
          </div>
          <div className="summaryCard">
            <div className="summaryTitle">篩選後數量</div>
            <div className="summaryValue">{bucketCount}</div>
          </div>
          <div className="summaryCard">
            <div className="summaryTitle">搜尋關鍵字</div>
            <div className="summaryValue" style={{ fontSize: 24 }}>
              {keyword.trim() || "無"}
            </div>
          </div>
        </section>

        <section className="pricePanel">
          <div className="panelHeader panelHeaderWrap">
            <h2>價格分類</h2>
            <span>點選價格區間切換股票清單</span>
          </div>

          <div className="tabs">
            {BUCKETS.map((b) => (
              <button
                key={b.key}
                onClick={() => setBucket(b.key)}
                className={`tabBtn ${bucket === b.key ? "tabBtnActive" : ""}`}
              >
                {b.label}
              </button>
            ))}
          </div>
        </section>

        <div className="mainGrid">
          <section className="panel">
            <div className="panelHeader">
              <h2>推薦前 10 檔</h2>
              <span>依分數、漲跌幅、成交量排序</span>
            </div>

            {loading ? (
              <div className="emptyBox">載入中...</div>
            ) : top10.length === 0 ? (
              <div className="emptyBox">目前沒有可顯示的推薦股票</div>
            ) : (
              <div className="topList">
                {top10.map((s) => (
                  <div key={s.symbol} className="topCard">
                    <div className="topCardHeader">
                      <div>
                        <div className="topName">{s.name}</div>
                        <div className="topSymbol">
                          {s.symbol} ・ {s.market}
                        </div>
                      </div>
                      <div className="scoreBig">{s.score}</div>
                    </div>

                    <div className="metricGrid">
                      <div className="metricBox">
                        <div className="metricLabel">現價</div>
                        <div className="metricValue">{s.price}</div>
                      </div>
                      <div className="metricBox">
                        <div className="metricLabel">漲跌幅</div>
                        <div className="metricValue">
                          {formatPercent(s.change_percent)}
                        </div>
                      </div>
                    </div>

                    <div className="strategyList">
                      <div className="strategyRow">
                        <span className="strategyLabel">進場</span>
                        <span className="strategyValue">
                          {s.entry_price || "-"}
                        </span>
                      </div>
                      <div className="strategyRow">
                        <span className="strategyLabel">目標</span>
                        <span className="strategyValue">
                          {s.target_price || "-"}
                        </span>
                      </div>
                      <div className="strategyRow">
                        <span className="strategyLabel">停損</span>
                        <span className="strategyValue">
                          {s.stop_loss || "-"}
                        </span>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </section>

          <section className="panel panelWide">
            <div className="panelHeader">
              <h2>股票清單</h2>
              <span>共 {filteredStocks.length} 檔</span>
            </div>

            {loading ? (
              <div className="emptyBox">載入股票資料中...</div>
            ) : filteredStocks.length === 0 ? (
              <div className="emptyBox">查無符合條件的股票</div>
            ) : (
              <div className="cardGrid">
                {filteredStocks.map((s) => {
                  const trendClass =
                    s.score >= 80
                      ? "trendBadge trendStrong"
                      : s.score >= 45
                      ? "trendBadge trendNeutral"
                      : "trendBadge trendWeak";

                  return (
                    <article key={s.symbol} className="stockCard">
                      <div className="stockHeader">
                        <div>
                          <div className="stockName">{s.name}</div>
                          <div className="stockSymbol">
                            {s.symbol} ・ {s.market}
                          </div>
                        </div>
                        <div className={trendClass}>{s.signal || "中性"}</div>
                      </div>

                      <div className="metricGrid">
                        <div className="metricBox">
                          <div className="metricLabel">現價</div>
                          <div className="metricValue">{s.price}</div>
                        </div>
                        <div className="metricBox">
                          <div className="metricLabel">漲跌幅</div>
                          <div className="metricValue">
                            {formatPercent(s.change_percent)}
                          </div>
                        </div>
                        <div className="metricBox">
                          <div className="metricLabel">成交量</div>
                          <div className="metricValue">
                            {formatVolume(s.volume)}
                          </div>
                        </div>
                        <div className="metricBox">
                          <div className="metricLabel">推薦分數</div>
                          <div className="metricValue">{s.score}</div>
                        </div>
                      </div>

                      <div className="strategyList">
                        <div className="strategyRow">
                          <span className="strategyLabel">進場價</span>
                          <span className="strategyValue">
                            {s.entry_price || "-"}
                          </span>
                        </div>
                        <div className="strategyRow">
                          <span className="strategyLabel">目標價</span>
                          <span className="strategyValue">
                            {s.target_price || "-"}
                          </span>
                        </div>
                        <div className="strategyRow">
                          <span className="strategyLabel">停損價</span>
                          <span className="strategyValue">
                            {s.stop_loss || "-"}
                          </span>
                        </div>
                      </div>

                      <div className="reasonBox">
                        <div className="reasonTitle">判斷說明</div>
                        <div className="reasonText">{s.reason || "暫無說明"}</div>
                      </div>
                    </article>
                  );
                })}
              </div>
            )}
          </section>
        </div>
      </div>
    </div>
  );
}
