import os
import time
import traceback
from typing import Optional, List, Dict, Any

import requests
from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware

# ========= 富邦 SDK =========
try:
    from fubon_neo.sdk import FubonSDK
except Exception:
    FubonSDK = None


app = FastAPI(title="TW Stock Realtime Screener")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ========= 環境變數 =========
FUBON_ID = os.getenv("FUBON_ID", "").strip()
FUBON_PASSWORD = os.getenv("FUBON_PASSWORD", "").strip()
FUBON_CERT_PATH = os.getenv("FUBON_CERT_PATH", "").strip()
FUBON_CERT_PASSWORD = os.getenv("FUBON_CERT_PASSWORD", "").strip()

# ========= 全域快取 =========
sdk = None
sdk_logged_in = False
sdk_login_message = ""
last_login_ts = 0

NAME_CACHE: Dict[str, Dict[str, str]] = {}
LAST_STOCKS_CACHE: Dict[str, Any] = {
    "ts": 0,
    "data": []
}

STOCKS_CACHE_SECONDS = 20


# =========================
# 工具函式
# =========================
def safe_float(v, default=0.0) -> float:
    try:
        if v is None or v == "":
            return default
        if isinstance(v, str):
            v = v.replace(",", "").replace("%", "").strip()
        return float(v)
    except Exception:
        return default


def safe_int(v, default=0) -> int:
    try:
        if v is None or v == "":
            return default
        if isinstance(v, str):
            v = v.replace(",", "").strip()
        return int(float(v))
    except Exception:
        return default


def to_tw_market_label(market_text: str) -> str:
    market_text = (market_text or "").strip().upper()

    if market_text in ["TSE", "TWSE", "上市"]:
        return "上市"
    if market_text in ["OTC", "TPEX", "上櫃"]:
        return "上櫃"
    if market_text in ["ESB", "興櫃"]:
        return "興櫃"
    if market_text in ["ETF"]:
        return "ETF"
    return market_text or "未知"


def normalize_market_for_sdk(market_text: Optional[str]) -> Optional[str]:
    if not market_text:
        return None

    mt = str(market_text).strip().upper()

    if mt in ["TSE", "TWSE", "上市"]:
        return "TSE"
    if mt in ["OTC", "TPEX", "上櫃"]:
        return "OTC"
    if mt in ["ESB", "興櫃"]:
        return "ESB"
    return mt


def guess_is_etf(symbol: str, name: str) -> bool:
    symbol = str(symbol or "").strip().upper()
    name = str(name or "").strip().upper()

    if symbol.startswith("00"):
        return True
    if "ETF" in name:
        return True
    return False


def calc_score(price: float, change: float, change_percent: float, volume: int) -> float:
    cp = abs(change_percent)
    vol_score = min(volume / 50000, 20)
    change_score = min(cp * 8, 80)
    change_abs_score = min(abs(change) * 2, 20)

    score = change_score + vol_score + change_abs_score
    return round(min(score, 100), 2)


def build_signal_and_reason(change: float, change_percent: float, volume: int) -> Dict[str, str]:
    cp = safe_float(change_percent)
    vol = safe_int(volume)

    if cp >= 5:
        signal = "偏多"
        reason = "漲幅擴大且量能活躍，短線偏強"
    elif cp >= 2:
        signal = "偏多"
        reason = "股價走強，漲幅穩定"
    elif cp > -2:
        signal = "中性"
        reason = "價格維持紅綠盤，走勢偏穩"
    elif cp > -5:
        signal = "偏空"
        reason = "股價轉弱，留意賣壓"
    else:
        signal = "偏空"
        reason = "跌幅擴大，短線偏弱"

    if vol > 100000:
        reason += "，成交量明顯放大"

    return {
        "signal": signal,
        "reason": reason
    }


