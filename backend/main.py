import os
import math
import traceback
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# =========================
# App
# =========================
app = FastAPI(title="TW Stock Realtime Screener")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# =========================
# Global SDK cache
# =========================
_fubon_sdk = None
_fubon_login_info = None

TW_TZ = timezone(timedelta(hours=8))


# =========================
# Utils
# =========================
def to_float(v: Any, default: float = 0.0) -> float:
    try:
        if v is None:
            return default
        if isinstance(v, bool):
            return default
        if isinstance(v, (int, float)):
            if isinstance(v, float) and math.isnan(v):
                return default
            return float(v)
        s = str(v).strip().replace(",", "")
        if s in ("", "-"):
            return default
        return float(s)
    except Exception:
        return default


def to_int(v: Any, default: int = 0) -> int:
    try:
        if v is None:
            return default
        if isinstance(v, bool):
            return default
        if isinstance(v, int):
            return v
        if isinstance(v, float):
            if math.isnan(v):
                return default
            return int(v)
        s = str(v).strip().replace(",", "")
        if s in ("", "-"):
            return default
        return int(float(s))
    except Exception:
        return default


def safe_get(d: Dict[str, Any], *keys: str, default=None):
    for k in keys:
        if k in d and d[k] is not None:
            return d[k]
    return default


def calc_score(price: float, change_percent: float, volume: int) -> float:
    vol_score = min(volume / 100000, 100)
    move_score = abs(change_percent) * 8
    price_score = 0

    if 10 <= price <= 200:
        price_score = 10
    elif 200 < price <= 500:
        price_score = 6
    elif 0 < price < 10:
        price_score = 3

    return round(move_score + vol_score + price_score, 2)


def build_reason(change_percent: float, volume: int, price: float) -> str:
    reasons = []

    if change_percent >= 3:
        reasons.append("漲幅強勢")
    elif change_percent <= -3:
        reasons.append("跌幅明顯")
    else:
        reasons.append("股價波動中性")

    if volume >= 20000:
        reasons.append("成交量活躍")
    elif volume >= 5000:
        reasons.append("量能尚可")
    else:
        reasons.append("量能偏低")

    if 10 <= price <= 200:
        reasons.append("股價區間適中")

    return "、".join(reasons)


def build_signal(change_percent: float, volume: int) -> str:
    if change_percent >= 3 and volume >= 5000:
        return "偏多"
    if change_percent <= -3 and volume >= 5000:
        return "偏空"
    return "中性"


def build_trade_plan(price: float, signal: str):
    if price <= 0:
        return "-", "-", "-"

    if signal == "偏多":
        entry_low = round(price * 0.985, 2)
        entry_high = round(price * 1.005, 2)
        target = round(price * 1.05, 2)
        stop_loss = round(price * 0.965, 2)
    elif signal == "偏空":
        entry_low = round(price * 0.995, 2)
        entry_high = round(price * 1.015, 2)
        target = round(price * 0.95, 2)
        stop_loss = round(price * 1.03, 2)
    else:
        entry_low = round(price * 0.99, 2)
        entry_high = round(price * 1.01, 2)
        target = round(price * 1.03, 2)
        stop_loss = round(price * 0.97, 2)

    return f"{entry_low} ~ {entry_high}", str(target), str(stop_loss)


def normalize_market(market: str) -> str:
    market = (market or "").upper().strip()
    if market in ["TSE", "TWSE", "上市"]:
        return "TSE"
    if market in ["OTC", "TPEX", "上櫃"]:
        return "OTC"
    return market


def market_label(market: str) -> str:
    market = normalize_market(market)
    if market == "TSE":
        return "上市"
    if market == "OTC":
        return "上櫃"
    return market


