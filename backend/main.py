import json
import os
import re
import threading
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

import requests
from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware

try:
    from fubon_neo.sdk import FubonSDK, Mode
except Exception as e:
    FubonSDK = None
    Mode = None
    SDK_IMPORT_ERROR = str(e)
else:
    SDK_IMPORT_ERROR = None


app = FastAPI(title="TW Stock Realtime Screener")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# =========================
# 基本設定
# =========================
WATCHLIST = ["2330", "2317", "2454", "1301", "1802"]

FUBON_ID = os.getenv("FUBON_ID", "").strip()
FUBON_PWD = os.getenv("FUBON_PWD", "").strip()
FUBON_CERT_PWD = os.getenv("FUBON_CERT_PWD", "").strip()

CERT_CANDIDATES = [
    "certs/API_20270327.p12",
    "backend/certs/API_20270327.p12",
    "./certs/API_20270327.p12",
    "./backend/certs/API_20270327.p12",
]

# 官方市場資料
TWSE_URL = "https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL"
TPEX_URL = "https://www.tpex.org.tw/openapi/v1/tpex_mainboard_daily_close_quotes"

MARKET_REFRESH_SECONDS = 300  # 5 分鐘
REQ_TIMEOUT = 20

# =========================
# 全域狀態
# =========================
state: Dict[str, Any] = {
    "success": False,
    "market_status": "初始化中",
    "data_date": "",
    "last_update": "",
    "message": "尚未啟動",
    "subscribed": [],
    "channel_ids": [],
    "cert_path": "",
    "cert_exists": False,
    "cert_size": 0,
    "sdk_import_ok": FubonSDK is not None,
    "sdk_import_error": SDK_IMPORT_ERROR,
    "ws_connected": False,
}

market_cache: Dict[str, Any] = {
    "success": False,
    "data_date": "",
    "last_update": "",
    "market_status": "初始化中",
    "message": "尚未載入市場資料",
    "total": 0,
    "source_summary": {
        "twse_count": 0,
        "tpex_count": 0,
    },
    "stocks": [],
}
market_lock = threading.Lock()

latest_stocks_map: Dict[str, Dict[str, Any]] = {}
latest_stocks_lock = threading.Lock()

sdk = None
stock_ws = None
realtime_started = False
market_started = False


# =========================
# 工具函式
# =========================
def now_str() -> str:
    return datetime.now().strftime("%Y/%m/%d %H:%M:%S")


def resolve_cert_path() -> str:
    for path in CERT_CANDIDATES:
        if os.path.exists(path):
            return path
    return CERT_CANDIDATES[0]


def update_cert_debug() -> str:
    cert_path = resolve_cert_path()
    state["cert_path"] = cert_path
    state["cert_exists"] = os.path.exists(cert_path)
    state["cert_size"] = os.path.getsize(cert_path) if os.path.exists(cert_path) else 0
    return cert_path


def safe_float(v: Any, default: float = 0.0) -> float:
    try:
        if v in ("", None, "--", "-", "除權息", "null"):
            return default
        if isinstance(v, (int, float)):
            return float(v)

        s = str(v).strip()
        s = s.replace(",", "")
        s = s.replace("X", "")
        s = s.replace("＋", "+").replace("－", "-")
        m = re.search(r"[-+]?\d+(?:\.\d+)?", s)
        return float(m.group()) if m else default
    except Exception:
        return default


def safe_int(v: Any, default: int = 0) -> int:
    try:
        if v in ("", None, "--", "-", "null"):
            return default
        if isinstance(v, int):
            return v
        if isinstance(v, float):
            return int(v)
        s = str(v).strip().replace(",", "")
        m = re.search(r"[-+]?\d+(?:\.\d+)?", s)
        return int(float(m.group())) if m else default
    except Exception:
        return default


def pick(record: Dict[str, Any], keys: List[str], default: Any = None) -> Any:
    for key in keys:
        if key in record and record[key] not in ("", None):
            return record[key]
    return default


def normalize_symbol(v: Any) -> str:
    s = str(v or "").strip().replace(" ", "")
    return s


def calc_score(price: float, change_percent: float, volume: int, open_price: float, high: float, low: float) -> float:
    score = 50.0

    if change_percent > 0:
        score += min(change_percent * 6, 20)
    else:
        score += max(change_percent * 4, -15)

    if volume > 50000:
        score += 15
    elif volume > 20000:
        score += 10
    elif volume > 5000:
        score += 5

    if price > 0 and high > low:
        if price >= (low + (high - low) * 0.7):
            score += 8
        elif price <= (low + (high - low) * 0.3):
            score -= 6

    if open_price > 0 and price > open_price:
        score += 4
    elif open_price > 0 and price < open_price:
        score -= 3

    return max(0, min(round(score, 2), 100))


