from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
import os
import base64
import time
from typing import Any, Dict, List, Optional

from fubon_neo.sdk import FubonSDK

try:
    from fubon_neo.fugle_marketdata.rest.base_rest import FugleAPIError
except Exception:
    FugleAPIError = Exception


app = FastAPI(title="TW Stock Fubon Backend", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 正式上線後可改成你的 Vercel 網址
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ===== 全域狀態 =====
sdk: Optional[FubonSDK] = None
login_accounts: Any = None
reststock: Any = None
cert_path = "/tmp/fubon_cert.p12"

snapshot_cache: Dict[str, Dict[str, Any]] = {
    "TSE": {"ts": 0, "data": None},
    "OTC": {"ts": 0, "data": None},
}

CACHE_SECONDS = 15


# ===== 工具函式 =====
def env_required(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"缺少環境變數: {name}")
    return value


def write_cert_file() -> str:
    cert_b64 = env_required("FUBON_CERT_BASE64")
    with open(cert_path, "wb") as f:
        f.write(base64.b64decode(cert_b64))
    return cert_path


def to_dict(obj: Any) -> Any:
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
    return str(obj)


def safe_get(obj: Any, key: str, default=None):
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def ensure_fubon_ready() -> None:
    global sdk, login_accounts, reststock

    if sdk is not None and reststock is not None:
        return

    person_id = env_required("FUBON_PERSON_ID")
    password = env_required("FUBON_PASSWORD")
    cert_password = env_required("FUBON_CERT_PASSWORD")

    write_cert_file()

    sdk = FubonSDK()
    result = sdk.login(person_id, password, cert_path, cert_password)

    is_success = safe_get(result, "is_success", False)
    if not is_success:
        message = safe_get(result, "message", "富邦登入失敗")
        raise RuntimeError(str(message))

    login_accounts = safe_get(result, "data", None)

    # 官方文件流程：登入後建立行情連線，再取 rest client。:contentReference[oaicite:1]{index=1}
    sdk.init_realtime()
    reststock = sdk.marketdata.rest_client.stock


def normalize_stock(item: Dict[str, Any], market_name: str) -> Dict[str, Any]:
    symbol = safe_get(item, "symbol", "")
    name = safe_get(item, "name", "")
    price = (
        safe_get(item, "lastPrice", None)
        or safe_get(item, "closePrice", None)
        or 0
    )
    change = safe_get(item, "change", 0) or 0
    change_percent = safe_get(item, "changePercent", 0) or 0
    volume = safe_get(item, "tradeVolume", 0) or 0
    open_price = safe_get(item, "openPrice", 0) or 0
    high_price = safe_get(item, "highPrice", 0) or 0
    low_price = safe_get(item, "lowPrice", 0) or 0
    last_updated = safe_get(item, "lastUpdated", None)
    ticker_type = safe_get(item, "type", "")

    score = round(
        abs(float(change_percent)) * 8
        + (min(float(volume), 50_000_000) / 1_000_000),
        2,
    )

    return {
        "market": market_name,
        "symbol": str(symbol),
        "name": str(name),
        "price": round(float(price), 2) if price else 0,
        "change": round(float(change), 2),
        "change_percent": round(float(change_percent), 2),
        "volume": int(volume) if volume else 0,
        "score": score,
        "open": round(float(open_price), 2) if open_price else 0,
        "high": round(float(high_price), 2) if high_price else 0,
        "low": round(float(low_price), 2) if low_price else 0,
        "update_time": str(last_updated) if last_updated is not None else "",
        "type": str(ticker_type),
        "signal": build_signal(change_percent, volume),
        "reason": build_reason(change_percent, volume),
        "entry_price": build_entry_price(price),
        "target_price": build_target_price(price, change_percent),
        "stop_loss": build_stop_loss(price),
    }


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


def fetch_snapshot_quotes(market: str, force: bool = False) -> Dict[str, Any]:
    ensure_fubon_ready()

    now = time.time()
    cached = snapshot_cache.get(market, {"ts": 0, "data": None})
    if not force and cached["data"] is not None and (now - cached["ts"] < CACHE_SECONDS):
        return cached["data"]

    try:
        # 官方文件: snapshot.quotes(market='TSE' / 'OTC')，type 可選 ALLBUT099 / COMMONSTOCK。:contentReference[oaicite:2]{index=2}
        raw = reststock.snapshot.quotes(market=market, type="ALLBUT099")
        data = to_dict(raw)
        snapshot_cache[market] = {"ts": now, "data": data}
        return data
    except FugleAPIError as e:
        raise HTTPException(
            status_code=502,
            detail=f"富邦 snapshot 讀取失敗: {str(e)}"
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"snapshot 發生錯誤: {str(e)}"
        )


# ===== 路由 =====
@app.get("/")
def root():
    return {"message": "TW Stock Fubon backend running"}


@app.get("/health")
def health():
    return {
        "success": True,
        "service": "ok",
        "cert_exists": os.path.exists(cert_path),
    }


@app.get("/test-fubon-login")
def test_fubon_login():
    try:
        ensure_fubon_ready()
        return {
            "success": True,
            "accounts": to_dict(login_accounts),
            "debug": {
                "cert_path": cert_path,
                "file_exists": os.path.exists(cert_path),
                "file_size": os.path.getsize(cert_path) if os.path.exists(cert_path) else 0,
            },
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
        }


@app.get("/fubon-accounts")
def fubon_accounts():
    try:
        ensure_fubon_ready()
        return {
            "success": True,
            "accounts": to_dict(login_accounts),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/fubon-quote/{symbol}")
def fubon_quote(symbol: str):
    try:
        ensure_fubon_ready()

        # 官方文件: intraday.quote(symbol='2330')。:contentReference[oaicite:3]{index=3}
        raw = reststock.intraday.quote(symbol=symbol)
        data = to_dict(raw)

        return {
            "success": True,
            "symbol": symbol,
            "quote": data,
        }
    except FugleAPIError as e:
        raise HTTPException(status_code=502, detail=f"富邦 quote 讀取失敗: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/stocks")
def get_stocks(
    market: str = Query("ALL", description="ALL / TSE / OTC"),
    min_price: float = Query(0, description="最低股價"),
    max_price: float = Query(999999, description="最高股價"),
    q: str = Query("", description="股票代碼或名稱"),
    sort_by: str = Query("change_percent", description="price / change / change_percent / volume / score"),
    order: str = Query("desc", description="asc / desc"),
    limit: int = Query(5000, description="最多回傳筆數"),
    force_refresh: bool = Query(False, description="是否強制刷新快取"),
):
    try:
        market = market.upper()

        all_items: List[Dict[str, Any]] = []

        if market in ("ALL", "TSE"):
            tse = fetch_snapshot_quotes("TSE", force=force_refresh)
            tse_list = safe_get(tse, "data", []) or []
            all_items.extend([normalize_stock(x, "上市") for x in tse_list])

        if market in ("ALL", "OTC"):
            otc = fetch_snapshot_quotes("OTC", force=force_refresh)
            otc_list = safe_get(otc, "data", []) or []
            all_items.extend([normalize_stock(x, "上櫃") for x in otc_list])

        keyword = q.strip().lower()
        if keyword:
            all_items = [
                s for s in all_items
                if keyword in s["symbol"].lower() or keyword in s["name"].lower()
            ]

        all_items = [
            s for s in all_items
            if min_price <= float(s["price"]) <= max_price
        ]

        reverse = order.lower() != "asc"
        allowed_sort_fields = {"price", "change", "change_percent", "volume", "score"}
        if sort_by not in allowed_sort_fields:
            sort_by = "change_percent"

        all_items.sort(key=lambda x: x.get(sort_by, 0), reverse=reverse)

        if limit > 0:
            all_items = all_items[:limit]

        market_status = "已連接富邦 API"
        last_update = str(int(time.time()))

        return {
            "success": True,
            "source": "Fubon",
            "market_status": market_status,
            "last_update": last_update,
            "total": len(all_items),
            "stocks": all_items,
        }

    except HTTPException:
        raise
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "total": 0,
            "stocks": [],
        }


@app.get("/top-recommendations")
def top_recommendations(limit: int = Query(10, description="推薦數量")):
    try:
        result = get_stocks(sort_by="score", order="desc", limit=300)
        if not result.get("success"):
            return result

        stocks = result.get("stocks", [])

        filtered = [
            s for s in stocks
            if s["price"] > 0 and s["volume"] > 0
        ]

        top_list = filtered[:limit]

        return {
            "success": True,
            "total": len(top_list),
            "stocks": top_list,
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "total": 0,
            "stocks": [],
        }
