import json
import os
import threading
import time
from datetime import datetime
from typing import Any, Dict, List

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

try:
    from fubon_neo.sdk import FubonSDK, Mode
except Exception as e:
    FubonSDK = None
    Mode = None
    SDK_IMPORT_ERROR = str(e)
else:
    SDK_IMPORT_ERROR = None


app = FastAPI(title="TW Stock Realtime Screener with Fubon API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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

sdk = None
stock_ws = None
login_started = False

latest_stocks_map: Dict[str, Dict[str, Any]] = {}
latest_stocks_lock = threading.Lock()


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


def get_latest_stocks_list() -> List[Dict[str, Any]]:
    with latest_stocks_lock:
        result = []
        for symbol in WATCHLIST:
            if symbol in latest_stocks_map:
                result.append(latest_stocks_map[symbol])
        return result


def debug_print_startup() -> None:
    cert_path = update_cert_debug()
    print("=" * 60)
    print("【FUBON DEBUG】啟動檢查")
    print("目前工作目錄:", os.getcwd())
    print("Python 檔位置:", __file__)
    print("SDK 可用:", state["sdk_import_ok"])
    if not state["sdk_import_ok"]:
        print("SDK import error:", state["sdk_import_error"])
    print("憑證路徑:", cert_path)
    print("憑證存在:", state["cert_exists"])
    print("憑證大小(bytes):", state["cert_size"])
    print("FUBON_ID 有值:", bool(FUBON_ID))
    print("FUBON_PWD 有值:", bool(FUBON_PWD))
    print("FUBON_CERT_PWD 有值:", bool(FUBON_CERT_PWD))
    print("=" * 60)


def ensure_default_rows():
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
                    "update_time": now_str(),
                }


def safe_float(v, default=0.0):
    try:
        if v in ("", None):
            return default
        return float(v)
    except Exception:
        return default


def safe_int(v, default=0):
    try:
        if v in ("", None):
            return default
        return int(float(v))
    except Exception:
        return default


def update_stock_from_marketdata(item: Dict[str, Any]) -> None:
    symbol = str(item.get("symbol", "")).strip()
    if not symbol:
        return

    name = item.get("name", "") or ""
    reference_price = item.get("referencePrice", 0) or 0
    previous_close = item.get("previousClose", reference_price) or 0
    open_price = item.get("openPrice", 0) or 0
    high_price = item.get("highPrice", 0) or 0
    low_price = item.get("lowPrice", 0) or 0

    last_price = (
        item.get("lastPrice")
        or item.get("closePrice")
        or item.get("price")
        or 0
    )

    change = item.get("change", 0) or 0
    change_percent = item.get("changePercent", 0) or 0

    total = item.get("total", {}) if isinstance(item.get("total"), dict) else {}
    volume = (
        item.get("volume")
        or item.get("totalVolume")
        or item.get("tradeVolume")
        or total.get("tradeVolume")
        or 0
    )

    row = {
        "symbol": symbol,
        "name": name,
        "price": safe_float(last_price),
        "change": safe_float(change),
        "change_percent": safe_float(change_percent),
        "volume": safe_int(volume),
        "open": safe_float(open_price),
        "high": safe_float(high_price),
        "low": safe_float(low_price),
        "prev_close": safe_float(previous_close),
        "reference_price": safe_float(reference_price),
        "update_time": now_str(),
    }

    with latest_stocks_lock:
        old = latest_stocks_map.get(symbol, {})
        if old.get("name") and not row["name"]:
            row["name"] = old["name"]
        latest_stocks_map[symbol] = {**old, **row}


def handle_message(message):
    try:
        if isinstance(message, str):
            payload = json.loads(message)
        else:
            payload = message

        if not isinstance(payload, dict):
            print("未處理訊息:", payload)
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

        if event == "unsubscribed":
            print("取消訂閱:", payload)
            return

        if event == "heartbeat":
            state["last_update"] = now_str()
            return

        if event == "pong":
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

        if event in ["snapshot", "data"]:
            if isinstance(data, dict):
                update_stock_from_marketdata(data)
                state["market_status"] = "即時行情中"
                state["last_update"] = now_str()
                state["data_date"] = data.get("date", "") or state["data_date"]
            return

        print("未處理訊息:", payload)

    except Exception as e:
        print("handle_message error:", e, "raw=", message)


def handle_connect():
    state["ws_connected"] = True
    state["last_update"] = now_str()
    state["message"] = "WebSocket 已連線"
    print("market data connected")


def handle_disconnect(code, message):
    state["ws_connected"] = False
    state["last_update"] = now_str()
    state["message"] = f"WebSocket 已斷線: {code}, {message}"
    print(f"market data disconnect: {code}, {message}")


def handle_error(error):
    state["last_update"] = now_str()
    state["message"] = f"market data error: {error}"
    print(f"market data error: {error}")


def connect_realtime_and_subscribe():
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
        "symbols": WATCHLIST
    })

    state["last_update"] = now_str()
    state["message"] = "已送出 aggregates 訂閱請求"


def try_login_and_start_realtime() -> None:
    global sdk, login_started

    if login_started:
        return

    login_started = True
    debug_print_startup()
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


@app.on_event("startup")
def startup_event():
    thread = threading.Thread(target=try_login_and_start_realtime, daemon=True)
    thread.start()


@app.get("/")
def root():
    update_cert_debug()
    return {
        "message": "TW Stock Realtime Screener with Fubon API is running",
        "status": state,
        "watchlist": WATCHLIST,
    }


@app.get("/health")
def health():
    update_cert_debug()
    return {
        "ok": True,
        "time": now_str(),
        "sdk_import_ok": state["sdk_import_ok"],
        "cert_path": state["cert_path"],
        "cert_exists": state["cert_exists"],
        "cert_size": state["cert_size"],
        "ws_connected": state["ws_connected"],
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
