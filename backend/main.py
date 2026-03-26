from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import requests
import time
import re
from typing import Dict, List, Any

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Referer": "https://mis.twse.com.tw/stock/index.jsp",
}

SESSION = requests.Session()
SESSION.headers.update(HEADERS)

CACHE = {
    "list": {"time": 0, "data": []},
    "price": {"time": 0, "data": {}},
}

LIST_CACHE_TIME = 60 * 60 * 6   # 股票清單 6 小時
PRICE_CACHE_TIME = 5            # 盤中價格快取 5 秒

# 單次查詢過多代碼容易讓 URL 太長，分批抓
BATCH_SIZE = 50


def safe_float(x: Any) -> float:
    try:
        s = str(x).replace(",", "").strip()
        if s in ("", "-", "--", "X"):
            return 0.0
        return float(s)
    except Exception:
        return 0.0


def chunks(lst: List[Any], size: int):
    for i in range(0, len(lst), size):
        yield lst[i:i + size]


def fetch_stock_list() -> List[Dict[str, str]]:
    """
    抓上市股票清單。
    這裡沿用你原本的 ISIN 頁面做法。
    """
    now = time.time()
    if now - CACHE["list"]["time"] < LIST_CACHE_TIME:
        return CACHE["list"]["data"]

    url = "https://isin.twse.com.tw/isin/C_public.jsp?strMode=2"
    r = SESSION.get(url, timeout=20)
    r.encoding = "big5"

    # 只抓 4 位數股票代碼
    matches = re.findall(r'>(\d{4})　([^<]+)<', r.text)

    stocks = []
    seen = set()
    for code, name in matches:
        if code.isdigit() and code not in seen:
            seen.add(code)
            stocks.append({"symbol": code, "name": name.strip()})

    CACHE["list"]["time"] = now
    CACHE["list"]["data"] = stocks
    return stocks


def fetch_prev_close_map() -> Dict[str, float]:
    """
    當 MIS 沒提供昨收/參考價時，備援抓一次日資料。
    這不是盤中價，只拿來輔助算漲跌幅。
    """
    url = "https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL"
    try:
        r = SESSION.get(url, timeout=20)
        data = r.json()
    except Exception:
        return {}

    result = {}
    for row in data:
        code = str(row.get("Code", "")).strip()
        close_price = safe_float(row.get("ClosingPrice"))
        if code:
            result[code] = close_price
    return result


def fetch_prices() -> Dict[str, Dict[str, Any]]:
    """
    用 TWSE MIS 盤中快照抓上市股票價格。
    這裡使用的是 MIS JSON 端點，屬於實務可用做法，
    但 JSON 規格並非官方正式文件化 API。
    """
    now = time.time()
    if now - CACHE["price"]["time"] < PRICE_CACHE_TIME:
        return CACHE["price"]["data"]

    stock_list = fetch_stock_list()
    symbols = [s["symbol"] for s in stock_list]

    # 備援：當 MIS 某些欄位缺失時，用昨收補
    prev_close_map = fetch_prev_close_map()

    result: Dict[str, Dict[str, Any]] = {}

    for batch in chunks(symbols, BATCH_SIZE):
        ex_ch = "|".join([f"tse_{code}.tw" for code in batch])

        # 常見可用的 MIS JSON 端點
        url = (
            "https://mis.twse.com.tw/stock/api/getStockInfo.jsp"
            f"?ex_ch={ex_ch}&json=1&delay=0&_={int(time.time() * 1000)}"
        )

        try:
            r = SESSION.get(url, timeout=20)
            data = r.json()
            rows = data.get("msgArray", [])
        except Exception:
            rows = []

        for row in rows:
            code = str(row.get("c", "")).strip()
            if not code:
                continue

            # z = 成交價，若沒成交可能為 "-"
            price = safe_float(row.get("z"))

            # 如果 z 取不到，嘗試用最新揭示價 / 模擬價欄位
            if price <= 0:
                price = safe_float(row.get("pz")) or safe_float(row.get("o"))

            volume = safe_float(row.get("v"))     # 累積成交量
            trade_volume = safe_float(row.get("tv"))  # 單筆成交量，可不一定需要

            # y 常是昨收/參考價
            prev_close = safe_float(row.get("y"))
            if prev_close <= 0:
                prev_close = prev_close_map.get(code, 0)

            change_percent = 0.0
            if price > 0 and prev_close > 0:
                change_percent = round((price - prev_close) / prev_close * 100, 2)

            result[code] = {
                "price": round(price, 2) if price > 0 else 0,
                "change_percent": change_percent,
                "volume": int(volume) if volume > 0 else int(trade_volume),
                "prev_close": round(prev_close, 2) if prev_close > 0 else 0,
                "open": safe_float(row.get("o")),
                "high": safe_float(row.get("h")),
                "low": safe_float(row.get("l")),
                "last_update": row.get("t", ""),   # MIS 時間字串
            }

        # 避免太猛
        time.sleep(0.15)

    CACHE["price"]["time"] = now
    CACHE["price"]["data"] = result
    return result


def calc_score(change_percent: float, volume: int) -> int:
    """
    簡單評分邏輯，先沿用可視化用途。
    """
    score = 50 + change_percent * 2

    if volume > 5000000:
        score += 4
    elif volume > 1000000:
        score += 2

    return max(0, min(100, int(round(score))))


@app.get("/")
def root():
    return {
        "message": "backend running",
        "mode": "MIS 5-second snapshot (best effort)",
    }


@app.get("/health")
def health():
    return {"ok": True, "timestamp": int(time.time())}


@app.get("/stocks")
def stocks():
    stock_list = fetch_stock_list()
    price_map = fetch_prices()

    result = []
    for s in stock_list:
        p = price_map.get(s["symbol"], {})

        price = p.get("price", 0)
        change_percent = p.get("change_percent", 0)
        volume = p.get("volume", 0)

        result.append({
            "symbol": s["symbol"],
            "name": s["name"],
            "price": price,
            "change_percent": change_percent,
            "volume": volume,
            "score": calc_score(change_percent, volume),
            "prev_close": p.get("prev_close", 0),
            "open": p.get("open", 0),
            "high": p.get("high", 0),
            "low": p.get("low", 0),
            "last_update": p.get("last_update", ""),
        })

    return {
        "success": True,
        "source": "TWSE MIS snapshot",
        "cache_seconds": PRICE_CACHE_TIME,
        "count": len(result),
        "stocks": result,
    }