def calc_signal(score: float, change_percent: float) -> str:
    if score >= 75 and change_percent >= 0:
        return "偏多"
    if score <= 35 and change_percent < 0:
        return "偏空"
    return "中性"


def fmt_price(v: float) -> str:
    if v >= 100:
        return f"{v:.1f}".rstrip("0").rstrip(".")
    if v >= 10:
        return f"{v:.2f}".rstrip("0").rstrip(".")
    return f"{v:.2f}".rstrip("0").rstrip(".")


def calc_trade_plan(price: float, signal: str) -> Dict[str, str]:
    if price <= 0:
        return {"entry_price": "-", "target_price": "-", "stop_loss": "-"}

    if signal == "偏多":
        entry_low = price * 0.99
        entry_high = price * 1.01
        target = price * 1.05
        stop = price * 0.96
    elif signal == "偏空":
        entry_low = price * 0.99
        entry_high = price * 1.00
        target = price * 0.95
        stop = price * 1.03
    else:
        entry_low = price * 0.995
        entry_high = price * 1.005
        target = price * 1.03
        stop = price * 0.97

    return {
        "entry_price": f"{fmt_price(entry_low)} ~ {fmt_price(entry_high)}",
        "target_price": fmt_price(target),
        "stop_loss": fmt_price(stop),
    }


def parse_market_row(record: Dict[str, Any], market_name: str) -> Optional[Dict[str, Any]]:
    symbol = normalize_symbol(
        pick(record, ["Code", "SecuritiesCompanyCode", "股票代號", "代號", "證券代號"], "")
    )
    name = str(
        pick(record, ["Name", "CompanyName", "股票名稱", "名稱", "證券名稱"], "")
    ).strip()

    if not symbol or not name:
        return None

    price = safe_float(
        pick(record, ["ClosingPrice", "Close", "收盤價", "ClosePrice", "close", "成交收盤"])
    )
    open_price = safe_float(
        pick(record, ["OpeningPrice", "Open", "開盤價", "OpenPrice", "open"])
    )
    high_price = safe_float(
        pick(record, ["HighestPrice", "High", "最高價", "HighPrice", "high"])
    )
    low_price = safe_float(
        pick(record, ["LowestPrice", "Low", "最低價", "LowPrice", "low"])
    )
    change = safe_float(
        pick(record, ["Change", "漲跌價差", "漲跌", "PriceChange", "change"])
    )
    volume = safe_int(
        pick(record, ["TradeVolume", "成交股數", "Volume", "成交量", "tradeVolume"])
    )

    if price <= 0:
        return None

    prev_close = price - change
    if prev_close <= 0:
        prev_close = price

    change_percent = round((change / prev_close) * 100, 2) if prev_close else 0.0
    score = calc_score(price, change_percent, volume, open_price, high_price, low_price)
    signal = calc_signal(score, change_percent)
    trade_plan = calc_trade_plan(price, signal)

    return {
        "market": market_name,
        "symbol": symbol,
        "name": name,
        "price": round(price, 2),
        "change": round(change, 2),
        "change_percent": round(change_percent, 2),
        "volume": volume,
        "score": score,
        "signal": signal,
        "open": round(open_price, 2),
        "high": round(high_price, 2),
        "low": round(low_price, 2),
        "prev_close": round(prev_close, 2),
        "update_time": now_str(),
        **trade_plan,
    }


def fetch_json(url: str) -> List[Dict[str, Any]]:
    res = requests.get(url, timeout=REQ_TIMEOUT)
    res.raise_for_status()
    data = res.json()
    if isinstance(data, list):
        return data
    return []


