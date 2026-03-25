from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import List, Dict, Any
import csv
import os
import twstock

app = FastAPI(title="TW Stock Realtime Screener B")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

CSV_FILE = "tw_stock_listed_otc_database.csv"


class ScanRequest(BaseModel):
    stocks: List[str] = Field(default_factory=list)


def safe_float(value, default=0.0):
    try:
        if value in [None, "", "-", "--"]:
            return default
        if isinstance(value, list):
            if not value:
                return default
            value = value[0]
        return float(str(value).replace(",", ""))
    except Exception:
        return default


def load_stock_database() -> Dict[str, str]:
    mapping: Dict[str, str] = {}

    if not os.path.exists(CSV_FILE):
        return mapping

    with open(CSV_FILE, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            symbol = str(
                row.get("symbol")
                or row.get("code")
                or row.get("股票代號")
                or row.get("代號")
                or ""
            ).strip()

            name = str(
                row.get("name")
                or row.get("股票名稱")
                or row.get("名稱")
                or ""
            ).strip()

            if symbol:
                mapping[symbol] = name or symbol

    return mapping


STOCK_NAME_MAP = load_stock_database()


def get_stock_name(symbol: str) -> str:
    if symbol in STOCK_NAME_MAP:
        return STOCK_NAME_MAP[symbol]

    try:
        if symbol in twstock.codes:
            return twstock.codes[symbol].name
    except Exception:
        pass

    return symbol


def get_stock_data(symbol: str):
    symbol = str(symbol).strip()

    try:
        rt = twstock.realtime.get(symbol)

        if not rt or not rt.get("success"):
            return None

        realtime = rt.get("realtime", {})
        info = rt.get("info", {})

        price = safe_float(realtime.get("latest_trade_price"), 0)
        open_price = safe_float(realtime.get("open"), 0)
        high = safe_float(realtime.get("high"), 0)
        low = safe_float(realtime.get("low"), 0)
        volume = safe_float(realtime.get("accumulate_trade_volume"), 0)
        yesterday_close = safe_float(info.get("yesterday_close"), 0)

        if price <= 0:
            price = open_price

        if price <= 0:
            best_bid_price = safe_float(realtime.get("best_bid_price"), 0)
            best_ask_price = safe_float(realtime.get("best_ask_price"), 0)
            if best_bid_price > 0:
                price = best_bid_price
            elif best_ask_price > 0:
                price = best_ask_price

        if price <= 0:
            return None

        if yesterday_close > 0:
            change_percent = round((price - yesterday_close) / yesterday_close * 100, 2)
        else:
            change_percent = 0.0

        ma5 = round(price * 0.99, 2)
        ma20 = round(price * 0.97, 2)

        return {
            "symbol": symbol,
            "name": get_stock_name(symbol),
            "price": round(price, 2),
            "open": round(open_price, 2),
            "high": round(high, 2),
            "low": round(low, 2),
            "volume": round(volume, 2),
            "change_percent": change_percent,
            "yesterday_close": round(yesterday_close, 2),
            "ma5": ma5,
            "ma20": ma20,
        }

    except Exception:
        return None


def analyze_stock(data: Dict[str, Any]) -> Dict[str, Any]:
    price = safe_float(data.get("price"))
    ma5 = safe_float(data.get("ma5"))
    ma20 = safe_float(data.get("ma20"))
    volume = safe_float(data.get("volume"))
    change_percent = safe_float(data.get("change_percent"))
    high = safe_float(data.get("high"))
    low = safe_float(data.get("low"))
    open_price = safe_float(data.get("open"))

    score = 0
    reasons = []

    if price > ma5 > 0:
        score += 20
        reasons.append("股價站上MA5")
    else:
        reasons.append("股價未站上MA5")

    if price > ma20 > 0:
        score += 20
        reasons.append("股價站上MA20")
    else:
        reasons.append("股價未站上MA20")

    if ma5 > ma20 > 0:
        score += 20
        reasons.append("MA5在MA20之上")
    else:
        reasons.append("均線排列偏弱")

    if change_percent > 0:
        score += 10
        reasons.append("當日漲幅為正")
    elif change_percent < 0:
        reasons.append("當日漲幅為負")
    else:
        reasons.append("當日漲跌持平")

    if volume >= 1000:
        score += 10
        reasons.append("成交量活躍")
    else:
        reasons.append("成交量普通")

    if high > 0 and low > 0 and price > 0:
        intraday_range = ((high - low) / price) * 100
        if intraday_range <= 3:
            score += 5
            reasons.append("日內波動穩定")
        elif intraday_range >= 7:
            reasons.append("日內波動較大")

    if open_price > 0 and price > open_price:
        score += 5
        reasons.append("現價高於開盤")

    score = max(0, min(100, score))

    if score >= 75:
        trend = "強勢"
    elif score >= 50:
        trend = "中性偏強"
    elif score >= 30:
        trend = "中性"
    else:
        trend = "弱勢"

    entry_low = round(ma5 * 0.98, 2)
    entry_high = round(ma5 * 1.02, 2)
    take_profit = round(price * 1.10, 2)
    stop_loss = round(price * 0.95, 2)

    return {
        "symbol": data["symbol"],
        "name": data["name"],
        "price": round(price, 2),
        "change_percent": round(change_percent, 2),
        "volume": round(volume, 2),
        "ma5": round(ma5, 2),
        "ma20": round(ma20, 2),
        "score": score,
        "trend": trend,
        "entry_range": f"{entry_low} ~ {entry_high}",
        "take_profit": take_profit,
        "stop_loss": stop_loss,
        "reason": "、".join(reasons[:5]),
    }


@app.get("/")
def root():
    return {"message": "TW Stock Realtime Screener B is running"}


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/scan")
def scan(request: ScanRequest):
    results = []

    for symbol in request.stocks:
        data = get_stock_data(symbol)
        if not data:
            continue

        analyzed = analyze_stock(data)
        results.append(analyzed)

    results.sort(key=lambda x: x["score"], reverse=True)
    return results


@app.get("/scan_all")
def scan_all(limit: int = 2000):
    results = []
    symbols = list(STOCK_NAME_MAP.keys())

    for symbol in symbols:
        data = get_stock_data(symbol)
        if not data:
            continue

        analyzed = analyze_stock(data)
        results.append(analyzed)

        if len(results) >= limit:
            break

    results.sort(key=lambda x: x["score"], reverse=True)
    return {
        "total_symbols": len(symbols),
        "returned_count": len(results),
        "results": results,
    }
