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

# =========================
# Global
# =========================
_sdk = None
_login_info = None
_marketdata_ready = False


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

    candidates = []
    if original_cert:
        raw = [
            original_cert,
            os.path.abspath(original_cert),
            os.path.abspath(os.path.join(os.getcwd(), original_cert)),
            os.path.join("/opt/render/project/src", os.path.basename(original_cert)),
            os.path.join("/opt/render/project/src/certs", os.path.basename(original_cert)),
            os.path.join("/opt/render/project/src/backend", os.path.basename(original_cert)),
            os.path.join("/opt/render/project/src/backend/certs", os.path.basename(original_cert)),
        ]
        seen = set()
        for p in raw:
            rp = os.path.abspath(p)
            if rp in seen:
                continue
            seen.add(rp)
            candidates.append({
                "path": rp,
                "exists": os.path.exists(rp),
                "is_file": os.path.isfile(rp),
            })

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
        "checked_paths": candidates,
    }


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
        raise Exception("sdk.marketdata 不存在，表示 init_realtime 後仍未建立行情物件")

    rest_client = getattr(marketdata, "rest_client", None)
    if rest_client is None:
        raise Exception("sdk.marketdata.rest_client 不存在")

    stock_client = getattr(rest_client, "stock", None)
    if stock_client is None:
        raise Exception("sdk.marketdata.rest_client.stock 不存在")

    return stock_client


def normalize_stock_item(symbol: str, name: str, quote: Dict[str, Any], market_label: str) -> Dict[str, Any]:
    price = safe_float(
        quote.get("lastPrice")
        or quote.get("closePrice")
        or quote.get("tradePrice")
        or quote.get("price")
        or quote.get("currentPrice")
    )
    change = safe_float(
        quote.get("change")
        or quote.get("priceChange")
        or quote.get("changePrice")
    )
    change_percent = safe_float(quote.get("changePercent"))

    prev_close = safe_float(quote.get("previousClose"))
    if prev_close <= 0 and price > 0 and change != 0:
        prev_close = price - change

    if change_percent == 0 and prev_close > 0 and change != 0:
        change_percent = (change / prev_close) * 100

    volume = safe_int(
        quote.get("tradeVolume")
        or quote.get("volume")
        or quote.get("totalVolume")
        or quote.get("accumulatedVolume")
    )

    return {
        "market": market_label,
        "symbol": symbol,
        "name": name or symbol,
        "price": round(price, 2),
        "change": round(change, 2),
        "change_percent": round(change_percent, 2),
        "volume": volume,
        "score": round(abs(change_percent) * 10 + min(volume / 100000, 50), 2),
        "prev_close": round(prev_close, 2) if prev_close > 0 else 0,
        "open": round(safe_float(quote.get("openPrice")), 2),
        "high": round(safe_float(quote.get("highPrice")), 2),
        "low": round(safe_float(quote.get("lowPrice")), 2),
        "update_time": str(
            quote.get("lastUpdated")
            or quote.get("updateTime")
            or quote.get("dateTime")
            or ""
        ),
    }


def get_demo_quotes() -> List[Dict[str, Any]]:
    stock_client = get_stock_rest_client()

    demo_symbols = [
        ("2330", "台積電", "上市"),
        ("2317", "鴻海", "上市"),
        ("2454", "聯發科", "上市"),
        ("2303", "聯電", "上市"),
        ("2603", "長榮", "上市"),
        ("8069", "元太", "上櫃"),
    ]

    results = []

    for symbol, name, market_label in demo_symbols:
        try:
            q = stock_client.intraday.quote(symbol=symbol)
            if isinstance(q, dict) and "data" in q and isinstance(q["data"], dict):
                q = q["data"]
            results.append(normalize_stock_item(symbol, name, q, market_label))
        except Exception:
            continue

    return results


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
        return {
            "success": False,
            "error": str(e),
            "trace": traceback.format_exc(),
        }


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
            "stock_client_dir": dir(stock_client) if stock_client is not None else [],
            "has_intraday": hasattr(stock_client, "intraday") if stock_client is not None else False,
            "has_snapshot": hasattr(stock_client, "snapshot") if stock_client is not None else False,
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "trace": traceback.format_exc(),
        }


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
        return {
            "success": False,
            "symbol": symbol,
            "error": str(e),
            "trace": traceback.format_exc(),
        }


@app.get("/stocks")
def get_stocks():
    try:
        stocks = get_demo_quotes()
        return {
            "success": True,
            "market_status": "富邦即時行情",
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
