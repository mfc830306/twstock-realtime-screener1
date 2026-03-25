from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from typing import List, Dict, Any, Optional
import requests
import time
import math

app = FastAPI(title="TW Stock Realtime Screener B")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Accept": "application/json, text/plain, */*",
}

CACHE = {
    "listed_stocks": {"time": 0, "data": []},   # 上市
    "otc_stocks": {"time": 0, "data": []},      # 上櫃
    "twse_price": {"time": 0, "data": {}},      # 上市即時行情
    "tpex_price": {"time": 0, "data": {}},      # 上櫃即時行情
}

CACHE_SECONDS_LIST = 60 * 60 * 6     # 名單快取 6 小時
CACHE_SECONDS_PRICE = 30             # 行情快取 30 秒


# ---------------------------
# 基本工具
# ---------------------------
def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        text = str(value).replace(",", "").replace("X", "").strip()
        if text in ["", "-", "--", "---", "null", "None", "除權息", "不適用"]:
            return default
        return float(text)
    except:
        return default


def safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(round(safe_float(value, default)))
    except:
        return default


def round2(x: float) -> float:
    return round(x, 2)


def calc_score(price: float, change_percent: float, volume: int) -> int:
    score = 50

    if change_percent >= 5:
        score += 25
    elif change_percent >= 3:
        score += 18
    elif change_percent >= 1:
        score += 10
    elif change_percent <= -5:
        score -= 20
    elif change_percent <= -3:
        score -= 15
    elif change_percent <= -1:
        score -= 8

    if volume >= 50000:
        score += 15
    elif volume >= 20000:
        score += 10
    elif volume >= 5000:
        score += 5
    elif volume <= 500:
        score -= 5

    if price >= 1000:
        score += 5
    elif price >= 300:
        score += 3
    elif price <= 20:
        score -= 2

    return max(1, min(100, int(score)))


def build_signal(score: int, change_percent: float) -> str:
    if score >= 80 and change_percent > 0:
        return "偏多"
    elif score >= 65:
        return "中性偏多"
    elif score <= 35 and change_percent < 0:
        return "偏空"
    elif score <= 45:
        return "中性偏空"
    return "中性"


def build_reason(price: float, change_percent: float, volume: int) -> str:
    reasons = []

    if change_percent >= 3:
        reasons.append("漲幅強勢")
    elif change_percent >= 1:
        reasons.append("股價走強")
    elif change_percent <= -3:
        reasons.append("跌幅偏大")
    elif change_percent <= -1:
        reasons.append("股價轉弱")
    else:
        reasons.append("股價震盪")

    if volume >= 50000:
        reasons.append("量能非常活躍")
    elif volume >= 10000:
        reasons.append("量能穩定")
    elif volume > 0:
        reasons.append("量能普通")
    else:
        reasons.append("成交量不足")

    if price >= 1000:
        reasons.append("高價股")
    elif price >= 100:
        reasons.append("中高價位")
    else:
        reasons.append("低中價位")

    return "、".join(reasons)


def build_trade_plan(price: float, signal: str) -> Dict[str, str]:
    if price <= 0:
        return {
            "entry_price": "-",
            "target_price": "-",
            "stop_loss": "-"
        }

    if signal in ["偏多", "中性偏多"]:
        entry_low = round2(price * 0.99)
        entry_high = round2(price * 1.01)
        target = round2(price * 1.04)
        stop = round2(price * 0.97)
    elif signal in ["偏空", "中性偏空"]:
        entry_low = round2(price * 0.985)
        entry_high = round2(price * 0.995)
        target = round2(price * 0.97)
        stop = round2(price * 1.02)
    else:
        entry_low = round2(price * 0.99)
        entry_high = round2(price * 1.01)
        target = round2(price * 1.02)
        stop = round2(price * 0.98)

    return {
        "entry_price": f"{entry_low} ~ {entry_high}",
        "target_price": str(target),
        "stop_loss": str(stop),
    }


def build_stock_item(symbol: str, name: str, market: str, price: float, change_percent: float, volume: int) -> Dict[str, Any]:
    score = calc_score(price, change_percent, volume)
    signal = build_signal(score, change_percent)
    reason = build_reason(price, change_percent, volume)
    plan = build_trade_plan(price, signal)

    return {
        "symbol": symbol,
        "name": name,
        "market": market,
        "price": round2(price),
        "change_percent": round2(change_percent),
        "volume": volume,
        "score": score,
        "signal": signal,
        "reason": reason,
        "entry_price": plan["entry_price"],
        "target_price": plan["target_price"],
        "stop_loss": plan["stop_loss"],
    }


# ---------------------------
# 抓股票名單
# ---------------------------
def fetch_twse_listed_stocks() -> List[Dict[str, str]]:
    now = time.time()
    if now - CACHE["listed_stocks"]["time"] < CACHE_SECONDS_LIST and CACHE["listed_stocks"]["data"]:
        return CACHE["listed_stocks"]["data"]

    stocks = []

    # TWSE 上市名單 CSV
    url = "https://isin.twse.com.tw/isin/C_public.jsp?strMode=2"
    r = requests.get(url, headers=HEADERS, timeout=20)
    r.encoding = "big5"

    lines = r.text.splitlines()
    for line in lines:
        cols = [c.strip().replace('"', "") for c in line.split(",")]
        if len(cols) < 5:
            continue

        code_name = cols[0]
        market = cols[3] if len(cols) > 3 else ""

        if "　" not in code_name:
            continue

        parts = code_name.split("　")
        if len(parts) < 2:
            continue

        symbol = parts[0].strip()
        name = parts[1].strip()

        if not symbol.isdigit():
            continue

        if market != "上市":
            continue

        stocks.append({
            "symbol": symbol,
            "name": name,
            "market": "上市"
        })

    CACHE["listed_stocks"]["time"] = now
    CACHE["listed_stocks"]["data"] = stocks
    return stocks


def fetch_tpex_otc_stocks() -> List[Dict[str, str]]:
    now = time.time()
    if now - CACHE["otc_stocks"]["time"] < CACHE_SECONDS_LIST and CACHE["otc_stocks"]["data"]:
        return CACHE["otc_stocks"]["data"]

    stocks = []

    # ISIN 上櫃名單
    url = "https://isin.twse.com.tw/isin/C_public.jsp?strMode=4"
    r = requests.get(url, headers=HEADERS, timeout=20)
    r.encoding = "big5"

    lines = r.text.splitlines()
    for line in lines:
        cols = [c.strip().replace('"', "") for c in line.split(",")]
        if len(cols) < 5:
            continue

        code_name = cols[0]
        market = cols[3] if len(cols) > 3 else ""

        if "　" not in code_name:
            continue

        parts = code_name.split("　")
        if len(parts) < 2:
            continue

        symbol = parts[0].strip()
        name = parts[1].strip()

        if not symbol.isdigit():
            continue

        if market != "上櫃":
            continue

        stocks.append({
            "symbol": symbol,
            "name": name,
            "market": "上櫃"
        })

    CACHE["otc_stocks"]["time"] = now
    CACHE["otc_stocks"]["data"] = stocks
    return stocks


# ---------------------------
# 抓上市即時行情（TWSE）
# ---------------------------
def fetch_twse_prices() -> Dict[str, Dict[str, Any]]:
    now = time.time()
    if now - CACHE["twse_price"]["time"] < CACHE_SECONDS_PRICE and CACHE["twse_price"]["data"]:
        return CACHE["twse_price"]["data"]

    result = {}

    # TWSE 全部上市個股即時/日行情
    urls = [
        "https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL",
        "https://www.twse.com.tw/exchangeReport/STOCK_DAY_ALL?response=json",
    ]

    data = None
    for url in urls:
        try:
            r = requests.get(url, headers=HEADERS, timeout=30)
            r.raise_for_status()
            data = r.json()
            if isinstance(data, list) and len(data) > 0:
                break
            if isinstance(data, dict) and data.get("data"):
                break
        except:
            continue

    if data is None:
        CACHE["twse_price"]["time"] = now
        CACHE["twse_price"]["data"] = {}
        return {}

    # openapi 版本
    if isinstance(data, list):
        for row in data:
            symbol = str(row.get("Code", "")).strip()
            if not symbol.isdigit():
                continue

            price = safe_float(row.get("ClosingPrice", 0))
            change = safe_float(row.get("Change", 0))
            volume = safe_int(row.get("TradeVolume", 0))

            prev_close = price - change
            if prev_close > 0:
                change_percent = (change / prev_close) * 100
            else:
                change_percent = 0

            result[symbol] = {
                "price": price,
                "change_percent": round2(change_percent),
                "volume": volume,
            }

    # json 版本備援
    elif isinstance(data, dict) and isinstance(data.get("data"), list):
        for row in data["data"]:
            if len(row) < 7:
                continue

            symbol = str(row[0]).strip()
            if not symbol.isdigit():
                continue

            volume = safe_int(row[2], 0)
            # row[6] 常是收盤價 / 最後成交價
            price = safe_float(row[6], 0)

            # 漲跌價差欄位位置可能變動，取保守法
            change = 0.0
            if len(row) > 7:
                change = safe_float(row[7], 0)

            prev_close = price - change
            if prev_close > 0:
                change_percent = (change / prev_close) * 100
            else:
                change_percent = 0

            result[symbol] = {
                "price": price,
                "change_percent": round2(change_percent),
                "volume": volume,
            }

    CACHE["twse_price"]["time"] = now
    CACHE["twse_price"]["data"] = result
    return result


# ---------------------------
# 抓上櫃即時行情（TPEx）
# ---------------------------
def fetch_tpex_prices() -> Dict[str, Dict[str, Any]]:
    now = time.time()
    if now - CACHE["tpex_price"]["time"] < CACHE_SECONDS_PRICE and CACHE["tpex_price"]["data"]:
        return CACHE["tpex_price"]["data"]

    result = {}

    urls = [
        "https://www.tpex.org.tw/openapi/v1/tpex_mainboard_quotes",
        "https://www.tpex.org.tw/openapi/v1/tpex_esb_quotes",
    ]

    for url in urls:
        try:
            r = requests.get(url, headers=HEADERS, timeout=30)
            r.raise_for_status()
            data = r.json()

            if not isinstance(data, list):
                continue

            for row in data:
                symbol = str(
                    row.get("SecuritiesCompanyCode")
                    or row.get("股票代號")
                    or row.get("代號")
                    or ""
                ).strip()

                if not symbol.isdigit():
                    continue

                price = safe_float(
                    row.get("Close")
                    or row.get("收盤")
                    or row.get("最新成交價")
                    or row.get("成交")
                    or 0
                )

                change_percent = safe_float(
                    row.get("ChangePercent")
                    or row.get("漲跌幅")
                    or 0
                )

                volume = safe_int(
                    row.get("TradingShares")
                    or row.get("成交股數")
                    or row.get("成交量")
                    or 0
                )

                # 若沒有直接給漲跌幅，試著由漲跌推回
                if change_percent == 0:
                    change = safe_float(
                        row.get("Change")
                        or row.get("漲跌")
                        or 0
                    )
                    prev_close = price - change
                    if prev_close > 0:
                        change_percent = (change / prev_close) * 100

                result[symbol] = {
                    "price": price,
                    "change_percent": round2(change_percent),
                    "volume": volume,
                }

        except:
            continue

    CACHE["tpex_price"]["time"] = now
    CACHE["tpex_price"]["data"] = result
    return result


# ---------------------------
# 組合完整股票資料
# ---------------------------
def get_all_stocks(market: str = "全部") -> List[Dict[str, Any]]:
    stocks: List[Dict[str, Any]] = []

    if market in ["全部", "上市"]:
        listed_list = fetch_twse_listed_stocks()
        listed_prices = fetch_twse_prices()

        for item in listed_list:
            symbol = item["symbol"]
            name = item["name"]
            p = listed_prices.get(symbol, {})
            stocks.append(
                build_stock_item(
                    symbol=symbol,
                    name=name,
                    market="上市",
                    price=safe_float(p.get("price", 0)),
                    change_percent=safe_float(p.get("change_percent", 0)),
                    volume=safe_int(p.get("volume", 0)),
                )
            )

    if market in ["全部", "上櫃"]:
        otc_list = fetch_tpex_otc_stocks()
        otc_prices = fetch_tpex_prices()

        for item in otc_list:
            symbol = item["symbol"]
            name = item["name"]
            p = otc_prices.get(symbol, {})
            stocks.append(
                build_stock_item(
                    symbol=symbol,
                    name=name,
                    market="上櫃",
                    price=safe_float(p.get("price", 0)),
                    change_percent=safe_float(p.get("change_percent", 0)),
                    volume=safe_int(p.get("volume", 0)),
                )
            )

    return stocks


# ---------------------------
# API
# ---------------------------
@app.get("/")
def root():
    return {"message": "TW Stock Realtime Screener B is running"}


@app.get("/health")
def health():
    listed_count = len(fetch_twse_listed_stocks())
    otc_count = len(fetch_tpex_otc_stocks())
    twse_price_count = len(fetch_twse_prices())
    tpex_price_count = len(fetch_tpex_prices())

    return {
        "success": True,
        "message": "backend running",
        "listed_count": listed_count,
        "otc_count": otc_count,
        "twse_price_count": twse_price_count,
        "tpex_price_count": tpex_price_count,
    }


@app.get("/stocks")
def get_stocks(
    market: str = Query("全部", description="全部 / 上市 / 上櫃"),
    min_price: float = Query(0, description="最低價格"),
    max_price: float = Query(999999, description="最高價格"),
    min_score: int = Query(0, description="最低分數"),
    keyword: str = Query("", description="代號或名稱搜尋"),
    sort_by: str = Query("score", description="score / price / change_percent / volume"),
    order: str = Query("desc", description="asc / desc"),
    limit: int = Query(3000, description="最多回傳筆數"),
):
    try:
        stocks = get_all_stocks(market)

        # 篩選
        keyword = keyword.strip()
        if keyword:
            stocks = [
                s for s in stocks
                if keyword in s["symbol"] or keyword in s["name"]
            ]

        stocks = [
            s for s in stocks
            if min_price <= s["price"] <= max_price and s["score"] >= min_score
        ]

        # 排序
        valid_sort_fields = {"score", "price", "change_percent", "volume"}
        if sort_by not in valid_sort_fields:
            sort_by = "score"

        reverse = order.lower() != "asc"
        stocks.sort(key=lambda x: x.get(sort_by, 0), reverse=reverse)

        # 限制筆數
        total = len(stocks)
        stocks = stocks[:limit]

        return {
            "success": True,
            "source": "TWSE+TPEX",
            "market": market,
            "total": total,
            "stocks": stocks,
        }
    except Exception as e:
        return {
            "success": False,
            "market": market,
            "total": 0,
            "stocks": [],
            "error": str(e),
        }


@app.post("/scan")
def scan_stocks(payload: Dict[str, Any]):
    """
    前端如果傳：
    {
      "stocks": ["2330", "2317", "2454"]
    }

    或
    {
      "stocks": "2330,2317,2454"
    }
    """
    try:
        raw = payload.get("stocks", [])

        if isinstance(raw, str):
            symbols = [x.strip() for x in raw.replace("\n", ",").split(",") if x.strip()]
        elif isinstance(raw, list):
            symbols = [str(x).strip() for x in raw if str(x).strip()]
        else:
            symbols = []

        all_stocks = get_all_stocks("全部")
        stock_map = {s["symbol"]: s for s in all_stocks}

        results = [stock_map[s] for s in symbols if s in stock_map]

        # 找不到的補空資料
        found_set = {r["symbol"] for r in results}
        missing = [s for s in symbols if s not in found_set]

        for s in missing:
            results.append({
                "symbol": s,
                "name": "查無資料",
                "market": "-",
                "price": 0,
                "change_percent": 0,
                "volume": 0,
                "score": 0,
                "signal": "無資料",
                "reason": "查無該股票代號",
                "entry_price": "-",
                "target_price": "-",
                "stop_loss": "-",
            })

        results.sort(key=lambda x: x.get("score", 0), reverse=True)

        return {
            "success": True,
            "count": len(results),
            "stocks": results,
        }

    except Exception as e:
        return {
            "success": False,
            "count": 0,
            "stocks": [],
            "error": str(e),
        }