def refresh_market_cache_once() -> None:
    twse_rows: List[Dict[str, Any]] = []
    tpex_rows: List[Dict[str, Any]] = []
    stocks: List[Dict[str, Any]] = []

    try:
        twse_data = fetch_json(TWSE_URL)
        for row in twse_data:
            parsed = parse_market_row(row, "上市")
            if parsed:
                twse_rows.append(parsed)

        tpex_data = fetch_json(TPEX_URL)
        for row in tpex_data:
            parsed = parse_market_row(row, "上櫃")
            if parsed:
                tpex_rows.append(parsed)

        stocks = twse_rows + tpex_rows
        stocks.sort(key=lambda x: (x["score"], x["change_percent"], x["volume"]), reverse=True)

        with market_lock:
            market_cache["success"] = True
            market_cache["data_date"] = datetime.now().strftime("%Y%m%d")
            market_cache["last_update"] = now_str()
            market_cache["market_status"] = "已更新"
            market_cache["message"] = "市場資料更新成功"
            market_cache["total"] = len(stocks)
            market_cache["source_summary"] = {
                "twse_count": len(twse_rows),
                "tpex_count": len(tpex_rows),
            }
            market_cache["stocks"] = stocks

        print(f"市場資料更新完成：TWSE={len(twse_rows)}, TPEX={len(tpex_rows)}, TOTAL={len(stocks)}")

    except Exception as e:
        with market_lock:
            market_cache["success"] = False
            market_cache["last_update"] = now_str()
            market_cache["market_status"] = "更新失敗"
            market_cache["message"] = f"市場資料更新失敗: {e}"
        print(market_cache["message"])


def market_refresh_loop() -> None:
    global market_started
    if market_started:
        return
    market_started = True

    while True:
        refresh_market_cache_once()
        time.sleep(MARKET_REFRESH_SECONDS)


def ensure_default_rows() -> None:
    with latest_stocks_lock:
        for symbol in WATCHLIST:
            if symbol not in latest_stocks_map:
                latest_stocks_map[symbol] = {
                    "symbol": symbol,
                    "name": "",
                    "price": 0,
                    "change": 0,
                    "change_percent": 0,
                    "volume": 0,
                    "open": 0,
                    "high": 0,
                    "low": 0,
                    "prev_close": 0,
                    "reference_price": 0,
                    "score": 0,
                    "signal": "中性",
                    "entry_price": "-",
                    "target_price": "-",
                    "stop_loss": "-",
                    "update_time": now_str(),
                }


def get_latest_stocks_list() -> List[Dict[str, Any]]:
    with latest_stocks_lock:
        result = []
        for symbol in WATCHLIST:
            if symbol in latest_stocks_map:
                result.append(latest_stocks_map[symbol])
        return result


def update_stock_from_marketdata(item: Dict[str, Any]) -> None:
    symbol = str(item.get("symbol", "")).strip()
    if not symbol:
        return

    name = item.get("name", "") or ""
    reference_price = safe_float(item.get("referencePrice", 0))
    previous_close = safe_float(item.get("previousClose", reference_price))
    open_price = safe_float(item.get("openPrice", 0))
    high_price = safe_float(item.get("highPrice", 0))
    low_price = safe_float(item.get("lowPrice", 0))

    last_price = safe_float(
        item.get("lastPrice") or item.get("closePrice") or item.get("price") or 0
    )
    change = safe_float(item.get("change", 0))
    change_percent = safe_float(item.get("changePercent", 0))

    total = item.get("total", {}) if isinstance(item.get("total"), dict) else {}
    volume = safe_int(
        item.get("volume")
        or item.get("totalVolume")
        or item.get("tradeVolume")
        or total.get("tradeVolume")
        or 0
    )

    score = calc_score(last_price, change_percent, volume, open_price, high_price, low_price)
    signal = calc_signal(score, change_percent)
    trade_plan = calc_trade_plan(last_price, signal)

    row = {
        "symbol": symbol,
        "name": name,
        "price": round(last_price, 2),
        "change": round(change, 2),
        "change_percent": round(change_percent, 2),
        "volume": volume,
        "open": round(open_price, 2),
        "high": round(high_price, 2),
        "low": round(low_price, 2),
        "prev_close": round(previous_close, 2),
        "reference_price": round(reference_price, 2),
        "score": score,
        "signal": signal,
        "update_time": now_str(),
        **trade_plan,
    }

    with latest_stocks_lock:
        old = latest_stocks_map.get(symbol, {})
        if old.get("name") and not row["name"]:
            row["name"] = old["name"]
        latest_stocks_map[symbol] = {**old, **row}


