from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import List, Optional
import yfinance as yf
import pandas as pd

app = FastAPI(title="Taiwan Stock Screener API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


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


def normalize_symbol(symbol: str) -> str:
    symbol = symbol.strip().replace(".TW", "").replace(".TWO", "")
    if symbol.isdigit():
        return f"{symbol}.TW"
    return symbol


def fetch_stock_data(symbol: str):
    tw_symbol = normalize_symbol(symbol)
    ticker = yf.Ticker(tw_symbol)

    hist = ticker.history(period="3mo")
    info = {}
    try:
        info = ticker.fast_info or {}
    except Exception:
        info = {}

    if hist.empty:
        return None

    hist = hist.dropna().copy()
    if hist.empty or len(hist) < 20:
        return None

    close = hist["Close"]
    volume = hist["Volume"]

    latest_close = float(close.iloc[-1])
    prev_close = float(close.iloc[-2]) if len(close) >= 2 else None
    latest_volume = int(volume.iloc[-1]) if len(volume) >= 1 else None

    ma5 = float(close.tail(5).mean()) if len(close) >= 5 else None
    ma20 = float(close.tail(20).mean()) if len(close) >= 20 else None

    change_percent = None
    if prev_close and prev_close != 0:
        change_percent = round((latest_close - prev_close) / prev_close * 100, 2)

    stock_name = tw_symbol.replace(".TW", "").replace(".TWO", "")

    return {
        "symbol": stock_name,
        "name": stock_name,
        "price": round(latest_close, 2),
        "change_percent": change_percent,
        "volume": latest_volume,
        "ma5": round(ma5, 2) if ma5 else None,
        "ma20": round(ma20, 2) if ma20 else None,
    }


def analyze_stock(data: dict) -> StockResult:
    price = data["price"]
    ma5 = data["ma5"]
    ma20 = data["ma20"]
    volume = data["volume"]
    change_percent = data["change_percent"]

    signal = "觀察"
    reasons = []

    if price and ma5 and ma20:
        if price > ma5 > ma20:
            signal = "偏多"
            reasons.append("股價站上 MA5 與 MA20")
        elif price < ma5 < ma20:
            signal = "偏空"
            reasons.append("股價跌破 MA5 與 MA20")
        else:
            reasons.append("均線排列不明確")

    if change_percent is not None:
        if change_percent > 3:
            reasons.append("當日漲幅偏強")
            if signal == "觀察":
                signal = "偏多"
        elif change_percent < -3:
            reasons.append("當日跌幅偏弱")
            if signal == "觀察":
                signal = "偏空"
        else:
            reasons.append("當日波動中性")

    if volume is not None:
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
        try:
            stock_data = fetch_stock_data(symbol)
            if stock_data:
                analyzed = analyze_stock(stock_data)
                results.append(analyzed)
        except Exception as e:
            results.append(
                StockResult(
                    symbol=symbol,
                    name=symbol,
                    price=None,
                    change_percent=None,
                    volume=None,
                    ma5=None,
                    ma20=None,
                    signal="錯誤",
                    reason=f"抓取失敗: {str(e)}",
                )
            )

    signal_priority = {"偏多": 0, "觀察": 1, "偏空": 2, "錯誤": 3}
    results.sort(key=lambda x: signal_priority.get(x.signal, 99))

    return results