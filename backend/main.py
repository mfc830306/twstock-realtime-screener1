import os
import math
import traceback
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
# Globals
# =========================
_sdk = None
_login_info = None
_marketdata_ready = False


# =========================
# Helpers
# =========================
def safe_float(v: Any, default: float = 0.0) -> float:
    try:
        if v is None:
            return default
        if isinstance(v, str):
            v = v.replace(",", "").replace("%", "").strip()
            if v in ("", "-", "--", "null", "None"):
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
            if v in ("", "-", "--", "null", "None"):
                return default
        return int(float(v))
    except Exception:
        return default


def normalize_code(v: Any) -> str:
    if v is None:
        return ""
    return str(v).strip()


def resolve_cert_path() -> Optional[str]:
    cert_path = os.getenv("FUBON_CERT_PATH", "").strip()
    if not cert_path:
        return None

    candidates = []

    # 原始值
    candidates.append(cert_path)

    # 若是相對路徑，補 cwd
    if not os.path.isabs(cert_path):
        candidates.append(os.path.abspath(cert_path))
        candidates.append(os.path.abspath(os.path.join(os.getcwd(), cert_path)))

    # 常見 Render / 專案路徑
    base_dirs = [
        os.getcwd(),
        "/opt/render/project/src",
        "/opt/render/project/src/backend",
        "/opt/render/project/src/backend/certs",
        "/opt/render/project/src/certs",
    ]

    filename = os.path.basename(cert_path)
    for base in base_dirs:
        candidates.append(os.path.join(base, cert_path))
        candidates.append(os.path.join(base, filename))
        candidates.append(os.path.join(base, "certs", filename))
        candidates.append(os.path.join(base, "backend", "certs", filename))

    checked = []
    seen = set()

    for p in candidates:
        rp = os.path.abspath(p)
        if rp in seen:
            continue
        seen.add(rp)

        exists = os.path.exists(rp)
        is_file = os.path.isfile(rp)
        checked.append({"path": rp, "exists": exists, "is_file": is_file})

        if exists and is_file:
            return rp

    return None


def get_env_debug_info() -> Dict[str, Any]:
    original_cert = os.getenv("FUBON_CERT_PATH", "").strip()
    resolved = resolve_cert_path()

    candidate_paths = []
    if original_cert:
        base_dirs = [
            os.getcwd(),
            "/opt/render/project/src",
            "/opt/render/project/src/backend",
            "/opt/render/project/src/backend/certs",
            "/opt/render/project/src/certs",
        ]
        filename = os.path.basename(original_cert)

        raw_candidates = [
            original_cert,
            os.path.abspath(original_cert),
            os.path.abspath(os.path.join(os.getcwd(), original_cert)),
        ]

        for base in base_dirs:
            raw_candidates.extend(
                [
                    os.path.join(base, original_cert),
                    os.path.join(base, filename),
                    os.path.join(base, "certs", filename),
                    os.path.join(base, "backend", "certs", filename),
                ]
            )

        seen = set()
        for p in raw_candidates:
            rp = os.path.abspath(p)
            if rp in seen:
                continue
            seen.add(rp)
            candidate_paths.append(
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
        "has_FUBON_CERT_PATH": bool(original_cert),
        "has_FUBON_CERT_PWD": bool(os.getenv("FUBON_CERT_PASSWORD") or os.getenv("FUBON_CERT_PWD")),
        "FUBON_CERT_PATH": original_cert,
        "resolved_cert_path": resolved,
        "cwd": os.getcwd(),
        "using_pwd_key": "FUBON_PASSWORD" if os.getenv("FUBON_PASSWORD") else ("FUBON_PWD" if os.getenv("FUBON_PWD") else None),
        "using_cert_pwd_key": "FUBON_CERT_PASSWORD" if os.getenv("FUBON_CERT_PASSWORD") else ("FUBON_CERT_PWD" if os.getenv("FUBON_CERT_PWD") else None),
        "checked_paths": candidate_paths,
    }


def ensure_fubon_sdk():
    global _sdk, _login_info, _marketdata_ready

    if _sdk is not None and _marketdata_ready:
        return _sdk

    fubon_id = os.getenv("FUBON_ID", "").strip()
    fubon_pwd = (os.getenv("FUBON_PASSWORD") or os.getenv("FUBON_PWD") or "").strip()
    cert_pwd = (os.getenv("FUBON_CERT_PASSWORD") or os.getenv("FUBON_CERT_PWD") or "").strip()
    cert_path = resolve_cert_path()

    if not fubon_id or not fubon_pwd or not cert_path or not cert_pwd:
        raise Exception("FUBON 環境變數未設定完整")

    try:
        from fubon_neo.sdk import FubonSDK
    except Exception as e:
        raise Exception(f"無法 import fubon_neo.sdk.FubonSDK: {e}")

    if _sdk is None:
        _sdk = FubonSDK()

    if _login_info is None:
        _login_info = _sdk.login(fubon_id, fubon_pwd, cert_path, cert_pwd)

    is_success = getattr(_login_info, "is_success", False)
    if not is_success:
        message = getattr(_login_info, "message", "unknown login error")
        raise Exception(f"Fubon SDK login failed: {message}")

    # 關鍵修正：login 後初始化行情
    if not _marketdata_ready:
        _sdk.init_realtime()
        _marketdata_ready = True

    return _sdk


