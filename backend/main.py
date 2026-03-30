import os
import math
import traceback
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="TW Stock Realtime Screener")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# =========================
# Globals
# =========================
_sdk = None
_login_info = None
_marketdata_ready = False

_CACHE: Dict[str, Any] = {
    "stocks": None,
    "fetched_at": None,
    "data_date": "",
    "last_update": "",
}
CACHE_SECONDS = 20

TZ_TAIPEI = timezone(timedelta(hours=8))


# =========================
# Utils
# =========================
def safe_float(v: Any, default: float = 0.0) -> float:
    try:
        if v is None:
            return default
        if isinstance(v, str):
            v = v.replace(",", "").replace("%", "").strip()
            if v in ("", "-", "--", "None", "null"):
                return default
        return float(v)
    except Exception:
        return default


def safe_int(v: Any, default: int = 0) -> int:
    try:
        if v is None:
            return default
        if isinstance(v, str):
            v = v.replace(",", "").strip()
            if v in ("", "-", "--", "None", "null"):
                return default
        return int(float(v))
    except Exception:
        return default


def safe_str(v: Any, default: str = "") -> str:
    if v is None:
        return default
    return str(v).strip()


def now_taipei() -> datetime:
    return datetime.now(TZ_TAIPEI)


def format_dt_taipei(dt: datetime) -> str:
    return dt.astimezone(TZ_TAIPEI).strftime("%Y/%m/%d %H:%M:%S")


def micros_to_taipei_str(v: Any) -> str:
    try:
        iv = int(float(v))
        if iv <= 0:
            return ""
        dt = datetime.fromtimestamp(iv / 1_000_000, tz=timezone.utc).astimezone(TZ_TAIPEI)
        return dt.strftime("%Y/%m/%d %H:%M:%S")
    except Exception:
        return ""


def micros_to_date_str(v: Any) -> str:
    try:
        iv = int(float(v))
        if iv <= 0:
            return ""
        dt = datetime.fromtimestamp(iv / 1_000_000, tz=timezone.utc).astimezone(TZ_TAIPEI)
        return dt.strftime("%Y%m%d")
    except Exception:
        return ""


def resolve_cert_path() -> Optional[str]:
    cert_path = os.getenv("FUBON_CERT_PATH", "").strip()
    if not cert_path:
        return None

    candidates = [
        cert_path,
        os.path.abspath(cert_path),
        os.path.abspath(os.path.join(os.getcwd(), cert_path)),
        os.path.join("/opt/render/project/src", os.path.basename(cert_path)),
        os.path.join("/opt/render/project/src/certs", os.path.basename(cert_path)),
        os.path.join("/opt/render/project/src/backend", os.path.basename(cert_path)),
        os.path.join("/opt/render/project/src/backend/certs", os.path.basename(cert_path)),
    ]

    seen = set()
    for p in candidates:
        rp = os.path.abspath(p)
        if rp in seen:
            continue
        seen.add(rp)
        if os.path.exists(rp) and os.path.isfile(rp):
            return rp
    return None


def get_env_debug_info() -> Dict[str, Any]:
    original_cert = os.getenv("FUBON_CERT_PATH", "").strip()

    raw = [
        original_cert,
        os.path.abspath(original_cert) if original_cert else "",
        os.path.abspath(os.path.join(os.getcwd(), original_cert)) if original_cert else "",
        os.path.join("/opt/render/project/src", os.path.basename(original_cert)) if original_cert else "",
        os.path.join("/opt/render/project/src/certs", os.path.basename(original_cert)) if original_cert else "",
        os.path.join("/opt/render/project/src/backend", os.path.basename(original_cert)) if original_cert else "",
        os.path.join("/opt/render/project/src/backend/certs", os.path.basename(original_cert)) if original_cert else "",
    ]

    checked_paths = []
    seen = set()
    for p in raw:
        if not p:
            continue
        rp = os.path.abspath(p)
        if rp in seen:
            continue
        seen.add(rp)
        checked_paths.append(
            {
                "path": rp,
                "exists": os.path.exists(rp),
                "is_file": os.path.isfile(rp),
            }
        )

    return {
        "success": True,
        "has_FUBON_ID": bool(os.getenv("FUBON_ID")),
        "has_FUBON_PWD": bool(os.getenv("FUBON_PASSWORD") or os.getenv("FUBON_PWD")),
        "has_FUBON_CERT_PATH": bool(os.getenv("FUBON_CERT_PATH")),
        "has_FUBON_CERT_PWD": bool(os.getenv("FUBON_CERT_PASSWORD") or os.getenv("FUBON_CERT_PWD")),
        "FUBON_CERT_PATH": os.getenv("FUBON_CERT_PATH"),
        "resolved_cert_path": resolve_cert_path(),
        "cwd": os.getcwd(),
        "using_pwd_key": "FUBON_PASSWORD" if os.getenv("FUBON_PASSWORD") else ("FUBON_PWD" if os.getenv("FUBON_PWD") else None),
        "using_cert_pwd_key": "FUBON_CERT_PASSWORD" if os.getenv("FUBON_CERT_PASSWORD") else ("FUBON_CERT_PWD" if os.getenv("FUBON_CERT_PWD") else None),
        "checked_paths": checked_paths,
    }