def build_trade_prices(price: float, signal: str) -> Dict[str, str]:
    p = safe_float(price)
    if p <= 0:
        return {
            "entry_price": "-",
            "target_price": "-",
            "stop_loss": "-"
        }

    if signal == "偏多":
        entry_low = round(p * 0.99, 2)
        entry_high = round(p * 1.01, 2)
        target = round(p * 1.03, 2)
        stop_loss = round(p * 0.97, 2)
    elif signal == "偏空":
        entry_low = round(p * 0.98, 2)
        entry_high = round(p * 0.995, 2)
        target = round(p * 0.95, 2)
        stop_loss = round(p * 1.02, 2)
    else:
        entry_low = round(p * 0.995, 2)
        entry_high = round(p * 1.005, 2)
        target = round(p * 1.01, 2)
        stop_loss = round(p * 0.98, 2)

    return {
        "entry_price": f"{entry_low} ~ {entry_high}",
        "target_price": str(target),
        "stop_loss": str(stop_loss),
    }


# =========================
# 名稱快取
# =========================
def load_name_cache():
    global NAME_CACHE

    cache: Dict[str, Dict[str, str]] = {}

    # TWSE 上市名稱
    try:
        twse_url = "https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL"
        res = requests.get(twse_url, timeout=15)
        rows = res.json()
        for row in rows:
            symbol = str(row.get("Code", "")).strip()
            name = str(row.get("Name", "")).strip()
            if symbol:
                cache[symbol] = {
                    "name": name,
                    "market": "上市"
                }
    except Exception:
        pass

    # TPEX 上櫃名稱
    try:
        tpex_url = "https://www.tpex.org.tw/openapi/v1/tpex_mainboard_quotes"
        res = requests.get(tpex_url, timeout=15)
        rows = res.json()
        for row in rows:
            symbol = str(
                row.get("SecuritiesCompanyCode")
                or row.get("股票代號")
                or row.get("Code")
                or ""
            ).strip()
            name = str(
                row.get("CompanyName")
                or row.get("股票名稱")
                or row.get("Name")
                or ""
            ).strip()

            if symbol:
                cache[symbol] = {
                    "name": name,
                    "market": "上櫃"
                }
    except Exception:
        pass

    if cache:
        NAME_CACHE = cache


# =========================
# 富邦 SDK 登入
# =========================
def ensure_sdk_login():
    global sdk, sdk_logged_in, sdk_login_message, last_login_ts

    if sdk_logged_in and time.time() - last_login_ts < 600:
        return True

    if FubonSDK is None:
        sdk_logged_in = False
        sdk_login_message = "fubon_neo 未安裝"
        return False

    if not FUBON_ID or not FUBON_PASSWORD or not FUBON_CERT_PATH or not FUBON_CERT_PASSWORD:
        sdk_logged_in = False
        sdk_login_message = "FUBON 環境變數未設定完整"
        return False

    if not os.path.exists(FUBON_CERT_PATH):
        sdk_logged_in = False
        sdk_login_message = f"憑證不存在: {FUBON_CERT_PATH}"
        return False

    try:
        sdk = FubonSDK()

        login_result = sdk.login(
            FUBON_ID,
            FUBON_PASSWORD,
            FUBON_CERT_PATH,
            FUBON_CERT_PASSWORD
        )

        ok = False
        msg = ""

        try:
            ok = bool(getattr(login_result, "is_success", False))
            msg = str(getattr(login_result, "message", ""))
        except Exception:
            pass

        if not ok:
            try:
                data = getattr(login_result, "data", None)
                if data is not None:
                    ok = True
            except Exception:
                pass

        if ok:
            sdk_logged_in = True
            sdk_login_message = msg or "已登入"
            last_login_ts = time.time()
            return True

        sdk_logged_in = False
        sdk_login_message = msg or "登入失敗"
        return False

    except Exception as e:
        sdk_logged_in = False
        sdk_login_message = f"登入例外: {e}"
        return False


