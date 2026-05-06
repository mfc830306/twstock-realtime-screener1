import os
import json
import urllib.request
import math
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional, Tuple

from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

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
    "message": "",
}
_RECOMMENDATION_CACHE: Dict[str, Any] = {
    "items": None,
    "data_date": "",
    "last_update": "",
    "top_n": 0,
}
CACHE_SECONDS = 30

# 驗證系統 - Upstash Redis
UPSTASH_REDIS_REST_URL   = os.getenv("UPSTASH_REDIS_REST_URL", "").strip()
UPSTASH_REDIS_REST_TOKEN = os.getenv("UPSTASH_REDIS_REST_TOKEN", "").strip()
UPSTASH_REDIS_KEY        = "twstock:validation_runs"
VALIDATION_STORE_PATH    = os.getenv(
    "VALIDATION_STORE_PATH",
    os.path.join(os.getcwd(), "validation_runs.json"),
)
ADMIN_SECRET = os.getenv("ADMIN_SECRET", "").strip()


TZ_TAIPEI = timezone(timedelta(hours=8))
RECOMMENDATION_SEED_LIMIT = 120



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


def normalize_date_key(v: Any) -> str:
    s = safe_str(v)
    if not s:
        return ""
    digits = "".join(ch for ch in s if ch.isdigit())
    return digits[:8] if len(digits) >= 8 else ""


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


def get_market_status_text() -> str:
    now = now_taipei()
    if now.weekday() >= 5:
        return "休市"
    minutes = now.hour * 60 + now.minute
    if 9 * 60 <= minutes <= 13 * 60 + 30:
        return "開盤"
    if minutes > 13 * 60 + 30:
        return "收盤"
    return "休市"


def should_settle_recommendations(market_status: Optional[str] = None) -> bool:
    status = market_status or get_market_status_text()
    return status != "開盤"


def build_recommendation_settlement_info(market_status: Optional[str] = None) -> Dict[str, str]:
    status = market_status or get_market_status_text()
    if should_settle_recommendations(status):
        return {
            "recommendation_status": "after_close_settlement",
            "recommendation_message": "推薦10檔以最近一次收盤後完整資料結算，適合隔日觀察或進場前追蹤。",
        }
    return {
        "recommendation_status": "intraday_paused",
        "recommendation_message": "盤中暫停結算推薦10檔，避免半日成交量與未完成日K影響名單；請收盤後再更新。",
    }


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


def format_price_value(v: float) -> str:
    if v <= 0:
        return ""
    rounded = round(v, 2)
    if abs(rounded - int(rounded)) < 0.001:
        return str(int(rounded))
    return f"{rounded:.2f}"


def calc_position_ratio(price: float, high_price: float, low_price: float) -> float:
    if high_price > low_price:
        ratio = (price - low_price) / (high_price - low_price)
        return max(0.0, min(ratio, 1.0))
    return 0.5


def calc_amplitude_pct(high_price: float, low_price: float, previous_close: float) -> float:
    intraday_range = max(high_price - low_price, 0.0)
    if previous_close > 0:
        return (intraday_range / previous_close) * 100
    return 0.0


def avg(values: List[float]) -> float:
    if not values:
        return 0.0
    return sum(values) / len(values)


def market_session_progress() -> float:
    now = now_taipei()
    if now.weekday() >= 5:
        return 1.0
    open_minutes = 9 * 60
    close_minutes = 13 * 60 + 30
    current_minutes = now.hour * 60 + now.minute
    if current_minutes <= open_minutes:
        return 0.05
    if current_minutes >= close_minutes:
        return 1.0
    return clamp((current_minutes - open_minutes) / (close_minutes - open_minutes), 0.05, 1.0)


def estimate_full_day_volume(current_volume: int) -> int:
    if current_volume <= 0:
        return 0
    status = get_market_status_text()
    if status != "開盤":
        return current_volume
    progress = market_session_progress()
    return int(current_volume / max(progress, 0.05))