def is_market_open() -> bool:
    now = now_taipei()
    # 週一~週五，09:00 ~ 13:30
    if now.weekday() >= 5:
        return False
    minutes = now.hour * 60 + now.minute
    return 9 * 60 <= minutes <= 13 * 60 + 30


def get_market_status_text() -> str:
    now = now_taipei()
    if now.weekday() >= 5:
        return "休市"
    minutes = now.hour * 60 + now.minute
    if minutes < 9 * 60:
        return "開盤前"
    if 9 * 60 <= minutes <= 13 * 60 + 30:
        return "開盤"
    return "收盤"


def is_etf_symbol(symbol: str, name: str) -> bool:
    s = safe_str(symbol)
    n = safe_str(name)
    # 台股 ETF / ETN 常見規則
    if s.startswith("00"):
        return True
    if "ETF" in n.upper():
        return True
    return False


def is_common_stock_candidate(symbol: str, name: str) -> bool:
    if is_etf_symbol(symbol, name):
        return False
    # 只保留數字代號或 KY 類型也可
    return True


def price_category(price: float) -> str:
    if price < 10:
        return "0-10"
    if price < 20:
        return "10-20"
    if price < 50:
        return "20-50"
    if price < 100:
        return "50-100"
    if price < 200:
        return "100-200"
    if price < 500:
        return "200-500"
    if price < 1000:
        return "500-1000"
    return "1000+"


# =========================
# Fubon SDK
# =========================
def ensure_fubon_sdk():
    global _sdk, _login_info, _marketdata_ready

    if _sdk is not None and _marketdata_ready:
        return _sdk

    from fubon_neo.sdk import FubonSDK

    fubon_id = os.getenv("FUBON_ID", "").strip()
    fubon_pwd = (os.getenv("FUBON_PASSWORD") or os.getenv("FUBON_PWD") or "").strip()
    cert_pwd = (os.getenv("FUBON_CERT_PASSWORD") or os.getenv("FUBON_CERT_PWD") or "").strip()
    cert_path = resolve_cert_path()

    if not fubon_id or not fubon_pwd or not cert_pwd or not cert_path:
        raise Exception("FUBON 環境變數未設定完整")

    if _sdk is None:
        _sdk = FubonSDK()

    if _login_info is None:
        _login_info = _sdk.login(fubon_id, fubon_pwd, cert_path, cert_pwd)

    is_success = getattr(_login_info, "is_success", False)
    if not is_success:
        raise Exception(f"Fubon SDK login failed: {getattr(_login_info, 'message', 'unknown error')}")

    if not _marketdata_ready:
        _sdk.init_realtime()
        _marketdata_ready = True

    return _sdk


def get_stock_rest_client():
    sdk = ensure_fubon_sdk()

    marketdata = getattr(sdk, "marketdata", None)
    if marketdata is None:
        raise Exception("sdk.marketdata 不存在")

    rest_client = getattr(marketdata, "rest_client", None)
    if rest_client is None:
        raise Exception("sdk.marketdata.rest_client 不存在")

    stock_client = getattr(rest_client, "stock", None)
    if stock_client is None:
        raise Exception("sdk.marketdata.rest_client.stock 不存在")

    return stock_client


# =========================
# Parse / Normalize
# =========================
def extract_rows(resp: Any) -> List[Dict[str, Any]]:
    if isinstance(resp, list):
        return resp

    if isinstance(resp, dict):
        for key in ["data", "items", "rows", "quotes", "result"]:
            val = resp.get(key)
            if isinstance(val, list):
                return val
            if isinstance(val, dict):
                for subkey in ["data", "items", "rows", "quotes"]:
                    subval = val.get(subkey)
                    if isinstance(subval, list):
                        return subval

    if hasattr(resp, "data"):
        data = getattr(resp, "data")
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            for key in ["data", "items", "rows", "quotes"]:
                val = data.get(key)
                if isinstance(val, list):
                    return val

    return []


