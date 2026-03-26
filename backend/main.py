from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import requests
import time
import re
from typing import Dict, List, Any
from datetime import datetime
from zoneinfo import ZoneInfo

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
BATCH_SIZE = 50                 # 分批抓，避免 URL 太長


def safe_float(x: Any) -> float:
    try:
        s = str(x).replace(",", "").strip()
        if s in ("", "-", "--", "X", "除權息"):
            return 0.0
        return float(s)
    except Exception:
        return 0.0


def chunks(lst: List[Any], size: int):
    for i in range(0, len(lst), size):
        yield lst[i:i + size]


def taipei_now() -> datetime:
    return datetime.now(ZoneInfo("Asia/Taipei"))


def taipei_now_str() -> str:
    return taipei_now().strftime("%H:%M:%S")


def is_after_close() -> bool:
    now = taipei_now()
    return now.hour > 13 or (now.hour == 13 and now.minute >= 30)


def get_market_last_update(row: Dict[str, Any]) -> str:
    """
    MIS 有時候 t 會是空的，所以做 fallback。
    優先順序：
    1. t
    2. time
    3. 收盤後固定 13:30:00
    4. 後端目前台北時間
    """
    t = str(row.get("t", "")).strip()
    if t:
        return t

    alt = str(row.get("time", "")).strip()
    if alt:
        return alt

    if is_after_close():
        return "13:30:00"

    return taipei_now_str()


def fetch_stock_list() -> List[Dict[str, str]]:
    """
    抓上市股票清單
    """
    now = time.time()
    if now - CACHE["list"]["time"] < LIST_CACHE_TIME:
        return CACHE["list"]["data"]

    url = "https://isin.twse.com.tw/isin/C_public.jsp?strMode=2"
    r = SESSION.get(url, timeout=20)
    r.encoding = "big5"

    matches = re.findall(r'>(\d{4})　([^<]+)<', r.text)

    stocks = []
    seen = set()

    for code, name in matches:
        if code.isdigit() and code not in seen:
            seen.add(code)
            stocks.append({
                "symbol": code,
                "name": name.strip(),
            })

    CACHE["list"]["time"] = now
    CACHE["list"]["data"] = stocks
    return stocks


def fetch_prev_close_map() -> Dict[str, float]:
    """
    當 MIS 沒提供昨收/參考價時，用日資料補昨收
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
    用 TWSE MIS 盤中快照抓上市股票價格
    """
    now = time.time()
    if now - CACHE["price"]["time"] < PRICE_CACHE_TIME:
        return CACHE["price"]["data"]

    stock_list = fetch_stock_list()
    symbols = [s["symbol"] for s in stock_list]
    prev_close_map = fetch_prev_close_map()

    result: Dict[str, Dict[str, Any]] = {}

    for batch in chunks(symbols, BATCH_SIZE):
        ex_ch = "|".join([f"tse_{code}.tw" for code in batch])

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

            # z = 最新成交價
            price = safe_float(row.get("z"))

            # 沒成交時可能為 "-"
            if price <= 0:
                price = safe_float(row.get("pz")) or safe_float(row.get("o"))

            # 累積成交量 / 單筆成交量
            volume = safe_float(row.get("v"))
            trade_volume = safe_float(row.get("tv"))

            # 昨收 / 參考價
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
                "last_update": get_market_last_update(row),
            }

        time.sleep(0.15)

    CACHE["price"]["time"] = now
    CACHE["price"]["data"] = result
    return result


def calc_score(change_percent: float, volume: int) -> int:
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
    return {
        "ok": True,
        "timestamp": int(time.time()),
        "taipei_time": taipei_now().strftime("%Y-%m-%d %H:%M:%S"),
    }


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
            "last_update": p.get("last_update", "13:30:00" if is_after_close() else taipei_now_str()),
        })

    return {
        "success": True,
        "source": "TWSE MIS snapshot",
        "cache_seconds": PRICE_CACHE_TIME,
        "count": len(result),
        "stocks": result,
    }
