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
  entry_price?: string;
  target_price?: string;
  stop_loss?: string;
  reason?: string;
  prev_close?: number;
  open?: number;
  high?: number;
  low?: number;
  update_time?: string;
};

type ApiResponse = {
  success?: boolean;
  market_status?: string;
  data_date?: string;
  last_update?: string;
  total?: number;
  stocks?: Stock[];
  message?: string;
};

const BACKEND_URL = "https://twstock-realtime-screener1.onrender.com/stocks";

export default function Home() {
  const [stocks, setStocks] = useState<Stock[]>([]);
  const [searchTerm, setSearchTerm] = useState("");
  const [selectedCategory, setSelectedCategory] = useState("50to100");
  const [lastUpdate, setLastUpdate] = useState("--");
  const [marketStatus, setMarketStatus] = useState("--");
  const [loading, setLoading] = useState(true);

  const fetchStocks = async () => {
    try {
      setLoading(true);
      const res = await fetch(BACKEND_URL, { cache: "no-store" });
      const data: ApiResponse = await res.json();

      setStocks(Array.isArray(data.stocks) ? data.stocks : []);
      setLastUpdate(data.last_update || "--");
      setMarketStatus(data.market_status || "--");
    } catch (error) {
      setStocks([]);
      setLastUpdate("--");
      setMarketStatus("讀取失敗");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchStocks();
  }, []);

  const isETF = (s: Stock) => {
    return s.symbol.startsWith("00") || s.name.includes("ETF");
  };

  const categories = [
    { key: "0to50", label: "0~50" },
    { key: "50to100", label: "50~100" },
    { key: "100to200", label: "100~200" },
    { key: "200plus", label: "200+" },
  ];

  const selectedCategoryLabel =
    categories.find((c) => c.key === selectedCategory)?.label || "50~100";

  const searchedStocks = useMemo(() => {
    const keyword = searchTerm.trim();
    if (!keyword) return stocks;

    return stocks.filter(
      (s) => s.symbol.includes(keyword) || s.name.includes(keyword)
    );
  }, [stocks, searchTerm]);

  const filterCategory = (s: Stock) => {
    if (isETF(s)) return false;
    if (selectedCategory === "0to50") return s.price >= 0 && s.price < 50;
    if (selectedCategory === "50to100") return s.price >= 50 && s.price < 100;
    if (selectedCategory === "100to200") return s.price >= 100 && s.price < 200;
    if (selectedCategory === "200plus") return s.price >= 200;
    return true;
  };

  const filteredStocks = useMemo(() => {
    return searchedStocks
      .filter(filterCategory)
      .sort((a, b) => (b.score || 0) - (a.score || 0));
  }, [searchedStocks, selectedCategory]);

  const recommendedTop10 = useMemo(() => {
    return filteredStocks.slice(0, 10);
  }, [filteredStocks]);

  const formatNumber = (value?: number) => {
    if (value === undefined || value === null) return "--";
    return value.toLocaleString();
  };

  const formatPercent = (value?: number) => {
    if (value === undefined || value === null) return "--";
    return `${value}%`;
  };

  const getPercentClass = (value?: number) => {
    if ((value || 0) >= 0) return "up";
    return "down";
  };

  return (
    <div className="dashboard">
      <aside className="sidebar">
        <div className="brandCard">
          <div className="brandTitle">台股智慧選股</div>
          <div className="brandSub">盤中選股系統</div>
        </div>

        <div className="sideCard">
          <div className="sideTitle">狀態</div>

          <div className="statusRow">
            <span className="statusDot" />
            <span className="statusText">
              {marketStatus === "收盤" ? "收盤（非即時）" : "盤中（準即時）"}
            </span>
          </div>

          <div className="sideLabel">最後更新</div>
          <div className="sideValue">{lastUpdate}</div>

          <div className="sideLabel">更新頻率</div>
          <div className="sideValue">手動更新</div>
        </div>

        <div className="sideCard">
          <div className="sideTitle">價格分類</div>

          <div className="categoryStack">
            {categories.map((c) => (
              <button
                key={c.key}
                className={`sideCategoryBtn ${
                  selectedCategory === c.key ? "active" : ""
                }`}
                onClick={() => setSelectedCategory(c.key)}
              >
                {c.label}
              </button>
            ))}
          </div>
        </div>

        <div className="sideCard">
          <div className="sideTitle">目前區間</div>
          <div className="sideValue">{selectedCategoryLabel}</div>

          <div className="sideLabel">目前筆數</div>
          <div className="sideValue">{filteredStocks.length}</div>
        </div>
      </aside>

      <main className="mainContent">
        <section className="heroCard">
          <div className="heroTop">
            <div>
              <h1 className="pageTitle">股票列表</h1>
              <p className="pageDesc">
                盤中顯示準即時資料，13:30 後顯示收盤結果
              </p>
            </div>

            <div className="searchArea">
              <input
                className="searchInput"
                placeholder="輸入代號或名稱"
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
              />
              <button className="refreshBtn" onClick={fetchStocks}>
                立即更新
              </button>
            </div>
          </div>

          <div className="infoBar">
            {loading ? "資料更新中..." : `資料已更新：${lastUpdate}`}
          </div>
        </section>

        <section className="recommendCard">
          <div className="sectionHeader">
            <h2>推薦前 10 檔</h2>
            <span>依推薦分數排序</span>
          </div>

          {recommendedTop10.length === 0 ? (
            <div className="emptyBox">目前沒有符合條件的股票</div>
          ) : (
            <div className="recommendList">
              {recommendedTop10.map((s, i) => (
                <div key={`${s.symbol}-${i}`} className="recommendItem">
                  <div className="recommendMain">
                    <div className="recommendRank">#{i + 1}</div>
                    <div className="recommendName">
                      {s.symbol} {s.name}
                    </div>
                  </div>

                  <div className="recommendPriceBlock">
                    <div className="recommendPrice">{s.price}</div>
                    <div className={`recommendChange ${getPercentClass(s.change_percent)}`}>
                      {formatPercent(s.change_percent)}
                    </div>
                    <div className="recommendSignal">訊號：{s.signal || "--"}</div>
                  </div>

                  <div className="recommendPlan">
                    <div>分數：{s.score ?? "--"}</div>
                    <div>進場：{s.entry_price || "--"}</div>
                    <div>出場：{s.target_price || "--"}</div>
                    <div>停損：{s.stop_loss || "--"}</div>
                  </div>

                  <div className="recommendReason">
                    <span className="reasonLabel">推薦原因</span>
                    <div className="reasonText">{s.reason || "暫無推薦原因"}</div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </section>

        <section className="tableCard">
          <div className="tableWrap">
            <table className="stockTable">
              <thead>
                <tr>
                  <th>代號</th>
                  <th>名稱</th>
                  <th>價格</th>
                  <th>漲跌</th>
                  <th>漲跌幅</th>
                  <th>成交量</th>
                  <th>推薦分數</th>
                  <th>進場價</th>
                  <th>出場價</th>
                  <th>停損價</th>
                </tr>
              </thead>

              <tbody>
                {filteredStocks.length === 0 ? (
                  <tr>
                    <td colSpan={10} className="emptyTd">
                      沒有符合條件的資料
                    </td>
                  </tr>
                ) : (
                  filteredStocks.map((s, i) => (
                    <tr key={`${s.symbol}-${i}`}>
                      <td>{s.symbol}</td>
                      <td>{s.name}</td>
                      <td>{s.price}</td>
                      <td className={getPercentClass(s.change || 0)}>
                        {s.change ?? "--"}
                      </td>
                      <td className={getPercentClass(s.change_percent)}>
                        {formatPercent(s.change_percent)}
                      </td>
                      <td>{formatNumber(s.volume)}</td>
                      <td>{s.score ?? "--"}</td>
                      <td>{s.entry_price || "--"}</td>
                      <td>{s.target_price || "--"}</td>
                      <td>{s.stop_loss || "--"}</td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </section>
      </main>
    </div>
  );
}
