from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional, Dict, Any, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
import requests
import time
import math
import csv
import io


app = FastAPI(title="TW Stock Realtime Screener B")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ScanRequest(BaseModel):
    stocks: Optional[List[str]] = None


SESSION = requests.Session()
SESSION.headers.update(
    {
        "User-Agent": "Mozilla/5.0",
        "Referer": "https://mis.twse.com.tw/stock/",
    }
)

CACHE: Dict[str, Any] = {
    "stock_list": {"ts": 0, "data": {}},
    "history": {},
    "full_scan": {"ts": 0, "data": []},
}


def now_ts() -> float:
    return time.time()


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        if isinstance(value, str):
            value = value.replace(",", "").strip()
            if value in ("", "-", "--"):
                return default
        return float(value)
    except Exception:
        return default


def safe_int(value: Any, default: int = 0) -> int:
    try:
        if value is None:
            return default
        if isinstance(value, str):
            value = value.replace(",", "").strip()
            if value in ("", "-", "--"):
                return default
        return int(float(value))
    except Exception:
        return default


def round2(value: float) -> float:
    return round(value, 2)


def mean_last(values: List[float], count: int) -> float:
    cleaned = [v for v in values if isinstance(v, (int, float)) and v > 0]
    if len(cleaned) < count:
        return 0.0
    return round2(sum(cleaned[-count:]) / count)


def fetch_json(url: str, timeout: int = 20) -> Any:
    res = SESSION.get(url, timeout=timeout)
    res.raise_for_status()
    return res.json()


def fetch_text(url: str, timeout: int = 20, encoding: Optional[str] = None) -> str:
    res = SESSION.get(url, timeout=timeout)
    res.raise_for_status()
    if encoding:
        res.encoding = encoding
    return res.text


def get_twse_stock_list() -> Dict[str, Dict[str, str]]:
    url = "https://openapi.twse.com.tw/v1/opendata/t187ap03_L"
    data = fetch_json(url)

    result: Dict[str, Dict[str, str]] = {}

    for item in data:
        symbol = str(item.get("公司代號", "")).strip()
        name = str(item.get("公司簡稱", "")).strip()

        if symbol.isdigit() and len(symbol) == 4 and name:
            result[symbol] = {
                "name": name,
                "market": "上市",
                "source": "tse",
            }

    return result


def get_tpex_stock_list() -> Dict[str, Dict[str, str]]:
    # TPEX 公開資料 CSV
    url = "https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap03_O"
    data = fetch_json(url)

    result: Dict[str, Dict[str, str]] = {}

    for item in data:
        symbol = str(item.get("SecuritiesCompanyCode", "")).strip()
        name = str(item.get("CompanyName", "")).strip()

        if symbol.isdigit() and len(symbol) == 4 and name:
            result[symbol] = {
                "name": name,
                "market": "上櫃",
                "source": "otc",
            }

    return result


def get_all_tw_stocks() -> Dict[str, Dict[str, str]]:
    cache = CACHE["stock_list"]
    if now_ts() - cache["ts"] < 60 * 60 * 6 and cache["data"]:
        return cache["data"]

    all_map: Dict[str, Dict[str, str]] = {}
    all_map.update(get_twse_stock_list())
    all_map.update(get_tpex_stock_list())

    all_map = dict(sorted(all_map.items(), key=lambda x: x[0]))
    CACHE["stock_list"] = {"ts": now_ts(), "data": all_map}
    return all_map


def chunked(seq: List[str], size: int) -> List[List[str]]:
    return [seq[i:i + size] for i in range(0, len(seq), size)]


def build_ex_ch(symbols: List[str], stock_map: Dict[str, Dict[str, str]]) -> str:
    parts = []
    for symbol in symbols:
        meta = stock_map.get(symbol, {})
        prefix = "tse" if meta.get("source") == "tse" else "otc"
        parts.append(f"{prefix}_{symbol}.tw")
    return "|".join(parts)