def resolve_fubon_cert_path() -> str:
    raw_path = (os.getenv("FUBON_CERT_PATH") or "").strip().strip('"').strip("'")
    if not raw_path:
        raise Exception("FUBON_CERT_PATH 未設定")

    if os.path.exists(raw_path) and os.path.isfile(raw_path):
        return raw_path

    filename = os.path.basename(raw_path)
    candidates = [
        raw_path,
        f"/opt/render/project/src/{filename}",
        f"/opt/render/project/src/certs/{filename}",
        f"/opt/render/project/src/backend/certs/{filename}",
        os.path.join(os.getcwd(), filename),
        os.path.join(os.getcwd(), "certs", filename),
        os.path.join(os.getcwd(), "backend", "certs", filename),
    ]

    checked = []
    for p in candidates:
        if not p:
            continue
        checked.append(p)
        if os.path.exists(p) and os.path.isfile(p):
            return p

    raise Exception(f"找不到憑證檔，已檢查路徑: {checked}")


def format_last_updated(value: Any) -> str:
    """
    富邦 lastUpdated 看起來是微秒 timestamp，例如:
    1774848600000000
    """
    try:
        if value is None or value == "":
            return ""

        iv = int(str(value).strip())

        # 微秒
        if iv > 10**14:
            dt = datetime.fromtimestamp(iv / 1_000_000, tz=timezone.utc).astimezone(TW_TZ)
        # 毫秒
        elif iv > 10**11:
            dt = datetime.fromtimestamp(iv / 1_000, tz=timezone.utc).astimezone(TW_TZ)
        # 秒
        else:
            dt = datetime.fromtimestamp(iv, tz=timezone.utc).astimezone(TW_TZ)

        return dt.strftime("%Y/%m/%d %H:%M:%S")
    except Exception:
        return str(value)


def market_status_from_now() -> str:
    now = datetime.now(TW_TZ)
    minutes = now.hour * 60 + now.minute
    open_start = 9 * 60
    close_end = 13 * 60 + 30

    if now.weekday() >= 5:
        return "休市"

    if open_start <= minutes <= close_end:
        return "開盤"
    return "收盤"


def get_best_last_update(stocks: List[Dict[str, Any]]) -> str:
    candidates = [s.get("update_time", "") for s in stocks if s.get("update_time")]
    if not candidates:
        return datetime.now(TW_TZ).strftime("%Y/%m/%d %H:%M:%S")
    return max(candidates)


# =========================
# Fubon SDK
# =========================
def get_fubon_sdk():
    """
    初始化並快取富邦 SDK
    支援以下環境變數名稱：
    FUBON_ID
    FUBON_PWD 或 FUBON_PASSWORD
    FUBON_CERT_PATH
    FUBON_CERT_PWD 或 FUBON_CERT_PASSWORD
    """
    global _fubon_sdk, _fubon_login_info

    if _fubon_sdk is not None:
        return _fubon_sdk

    fubon_id = (os.getenv("FUBON_ID") or "").strip()
    fubon_pwd = (os.getenv("FUBON_PWD", os.getenv("FUBON_PASSWORD", "")) or "").strip()
    fubon_cert_pwd = (os.getenv("FUBON_CERT_PWD", os.getenv("FUBON_CERT_PASSWORD", "")) or "").strip()
    fubon_cert_path = resolve_fubon_cert_path()

    if not all([fubon_id, fubon_pwd, fubon_cert_path, fubon_cert_pwd]):
        raise Exception(
            f"FUBON 環境變數未設定完整: "
            f"ID={bool(fubon_id)}, "
            f"PWD={bool(fubon_pwd)}, "
            f"CERT_PATH={bool(fubon_cert_path)}, "
            f"CERT_PWD={bool(fubon_cert_pwd)}"
        )

    from fubon_neo.sdk import FubonSDK

    sdk = FubonSDK()
    login_info = sdk.login(
        fubon_id,
        fubon_pwd,
        fubon_cert_path,
        fubon_cert_pwd,
    )

    is_success = False
    message = None
    data = None

    try:
        is_success = bool(getattr(login_info, "is_success", False))
    except Exception:
        is_success = False

    try:
        message = getattr(login_info, "message", None)
    except Exception:
        message = None

    try:
        data = getattr(login_info, "data", None)
    except Exception:
        data = None

    if not is_success and not data:
        raise Exception(f"Fubon SDK login 失敗: {message or login_info}")

    _fubon_sdk = sdk
    _fubon_login_info = login_info
    return _fubon_sdk


