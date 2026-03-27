"use client";

import { useEffect, useMemo, useState } from "react";

type Stock = {
  symbol: string;
  name: string;
  price: number;
  change?: number;
  change_percent: number;
  volume?: number;
  score?: number;
  signal?: string;
  reason?: string;
  entry_price?: string;
  target_price?: string;
  stop_loss?: string;
  prev_close?: number;
  open?: number;
  high?: number;
  low?: number;
  update_time?: string;
};

type ApiResponse = {
  success: boolean;
  market_status?: string;
  data_date?: string;
  last_update?: string;
  total?: number;
  stocks?: Stock[];
  message?: string;
};

const BACKEND_URL =
  "https://twstock-realtime-screener1.onrender.com/stocks";

export default function Home() {
  const [stocks, setStocks] = useState<Stock[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const [searchTerm, setSearchTerm] = useState("");
  const [selectedCategory, setSelectedCategory] = useState("all");
  const [rankType, setRankType] = useState<"up" | "down" | "volume">("up");

  const [lastUpdate, setLastUpdate] = useState("--:--:--");
  const [marketStatus, setMarketStatus] = useState("載入中");
  const [dataDate, setDataDate] = useState("");

  const fetchStocks = async () => {
    try {
      setLoading(true);
      setError("");

      const res = await fetch(BACKEND_URL, {
        cache: "no-store",
      });

      const data: ApiResponse = await res.json();

      if (!data.success || !data.stocks) {
        throw new Error(data.message || "取得資料失敗");
      }

      const normalizedStocks = data.stocks.map((stock) => ({
        ...stock,
        price: Number(stock.price || 0),
        change: Number(stock.change || 0),
        change_percent: Number(stock.change_percent || 0),
        volume: Number(stock.volume || 0),
        score: Number(stock.score || 0),
        prev_close: Number(stock.prev_close || 0),
        open: Number(stock.open || 0),
        high: Number(stock.high || 0),
        low: Number(stock.low || 0),
      }));

      setStocks(normalizedStocks);
      setLastUpdate(data.last_update || "--:--:--");
      setMarketStatus(data.market_status || "正常");
      setDataDate(data.data_date || "");
    } catch (err) {
      console.error(err);
      setError("讀取股票資料失敗，請稍後再試");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchStocks();
  }, []);

  const categories = useMemo(() => {
    const countByRange = (min: number, max: number | null) => {
      return stocks.filter((s) => {
        if (max === null) return s.price >= min;
        return s.price >= min && s.price < max;
      }).length;
    };

    return [
      { key: "all", label: `全部 (${stocks.length})` },
      { key: "under10", label: `10元以下 (${countByRange(0, 10)})` },
      { key: "10to30", label: `10~30元 (${countByRange(10, 30)})` },
      { key: "30to50", label: `30~50元 (${countByRange(30, 50)})` },
      { key: "50to100", label: `50~100元 (${countByRange(50, 100)})` },
      { key: "100to200", label: `100~200元 (${countByRange(100, 200)})` },
      { key: "200to500", label: `200~500元 (${countByRange(200, 500)})` },
      { key: "over500", label: `500元以上 (${countByRange(500, null)})` },
    ];
  }, [stocks]);

  const filterByCategory = (stock: Stock) => {
    switch (selectedCategory) {
      case "under10":
        return stock.price < 10;
      case "10to30":
        return stock.price >= 10 && stock.price < 30;
      case "30to50":
        return stock.price >= 30 && stock.price < 50;
      case "50to100":
        return stock.price >= 50 && stock.price < 100;
      case "100to200":
        return stock.price >= 100 && stock.price < 200;
      case "200to500":
        return stock.price >= 200 && stock.price < 500;
      case "over500":
        return stock.price >= 500;
      default:
        return true;
    }
  };

  const filteredStocks = useMemo(() => {
    return stocks.filter((stock) => {
      const keyword = searchTerm.trim().toLowerCase();

      const matchSearch =
        !keyword ||
        stock.symbol.toLowerCase().includes(keyword) ||
        stock.name.toLowerCase().includes(keyword);

      return matchSearch && filterByCategory(stock);
    });
  }, [stocks, searchTerm, selectedCategory]);

  const top10Stocks = useMemo(() => {
    return [...stocks]
      .sort((a, b) => {
        const scoreDiff = (b.score || 0) - (a.score || 0);
        if (scoreDiff !== 0) return scoreDiff;
        return b.change_percent - a.change_percent;
      })
      .slice(0, 10);
  }, [stocks]);

  const rankedStocks = useMemo(() => {
    const copied = [...stocks];

    if (rankType === "up") {
      return copied.sort((a, b) => b.change_percent - a.change_percent);
    }

    if (rankType === "down") {
      return copied.sort((a, b) => a.change_percent - b.change_percent);
    }

    return copied.sort((a, b) => (b.volume || 0) - (a.volume || 0));
  }, [stocks, rankType]);

  const categoryLabelMap: Record<string, string> = {
    all: "全部",
    under10: "10元以下",
    "10to30": "10~30元",
    "30to50": "30~50元",
    "50to100": "50~100元",
    "100to200": "100~200元",
    "200to500": "200~500元",
    over500: "500元以上",
  };

  const formatNumber = (num?: number) => {
    return Number(num || 0).toLocaleString("zh-TW");
  };

  const formatPrice = (num?: number) => {
    const n = Number(num || 0);
    return n % 1 === 0 ? String(n) : n.toFixed(2);
  };

  return (
    <div className="page">
      <div className="container">
        <div className="topBar">
          <div className="titleBlock">
            <h1>台股選股系統</h1>
            <p>全部股票 / 價格分類 / 推薦TOP10 / 即時排行</p>
            {dataDate ? (
              <p style={{ marginTop: 8, fontSize: 14, color: "#8fb2de" }}>
                資料日期：{dataDate}
              </p>
            ) : null}
          </div>

          <div className="updateCard">
            <div className="label">最後更新時間</div>
            <div className="time">{lastUpdate}</div>
            <div className="status">{marketStatus}</div>
          </div>
        </div>

        <div className="searchWrap">
          <input
            className="searchInput"
            type="text"
            placeholder="搜尋股票代碼或名稱，例如：2330 / 台積電"
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
          />
        </div>

        <div className="sectionBox">
          <div className="sectionTitle">💰 價格分類</div>
          <div className="categoryScroll">
            <div className="categoryRow">
              {categories.map((cat) => (
                <button
                  key={cat.key}
                  className={`categoryBtn ${
                    selectedCategory === cat.key ? "active" : ""
                  }`}
                  onClick={() => setSelectedCategory(cat.key)}
                >
                  {cat.label}
                </button>
              ))}
            </div>
          </div>
        </div>

        {loading ? (
          <div className="panelCard">
            <div className="panelTitle">載入中...</div>
            <div style={{ color: "#b9ccea" }}>正在取得股票資料，請稍候</div>
          </div>
        ) : error ? (
          <div className="panelCard">
            <div className="panelTitle">讀取失敗</div>
            <div style={{ color: "#ff9aa8", marginBottom: 12 }}>{error}</div>
            <button className="categoryBtn active" onClick={fetchStocks}>
              重新載入
            </button>
          </div>
        ) : (
          <div className="mainLayout">
            <div className="leftPanel">
              <div className="panelCard">
                <div className="panelTitle">🔥 推薦 TOP10</div>
                <div className="top10List">
                  {top10Stocks.map((stock, index) => (
                    <div key={stock.symbol} className="top10Card">
                      <div className="top10Rank">#{index + 1}</div>
                      <div className="stockName">
                        {stock.symbol} {stock.name}
                      </div>
                      <div className="stockPrice">{formatPrice(stock.price)}</div>

                      <div
                        className={
                          stock.change_percent >= 0
                            ? "stockChangeUp"
                            : "stockChangeDown"
                        }
                      >
                        {stock.change_percent >= 0 ? "+" : ""}
                        {stock.change_percent.toFixed(2)}%
                      </div>

                      <div className="stockMeta">
                        昨收 {formatPrice(stock.prev_close)}｜開{" "}
                        {formatPrice(stock.open)}
                      </div>
                      <div className="stockMeta">
                        高 {formatPrice(stock.high)}｜低 {formatPrice(stock.low)}
                      </div>
                      <div className="stockScore">
                        推薦分數：{stock.score || 0}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </div>

            <div className="rankPanel">
              <div className="panelCard">
                <div className="panelTitle">📈 排行榜</div>

                <div className="rankTabs">
                  <button
                    className={`rankTab ${rankType === "up" ? "active" : ""}`}
                    onClick={() => setRankType("up")}
                  >
                    漲幅排行
                  </button>
                  <button
                    className={`rankTab ${rankType === "down" ? "active" : ""}`}
                    onClick={() => setRankType("down")}
                  >
                    跌幅排行
                  </button>
                  <button
                    className={`rankTab ${
                      rankType === "volume" ? "active" : ""
                    }`}
                    onClick={() => setRankType("volume")}
                  >
                    成交量排行
                  </button>
                </div>

                <div className="rankList">
                  {rankedStocks.slice(0, 10).map((stock, index) => (
                    <div key={stock.symbol} className="rankItem">
                      <div className="rankLeft">
                        <div className="rankNum">{index + 1}</div>
                        <div className="rankName">
                          {stock.symbol} {stock.name}
                        </div>
                        <div className="rankPrice">
                          價格 {formatPrice(stock.price)}
                        </div>
                      </div>

                      <div className="rankRight">
                        {rankType === "volume"
                          ? formatNumber(stock.volume)
                          : `${stock.change_percent >= 0 ? "+" : ""}${stock.change_percent.toFixed(2)}%`}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </div>

            <div className="listPanel">
              <div className="panelCard">
                <div className="listHeader">
                  <div className="listTitle">
                    全部股票 ({filteredStocks.length})
                  </div>
                  <div className="listSub">
                    目前分類：{categoryLabelMap[selectedCategory]}
                  </div>
                </div>

                <div className="stockGrid">
                  {filteredStocks.map((stock) => (
                    <div key={stock.symbol} className="stockCard">
                      <div className="stockCardTop">
                        <div className="stockCodeName">
                          <div className="stockCode">{stock.symbol}</div>
                          <div className="stockTitle">{stock.name}</div>
                        </div>
                        <div className="scoreBadge">分數 {stock.score || 0}</div>
                      </div>

                      <div className="stockBigPrice">
                        {formatPrice(stock.price)}
                      </div>

                      <div
                        className={
                          stock.change_percent >= 0
                            ? "stockChangeUp"
                            : "stockChangeDown"
                        }
                        style={{ marginBottom: 10 }}
                      >
                        {stock.change_percent >= 0 ? "+" : ""}
                        {stock.change_percent.toFixed(2)}%
                      </div>

                      <div className="stockInfo">
                        昨收：{formatPrice(stock.prev_close)}
                        <br />
                        開盤：{formatPrice(stock.open)}
                        <br />
                        最高：{formatPrice(stock.high)}
                        <br />
                        最低：{formatPrice(stock.low)}
                        <br />
                        成交量：{formatNumber(stock.volume)}
                        <br />
                        更新：{stock.update_time || "--"}
                      </div>
                    </div>
                  ))}
                </div>

                {filteredStocks.length === 0 && (
                  <div style={{ color: "#b9ccea", paddingTop: 8 }}>
                    找不到符合條件的股票
                  </div>
                )}
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