def build_signal_and_reason(
    price: float,
    change: float,
    change_percent: float,
    volume: int,
    open_price: float,
    high_price: float,
    low_price: float,
    is_etf: bool,
) -> Dict[str, str]:
    if is_etf:
        if change_percent >= 2:
            signal = "偏多"
            reason = "ETF 走勢偏強、漲幅明顯，適合持續觀察"
        elif change_percent <= -2:
            signal = "偏空"
            reason = "ETF 走勢偏弱、跌幅明顯，短線宜保守"
        else:
            signal = "中性"
            reason = "ETF 波動中性，建議等待更明確方向"
        return {"signal": signal, "reason": reason}

    intraday_range = max(high_price - low_price, 0)
    bullish = change_percent > 3 and volume > 1000
    bearish = change_percent < -3 and volume > 1000

    if bullish:
        return {
            "signal": "偏多",
            "reason": "股價強勢上漲，量能放大，短線多方較有優勢",
        }
    if bearish:
        return {
            "signal": "偏空",
            "reason": "股價明顯轉弱且量能放大，短線需留意賣壓",
        }

    if change_percent > 0:
        return {
            "signal": "中性偏多",
            "reason": f"股價收紅，波動區間約 {round(intraday_range, 2)} 元，走勢偏穩",
        }

    if change_percent < 0:
        return {
            "signal": "中性偏空",
            "reason": f"股價收黑，波動區間約 {round(intraday_range, 2)} 元，仍需觀察支撐",
        }

    return {
        "signal": "中性",
        "reason": "股價變動不大，建議等待更明確的方向",
    }


def build_trade_plan(
    price: float,
    change_percent: float,
    high_price: float,
    low_price: float,
    is_etf: bool,
) -> Dict[str, str]:
    if price <= 0:
        return {
            "entry_price": "",
            "target_price": "",
            "stop_loss": "",
        }

    # 波動寬度
    swing = max(high_price - low_price, price * 0.02)
    entry_low = max(price - swing * 0.25, 0.01)
    entry_high = price

    if is_etf:
        target = price * 1.03
        stop = price * 0.97
    else:
        if change_percent >= 5:
            target = price * 1.06
            stop = price * 0.96
        elif change_percent >= 0:
            target = price * 1.04
            stop = price * 0.97
        else:
            target = price * 1.03
            stop = price * 0.95

    return {
        "entry_price": f"{round(entry_low, 2)} ~ {round(entry_high, 2)}",
        "target_price": f"{round(target, 2)}",
        "stop_loss": f"{round(stop, 2)}",
    }