def extract_rows_from_response(resp: Any) -> List[Dict[str, Any]]:
    if resp is None:
        return []

    if isinstance(resp, list):
        return resp

    if isinstance(resp, dict):
        data = resp.get("data", [])
        return data if isinstance(data, list) else []

    data = getattr(resp, "data", None)
    if isinstance(data, list):
        return data

    if hasattr(resp, "__dict__"):
        data = resp.__dict__.get("data", [])
        if isinstance(data, list):
            return data

    return []


def get_stock_rest_client():
    """
    兼容:
    sdk.marketdata.rest_client.stock
    sdk.marketdata.restClient.stock
    """
    sdk = get_fubon_sdk()

    marketdata = getattr(sdk, "marketdata", None)
    if marketdata is None:
        raise Exception("sdk.marketdata 不存在，請確認 login 是否成功")

    rest_client = getattr(marketdata, "rest_client", None)
    if rest_client is None:
        rest_client = getattr(marketdata, "restClient", None)

    if rest_client is None:
        raise Exception("找不到 marketdata.rest_client / restClient")

    stock_client = getattr(rest_client, "stock", None)
    if stock_client is None:
        raise Exception("找不到 marketdata.rest_client.stock")

    return stock_client


def get_sdk_market_snapshot(market: str) -> List[Dict[str, Any]]:
    market = normalize_market(market)
    stock_client = get_stock_rest_client()

    snapshot = getattr(stock_client, "snapshot", None)
    if snapshot is None:
        raise Exception("找不到 stock.snapshot")

    quotes_fn = getattr(snapshot, "quotes", None)
    if not callable(quotes_fn):
        raise Exception("找不到可用的 stock.snapshot.quotes 方法")

    resp = quotes_fn(market=market)
    rows = extract_rows_from_response(resp)

    if not isinstance(rows, list):
        raise Exception(f"snapshot.quotes 回傳格式異常: {type(rows)}")

    return rows


def map_snapshot_row(row: Dict[str, Any], market: str) -> Optional[Dict[str, Any]]:
    symbol = str(safe_get(row, "symbol", "code", default="")).strip()
    name = str(safe_get(row, "name", default="")).strip()

    if not symbol:
        return None

    price = to_float(safe_get(row, "lastPrice", "closePrice", "price", "close", default=0))
    open_price = to_float(safe_get(row, "openPrice", "open", default=0))
    high_price = to_float(safe_get(row, "highPrice", "high", default=0))
    low_price = to_float(safe_get(row, "lowPrice", "low", default=0))
    change = to_float(safe_get(row, "change", default=0))
    change_percent = to_float(safe_get(row, "changePercent", "change_percent", default=0))
    volume = to_int(safe_get(row, "tradeVolume", "volume", "totalVolume", default=0))
    prev_close = to_float(safe_get(row, "previousClose", "prevClose", "referencePrice", default=0))
    last_updated_raw = safe_get(row, "lastUpdated", "last_update", default="")

    if price <= 0:
        price = to_float(safe_get(row, "closePrice", default=0))

    if change_percent == 0 and price > 0 and change != 0:
        base = price - change
        if base != 0:
            change_percent = round((change / base) * 100, 2)

    score = calc_score(price, change_percent, volume)
    signal = build_signal(change_percent, volume)
    reason = build_reason(change_percent, volume, price)
    entry_price, target_price, stop_loss = build_trade_plan(price, signal)

    return {
        "market": market_label(market),
        "symbol": symbol,
        "name": name,
        "price": round(price, 2),
        "change": round(change, 2),
        "change_percent": round(change_percent, 2),
        "volume": volume,
        "score": score,
        "signal": signal,
        "reason": reason,
        "entry_price": entry_price,
        "target_price": target_price,
        "stop_loss": stop_loss,
        "prev_close": round(prev_close, 2),
        "open": round(open_price, 2),
        "high": round(high_price, 2),
        "low": round(low_price, 2),
        "update_time": format_last_updated(last_updated_raw),
    }


