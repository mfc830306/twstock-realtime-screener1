"use client";

import { useEffect, useMemo, useState } from "react";

type Stock = {
  stock_code: string;
  stock_name: string;
  market: string;
  industry_category: string;
  price: number;
  change: number;
};

type StockDetail = {
  stock_code: string;
  stock_name: string;
  market: string;
  industry_category: string;
  price: number | null;
  change: number | null;
  change_percent: number | null;
  open: number | null;
  high: number | null;
  low: number | null;
  volume: number | null;
  prev_close: number | null;
};

type RecommendStock = {
  stock_code: string;
  stock_name: string;
  market: string;
  industry_category: string;
  entry_price: number;
  target_price: number;
  stop_loss: number;
  reason: string;
  price: number | null;
  change: number | null;
  change_percent: number | null;
};

export default function Home() {
  const [stocks, setStocks] = useState<Stock[]>([]);
  const [recommendStocks, setRecommendStocks] = useState<RecommendStock[]>([]);
  const [industries, setIndustries] = useState<string[]>(["全部"]);
  const [keyword, setKeyword] = useState("");
  const [selectedIndustry, setSelectedIndustry] = useState("全部");
  const [loading, setLoading] = useState(true);
  const [selectedStock, setSelectedStock] = useState<StockDetail | null>(null);
  const [selectedLoading, setSelectedLoading] = useState(false);

  useEffect(() => {
    Promise.all([
      fetch("http://127.0.0.1:8000/api/stocks?limit=2000").then((res) => res.json()),
      fetch("http://127.0.0.1:8000/api/recommend/short").then((res) => res.json()),
      fetch("http://127.0.0.1:8000/api/industries").then((res) => res.json()),
    ])
      .then(([stockData, recommendData, industriesData]) => {
        setStocks(stockData);
        setRecommendStocks(recommendData);
        setIndustries(industriesData);
      })
      .catch((err) => console.error("讀取資料失敗：", err))
      .finally(() => setLoading(false));
  }, []);

  const filteredStocks = useMemo(() => {
    return stocks.filter((s) => {
      const text = `${s.stock_code}${s.stock_name}${s.market}${s.industry_category}`.toLowerCase();
      const matchKeyword = text.includes(keyword.toLowerCase());
      const matchIndustry =
        selectedIndustry === "全部" || s.industry_category === selectedIndustry;
      return matchKeyword && matchIndustry;
    });
  }, [stocks, keyword, selectedIndustry]);

  const fetchSingleStock = async (code: string) => {
    setSelectedLoading(true);
    try {
      const res = await fetch(`http://127.0.0.1:8000/api/stock_detail?code=${code}`);
      const data = await res.json();
      setSelectedStock(data);
    } catch (err) {
      console.error(err);
    } finally {
      setSelectedLoading(false);
    }
  };

  const colorStyle = (n: number | null | undefined): React.CSSProperties => {
    if (n == null) return {};
    return {
      color: n >= 0 ? "#d11a2a" : "#0a8f3c",
      fontWeight: 700,
    };
  };

  const pageStyle: React.CSSProperties = {
    padding: 20,
    fontFamily: "sans-serif",
    textAlign: "center",
  };

  const toolbarStyle: React.CSSProperties = {
    display: "flex",
    gap: 12,
    justifyContent: "center",
    alignItems: "center",
    flexWrap: "wrap",
    marginBottom: 20,
  };

  const inputStyle: React.CSSProperties = {
    padding: 12,
    border: "1px solid #ccc",
    borderRadius: 10,
    fontSize: 16,
    minWidth: 320,
    maxWidth: "100%",
  };

  const buttonStyle: React.CSSProperties = {
    padding: 12,
    border: "1px solid #ccc",
    borderRadius: 10,
    fontSize: 16,
    cursor: "pointer",
    background: "#111827",
    color: "white",
  };

  const miniButtonStyle: React.CSSProperties = {
    ...buttonStyle,
    padding: "8px 12px",
    fontSize: 14,
  };

  const cardStyle: React.CSSProperties = {
    marginBottom: 28,
    padding: 16,
    border: "1px solid #ddd",
    borderRadius: 14,
    background: "#f8fafc",
  };

  const tableWrapStyle: React.CSSProperties = {
    overflowX: "auto",
  };

  const tableStyle: React.CSSProperties = {
    width: "100%",
    borderCollapse: "collapse",
    background: "#fff",
  };

  const cellStyle: React.CSSProperties = {
    border: "1px solid #ddd",
    padding: 10,
    textAlign: "center",
    whiteSpace: "nowrap",
  };

  const detailGridStyle: React.CSSProperties = {
    display: "grid",
    gridTemplateColumns: "repeat(2, minmax(0, 1fr))",
    gap: 12,
    textAlign: "center",
  };

  return (
    <main style={pageStyle}>
      <h1 style={{ marginBottom: 8, fontSize: 32 }}>台股選股系統</h1>
      <p style={{ marginBottom: 20, color: "#555" }}>
        今日短線推薦、完整台股搜尋、單檔即時價
      </p>

      <div style={toolbarStyle}>
        <input
          style={inputStyle}
          placeholder="搜尋股票代號、名稱、市場、產業..."
          value={keyword}
          onChange={(e) => setKeyword(e.target.value)}
        />

        <select
          style={inputStyle}
          value={selectedIndustry}
          onChange={(e) => setSelectedIndustry(e.target.value)}
        >
          {industries.map((item) => (
            <option key={item} value={item}>
              {item}
            </option>
          ))}
        </select>

        <button
          style={buttonStyle}
          onClick={() => {
            const exact = stocks.find((s) => s.stock_code === keyword.trim());
            if (exact) fetchSingleStock(exact.stock_code);
          }}
        >
          查即時價
        </button>
      </div>

      {selectedLoading && <p>即時資料查詢中...</p>}

      {selectedStock && (
        <section style={cardStyle}>
          <h2 style={{ marginTop: 0, marginBottom: 16 }}>單檔即時資訊</h2>
          <div style={detailGridStyle}>
            <div>代號：{selectedStock.stock_code}</div>
            <div>名稱：{selectedStock.stock_name}</div>
            <div>市場：{selectedStock.market}</div>
            <div>產業：{selectedStock.industry_category}</div>
            <div style={colorStyle(selectedStock.change)}>目前價位：{selectedStock.price ?? "-"}</div>
            <div style={colorStyle(selectedStock.change)}>漲跌：{selectedStock.change ?? "-"}</div>
            <div style={colorStyle(selectedStock.change_percent)}>
              漲跌幅：{selectedStock.change_percent ?? "-"}
            </div>
            <div>開盤：{selectedStock.open ?? "-"}</div>
            <div>最高：{selectedStock.high ?? "-"}</div>
            <div>最低：{selectedStock.low ?? "-"}</div>
            <div>昨收：{selectedStock.prev_close ?? "-"}</div>
            <div>成交量：{selectedStock.volume ?? "-"}</div>
          </div>
        </section>
      )}

      {loading ? (
        <p>資料載入中...</p>
      ) : (
        <>
          <section style={cardStyle}>
            <h2 style={{ marginTop: 0, marginBottom: 16 }}>今日短線推薦</h2>
            <div style={tableWrapStyle}>
              <table style={tableStyle}>
                <thead>
                  <tr>
                    <th style={cellStyle}>代號</th>
                    <th style={cellStyle}>名稱</th>
                    <th style={cellStyle}>市場</th>
                    <th style={cellStyle}>產業</th>
                    <th style={cellStyle}>目前價位</th>
                    <th style={cellStyle}>漲跌</th>
                    <th style={cellStyle}>建議進場價</th>
                    <th style={cellStyle}>建議出場價</th>
                    <th style={cellStyle}>停損價</th>
                    <th style={cellStyle}>推薦原因</th>
                  </tr>
                </thead>
                <tbody>
                  {recommendStocks.map((s) => (
                    <tr key={s.stock_code}>
                      <td style={cellStyle}>{s.stock_code}</td>
                      <td style={cellStyle}>{s.stock_name}</td>
                      <td style={cellStyle}>{s.market}</td>
                      <td style={cellStyle}>{s.industry_category}</td>
                      <td style={{ ...cellStyle, ...colorStyle(s.change) }}>{s.price ?? "-"}</td>
                      <td style={{ ...cellStyle, ...colorStyle(s.change) }}>{s.change ?? "-"}</td>
                      <td style={{ ...cellStyle, color: "#d11a2a", fontWeight: 700 }}>{s.entry_price}</td>
                      <td style={{ ...cellStyle, color: "#d11a2a", fontWeight: 700 }}>{s.target_price}</td>
                      <td style={{ ...cellStyle, color: "#0a8f3c", fontWeight: 700 }}>{s.stop_loss}</td>
                      <td style={cellStyle}>{s.reason}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>

          <section style={cardStyle}>
            <h2 style={{ marginTop: 0, marginBottom: 16 }}>全部股票</h2>
            <p style={{ marginBottom: 12 }}>目前顯示 {filteredStocks.length} 檔</p>
            <div style={tableWrapStyle}>
              <table style={tableStyle}>
                <thead>
                  <tr>
                    <th style={cellStyle}>股票代碼</th>
                    <th style={cellStyle}>股票名稱</th>
                    <th style={cellStyle}>市場別</th>
                    <th style={cellStyle}>產業分類</th>
                    <th style={cellStyle}>目前價位</th>
                    <th style={cellStyle}>漲跌</th>
                    <th style={cellStyle}>操作</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredStocks.map((s) => (
                    <tr key={`${s.market}-${s.stock_code}`}>
                      <td style={cellStyle}>{s.stock_code}</td>
                      <td style={cellStyle}>{s.stock_name}</td>
                      <td style={cellStyle}>{s.market}</td>
                      <td style={cellStyle}>{s.industry_category}</td>
                      <td style={{ ...cellStyle, ...colorStyle(s.change) }}>{s.price}</td>
                      <td style={{ ...cellStyle, ...colorStyle(s.change) }}>{s.change}</td>
                      <td style={cellStyle}>
                        <button style={miniButtonStyle} onClick={() => fetchSingleStock(s.stock_code)}>
                          看即時價
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        </>
      )}
    </main>
  );
}