def normalize_snapshot_row(row: Dict[str, Any], market_label: str) -> Optional[Dict[str, Any]]:
    if not isinstance(row, dict):
        return None

    symbol = safe_str(
        row.get("symbol")
        or row.get("stockNo")
        or row.get("stock_no")
        or row.get("code")
        or row.get("ticker")
    )
    if not symbol:
        return None

    name = safe_str(row.get("name") or row.get("stockName") or row.get("stock_name") or symbol)

    price = safe_float(
        row.get("lastPrice")
        or row.get("closePrice")
        or row.get("tradePrice")
        or row.get("price")
        or row.get("currentPrice")
    )
    if price <= 0:
        return None

    change = safe_float(row.get("change") or row.get("priceChange") or row.get("changePrice"))
    previous_close = safe_float(row.get("previousClose") or row.get("referencePrice"))
    change_percent = safe_float(row.get("changePercent"))

    if previous_close <= 0 and price > 0 and change != 0:
        prev = price - change
        if prev > 0:
            previous_close = prev

    if change_percent == 0 and previous_close > 0 and change != 0:
        change_percent = (change / previous_close) * 100

    volume = safe_int(
        row.get("tradeVolume")
        or row.get("volume")
        or row.get("totalVolume")
        or row.get("accumulatedVolume")
        or row.get("tradeVolumeAtBid")
    )
    trade_value = safe_int(row.get("tradeValue"))

    open_price = safe_float(row.get("openPrice"))
    high_price = safe_float(row.get("highPrice"))
    low_price = safe_float(row.get("lowPrice"))

    update_time_raw = row.get("lastUpdated") or row.get("time") or 0
    update_time_str = micros_to_taipei_str(update_time_raw)

    etf = is_etf_symbol(symbol, name)
    category = price_category(price)

    # 基本分數
    score = round(abs(change_percent) * 10 + min(volume / 100000, 50), 2)

    # 推薦分數
    liquidity_bonus = min(volume / 5000, 20)
    stability_penalty = 0 if low_price <= 0 or high_price <= 0 else min((high_price - low_price) / max(price, 1) * 10, 10)
    recommendation_score = round(
        max(
            0.0,
            abs(change_percent) * 6 + liquidity_bonus + (2 if not etf else -1) - stability_penalty * 0.3,
        ),
        2,
    )

    signal_info = build_signal_and_reason(
        price=price,
        change=change,
        change_percent=change_percent,
        volume=volume,
        open_price=open_price,
        high_price=high_price,
        low_price=low_price,
        is_etf=etf,
    )
    plan = build_trade_plan(
        price=price,
        change_percent=change_percent,
        high_price=high_price,
        low_price=low_price,
        is_etf=etf,
    )

    return {
        "market": market_label,
        "symbol": symbol,
        "name": name,
        "price": round(price, 2),
        "change": round(change, 2),
        "change_percent": round(change_percent, 2),
        "volume": volume,
        "trade_value": trade_value,
        "score": score,
        "recommendation_score": recommendation_score,
        "prev_close": round(previous_close, 2) if previous_close > 0 else 0,
        "open": round(open_price, 2),
        "high": round(high_price, 2),
        "low": round(low_price, 2),
        "update_time": update_time_str,
        "update_time_raw": update_time_raw,
        "category": category,
        "is_etf": etf,
        "signal": signal_info["signal"],
        "reason": signal_info["reason"],
        "entry_price": plan["entry_price"],
        "target_price": plan["target_price"],
        "stop_loss": plan["stop_loss"],
    }


# =========================
# Market Data
# =========================
def fetch_snapshot_market(market: str, market_label: str) -> List[Dict[str, Any]]:
    stock_client = get_stock_rest_client()
    resp = stock_client.snapshot.quotes(market=market, type="ALLBUT0999")
    rows = extract_rows(resp)

    result: List[Dict[str, Any]] = []
    for row in rows:
        item = normalize_snapshot_row(row, market_label=market_label)
        if item:
            result.append(item)

    dedup = {}
    for item in result:
        dedup[item["symbol"]] = item

    return list(dedup.values())


def get_all_stocks_raw() -> Dict[str, Any]:
    all_stocks: List[Dict[str, Any]] = []
    errors: List[str] = []

    try:
        all_stocks.extend(fetch_snapshot_market("TSE", "上市"))
    except Exception as e:
        errors.append(f"TSE 失敗: {e}")

    try:
        all_stocks.extend(fetch_snapshot_market("OTC", "上櫃"))
    except Exception as e:
        errors.append(f"OTC 失敗: {e}")

    dedup = {}
    for item in all_stocks:
        dedup[item["symbol"]] = item

    stocks = list(dedup.values())

    if not stocks and errors:
        raise Exception("；".join(errors))

    latest_raw = 0
    for s in stocks:
        latest_raw = max(latest_raw, safe_int(s.get("update_time_raw")))

    data_date = micros_to_date_str(latest_raw) if latest_raw else now_taipei().strftime("%Y%m%d")
    last_update = micros_to_taipei_str(latest_raw) if latest_raw else format_dt_taipei(now_taipei())

    return {
        "stocks": stocks,
        "data_date": data_date,
        "last_update": last_update,
    }


def get_cached_all_stocks(force_refresh: bool = False) -> Dict[str, Any]:
    now = now_taipei()

    if (
        not force_refresh
        and _CACHE["stocks"] is not None
        and _CACHE["fetched_at"] is not None
        and (now - _CACHE["fetched_at"]).total_seconds() < CACHE_SECONDS
    ):
        return {
            "stocks": _CACHE["stocks"],
            "data_date": _CACHE["data_date"],
            "last_update": _CACHE["last_update"],
        }

    result = get_all_stocks_raw()
    _CACHE["stocks"] = result["stocks"]
    _CACHE["fetched_at"] = now
    _CACHE["data_date"] = result["data_date"]
    _CACHE["last_update"] = result["last_update"]

    return result