def get_stock_rest_client():
    sdk = ensure_fubon_sdk()

    if not hasattr(sdk, "marketdata") or sdk.marketdata is None:
        raise Exception("sdk.marketdata 不存在，請確認是否已執行 sdk.init_realtime()")

    if not hasattr(sdk.marketdata, "rest_client") or sdk.marketdata.rest_client is None:
        raise Exception("sdk.marketdata.rest_client 不存在")

    stock_client = getattr(sdk.marketdata.rest_client, "stock", None)
    if stock_client is None:
        raise Exception("sdk.marketdata.rest_client.stock 不存在")

    return stock_client


def _extract_rows_from_any_response(resp: Any) -> List[Dict[str, Any]]:
    # dict
    if isinstance(resp, dict):
        for key in ["data", "items", "rows", "result", "quotes"]:
            val = resp.get(key)
            if isinstance(val, list):
                return val
            if isinstance(val, dict):
                for subkey in ["data", "items", "rows", "quotes"]:
                    subval = val.get(subkey)
                    if isinstance(subval, list):
                        return subval

    # object with .data
    if hasattr(resp, "data"):
        data = getattr(resp, "data")
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            for key in ["data", "items", "rows", "quotes"]:
                val = data.get(key)
                if isinstance(val, list):
                    return val

    # already list
    if isinstance(resp, list):
        return resp

    return []


def get_sdk_market_snapshot(market: str = "TSE") -> List[Dict[str, Any]]:
    stock_client = get_stock_rest_client()

    errors = []

    # 1) snapshot.quotes
    try:
        if hasattr(stock_client, "snapshot") and stock_client.snapshot is not None:
            snapshot_obj = stock_client.snapshot
            if hasattr(snapshot_obj, "quotes"):
                resp = snapshot_obj.quotes(market=market)
                rows = _extract_rows_from_any_response(resp)
                if rows:
                    return rows
                errors.append("snapshot.quotes 有回應但解析不到資料")
            else:
                errors.append("stock_client.snapshot.quotes 不存在")
        else:
            errors.append("stock_client.snapshot 不存在")
    except Exception as e:
        errors.append(f"snapshot.quotes 失敗: {e}")

    # 2) intraday.tickers
    try:
        if hasattr(stock_client, "intraday") and stock_client.intraday is not None:
            intraday_obj = stock_client.intraday
            if hasattr(intraday_obj, "tickers"):
                resp = intraday_obj.tickers(market=market)
                rows = _extract_rows_from_any_response(resp)
                if rows:
                    return rows
                errors.append("intraday.tickers 有回應但解析不到資料")
            else:
                errors.append("stock_client.intraday.tickers 不存在")
        else:
            errors.append("stock_client.intraday 不存在")
    except Exception as e:
        errors.append(f"intraday.tickers 失敗: {e}")

    raise Exception("；".join(errors) if errors else "找不到可用的 market snapshot 方法")


