from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from threading import Thread, Lock
from datetime import datetime
import json
import os
import time
from typing import Any, Dict, List

from fubon_neo.sdk import FubonSDK, Mode

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# =========================
# 環境變數
# =========================
FUBON_ID = os.getenv("FUBON_ID", "").strip()
FUBON_PWD = os.getenv("FUBON_PWD", "").strip()
FUBON_CERT_PATH = os.getenv("FUBON_CERT_PATH", "").strip()
FUBON_CERT_PWD = os.getenv("FUBON_CERT_PWD", "").strip()

# 先不要一開始就訂閱全市場，先用自選測穩定
WATCHLIST = [
    s.strip()
    for s in os.getenv("WATCHLIST", "2330,2317,2454,1301,1802").split(",")
    if s.strip()
]

# 可選：前端要顯示幾筆推薦
TOP_LIMIT = int(os.getenv("TOP_LIMIT", "300"))

# =========================
# 全域狀態
# =========================
sdk = None
stock_ws = None

cache_lock = Lock()
stocks_cache: Dict[str, Dict[str, Any]] = {}

system_status = {
    "success": False,
    "market_status": "初始化中",
    "data_date": "",
    "last_update": "",
    "message": "系統啟動中",
    "subscribed": [],
}


# =========================
# 工具函式
# =========================
def now_str() -> str:
    return datetime.now().strftime("%Y/%m/%d %H:%M:%S")


def today_str() -> str:
    return datetime.now().strftime("%Y%m%d")


def to_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except Exception:
        return default


def to_int(value: Any, default: int = 0) -> int:
    try:
        if value is None or value == "":
            return default
        return int(float(value))
    except Exception:
        return default


def calc_score(price: float, change_percent: float, volume: int) -> int:
    score = 50

    if change_percent >= 7:
        score += 28
    elif change_percent >= 5:
        score += 22
    elif change_percent >= 3:
        score += 16
    elif change_percent >= 1:
        score += 8
    elif change_percent <= -5:
        score -= 12
    elif change_percent <= -3:
        score -= 8

    if volume >= 100000:
        score += 18
    elif volume >= 50000:
        score += 12
    elif volume >= 10000:
        score += 8
    elif volume >= 3000:
        score += 4

    if price >= 1000:
        score += 4
    elif price >= 300:
        score += 2

    return max(0, min(100, round(score)))


def calc_signal(change_percent: float, price: float, open_price: float) -> str:
    if price <= 0:
        return "中性"

    if change_percent >= 3 and price >= open_price:
        return "偏多"
    if change_percent <= -3 and (open_price == 0 or price <= open_price):
        return "偏空"
    return "中性"


def calc_reason(change_percent: float, volume: int, price: float, open_price: float) -> str:
    reasons: List[str] = []

    if change_percent >= 3:
        reasons.append("漲幅強勢")
    elif change_percent >= 1:
        reasons.append("股價偏強")
    elif change_percent <= -3:
        reasons.append("走勢偏弱")
    else:
        reasons.append("區間震盪")

    if volume >= 50000:
        reasons.append("量能明顯放大")
    elif volume >= 10000:
        reasons.append("成交量活躍")
    else:
        reasons.append("量能一般")

    if open_price > 0:
        if price > open_price:
            reasons.append("現價站上開盤價")
        elif price < open_price:
            reasons.append("現價低於開盤價")

    return "、".join(reasons)


def calc_entry_target_stop(price: float, change_percent: float) -> tuple[str, str, str]:
    if price <= 0:
        return "-", "-", "-"

    entry_low = round(price * 0.99, 2)
    entry_high = round(price * 1.01, 2)

    if change_percent >= 3:
        target = round(price * 1.05, 2)
        stop_loss = round(price * 0.97, 2)
    elif change_percent >= 0:
        target = round(price * 1.03, 2)
        stop_loss = round(price * 0.97, 2)
    else:
        target = round(price * 1.02, 2)
        stop_loss = round(price * 0.96, 2)

    return f"{entry_low} ~ {entry_high}", str(target), str(stop_loss)


