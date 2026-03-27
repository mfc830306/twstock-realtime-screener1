"use client";

import { useEffect, useMemo, useState } from "react";

type Stock = {
  symbol: string;
  name: string;
  price: number;
  change_percent: number;
  volume?: number;
  score?: number;
  signal?: string;
  entry_price?: string;
  target_price?: string;
  stop_loss?: string;
  reason?: string;
  update_time?: string;
};

const BACKEND_URL = "https://twstock-realtime-screener1.onrender.com/stocks";

export default function Home() {
  const [stocks, setStocks] = useState<Stock[]>([]);
  const [searchTerm, setSearchTerm] = useState("");
  const [selectedCategory, setSelectedCategory] = useState("all");
  const [rankType, setRankType] = useState<"up" | "down" | "volume">("up");

  useEffect(() => {
    fetch(BACKEND_URL)
      .then((res) => res.json())
      .then((data) => setStocks(data.stocks || []));
  }, []);

  const isETF = (s: Stock) =>
    s.symbol.startsWith("00") || s.name.includes("ETF");

  const searched = useMemo(() => {
    if (!searchTerm) return stocks;
    return stocks.filter(
      (s) =>
        s.symbol.includes(searchTerm) ||
        s.name.includes(searchTerm)
    );
  }, [stocks, searchTerm]);

  const filterCategory = (s: Stock) => {
    if (selectedCategory === "etf") return isETF(s);
    if (selectedCategory === "under10") return !isETF(s) && s.price < 10;
    if (selectedCategory === "10to30") return !isETF(s) && s.price >= 10 && s.price < 30;
    if (selectedCategory === "30to50") return !isETF(s) && s.price >= 30 && s.price < 50;
    if (selectedCategory === "50to100") return !isETF(s) && s.price >= 50 && s.price < 100;
    if (selectedCategory === "100to200") return !isETF(s) && s.price >= 100 && s.price < 200;
    if (selectedCategory === "200to500") return !isETF(s) && s.price >= 200 && s.price < 500;
    if (selectedCategory === "over500") return !isETF(s) && s.price >= 500;
    return true;
  };

  const filteredStocks = useMemo(() => {
    return searched.filter(filterCategory);
  }, [searched, selectedCategory]);

  const top10 = useMemo(() => {
    return [...stocks]
      .sort((a, b) => (b.score || 0) - (a.score || 0))
      .slice(0, 10);
  }, [stocks]);

  const ranked = useMemo(() => {
    const arr = [...stocks];
    if (rankType === "up") return arr.sort((a, b) => b.change_percent - a.change_percent);
    if (rankType === "down") return arr.sort((a, b) => a.change_percent - b.change_percent);
    return arr.sort((a, b) => (b.volume || 0) - (a.volume || 0));
  }, [stocks, rankType]);

  const categories = [
    { key: "all", label: "全部" },
    { key: "etf", label: "ETF" },
    { key: "under10", label: "10元以下" },
    { key: "10to30", label: "10~30元" },
    { key: "30to50", label: "30~50元" },
    { key: "50to100", label: "50~100元" },
    { key: "100to200", label: "100~200元" },
    { key: "200to500", label: "200~500元" },
    { key: "over500", label: "500元以上" },
  ];

  return (
    <div className="page">
      <div className="container">

        {/* 標題 */}
        <div className="topBar">
          <div className="titleBlock">
            <h1>台股即時選股系統</h1>
            <p>依價格分類 + 即時排行 + 推薦策略</p>
          </div>
        </div>

        {/* 搜尋 */}
        <div className="searchWrap">
          <input
            className="searchInput"
            placeholder="搜尋股票代號或名稱..."
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
          />
        </div>

        {/* 分類 */}
        <div className="sectionBox">
          <div className="sectionTitle">分類</div>

          <div className="categoryScroll">
            <div className="categoryRow">
              {categories.map((c) => (
                <button
                  key={c.key}
                  className={`categoryBtn ${
                    selectedCategory === c.key ? "active" : ""
                  }`}
                  onClick={() => setSelectedCategory(c.key)}
                >
                  {c.label}
                </button>
              ))}
            </div>
          </div>
        </div>

        {/* 主布局 */}
        <div className="mainLayout">

          {/* 🔥 TOP10 */}
          <div className="leftPanel panelCard">
            <div className="panelTitle">🔥 推薦TOP10</div>

            <div className="top10List">
              {top10.map((s, i) => (
                <div key={i} className="top10Card">
                  <div className="top10Rank">#{i + 1}</div>

                  <div className="stockName">
                    {s.symbol} {s.name}
                  </div>

                  <div className="stockPrice">{s.price}</div>

                  <div
                    className={
                      s.change_percent >= 0
                        ? "stockChangeUp"
                        : "stockChangeDown"
                    }
                  >
                    {s.change_percent}%
                  </div>

                  <div className="stockMeta">
                    訊號：{s.signal || "--"}
                  </div>

                  <div className="stockScore">
                    分數：{s.score}
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* 📊 排行 */}
          <div className="rankPanel panelCard">
            <div className="panelTitle">📊 排行榜</div>

            <div className="rankTabs">
              <button
                className={`rankTab ${rankType === "up" ? "active" : ""}`}
                onClick={() => setRankType("up")}
              >
                漲幅
              </button>
              <button
                className={`rankTab ${rankType === "down" ? "active" : ""}`}
                onClick={() => setRankType("down")}
              >
                跌幅
              </button>
              <button
                className={`rankTab ${rankType === "volume" ? "active" : ""}`}
                onClick={() => setRankType("volume")}
              >
                成交量
              </button>
            </div>

            <div className="rankList">
              {ranked.slice(0, 10).map((s, i) => (
                <div key={i} className="rankItem">
                  <div className="rankLeft">
                    <div className="rankNum">#{i + 1}</div>
                    <div className="rankName">
                      {s.symbol} {s.name}
                    </div>
                    <div className="rankPrice">{s.price}</div>
                  </div>

                  <div className="rankRight">
                    {s.change_percent}%
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* 📈 主區 */}
          <div className="listPanel panelCard">
            <div className="listHeader">
              <div className="listTitle">
                股票列表（{selectedCategory}）
              </div>
              <div className="listSub">
                共 {filteredStocks.length} 檔
              </div>
            </div>

            <div className="stockGrid">
              {filteredStocks.map((s, i) => (
                <div key={i} className="stockCard">
                  <div className="stockCardTop">
                    <div className="stockCodeName">
                      <div className="stockCode">{s.symbol}</div>
                      <div className="stockTitle">{s.name}</div>
                    </div>

                    <div className="scoreBadge">
                      {s.score}
                    </div>
                  </div>

                  <div className="stockBigPrice">{s.price}</div>

                  <div
                    className={
                      s.change_percent >= 0
                        ? "stockChangeUp"
                        : "stockChangeDown"
                    }
                  >
                    {s.change_percent}%
                  </div>

                  <div className="stockInfo">
                    訊號：{s.signal}<br />
                    進場：{s.entry_price}<br />
                    目標：{s.target_price}<br />
                    停損：{s.stop_loss}
                  </div>
                </div>
              ))}
            </div>
          </div>

        </div>
      </div>
    </div>
  );
}