def parse_fubon_row(row: Dict[str, Any], market_label: str) -> Optional[Dict[str, Any]]:
    if not isinstance(row, dict):
        return None

    symbol = (
        normalize_code(row.get("symbol"))
        or normalize_code(row.get("stockNo"))
        or normalize_code(row.get("stock_no"))
        or normalize_code(row.get("code"))
        or normalize_code(row.get("ticker"))
    )

    name = (
        str(row.get("name", "")).strip()
        or str(row.get("stockName", "")).strip()
        or str(row.get("stock_name", "")).strip()
    )

    price = safe_float(
        row.get("closePrice", None)
        if row.get("closePrice", None) not in (None, "", "-", "--")
        else row.get("lastPrice", None)
    )

    if price <= 0:
        price = safe_float(row.get("lastPrice"))
    if price <= 0:
        price = safe_float(row.get("tradePrice"))
    if price <= 0:
        price = safe_float(row.get("price"))
    if price <= 0:
        price = safe_float(row.get("currentPrice"))

    change = safe_float(row.get("change"))
    if change == 0:
        change = safe_float(row.get("priceChange"))
    if change == 0:
        change = safe_float(row.get("changePrice"))

    change_percent = safe_float(row.get("changePercent"))
    if change_percent == 0 and price > 0 and change != 0:
        prev_close = price - change
        if prev_close > 0:
            change_percent = (change / prev_close) * 100

    volume = safe_int(
        row.get("tradeVolume", None)
        if row.get("tradeVolume", None) not in (None, "", "-", "--")
        else row.get("volume", None)
    )
    if volume == 0:
        volume = safe_int(row.get("totalVolume"))
    if volume == 0:
        volume = safe_int(row.get("accumulatedVolume"))

    open_price = safe_float(row.get("openPrice"))
    high_price = safe_float(row.get("highPrice"))
    low_price = safe_float(row.get("lowPrice"))
    prev_close = safe_float(row.get("previousClose"))
    if prev_close <= 0 and price > 0 and change != 0:
        prev_close = price - change

    update_time = (
        str(row.get("lastUpdated", "")).strip()
        or str(row.get("updateTime", "")).strip()
        or str(row.get("dateTime", "")).strip()
        or str(row.get("time", "")).strip()
    )

    if not symbol or price <= 0:
        return None

    score = round(abs(change_percent) * 10 + min(volume / 100000, 50), 2)

    return {
        "market": market_label,
        "symbol": symbol,
        "name": name or symbol,
        "price": round(price, 2),
        "change": round(change, 2),
        "change_percent": round(change_percent, 2),
        "volume": volume,
        "score": score,
        "prev_close": round(prev_close, 2) if prev_close > 0 else 0,
        "open": round(open_price, 2) if open_price > 0 else 0,
        "high": round(high_price, 2) if high_price > 0 else 0,
        "low": round(low_price, 2) if low_price > 0 else 0,
        "update_time": update_time,
    }


def fetch_market_stocks(market_code: str, market_label: str) -> List[Dict[str, Any]]:
    rows = get_sdk_market_snapshot(market_code)
    stocks: List[Dict[str, Any]] = []

    for row in rows:
        item = parse_fubon_row(row, market_label)
        if item:
            stocks.append(item)

    # 去重
    dedup = {}
    for s in stocks:
        dedup[s["symbol"]] = s

    return list(dedup.values())


def get_all_stocks() -> List[Dict[str, Any]]:
    all_stocks: List[Dict[str, Any]] = []

    try:
        all_stocks.extend(fetch_market_stocks("TSE", "上市"))
    except Exception:
        pass

    try:
        all_stocks.extend(fetch_market_stocks("OTC", "上櫃"))
    except Exception:
        pass

    dedup = {}
    for s in all_stocks:
        dedup[s["symbol"]] = s

    stocks = list(dedup.values())

    # 排序：先看分數，再看成交量
    stocks.sort(key=lambda x: (x.get("score", 0), x.get("volume", 0)), reverse=True)
    return stocks


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
        global _sdk, _login_info, _marketdata_ready

        sdk = ensure_fubon_sdk()

        return {
            "success": True,
            "sdk_type": str(type(sdk)),
            "login_info_type": str(type(_login_info)),
            "login_info": str(_login_info),
            "marketdata_ready": _marketdata_ready,
            "has_marketdata": hasattr(sdk, "marketdata") and sdk.marketdata is not None,
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
            "sdk_type": str(type(sdk)),
            "has_marketdata": marketdata is not None,
            "marketdata_type": str(type(marketdata)) if marketdata is not None else None,
            "has_rest_client": rest_client is not None,
            "rest_client_type": str(type(rest_client)) if rest_client is not None else None,
            "has_stock_client": stock_client is not None,
            "stock_client_type": str(type(stock_client)) if stock_client is not None else None,
            "stock_client_dir": dir(stock_client) if stock_client is not None else [],
            "snapshot_dir": dir(stock_client.snapshot) if getattr(stock_client, "snapshot", None) else [],
            "intraday_dir": dir(stock_client.intraday) if getattr(stock_client, "intraday", None) else [],
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "trace": traceback.format_exc(),
        }


@app.get("/debug-snapshot")
def debug_snapshot(market: str = "TSE"):
    try:
        rows = get_sdk_market_snapshot(market)
        preview = rows[:5] if isinstance(rows, list) else []

        return {
            "success": True,
            "market": market,
            "count": len(rows) if isinstance(rows, list) else 0,
            "preview": preview,
        }
    except Exception as e:
        return {
            "success": False,
            "market": market,
            "error": str(e),
            "trace": traceback.format_exc(),
        }


@app.get("/stocks")
def get_stocks():
    try:
        stocks = get_all_stocks()

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