# =========================
# 富邦快照讀取
# =========================
def get_sdk_market_snapshot(market: str) -> List[Dict[str, Any]]:
    if not ensure_sdk_login():
        raise Exception(sdk_login_message or "富邦 SDK 登入失敗")

    market = normalize_market_for_sdk(market) or "TSE"
    last_error = None
    candidates = []

    try:
        candidates.append(sdk.marketdata.rest_client.stock.snapshot.quotes)
    except Exception:
        pass

    try:
        candidates.append(sdk.marketdata.rest.stock.snapshot.quotes)
    except Exception:
        pass

    try:
        candidates.append(sdk.rest_client.stock.snapshot.quotes)
    except Exception:
        pass

    if not candidates:
        raise Exception("找不到可用的 snapshot.quotes 方法")

    for fn in candidates:
        try:
            result = fn(market=market)

            if isinstance(result, dict):
                data = result.get("data") or result.get("items") or result.get("stocks") or []
                if isinstance(data, list):
                    return data

            data = getattr(result, "data", None)
            if isinstance(data, list):
                return data

            if isinstance(result, list):
                return result

        except Exception as e:
            last_error = e
            continue

    raise Exception(f"snapshot 讀取失敗: {last_error}")


# =========================
# 資料轉換
# =========================
def convert_snapshot_item(item: Dict[str, Any], default_market: str) -> Dict[str, Any]:
    symbol = str(item.get("symbol", "")).strip()
    raw_name = str(item.get("name", "")).strip()

    market_label = to_tw_market_label(item.get("market") or default_market)

    name_from_cache = NAME_CACHE.get(symbol, {}).get("name", "")
    market_from_cache = NAME_CACHE.get(symbol, {}).get("market", "")

    name = raw_name or name_from_cache or symbol
    if market_from_cache:
        market_label = market_from_cache

    price = safe_float(item.get("lastPrice", item.get("closePrice", item.get("price", 0))))
    open_price = safe_float(item.get("openPrice", item.get("open", 0)))
    high_price = safe_float(item.get("highPrice", item.get("high", 0)))
    low_price = safe_float(item.get("lowPrice", item.get("low", 0)))
    volume = safe_int(item.get("tradeVolume", item.get("volume", 0)))
    last_updated = item.get("lastUpdated", item.get("update_time", ""))

    change = safe_float(item.get("change", 0))
    change_percent = safe_float(item.get("changePercent", item.get("change_percent", 0)))

    if change == 0 and open_price > 0 and price > 0:
        change = round(price - open_price, 2)

    if change_percent == 0 and price > 0 and change != 0:
        base = price - change
        if base > 0:
            change_percent = round(change / base * 100, 2)

    score = calc_score(price, change, change_percent, volume)
    sr = build_signal_and_reason(change, change_percent, volume)
    tp = build_trade_prices(price, sr["signal"])

    if guess_is_etf(symbol, name):
        market_label = "ETF"

    return {
        "market": market_label,
        "symbol": symbol,
        "name": name,
        "price": round(price, 2),
        "change": round(change, 2),
        "change_percent": round(change_percent, 2),
        "volume": volume,
        "score": score,
        "open": round(open_price, 2),
        "high": round(high_price, 2),
        "low": round(low_price, 2),
        "update_time": str(last_updated),
        "type": item.get("type", "EQUITY"),
        "signal": sr["signal"],
        "reason": sr["reason"],
        "entry_price": tp["entry_price"],
        "target_price": tp["target_price"],
        "stop_loss": tp["stop_loss"],
    }


def fetch_all_stocks_from_fubon() -> List[Dict[str, Any]]:
    all_rows: List[Dict[str, Any]] = []

    for mk in ["TSE", "OTC"]:
        try:
            rows = get_sdk_market_snapshot(mk)
            for row in rows:
                try:
                    all_rows.append(convert_snapshot_item(row, mk))
                except Exception:
                    continue
        except Exception:
            continue

    return all_rows


# =========================
# 啟動時載入名稱快取
# =========================
@app.on_event("startup")
def startup_event():
    try:
        load_name_cache()
    except Exception:
        pass


# =========================
# API
# =========================
@app.get("/")
def root():
    return {"message": "TW Stock Realtime Screener is running"}


@app.get("/health")
def health():
    cert_exists = bool(FUBON_CERT_PATH and os.path.exists(FUBON_CERT_PATH))

    return {
        "success": True,
        "cert_exists": cert_exists,
        "name_cache_count": len(NAME_CACHE),
        "sdk_ready": sdk_logged_in,
        "sdk_message": sdk_login_message
    }


