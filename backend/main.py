import os
import traceback
from typing import Any, Dict, List, Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="TW Stock Realtime Screener")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

_sdk = None
_login_info = None
_marketdata_ready = False


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


def to_market_label(exchange: str, market: str) -> str:
    ex = safe_str(exchange).upper()
    mk = safe_str(market).upper()

    if ex == "TWSE" or mk == "TSE":
        return "上市"
    if ex == "TPEX" or mk == "OTC":
        return "上櫃"
    if mk == "ESB":
        return "興櫃"
    if mk == "TIB":
        return "創新板"
    if mk == "PSB":
        return "戰略新板"
    return mk or ex or ""


def normalize_snapshot_row(row: Dict[str, Any]) -> Optional[Dict[str, Any]]:
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
    exchange = safe_str(row.get("exchange"))
    market = safe_str(row.get("market"))
    market_label = to_market_label(exchange, market)

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

    if change_percent == 0 and previous_close > 0 and change != 0:
        change_percent = (change / previous_close) * 100
    elif change_percent == 0 and previous_close <= 0 and price > 0 and change != 0:
        prev = price - change
        if prev > 0:
            previous_close = prev
            change_percent = (change / prev) * 100

    total = row.get("total") if isinstance(row.get("total"), dict) else {}
    volume = safe_int(
        row.get("tradeVolume")
        or row.get("volume")
        or row.get("totalVolume")
        or row.get("accumulatedVolume")
        or total.get("tradeVolume")
    )

    score = round(abs(change_percent) * 10 + min(volume / 100000, 50), 2)

    return {
        "market": market_label,
        "symbol": symbol,
        "name": name,
        "price": round(price, 2),
        "change": round(change, 2),
        "change_percent": round(change_percent, 2),
        "volume": volume,
        "score": score,
        "prev_close": round(previous_close, 2) if previous_close > 0 else 0,
        "open": round(safe_float(row.get("openPrice")), 2),
        "high": round(safe_float(row.get("highPrice")), 2),
        "low": round(safe_float(row.get("lowPrice")), 2),
        "update_time": safe_str(row.get("lastUpdated") or total.get("time")),
    }


def fetch_snapshot_market(market: str) -> List[Dict[str, Any]]:
    stock_client = get_stock_rest_client()
    resp = stock_client.snapshot.quotes(market=market, type="ALLBUT0999")
    rows = extract_rows(resp)

    result: List[Dict[str, Any]] = []
    for row in rows:
        item = normalize_snapshot_row(row)
        if item:
            result.append(item)

    dedup = {}
    for item in result:
        dedup[item["symbol"]] = item

    return list(dedup.values())


def get_all_stocks() -> List[Dict[str, Any]]:
    all_stocks: List[Dict[str, Any]] = []
    errors: List[str] = []

    try:
        all_stocks.extend(fetch_snapshot_market("TSE"))
    except Exception as e:
        errors.append(f"TSE 失敗: {e}")

    try:
        all_stocks.extend(fetch_snapshot_market("OTC"))
    except Exception as e:
        errors.append(f"OTC 失敗: {e}")

    dedup = {}
    for item in all_stocks:
        dedup[item["symbol"]] = item

    stocks = list(dedup.values())
    stocks.sort(key=lambda x: (x.get("score", 0), x.get("volume", 0)), reverse=True)

    if not stocks and errors:
        raise Exception("；".join(errors))

    return stocks


@app.on_event("startup")
def startup_event():
    try:
        ensure_fubon_sdk()
        print("✅ Fubon SDK initialized successfully")
    except Exception as e:
        print(f"⚠️ Fubon SDK startup init failed: {e}")


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


@app.get("/stocks")
def get_stocks():
    try:
        stocks = get_all_stocks()
        return {
            "success": True,
            "market_status": "富邦即時行情" if stocks else "無資料",
            "data_date": "",
            "last_update": "",
            "total": len(stocks),
            "stocks": stocks,
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "trace": traceback.format_exc(),
            "stocks": [],
        }