def get_market_stocks_from_fubon(market: str) -> List[Dict[str, Any]]:
    rows = get_sdk_market_snapshot(market)
    stocks: List[Dict[str, Any]] = []

    for row in rows:
        try:
            mapped = map_snapshot_row(row, market)
            if mapped is None:
                continue
            if mapped["price"] <= 0:
                continue
            stocks.append(mapped)
        except Exception:
            continue

    return stocks


# =========================
# Routes
# =========================
@app.get("/")
def root():
    return {"message": "TW Stock Realtime Screener backend running"}


@app.get("/health")
def health():
    return {"success": True, "message": "ok"}


@app.get("/debug_env")
def debug_env():
    fubon_pwd = os.getenv("FUBON_PWD", os.getenv("FUBON_PASSWORD", ""))
    fubon_cert_pwd = os.getenv("FUBON_CERT_PWD", os.getenv("FUBON_CERT_PASSWORD", ""))
    raw_path = (os.getenv("FUBON_CERT_PATH") or "").strip().strip('"').strip("'")
    filename = os.path.basename(raw_path) if raw_path else ""

    candidates = [
        raw_path,
        f"/opt/render/project/src/{filename}" if filename else "",
        f"/opt/render/project/src/certs/{filename}" if filename else "",
        f"/opt/render/project/src/backend/certs/{filename}" if filename else "",
        os.path.join(os.getcwd(), filename) if filename else "",
        os.path.join(os.getcwd(), "certs", filename) if filename else "",
        os.path.join(os.getcwd(), "backend", "certs", filename) if filename else "",
    ]

    checked_paths = []
    for p in candidates:
        if p:
            checked_paths.append({
                "path": p,
                "exists": os.path.exists(p),
                "is_file": os.path.isfile(p),
            })

    return {
        "success": True,
        "has_FUBON_ID": bool(os.getenv("FUBON_ID")),
        "has_FUBON_PWD": bool(fubon_pwd),
        "has_FUBON_CERT_PATH": bool(os.getenv("FUBON_CERT_PATH")),
        "has_FUBON_CERT_PWD": bool(fubon_cert_pwd),
        "FUBON_CERT_PATH": os.getenv("FUBON_CERT_PATH", ""),
        "resolved_cert_path": resolve_fubon_cert_path() if raw_path else "",
        "cwd": os.getcwd(),
        "using_pwd_key": "FUBON_PWD" if os.getenv("FUBON_PWD") else ("FUBON_PASSWORD" if os.getenv("FUBON_PASSWORD") else ""),
        "using_cert_pwd_key": "FUBON_CERT_PWD" if os.getenv("FUBON_CERT_PWD") else ("FUBON_CERT_PASSWORD" if os.getenv("FUBON_CERT_PASSWORD") else ""),
        "checked_paths": checked_paths,
    }


@app.get("/debug_snapshot")
def debug_snapshot(market: str = "TSE"):
    try:
        sdk = get_fubon_sdk()
        market = normalize_market(market)

        marketdata = getattr(sdk, "marketdata", None)
        rest_client = getattr(marketdata, "rest_client", None) if marketdata else None
        rest_client2 = getattr(marketdata, "restClient", None) if marketdata else None

        stock_client = None
        if rest_client is not None:
            stock_client = getattr(rest_client, "stock", None)
        elif rest_client2 is not None:
            stock_client = getattr(rest_client2, "stock", None)

        snapshot = getattr(stock_client, "snapshot", None) if stock_client else None
        quotes_fn = getattr(snapshot, "quotes", None) if snapshot else None

        rows = get_sdk_market_snapshot(market)

        return {
            "success": True,
            "market": market,
            "count": len(rows),
            "sample": rows[:3],
            "debug": {
                "has_marketdata": marketdata is not None,
                "has_rest_client": rest_client is not None,
                "has_restClient": rest_client2 is not None,
                "has_stock": stock_client is not None,
                "has_snapshot": snapshot is not None,
                "has_quotes": callable(quotes_fn),
                "marketdata_type": str(type(marketdata)),
                "stock_type": str(type(stock_client)),
                "snapshot_type": str(type(snapshot)),
                "marketdata_dir": dir(marketdata) if marketdata else [],
                "stock_dir": dir(stock_client) if stock_client else [],
                "snapshot_dir": dir(snapshot) if snapshot else [],
            }
        }
    except Exception as e:
        return {
            "success": False,
            "market": market,
            "error": str(e),
            "trace": traceback.format_exc()
        }