# =========================
# Business Logic
# =========================
def build_categories(stocks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    order = ["0-10", "10-20", "20-50", "50-100", "100-200", "200-500", "500-1000", "1000+"]
    counts = {k: 0 for k in order}
    for s in stocks:
        c = s.get("category", "")
        if c in counts:
            counts[c] += 1

    return [{"key": k, "label": k, "count": counts[k]} for k in order]


def filter_stocks(
    stocks: List[Dict[str, Any]],
    market: str = "all",
    category: str = "all",
    q: str = "",
    price_min: float = 0.0,
    price_max: float = 0.0,
    include_etf: bool = True,
) -> List[Dict[str, Any]]:
    result = stocks

    if market != "all":
        market_map = {
            "tse": "上市",
            "otc": "上櫃",
            "上市": "上市",
            "上櫃": "上櫃",
        }
        target_market = market_map.get(market.lower(), market)
        result = [s for s in result if s.get("market") == target_market]

    if category != "all":
        result = [s for s in result if s.get("category") == category]

    if q.strip():
        qq = q.strip().lower()
        result = [
            s for s in result
            if qq in safe_str(s.get("symbol")).lower() or qq in safe_str(s.get("name")).lower()
        ]

    if price_min > 0:
        result = [s for s in result if safe_float(s.get("price")) >= price_min]

    if price_max > 0:
        result = [s for s in result if safe_float(s.get("price")) <= price_max]

    if not include_etf:
        result = [s for s in result if not s.get("is_etf", False)]

    return result


def sort_stocks(stocks: List[Dict[str, Any]], sort_by: str = "score", sort_dir: str = "desc") -> List[Dict[str, Any]]:
    reverse = sort_dir.lower() != "asc"

    allowed = {
        "score": "score",
        "recommendation_score": "recommendation_score",
        "price": "price",
        "change": "change",
        "change_percent": "change_percent",
        "volume": "volume",
        "trade_value": "trade_value",
        "symbol": "symbol",
        "name": "name",
    }
    key = allowed.get(sort_by, "score")

    return sorted(stocks, key=lambda x: x.get(key, 0), reverse=reverse)


def build_recommendations(stocks: List[Dict[str, Any]], top_n: int = 10) -> List[Dict[str, Any]]:
    candidates = []
    for s in stocks:
        if s.get("is_etf", False):
            continue
        if safe_float(s.get("price")) <= 0:
            continue
        if safe_int(s.get("volume")) <= 0:
            continue
        candidates.append(s)

    candidates.sort(
        key=lambda x: (
            x.get("recommendation_score", 0),
            x.get("volume", 0),
            abs(x.get("change_percent", 0)),
        ),
        reverse=True,
    )
    return candidates[:top_n]


def clean_stock_output(s: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "market": s.get("market", ""),
        "symbol": s.get("symbol", ""),
        "name": s.get("name", ""),
        "price": s.get("price", 0),
        "change": s.get("change", 0),
        "change_percent": s.get("change_percent", 0),
        "volume": s.get("volume", 0),
        "score": s.get("score", 0),
        "recommendation_score": s.get("recommendation_score", 0),
        "prev_close": s.get("prev_close", 0),
        "open": s.get("open", 0),
        "high": s.get("high", 0),
        "low": s.get("low", 0),
        "update_time": s.get("update_time", ""),
        "category": s.get("category", ""),
        "is_etf": s.get("is_etf", False),
        "signal": s.get("signal", ""),
        "reason": s.get("reason", ""),
        "entry_price": s.get("entry_price", ""),
        "target_price": s.get("target_price", ""),
        "stop_loss": s.get("stop_loss", ""),
    }


# =========================
# Startup
# =========================
@app.on_event("startup")
def startup_event():
    try:
        ensure_fubon_sdk()
        print("✅ Fubon SDK initialized successfully")
    except Exception as e:
        print(f"⚠️ Fubon SDK startup init failed: {e}")


# =========================
# Routes
# =========================
@app.get("/")
def root():
    return {"message": "TW Stock Realtime Screener is running"}


@app.get("/debug-env")
def debug_env():
    return get_env_debug_info()


@app.get("/debug-login")
def debug_login():
    try:
        sdk = ensure_fubon_sdk()
        return {
            "success": True,
            "sdk_type": str(type(sdk)),
            "login_info_type": str(type(_login_info)),
            "login_info": str(_login_info),
            "marketdata_ready": _marketdata_ready,
            "has_marketdata": hasattr(sdk, "marketdata") and getattr(sdk, "marketdata", None) is not None,
            "message": "Fubon SDK login success",
        }
    except Exception as e:
        return {"success": False, "error": str(e), "trace": traceback.format_exc()}


@app.get("/debug-sdk")
def debug_sdk():
    try:
        sdk = ensure_fubon_sdk()
        marketdata = getattr(sdk, "marketdata", None)
        rest_client = getattr(marketdata, "rest_client", None) if marketdata else None
        stock_client = getattr(rest_client, "stock", None) if rest_client else None

        return {
            "success": True,
            "has_marketdata": marketdata is not None,
            "marketdata_type": str(type(marketdata)) if marketdata is not None else None,
            "has_rest_client": rest_client is not None,
            "rest_client_type": str(type(rest_client)) if rest_client is not None else None,
            "has_stock_client": stock_client is not None,
            "stock_client_type": str(type(stock_client)) if stock_client is not None else None,
            "has_intraday": hasattr(stock_client, "intraday") if stock_client is not None else False,
            "has_snapshot": hasattr(stock_client, "snapshot") if stock_client is not None else False,
        }
    except Exception as e:
        return {"success": False, "error": str(e), "trace": traceback.format_exc()}


@app.get("/debug-snapshot")
def debug_snapshot(symbol: str = "2330"):
    try:
        stock_client = get_stock_rest_client()
        resp = stock_client.intraday.quote(symbol=symbol)
        return {
            "success": True,
            "symbol": symbol,
            "raw_type": str(type(resp)),
            "raw": resp,
        }
    except Exception as e:
        return {"success": False, "symbol": symbol, "error": str(e), "trace": traceback.format_exc()}


@app.get("/debug-market-snapshot")
def debug_market_snapshot(market: str = "TSE"):
    try:
        stock_client = get_stock_rest_client()
        resp = stock_client.snapshot.quotes(market=market, type="ALLBUT0999")
        rows = extract_rows(resp)
        return {
            "success": True,
            "market": market,
            "raw_type": str(type(resp)),
            "count": len(rows),
            "preview": rows[:5],
        }
    except Exception as e:
        return {"success": False, "market": market, "error": str(e), "trace": traceback.format_exc()}


@app.get("/recommendations")
def recommendations():
    try:
        result = get_cached_all_stocks()
        recs = build_recommendations(result["stocks"], top_n=10)
        return {
            "success": True,
            "total": len(recs),
            "recommendations": [clean_stock_output(x) for x in recs],
        }
    except Exception as e:
        return {"success": False, "error": str(e), "trace": traceback.format_exc(), "recommendations": []}


@app.get("/categories")
def categories():
    try:
        result = get_cached_all_stocks()
        return {
            "success": True,
            "categories": build_categories(result["stocks"]),
        }
    except Exception as e:
        return {"success": False, "error": str(e), "trace": traceback.format_exc(), "categories": []}


@app.get("/stocks")
def get_stocks(
    market: str = Query("all"),
    category: str = Query("all"),
    q: str = Query(""),
    sort_by: str = Query("score"),
    sort_dir: str = Query("desc"),
    limit: int = Query(300, ge=1, le=5000),
    offset: int = Query(0, ge=0),
    price_min: float = Query(0),
    price_max: float = Query(0),
    include_etf: bool = Query(True),
    force_refresh: bool = Query(False),
):
    try:
        result = get_cached_all_stocks(force_refresh=force_refresh)
        all_stocks = result["stocks"]

        filtered = filter_stocks(
            all_stocks,
            market=market,
            category=category,
            q=q,
            price_min=price_min,
            price_max=price_max,
            include_etf=include_etf,
        )
        filtered = sort_stocks(filtered, sort_by=sort_by, sort_dir=sort_dir)

        total_filtered = len(filtered)
        paged = filtered[offset: offset + limit]

        recs = build_recommendations(all_stocks, top_n=10)
        cats = build_categories(all_stocks)

        return {
            "success": True,
            "market_status": get_market_status_text(),
            "data_date": result["data_date"],
            "last_update": result["last_update"],
            "total": total_filtered,
            "offset": offset,
            "limit": limit,
            "categories": cats,
            "recommendations": [clean_stock_output(x) for x in recs],
            "stocks": [clean_stock_output(x) for x in paged],
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "trace": traceback.format_exc(),
            "stocks": [],
            "recommendations": [],
            "categories": [],
        }
