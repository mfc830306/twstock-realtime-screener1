from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import List, Optional
import yfinance as yf
import pandas as pd

app = FastAPI(title="Taiwan Stock Screener API")

# CORS（前端可連）
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 🔥 台股中文名稱（可擴充）
STOCK_NAMES = {
    "2330": "台積電",
    "2317": "鴻海",
    "2454": "聯發科",
    "2303": "聯電",
    "2603": "長榮",
    "1301": "台塑",
    "1802": "台玻",
}

# ===== Request / Response =====

class ScanRequest(BaseModel):
    symbols: List[str] = Field(
        default=["2330", "2317", "2454", "2303", "2603", "1301", "1802"]
    )


class StockResult(BaseModel):
    symbol: str
    name: str
    price: Optional[float]
    change_percent: Optional[float]
    volume: Optional[int]
    ma5: Optional[float]
    ma20: Optional[float]
    signal: str
    reason: str


# ===== 工具 =====

def normalize_symbol(symbol: str) -> str:
    symbol = symbol.strip().replace(".TW", "").replace(".TWO", "")
    if symbol.isdigit():
        return f"{symbol}.TW"
    return symbol


# ===== 抓資料 =====

def fetch_stock_data(symbol: str):
    try:
        tw_symbol = normalize_symbol(symbol)
        ticker = yf.Ticker(tw_symbol)

        hist = ticker.history(period="3mo")

        if hist.empty:
            return None

        hist = hist.dropna().copy()
        if len(hist) < 20:
            return None

        close = hist["Close"]
        volume = hist["Volume"]

        latest_close = float(close.iloc[-1])
        prev_close = float(close.iloc[-2])
        latest_volume = int(volume.iloc[-1])

        ma5 = float(close.tail(5).mean())
        ma20 = float(close.tail(20).mean())

        change_percent = round((latest_close - prev_close) / prev_close * 100, 2)

        # 🔥 中文名稱
        stock_code = tw_symbol.replace(".TW", "").replace(".TWO", "")
        stock_name = STOCK_NAMES.get(stock_code, stock_code)

        return {
            "symbol": stock_code,
            "name": stock_name,
            "price": round(latest_close, 2),
            "change_percent": change_percent,
            "volume": latest_volume,
            "ma5": round(ma5, 2),
            "ma20": round(ma20, 2),
        }

    except Exception as e:
        return {
            "symbol": symbol,
            "name": symbol,
            "price": None,
            "change_percent": None,
            "volume": None,
            "ma5": None,
            "ma20": None,
            "error": str(e),
        }


# ===== 分析 =====

def analyze_stock(data: dict) -> StockResult:
    if "error" in data:
        return StockResult(
            symbol=data["symbol"],
            name=data["name"],
            price=None,
            change_percent=None,
            volume=None,
            ma5=None,
            ma20=None,
            signal="錯誤",
            reason=f"抓取失敗: {data['error']}",
        )

    price = data["price"]
    ma5 = data["ma5"]
    ma20 = data["ma20"]
    volume = data["volume"]
    change_percent = data["change_percent"]

    signal = "觀察"
    reasons = []

    # 均線判斷
    if price > ma5 > ma20:
        signal = "偏多"
        reasons.append("股價站上 MA5 與 MA20")
    elif price < ma5 < ma20:
        signal = "偏空"
        reasons.append("股價跌破 MA5 與 MA20")
    else:
        reasons.append("均線排列不明確")

    # 漲跌幅
    if change_percent > 3:
        reasons.append("當日漲幅偏強")
    elif change_percent < -3:
        reasons.append("當日跌幅偏弱")
    else:
        reasons.append("當日波動中性")

    # 成交量
    if volume > 3000000:
        reasons.append("成交量活躍")
    else:
        reasons.append("成交量普通")

    return StockResult(
        symbol=data["symbol"],
        name=data["name"],
        price=price,
        change_percent=change_percent,
        volume=volume,
        ma5=ma5,
        ma20=ma20,
        signal=signal,
        reason="、".join(reasons),
    )


# ===== API =====

@app.get("/")
def root():
    return {
        "message": "Taiwan Stock Screener API is running",
        "endpoints": ["/health", "/scan"],
    }


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/scan", response_model=List[StockResult])
def scan_stocks(request: ScanRequest):
    results = []

    for symbol in request.symbols:
        stock_data = fetch_stock_data(symbol)

        if stock_data:
            analyzed = analyze_stock(stock_data)
            results.append(analyzed)

    # 排序（偏多優先）
    priority = {"偏多": 0, "觀察": 1, "偏空": 2, "錯誤": 3}
    results.sort(key=lambda x: priority.get(x.signal, 99))

    return results