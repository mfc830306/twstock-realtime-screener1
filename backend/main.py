from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
import os
import base64
import time
from typing import Any, Dict, List, Optional

import requests
from fubon_neo.sdk import FubonSDK

try:
    from fubon_neo.fugle_marketdata.rest.base_rest import FugleAPIError
except Exception:
    FugleAPIError = Exception


app = FastAPI(title="TW Stock Fubon Backend FINAL", version="2.2.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

sdk: Optional[FubonSDK] = None
login_accounts = None
reststock = None
cert_path = "/tmp/fubon_cert.p12"

snapshot_cache: Dict[str, Dict[str, Any]] = {
    "TSE": {"ts": 0, "data": None},
    "OTC": {"ts": 0, "data": None},
}

name_cache: Dict[str, Any] = {"ts": 0, "data": {}}

CACHE_SECONDS = 15
NAME_CACHE_SECONDS = 60 * 60 * 6


def env_required(name: str) -> str:
    val = os.getenv(name)
    if not val:
        raise RuntimeError(f"缺少環境變數: {name}")
    return val


def write_cert() -> None:
    b64 = env_required("FUBON_CERT_BASE64")
    with open(cert_path, "wb") as f:
        f.write(base64.b64decode(b64))


def safe_get(obj: Any, key: str, default=None):
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def to_dict(obj: Any):
    if obj is None:
        return None
    if isinstance(obj, (str, int, float, bool)):
        return obj
    if isinstance(obj, list):
        return [to_dict(x) for x in obj]
    if isinstance(obj, dict):
        return {k: to_dict(v) for k, v in obj.items()}
    if hasattr(obj, "__dict__"):
        return {k: to_dict(v) for k, v in vars(obj).items()}
    return obj


def ensure_fubon() -> None:
    global sdk, login_accounts, reststock

    if sdk is not None and reststock is not None:
        return

    person_id = env_required("FUBON_PERSON_ID")
    password = env_required("FUBON_PASSWORD")
    cert_pwd = env_required("FUBON_CERT_PASSWORD")

    write_cert()

    sdk = FubonSDK()
    res = sdk.login(person_id, password, cert_path, cert_pwd)

    if not safe_get(res, "is_success", False):
        raise RuntimeError(safe_get(res, "message", "登入失敗"))

    login_accounts = safe_get(res, "data", None)

    sdk.init_realtime()
    reststock = sdk.marketdata.rest_client.stock


def fetch_twse() -> Dict[str, str]:
    url = "https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL"
    res = requests.get(url, timeout=20)
    res.raise_for_status()
    data = res.json()
    return {
        str(r.get("Code", "")).strip(): str(r.get("Name", "")).strip()
        for r in data
        if r.get("Code") and r.get("Name")
    }


def fetch_tpex() -> Dict[str, str]:
    urls = [
        "https://www.tpex.org.tw/openapi/v1/tpex_mainboard_daily_close_quotes",
        "https://www.tpex.org.tw/openapi/v1/tpex_esb_latest_statistics",
    ]

    out: Dict[str, str] = {}
    for url in urls:
        try:
            res = requests.get(url, timeout=20)
            res.raise_for_status()
            data = res.json()

            for r in data:
                symbol = str(
                    r.get("SecuritiesCompanyCode", "")
                    or r.get("股票代號", "")
                    or r.get("代號", "")
                ).strip()
                name = str(
                    r.get("CompanyName", "")
                    or r.get("股票名稱", "")
                    or r.get("名稱", "")
                ).strip()

                if symbol and name:
                    out[symbol] = name
        except Exception:
            continue

    return out


def get_name_map(force: bool = False) -> Dict[str, str]:
    now = time.time()
    if (
        not force
        and name_cache["data"]
        and now - name_cache["ts"] < NAME_CACHE_SECONDS
    ):
        return name_cache["data"]

    m: Dict[str, str] = {}
    try:
        m.update(fetch_twse())
    except Exception:
        pass
    try:
        m.update(fetch_tpex())
    except Exception:
        pass

    name_cache["ts"] = now
    name_cache["data"] = m
    return m


def get_name(symbol: str, fallback: str = "", force: bool = False) -> str:
    return get_name_map(force=force).get(str(symbol), fallback)


def build_signal(change_percent: float, volume: int) -> str:
    if change_percent >= 3 and volume >= 1000:
        return "偏多"
    if change_percent <= -3 and volume >= 1000:
        return "偏空"
    return "中性"


def build_reason(change_percent: float, volume: int) -> str:
    if change_percent >= 3 and volume >= 1000:
        return "漲幅擴大且量能活躍，短線偏強"
    if change_percent > 0:
        return "價格維持紅盤，走勢偏穩"
    if change_percent <= -3 and volume >= 1000:
        return "跌幅明顯且量能偏大，短線偏弱"
    if change_percent < 0:
        return "價格走弱，觀察是否止跌"
    return "價格整理中，等待方向明確"


def build_entry_price(price: float) -> str:
    if not price:
        return "-"
    low = round(price * 0.99, 2)
    high = round(price * 1.01, 2)
    return f"{low} ~ {high}"


def build_target_price(price: float, change_percent: float) -> str:
    if not price:
        return "-"
    multiplier = 1.03 if change_percent >= 0 else 1.02
    return str(round(price * multiplier, 2))


def build_stop_loss(price: float) -> str:
    if not price:
        return "-"
    return str(round(price * 0.97, 2))


def normalize(item: Dict[str, Any], market: str):
    symbol = str(safe_get(item, "symbol", "")).strip()
    raw_name = str(safe_get(item, "name", "")).strip()
    name = get_name(symbol, raw_name)

    price = safe_get(item, "lastPrice", None)
    if price in (None, 0, ""):
        price = safe_get(item, "closePrice", 0) or 0

    change = safe_get(item, "change", 0) or 0
    pct = safe_get(item, "changePercent", 0) or 0

    # 修正：snapshot.quotes 的成交量直接在 item.tradeVolume
    vol = safe_get(item, "tradeVolume", 0) or 0

    open_price = safe_get(item, "openPrice", 0) or 0
    high_price = safe_get(item, "highPrice", 0) or 0
    low_price = safe_get(item, "lowPrice", 0) or 0
    last_updated = safe_get(item, "lastUpdated", None)
    ticker_type = safe_get(item, "type", "") or ""

    try:
        score = round(abs(float(pct)) * 10 + float(vol) / 1_000_000, 2)
    except Exception:
        score = 0

    try:
        price_f = round(float(price), 2) if price else 0
        change_f = round(float(change), 2) if change else 0
        pct_f = round(float(pct), 2) if pct else 0
        open_f = round(float(open_price), 2) if open_price else 0
        high_f = round(float(high_price), 2) if high_price else 0
        low_f = round(float(low_price), 2) if low_price else 0
        vol_i = int(vol) if vol else 0
    except Exception:
        price_f, change_f, pct_f, open_f, high_f, low_f, vol_i = 0, 0, 0, 0, 0, 0, 0

    return {
        "market": market,
        "symbol": symbol,
        "name": name,
        "price": price_f,
        "change": change_f,
        "change_percent": pct_f,
        "volume": vol_i,
        "score": score,
        "open": open_f,
        "high": high_f,
        "low": low_f,
        "update_time": str(last_updated) if last_updated is not None else "",
        "type": str(ticker_type),
        "signal": build_signal(pct_f, vol_i),
        "reason": build_reason(pct_f, vol_i),
        "entry_price": build_entry_price(price_f),
        "target_price": build_target_price(price_f, pct_f),
        "stop_loss": build_stop_loss(price_f),
    }


def fetch_snapshot(market: str, force: bool = False):
    ensure_fubon()

    now = time.time()
    cache = snapshot_cache[market]

    if not force and cache["data"] and now - cache["ts"] < CACHE_SECONDS:
        return cache["data"]

    try:
        raw = reststock.snapshot.quotes(market=market, type="ALLBUT0999")
        data = to_dict(raw)
        snapshot_cache[market] = {"ts": now, "data": data}
        return data
    except FugleAPIError as e:
        raise HTTPException(status_code=502, detail=f"富邦 snapshot 讀取失敗: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"snapshot 發生錯誤: {str(e)}")


@app.get("/")
def root():
    return {"msg": "Fubon backend running"}


@app.get("/health")
def health():
    return {
        "success": True,
        "cert_exists": os.path.exists(cert_path),
        "name_cache_count": len(name_cache["data"]) if name_cache["data"] else 0,
    }


@app.get("/refresh-names")
def refresh_names():
    try:
        stock_map = get_name_map(force=True)
        return {
            "success": True,
            "count": len(stock_map),
            "message": "股票名稱表已更新",
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


@app.get("/test-fubon-login")
def login_test():
    try:
        ensure_fubon()

        accounts = []
        if login_accounts:
            for acc in login_accounts:
                accounts.append(
                    {
                        "branch_no": getattr(acc, "branch_no", ""),
                        "account": getattr(acc, "account", ""),
                        "account_type": getattr(acc, "account_type", ""),
                    }
                )

        return {
            "success": True,
            "accounts": accounts,
            "debug": {
                "cert_path": cert_path,
                "file_exists": os.path.exists(cert_path),
                "file_size": os.path.getsize(cert_path) if os.path.exists(cert_path) else 0,
            },
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


@app.get("/fubon-accounts")
def fubon_accounts():
    try:
        ensure_fubon()

        accounts = []
        if login_accounts:
            for acc in login_accounts:
                accounts.append(
                    {
                        "branch_no": getattr(acc, "branch_no", ""),
                        "account": getattr(acc, "account", ""),
                        "account_type": getattr(acc, "account_type", ""),
                    }
                )

        return {"success": True, "accounts": accounts}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/fubon-quote/{symbol}")
def quote(symbol: str):
    try:
        ensure_fubon()
        data = to_dict(reststock.intraday.quote(symbol=symbol))
        if isinstance(data, dict):
            data["name"] = get_name(symbol, data.get("name", ""))
        return {"success": True, "symbol": symbol, "quote": data}
    except FugleAPIError as e:
        raise HTTPException(status_code=502, detail=f"富邦 quote 讀取失敗: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/debug-snapshot/{market}")
def debug_snapshot(market: str):
    try:
        market = market.upper()
        if market not in ("TSE", "OTC"):
            return {"success": False, "error": "market 只能是 TSE 或 OTC"}

        data = fetch_snapshot(market, force=True)
        rows = data.get("data", [])

        return {
            "success": True,
            "market": market,
            "count": len(rows),
            "first_item": rows[0] if rows else None,
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


@app.get("/stocks")
def stocks(
    market: str = Query("ALL", description="ALL / TSE / OTC"),
    min_price: float = Query(0, description="最低股價"),
    max_price: float = Query(999999, description="最高股價"),
    q: str = Query("", description="股票代碼或名稱"),
    sort_by: str = Query("change_percent", description="price / change / change_percent / volume / score"),
    order: str = Query("desc", description="asc / desc"),
    limit: int = Query(50, description="最多回傳筆數"),
    force_refresh: bool = Query(False, description="是否強制刷新報價快取"),
    force_name_refresh: bool = Query(False, description="是否強制刷新名稱表"),
):
    try:
        market = market.upper()
        get_name_map(force=force_name_refresh)

        data: List[Dict[str, Any]] = []

        if market in ("ALL", "TSE"):
            tse = fetch_snapshot("TSE", force=force_refresh)
            for item in tse.get("data", []):
                data.append(normalize(item, "上市"))

        if market in ("ALL", "OTC"):
            otc = fetch_snapshot("OTC", force=force_refresh)
            for item in otc.get("data", []):
                data.append(normalize(item, "上櫃"))

        keyword = q.strip().lower()
        if keyword:
            data = [
                s for s in data
                if keyword in s["symbol"].lower() or keyword in s["name"].lower()
            ]

        data = [s for s in data if min_price <= float(s["price"]) <= max_price]

        allowed_sort_fields = {"price", "change", "change_percent", "volume", "score"}
        if sort_by not in allowed_sort_fields:
            sort_by = "change_percent"

        reverse = order.lower() != "asc"
        data.sort(key=lambda x: x.get(sort_by, 0), reverse=reverse)

        if limit > 0:
            data = data[:limit]

        return {
            "success": True,
            "source": "Fubon + TWSE/TPEx Name Map",
            "market_status": "已連接富邦 API",
            "last_update": str(int(time.time())),
            "total": len(data),
            "stocks": data,
        }

    except HTTPException:
        raise
    except Exception as e:
        return {"success": False, "error": str(e), "total": 0, "stocks": []}


@app.get("/top-recommendations")
def top_recommendations(
    limit: int = Query(10, description="推薦數量"),
    force_refresh: bool = Query(False),
    force_name_refresh: bool = Query(False),
):
    try:
        result = stocks(
            sort_by="score",
            order="desc",
            limit=300,
            force_refresh=force_refresh,
            force_name_refresh=force_name_refresh,
        )

        if not result.get("success"):
            return result

        items = result.get("stocks", [])
        filtered = [s for s in items if s["price"] > 0 and s["volume"] > 0]
        top_list = filtered[:limit]

        return {
            "success": True,
            "total": len(top_list),
            "stocks": top_list,
        }
    except Exception as e:
        return {"success": False, "error": str(e), "total": 0, "stocks": []}
