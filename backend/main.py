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
    allow_origins=["*"],   # 先全部開放，之後可改成你的前端網域
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# =========================
# Global SDK cache
# =========================
_fubon_sdk = None
_fubon_login_info = None


# =========================
# Utils
# =========================
def to_float(v: Any, default: float = 0.0) -> float:
    try:
        if v is None:
            return default
        if isinstance(v, (int, float)):
            if math.isnan(v):
                return default
            return float(v)
        s = str(v).strip().replace(",", "")
        if s == "" or s == "-":
            return default
        return float(s)
    except Exception:
        return default


def to_int(v: Any, default: int = 0) -> int:
    try:
        if v is None:
            return default
        if isinstance(v, int):
            return v
        if isinstance(v, float):
            if math.isnan(v):
                return default
            return int(v)
        s = str(v).strip().replace(",", "")
        if s == "" or s == "-":
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
    """
    簡單推薦分數，可依你需求再調整
    """
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


# =========================
# Fubon SDK
# =========================
def get_fubon_sdk():
    """
    初始化並快取富邦 SDK
    需要環境變數：
    FUBON_ID
    FUBON_PWD
    FUBON_CERT_PATH
    FUBON_CERT_PWD
    """
    global _fubon_sdk, _fubon_login_info

    if _fubon_sdk is not None:
        return _fubon_sdk

    fubon_id = os.getenv("FUBON_ID", "").strip()
    fubon_pwd = os.getenv("FUBON_PWD", "").strip()
    fubon_cert_path = os.getenv("FUBON_CERT_PATH", "").strip()
    fubon_cert_pwd = os.getenv("FUBON_CERT_PWD", "").strip()

    if not all([fubon_id, fubon_pwd, fubon_cert_path, fubon_cert_pwd]):
        raise Exception("FUBON 環境變數未設定完整")

    from fubon_neo.sdk import FubonSDK

    sdk = FubonSDK()
    accounts = sdk.login(
        fubon_id,
        fubon_pwd,
        fubon_cert_path,
        fubon_cert_pwd,
    )

    # 官方文件要求：登入後建立行情連線
    sdk.init_realtime()

    _fubon_sdk = sdk
    _fubon_login_info = accounts
    return _fubon_sdk


def extract_rows_from_response(resp: Any) -> List[Dict[str, Any]]:
    """
    兼容 SDK 不同回傳格式
    """
    if resp is None:
        return []

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
        raise Exception("sdk.marketdata 不存在，請確認 login 與 init_realtime 是否成功")

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
    """
    用富邦 SDK 讀整個市場 snapshot
    """
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
    """
    把富邦 snapshot 的欄位整理成前端用格式
    """
    symbol = str(safe_get(row, "symbol", "code", default="")).strip()
    name = str(safe_get(row, "name", default="")).strip()

    if not symbol:
        return None

    price = to_float(
        safe_get(row, "closePrice", "lastPrice", "price", "close", default=0)
    )
    open_price = to_float(safe_get(row, "openPrice", "open", default=0))
    high_price = to_float(safe_get(row, "highPrice", "high", default=0))
    low_price = to_float(safe_get(row, "lowPrice", "low", default=0))
    change = to_float(safe_get(row, "change", default=0))
    change_percent = to_float(safe_get(row, "changePercent", "change_percent", default=0))
    volume = to_int(
        safe_get(row, "tradeVolume", "volume", "totalVolume", default=0)
    )
    prev_close = to_float(
        safe_get(row, "previousClose", "prevClose", "referencePrice", default=0)
    )
    last_updated = safe_get(row, "lastUpdated", "last_update", default="")

    # 若 changePercent 沒有，自己算
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
        "update_time": str(last_updated),
    }


def get_market_stocks_from_fubon(market: str) -> List[Dict[str, Any]]:
    rows = get_sdk_market_snapshot(market)
    stocks: List[Dict[str, Any]] = []

    for row in rows:
        try:
            mapped = map_snapshot_row(row, market)
            if mapped is None:
                continue

            # 過濾明顯異常資料
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
    return {
        "success": True,
        "has_FUBON_ID": bool(os.getenv("FUBON_ID")),
        "has_FUBON_PWD": bool(os.getenv("FUBON_PWD")),
        "has_FUBON_CERT_PATH": bool(os.getenv("FUBON_CERT_PATH")),
        "has_FUBON_CERT_PWD": bool(os.getenv("FUBON_CERT_PWD")),
        "FUBON_CERT_PATH": os.getenv("FUBON_CERT_PATH", ""),
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
    """
    抓上市 + 上櫃
    """
    try:
        tse_stocks = get_market_stocks_from_fubon("TSE")
        otc_stocks = get_market_stocks_from_fubon("OTC")

        stocks = tse_stocks + otc_stocks

        # 排序：分數高的在前面，再看成交量
        stocks.sort(key=lambda x: (x.get("score", 0), x.get("volume", 0)), reverse=True)

        return {
            "success": True,
            "source": "FUBON_SDK",
            "market_status": "即時資料",
            "data_date": "",
            "last_update": "",
            "total": len(stocks),
            "stocks": stocks,
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
    """
    market: TSE / OTC
    """
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
        tse_stocks = get_market_stocks_from_fubon("TSE")
        otc_stocks = get_market_stocks_from_fubon("OTC")
        stocks = tse_stocks + otc_stocks

        stocks.sort(key=lambda x: (x.get("score", 0), x.get("volume", 0)), reverse=True)

        return {
            "success": True,
            "total": min(10, len(stocks)),
            "stocks": stocks[:10],
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
            "message": "Fubon SDK login success"
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "trace": traceback.format_exc()
        }
