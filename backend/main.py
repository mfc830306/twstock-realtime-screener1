from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import requests
from datetime import datetime
from typing import List, Dict, Any

app = FastAPI(title="TW Stock Realtime Screener")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def safe_float(v, default=0.0):
    try:
        if v in [None, "", "-", "--", "----", "除權息"]:
            return default
        return float(str(v).replace(",", "").strip())
    except:
        return default


def safe_int(v, default=0):
    try:
        if v in [None, "", "-", "--", "----"]:
            return default
        return int(float(str(v).replace(",", "").strip()))
    except:
        return default


def calc_score(change_percent: float, volume: int, price: float) -> int:
    score = 50

    if change_percent > 0:
        score += min(int(change_percent * 6), 25)
    else:
        score += max(int(change_percent * 4), -20)

    if volume > 20000000:
        score += 20
    elif volume > 5000000:
        score += 12
    elif volume > 1000000:
        score += 8
    elif volume > 300000:
        score += 4

    if 10 <= price <= 300:
        score += 5

    return max(1, min(score, 99))


def get_signal(change_percent: float, volume: int) -> str:
    if change_percent >= 3 and volume >= 1000000:
        return "偏多"
    if change_percent >= 0:
        return "中性偏多"
    if change_percent <= -3 and volume >= 1000000:
        return "偏空"
    return "中性"


def build_reason(change_percent: float, volume: int) -> str:
    volume_text = "量能大" if volume >= 1000000 else "量能普通"
    if change_percent >= 3:
        return f"漲幅明顯、{volume_text}"
    if change_percent > 0:
        return f"股價偏強、{volume_text}"
    if change_percent <= -3:
        return f"跌幅較大、{volume_text}"
    return f"震盪整理、{volume_text}"


def build_entry(price: float) -> str:
    low = round(price * 0.99, 2)
    high = round(price * 1.01, 2)
    return f"{low} ~ {high}"


def build_target(price: float) -> str:
    return str(round(price * 1.05, 2))


def build_stop(price: float) -> str:
    return str(round(price * 0.97, 2))


def is_stock_symbol(symbol: str) -> bool:
    return symbol.isdigit() and len(symbol) == 4


def is_etf_symbol(symbol: str) -> bool:
    return symbol.isdigit() and 4 <= len(symbol) <= 6 and symbol.startswith("00")


def normalize_stock(
    symbol: str,
    name: str,
    price: float,
    change: float,
    volume: int,
    market: str,
    category: str,
) -> Dict[str, Any]:
    change_percent = round((change / price) * 100, 2) if price else 0.0
    score = calc_score(change_percent, volume, price)

    return {
        "market": market,
        "symbol": symbol,
        "name": name,
        "price": round(price, 2),
        "change": round(change, 2),
        "change_percent": change_percent,
        "volume": volume,
        "score": score,
        "signal": get_signal(change_percent, volume),
        "reason": build_reason(change_percent, volume),
        "entry_price": build_entry(price),
        "target_price": build_target(price),
        "stop_loss": build_stop(price),
        "category": category,
    }


def fetch_twse_stocks() -> List[Dict[str, Any]]:
    stocks = []
    url = "https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL"

    try:
        res = requests.get(url, timeout=20)
        res.raise_for_status()
        data = res.json()

        for s in data:
            symbol = str(s.get("Code", "")).strip()
            name = str(s.get("Name", "")).strip()

            if not is_stock_symbol(symbol):
                continue

            price = safe_float(s.get("ClosingPrice"))
            change = safe_float(s.get("Change"))
            volume = safe_int(s.get("TradeVolume"))

            if price <= 0:
                continue

            stocks.append(
                normalize_stock(
                    symbol=symbol,
                    name=name,
                    price=price,
                    change=change,
                    volume=volume,
                    market="上市",
                    category="stock",
                )
            )
    except Exception as e:
        print(f"TWSE stocks fetch failed: {e}")

    return stocks


def fetch_tpex_stocks() -> List[Dict[str, Any]]:
    stocks = []
    url = "https://www.tpex.org.tw/openapi/v1/tpex_mainboard_quotes"

    try:
        res = requests.get(url, timeout=20)
        res.raise_for_status()
        data = res.json()

        for s in data:
            symbol = str(s.get("SecuritiesCompanyCode", "")).strip()
            name = str(s.get("CompanyName", "")).strip()

            if not is_stock_symbol(symbol):
                continue

            price = safe_float(s.get("Close"))
            change = safe_float(s.get("Change"))
            volume = safe_int(s.get("TradingShares"))

            if price <= 0:
                continue

            stocks.append(
                normalize_stock(
                    symbol=symbol,
                    name=name,
                    price=price,
                    change=change,
                    volume=volume,
                    market="上櫃",
                    category="stock",
                )
            )
    except Exception as e:
        print(f"TPEX stocks fetch failed: {e}")

    return stocks


def fetch_twse_etfs() -> List[Dict[str, Any]]:
    etfs = []
    url = "https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL"

    try:
        res = requests.get(url, timeout=20)
        res.raise_for_status()
        data = res.json()

        for s in data:
            symbol = str(s.get("Code", "")).strip()
            name = str(s.get("Name", "")).strip()

            if not is_etf_symbol(symbol):
                continue

            price = safe_float(s.get("ClosingPrice"))
            change = safe_float(s.get("Change"))
            volume = safe_int(s.get("TradeVolume"))

            if price <= 0:
                continue

            etfs.append(
                normalize_stock(
                    symbol=symbol,
                    name=name,
                    price=price,
                    change=change,
                    volume=volume,
                    market="ETF",
                    category="etf",
                )
            )
    except Exception as e:
        print(f"TWSE ETF fetch failed: {e}")

    return etfs


@app.get("/")
def root():
    return {"message": "TW Stock Realtime Screener is running"}


@app.get("/stocks")
def get_stocks():
    twse_stocks = fetch_twse_stocks()
    tpex_stocks = fetch_tpex_stocks()
    etf_stocks = fetch_twse_etfs()

    merged = twse_stocks + tpex_stocks + etf_stocks

    seen = set()
    final_stocks = []

    for s in merged:
        key = (s["symbol"], s["category"])
        if key in seen:
            continue
        seen.add(key)
        final_stocks.append(s)

    now_str = datetime.now().strftime("%Y/%m/%d %H:%M:%S")
    data_date = datetime.now().strftime("%Y%m%d")

    return {
        "success": True,
        "market_status": "收盤資料",
        "data_date": data_date,
        "last_update": now_str,
        "total": len(final_stocks),
        "source_summary": {
            "twse_stock_count": len(twse_stocks),
            "tpex_stock_count": len(tpex_stocks),
            "etf_count": len(etf_stocks),
        },
        "stocks": final_stocks,
    }
