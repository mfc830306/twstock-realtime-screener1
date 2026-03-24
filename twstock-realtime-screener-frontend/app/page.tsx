"use client";

import { useEffect, useMemo, useState } from "react";

type RawStock = {
  symbol: string;
  name?: string;
  price: number;
  change_percent?: number;
  volume?: number;
  ma5?: number;
  ma20?: number;
  signal?: string;
  reason?: string;
};

type StockCategory =
  | "all"
  | "top10"
  | "bullish"
  | "breakout"
  | "pullback"
  | "active"
  | "bearish";

type EnrichedStock = RawStock & {
  score: number;
  categoryTags: string[];
  entryPrice: number;
  targetPrice: number;
  stopLossPrice: number;
};

const API_URL = "https://twstock-realtime-screener1.onrender.com/scan";

const categoryLabels: Record<StockCategory, string> = {
  all: "全部股票",
  top10: "推薦前10",
  bullish: "均線多頭",
  breakout: "強勢突破",
  pullback: "拉回觀察",
  active: "成交活躍",
  bearish: "偏空避開",
};

function safeNumber(value: unknown, fallback = 0) {
  const num = Number(value);
  return Number.isFinite(num) ? num : fallback;
}

function round2(value: number) {
  return Math.round(value * 100) / 100;
}

function formatPrice(value: number) {
  return Number.isFinite(value) ? value.toFixed(2) : "-";
}

function formatPercent(value?: number) {
  if (value === undefined || value === null || Number.isNaN(value)) return "-";
  const sign = value > 0 ? "+" : "";
  return `${sign}${value.toFixed(2)}%`;
}

function formatVolume(value?: number) {
  if (!value || Number.isNaN(value)) return "-";
  return new Intl.NumberFormat("zh-TW").format(value);
}

function getScore(stock: RawStock) {
  const price = safeNumber(stock.price);
  const ma5 = safeNumber(stock.ma5);
  const ma20 = safeNumber(stock.ma20);
  const change = safeNumber(stock.change_percent);
  const volume = safeNumber(stock.volume);

  let score = 0;

  if (price > ma5 && ma5 > 0) score += 20;
  if (price > ma20 && ma20 > 0) score += 20;
  if (ma5 > ma20 && ma5 > 0 && ma20 > 0) score += 20;
  if (change > 0) score += Math.min(change * 4, 20);
  if (change > 3) score += 8;
  if (volume > 3000000) score += 8;
  if (volume > 10000000) score += 8;

  if (stock.signal?.includes("偏多")) score += 12;
  if (stock.signal?.includes("強勢")) score += 10;
  if (stock.signal?.includes("偏空")) score -= 18;

  return Math.max(0, Math.min(100, round2(score)));
}

function getCategoryTags(stock: RawStock) {
  const price = safeNumber(stock.price);
  const ma5 = safeNumber(stock.ma5);
  const ma20 = safeNumber(stock.ma20);
  const change = safeNumber(stock.change_percent);
  const volume = safeNumber(stock.volume);

  const tags: string[] = [];

  if (price > ma5 && price > ma20 && ma5 >= ma20) tags.push("bullish");
  if (change >= 3 && volume >= 3000000) tags.push("breakout");
  if (price >= ma20 && price <= ma20 * 1.03) tags.push("pullback");
  if (volume >= 5000000) tags.push("active");
  if (price < ma5 && price < ma20) tags.push("bearish");

  return tags;
}

function getTradePlan(stock: RawStock) {
  const price = safeNumber(stock.price);
  const ma5 = safeNumber(stock.ma5);
  const ma20 = safeNumber(stock.ma20);
  const change = safeNumber(stock.change_percent);

  let entry = price;
  let target = price * 1.08;
  let stop = price * 0.95;

  if (price > ma5 && price > ma20) {
    entry = price;
    target = price * (change >= 3 ? 1.1 : 1.07);
    stop = ma5 > 0 ? ma5 * 0.985 : price * 0.95;
  } else if (price >= ma20 && price <= ma20 * 1.03) {
    entry = ma20;
    target = price * 1.06;
    stop = ma20 * 0.97;
  } else if (price < ma5 && price < ma20) {
    entry = price;
    target = price * 1.03;
    stop = price * 0.96;
  } else {
    entry = price;
    target = price * 1.05;
    stop = ma20 > 0 ? ma20 * 0.97 : price * 0.95;
  }

  return {
    entryPrice: round2(entry),
    targetPrice: round2(target),
    stopLossPrice: round2(stop),
  };
}

function enrichStock(stock: RawStock): EnrichedStock {
  const score = getScore(stock);
  const categoryTags = getCategoryTags(stock);
  const tradePlan = getTradePlan(stock);

  return {
    ...stock,
    name: stock.name || "未提供名稱",
    score,
    categoryTags,
    ...tradePlan,
  };
}