def build_stock_object(raw: Dict[str, Any]) -> Dict[str, Any] | None:
    symbol = str(raw.get("symbol", "")).strip()
    if not symbol:
        return None

    name = str(raw.get("name", "")).strip()

    # aggregates 常見欄位
    price = to_float(raw.get("lastPrice", raw.get("closePrice", 0)))
    change = to_float(raw.get("change", 0))
    change_percent = to_float(raw.get("changePercent", 0))
    open_price = to_float(raw.get("openPrice", 0))
    high_price = to_float(raw.get("highPrice", 0))
    low_price = to_float(raw.get("lowPrice", 0))
    prev_close = to_float(raw.get("previousClose", raw.get("referencePrice", 0)))
    avg_price = to_float(raw.get("avgPrice", 0))
    reference_price = to_float(raw.get("referencePrice", 0))
    amplitude = to_float(raw.get("amplitude", 0))
    is_close = bool(raw.get("isClose", False))

    total = raw.get("total", {}) or {}
    volume = to_int(total.get("tradeVolume", 0))
    trade_value = to_float(total.get("tradeValue", 0))
    transaction = to_int(total.get("transaction", 0))

    last_trade = raw.get("lastTrade", {}) or {}
    bid = to_float(last_trade.get("bid", 0))
    ask = to_float(last_trade.get("ask", 0))

    score = calc_score(price, change_percent, volume)
    signal = calc_signal(change_percent, price, open_price)
    reason = calc_reason(change_percent, volume, price, open_price)
    entry_price, target_price, stop_loss = calc_entry_target_stop(price, change_percent)

    stock_obj = {
        # ===== 你前端原本常用欄位 =====
        "symbol": symbol,
        "name": name,
        "price": price,
        "change": round(change, 2),
        "change_percent": round(change_percent, 2),
        "volume": volume,
        "score": score,
        "signal": signal,
        "reason": reason,
        "entry_price": entry_price,
        "target_price": target_price,
        "stop_loss": stop_loss,
        "prev_close": prev_close,
        "open": open_price,
        "high": high_price,
        "low": low_price,
        "update_time": now_str(),

        # ===== 額外保留欄位（前端用不到也沒關係） =====
        "avg_price": avg_price,
        "reference_price": reference_price,
        "amplitude": amplitude,
        "trade_value": trade_value,
        "transaction": transaction,
        "bid": bid,
        "ask": ask,
        "is_close": is_close,
    }

    return stock_obj


def update_market_status_by_payload(raw: Dict[str, Any]) -> None:
    is_close = bool(raw.get("isClose", False))
    data_date = str(raw.get("date", "")).replace("-", "")

    system_status["market_status"] = "收盤" if is_close else "盤中即時"
    system_status["data_date"] = data_date if data_date else today_str()
    system_status["last_update"] = now_str()


def upsert_stock(raw: Dict[str, Any]) -> None:
    stock_obj = build_stock_object(raw)
    if not stock_obj:
        return

    symbol = stock_obj["symbol"]

    with cache_lock:
        stocks_cache[symbol] = stock_obj
        update_market_status_by_payload(raw)
        system_status["success"] = True
        system_status["message"] = f"已接收富邦資料，共 {len(stocks_cache)} 檔"


# =========================
# WebSocket 事件
# =========================
def handle_message(message: Any) -> None:
    try:
        if isinstance(message, str):
            payload = json.loads(message)
        else:
            payload = message

        event = payload.get("event")
        data = payload.get("data", {})

        if event == "authenticated":
            system_status["success"] = True
            system_status["message"] = "富邦驗證成功"
            system_status["last_update"] = now_str()
            return

        if event == "subscribed":
            symbol = payload.get("data", {}).get("symbol", "")
            if symbol and symbol not in system_status["subscribed"]:
                system_status["subscribed"].append(symbol)
            system_status["message"] = f"已訂閱 {len(system_status['subscribed'])} 檔股票"
            system_status["last_update"] = now_str()
            return

        if event in ("snapshot", "data") and isinstance(data, dict):
            upsert_stock(data)
            return

        if event in ("heartbeat", "pong"):
            system_status["last_update"] = now_str()
            return

    except Exception as e:
        system_status["success"] = False
        system_status["message"] = f"解析訊息失敗: {str(e)}"
        system_status["last_update"] = now_str()


def handle_connect() -> None:
    system_status["success"] = True
    system_status["message"] = "富邦 WebSocket 已連線"
    system_status["last_update"] = now_str()


def handle_disconnect(code: Any, msg: Any) -> None:
    system_status["success"] = False
    system_status["message"] = f"WebSocket 斷線: code={code}, msg={msg}"
    system_status["last_update"] = now_str()


def handle_error(err: Any) -> None:
    system_status["success"] = False
    system_status["message"] = f"WebSocket 錯誤: {err}"
    system_status["last_update"] = now_str()