def completed_candles_for_reference(candles: List[Dict[str, Any]], base_stock: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    if not candles:
        return []
    snapshot_date_key = normalize_date_key((base_stock or {}).get("update_time"))
    last_date_key = normalize_date_key(candles[-1].get("date"))
    if snapshot_date_key and last_date_key and snapshot_date_key >= last_date_key:
        return candles[:-1] if len(candles) > 1 else candles
    if get_market_status_text() == "開盤" and len(candles) > 1:
        return candles[:-1]
    return candles


def clamp(v: float, low: float, high: float) -> float:
    return max(low, min(v, high))


def score_band(value: float, low: float, high: float, peak: float, full_score: float) -> float:
    if value < low or value > high:
        return 0.0
    if value == peak:
        return full_score
    if value < peak:
        width = max(peak - low, 1e-9)
        return full_score * ((value - low) / width)
    width = max(high - peak, 1e-9)
    return full_score * ((high - value) / width)


def is_main_board_stock(s: Dict[str, Any]) -> bool:
    return safe_str(s.get("market")) in ("上市", "上櫃")


def is_valid_main_board_symbol(symbol: str, name: str) -> bool:
    s = safe_str(symbol).upper()
    n = safe_str(name).upper()
    if not s or len(s) != 4 or not s.isdigit():
        return False
    if s.startswith("00") or "ETF" in n:
        return False
    return True


def merge_stock_lists(*groups: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    dedup: Dict[str, Dict[str, Any]] = {}
    for group in groups:
        for item in group:
            symbol = safe_str(item.get("symbol"))
            if not symbol:
                continue
            dedup[symbol] = item
    return list(dedup.values())


def calc_pct(base: float, price: float) -> float:
    if base <= 0 or price <= 0:
        return 0.0
    return round(((price - base) / base) * 100, 2)


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
        raise Exception(
            f"Fubon SDK login failed: {getattr(_login_info, 'message', 'unknown error')}"
        )

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


# =========================
# Snapshot 短線型態
# =========================
def build_signal_and_reason(
    price: float,
    change: float,
    change_percent: float,
    volume: int,
    high_price: float,
    low_price: float,
    open_price: float,
    previous_close: float,
) -> Dict[str, str]:
    amplitude_pct = calc_amplitude_pct(high_price, low_price, previous_close)
    close_position = calc_position_ratio(price, high_price, low_price)
    vol_k = volume / 1000

    if 0.8 <= change_percent <= 4.2 and 0.48 <= close_position <= 0.82 and price >= open_price:
        return {
            "signal": "量增轉強",
            "reason": (
                f"今日漲幅 {change_percent:.2f}% 屬溫和轉強區間，收盤位置比 {close_position:.0%}，"
                f"成交量 {vol_k:.0f}K 張，屬短線資金開始進場但尚未過熱的型態。"
                "這類型股票較符合 2~4 天延續上攻的節奏。"
            ),
        }

    if 0.3 <= change_percent <= 3.2 and 0.42 <= close_position <= 0.74 and amplitude_pct <= 4.8:
        return {
            "signal": "整理待發",
            "reason": (
                f"今日小幅墊高 {change_percent:.2f}%，振幅 {amplitude_pct:.2f}%，"
                "價格仍在可攻擊區而非情緒高點，屬整理後準備表態型。"
            ),
        }

    if change_percent >= 4.8 and close_position >= 0.86:
        return {
            "signal": "短線過熱",
            "reason": (
                f"今日漲幅 {change_percent:.2f}% 已偏大，且收盤逼近高點（位置比 {close_position:.0%}），"
                "雖然強勢，但較像已經發動後段，追價風險提升。"
            ),
        }

    if price > open_price and 0.4 <= change_percent <= 3.8 and 0.45 <= close_position <= 0.8:
        return {
            "signal": "穩步走高",
            "reason": (
                "價格維持溫和上行，盤中承接力尚可，未見急拉急殺，"
                "屬短線可觀察續強的健康結構。"
            ),
        }

    if -0.8 <= change_percent <= 0.8 and amplitude_pct <= 3.5:
        return {
            "signal": "區間整理",
            "reason": (
                f"今日漲跌幅 {change_percent:+.2f}%，振幅 {amplitude_pct:.2f}%，"
                "股價仍在整理消化階段，需等待下一次量價表態。"
            ),
        }

    if change_percent < 0 and close_position <= 0.35:
        return {
            "signal": "偏弱整理",
            "reason": (
                f"今日收跌 {abs(change_percent):.2f}%，收盤偏低，短線買盤主導性不足，"
                "暫不屬於 2~4 天潛力攻擊型。"
            ),
        }

    return {
        "signal": "觀察中",
        "reason": "目前量價結構沒有明確優勢，先觀察是否出現量增與關鍵價位突破。",
    }


# =========================
# Snapshot 標準化（純資料，不做評分）
# =========================

def normalize_snapshot_row(row: Dict[str, Any], market_label: str) -> Optional[Dict[str, Any]]:
    if not isinstance(row, dict):
        return None
    symbol = safe_str(
        row.get("symbol") or row.get("stockNo") or row.get("stock_no")
        or row.get("code") or row.get("ticker")
    )
    if not symbol:
        return None
    name = safe_str(row.get("name") or row.get("stockName") or row.get("stock_name") or symbol)
    if not is_valid_main_board_symbol(symbol, name):
        return None
    price = safe_float(
        row.get("lastPrice") or row.get("closePrice") or row.get("tradePrice")
        or row.get("price") or row.get("currentPrice")
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
        row.get("tradeVolume") or row.get("volume") or row.get("totalVolume")
        or row.get("accumulatedVolume") or row.get("tradeVolumeAtBid")
    )
    trade_value = safe_int(row.get("tradeValue"))
    open_price  = safe_float(row.get("openPrice"))
    high_price  = safe_float(row.get("highPrice"))
    low_price   = safe_float(row.get("lowPrice"))
    update_time_raw = row.get("lastUpdated") or row.get("time") or 0
    update_time_str = micros_to_taipei_str(update_time_raw)
    category = price_category(price)
    # 快速快照評分（給列表用，非完整技術分析）
    close_position = calc_position_ratio(price, high_price, low_price)
    amplitude_pct  = calc_amplitude_pct(high_price, low_price, previous_close)
    signal_info    = build_signal_and_reason(
        price=price, change=change, change_percent=change_percent,
        volume=volume, high_price=high_price, low_price=low_price,
        open_price=open_price, previous_close=previous_close,
    )
    signal = signal_info["signal"]

    # 簡易快照評分
    snap_score = round(max(
        score_band(change_percent, 0.3, 4.5, 2.0, 30)
        + score_band(close_position, 0.4, 0.85, 0.65, 20)
        + score_band(amplitude_pct, 0.8, 6.0, 3.0, 15)
        + score_band(volume, 1000, 50000, 8000, 20)
        + (10 if price >= open_price else 0)
        - (15 if change_percent >= 5 else 0)
        - (10 if close_position >= 0.9 else 0)
    , 0.0), 1)

    # 快速評級
    if signal in {"量增轉強", "整理待發"} and snap_score >= 55:
        op_rating = "A"
    elif signal in {"穩步走高"} and snap_score >= 45:
        op_rating = "B+"
    elif signal in {"短線過熱", "偏弱整理"}:
        op_rating = "D"
    else:
        op_rating = "C"

    plan = build_fixed_trade_plan(price)

    return {
        "market": market_label,
        "symbol": symbol,
        "name": name,
        "price": round(price, 2),
        "change": round(change, 2),
        "change_percent": round(change_percent, 2),
        "volume": volume,
        "trade_value": trade_value,
        "prev_close": round(previous_close, 2) if previous_close > 0 else 0,
        "open": round(open_price, 2),
        "high": round(high_price, 2),
        "low": round(low_price, 2),
        "update_time": update_time_str,
        "update_time_raw": update_time_raw,
        "category": category,
        "signal": signal,
        "trend_type": signal,
        "reason": signal_info["reason"],
        "technical_comment": f"收盤位置 {close_position:.0%}；振幅 {amplitude_pct:.1f}%；量 {volume:,} 張",
        "operation_rating": op_rating,
        "operation_bias": "偏多觀察" if op_rating in {"A", "B+"} else "觀察",
        "operation_style": "2~3天短線",
        "strategy_action": f"收盤後評估，目標 {plan['target_price']}，停損 {plan['stop_loss']}",
        "entry_price": plan["entry_price"],
        "target_price": plan["target_price"],
        "stop_loss": plan["stop_loss"],
        "risk_reward": "固定 2.5% 停損 / 5~6% 停利",
        "risk_note": f"跌破 {plan['stop_loss']} 停損",
        "score": snap_score,
        "recommendation_score": snap_score,
        "setup_score": 0,
        "analysis_source": "snapshot",
    }


# =========================
# Market Data
# =========================

def fetch_snapshot_rows_by_type(
    stock_client: Any, market: str, market_label: str, quote_type: str,
) -> List[Dict[str, Any]]:
    resp = stock_client.snapshot.quotes(market=market, type=quote_type)
    rows = extract_rows(resp)
    result: List[Dict[str, Any]] = []
    for row in rows:
        item = normalize_snapshot_row(row, market_label=market_label)
        if item:
            result.append(item)
    return result


def fetch_snapshot_market(market: str, market_label: str) -> List[Dict[str, Any]]:
    stock_client = get_stock_rest_client()
    try:
        return fetch_snapshot_rows_by_type(
            stock_client=stock_client,
            market=market,
            market_label=market_label,
            quote_type="ALLBUT0999",
        )
    except Exception as e:
        raise Exception(f"{market_label} snapshot 失敗: {e}")


def get_all_stocks_raw() -> Dict[str, Any]:
    all_stocks: List[Dict[str, Any]] = []
    errors: List[str] = []
    for market_code, market_label in [("TSE", "上市"), ("OTC", "上櫃")]:
        try:
            rows = fetch_snapshot_market(market_code, market_label)
            all_stocks.extend(rows)
        except Exception as e:
            errors.append(f"{market_label} 失敗: {e}")
    stocks = merge_stock_lists(all_stocks)
    if not stocks:
        raise Exception("；".join(errors) if errors else "目前無法取得任何市場資料")
    latest_raw = max((safe_int(s.get("update_time_raw")) for s in stocks), default=0)
    data_date  = micros_to_date_str(latest_raw)   if latest_raw else now_taipei().strftime("%Y%m%d")
    last_update = micros_to_taipei_str(latest_raw) if latest_raw else format_dt_taipei(now_taipei())
    return {
        "stocks": stocks,
        "data_date": data_date,
        "last_update": last_update,
        "message": "；".join(errors) if errors else "",
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
            "stocks":      _CACHE["stocks"],
            "data_date":   _CACHE["data_date"],
            "last_update": _CACHE["last_update"],
            "message":     _CACHE.get("message", ""),
        }
    result = get_all_stocks_raw()
    _CACHE["stocks"]      = result["stocks"]
    _CACHE["fetched_at"]  = now
    _CACHE["data_date"]   = result["data_date"]
    _CACHE["last_update"] = result["last_update"]
    _CACHE["message"]     = result.get("message", "")
    return result


def get_cached_recommendations(
    stocks: List[Dict[str, Any]],
    data_date: str,
    last_update: str,
    top_n: int = 10,
) -> List[Dict[str, Any]]:
    if not should_settle_recommendations():
        return []
    cached_items = _RECOMMENDATION_CACHE.get("items")
    if (
        isinstance(cached_items, list)
        and _RECOMMENDATION_CACHE.get("data_date")   == data_date
        and _RECOMMENDATION_CACHE.get("last_update") == last_update
        and _RECOMMENDATION_CACHE.get("top_n")       == top_n
    ):
        return cached_items
    items = build_recommendations(stocks, top_n=top_n)
    # 只快取非空結果，避免空推薦被鎖住
    if items:
        _RECOMMENDATION_CACHE["items"]       = items
        _RECOMMENDATION_CACHE["data_date"]   = data_date
        _RECOMMENDATION_CACHE["last_update"] = last_update
        _RECOMMENDATION_CACHE["top_n"]       = top_n
    return items


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
) -> List[Dict[str, Any]]:
    result = stocks
    market_lower = safe_str(market).lower()
    if market_lower in ("all", ""):
        result = [s for s in result if is_main_board_stock(s)]
    elif market_lower in ("tse", "上市"):
        result = [s for s in result if s.get("market") == "上市"]
    elif market_lower in ("otc", "上櫃"):
        result = [s for s in result if s.get("market") == "上櫃"]
    else:
        result = [s for s in result if is_main_board_stock(s)]
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
    return result


def sort_stocks(
    stocks: List[Dict[str, Any]],
    sort_by: str = "setup_score",
    sort_dir: str = "desc",
) -> List[Dict[str, Any]]:
    reverse = sort_dir.lower() != "asc"
    allowed = {
        "score": "score",
        "setup_score": "setup_score",
        "recommendation_score": "recommendation_score",
        "price": "price",
        "change": "change",
        "change_percent": "change_percent",
        "volume": "volume",
    }
    key = allowed.get(sort_by, "setup_score")
    return sorted(stocks, key=lambda x: x.get(key, 0), reverse=reverse)


def find_focused_stock(filtered: List[Dict[str, Any]], q: str) -> Optional[Dict[str, Any]]:
    qq = safe_str(q).lower()
    if not qq:
        return None
    exact_symbol = [s for s in filtered if safe_str(s.get("symbol")).lower() == qq]
    if len(exact_symbol) == 1:
        return exact_symbol[0]
    exact_name = [s for s in filtered if safe_str(s.get("name")).lower() == qq]
    if len(exact_name) == 1:
        return exact_name[0]
    partial = [
        s for s in filtered
        if qq in safe_str(s.get("symbol")).lower() or qq in safe_str(s.get("name")).lower()
    ]
    if len(partial) == 1:
        return partial[0]
    return None


# =========================
# 交易規則（固定）
# =========================
TAKE_PROFIT_PCT  = 0.05   # 停利 +5%
STOP_LOSS_PCT    = 0.025  # 停損 -2.5%
MAX_HOLD_DAYS    = 3      # 最多持有3天


def build_fixed_trade_plan(price: float) -> Dict[str, str]:
    """固定停利5~6%、停損2.5%、最多持有3天"""
    if price <= 0:
        return {
            "entry_price": "隔日開盤",
            "target_price": "",
            "stop_loss": "",
            "max_hold_days": str(MAX_HOLD_DAYS),
        }
    target_low  = round(price * (1 + TAKE_PROFIT_PCT), 2)
    target_high = round(price * 1.06, 2)
    stop_loss   = round(price * (1 - STOP_LOSS_PCT), 2)
    return {
        "entry_price": "隔日開盤",
        "target_price": f"{target_low} ~ {target_high}",
        "stop_loss": str(stop_loss),
        "max_hold_days": str(MAX_HOLD_DAYS),
    }


# =========================
# K 線分析工具函數
# =========================

_K_CACHE: Dict[str, Dict[str, Any]] = {}  # 當次服務期間的 K 線快取

def positive_min(values: List[float], default: float = 0.0) -> float:
    positives = [x for x in values if x > 0]
    return min(positives) if positives else default


def overlay_snapshot_on_candles(
    candles: List[Dict[str, Any]],
    base_stock: Dict[str, Any],
) -> Tuple[List[Dict[str, Any]], float]:
    if not candles:
        return [], 0.0
    merged = [dict(x) for x in candles]
    snapshot_price     = safe_float(base_stock.get("price"))
    snapshot_volume    = safe_int(base_stock.get("volume"))
    snapshot_prev_close = safe_float(base_stock.get("prev_close"))
    snapshot_open      = safe_float(base_stock.get("open"))
    snapshot_high      = safe_float(base_stock.get("high"))
    snapshot_low       = safe_float(base_stock.get("low"))
    snapshot_date_key  = normalize_date_key(base_stock.get("update_time")) or now_taipei().strftime("%Y%m%d")
    last_candle_date   = normalize_date_key(merged[-1].get("date"))

    if snapshot_price <= 0:
        prev = snapshot_prev_close or (safe_float(merged[-2].get("close")) if len(merged) >= 2 else safe_float(merged[-1].get("close")))
        return merged, prev

    if snapshot_date_key and last_candle_date and snapshot_date_key > last_candle_date:
        prev_close  = snapshot_prev_close if snapshot_prev_close > 0 else safe_float(merged[-1].get("close"))
        open_price  = snapshot_open if snapshot_open > 0 else prev_close
        high_price  = max([x for x in [snapshot_high, snapshot_price, open_price] if x > 0], default=snapshot_price)
        low_price   = positive_min([snapshot_low, snapshot_price, open_price], min(snapshot_price, open_price))
        merged.append({
            "date": snapshot_date_key, "open": open_price, "high": high_price,
            "low": low_price, "close": snapshot_price,
            "volume": snapshot_volume if snapshot_volume > 0 else safe_int(merged[-1].get("volume")),
            "change": round(snapshot_price - prev_close, 2) if prev_close > 0 else 0.0,
        })
        return merged, prev_close

    current    = dict(merged[-1])
    prev_close = snapshot_prev_close if snapshot_prev_close > 0 else (
        safe_float(merged[-2].get("close")) if len(merged) >= 2 else safe_float(current.get("close"))
    )
    c_open  = snapshot_open if snapshot_open > 0 else safe_float(current.get("open"))
    c_high  = max([x for x in [safe_float(current.get("high")), snapshot_high, snapshot_price, c_open] if x > 0], default=snapshot_price)
    c_low   = positive_min([safe_float(current.get("low")), snapshot_low, snapshot_price, c_open],
                           min(snapshot_price, c_open if c_open > 0 else snapshot_price))
    current.update({
        "open": c_open if c_open > 0 else snapshot_price,
        "high": c_high, "low": c_low, "close": snapshot_price,
        "change": round(snapshot_price - prev_close, 2) if prev_close > 0 else safe_float(current.get("change")),
    })
    if snapshot_volume > 0:
        current["volume"] = snapshot_volume
    merged[-1] = current
    return merged, prev_close


def ema(values: List[float], period: int) -> List[float]:
    if not values:
        return []
    alpha  = 2 / (period + 1)
    result = [values[0]]
    for v in values[1:]:
        result.append((v * alpha) + (result[-1] * (1 - alpha)))
    return result


def calc_rsi(closes: List[float], period: int = 14) -> float:
    if len(closes) <= period:
        return 50.0
    gains, losses = [], []
    for i in range(1, len(closes)):
        diff = closes[i] - closes[i - 1]
        gains.append(max(diff, 0))
        losses.append(abs(min(diff, 0)))
    ag = avg(gains[:period])
    al = avg(losses[:period])
    for i in range(period, len(gains)):
        ag = ((ag * (period - 1)) + gains[i]) / period
        al = ((al * (period - 1)) + losses[i]) / period
    return 100.0 if al == 0 else 100 - (100 / (1 + ag / al))


def calc_macd(closes: List[float]) -> Tuple[float, float, float]:
    if len(closes) < 35:
        return 0.0, 0.0, 0.0
    ema12  = ema(closes, 12)
    ema26  = ema(closes, 26)
    macd_s = [a - b for a, b in zip(ema12, ema26)]
    sig_s  = ema(macd_s, 9)
    ml, sl = macd_s[-1], sig_s[-1]
    return ml, sl, ml - sl


def calc_atr(candles: List[Dict[str, Any]], period: int = 14) -> float:
    if len(candles) < 2:
        return 0.0
    trs: List[float] = []
    prev = safe_float(candles[0].get("close"))
    for c in candles[1:]:
        h = safe_float(c.get("high"))
        l = safe_float(c.get("low"))
        cl = safe_float(c.get("close"))
        trs.append(max(h - l, abs(h - prev), abs(l - prev)))
        prev = cl
    return avg(trs[-period:]) if trs else 0.0


def fetch_symbol_daily_candles(symbol: str) -> Dict[str, Any]:
    """取得個股歷史日K，使用記憶體快取避免重複呼叫。"""
    if symbol in _K_CACHE:
        return _K_CACHE[symbol]

    stock_client = get_stock_rest_client()
    to_date   = now_taipei().strftime("%Y-%m-%d")
    from_date = (now_taipei() - timedelta(days=400)).strftime("%Y-%m-%d")

    resp = stock_client.historical.candles(
        **{"symbol": symbol, "from": from_date, "to": to_date, "timeframe": "D", "sort": "asc"}
    )
    rows    = extract_rows(resp)
    candles: List[Dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        candles.append({
            "date":   safe_str(row.get("date")),
            "open":   safe_float(row.get("open")),
            "high":   safe_float(row.get("high")),
            "low":    safe_float(row.get("low")),
            "close":  safe_float(row.get("close")),
            "volume": safe_int(row.get("volume")),
            "change": safe_float(row.get("change")),
        })
    candles = [x for x in candles if x["close"] > 0][-250:]
    data = {"candles": candles}
    _K_CACHE[symbol] = data
    return data


# =========================
# 純技術分析系統
# =========================

def calc_kd(candles: List[Dict[str, Any]], period: int = 9) -> Tuple[float, float]:
    """KD 隨機指標"""
    if len(candles) < period:
        return 50.0, 50.0
    highs  = [safe_float(c.get("high"))  for c in candles]
    lows   = [safe_float(c.get("low"))   for c in candles]
    closes = [safe_float(c.get("close")) for c in candles]
    k, d = 50.0, 50.0
    for i in range(period - 1, len(candles)):
        highest = max(highs[i - period + 1:i + 1])
        lowest  = min(lows[i  - period + 1:i + 1])
        close   = closes[i]
        rsv = ((close - lowest) / (highest - lowest) * 100) if highest != lowest else 50.0
        k = k * 2 / 3 + rsv * 1 / 3
        d = d * 2 / 3 + k   * 1 / 3
    return round(k, 2), round(d, 2)


def detect_candlestick_pattern(candles: List[Dict[str, Any]]) -> Dict[str, Any]:
    """偵測K棒型態（最近2~3根）"""
    if len(candles) < 2:
        return {"pattern": "無", "bias": "中性", "score_bonus": 0}

    def props(c: Dict[str, Any]):
        o  = safe_float(c.get("open"))
        h  = safe_float(c.get("high"))
        l  = safe_float(c.get("low"))
        cl = safe_float(c.get("close"))
        body   = abs(cl - o)
        rng    = (h - l) if h > l else 0.001
        upper  = h - max(o, cl)
        lower  = min(o, cl) - l
        bull   = cl >= o
        return o, h, l, cl, body, rng, upper, lower, bull

    co, ch, cl_l, cc, cbody, crng, cupper, clower, cbull = props(candles[-1])
    po, ph, pl,   pc, pbody, prng, pupper, plower, pbull = props(candles[-2])

    # 長上影線 / 射擊之星
    if cupper >= cbody * 2 and clower <= cbody * 0.5:
        return {"pattern": "長上影線", "bias": "偏空", "score_bonus": -10}

    # 開高走低收黑K
    if co > pc * 1.002 and cc < co and (co - cc) / co > 0.01:
        return {"pattern": "開高走低黑K", "bias": "偏空", "score_bonus": -12}

    # 多方吞噬
    if not pbull and cbull and co <= pc and cc >= po:
        return {"pattern": "多方吞噬", "bias": "偏多", "score_bonus": 10}

    # 空方吞噬
    if pbull and not cbull and co >= pc and cc <= po:
        return {"pattern": "空方吞噬", "bias": "偏空", "score_bonus": -12}

    # 早晨之星（3根）
    if len(candles) >= 3:
        _, _, _, p2c, p2body, p2rng, _, _, p2bull = props(candles[-3])
        if (not p2bull and p2body > p2rng * 0.5
                and pbody < prng * 0.3
                and cbull and cbody > crng * 0.5):
            return {"pattern": "早晨之星", "bias": "偏多", "score_bonus": 12}

    # 錘子線
    if clower >= cbody * 2 and cupper <= cbody * 0.5:
        return {"pattern": "錘子線", "bias": "偏多", "score_bonus": 8}

    # 十字星
    if crng > 0 and cbody / crng < 0.1:
        return {"pattern": "十字星", "bias": "中性", "score_bonus": 0}

    # 紅K收高檔
    if cbull and crng > 0 and (cc - cl_l) / crng >= 0.7:
        return {"pattern": "紅K收高", "bias": "偏多", "score_bonus": 5}

    return {"pattern": "無明顯型態", "bias": "中性", "score_bonus": 0}


def detect_volume_contraction(
    reference_volumes: List[int],
    current_vol: int,
) -> Dict[str, Any]:
    """偵測量縮後放量"""
    if len(reference_volumes) < 5:
        return {"pattern": "資料不足", "score": 0, "vol_ratio": 1.0}

    avg5 = avg(reference_volumes[-5:])
    vol_ratio = (current_vol / avg5) if avg5 > 0 else 1.0

    recent5 = reference_volumes[-5:]
    contracting = sum(
        1 for i in range(1, len(recent5)) if recent5[i] <= recent5[i - 1] * 1.05
    )

    if contracting >= 3 and vol_ratio >= 1.5:
        return {"pattern": "量縮後放量", "score": 25, "vol_ratio": round(vol_ratio, 2)}
    if 1.3 <= vol_ratio <= 3.0:
        return {"pattern": "量穩定放大", "score": 18, "vol_ratio": round(vol_ratio, 2)}
    if vol_ratio > 3.0:
        return {"pattern": "爆量", "score": 5, "vol_ratio": round(vol_ratio, 2)}
    if 0.8 <= vol_ratio < 1.3:
        return {"pattern": "量平穩", "score": 10, "vol_ratio": round(vol_ratio, 2)}
    return {"pattern": "量縮", "score": 0, "vol_ratio": round(vol_ratio, 2)}


def detect_ma_cross(
    closes: List[float],
    fast: int = 5,
    slow: int = 10,
    lookback: int = 5,
) -> Dict[str, Any]:
    """偵測黃金交叉/死亡交叉（近N天）"""
    if len(closes) < slow + lookback:
        return {"cross": "無", "days_ago": 0}

    for days_ago in range(1, lookback + 1):
        end = len(closes) - days_ago + 1
        end_prev = end - 1
        if end < slow or end_prev < slow:
            continue
        curr_fast = avg(closes[end - fast:end])
        curr_slow = avg(closes[end - slow:end])
        prev_fast = avg(closes[end_prev - fast:end_prev])
        prev_slow = avg(closes[end_prev - slow:end_prev])
        if curr_fast > curr_slow and prev_fast <= prev_slow:
            return {"cross": "黃金交叉", "days_ago": days_ago}
        if curr_fast < curr_slow and prev_fast >= prev_slow:
            return {"cross": "死亡交叉", "days_ago": days_ago}
    return {"cross": "無", "days_ago": 0}


def calc_setup_score(
    close: float,
    ma5: float,
    ma10: float,
    ma20: float,
    macd_hist: float,
    prev_macd_hist: float,
    vol_pattern: Dict[str, Any],
    candle_pattern: Dict[str, Any],
    ma_cross: Dict[str, Any],
    change_pct: float,
    prev3_change_pct: float,
    dist_from_ma5_pct: float,
) -> Tuple[float, str, Dict[str, Any]]:
    """
    純技術評分系統（100分制）
    核心邏輯：找出「K棒轉強、股價站上MA5/MA10、
    MA5接近或黃金交叉MA10、成交量放大、MACD剛翻多，但尚未過熱」的股票。

    條件一：股價站上MA5且MA10（25分）
    條件二：MA5接近或黃金交叉MA10（20分）
    條件三：成交量放大（20分）
    條件四：MACD剛翻多（15分）
    條件五：K棒轉強（20分）
    """
    ma_gap_pct = ((ma5 - ma10) / ma10 * 100) if ma10 > 0 else 0
    vol_ratio = vol_pattern.get("vol_ratio", 1.0)

    ma_score = 0.0
    volume_score = 0.0
    macd_score = 0.0
    candle_score = 0.0
    overheat_penalty = 0.0
    overheat_flags: List[str] = []
    fail_reasons: List[str] = []

    if close < ma5:
        fail_reasons.append("跌破5日線")
    if close < ma10:
        fail_reasons.append("跌破10日線")
    if prev3_change_pct > 10:
        fail_reasons.append("近3日漲幅過大")
        overheat_flags.append("近3日漲幅過大")
        overheat_penalty += 18
    if change_pct > 5.2:
        fail_reasons.append("單日漲幅偏大")
        overheat_flags.append("單日漲幅偏大")
        overheat_penalty += 18
    if dist_from_ma5_pct > 8.0:
        fail_reasons.append("距5日線過遠")
        overheat_flags.append("距5日線過遠")
        overheat_penalty += 12
    if ma_cross["cross"] == "死亡交叉":
        fail_reasons.append("5日線死亡交叉10日線")
    if candle_pattern["pattern"] in {"長上影線", "開高走低黑K", "空方吞噬"}:
        fail_reasons.append(f"K棒偏空：{candle_pattern['pattern']}")
    if vol_pattern["pattern"] == "爆量" and candle_pattern.get("bias") != "偏多":
        fail_reasons.append("爆量但K棒未轉強")
        overheat_flags.append("爆量未轉強")
        overheat_penalty += 10

    if fail_reasons:
        return 0.0, "不符條件", {
            "candle_score": 0.0,
            "ma_score": 0.0,
            "volume_score": 0.0,
            "macd_score": 0.0,
            "overheat_penalty": round(overheat_penalty, 1),
            "total_score": 0.0,
            "ma_score_max": 45,
            "volume_score_max": 20,
            "macd_score_max": 15,
            "candle_score_max": 20,
            "ma_gap_pct": round(ma_gap_pct, 2),
            "vol_ratio": round(vol_ratio, 2),
            "dist_from_ma5_pct": round(dist_from_ma5_pct, 2),
            "macd_hist": round(macd_hist, 4),
            "prev_macd_hist": round(prev_macd_hist, 4),
            "overheat_flags": overheat_flags,
            "fail_reasons": fail_reasons,
        }

    # ===== 條件一：股價站上MA5且MA10（25分）=====
    # 兩個都站上才完整
    if close > ma5 and close > ma10:
        ma_score += 20
        # 剛站上（今日站上）加分
        if dist_from_ma5_pct <= 2.0:
            ma_score += 5   # 剛站上不遠，轉折最佳位置

    # ===== 條件二：MA5接近或黃金交叉MA10（20分）=====
    if ma_cross["cross"] == "黃金交叉":
        days = ma_cross["days_ago"]
        if days <= 2:
            ma_score += 20   # 剛發生黃金交叉（最強）
        elif days <= 5:
            ma_score += 15   # 近5天內黃金交叉
    elif -0.5 <= ma_gap_pct <= 1.0:
        ma_score += 12   # MA5接近MA10（即將黃金交叉）
    elif 1.0 < ma_gap_pct <= 3.0:
        ma_score += 8    # MA5略高於MA10（已轉多但未過熱）
    elif ma_gap_pct > 3.0:
        ma_score += 3    # MA5遠高於MA10（可能過熱）
        overheat_penalty += 4
        overheat_flags.append("MA5明顯高於MA10")

    # ===== 條件三：成交量放大（20分）=====
    vol_score_map = {
        "量縮後放量": 20,
        "量穩定放大": 15,
        "量平穩":     8,
        "爆量":       5,
        "量縮":       0,
        "資料不足":   5,
    }
    volume_score = float(vol_score_map.get(vol_pattern["pattern"], 5))
    if vol_ratio > 3.0:
        overheat_penalty += 5
        overheat_flags.append("量能偏爆量")

    # ===== 條件四：MACD剛翻多（15分）=====
    if prev_macd_hist < 0 and macd_hist >= 0:
        macd_score = 15   # 剛翻多（最強訊號）
    elif prev_macd_hist < 0 and macd_hist < 0 and macd_hist > prev_macd_hist:
        macd_score = 10   # 負值縮小，即將翻多
    elif macd_hist > 0 and macd_hist > prev_macd_hist:
        macd_score = 8    # 正值擴大，動能持續
    elif macd_hist > 0:
        macd_score = 4    # 正值但縮小

    # ===== 條件五：K棒轉強（20分）=====
    k_bonus_map = {
        "多方吞噬":   20,
        "早晨之星":   20,
        "錘子線":     15,
        "紅K收高":    10,
        "十字星":      5,
        "無明顯型態":  5,
    }
    candle_score = float(k_bonus_map.get(candle_pattern["pattern"], 5))
    # 今日漲幅適中加分
    if 0.5 <= change_pct <= 3.0:
        candle_score += 3
    candle_score = min(candle_score, 20.0)

    if change_pct > 4.2:
        overheat_penalty += 8
        overheat_flags.append("單日漲幅接近過熱")
    if dist_from_ma5_pct > 5.0:
        overheat_penalty += 6
        overheat_flags.append("離5日線偏遠")

    raw_score = ma_score + volume_score + macd_score + candle_score
    score = round(clamp(raw_score - overheat_penalty, 0.0, 100.0), 1)

    score_breakdown = {
        "candle_score": round(candle_score, 1),
        "ma_score": round(ma_score, 1),
        "volume_score": round(volume_score, 1),
        "macd_score": round(macd_score, 1),
        "overheat_penalty": round(overheat_penalty, 1),
        "total_score": score,
        "ma_score_max": 45,
        "volume_score_max": 20,
        "macd_score_max": 15,
        "candle_score_max": 20,
        "ma_gap_pct": round(ma_gap_pct, 2),
        "vol_ratio": round(vol_ratio, 2),
        "dist_from_ma5_pct": round(dist_from_ma5_pct, 2),
        "macd_hist": round(macd_hist, 4),
        "prev_macd_hist": round(prev_macd_hist, 4),
        "overheat_flags": overheat_flags,
        "fail_reasons": [],
    }

    # ===== 判斷型態 =====
    # 準備轉強：MACD剛翻多或負值縮小，量放大，K棒轉強，漲幅不大
    is_turning = (
        macd_score >= 10
        and change_pct <= 3.0
        and vol_pattern["pattern"] in {"量縮後放量", "量穩定放大"}
        and candle_pattern["bias"] in {"偏多", "中性"}
    )
    # 續攻型：MA5已大於MA10，MACD正值擴大，量穩定，未過熱
    is_continuation = (
        ma5 > ma10
        and ma_gap_pct <= 4.0
        and macd_hist > 0
        and macd_score >= 4
        and vol_pattern["pattern"] in {"量縮後放量", "量穩定放大"}
        and dist_from_ma5_pct <= 5.0
    )

    if score >= 80:
        return score, "準備轉強" if is_turning else "續攻型", score_breakdown
    if score >= 65:
        if is_turning:
            return score, "準備轉強", score_breakdown
        if is_continuation:
            return score, "續攻型", score_breakdown
        return score, "轉強觀察", score_breakdown
    if score >= 50:
        return score, "整理待發", score_breakdown
    return score, "不符條件", score_breakdown


def build_technical_reason(
    name: str,
    stock_type: str,
    setup_score: float,
    close: float,
    ma5: float,
    ma10: float,
    ma20: float,
    macd_hist: float,
    prev_macd_hist: float,
    rsi14: float,
    vol_pattern: Dict[str, Any],
    candle_pattern: Dict[str, Any],
    ma_cross: Dict[str, Any],
    change_pct: float,
    score_breakdown: Dict[str, Any],
    dist_from_ma5_pct: float,
) -> str:
    lines = [f"【{name} 收盤技術篩選｜{stock_type}｜總分 {setup_score}】"]

    # 均線
    ma_desc = f"MA5 {format_price_value(ma5)} / MA10 {format_price_value(ma10)} / MA20 {format_price_value(ma20)}"
    ma_gap_pct = safe_float(score_breakdown.get("ma_gap_pct"))
    lines.append(
        f"均線：現價 {format_price_value(close)} 已站上5日與10日線，{ma_desc}；"
        f"MA5與MA10差距 {ma_gap_pct:+.2f}%，距5日線 {dist_from_ma5_pct:+.2f}%，"
        f"{safe_str(ma_cross.get('cross'), '無')}，均線分 {score_breakdown.get('ma_score', 0)}/45。"
    )

    # MACD
    if prev_macd_hist < 0 and macd_hist >= 0:
        macd_text = f"由負翻正（Hist {prev_macd_hist:.3f} -> {macd_hist:.3f}），屬剛翻多。"
    elif prev_macd_hist < 0 and macd_hist > prev_macd_hist:
        macd_text = f"負值收斂（Hist {prev_macd_hist:.3f} -> {macd_hist:.3f}），翻多前段。"
    elif macd_hist > 0 and macd_hist > prev_macd_hist:
        macd_text = f"正值擴大（Hist {macd_hist:.3f}），多方動能延續。"
    else:
        macd_text = f"Hist {macd_hist:.3f}，動能仍需確認。"
    lines.append(f"MACD：{macd_text}MACD分 {score_breakdown.get('macd_score', 0)}/15。")

    # 量能
    lines.append(
        f"量能：{vol_pattern['pattern']}，量比 {vol_pattern.get('vol_ratio', 0):.2f} 倍；"
        f"量能分 {score_breakdown.get('volume_score', 0)}/20。"
    )

    # K棒
    lines.append(
        f"K棒：{candle_pattern['pattern']}（{candle_pattern['bias']}），今日漲幅 {change_pct:+.2f}%；"
        f"K棒分 {score_breakdown.get('candle_score', 0)}/20。"
    )

    overheat_penalty = safe_float(score_breakdown.get("overheat_penalty"))
    overheat_flags = score_breakdown.get("overheat_flags") or []
    if overheat_penalty > 0:
        lines.append(f"過熱控管：{'、'.join(overheat_flags)}，扣 {overheat_penalty:.1f} 分。")
    else:
        lines.append("過熱控管：單日漲幅、量能與5日線乖離仍在可接受區，未判定過熱。")

    # RSI
    lines.append(f"RSI(14)：{rsi14:.1f}{'，位於健康動能區。' if 50 <= rsi14 <= 70 else '，需留意是否過熱。' if rsi14 > 70 else '。'}")

    return " ".join(lines)


def build_historical_analysis_for_stock(base_stock: Dict[str, Any]) -> Dict[str, Any]:
    try:
        symbol = safe_str(base_stock.get("symbol"))
        if not symbol:
            return base_stock

        data = fetch_symbol_daily_candles(symbol)
        candles = data.get("candles", [])
        if len(candles) < 35:
            return base_stock

        analysis_candles, prev_close = overlay_snapshot_on_candles(candles, base_stock)
        if len(analysis_candles) < 35:
            return base_stock

        closes  = [safe_float(x.get("close"))  for x in analysis_candles]
        volumes = [safe_int(x.get("volume"))    for x in analysis_candles]
        reference_candles = completed_candles_for_reference(analysis_candles, base_stock)
        reference_volumes = [safe_int(x.get("volume")) for x in reference_candles]

        close_now = closes[-1]
        vol_now   = volumes[-1]
        projected_vol_now = estimate_full_day_volume(vol_now)

        ma5  = avg(closes[-5:])
        ma10 = avg(closes[-10:])
        ma20 = avg(closes[-20:])
        rsi14 = calc_rsi(closes, 14)
        macd_line, signal_line, macd_hist = calc_macd(closes)
        atr14 = calc_atr(analysis_candles, 14)
        kd_k, kd_d = calc_kd(analysis_candles)

        # 前一天的 MACD Hist
        prev_closes = closes[:-1]
        _, _, prev_macd_hist = calc_macd(prev_closes) if len(prev_closes) >= 35 else (0, 0, 0)

        # 近3天累積漲幅
        prev3_close = closes[-4] if len(closes) >= 4 else closes[0]
        prev3_change_pct = ((close_now - prev3_close) / prev3_close * 100) if prev3_close > 0 else 0.0

        # 距MA5距離
        dist_from_ma5_pct = ((close_now - ma5) / ma5 * 100) if ma5 > 0 else 0.0

        # 技術指標偵測
        vol_pattern    = detect_volume_contraction(reference_volumes, projected_vol_now)
        candle_pattern = detect_candlestick_pattern(analysis_candles[-3:])
        ma_cross       = detect_ma_cross(closes)

        change_pct = safe_float(base_stock.get("change_percent"))

        # 純技術評分
        setup_score, stock_type, score_breakdown = calc_setup_score(
            close=close_now,
            ma5=ma5,
            ma10=ma10,
            ma20=ma20,
            macd_hist=macd_hist,
            prev_macd_hist=prev_macd_hist,
            vol_pattern=vol_pattern,
            candle_pattern=candle_pattern,
            ma_cross=ma_cross,
            change_pct=change_pct,
            prev3_change_pct=prev3_change_pct,
            dist_from_ma5_pct=dist_from_ma5_pct,
        )

        # 固定交易計畫
        plan = build_fixed_trade_plan(close_now)

        # 分析原因
        reason = build_technical_reason(
            name=safe_str(base_stock.get("name")),
            stock_type=stock_type,
            setup_score=setup_score,
            close=close_now,
            ma5=ma5,
            ma10=ma10,
            ma20=ma20,
            macd_hist=macd_hist,
            prev_macd_hist=prev_macd_hist,
            rsi14=rsi14,
            vol_pattern=vol_pattern,
            candle_pattern=candle_pattern,
            ma_cross=ma_cross,
            change_pct=change_pct,
            score_breakdown=score_breakdown,
            dist_from_ma5_pct=dist_from_ma5_pct,
        )

        # 操作評級
        if stock_type in {"準備轉強", "續攻型"}:
            operation_rating = "A"
            operation_bias   = "偏多進場"
            strategy_action  = f"隔日開盤進場，目標 {plan['target_price']}，停損 {plan['stop_loss']}，最多持有 {MAX_HOLD_DAYS} 天。"
        elif stock_type == "轉強觀察":
            operation_rating = "B+"
            operation_bias   = "觀察等確認"
            strategy_action  = f"觀察隔日是否續量，確認後再進場。停損參考 {plan['stop_loss']}。"
        else:
            operation_rating = "C"
            operation_bias   = "暫不操作"
            strategy_action  = "技術條件尚未完整，先觀察。"

        merged = dict(base_stock)
        merged.update({
            "signal":             stock_type,
            "trend_type":         stock_type,
            "reason":             reason,
            "technical_comment":  (
                f"MA5/{format_price_value(ma5)} MA10/{format_price_value(ma10)} MA20/{format_price_value(ma20)}"
                f"；RSI {rsi14:.1f}；KD {kd_k}/{kd_d}"
                f"；MACD Hist {macd_hist:.3f}；量比 {vol_pattern.get('vol_ratio',0):.2f}x"
                f"；K棒 {candle_pattern['pattern']}；均線 {ma_cross['cross']}"
            ),
            "operation_rating":   operation_rating,
            "operation_bias":     operation_bias,
            "operation_style":    f"2~3天短線平倉",
            "strategy_action":    strategy_action,
            "entry_price":        plan["entry_price"],
            "target_price":       plan["target_price"],
            "stop_loss":          plan["stop_loss"],
            "max_hold_days":      plan["max_hold_days"],
            "risk_reward":        "固定 2.5% 停損 / 5~6% 停利",
            "risk_note":          f"收盤跌破 MA5（{format_price_value(ma5)}）即停損出場。",
            "recommendation_score": setup_score,
            "setup_score":          setup_score,
            "score_breakdown":      score_breakdown,
            "score":                setup_score,
            "stock_type":           stock_type,
            "candlestick_pattern":  candle_pattern["pattern"],
            "candlestick_bias":     candle_pattern["bias"],
            "ma_cross":             ma_cross["cross"],
            "ma_cross_days_ago":    ma_cross["days_ago"],
            "vol_pattern":          vol_pattern["pattern"],
            "vol_ratio":            vol_pattern.get("vol_ratio", 0),
            "ma5_value":            round(ma5, 2),
            "ma10_value":           round(ma10, 2),
            "ma20_value":           round(ma20, 2),
            "rsi14_value":          round(rsi14, 2),
            "kd_k":                 kd_k,
            "kd_d":                 kd_d,
            "macd_hist_value":      round(macd_hist, 4),
            "prev3_change_pct":     round(prev3_change_pct, 2),
            "dist_from_ma5_pct":    round(dist_from_ma5_pct, 2),
            "analysis_source":      "technical_k",
        })
        merged["price"] = round(close_now, 2)
        merged["volume"] = vol_now
        if safe_float(merged.get("prev_close")) <= 0 and prev_close > 0:
            merged["prev_close"] = round(prev_close, 2)
        return merged

    except Exception:
        return base_stock


def build_snapshot_fallback_reason(stock: Dict[str, Any], score: float) -> str:
    """推薦名單不足時，用快照資料補位的說明文字"""
    name      = safe_str(stock.get("name"), safe_str(stock.get("symbol")))
    signal    = safe_str(stock.get("signal"), "收盤快照候選")
    rating    = safe_str(stock.get("operation_rating"), "-")
    price     = safe_float(stock.get("price"))
    change_pct = safe_float(stock.get("change_percent"))
    open_price = safe_float(stock.get("open")) or price
    high_price = safe_float(stock.get("high")) or price
    low_price  = safe_float(stock.get("low"))  or price
    prev_close = safe_float(stock.get("prev_close"))
    volume     = safe_int(stock.get("volume"))
    close_pos  = calc_position_ratio(price, high_price, low_price)
    amp_pct    = calc_amplitude_pct(high_price, low_price, prev_close)
    red_k      = price >= open_price if open_price > 0 else False

    pos_note = (
        "收在日內高檔，尾盤承接力較強" if close_pos >= 0.68
        else "收在日內中段偏上" if close_pos >= 0.5
        else "收盤位置仍不算強"
    )
    vol_note = (
        "量能活絡但未失控" if 500 <= volume <= 30000
        else "量能偏大，需留意隔日震盪" if volume > 30000
        else "量能偏低，需小心觀察"
    )
    k_note = "收紅K，短線買盤佔優" if red_k else "未收紅K，需確認隔日開盤承接"

    return (
        f"【{name} 快照候選｜{signal}｜評級 {rating}｜分數 {score:.1f}】"
        f"今日漲幅 {change_pct:+.2f}%，振幅 {amp_pct:.2f}%，{pos_note}。"
        f"{k_note}；成交量 {volume:,} 張，{vol_note}。"
        "隔日若開盤守住今日中段並維持量能，視為有效續強；"
        "開高走低或跌破今日低點，應降級觀察。"
    )


def get_recommendations_safe(
    stocks: List[Dict[str, Any]],
    data_date: str,
    last_update: str,
    top_n: int = 10,
) -> Tuple[List[Dict[str, Any]], str]:
    """安全包裝 get_cached_recommendations，不讓例外中斷主流程"""
    try:
        return get_cached_recommendations(
            stocks,
            data_date=data_date,
            last_update=last_update,
            top_n=top_n,
        ), ""
    except Exception as exc:
        print(f"recommendation build skipped: {exc}")
        return [], f"推薦10檔暫時無法計算：{exc}"


def build_recommendations(
    stocks: List[Dict[str, Any]],
    top_n: int = 10,
) -> List[Dict[str, Any]]:
    """
    純技術分析選股 - 三層篩選機制
    第一層：setup_score >= 65，完整技術分析
    第二層：setup_score >= 50，放寬條件
    第三層：快照候選補位
    """
    candidates = [
        s for s in stocks
        if is_main_board_stock(s)
        and safe_float(s.get("price")) >= 8
        and safe_int(s.get("volume")) >= 500
        and safe_int(s.get("volume")) <= 150000
        and 0.1 <= safe_float(s.get("change_percent")) <= 5.2
    ]

    def snapshot_prescore(s: Dict[str, Any]) -> float:
        chg    = safe_float(s.get("change_percent"))
        vol    = safe_int(s.get("volume"))
        price  = safe_float(s.get("price"))
        high   = safe_float(s.get("high"))
        low    = safe_float(s.get("low"))
        open_p = safe_float(s.get("open"))
        pos    = calc_position_ratio(price, high, low)
        vol_score = 20 if 500 <= vol <= 30000 else 10 if vol <= 80000 else 0
        chg_score = 20 if 0.5 <= chg <= 4.0 else 10 if chg <= 5.2 else 0
        pos_score = 15 if pos >= 0.65 else 8 if pos >= 0.45 else 0
        red_score = 10 if price >= open_p > 0 else 0
        return vol_score + chg_score + pos_score + red_score

    candidates.sort(key=snapshot_prescore, reverse=True)
    seed_items = candidates[:RECOMMENDATION_SEED_LIMIT]

    result_map: Dict[str, Dict[str, Any]] = {}
    with ThreadPoolExecutor(max_workers=6) as executor:
        future_to_symbol = {
            executor.submit(build_historical_analysis_for_stock, stock): stock["symbol"]
            for stock in seed_items
        }
        for future in as_completed(future_to_symbol):
            symbol = future_to_symbol[future]
            try:
                result_map[symbol] = future.result()
            except Exception:
                original = next((s for s in seed_items if s["symbol"] == symbol), None)
                if original:
                    result_map[symbol] = original

    def rank_key(x: Dict[str, Any]) -> Tuple[float, int, int, int]:
        return (
            safe_float(x.get("setup_score") or x.get("recommendation_score") or x.get("score")),
            1 if x.get("stock_type") == "準備轉強" else 0,
            1 if x.get("operation_rating") in {"A", "B+"} else 0,
            safe_int(x.get("volume")),
        )

    def add_unique(target: List[Dict[str, Any]], source: List[Dict[str, Any]]) -> None:
        seen = {safe_str(item.get("symbol")) for item in target}
        for item in source:
            sym = safe_str(item.get("symbol"))
            if not sym or sym in seen:
                continue
            target.append(item)
            seen.add(sym)
            if len(target) >= top_n:
                break

    # 第一層：嚴格技術條件
    qualified = [
        s for s in result_map.values()
        if safe_float(s.get("setup_score")) >= 65
        and s.get("stock_type") in {"準備轉強", "續攻型", "轉強觀察"}
    ]
    qualified.sort(key=rank_key, reverse=True)
    recommendations: List[Dict[str, Any]] = qualified[:top_n]

    if len(recommendations) >= top_n:
        return recommendations

    # 第二層：放寬條件
    relaxed = [
        s for s in result_map.values()
        if safe_float(s.get("setup_score")) >= 50
        and s.get("stock_type") in {"準備轉強", "續攻型", "轉強觀察", "整理待發"}
        and s.get("candlestick_pattern") not in {"長上影線", "開高走低黑K", "空方吞噬"}
        and s.get("ma_cross") != "死亡交叉"
    ]
    relaxed.sort(key=rank_key, reverse=True)
    add_unique(recommendations, relaxed)

    if len(recommendations) >= top_n:
        return recommendations

    # 第三層：快照候選補位
    snapshot_fallback: List[Dict[str, Any]] = []
    for stock in candidates:
        score  = safe_float(stock.get("recommendation_score") or stock.get("score"))
        signal = safe_str(stock.get("signal"))
        rating = safe_str(stock.get("operation_rating"))
        change_pct = safe_float(stock.get("change_percent"))
        if (
            score >= 45
            and 0.1 <= change_pct <= 5.2
            and signal in {"量增轉強", "整理待發", "穩步走高"}
            and rating in {"A", "B+"}
        ):
            fb = dict(stock)
            fb["setup_score"]          = safe_float(fb.get("setup_score")) or score
            fb["recommendation_score"] = score
            fb["stock_type"]           = fb.get("stock_type") or "收盤快照候選"
            fb["analysis_source"]      = "snapshot_fallback"
            fb["score_breakdown"]      = {
                "candle_score": 8,
                "ma_score": 0,
                "volume_score": 8,
                "macd_score": 0,
                "overheat_penalty": 0,
                "total_score": score,
                "ma_score_max": 45,
                "volume_score_max": 20,
                "macd_score_max": 15,
                "candle_score_max": 20,
                "ma_gap_pct": 0,
                "vol_ratio": 1,
                "dist_from_ma5_pct": 0,
                "macd_hist": 0,
                "prev_macd_hist": 0,
                "overheat_flags": [],
                "fail_reasons": [],
                "note": "快照補位項目，均線與MACD等待歷史K補齊後重算。",
            }
            fb["reason"]               = build_snapshot_fallback_reason(fb, score)
            snapshot_fallback.append(fb)
    snapshot_fallback.sort(key=rank_key, reverse=True)
    add_unique(recommendations, snapshot_fallback)

    return recommendations[:top_n]


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
        "signal": s.get("signal", ""),
        "trend_type": s.get("trend_type", ""),
        "reason": s.get("reason", ""),
        "technical_comment": s.get("technical_comment", ""),
        "operation_rating": s.get("operation_rating", ""),
        "operation_bias": s.get("operation_bias", ""),
        "operation_style": s.get("operation_style", ""),
        "strategy_action": s.get("strategy_action", ""),
        "entry_price": s.get("entry_price", ""),
        "target_price": s.get("target_price", ""),
        "stop_loss": s.get("stop_loss", ""),
        "risk_reward": s.get("risk_reward", ""),
        "risk_note": s.get("risk_note", ""),
        "setup_score": s.get("setup_score", 0),
        "score_breakdown": s.get("score_breakdown", {}),
        "stock_type": s.get("stock_type", ""),
        "candlestick_pattern": s.get("candlestick_pattern", ""),
        "ma_cross": s.get("ma_cross", ""),
        "vol_pattern": s.get("vol_pattern", ""),
        "vol_ratio": s.get("vol_ratio", 0),
        "ma5_value": s.get("ma5_value", 0),
        "ma10_value": s.get("ma10_value", 0),
        "ma20_value": s.get("ma20_value", 0),
        "macd_hist_value": s.get("macd_hist_value", 0),
        "dist_from_ma5_pct": s.get("dist_from_ma5_pct", 0),
        "analysis_source": s.get("analysis_source", "snapshot"),
    }


def build_focused_analysis(stock: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "symbol":               stock.get("symbol", ""),
        "name":                 stock.get("name", ""),
        "market":               stock.get("market", ""),
        "price":                stock.get("price", 0),
        "change":               stock.get("change", 0),
        "change_percent":       stock.get("change_percent", 0),
        "volume":               stock.get("volume", 0),
        "signal":               stock.get("signal", ""),
        "stock_type":           stock.get("stock_type", stock.get("signal", "")),
        "trend_type":           stock.get("trend_type", ""),
        "operation_rating":     stock.get("operation_rating", ""),
        "operation_bias":       stock.get("operation_bias", ""),
        "operation_style":      stock.get("operation_style", "2~3天短線平倉"),
        "technical_comment":    stock.get("technical_comment", ""),
        "analysis":             stock.get("reason", ""),
        "strategy_action":      stock.get("strategy_action", ""),
        "entry_price":          stock.get("entry_price", "隔日開盤"),
        "target_price":         stock.get("target_price", ""),
        "stop_loss":            stock.get("stop_loss", ""),
        "max_hold_days":        stock.get("max_hold_days", str(MAX_HOLD_DAYS)),
        "risk_reward":          stock.get("risk_reward", "固定 2.5% 停損 / 5~6% 停利"),
        "risk_note":            stock.get("risk_note", ""),
        "setup_score":          stock.get("setup_score", 0),
        "candlestick_pattern":  stock.get("candlestick_pattern", ""),
        "candlestick_bias":     stock.get("candlestick_bias", ""),
        "ma_cross":             stock.get("ma_cross", ""),
        "ma_cross_days_ago":    stock.get("ma_cross_days_ago", 0),
        "vol_pattern":          stock.get("vol_pattern", ""),
        "vol_ratio":            stock.get("vol_ratio", 0),
        "ma5_value":            stock.get("ma5_value", 0),
        "ma10_value":           stock.get("ma10_value", 0),
        "ma20_value":           stock.get("ma20_value", 0),
        "rsi14_value":          stock.get("rsi14_value", 0),
        "update_time":          stock.get("update_time", ""),
    }



# =========================
# 驗證系統
# =========================

def _upstash_cmd(*args) -> None:
    """呼叫 Upstash Redis REST API"""
    if not UPSTASH_REDIS_REST_URL or not UPSTASH_REDIS_REST_TOKEN:
        return None
    try:
        body = json.dumps(list(args)).encode("utf-8")
        req  = urllib.request.Request(
            UPSTASH_REDIS_REST_URL,
            data=body,
            headers={
                "Authorization": f"Bearer {UPSTASH_REDIS_REST_TOKEN}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=8) as resp:
            return json.loads(resp.read().decode("utf-8")).get("result")
    except Exception:
        return None


def load_validation_store() -> Dict[str, Any]:
    """讀取驗證資料（優先 Upstash，fallback 本地 JSON）"""
    if UPSTASH_REDIS_REST_URL and UPSTASH_REDIS_REST_TOKEN:
        try:
            raw = _upstash_cmd("GET", UPSTASH_REDIS_KEY)
            if raw:
                data = json.loads(raw)
                if isinstance(data, dict):
                    data.setdefault("runs", {})
                    return data
            return {"runs": {}}
        except Exception:
            # 讀取失敗：回傳哨兵，避免誤寫覆蓋
            return {"runs": {}, "_read_error": True}
    try:
        if not os.path.exists(VALIDATION_STORE_PATH):
            return {"runs": {}}
        with open(VALIDATION_STORE_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return {"runs": {}}
        data.setdefault("runs", {})
        return data
    except Exception:
        return {"runs": {}}


def save_validation_store(store: Dict[str, Any]) -> None:
    """寫入驗證資料（讀取失敗時不寫入，防止覆蓋）"""
    if store.get("_read_error"):
        return
    clean = {k: v for k, v in store.items() if k != "_read_error"}

    if UPSTASH_REDIS_REST_URL and UPSTASH_REDIS_REST_TOKEN:
        try:
            _upstash_cmd("SET", UPSTASH_REDIS_KEY, json.dumps(clean, ensure_ascii=False))
        except Exception:
            pass
        return
    try:
        os.makedirs(os.path.dirname(os.path.abspath(VALIDATION_STORE_PATH)) or ".", exist_ok=True)
        tmp = f"{VALIDATION_STORE_PATH}.tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(clean, f, ensure_ascii=False, indent=2)
        os.replace(tmp, VALIDATION_STORE_PATH)
    except Exception:
        pass


def create_validation_run(
    date_key: str,
    recommendations: List[Dict[str, Any]],
    last_update: str,
) -> Dict[str, Any]:
    """收盤後保存推薦10檔，等隔日開盤填入進場價"""
    items = []
    for i, stock in enumerate(recommendations[:10]):
        items.append({
            "rank":               i + 1,
            "symbol":             stock.get("symbol", ""),
            "name":               stock.get("name", ""),
            "signal":             stock.get("signal", ""),
            "operation_rating":   stock.get("operation_rating", ""),
            "setup_score":        safe_float(stock.get("setup_score", stock.get("score", 0))),
            "start_close_price":  safe_float(stock.get("price")),
            # 進場資訊（隔日才填）
            "entry_date":         "",
            "entry_open_price":   0.0,
            # 每日收盤追蹤 { "20260506": 85.0, ... }
            "daily_closes":       {},
            # 計算結果
            "return_from_close_pct": 0.0,
            "latest_return_pct":      0.0,
            "horizon_returns":    {},   # {"1": x, "3": x, "5": x}
        })

    run = {
        "date":       date_key,
        "created_at": format_dt_taipei(now_taipei()),
        "last_update": last_update,
        "items":      items,
    }
    store = load_validation_store()
    if store.get("_read_error"):
        return run
    store["runs"][date_key] = run
    save_validation_store(store)
    return run


def update_validation_run(
    run: Dict[str, Any],
    today_date: str,
    stock_map: Dict[str, Any],
    last_update: str,
) -> Dict[str, Any]:
    """
    每次呼叫 /validation 時更新：
    1. 若隔日第一次 → 填入開盤價（進場價）
    2. 記錄今日收盤
    3. 重算 horizon_returns（1/3/5日）
    """
    run_date = normalize_date_key(run.get("date", ""))
    if not run_date or today_date <= run_date:
        return run

    changed = False
    for item in run.get("items", []):
        symbol = safe_str(item.get("symbol"))
        stock  = stock_map.get(symbol)
        if not stock:
            continue

        price      = safe_float(stock.get("price"))
        open_price = safe_float(stock.get("open")) or price
        if price <= 0:
            continue

        # 步驟1：首次出現 → 記錄進場價
        if not item.get("entry_date"):
            item["entry_date"]       = today_date
            item["entry_open_price"] = open_price
            changed = True

        # 步驟2：記錄今日收盤
        daily_closes: Dict[str, float] = item.setdefault("daily_closes", {})
        if today_date not in daily_closes:
            daily_closes[today_date] = price
            changed = True

        # 步驟3：計算報酬
        start_close = safe_float(item.get("start_close_price"))
        if start_close > 0:
            item["return_from_close_pct"] = calc_pct(start_close, price)

        entry_price = safe_float(item.get("entry_open_price"))
        entry_date  = safe_str(item.get("entry_date"))
        if entry_price > 0 and entry_date:
            # sorted_closes: 進場日起的每日收盤（時間順序）
            # sorted_closes[0] = 進場日收盤
            # sorted_closes[1] = 第1日收盤 → horizon "1"
            # sorted_closes[3] = 第3日收盤 → horizon "3"
            # sorted_closes[5] = 第5日收盤 → horizon "5"
            sorted_closes = [
                v for k, v in sorted(daily_closes.items()) if k >= entry_date
            ]
            if sorted_closes:
                item["latest_return_pct"] = calc_pct(entry_price, sorted_closes[-1])
            horizon_returns: Dict[str, float] = {}
            for h in [1, 3, 5]:
                if len(sorted_closes) > h:
                    horizon_returns[str(h)] = calc_pct(entry_price, sorted_closes[h])
            item["horizon_returns"] = horizon_returns

    if changed:
        run["last_update"] = last_update
        store = load_validation_store()
        if not store.get("_read_error"):
            run_date_key = normalize_date_key(run.get("date", ""))
            store["runs"][run_date_key] = run
            save_validation_store(store)
    return run


def update_all_runs(
    today_date: str,
    stock_map: Dict[str, Any],
    last_update: str,
) -> None:
    """批次更新所有歷史 run（只在 /validation 呼叫）"""
    store = load_validation_store()
    if store.get("_read_error"):
        return
    for date_key, run in list(store["runs"].items()):
        if isinstance(run, dict):
            store["runs"][date_key] = update_validation_run(
                run, today_date, stock_map, last_update
            )
    save_validation_store(store)


def summarize_run(run: Dict[str, Any]) -> Dict[str, Any]:
    """計算單一 run 的4個總結指標"""
    items   = run.get("items", [])
    entered = [x for x in items if safe_float(x.get("entry_open_price")) > 0]

    if not entered:
        return {
            "count": len(items), "entered_count": 0,
            "avg_return_pct": 0.0, "win_rate_pct": 0.0,
            "best": None, "worst": None, "horizon_summary": {},
        }

    # 統一用隔日開盤進場後的最新報酬，不混用推薦日收盤價。
    latest_returns = [safe_float(x.get("latest_return_pct")) for x in entered]
    wins   = [r for r in latest_returns if r > 0]

    best_item  = max(entered, key=lambda x: safe_float(x.get("latest_return_pct")))
    worst_item = min(entered, key=lambda x: safe_float(x.get("latest_return_pct")))

    # Horizon 統計（1/3/5日）
    horizon_summary: Dict[str, Any] = {}
    for h in ["1", "3", "5"]:
        h_rets = [
            safe_float(x.get("horizon_returns", {}).get(h))
            for x in entered
            if x.get("horizon_returns", {}).get(h) is not None
        ]
        if h_rets:
            horizon_summary[h] = {
                "count":        len(h_rets),
                "avg_pct":      round(avg(h_rets), 2),
                "win_rate_pct": round(sum(1 for r in h_rets if r > 0) / len(h_rets) * 100, 2),
            }

    return {
        "count":         len(items),
        "entered_count": len(entered),
        "avg_return_pct": round(avg(latest_returns), 2),
        "win_rate_pct":  round(len(wins) / len(entered) * 100, 2) if entered else 0.0,
        "best":  {"symbol": best_item.get("symbol"), "name": best_item.get("name"),
                  "pct": safe_float(best_item.get("latest_return_pct"))},
        "worst": {"symbol": worst_item.get("symbol"), "name": worst_item.get("name"),
                  "pct": safe_float(worst_item.get("latest_return_pct"))},
        "horizon_summary": horizon_summary,
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


@app.get("/health")
def health():
    return {"status": "ok"}



@app.get("/validation")
def get_validation(
    date: str = Query("latest"),
    force_refresh: bool = Query(False),
):
    """
    驗證追蹤端點：
    - 收盤後自動保存當日推薦10檔
    - 每次呼叫更新所有 run 的追蹤資料
    - 返回指定日期（或最新）的驗證結果
    """
    try:
        result      = get_cached_all_stocks(force_refresh=force_refresh)
        all_stocks  = result["stocks"]
        market_status = get_market_status_text()
        today_date  = normalize_date_key(result["data_date"])
        stock_map   = {safe_str(s.get("symbol")): s for s in all_stocks if safe_str(s.get("symbol"))}

        # 收盤後：保存今日推薦（若尚未保存）
        if should_settle_recommendations(market_status):
            store = load_validation_store()
            if not store.get("_read_error") and today_date and today_date not in store.get("runs", {}):
                recs, _ = get_recommendations_safe(
                    all_stocks,
                    data_date=result["data_date"],
                    last_update=result["last_update"],
                    top_n=10,
                )
                if recs:
                    create_validation_run(today_date, recs, result["last_update"])

            # 更新所有 run（只在 /validation 呼叫）
            update_all_runs(today_date, stock_map, result["last_update"])

        # 取目標日期的 run
        store = load_validation_store()
        runs  = store.get("runs", {})

        if date.lower() in ("latest", "", "auto"):
            target_date = max(runs.keys()) if runs else today_date
        else:
            target_date = normalize_date_key(date) or today_date

        run = runs.get(target_date)
        if run is None:
            latest = max(runs.keys()) if runs else ""
            run = {
                "date":       target_date,
                "created_at": "",
                "last_update": result["last_update"],
                "items":      [],
                "status":     "missing",
                "message":    f"尚未保存 {target_date} 的推薦。收盤後呼叫 /validation 即自動保存。"
                              + (f" 最新日期：{latest}" if latest else ""),
            }

        return {
            "success":       True,
            "market_status": market_status,
            "data_date":     result["data_date"],
            "last_update":   result["last_update"],
            "validation":    run,
            "summary":       summarize_run(run),
            "available_dates": sorted(runs.keys(), reverse=True)[:30],
        }
    except Exception as e:
        return JSONResponse(status_code=500, content={
            "success": False, "error": str(e),
            "trace": traceback.format_exc(),
        })


@app.get("/validation/history")
def get_validation_history(limit: int = Query(60, ge=1, le=365)):
    """所有歷史驗證 run 列表（含摘要）"""
    try:
        store = load_validation_store()
        runs  = store.get("runs", {})
        result = []
        for date_key in sorted(runs.keys(), reverse=True)[:limit]:
            run = runs.get(date_key)
            if not isinstance(run, dict):
                continue
            result.append({
                "date":       run.get("date", date_key),
                "created_at": run.get("created_at", ""),
                "last_update": run.get("last_update", ""),
                "summary":    summarize_run(run),
                "items":      run.get("items", []),
            })
        return {"success": True, "total": len(result), "runs": result}
    except Exception as e:
        return JSONResponse(status_code=500, content={
            "success": False, "error": str(e),
        })


@app.post("/admin/reset-validation")
def reset_validation(secret: str = Query("")):
    """月底清空驗證資料（需帶 ADMIN_SECRET）"""
    if not ADMIN_SECRET or secret != ADMIN_SECRET:
        return JSONResponse(status_code=403, content={"error": "forbidden"})
    try:
        if UPSTASH_REDIS_REST_URL and UPSTASH_REDIS_REST_TOKEN:
            _upstash_cmd("DEL", UPSTASH_REDIS_KEY)
        else:
            save_validation_store({"runs": {}})
        return {"success": True, "message": "驗證資料已清空，下次收盤後重新累積。"}
    except Exception as e:
        return JSONResponse(status_code=500, content={"success": False, "error": str(e)})


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
    force_refresh: bool = Query(False),
    include_recommendations: bool = Query(True),
):
    try:
        result = get_cached_all_stocks(force_refresh=force_refresh)
        all_stocks = result["stocks"]
        market_status = get_market_status_text()
        recommendation_info = build_recommendation_settlement_info(market_status)

        filtered = filter_stocks(
            all_stocks,
            market=market,
            category=category,
            q=q,
            price_min=price_min,
            price_max=price_max,
        )
        filtered = sort_stocks(filtered, sort_by=sort_by, sort_dir=sort_dir)

        total_filtered = len(filtered)
        paged = filtered[offset: offset + limit]

        recs = []
        rec_err = ""
        if (
            include_recommendations
            and
            offset == 0
            and safe_str(market).lower() == "all"
            and safe_str(category).lower() == "all"
            and not q.strip()
            and price_min <= 0
            and price_max <= 0
            and should_settle_recommendations(market_status)
        ):
            recs, rec_err = get_recommendations_safe(
                all_stocks,
                data_date=result["data_date"],
                last_update=result["last_update"],
                top_n=10,
            )
            if rec_err:
                recommendation_info["recommendation_status"] = "recommendation_error"
                recommendation_info["recommendation_message"] = rec_err

        cats = build_categories([s for s in all_stocks if is_main_board_stock(s)])

        focused = find_focused_stock(filtered, q)
        if focused:
            focused = build_historical_analysis_for_stock(focused)
            symbol = focused.get("symbol", "")
            paged = [focused if x.get("symbol") == symbol else x for x in paged]

        twse_total = len([s for s in all_stocks if s.get("market") == "上市"])
        otc_total = len([s for s in all_stocks if s.get("market") == "上櫃"])
        response_message = result.get("message", "")
        if rec_err:
            response_message = "；".join([x for x in [response_message, rec_err] if x])

        return {
            "success": True,
            "market_status": market_status,
            "data_date": result["data_date"],
            "last_update": result["last_update"],
            "message": response_message,
            "recommendation_status": recommendation_info["recommendation_status"],
            "recommendation_message": recommendation_info["recommendation_message"],
            "total": total_filtered,
            "offset": offset,
            "limit": limit,
            "twse_total": twse_total,
            "otc_total": otc_total,
            "all_total": twse_total + otc_total,
            "categories": cats,
            "recommendations": [clean_stock_output(x) for x in recs],
            "focused_stock": build_focused_analysis(focused) if focused else None,
            "stocks": [clean_stock_output(x) for x in paged],
        }
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "error": str(e),
                "trace": traceback.format_exc(),
                "stocks": [],
                "recommendations": [],
                "categories": [],
                "focused_stock": None,
            },
        )