def handle_message(message: Any) -> None:
    try:
        payload = json.loads(message) if isinstance(message, str) else message
        if not isinstance(payload, dict):
            return

        event = payload.get("event")
        data = payload.get("data")

        if event == "subscribed":
            if isinstance(data, list):
                for item in data:
                    if not isinstance(item, dict):
                        continue
                    sub_id = item.get("id")
                    symbol = item.get("symbol")
                    if sub_id and sub_id not in state["channel_ids"]:
                        state["channel_ids"].append(sub_id)
                    if symbol and symbol not in state["subscribed"]:
                        state["subscribed"].append(symbol)
            elif isinstance(data, dict):
                sub_id = data.get("id")
                symbol = data.get("symbol")
                if sub_id and sub_id not in state["channel_ids"]:
                    state["channel_ids"].append(sub_id)
                if symbol and symbol not in state["subscribed"]:
                    state["subscribed"].append(symbol)

            state["last_update"] = now_str()
            state["message"] = f"已訂閱 {len(state['subscribed'])} 檔股票"
            print("訂閱成功:", payload)
            return

        if event in ("pong", "heartbeat"):
            state["last_update"] = now_str()
            return

        if event == "authenticated":
            state["ws_connected"] = True
            state["last_update"] = now_str()
            state["message"] = "WebSocket 驗證成功"
            print("WebSocket authenticated")
            return

        if event == "error":
            state["last_update"] = now_str()
            state["message"] = f"WebSocket error: {data}"
            print("WebSocket error:", payload)
            return

        if event in ("snapshot", "data"):
            if isinstance(data, dict):
                update_stock_from_marketdata(data)
                state["market_status"] = "即時行情中"
                state["last_update"] = now_str()
                state["data_date"] = data.get("date", "") or state["data_date"]
            return

    except Exception as e:
        print("handle_message error:", e, "raw=", message)


def handle_connect() -> None:
    state["ws_connected"] = True
    state["last_update"] = now_str()
    state["message"] = "WebSocket 已連線"
    print("market data connected")


def handle_disconnect(code: Any, message: Any) -> None:
    state["ws_connected"] = False
    state["last_update"] = now_str()
    state["message"] = f"WebSocket 已斷線: {code}, {message}"
    print(f"market data disconnect: {code}, {message}")


def handle_error(error: Any) -> None:
    state["last_update"] = now_str()
    state["message"] = f"market data error: {error}"
    print(f"market data error: {error}")


def connect_realtime_and_subscribe() -> None:
    global stock_ws

    sdk.init_realtime(Mode.Normal)
    stock_ws = sdk.marketdata.websocket_client.stock

    stock_ws.on("message", handle_message)
    stock_ws.on("connect", handle_connect)
    stock_ws.on("disconnect", handle_disconnect)
    stock_ws.on("error", handle_error)

    print("準備連接 WebSocket...")
    stock_ws.connect()
    time.sleep(2)

    print("準備訂閱 aggregates:", WATCHLIST)
    stock_ws.subscribe({
        "channel": "aggregates",
        "symbols": WATCHLIST,
    })

    state["last_update"] = now_str()
    state["message"] = "已送出 aggregates 訂閱請求"


def realtime_loop() -> None:
    global sdk, realtime_started

    if realtime_started:
        return
    realtime_started = True

    update_cert_debug()
    ensure_default_rows()

    while True:
        try:
            cert_path = update_cert_debug()
            state["last_update"] = now_str()

            if FubonSDK is None:
                state["success"] = False
                state["market_status"] = "初始化失敗"
                state["message"] = f"FubonSDK 匯入失敗: {state['sdk_import_error']}"
                print(state["message"])
                time.sleep(10)
                continue

            if not FUBON_ID or not FUBON_PWD or not FUBON_CERT_PWD:
                state["success"] = False
                state["market_status"] = "等待設定"
                state["message"] = "缺少環境變數：FUBON_ID / FUBON_PWD / FUBON_CERT_PWD"
                print(state["message"])
                time.sleep(10)
                continue

            if not os.path.exists(cert_path):
                state["success"] = False
                state["market_status"] = "初始化中"
                state["message"] = f"憑證不存在: {cert_path}"
                print(state["message"])
                time.sleep(10)
                continue

            if os.path.getsize(cert_path) <= 0:
                state["success"] = False
                state["market_status"] = "初始化中"
                state["message"] = f"憑證檔為空: {cert_path}"
                print(state["message"])
                time.sleep(10)
                continue

            print("準備登入富邦...")
            sdk = FubonSDK()
            result = sdk.login(FUBON_ID, FUBON_PWD, cert_path, FUBON_CERT_PWD)

            is_success = getattr(result, "is_success", False)
            message = getattr(result, "message", None)
            if not is_success:
                raise Exception(f"login failed: {message}")

            state["success"] = True
            state["market_status"] = "已登入"
            state["message"] = "富邦登入成功，準備建立即時行情"
            state["last_update"] = now_str()
            print(state["message"])

            connect_realtime_and_subscribe()
            break

        except Exception as e:
            state["success"] = False
            state["ws_connected"] = False
            state["market_status"] = "初始化中"
            state["message"] = f"富邦連線失敗，10 秒後重試: {str(e)}"
            state["last_update"] = now_str()
            print(state["message"])
            time.sleep(10)