# =========================
# 富邦連線主程序
# =========================
def validate_env() -> tuple[bool, str]:
    if not FUBON_ID:
        return False, "缺少 FUBON_ID"
    if not FUBON_PWD:
        return False, "缺少 FUBON_PWD"
    if not FUBON_CERT_PATH:
        return False, "缺少 FUBON_CERT_PATH"
    if not FUBON_CERT_PWD:
        return False, "缺少 FUBON_CERT_PWD"
    if not os.path.exists(FUBON_CERT_PATH):
        return False, f"憑證檔不存在: {FUBON_CERT_PATH}"
    return True, "OK"


def subscribe_watchlist() -> None:
    global stock_ws

    for symbol in WATCHLIST:
        try:
            stock_ws.subscribe({
                "channel": "aggregates",
                "symbol": symbol
            })
            time.sleep(0.2)
        except Exception as e:
            system_status["message"] = f"訂閱 {symbol} 失敗: {str(e)}"
            system_status["last_update"] = now_str()


def connect_fubon_forever() -> None:
    global sdk, stock_ws

    ok, msg = validate_env()
    if not ok:
        system_status["success"] = False
        system_status["message"] = msg
        system_status["last_update"] = now_str()
        return

    while True:
        try:
            system_status["success"] = False
            system_status["message"] = "正在登入富邦 API..."
            system_status["last_update"] = now_str()

            sdk = FubonSDK()
            accounts = sdk.login(
                FUBON_ID,
                FUBON_PWD,
                FUBON_CERT_PATH,
                FUBON_CERT_PWD
            )

            if not getattr(accounts, "is_success", False):
                raise Exception(getattr(accounts, "message", "登入失敗"))

            system_status["message"] = "登入成功，初始化即時行情中..."
            system_status["last_update"] = now_str()

            # aggregates 要用 Normal mode
            sdk.init_realtime(Mode.Normal)

            stock_ws = sdk.marketdata.websocket_client.stock
            stock_ws.on("message", handle_message)
            stock_ws.on("connect", handle_connect)
            stock_ws.on("disconnect", handle_disconnect)
            stock_ws.on("error", handle_error)

            stock_ws.connect()
            time.sleep(2)

            system_status["subscribed"] = []
            subscribe_watchlist()

            system_status["success"] = True
            system_status["message"] = f"富邦即時行情已啟動，已送出 {len(WATCHLIST)} 檔訂閱"
            system_status["last_update"] = now_str()

            # 維持背景執行
            while True:
                time.sleep(5)

        except Exception as e:
            system_status["success"] = False
            system_status["message"] = f"富邦連線失敗，10 秒後重試: {str(e)}"
            system_status["last_update"] = now_str()
            time.sleep(10)


# =========================
# 啟動事件
# =========================
@app.on_event("startup")
def startup_event() -> None:
    t = Thread(target=connect_fubon_forever, daemon=True)
    t.start()


# =========================
# API
# =========================
@app.get("/")
def root():
    return {
        "message": "TW Stock Realtime Screener with Fubon API is running",
        "status": system_status,
        "watchlist": WATCHLIST,
    }


@app.get("/health")
def health():
    return {
        "success": system_status["success"],
        "message": system_status["message"],
        "market_status": system_status["market_status"],
        "last_update": system_status["last_update"],
        "subscribed": system_status["subscribed"],
        "cache_count": len(stocks_cache),
    }


@app.get("/stocks")
def get_stocks():
    with cache_lock:
        stock_list = list(stocks_cache.values())

    # 依分數優先，其次成交量，再來漲跌幅
    stock_list.sort(
        key=lambda x: (
            x.get("score", 0),
            x.get("volume", 0),
            x.get("change_percent", 0),
        ),
        reverse=True,
    )

    return {
        "success": system_status["success"],
        "market_status": system_status["market_status"],
        "data_date": system_status["data_date"],
        "last_update": system_status["last_update"],
        "message": system_status["message"],
        "total": len(stock_list),
        "stocks": stock_list[:TOP_LIMIT],
    }


@app.get("/stocks/{symbol}")
def get_stock_by_symbol(symbol: str):
    symbol = symbol.strip()

    with cache_lock:
        stock = stocks_cache.get(symbol)

    if not stock:
        return {
            "success": False,
            "message": f"查無股票 {symbol}",
            "stock": None
        }

    return {
        "success": True,
        "message": "ok",
        "stock": stock
    }