function getFilteredStocks(stocks: EnrichedStock[], category: StockCategory) {
  switch (category) {
    case "top10":
      return [...stocks].sort((a, b) => b.score - a.score).slice(0, 10);
    case "bullish":
      return stocks.filter((s) => s.categoryTags.includes("bullish"));
    case "breakout":
      return stocks.filter((s) => s.categoryTags.includes("breakout"));
    case "pullback":
      return stocks.filter((s) => s.categoryTags.includes("pullback"));
    case "active":
      return stocks.filter((s) => s.categoryTags.includes("active"));
    case "bearish":
      return stocks.filter((s) => s.categoryTags.includes("bearish"));
    case "all":
    default:
      return stocks;
  }
}

export default function Page() {
  const [stockInput, setStockInput] = useState("");
  const [allStocks, setAllStocks] = useState<EnrichedStock[]>([]);
  const [activeCategory, setActiveCategory] = useState<StockCategory>("top10");
  const [keyword, setKeyword] = useState("");
  const [loading, setLoading] = useState(false);
  const [loaded, setLoaded] = useState(false);
  const [error, setError] = useState("");

  const fetchStocks = async () => {
    setLoading(true);
    setError("");

    try {
      const symbols = stockInput
        .split(/[\s,，]+/)
        .map((s) => s.trim())
        .filter(Boolean);

      const response = await fetch(API_URL, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify(
          symbols.length > 0
            ? { stocks: symbols }
            : {}
        ),
      });

      if (!response.ok) {
        throw new Error(`API 連線失敗，狀態碼：${response.status}`);
      }

      const data = await response.json();

      if (!Array.isArray(data)) {
        throw new Error("後端回傳格式錯誤，預期為陣列資料");
      }

      const enriched = data
        .map((item: RawStock) => enrichStock(item))
        .sort((a, b) => b.score - a.score);

      setAllStocks(enriched);
      setLoaded(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : "資料載入失敗");
      setAllStocks([]);
      setLoaded(true);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchStocks();
  }, []);

  const filteredStocks = useMemo(() => {
    const byCategory = getFilteredStocks(allStocks, activeCategory);

    if (!keyword.trim()) return byCategory;

    const q = keyword.trim().toLowerCase();
    return byCategory.filter((stock) => {
      return (
        stock.symbol.toLowerCase().includes(q) ||
        (stock.name || "").toLowerCase().includes(q) ||
        (stock.signal || "").toLowerCase().includes(q) ||
        (stock.reason || "").toLowerCase().includes(q)
      );
    });
  }, [allStocks, activeCategory, keyword]);

  const stats = useMemo(() => {
    const total = allStocks.length;
    const bullish = allStocks.filter((s) => s.categoryTags.includes("bullish")).length;
    const breakout = allStocks.filter((s) => s.categoryTags.includes("breakout")).length;
    const active = allStocks.filter((s) => s.categoryTags.includes("active")).length;
    const bearish = allStocks.filter((s) => s.categoryTags.includes("bearish")).length;

    return { total, bullish, breakout, active, bearish };
  }, [allStocks]);

  return (
    <main className="page-shell">
      <section className="hero-section">
        <div className="hero-badge">TW STOCK SCREENER PRO</div>
        <h1 className="hero-title">台股智慧選股系統</h1>
        <p className="hero-desc">
          一個頁面直接完成台股掃描、分類、推薦排序與進出場規劃。
        </p>

        <div className="control-panel">
          <div className="input-group">
            <label className="input-label">指定股票代號（可留空，留空則掃描後端預設清單）</label>
            <textarea
              className="stock-textarea"
              value={stockInput}
              onChange={(e) => setStockInput(e.target.value)}
              placeholder="例如：2330 2317 2454 2303"
            />
          </div>

          <div className="toolbar">
            <div className="search-box">
              <input
                className="search-input"
                type="text"
                value={keyword}
                onChange={(e) => setKeyword(e.target.value)}
                placeholder="搜尋代號、名稱、訊號、理由"
              />
            </div>

            <button
              className="primary-button"
              onClick={fetchStocks}
              disabled={loading}
            >
              {loading ? "載入中..." : "立即掃描"}
            </button>
          </div>
        </div>
      </section>

      <section className="stats-grid">
        <div className="stat-card">
          <div className="stat-label">總股票數</div>
          <div className="stat-value">{stats.total}</div>
        </div>
        <div className="stat-card">
          <div className="stat-label">均線多頭</div>
          <div className="stat-value">{stats.bullish}</div>
        </div>
        <div className="stat-card">
          <div className="stat-label">強勢突破</div>
          <div className="stat-value">{stats.breakout}</div>
        </div>
        <div className="stat-card">
          <div className="stat-label">成交活躍</div>
          <div className="stat-value">{stats.active}</div>
        </div>
        <div className="stat-card">
          <div className="stat-label">偏空避開</div>
          <div className="stat-value">{stats.bearish}</div>
        </div>
      </section>

      <section className="tabs-section">
        <div className="tabs-scroll">
          {(Object.keys(categoryLabels) as StockCategory[]).map((key) => (
            <button
              key={key}
              className={`tab-button ${activeCategory === key ? "active" : ""}`}
              onClick={() => setActiveCategory(key)}
            >
              {categoryLabels[key]}
            </button>
          ))}
        </div>
      </section>

      {error ? (
        <section className="message-card error-card">{error}</section>
      ) : null}

      {!loading && loaded && filteredStocks.length === 0 ? (
        <section className="message-card">查無符合條件的股票資料</section>
      ) : null}

      <section className="desktop-table-wrap">
        <table className="stock-table">
          <thead>
            <tr>
              <th>排名</th>
              <th>代號</th>
              <th>名稱</th>
              <th>現價</th>
              <th>漲跌幅</th>
              <th>成交量</th>
              <th>MA5</th>
              <th>MA20</th>
              <th>訊號</th>
              <th>推薦分數</th>
              <th>進場價</th>
              <th>出場價</th>
              <th>停損價</th>
              <th>判斷理由</th>
            </tr>
          </thead>
          <tbody>
            {filteredStocks.map((stock, index) => (
              <tr key={`${stock.symbol}-${index}`}>
                <td>{index + 1}</td>
                <td className="mono">{stock.symbol}</td>
                <td>{stock.name}</td>
                <td className="mono">{formatPrice(stock.price)}</td>
                <td
                  className={
                    safeNumber(stock.change_percent) > 0
                      ? "up"
                      : safeNumber(stock.change_percent) < 0
                      ? "down"
                      : ""
                  }
                >
                  {formatPercent(stock.change_percent)}
                </td>
                <td className="mono">{formatVolume(stock.volume)}</td>
                <td className="mono">{formatPrice(safeNumber(stock.ma5))}</td>
                <td className="mono">{formatPrice(safeNumber(stock.ma20))}</td>
                <td>{stock.signal || "-"}</td>
                <td>
                  <span className="score-badge">{stock.score}</span>
                </td>
                <td className="mono highlight">{formatPrice(stock.entryPrice)}</td>
                <td className="mono take-profit">{formatPrice(stock.targetPrice)}</td>
                <td className="mono stop-loss">{formatPrice(stock.stopLossPrice)}</td>
                <td className="reason-cell">{stock.reason || "-"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      <section className="mobile-cards">
        {filteredStocks.map((stock, index) => (
          <article className="stock-card" key={`${stock.symbol}-mobile-${index}`}>
            <div className="stock-card-top">
              <div>
                <div className="stock-name-row">
                  <span className="stock-symbol">{stock.symbol}</span>
                  <span className="stock-name">{stock.name}</span>
                </div>
                <div className="stock-signal">{stock.signal || "-"}</div>
              </div>
              <div className="score-badge large">{stock.score}</div>
            </div>

            <div className="stock-grid">
              <div>
                <span className="field-label">現價</span>
                <span className="field-value">{formatPrice(stock.price)}</span>
              </div>
              <div>
                <span className="field-label">漲跌幅</span>
                <span
                  className={`field-value ${
                    safeNumber(stock.change_percent) > 0
                      ? "up"
                      : safeNumber(stock.change_percent) < 0
                      ? "down"
                      : ""
                  }`}
                >
                  {formatPercent(stock.change_percent)}
                </span>
              </div>
              <div>
                <span className="field-label">成交量</span>
                <span className="field-value">{formatVolume(stock.volume)}</span>
              </div>
              <div>
                <span className="field-label">MA5 / MA20</span>
                <span className="field-value">
                  {formatPrice(safeNumber(stock.ma5))} / {formatPrice(safeNumber(stock.ma20))}
                </span>
              </div>
              <div>
                <span className="field-label">進場價</span>
                <span className="field-value highlight">{formatPrice(stock.entryPrice)}</span>
              </div>
              <div>
                <span className="field-label">出場價</span>
                <span className="field-value take-profit">{formatPrice(stock.targetPrice)}</span>
              </div>
              <div>
                <span className="field-label">停損價</span>
                <span className="field-value stop-loss">{formatPrice(stock.stopLossPrice)}</span>
              </div>
              <div>
                <span className="field-label">排名</span>
                <span className="field-value">{index + 1}</span>
              </div>
            </div>

            <div className="reason-box">
              <div className="field-label">判斷理由</div>
              <div className="reason-text">{stock.reason || "-"}</div>
            </div>
          </article>
        ))}
      </section>
    </main>
  );
}