def filter_by_category(stocks: List[Dict[str, Any]], category: str) -> List[Dict[str, Any]]:
    if category == "all":
        return stocks

    ranges = {
        "0-10": (0, 10),
        "10-20": (10, 20),
        "20-50": (20, 50),
        "50-100": (50, 100),
        "100-200": (100, 200),
        "200-500": (200, 500),
        "500-1000": (500, 1000),
        "1000+": (1000, float("inf")),
    }

    if category not in ranges:
        return stocks

    low, high = ranges[category]
    if category == "1000+":
        return [s for s in stocks if s["price"] >= low]
    return [s for s in stocks if low <= s["price"] < high]


def sort_stocks(stocks: List[Dict[str, Any]], sort_by: str) -> List[Dict[str, Any]]:
    if sort_by == "up":
        return sorted(stocks, key=lambda x: (x["change_percent"], x["score"], x["volume"]), reverse=True)
    if sort_by == "down":
        return sorted(stocks, key=lambda x: (x["change_percent"], -x["score"]), reverse=False)
    if sort_by == "volume":
        return sorted(stocks, key=lambda x: (x["volume"], x["score"]), reverse=True)
    return sorted(stocks, key=lambda x: (x["score"], x["change_percent"], x["volume"]), reverse=True)


@app.on_event("startup")
def startup_event():
    threading.Thread(target=realtime_loop, daemon=True).start()
    threading.Thread(target=market_refresh_loop, daemon=True).start()


@app.get("/")
def root():
    update_cert_debug()
    with market_lock:
        summary = market_cache["source_summary"]

    return {
        "message": "TW Stock Realtime Screener is running",
        "realtime_status": state,
        "market_summary": summary,
        "watchlist": WATCHLIST,
    }


@app.get("/health")
def health():
    update_cert_debug()
    with market_lock:
        market_total = market_cache["total"]
        market_last_update = market_cache["last_update"]

    return {
        "ok": True,
        "time": now_str(),
        "sdk_import_ok": state["sdk_import_ok"],
        "cert_path": state["cert_path"],
        "cert_exists": state["cert_exists"],
        "cert_size": state["cert_size"],
        "ws_connected": state["ws_connected"],
        "market_total": market_total,
        "market_last_update": market_last_update,
    }


@app.get("/status")
def get_status():
    update_cert_debug()
    return state


@app.get("/stocks")
def get_stocks():
    update_cert_debug()
    stocks = get_latest_stocks_list()
    return {
        "success": state["success"],
        "market_status": state["market_status"],
        "data_date": state["data_date"],
        "last_update": state["last_update"],
        "message": state["message"],
        "total": len(stocks),
        "stocks": stocks,
        "watchlist": WATCHLIST,
        "cert_debug": {
            "cert_path": state["cert_path"],
            "cert_exists": state["cert_exists"],
            "cert_size": state["cert_size"],
        },
        "ws_connected": state["ws_connected"],
        "channel_ids": state["channel_ids"],
    }


@app.get("/market")
def get_market(
    q: str = Query(default=""),
    category: str = Query(default="all"),
    sort_by: str = Query(default="score"),
    limit: int = Query(default=5000, ge=1, le=10000),
):
    with market_lock:
        stocks = list(market_cache["stocks"])
        meta = {
            "success": market_cache["success"],
            "data_date": market_cache["data_date"],
            "last_update": market_cache["last_update"],
            "market_status": market_cache["market_status"],
            "message": market_cache["message"],
            "source_summary": market_cache["source_summary"],
            "total_before_filter": market_cache["total"],
        }

    q = q.strip().lower()
    if q:
        stocks = [
            s for s in stocks
            if q in s["symbol"].lower() or q in s["name"].lower()
        ]

    stocks = filter_by_category(stocks, category)
    stocks = sort_stocks(stocks, sort_by)
    stocks = stocks[:limit]

    return {
        **meta,
        "query": q,
        "category": category,
        "sort_by": sort_by,
        "total": len(stocks),
        "stocks": stocks,
    }


@app.get("/recommended")
def get_recommended(limit: int = Query(default=10, ge=1, le=50)):
    with market_lock:
        stocks = list(market_cache["stocks"])

    stocks = sort_stocks(stocks, "score")[:limit]
    return {
        "success": True,
        "last_update": market_cache["last_update"],
        "total": len(stocks),
        "stocks": stocks,
    }