def fetch_realtime_batch(symbols: List[str], stock_map: Dict[str, Dict[str, str]]) -> Dict[str, Dict[str, Any]]:
    if not symbols:
        return {}

    ex_ch = build_ex_ch(symbols, stock_map)
    url = f"https://mis.twse.com.tw/stock/api/getStockInfo.jsp?ex_ch={ex_ch}&json=1&delay=0"

    try:
        data = fetch_json(url, timeout=25)
        rows = data.get("msgArray", []) or []
    except Exception:
        return {}

    result: Dict[str, Dict[str, Any]] = {}

    for row in rows:
        symbol = str(row.get("c", "")).strip()
        if not symbol:
            continue

        price = safe_float(row.get("z"))
        if price <= 0:
            bid = safe_float(row.get("b", "").split("_")[0] if row.get("b") else 0)
            ask = safe_float(row.get("a", "").split("_")[0] if row.get("a") else 0)
            if bid > 0 and ask > 0:
                price = round2((bid + ask) / 2)
            elif bid > 0:
                price = bid
            elif ask > 0:
                price = ask

        prev_close = safe_float(row.get("y"))
        volume = safe_int(row.get("v"))
        if volume <= 0:
            volume = safe_int(row.get("tv"))

        result[symbol] = {
            "symbol": symbol,
            "name": str(row.get("n", "")).strip() or stock_map.get(symbol, {}).get("name", ""),
            "price": round2(price),
            "prev_close": round2(prev_close),
            "volume": volume,
        }

    return result


def get_recent_month_keys(month_count: int = 4) -> List[Tuple[int, int]]:
    today = datetime.today()
    year = today.year
    month = today.month

    result = []
    for i in range(month_count):
        y = year
        m = month - i
        while m <= 0:
            y -= 1
            m += 12
        result.append((y, m))
    return result


def fetch_twse_history(symbol: str) -> List[float]:
    closes: List[float] = []

    for year, month in get_recent_month_keys(4):
        date_str = f"{year}{month:02d}01"
        url = f"https://www.twse.com.tw/rwd/zh/afterTrading/STOCK_DAY?date={date_str}&stockNo={symbol}&response=json"
        try:
            data = fetch_json(url, timeout=20)
            rows = data.get("data", []) or []
            for row in rows:
                if len(row) >= 7:
                    close_price = safe_float(row[6])
                    if close_price > 0:
                        closes.append(close_price)
        except Exception:
            continue

        if len(closes) >= 25:
            break

    return closes[-25:]


def fetch_tpex_history(symbol: str) -> List[float]:
    closes: List[float] = []

    for year, month in get_recent_month_keys(4):
        roc_year = year - 1911
        date_str = f"{roc_year}/{month:02d}"
        url = f"https://www.tpex.org.tw/www/zh-tw/afterTrading/dailyQuotesHis?code={symbol}&date={date_str}&response=json"
        try:
            data = fetch_json(url, timeout=20)
            rows = data.get("tables", [])
            if rows and isinstance(rows, list):
                raw = rows[0].get("data", []) or []
            else:
                raw = data.get("aaData", []) or []

            for row in raw:
                if len(row) >= 7:
                    close_price = safe_float(row[6])
                    if close_price > 0:
                        closes.append(close_price)
        except Exception:
            continue

        if len(closes) >= 25:
            break

    return closes[-25:]


def get_history_data(symbol: str, stock_map: Dict[str, Dict[str, str]]) -> Dict[str, Any]:
    cache_key = f"history:{symbol}"
    cache = CACHE["history"].get(cache_key)

    if cache and now_ts() - cache["ts"] < 60 * 30:
        return cache["data"]

    meta = stock_map.get(symbol, {})
    source = meta.get("source")

    if source == "tse":
        closes = fetch_twse_history(symbol)
    else:
        closes = fetch_tpex_history(symbol)

    data = {
        "closes": closes,
        "ma5": mean_last(closes, 5),
        "ma20": mean_last(closes, 20),
    }

    CACHE["history"][cache_key] = {"ts": now_ts(), "data": data}
    return data