@app.get("/debug-snapshot/{market}")
def debug_snapshot(market: str):
    try:
        market = normalize_market_for_sdk(market) or "TSE"
        rows = get_sdk_market_snapshot(market)

        return {
            "success": True,
            "market": market,
            "count": len(rows),
            "first_item": rows[0] if rows else None
        }
    except Exception as e:
        return {
            "success": False,
            "market": market,
            "error": str(e),
            "trace": traceback.format_exc()
        }


@app.get("/stocks")
def get_stocks(
    limit: int = Query(200, ge=1, le=6000),
    market: Optional[str] = Query(None, description="可選: TSE / OTC / ALL / 上市 / 上櫃 / ETF"),
    search: Optional[str] = Query(None, description="股票代號或名稱搜尋"),
    sort_by: str = Query("score", description="score / change_percent / volume / price / change"),
    sort_order: str = Query("desc", description="asc / desc")
):
    global LAST_STOCKS_CACHE

    try:
        now = time.time()

        use_cache = False
        if LAST_STOCKS_CACHE["data"] and (now - LAST_STOCKS_CACHE["ts"] <= STOCKS_CACHE_SECONDS):
            all_stocks = LAST_STOCKS_CACHE["data"]
            use_cache = True
        else:
            all_stocks = fetch_all_stocks_from_fubon()
            LAST_STOCKS_CACHE = {
                "ts": now,
                "data": all_stocks
            }

        stocks = list(all_stocks)

        if market:
            market_text = str(market).strip().upper()

            if market_text in ["TSE", "TWSE", "上市"]:
                stocks = [s for s in stocks if s.get("market") == "上市"]
            elif market_text in ["OTC", "TPEX", "上櫃"]:
                stocks = [s for s in stocks if s.get("market") == "上櫃"]
            elif market_text in ["ETF"]:
                stocks = [s for s in stocks if s.get("market") == "ETF"]
            elif market_text in ["ALL", "全部"]:
                pass

        if search:
            kw = str(search).strip().lower()
            stocks = [
                s for s in stocks
                if kw in str(s.get("symbol", "")).lower() or kw in str(s.get("name", "")).lower()
            ]

        allowed_sort = {"score", "change_percent", "volume", "price", "change"}
        if sort_by not in allowed_sort:
            sort_by = "score"

        reverse = str(sort_order).lower() != "asc"
        stocks.sort(key=lambda x: safe_float(x.get(sort_by, 0)), reverse=reverse)

        total = len(stocks)
        stocks = stocks[:limit]

        market_status = "已連接富邦 API"
        last_update = str(int(time.time()))

        return {
            "success": True,
            "source": "Fubon + TWSE/TPEX Name Map",
            "market_status": market_status,
            "last_update": last_update,
            "total": total,
            "stocks": stocks,
            "cache_used": use_cache
        }

    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "total": 0,
            "stocks": [],
            "trace": traceback.format_exc()
        }


@app.get("/top-recommendations")
def top_recommendations(
    market: Optional[str] = Query(None, description="可選: TSE / OTC / ALL / 上市 / 上櫃 / ETF"),
    limit: int = Query(10, ge=1, le=50)
):
    try:
        result = get_stocks(
            limit=5000,
            market=market,
            search=None,
            sort_by="score",
            sort_order="desc"
        )

        if not isinstance(result, dict) or not result.get("success"):
            return {
                "success": False,
                "error": "無法取得股票資料",
                "total": 0,
                "stocks": []
            }

        stocks = result.get("stocks", [])

        valid_stocks = []
        for s in stocks:
            try:
                s["score"] = round(float(s.get("score", 0)), 2)
                valid_stocks.append(s)
            except Exception:
                continue

        valid_stocks.sort(key=lambda x: x.get("score", 0), reverse=True)
        top_stocks = valid_stocks[:limit]

        return {
            "success": True,
            "market": market if market else "ALL",
            "total": len(top_stocks),
            "stocks": top_stocks
        }

    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "total": 0,
            "stocks": [],
            "trace": traceback.format_exc()
        }


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=False)
