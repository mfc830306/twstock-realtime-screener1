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
  market?: string;
};

type ApiResponse = {
  success?: boolean;
  market_status?: string;
  data_date?: string;
  last_fetch_time?: string;
  last_update?: string;
  total?: number;
  stocks?: Stock[];
  message?: string;
};

const BACKEND_URL = "https://twstock-realtime-screener1.onrender.com/stocks";

export default function Home() {
  const [stocks, setStocks] = useState<Stock[]>([]);
  const [searchTerm, setSearchTerm] = useState("");
  const [selectedCategory, setSelectedCategory] = useState("all");
  const [lastFetchTime, setLastFetchTime] = useState("--");
  const [dataDate, setDataDate] = useState("--");
  const [marketStatus, setMarketStatus] = useState("--");
  const [loading, setLoading] = useState(true);

  const fetchStocks = async () => {
    try {
      setLoading(true);
      const res = await fetch(BACKEND_URL, { cache: "no-store" });
      const data: ApiResponse = await res.json();

      setStocks(Array.isArray(data.stocks) ? data.stocks : []);
      setLastFetchTime(data.last_fetch_time || "--");
      setDataDate(data.data_date || "--");
      setMarketStatus(data.market_status || "--");
    } catch (error) {
      setStocks([]);
      setLastFetchTime("--");
      setDataDate("--");
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
    { key: "all", label: "全部股票" },
    { key: "0to50", label: "0~50" },
    { key: "50to100", label: "50~100" },
    { key: "100to200", label: "100~200" },
    { key: "200plus", label: "200+" },
  ];

  const searchedStocks = useMemo(() => {
    if (!searchTerm) return stocks;
    return stocks.filter(
      (s) =>
        s.symbol.includes(searchTerm) ||
        s.name.includes(searchTerm)
    );
  }, [stocks, searchTerm]);

  const filterCategory = (s: Stock) => {
    if (selectedCategory === "all") return true;

    if (isETF(s)) return false;

    if (selectedCategory === "0to50") return s.price < 50;
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

  const top10 = useMemo(() => {
    return filteredStocks.slice(0, 10);
  }, [filteredStocks]);

  const formatPercent = (v?: number) =>
    v !== undefined ? `${v}%` : "--";

  const getClass = (v?: number) =>
    (v || 0) >= 0 ? "up" : "down";

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
            <span className="statusText">{marketStatus}</span>
          </div>

          <div className="sideLabel">資料日期</div>
          <div className="sideValue">{dataDate}</div>

          <div className="sideLabel">抓取時間</div>
          <div className="sideValue">{lastFetchTime}</div>
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
          <div className="sideTitle">統計</div>
          <div className="sideValue">總數：{filteredStocks.length}</div>
        </div>
      </aside>

      <main className="mainContent">
        <section className="heroCard">
          <div className="heroTop">
            <div>
              <h1 className="pageTitle">股票列表</h1>
              <p className="pageDesc">資料已分離：交易日 / 抓取時間</p>
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
            {loading ? "更新中..." : `資料日期：${dataDate}`}
          </div>
        </section>

        <section className="recommendCard">
          <div className="sectionHeader">
            <h2>推薦前 10 檔</h2>
          </div>

          <div className="recommendList">
            {top10.map((s, i) => (
              <div key={i} className="recommendItem">
                <div className="recommendMain">
                  #{i + 1} {s.symbol} {s.name}
                </div>

                <div>
                  <div>{s.price}</div>
                  <div className={getClass(s.change_percent)}>
                    {formatPercent(s.change_percent)}
                  </div>
                </div>

                <div>
                  分數：{s.score}<br />
                  進場：{s.entry_price}<br />
                  目標：{s.target_price}<br />
                  停損：{s.stop_loss}
                </div>

                <div className="recommendReason">
                  {s.reason}
                </div>
              </div>
            ))}
          </div>
        </section>

        <section className="tableCard">
          <div className="tableWrap">
            <table className="stockTable">
              <thead>
                <tr>
                  <th>市場</th>
                  <th>代號</th>
                  <th>名稱</th>
                  <th>價格</th>
                  <th>漲跌幅</th>
                  <th>成交量</th>
                </tr>
              </thead>

              <tbody>
                {filteredStocks.map((s, i) => (
                  <tr key={i}>
                    <td>{s.market}</td>
                    <td>{s.symbol}</td>
                    <td>{s.name}</td>
                    <td>{s.price}</td>
                    <td className={getClass(s.change_percent)}>
                      {formatPercent(s.change_percent)}
                    </td>
                    <td>{s.volume}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      </main>
    </div>
  );
}