def build_signal_and_reason(price: float, change_percent: float, volume: int, ma5: float, ma20: float):
    reasons = []

    if price > 0 and ma5 > 0 and ma20 > 0:
        if price > ma5 and price > ma20:
            reasons.append("股價站上 MA5 與 MA20")
        elif price > ma5 and price <= ma20:
            reasons.append("股價站上 MA5、接近 MA20")
        elif price < ma5 and price < ma20:
            reasons.append("股價跌破 MA5 與 MA20")
        else:
            reasons.append("股價位於均線之間")

        if ma5 > ma20:
            reasons.append("短期均線強於中期均線")
        elif ma5 < ma20:
            reasons.append("短期均線弱於中期均線")

    if change_percent >= 3:
        reasons.append("當日漲幅強勢")
    elif change_percent > 0:
        reasons.append("當日走勢偏強")
    elif change_percent <= -3:
        reasons.append("當日跌幅偏大")
    elif change_percent < 0:
        reasons.append("當日走勢偏弱")

    if volume >= 10000000:
        reasons.append("成交量非常活躍")
    elif volume >= 3000000:
        reasons.append("成交量活躍")
    elif volume > 0:
        reasons.append("成交量普通")

    bullish = price > ma5 > 0 and price > ma20 > 0 and ma5 >= ma20
    breakout = change_percent >= 3 and volume >= 3000000
    bearish = price < ma5 and price < ma20 and ma5 > 0 and ma20 > 0

    if breakout:
        signal = "強勢突破"
    elif bullish:
        signal = "偏多"
    elif bearish:
        signal = "偏空"
    else:
        signal = "觀望"

    if not reasons:
        reasons.append("資料不足")

    return signal, "、".join(reasons)


def analyze_single_stock(symbol: str, realtime_item: Dict[str, Any], stock_map: Dict[str, Dict[str, str]]) -> Optional[Dict[str, Any]]:
    try:
        price = safe_float(realtime_item.get("price"))
        prev_close = safe_float(realtime_item.get("prev_close"))
        volume = safe_int(realtime_item.get("volume"))

        if price <= 0:
            return None

        history = get_history_data(symbol, stock_map)
        ma5 = safe_float(history.get("ma5"))
        ma20 = safe_float(history.get("ma20"))

        change_percent = 0.0
        if prev_close > 0:
            change_percent = round2(((price - prev_close) / prev_close) * 100)

        signal, reason = build_signal_and_reason(
            price=price,
            change_percent=change_percent,
            volume=volume,
            ma5=ma5,
            ma20=ma20,
        )

        return {
            "symbol": symbol,
            "name": realtime_item.get("name") or stock_map.get(symbol, {}).get("name", ""),
            "price": round2(price),
            "change_percent": round2(change_percent),
            "volume": volume,
            "ma5": round2(ma5),
            "ma20": round2(ma20),
            "signal": signal,
            "reason": reason,
        }
    except Exception:
        return None


@app.get("/")
def root():
    return {"message": "TW Stock Realtime Screener B API is running"}


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/scan")
def scan_stocks(req: ScanRequest):
    stock_map = get_all_tw_stocks()

    if req.stocks and len(req.stocks) > 0:
        stock_list = []
        for s in req.stocks:
            symbol = str(s).strip()
            if symbol.isdigit() and len(symbol) == 4 and symbol in stock_map:
                stock_list.append(symbol)
        stock_list = list(dict.fromkeys(stock_list))
    else:
        # 全台股掃描結果快取 60 秒，避免重複壓爆 Render
        full_cache = CACHE["full_scan"]
        if now_ts() - full_cache["ts"] < 60 and full_cache["data"]:
            return full_cache["data"]
        stock_list = list(stock_map.keys())

    if not stock_list:
        return []

    realtime_map: Dict[str, Dict[str, Any]] = {}

    batch_size = 80
    for batch in chunked(stock_list, batch_size):
        realtime_map.update(fetch_realtime_batch(batch, stock_map))

    # 沒拿到即時資料的股票先跳過
    valid_symbols = [s for s in stock_list if s in realtime_map]

    results: List[Dict[str, Any]] = []

    max_workers = 16 if len(valid_symbols) > 200 else 8

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(analyze_single_stock, symbol, realtime_map[symbol], stock_map): symbol
            for symbol in valid_symbols
        }

        for future in as_completed(futures):
            item = future.result()
            if item:
                results.append(item)

    results.sort(key=lambda x: x["symbol"])

    if not req.stocks:
        CACHE["full_scan"] = {"ts": now_ts(), "data": results}

    return results