@app.get("/stocks")
def get_stocks():
    try:
        errors = []

        try:
            tse_stocks = get_market_stocks_from_fubon("TSE")
        except Exception as e:
            tse_stocks = []
            errors.append(f"TSE 失敗: {str(e)}")

        try:
            otc_stocks = get_market_stocks_from_fubon("OTC")
        except Exception as e:
            otc_stocks = []
            errors.append(f"OTC 失敗: {str(e)}")

        stocks = tse_stocks + otc_stocks
        stocks.sort(key=lambda x: (x.get("score", 0), x.get("volume", 0)), reverse=True)

        if not stocks:
            raise Exception("TSE 與 OTC 都沒有抓到資料" + (f"；{'; '.join(errors)}" if errors else ""))

        last_update = get_best_last_update(stocks)

        return {
            "success": True,
            "source": "FUBON_SDK",
            "market_status": market_status_from_now(),
            "data_date": datetime.now(TW_TZ).strftime("%Y%m%d"),
            "last_update": last_update,
            "total": len(stocks),
            "stocks": stocks,
            "message": "；".join(errors) if errors else "",
        }

    except Exception as e:
        return {
            "success": False,
            "source": "FUBON_SDK",
            "error": str(e),
            "trace": traceback.format_exc(),
        }


@app.get("/stocks/{market}")
def get_stocks_by_market(market: str):
    try:
        market = normalize_market(market)
        if market not in ["TSE", "OTC"]:
            return {
                "success": False,
                "error": "market 只支援 TSE 或 OTC"
            }

        stocks = get_market_stocks_from_fubon(market)
        stocks.sort(key=lambda x: (x.get("score", 0), x.get("volume", 0)), reverse=True)

        return {
            "success": True,
            "source": "FUBON_SDK",
            "market": market,
            "market_label": market_label(market),
            "market_status": market_status_from_now(),
            "data_date": datetime.now(TW_TZ).strftime("%Y%m%d"),
            "last_update": get_best_last_update(stocks),
            "total": len(stocks),
            "stocks": stocks,
        }

    except Exception as e:
        return {
            "success": False,
            "market": market,
            "error": str(e),
            "trace": traceback.format_exc(),
        }


@app.get("/top10")
def get_top10():
    try:
        errors = []

        try:
            tse_stocks = get_market_stocks_from_fubon("TSE")
        except Exception as e:
            tse_stocks = []
            errors.append(f"TSE 失敗: {str(e)}")

        try:
            otc_stocks = get_market_stocks_from_fubon("OTC")
        except Exception as e:
            otc_stocks = []
            errors.append(f"OTC 失敗: {str(e)}")

        stocks = tse_stocks + otc_stocks
        stocks.sort(key=lambda x: (x.get("score", 0), x.get("volume", 0)), reverse=True)

        return {
            "success": True,
            "total": min(10, len(stocks)),
            "stocks": stocks[:10],
            "message": "；".join(errors) if errors else "",
        }

    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "trace": traceback.format_exc(),
        }


@app.get("/debug_login")
def debug_login():
    try:
        sdk = get_fubon_sdk()
        return {
            "success": True,
            "sdk_type": str(type(sdk)),
            "login_info_type": str(type(_fubon_login_info)),
            "login_info": str(_fubon_login_info),
            "message": "Fubon SDK login success"
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "trace": traceback.format_exc()
        }
