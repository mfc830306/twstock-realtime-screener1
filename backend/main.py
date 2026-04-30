import os
import json
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
CACHE_SECONDS = 60

_HISTORY_CACHE: Dict[str, Dict[str, Any]] = {}
HISTORY_CACHE_HOURS = 6
HISTORY_CACHE_MAX_SYMBOLS = 400

TZ_TAIPEI = timezone(timedelta(hours=8))
HISTORICAL_K_CANDLES = 250
HISTORICAL_K_CALENDAR_DAYS = 400
RECOMMENDATION_SEED_LIMIT = 80
BOOK_PROXY_MIN_SELECTION_SCORE = 58.0
BOOK_PROXY_STRONG_SELECTION_SCORE = 68.0

VALIDATION_START_DATE = os.getenv("VALIDATION_START_DATE", "latest")
VALIDATION_STORE_PATH = os.getenv("VALIDATION_STORE_PATH", "validation_runs.json")
VALIDATION_HORIZONS = [1, 2, 3, 5, 10]


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


def positive_min(values: List[float], default: float = 0.0) -> float:
    positives = [x for x in values if x > 0]
    return min(positives) if positives else default


def build_signal_rating_key(signal: Any, rating: Any) -> str:
    return f"{safe_str(signal)}|{safe_str(rating)}"


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


def format_price_range(low: float, high: float) -> str:
    low = max(low, 0.01)
    high = max(high, low)
    return f"{format_price_value(low)} ~ {format_price_value(high)}"


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


def parse_range_mid(text: str, fallback: float = 0.0) -> float:
    txt = safe_str(text)
    if not txt:
        return fallback
    txt = txt.replace("突破", "").replace("後再評估", "").strip()
    parts = [p.strip() for p in txt.split("~")]
    nums = []
    for p in parts:
        try:
            nums.append(float(p))
        except Exception:
            pass
    if not nums:
        return fallback
    return sum(nums) / len(nums)


def parse_range_bounds(text: str, fallback: float = 0.0) -> Tuple[float, float]:
    txt = safe_str(text)
    if not txt:
        return fallback, fallback
    txt = txt.replace("突破", "").replace("後再評估", "").strip()
    parts = [p.strip() for p in txt.split("~")]
    nums: List[float] = []
    for p in parts:
        try:
            nums.append(float(p))
        except Exception:
            pass
    if not nums:
        return fallback, fallback
    if len(nums) == 1:
        return nums[0], nums[0]
    return min(nums), max(nums)


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


def format_number(num: float) -> str:
    try:
        if num is None or math.isnan(num):
            return "-"
    except Exception:
        pass
    if abs(num - int(num)) < 0.001:
        return f"{int(num):,}"
    return f"{num:,.2f}"


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


def enrich_reason_with_context(
    base_reason: str,
    price: float,
    open_price: float,
    high_price: float,
    low_price: float,
    change_percent: float,
    volume: int,
    previous_close: float,
) -> str:
    extra: List[str] = []
    pos = calc_position_ratio(price, high_price, low_price)
    amplitude_pct = calc_amplitude_pct(high_price, low_price, previous_close)

    if pos >= 0.85:
        extra.append("收盤偏高，若隔日續量容易轉成追價盤")
    elif 0.5 <= pos <= 0.8:
        extra.append("收盤落在中高區但未過熱，較適合短線續強觀察")
    elif pos <= 0.2:
        extra.append("收盤過低，代表尾盤承接力道不足")

    if price > open_price:
        extra.append("收盤高於開盤，日內買盤略占上風")
    elif price < open_price:
        extra.append("收盤低於開盤，盤中追價延續性較弱")

    if change_percent >= 5:
        extra.append("單日漲幅過大，較不利 2~4 天低風險切入")
    elif 0.8 <= change_percent <= 4:
        extra.append("漲幅屬合理動能區，較符合潛力股模型")

    if volume >= 30000:
        extra.append("量能過大，需小心已經成為市場熱門追價股")
    elif 5000 <= volume <= 20000:
        extra.append("量能活絡但未失控，屬較健康的短線放量")
    elif volume < 2000:
        extra.append("量能仍偏低，後續續攻力道需再確認")

    if amplitude_pct >= 6:
        extra.append("日內振幅偏大，隔日追價波動風險提高")
    elif amplitude_pct <= 3.5:
        extra.append("振幅控制尚可，走勢結構相對穩定")

    if not extra:
        return base_reason

    return base_reason + "。補充：" + "；".join(extra) + "。"


def build_trade_plan(
    price: float,
    high_price: float,
    low_price: float,
    signal: str,
) -> Dict[str, str]:
    if price <= 0:
        return {"entry_price": "", "target_price": "", "stop_loss": ""}

    intraday_range = max(high_price - low_price, 0.0)
    base_buffer = max(price * 0.012, intraday_range * 0.35, 0.25)
    wider_buffer = max(price * 0.022, intraday_range * 0.55, 0.45)

    if signal in {"量增轉強", "穩步走高", "整理待發"}:
        entry_low = max(price - base_buffer, 0.01)
        entry_high = price
        target_low = price * 1.03
        target_high = price * 1.07
        stop = max(price - wider_buffer, 0.01)
        return {
            "entry_price": format_price_range(entry_low, entry_high),
            "target_price": format_price_range(target_low, target_high),
            "stop_loss": format_price_value(stop),
        }

    if signal in {"短線過熱"}:
        return {
            "entry_price": "等拉回後再評估",
            "target_price": format_price_range(price * 1.02, price * 1.04),
            "stop_loss": format_price_value(max(price * 0.965, 0.01)),
        }

    if signal in {"偏弱整理"}:
        return {
            "entry_price": "暫不建議",
            "target_price": "",
            "stop_loss": format_price_value(max(price * 0.97, 0.01)),
        }

    return {
        "entry_price": format_price_range(price * 0.985, price),
        "target_price": format_price_range(price * 1.02, price * 1.05),
        "stop_loss": format_price_value(max(price * 0.97, 0.01)),
    }


def build_strategy_and_risk(
    signal: str,
    price: float,
    open_price: float,
    high_price: float,
    low_price: float,
    volume: int,
    previous_close: float,
) -> Dict[str, str]:
    pos = calc_position_ratio(price, high_price, low_price)
    amplitude_pct = calc_amplitude_pct(high_price, low_price, previous_close)

    if signal in {"量增轉強", "整理待發"}:
        return {
            "trend_type": "短線潛力攻擊",
            "technical_comment": (
                f"收盤位置比 {pos:.0%}；日內振幅 {amplitude_pct:.2f}%；成交量 {volume:,} 張。"
                " 結構偏向 2~4 天續強觀察。"
            ),
            "operation_rating": "A",
            "operation_bias": "偏多卡位",
            "operation_style": "拉回布局",
            "strategy_action": "以回測不破或次日開盤穩住為進場依據，不追盤中急拉。",
            "risk_note": "若隔日爆量長紅或開高走低，代表短線過熱，應避免追價。",
        }

    if signal in {"穩步走高"}:
        return {
            "trend_type": "溫和轉強",
            "technical_comment": (
                f"收盤位置比 {pos:.0%}；日內振幅 {amplitude_pct:.2f}%；成交量 {volume:,} 張。"
                " 結構健康，但仍需下一日量價確認。"
            ),
            "operation_rating": "B+",
            "operation_bias": "偏多觀察",
            "operation_style": "等待續強",
            "strategy_action": "優先觀察隔日是否續量或回測守住前一日中段價位。",
            "risk_note": "若隔日無量或跌破前一日低點，代表轉強失敗。",
        }

    if signal in {"短線過熱"}:
        return {
            "trend_type": "強勢過熱",
            "technical_comment": (
                f"收盤位置比 {pos:.0%}；日內振幅 {amplitude_pct:.2f}%；成交量 {volume:,} 張。"
                " 強勢明顯，但較不符合低風險潛力股切入。"
            ),
            "operation_rating": "C",
            "operation_bias": "不追高",
            "operation_style": "等拉回",
            "strategy_action": "避免追價，等拉回量縮不破支撐後再觀察。",
            "risk_note": "隔日若無法續強，容易轉成短線獲利了結。",
        }

    if signal in {"偏弱整理"}:
        return {
            "trend_type": "偏弱結構",
            "technical_comment": (
                f"收盤位置比 {pos:.0%}；日內振幅 {amplitude_pct:.2f}%；成交量 {volume:,} 張。"
                " 目前不在短線潛力模型內。"
            ),
            "operation_rating": "D",
            "operation_bias": "保守觀望",
            "operation_style": "不急著進",
            "strategy_action": "先等止跌與站回關鍵均線再考慮。",
            "risk_note": "弱勢股搶反彈成功率低。",
        }

    return {
        "trend_type": "整理觀察",
        "technical_comment": (
            f"收盤位置比 {pos:.0%}；日內振幅 {amplitude_pct:.2f}%；成交量 {volume:,} 張。"
            " 需等待更明確表態。"
        ),
        "operation_rating": "C",
        "operation_bias": "觀察",
        "operation_style": "等訊號",
        "strategy_action": "等待量增或突破確認後再進場。",
        "risk_note": "方向未明前，不宜頻繁進出。",
    }


def calc_risk_reward(entry_price: str, target_price: str, stop_loss: str) -> str:
    entry_mid = parse_range_mid(entry_price, 0.0)
    target_mid = parse_range_mid(target_price, 0.0)
    stop = safe_float(stop_loss, 0.0)
    if entry_mid <= 0 or target_mid <= 0 or stop <= 0:
        return ""
    reward = abs(target_mid - entry_mid)
    risk = abs(entry_mid - stop)
    if risk <= 0:
        return ""
    return f"1:{reward / risk:.2f}"


# =========================
# Historical K analysis
# =========================
def get_history_cache(symbol: str) -> Optional[Dict[str, Any]]:
    item = _HISTORY_CACHE.get(symbol)
    if not item:
        return None
    fetched_at = item.get("fetched_at")
    if not isinstance(fetched_at, datetime):
        return None
    if (now_taipei() - fetched_at).total_seconds() > HISTORY_CACHE_HOURS * 3600:
        return None
    return item.get("data")


def set_history_cache(symbol: str, data: Dict[str, Any]) -> None:
    _HISTORY_CACHE[symbol] = {"fetched_at": now_taipei(), "data": data}
    if len(_HISTORY_CACHE) <= HISTORY_CACHE_MAX_SYMBOLS:
        return
    stale_keys = sorted(
        _HISTORY_CACHE.items(),
        key=lambda item: item[1].get("fetched_at") or datetime.min.replace(tzinfo=TZ_TAIPEI),
    )
    for cache_key, _ in stale_keys[: max(len(_HISTORY_CACHE) - HISTORY_CACHE_MAX_SYMBOLS, 0)]:
        _HISTORY_CACHE.pop(cache_key, None)


def overlay_snapshot_on_candles(
    candles: List[Dict[str, Any]],
    base_stock: Dict[str, Any],
) -> Tuple[List[Dict[str, Any]], float]:
    if not candles:
        return [], 0.0

    merged = [dict(x) for x in candles]
    snapshot_price = safe_float(base_stock.get("price"))
    snapshot_volume = safe_int(base_stock.get("volume"))
    snapshot_prev_close = safe_float(base_stock.get("prev_close"))
    snapshot_open = safe_float(base_stock.get("open"))
    snapshot_high = safe_float(base_stock.get("high"))
    snapshot_low = safe_float(base_stock.get("low"))
    snapshot_date_key = normalize_date_key(base_stock.get("update_time")) or now_taipei().strftime("%Y%m%d")
    last_candle_date_key = normalize_date_key(merged[-1].get("date"))

    if snapshot_price <= 0:
        prev_close = snapshot_prev_close
        if prev_close <= 0 and len(merged) >= 2:
            prev_close = safe_float(merged[-2].get("close"))
        elif prev_close <= 0:
            prev_close = safe_float(merged[-1].get("close"))
        return merged, prev_close

    if snapshot_date_key and last_candle_date_key and snapshot_date_key > last_candle_date_key:
        prev_close = snapshot_prev_close if snapshot_prev_close > 0 else safe_float(merged[-1].get("close"))
        open_price = snapshot_open if snapshot_open > 0 else prev_close
        high_price = max([x for x in [snapshot_high, snapshot_price, open_price] if x > 0], default=snapshot_price)
        low_price = positive_min([snapshot_low, snapshot_price, open_price], min(snapshot_price, open_price))
        merged.append({
            "date": snapshot_date_key,
            "open": open_price,
            "high": high_price,
            "low": low_price,
            "close": snapshot_price,
            "volume": snapshot_volume if snapshot_volume > 0 else safe_int(merged[-1].get("volume")),
            "change": round(snapshot_price - prev_close, 2) if prev_close > 0 else 0.0,
        })
        return merged, prev_close

    current = dict(merged[-1])
    prev_close = snapshot_prev_close if snapshot_prev_close > 0 else (
        safe_float(merged[-2].get("close")) if len(merged) >= 2 else safe_float(current.get("close"))
    )
    current_open = snapshot_open if snapshot_open > 0 else safe_float(current.get("open"))
    current_high = max(
        [x for x in [safe_float(current.get("high")), snapshot_high, snapshot_price, current_open] if x > 0],
        default=snapshot_price,
    )
    current_low = positive_min(
        [safe_float(current.get("low")), snapshot_low, snapshot_price, current_open],
        min(snapshot_price, current_open if current_open > 0 else snapshot_price),
    )
    current["open"] = current_open if current_open > 0 else snapshot_price
    current["high"] = current_high
    current["low"] = current_low
    current["close"] = snapshot_price
    if snapshot_volume > 0:
        current["volume"] = snapshot_volume
    current["change"] = round(snapshot_price - prev_close, 2) if prev_close > 0 else safe_float(current.get("change"))
    merged[-1] = current
    return merged, prev_close


def ema(values: List[float], period: int) -> List[float]:
    if not values:
        return []
    alpha = 2 / (period + 1)
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
    avg_gain = avg(gains[:period])
    avg_loss = avg(losses[:period])
    for i in range(period, len(gains)):
        avg_gain = ((avg_gain * (period - 1)) + gains[i]) / period
        avg_loss = ((avg_loss * (period - 1)) + losses[i]) / period
    if avg_loss == 0:
        return 100.0
    return 100 - (100 / (1 + avg_gain / avg_loss))


def calc_macd(closes: List[float]) -> Tuple[float, float, float]:
    if len(closes) < 35:
        return 0.0, 0.0, 0.0
    ema12 = ema(closes, 12)
    ema26 = ema(closes, 26)
    macd_line_series = [a - b for a, b in zip(ema12, ema26)]
    signal_series = ema(macd_line_series, 9)
    macd_line = macd_line_series[-1]
    signal_line = signal_series[-1]
    return macd_line, signal_line, macd_line - signal_line


def calc_atr(candles: List[Dict[str, Any]], period: int = 14) -> float:
    if len(candles) < 2:
        return 0.0
    trs: List[float] = []
    prev_close = safe_float(candles[0].get("close"))
    for c in candles[1:]:
        high = safe_float(c.get("high"))
        low = safe_float(c.get("low"))
        close = safe_float(c.get("close"))
        tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
        trs.append(max(tr, 0.0))
        prev_close = close
    return avg(trs[-period:]) if trs else 0.0


def fetch_symbol_daily_candles(symbol: str) -> Dict[str, Any]:
    cached = get_history_cache(symbol)
    if cached:
        return cached

    stock_client = get_stock_rest_client()
    to_date = now_taipei().strftime("%Y-%m-%d")
    from_date = (now_taipei() - timedelta(days=HISTORICAL_K_CALENDAR_DAYS)).strftime("%Y-%m-%d")

    resp = stock_client.historical.candles(
        **{"symbol": symbol, "from": from_date, "to": to_date, "timeframe": "D", "sort": "asc"}
    )
    rows = extract_rows(resp)
    candles: List[Dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        candles.append({
            "date": safe_str(row.get("date")),
            "open": safe_float(row.get("open")),
            "high": safe_float(row.get("high")),
            "low": safe_float(row.get("low")),
            "close": safe_float(row.get("close")),
            "volume": safe_int(row.get("volume")),
            "change": safe_float(row.get("change")),
        })
    candles = [x for x in candles if x["close"] > 0]
    if len(candles) > HISTORICAL_K_CANDLES:
        candles = candles[-HISTORICAL_K_CANDLES:]
    data = {"candles": candles}
    set_history_cache(symbol, data)
    return data


def classify_daily_pattern(
    close_now: float,
    prev_close: float,
    ma5: float,
    ma10: float,
    ma20: float,
    high20: float,
    low20: float,
    vol_ratio5: float,
    rsi14: float,
    macd_hist: float,
) -> Dict[str, str]:
    day_change_pct = ((close_now - prev_close) / prev_close * 100) if prev_close > 0 else 0.0
    distance_to_high20 = ((high20 - close_now) / high20 * 100) if high20 > 0 else 999.0
    above_ma20 = close_now > ma20
    ma5_turn_up = ma5 >= ma10
    ma10_support = ma10 >= ma20
    close_above_ma5 = close_now >= ma5
    healthy_momentum = 0.2 <= day_change_pct <= 5.0
    healthy_volume = 0.95 <= vol_ratio5 <= 3.2
    healthy_rsi = 48 <= rsi14 <= 70

    breakout_score = 0.0
    if above_ma20:
        breakout_score += 18
    if ma5_turn_up:
        breakout_score += 14
    if ma10_support or close_now >= ma10 * 0.985:
        breakout_score += 12
    if close_above_ma5:
        breakout_score += 10
    if healthy_momentum:
        breakout_score += 12
    if healthy_volume:
        breakout_score += 12
    if healthy_rsi:
        breakout_score += 8
    if 0.0 <= distance_to_high20 <= 6.0:
        breakout_score += 10
    elif 6.0 < distance_to_high20 <= 8.0:
        breakout_score += 5
    if macd_hist >= -0.05:
        breakout_score += 8

    hard_fail = (
        close_now < ma20 * 0.99
        or day_change_pct < -0.6
        or day_change_pct > 5.5
        or vol_ratio5 < 0.75
        or vol_ratio5 > 3.8
        or rsi14 < 44
        or rsi14 > 74
        or distance_to_high20 > 9.5
    )

    if breakout_score >= 78 and not hard_fail:
        return {
            "signal": "突破前夕",
            "trend_type": "短線潛力最強",
            "pattern": "站上中期均線、量增靠近波段高點，且短均線結構完整",
        }

    if (
        above_ma20
        and ma5_turn_up
        and close_above_ma5
        and -0.2 <= day_change_pct <= 4.6
        and 0.9 <= vol_ratio5 <= 3.0
        and 46 <= rsi14 <= 70
        and macd_hist >= -0.08
    ):
        return {
            "signal": "量增轉強",
            "trend_type": "短線準備發動",
            "pattern": "價格轉強、量能溫和放大，短線結構開始成形",
        }

    if (
        above_ma20
        and ma5 >= ma20
        and 0.8 <= distance_to_high20 <= 8.0
        and 0.75 <= vol_ratio5 <= 1.6
        and 45 <= rsi14 <= 64
        and macd_hist >= -0.08
    ):
        return {
            "signal": "整理待發",
            "trend_type": "整理後可攻",
            "pattern": "整理靠近壓力區，尚未過熱，等待放量突破",
        }

    if close_now > ma20 and ma5 >= ma20 and close_now >= ma5 and rsi14 >= 48 and macd_hist >= -0.03:
        return {
            "signal": "溫和轉強",
            "trend_type": "趨勢改善",
            "pattern": "重回中期均線之上，結構改善但尚未進入最強型",
        }

    if close_now < ma20 or (ma5 < ma10 < ma20) or rsi14 < 45:
        return {
            "signal": "偏弱觀察",
            "trend_type": "暫不列入主攻",
            "pattern": "仍未完成轉強，較接近弱勢反彈或空頭整理",
        }

    return {
        "signal": "中性觀察",
        "trend_type": "等待確認",
        "pattern": "方向尚未完全明朗",
    }


def build_historical_reason(
    name: str,
    close_now: float,
    prev_close: float,
    ma5: float,
    ma10: float,
    ma20: float,
    high20: float,
    low20: float,
    vol_now: int,
    avg_vol5: float,
    rsi14: float,
    macd_line: float,
    signal_line: float,
    macd_hist: float,
    pattern_text: str,
) -> str:
    day_change_pct = ((close_now - prev_close) / prev_close * 100) if prev_close > 0 else 0.0
    distance_to_high20 = ((high20 - close_now) / high20 * 100) if high20 > 0 else 0.0
    vol_ratio5 = (vol_now / avg_vol5) if avg_vol5 > 0 else 1.0

    return (
        f"【{name} 短線潛力分析】現價 {format_price_value(close_now)}，"
        f"日漲幅 {day_change_pct:.2f}%，MA5/MA10/MA20 分別為 "
        f"{format_price_value(ma5)} / {format_price_value(ma10)} / {format_price_value(ma20)}。"
        f" 目前 5 日量比 {vol_ratio5:.2f} 倍，RSI {rsi14:.1f}，MACD Hist {macd_hist:.3f}。"
        f" 股價距離 20 日高點約 {distance_to_high20:.2f}%，近 20 日區間為 "
        f"{format_price_value(low20)} ~ {format_price_value(high20)}。"
        f" 綜合判斷屬「{pattern_text}」，較偏向 2~4 天內可能續強的準備型結構，而非已經爆衝末端。"
    )


def build_historical_technical_comment(
    ma5: float,
    ma10: float,
    ma20: float,
    avg_vol5: float,
    avg_vol20: float,
    rsi14: float,
    macd_line: float,
    signal_line: float,
    macd_hist: float,
    high20: float,
    low20: float,
    atr14: float,
) -> str:
    return "；".join([
        f"均線 MA5/{format_price_value(ma5)} MA10/{format_price_value(ma10)} MA20/{format_price_value(ma20)}",
        f"5日均量 {format_number(avg_vol5)} 張 / 20日均量 {format_number(avg_vol20)} 張",
        f"RSI(14) {rsi14:.2f}",
        f"MACD DIF {macd_line:.3f} / Signal {signal_line:.3f} / Hist {macd_hist:.3f}",
        f"近20日區間 {format_price_value(low20)} ~ {format_price_value(high20)}",
        f"ATR(14) {format_price_value(atr14)}",
    ]) + "。"


def build_historical_trade_plan(
    price: float,
    ma5: float,
    ma20: float,
    high20: float,
    low20: float,
    atr14: float,
    signal: str,
) -> Dict[str, str]:
    if price <= 0:
        return {"entry_price": "", "target_price": "", "stop_loss": ""}

    buffer_small = max(atr14 * 0.6, price * 0.012, 0.3)
    buffer_large = max(atr14 * 1.0, price * 0.025, 0.5)

    if signal in {"突破前夕", "量增轉強", "整理待發", "溫和轉強"}:
        support = max(min(ma5, price), ma20, low20)
        return {
            "entry_price": format_price_range(max(support, price - buffer_large), price),
            "target_price": format_price_range(max(price * 1.03, high20), max(price * 1.07, high20 + buffer_small)),
            "stop_loss": format_price_value(max(support - buffer_small, 0.01)),
        }

    return {
        "entry_price": "暫不建議",
        "target_price": "",
        "stop_loss": format_price_value(max(price * 0.97, 0.01)),
    }


def build_historical_strategy(signal: str) -> Dict[str, str]:
    if signal in {"突破前夕", "量增轉強"}:
        return {
            "operation_rating": "A",
            "operation_bias": "偏多卡位",
            "operation_style": "2~4天主攻",
            "strategy_action": "優先找回測不破或隔日量穩續強切入，不追單日急拉。",
            "risk_note": "若次日直接爆量長紅，代表追價溫度升高，應縮小部位避免買在短線高潮。",
        }
    if signal in {"整理待發", "溫和轉強"}:
        return {
            "operation_rating": "B+",
            "operation_bias": "偏多觀察",
            "operation_style": "等突破",
            "strategy_action": "等待量增突破或回測守住 MA20 後進場。",
            "risk_note": "若量能遲遲不出來，容易繼續橫盤拖時間。",
        }
    if signal in {"偏弱觀察"}:
        return {
            "operation_rating": "D",
            "operation_bias": "保守",
            "operation_style": "先不主攻",
            "strategy_action": "先等站回 MA20 與量能回升再看。",
            "risk_note": "弱勢股不適合拿來做 2~4 天主攻。",
        }
    return {
        "operation_rating": "C",
        "operation_bias": "中性",
        "operation_style": "等待確認",
        "strategy_action": "先觀察，等更完整轉強條件出現。",
        "risk_note": "方向還不夠清楚，不適合重押。",
    }


def calc_potential_recommendation_score(
    close_now: float,
    prev_close: float,
    ma5: float,
    ma10: float,
    ma20: float,
    high20: float,
    low20: float,
    vol_now: int,
    avg_vol5: float,
    rsi14: float,
    macd_hist: float,
) -> float:
    if prev_close <= 0 or close_now <= 0:
        return 0.0

    day_change_pct = ((close_now - prev_close) / prev_close) * 100
    vol_ratio5 = (vol_now / avg_vol5) if avg_vol5 > 0 else 0.0
    distance_to_high20 = ((high20 - close_now) / high20 * 100) if high20 > 0 else 99.0

    score = 0.0
    score += score_band(day_change_pct, 0.3, 5.0, 2.0, 22)
    score += score_band(vol_ratio5, 0.95, 3.0, 1.6, 24)
    score += score_band(rsi14, 46, 71, 57, 16)
    score += score_band(distance_to_high20, 0.8, 8.0, 2.6, 22)

    if close_now > ma20:
        score += 12
    if ma5 >= ma10:
        score += 8
    if ma10 >= ma20:
        score += 6
    if close_now >= ma5:
        score += 4
    if macd_hist >= 0:
        score += 8

    if close_now < ma20:
        score -= 15
    if close_now < ma5:
        score -= 6
    if ma5 < ma10 < ma20:
        score -= 12
    if close_now < low20 * 1.03:
        score -= 10
    if day_change_pct >= 5.2:
        score -= 15
    if vol_ratio5 >= 3.0:
        score -= 12
    if rsi14 >= 72:
        score -= 10
    if distance_to_high20 < 0.5:
        score -= 6

    return round(max(score, 0.0), 2)


def calc_distance_pct(ceiling: float, value: float) -> float:
    if ceiling <= 0 or value <= 0:
        return 999.0
    return ((ceiling - value) / ceiling) * 100


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

        closes = [safe_float(x.get("close")) for x in analysis_candles]
        volumes = [safe_int(x.get("volume")) for x in analysis_candles]
        reference_candles = completed_candles_for_reference(analysis_candles, base_stock)
        reference_volumes = [safe_int(x.get("volume")) for x in reference_candles]
        close_now = closes[-1]
        vol_now = volumes[-1]
        projected_vol_now = estimate_full_day_volume(vol_now)
        snapshot_price = safe_float(base_stock.get("price"))
        snapshot_volume = safe_int(base_stock.get("volume"))
        snapshot_recommendation_score = safe_float(
            base_stock.get("snapshot_recommendation_score")
            or base_stock.get("recommendation_score")
            or base_stock.get("score")
        )

        ma5 = avg(closes[-5:])
        ma10 = avg(closes[-10:])
        ma20 = avg(closes[-20:])
        ma60 = avg(closes[-60:]) if len(closes) >= 60 else avg(closes)
        avg_vol5 = avg(reference_volumes[-5:])
        avg_vol20 = avg(reference_volumes[-20:])
        high20 = max(safe_float(x.get("high")) for x in reference_candles[-20:]) if reference_candles else max(
            safe_float(x.get("high")) for x in analysis_candles[-20:]
        )
        low20 = min(safe_float(x.get("low")) for x in reference_candles[-20:]) if reference_candles else min(
            safe_float(x.get("low")) for x in analysis_candles[-20:]
        )
        high60 = max(safe_float(x.get("high")) for x in reference_candles[-60:]) if reference_candles else max(
            safe_float(x.get("high")) for x in analysis_candles
        )
        low60 = min(safe_float(x.get("low")) for x in reference_candles[-60:]) if reference_candles else min(
            safe_float(x.get("low")) for x in analysis_candles
        )
        rsi14 = calc_rsi(closes, 14)
        macd_line, signal_line, macd_hist = calc_macd(closes)
        atr14 = calc_atr(analysis_candles, 14)

        vol_ratio5 = (projected_vol_now / avg_vol5) if avg_vol5 > 0 else 1.0
        atr14_pct = ((atr14 / close_now) * 100) if close_now > 0 else 0.0
        premium_to_ma20_pct = ((close_now - ma20) / ma20 * 100) if ma20 > 0 else 0.0
        premium_to_ma60_pct = ((close_now - ma60) / ma60 * 100) if ma60 > 0 else 0.0
        distance_to_high20 = calc_distance_pct(high20, close_now)
        distance_to_high60 = calc_distance_pct(high60, close_now)
        pattern_info = classify_daily_pattern(
            close_now=close_now,
            prev_close=prev_close,
            ma5=ma5,
            ma10=ma10,
            ma20=ma20,
            high20=high20,
            low20=low20,
            vol_ratio5=vol_ratio5,
            rsi14=rsi14,
            macd_hist=macd_hist,
        )

        reason = build_historical_reason(
            name=safe_str(base_stock.get("name")),
            close_now=close_now,
            prev_close=prev_close,
            ma5=ma5,
            ma10=ma10,
            ma20=ma20,
            high20=high20,
            low20=low20,
            vol_now=vol_now,
            avg_vol5=avg_vol5,
            rsi14=rsi14,
            macd_line=macd_line,
            signal_line=signal_line,
            macd_hist=macd_hist,
            pattern_text=pattern_info["pattern"],
        )
        technical_comment = build_historical_technical_comment(
            ma5=ma5,
            ma10=ma10,
            ma20=ma20,
            avg_vol5=avg_vol5,
            avg_vol20=avg_vol20,
            rsi14=rsi14,
            macd_line=macd_line,
            signal_line=signal_line,
            macd_hist=macd_hist,
            high20=high20,
            low20=low20,
            atr14=atr14,
        )
        plan = build_historical_trade_plan(
            price=close_now,
            ma5=ma5,
            ma20=ma20,
            high20=high20,
            low20=low20,
            atr14=atr14,
            signal=pattern_info["signal"],
        )
        strategy = build_historical_strategy(pattern_info["signal"])
        risk_reward = calc_risk_reward(plan["entry_price"], plan["target_price"], plan["stop_loss"])

        recommendation_score = calc_potential_recommendation_score(
            close_now=close_now,
            prev_close=prev_close,
            ma5=ma5,
            ma10=ma10,
            ma20=ma20,
            high20=high20,
            low20=low20,
            vol_now=projected_vol_now,
            avg_vol5=avg_vol5,
            rsi14=rsi14,
            macd_hist=macd_hist,
        )

        merged = dict(base_stock)
        merged.update({
            "signal": pattern_info["signal"],
            "trend_type": pattern_info["trend_type"],
            "reason": reason,
            "technical_comment": technical_comment,
            "operation_rating": strategy["operation_rating"],
            "operation_bias": strategy["operation_bias"],
            "operation_style": strategy["operation_style"],
            "strategy_action": strategy["strategy_action"],
            "entry_price": plan["entry_price"],
            "target_price": plan["target_price"],
            "stop_loss": plan["stop_loss"],
            "risk_reward": risk_reward,
            "risk_note": strategy["risk_note"],
            "recommendation_score": recommendation_score,
            "historical_recommendation_score": recommendation_score,
            "snapshot_recommendation_score": snapshot_recommendation_score,
            "score": recommendation_score,
            "analysis_source": "historical_k",
            "analysis_basis": "realtime_overlay",
            "ma20_value": round(ma20, 2),
            "ma60_value": round(ma60, 2),
            "high20_value": round(high20, 2),
            "high60_value": round(high60, 2),
            "low20_value": round(low20, 2),
            "low60_value": round(low60, 2),
            "rsi14_value": round(rsi14, 2),
            "vol_ratio5_value": round(vol_ratio5, 2),
            "projected_volume": projected_vol_now,
            "atr14_pct": round(atr14_pct, 2),
            "premium_to_ma20_pct": round(premium_to_ma20_pct, 2),
            "premium_to_ma60_pct": round(premium_to_ma60_pct, 2),
            "distance_to_high20_pct": round(distance_to_high20, 2),
            "distance_to_high60_pct": round(distance_to_high60, 2),
        })
        merged["price"] = round(close_now, 2)
        merged["volume"] = vol_now
        if safe_float(merged.get("prev_close")) <= 0 and prev_close > 0:
            merged["prev_close"] = round(prev_close, 2)
        return merged

    except Exception:
        return base_stock


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

    open_price = safe_float(row.get("openPrice"))
    high_price = safe_float(row.get("highPrice"))
    low_price = safe_float(row.get("lowPrice"))

    update_time_raw = row.get("lastUpdated") or row.get("time") or 0
    update_time_str = micros_to_taipei_str(update_time_raw)
    category = price_category(price)

    close_position = calc_position_ratio(price, high_price, low_price)
    amplitude_pct = calc_amplitude_pct(high_price, low_price, previous_close)

    momentum_score = score_band(change_percent, -0.3, 5.0, 2.1, 20)
    position_score = score_band(close_position, 0.28, 0.88, 0.62, 18)
    amplitude_score = score_band(amplitude_pct, 0.8, 6.8, 3.2, 10)
    liquidity_score = score_band(volume, 1200, 40000, 9000, 12)

    structure_bonus = 0.0
    if price >= open_price:
        structure_bonus += 5
    if 0.48 <= close_position <= 0.8:
        structure_bonus += 4
    if 0.6 <= change_percent <= 4.2:
        structure_bonus += 4

    weakness_penalty = 0.0
    if price < open_price:
        weakness_penalty += 5
    if close_position <= 0.22:
        weakness_penalty += 6
    if change_percent < -1.0:
        weakness_penalty += 6

    overheat_penalty = 0.0
    if change_percent >= 5:
        overheat_penalty += 12
    if close_position >= 0.9:
        overheat_penalty += 8
    if amplitude_pct >= 7:
        overheat_penalty += 6

    score = round(
        max(momentum_score + position_score + amplitude_score + liquidity_score + structure_bonus - weakness_penalty - overheat_penalty, 0),
        2
    )
    base_recommendation_score = score

    signal_info = build_signal_and_reason(
        price=price,
        change=change,
        change_percent=change_percent,
        volume=volume,
        high_price=high_price,
        low_price=low_price,
        open_price=open_price,
        previous_close=previous_close,
    )
    final_reason = enrich_reason_with_context(
        base_reason=signal_info["reason"],
        price=price,
        open_price=open_price,
        high_price=high_price,
        low_price=low_price,
        change_percent=change_percent,
        volume=volume,
        previous_close=previous_close,
    )
    plan = build_trade_plan(price=price, high_price=high_price, low_price=low_price, signal=signal_info["signal"])
    strategy_info = build_strategy_and_risk(
        signal=signal_info["signal"],
        price=price,
        open_price=open_price,
        high_price=high_price,
        low_price=low_price,
        volume=volume,
        previous_close=previous_close,
    )
    risk_reward = calc_risk_reward(plan["entry_price"], plan["target_price"], plan["stop_loss"])

    rating_bonus_map = {"A": 12, "B+": 8, "C": 3, "D": 0}
    recommendation_score = round(
        base_recommendation_score + rating_bonus_map.get(strategy_info["operation_rating"], 0), 2
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
        "snapshot_score": score,
        "recommendation_score": recommendation_score,
        "snapshot_recommendation_score": recommendation_score,
        "prev_close": round(previous_close, 2) if previous_close > 0 else 0,
        "open": round(open_price, 2),
        "high": round(high_price, 2),
        "low": round(low_price, 2),
        "update_time": update_time_str,
        "update_time_raw": update_time_raw,
        "category": category,
        "signal": signal_info["signal"],
        "trend_type": strategy_info["trend_type"],
        "reason": final_reason,
        "technical_comment": strategy_info["technical_comment"],
        "operation_rating": strategy_info["operation_rating"],
        "operation_bias": strategy_info["operation_bias"],
        "operation_style": strategy_info["operation_style"],
        "strategy_action": strategy_info["strategy_action"],
        "entry_price": plan["entry_price"],
        "target_price": plan["target_price"],
        "stop_loss": plan["stop_loss"],
        "risk_reward": risk_reward,
        "risk_note": strategy_info["risk_note"],
        "analysis_source": "snapshot",
    }




# =========================
# Validation Tracking
# =========================
def load_validation_store() -> Dict[str, Any]:
    try:
        if not os.path.exists(VALIDATION_STORE_PATH):
            return {"runs": {}}
        with open(VALIDATION_STORE_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return {"runs": {}}
        if not isinstance(data.get("runs"), dict):
            data["runs"] = {}
        return data
    except Exception:
        return {"runs": {}}


def save_validation_store(store: Dict[str, Any]) -> None:
    directory = os.path.dirname(os.path.abspath(VALIDATION_STORE_PATH))
    if directory:
        os.makedirs(directory, exist_ok=True)
    tmp_path = f"{VALIDATION_STORE_PATH}.tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(store, f, ensure_ascii=False, indent=2)
    os.replace(tmp_path, VALIDATION_STORE_PATH)


def get_validation_run(date_key: str) -> Optional[Dict[str, Any]]:
    store = load_validation_store()
    run = store.get("runs", {}).get(date_key)
    return run if isinstance(run, dict) else None


def get_latest_validation_date() -> str:
    store = load_validation_store()
    runs = store.get("runs", {})
    if not isinstance(runs, dict) or not runs:
        return ""
    valid_dates = [normalize_date_key(key) for key in runs.keys()]
    valid_dates = [key for key in valid_dates if key]
    return max(valid_dates) if valid_dates else ""


def resolve_validation_date(date_key: str, fallback_date: str = "") -> str:
    raw = safe_str(date_key).lower()
    if raw in ("", "latest", "current", "auto"):
        return get_latest_validation_date() or normalize_date_key(fallback_date)
    return normalize_date_key(date_key) or normalize_date_key(fallback_date)


def build_validation_item(stock: Dict[str, Any], rank: int) -> Dict[str, Any]:
    start_close_price = safe_float(stock.get("price"))
    return {
        "rank": rank,
        "market": stock.get("market", ""),
        "symbol": stock.get("symbol", ""),
        "name": stock.get("name", ""),
        "recommendation_score": stock.get("recommendation_score", stock.get("score", 0)),
        "signal": stock.get("signal", ""),
        "operation_rating": stock.get("operation_rating", ""),
        "entry_price_plan": stock.get("entry_price", ""),
        "target_price_plan": stock.get("target_price", ""),
        "stop_loss_plan": stock.get("stop_loss", ""),
        "risk_reward_plan": stock.get("risk_reward", ""),
        "start_close_price": start_close_price,
        "current_price": start_close_price,
        "current_day_change_pct": safe_float(stock.get("change_percent")),
        "return_from_start_close_pct": 0,
        "entry_date": "",
        "entry_open_price": 0,
        "latest_price": start_close_price,
        "latest_change_pct": 0,
        "max_high_pct": 0,
        "max_drawdown_pct": 0,
        "hit_target": False,
        "hit_stop": False,
        "observations": {},
        "horizon_returns": {},
    }


def create_validation_run(date_key: str, recommendations: List[Dict[str, Any]], last_update: str) -> Dict[str, Any]:
    items = [build_validation_item(stock, index + 1) for index, stock in enumerate(recommendations[:10])]
    run = {
        "date": date_key,
        "created_at": format_dt_taipei(now_taipei()),
        "last_update": last_update,
        "status": "tracking" if items else "empty",
        "message": "已固定保存收盤推薦10檔，後續只追蹤這批股票。",
        "items": items,
    }
    store = load_validation_store()
    store.setdefault("runs", {})[date_key] = run
    save_validation_store(store)
    return run


def update_validation_run_tracking(run: Dict[str, Any], stocks: List[Dict[str, Any]], data_date: str, last_update: str) -> Dict[str, Any]:
    date_key = normalize_date_key(data_date)
    if not date_key:
        return run

    stock_map = {safe_str(s.get("symbol")): s for s in stocks if safe_str(s.get("symbol"))}
    changed = False
    run_date = normalize_date_key(run.get("date"))

    for item in run.get("items", []):
        symbol = safe_str(item.get("symbol"))
        stock = stock_map.get(symbol)
        if not symbol:
            continue

        start_close_price = safe_float(item.get("start_close_price"))
        observations = item.setdefault("observations", {})

        candles: List[Dict[str, Any]] = []
        try:
            candles = fetch_symbol_daily_candles(symbol).get("candles", [])
        except Exception:
            candles = []

        historical_observations: List[Dict[str, Any]] = []
        for index, candle in enumerate(candles):
            current_candle_date = candle_date_key(candle)
            if not current_candle_date or current_candle_date < run_date or current_candle_date > date_key:
                continue
            previous_close = safe_float(candles[index - 1].get("close")) if index > 0 else 0
            historical_observations.append(
                build_observation_from_candle(candle, start_close_price, last_update, previous_close)
            )

        if historical_observations:
            for observation in historical_observations:
                observations[observation["date"]] = observation

            latest_observation = historical_observations[-1]
            close_price = safe_float(latest_observation.get("close"))
            item["current_price"] = close_price
            item["current_day_change_pct"] = round(safe_float(latest_observation.get("day_change_pct")), 2)
            item["return_from_start_close_pct"] = latest_observation.get("return_from_start_close_pct", 0)

            if not item.get("entry_date"):
                entry_candidates = [x for x in historical_observations if safe_str(x.get("date")) > run_date]
                if entry_candidates:
                    entry_observation = entry_candidates[0]
                    item["entry_date"] = entry_observation["date"]
                    item["entry_open_price"] = safe_float(entry_observation.get("open"))

        elif stock:
            price = safe_float(stock.get("price"))
            open_price = safe_float(stock.get("open")) or price
            high_price = safe_float(stock.get("high")) or price
            low_price = safe_float(stock.get("low")) or price
            close_price = price

            item["current_price"] = close_price
            item["current_day_change_pct"] = round(safe_float(stock.get("change_percent")), 2)
            if start_close_price > 0:
                item["return_from_start_close_pct"] = round(
                    ((close_price - start_close_price) / start_close_price) * 100,
                    2,
                )

            observations[date_key] = {
                "date": date_key,
                "open": open_price,
                "high": high_price,
                "low": low_price,
                "close": close_price,
                "volume": safe_int(stock.get("volume")),
                "day_change_pct": round(safe_float(stock.get("change_percent")), 2),
                "return_from_start_close_pct": item.get("return_from_start_close_pct", 0),
                "last_update": last_update,
                "source": "settled_snapshot",
            }

        entry_price = safe_float(item.get("entry_open_price"))
        if entry_price > 0:
            tracked = [observations[k] for k in sorted(observations) if k >= safe_str(item.get("entry_date"))]
            highs = [safe_float(x.get("high")) for x in tracked]
            lows = [safe_float(x.get("low")) for x in tracked]
            item["latest_price"] = close_price
            item["latest_change_pct"] = round(((close_price - entry_price) / entry_price) * 100, 2)
            item["max_high_pct"] = round(((max(highs) - entry_price) / entry_price) * 100, 2) if highs else 0
            item["max_drawdown_pct"] = round(((min(lows) - entry_price) / entry_price) * 100, 2) if lows else 0
            target_high = parse_range_bounds(safe_str(item.get("target_price_plan")), 0.0)[1]
            stop_loss = safe_float(item.get("stop_loss_plan"))
            item["hit_target"] = target_high > 0 and bool(highs) and max(highs) >= target_high
            item["hit_stop"] = stop_loss > 0 and bool(lows) and min(lows) <= stop_loss
            horizon_returns: Dict[str, Any] = {}
            for horizon in VALIDATION_HORIZONS:
                if len(tracked) > horizon:
                    horizon_close = safe_float(tracked[horizon].get("close"))
                    horizon_returns[str(horizon)] = round(((horizon_close - entry_price) / entry_price) * 100, 2)
            item["horizon_returns"] = horizon_returns
        changed = True

    if changed:
        run["last_update"] = last_update
        run["status"] = "tracking"
        run["message"] = "驗證樣本已固定；追蹤資料會依每日行情快照更新。"
        store = load_validation_store()
        store.setdefault("runs", {})[safe_str(run.get("date"))] = run
        save_validation_store(store)
    return run


def get_or_create_validation_run(date_key: str, all_stocks: List[Dict[str, Any]], data_date: str, last_update: str, recommendations: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    target_date = resolve_validation_date(date_key, data_date)
    current_data_date = normalize_date_key(data_date)
    run = get_validation_run(target_date)

    if run is None and current_data_date == target_date and recommendations:
        run = create_validation_run(target_date, recommendations, last_update)

    if run is not None:
        return update_validation_run_tracking(run, all_stocks, data_date, last_update)

    latest_date = get_latest_validation_date()
    hint = f"目前最新保存日為 {latest_date}。" if latest_date else "目前尚未保存任何收盤推薦。"
    return {
        "date": target_date or current_data_date,
        "created_at": "",
        "last_update": last_update,
        "status": "missing",
        "message": f"尚未保存 {target_date or current_data_date} 的固定驗證樣本。系統會從部署後每個收盤日開始自動保存推薦10檔。{hint}",
        "items": [],
    }


def candle_date_key(candle: Dict[str, Any]) -> str:
    return normalize_date_key(candle.get("date"))


def build_observation_from_candle(
    candle: Dict[str, Any],
    start_close_price: float,
    last_update: str,
    previous_close: float = 0.0,
) -> Dict[str, Any]:
    close_price = safe_float(candle.get("close"))
    day_change_pct = ((close_price - previous_close) / previous_close) * 100 if previous_close > 0 else 0
    return {
        "date": candle_date_key(candle),
        "open": safe_float(candle.get("open")),
        "high": safe_float(candle.get("high")),
        "low": safe_float(candle.get("low")),
        "close": close_price,
        "volume": safe_int(candle.get("volume")),
        "day_change_pct": round(day_change_pct, 2),
        "return_from_start_close_pct": round(((close_price - start_close_price) / start_close_price) * 100, 2)
        if start_close_price > 0 and close_price > 0
        else 0,
        "last_update": last_update,
        "source": "historical_k",
    }


def update_all_validation_runs_tracking(all_stocks: List[Dict[str, Any]], data_date: str, last_update: str) -> None:
    store = load_validation_store()
    runs = store.get("runs", {})
    if not isinstance(runs, dict):
        return

    changed = False
    for date_key, run in list(runs.items()):
        if not isinstance(run, dict):
            continue
        updated = update_validation_run_tracking(run, all_stocks, data_date, last_update)
        runs[date_key] = updated
        changed = True

    if changed:
        store["runs"] = runs
        save_validation_store(store)


def summarize_validation_run(run: Dict[str, Any]) -> Dict[str, Any]:
    items = run.get("items", []) if isinstance(run.get("items"), list) else []
    entered = [x for x in items if safe_float(x.get("entry_open_price")) > 0]
    latest_returns = [safe_float(x.get("latest_change_pct")) for x in entered]
    start_returns = [safe_float(x.get("return_from_start_close_pct")) for x in items]
    wins = [x for x in entered if safe_float(x.get("latest_change_pct")) > 0]
    start_wins = [x for x in items if safe_float(x.get("return_from_start_close_pct")) > 0]
    hit_targets = [x for x in entered if x.get("hit_target")]
    hit_stops = [x for x in entered if x.get("hit_stop")]
    return {
        "count": len(items),
        "entered_count": len(entered),
        "avg_latest_return_pct": round(avg(latest_returns), 2) if latest_returns else 0,
        "avg_return_from_start_close_pct": round(avg(start_returns), 2) if start_returns else 0,
        "win_rate_pct": round((len(wins) / len(entered)) * 100, 2) if entered else 0,
        "start_close_win_rate_pct": round((len(start_wins) / len(items)) * 100, 2) if items else 0,
        "hit_target_count": len(hit_targets),
        "hit_stop_count": len(hit_stops),
    }


# =========================
# Market Data（只抓上市 + 上櫃）
# =========================
def fetch_snapshot_rows_by_type(
    stock_client, market: str, market_label: str, quote_type: str,
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
    data_date = micros_to_date_str(latest_raw) if latest_raw else now_taipei().strftime("%Y%m%d")
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
            "stocks": _CACHE["stocks"],
            "data_date": _CACHE["data_date"],
            "last_update": _CACHE["last_update"],
            "message": _CACHE.get("message", ""),
        }

    result = get_all_stocks_raw()
    _CACHE["stocks"] = result["stocks"]
    _CACHE["fetched_at"] = now
    _CACHE["data_date"] = result["data_date"]
    _CACHE["last_update"] = result["last_update"]
    _CACHE["message"] = result.get("message", "")
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
        and _RECOMMENDATION_CACHE.get("data_date") == data_date
        and _RECOMMENDATION_CACHE.get("last_update") == last_update
        and _RECOMMENDATION_CACHE.get("top_n") == top_n
    ):
        return cached_items

    items = build_recommendations(stocks, top_n=top_n)
    _RECOMMENDATION_CACHE["items"] = items
    _RECOMMENDATION_CACHE["data_date"] = data_date
    _RECOMMENDATION_CACHE["last_update"] = last_update
    _RECOMMENDATION_CACHE["top_n"] = top_n
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
        "operation_rating": "operation_rating",
    }
    key = allowed.get(sort_by, "score")

    if key == "operation_rating":
        rating_order = {"A": 4, "B+": 3, "C": 2, "D": 1}
        return sorted(stocks, key=lambda x: rating_order.get(x.get("operation_rating", ""), 0), reverse=reverse)

    return sorted(stocks, key=lambda x: x.get(key, 0), reverse=reverse)


def build_market_proxy_context(stocks: List[Dict[str, Any]]) -> Dict[str, Any]:
    universe = [s for s in stocks if is_main_board_stock(s)]
    if not universe:
        return {
            "regime": "中性",
            "advance_ratio": 0.5,
            "avg_change": 0.0,
            "strong_ratio": 0.0,
            "up_trade_ratio": 0.5,
        }

    advance_count = sum(1 for s in universe if safe_float(s.get("change_percent")) > 0)
    strong_count = sum(
        1
        for s in universe
        if safe_str(s.get("signal")) in {"量增轉強", "整理待發", "穩步走高"}
    )
    total_trade_value = sum(max(safe_int(s.get("trade_value")), 0) for s in universe)
    up_trade_value = sum(
        max(safe_int(s.get("trade_value")), 0)
        for s in universe
        if safe_float(s.get("change_percent")) > 0
    )
    advance_ratio = advance_count / len(universe)
    strong_ratio = strong_count / len(universe)
    avg_change = avg([safe_float(s.get("change_percent")) for s in universe])
    up_trade_ratio = (up_trade_value / total_trade_value) if total_trade_value > 0 else 0.5

    if advance_ratio >= 0.56 and avg_change >= 0.45 and up_trade_ratio >= 0.58:
        regime = "偏多"
    elif advance_ratio <= 0.43 and avg_change <= -0.35 and up_trade_ratio <= 0.45:
        regime = "保守"
    else:
        regime = "中性"

    return {
        "regime": regime,
        "advance_ratio": round(advance_ratio, 4),
        "avg_change": round(avg_change, 2),
        "strong_ratio": round(strong_ratio, 4),
        "up_trade_ratio": round(up_trade_ratio, 4),
    }


def build_book_proxy_selection(stock: Dict[str, Any], market_context: Dict[str, Any]) -> Dict[str, Any]:
    price = safe_float(stock.get("price"))
    volume = safe_int(stock.get("volume"))
    trade_value = max(safe_int(stock.get("trade_value")), 0)
    signal = safe_str(stock.get("signal"))
    rating = safe_str(stock.get("operation_rating"))
    rsi14 = safe_float(stock.get("rsi14_value"))
    vol_ratio5 = safe_float(stock.get("vol_ratio5_value"))
    atr14_pct = safe_float(stock.get("atr14_pct"))
    premium_to_ma20_pct = safe_float(stock.get("premium_to_ma20_pct"))
    premium_to_ma60_pct = safe_float(stock.get("premium_to_ma60_pct"))
    distance_to_high20_pct = safe_float(stock.get("distance_to_high20_pct"))
    distance_to_high60_pct = safe_float(stock.get("distance_to_high60_pct"))
    change_percent = safe_float(stock.get("change_percent"))

    regime = safe_str(market_context.get("regime"), "中性")
    advance_ratio = safe_float(market_context.get("advance_ratio"), 0.5)
    avg_change = safe_float(market_context.get("avg_change"), 0.0)
    up_trade_ratio = safe_float(market_context.get("up_trade_ratio"), 0.5)

    market_score = 0.0
    if regime == "偏多":
        market_score += 18
    elif regime == "中性":
        market_score += 11
    else:
        market_score += 4
    if advance_ratio >= 0.5:
        market_score += 4
    if up_trade_ratio >= 0.52:
        market_score += 4
    if avg_change > 0:
        market_score += 3

    leadership_score = 0.0
    if signal == "突破前夕":
        leadership_score += 22
    elif signal == "量增轉強":
        leadership_score += 18
    elif signal == "整理待發":
        leadership_score += 12
    elif signal == "溫和轉強":
        leadership_score += 10

    if rating == "A":
        leadership_score += 10
    elif rating == "B+":
        leadership_score += 6

    if price > safe_float(stock.get("ma20_value")) > 0:
        leadership_score += 8
    if price > safe_float(stock.get("ma60_value")) > 0:
        leadership_score += 8
    if 0.0 <= distance_to_high20_pct <= 7.0:
        leadership_score += 8
    elif 7.0 < distance_to_high20_pct <= 12.0:
        leadership_score += 4
    if 0.0 <= distance_to_high60_pct <= 10.0:
        leadership_score += 4

    quality_score = 0.0
    quality_score += score_band(volume, 800, 60000, 5000, 14)
    quality_score += score_band(trade_value, 50_000_000, 6_000_000_000, 500_000_000, 12)
    quality_score += score_band(price, 8, 500, 60, 6)
    if atr14_pct <= 7.5:
        quality_score += 6
    elif atr14_pct <= 10.5:
        quality_score += 3

    valuation_proxy_score = 0.0
    valuation_proxy_score += score_band(premium_to_ma20_pct, -4.0, 14.0, 5.0, 12)
    valuation_proxy_score += score_band(premium_to_ma60_pct, -6.0, 18.0, 8.0, 12)
    valuation_proxy_score += score_band(rsi14, 48.0, 68.0, 58.0, 10)
    valuation_proxy_score += score_band(vol_ratio5, 0.85, 2.8, 1.35, 8)

    overheat_penalty = 0.0
    if change_percent >= 5.0:
        overheat_penalty += 10
    if rsi14 >= 72:
        overheat_penalty += 8
    if premium_to_ma20_pct >= 16:
        overheat_penalty += 8
    if premium_to_ma60_pct >= 24:
        overheat_penalty += 6
    if atr14_pct >= 12:
        overheat_penalty += 5

    selection_score = round(
        max(market_score + leadership_score + quality_score + valuation_proxy_score - overheat_penalty, 0.0),
        2,
    )

    environment_ok = regime != "保守" or (signal in {"突破前夕", "量增轉強"} and rating == "A")
    leadership_ok = leadership_score >= 28
    quality_ok = quality_score >= 18
    value_ok = valuation_proxy_score >= 16 and overheat_penalty <= 12
    framework_pass = (
        environment_ok
        and leadership_ok
        and quality_ok
        and value_ok
        and selection_score >= BOOK_PROXY_MIN_SELECTION_SCORE
    )

    summary_bits = [
        f"環境{regime}",
        "強勢領先" if leadership_ok else "待觀察",
        "流動性佳" if quality_ok else "量能偏弱",
        "價格未過熱" if value_ok else "位置偏高",
    ]

    return {
        "book_selection_score": selection_score,
        "book_framework_pass": framework_pass,
        "book_environment_ok": environment_ok,
        "book_leadership_ok": leadership_ok,
        "book_quality_ok": quality_ok,
        "book_value_ok": value_ok,
        "book_market_regime": regime,
        "book_selection_comment": "／".join(summary_bits),
    }


def build_recommendations(stocks: List[Dict[str, Any]], top_n: int = 10) -> List[Dict[str, Any]]:
    market_context = build_market_proxy_context(stocks)
    candidates = [
        s for s in stocks
        if is_main_board_stock(s)
        and safe_float(s.get("price")) >= 8
        and safe_int(s.get("volume")) >= 500
        and -2.0 <= safe_float(s.get("change_percent")) <= 6.5
        and safe_float(s.get("snapshot_recommendation_score") or s.get("recommendation_score")) >= 14
        and safe_str(s.get("signal")) not in {"短線過熱", "偏弱整理"}
    ]

    candidates.sort(
        key=lambda x: (
            x.get("snapshot_recommendation_score", x.get("recommendation_score", 0)),
            x.get("snapshot_score", x.get("score", 0)),
            x.get("volume", 0),
            x.get("trade_value", 0),
        ),
        reverse=True,
    )
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

    analyzed = list(result_map.values())
    analyzed_with_proxy: List[Dict[str, Any]] = []
    for stock in analyzed:
        proxy_info = build_book_proxy_selection(stock, market_context)
        merged = dict(stock)
        merged.update(proxy_info)
        analyzed_with_proxy.append(merged)
    analyzed = analyzed_with_proxy

    analyzed = [
        s for s in analyzed
        if s.get("signal") in {"突破前夕", "量增轉強", "整理待發", "溫和轉強"}
        and safe_float(s.get("recommendation_score")) >= 30
        and safe_str(s.get("operation_rating")) in {"A", "B+"}
        and (
            safe_float(s.get("book_selection_score")) >= BOOK_PROXY_STRONG_SELECTION_SCORE
            or bool(s.get("book_framework_pass"))
        )
    ]

    analyzed.sort(
        key=lambda x: (
            x.get("book_selection_score", 0),
            x.get("recommendation_score", 0),
            1 if x.get("signal") == "突破前夕" else 0,
            1 if x.get("operation_rating") == "A" else 0,
            x.get("volume", 0),
        ),
        reverse=True,
    )
    return analyzed[:top_n]


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
        "book_selection_score": s.get("book_selection_score", 0),
        "book_market_regime": s.get("book_market_regime", ""),
        "book_selection_comment": s.get("book_selection_comment", ""),
        "analysis_source": s.get("analysis_source", "snapshot"),
    }


def build_focused_analysis(stock: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "symbol": stock.get("symbol", ""),
        "name": stock.get("name", ""),
        "market": stock.get("market", ""),
        "price": stock.get("price", 0),
        "change": stock.get("change", 0),
        "change_percent": stock.get("change_percent", 0),
        "volume": stock.get("volume", 0),
        "signal": stock.get("signal", ""),
        "trend_type": stock.get("trend_type", ""),
        "operation_rating": stock.get("operation_rating", ""),
        "operation_bias": stock.get("operation_bias", ""),
        "operation_style": stock.get("operation_style", ""),
        "technical_comment": stock.get("technical_comment", ""),
        "analysis": stock.get("reason", ""),
        "strategy_action": stock.get("strategy_action", ""),
        "entry_price": stock.get("entry_price", ""),
        "target_price": stock.get("target_price", ""),
        "stop_loss": stock.get("stop_loss", ""),
        "risk_reward": stock.get("risk_reward", ""),
        "risk_note": stock.get("risk_note", ""),
        "book_selection_score": stock.get("book_selection_score", 0),
        "book_market_regime": stock.get("book_market_regime", ""),
        "book_selection_comment": stock.get("book_selection_comment", ""),
        "update_time": stock.get("update_time", ""),
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
    date: str = Query(VALIDATION_START_DATE),
    force_refresh: bool = Query(False),
):
    try:
        result = get_cached_all_stocks(force_refresh=force_refresh)
        all_stocks = result["stocks"]
        market_status = get_market_status_text()
        current_data_date = normalize_date_key(result["data_date"])
        target_date = resolve_validation_date(date, current_data_date)
        recs: List[Dict[str, Any]] = []

        if current_data_date and should_settle_recommendations(market_status):
            recs = get_cached_recommendations(
                all_stocks,
                data_date=result["data_date"],
                last_update=result["last_update"],
                top_n=10,
            )
            if recs:
                get_or_create_validation_run(
                    current_data_date,
                    all_stocks,
                    data_date=result["data_date"],
                    last_update=result["last_update"],
                    recommendations=recs,
                )
                if safe_str(date).lower() in ("", "latest", "current", "auto"):
                    target_date = current_data_date

        run = get_or_create_validation_run(
            target_date,
            all_stocks,
            data_date=result["data_date"],
            last_update=result["last_update"],
            recommendations=recs if target_date == current_data_date else None,
        )
        return {
            "success": True,
            "market_status": market_status,
            "data_date": result["data_date"],
            "last_update": result["last_update"],
            "validation": run,
            "summary": summarize_validation_run(run),
        }
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "error": str(e),
                "trace": traceback.format_exc(),
                "validation": None,
                "summary": {},
            },
        )


@app.get("/validation/history")
def get_validation_history(
    limit: int = Query(60, ge=1, le=365),
    include_items: bool = Query(True),
):
    try:
        store = load_validation_store()
        runs = store.get("runs", {})
        if not isinstance(runs, dict):
            runs = {}

        items = []
        for date_key in sorted(runs.keys(), reverse=True)[:limit]:
            run = runs.get(date_key)
            if not isinstance(run, dict):
                continue
            row = {
                "date": run.get("date", date_key),
                "created_at": run.get("created_at", ""),
                "last_update": run.get("last_update", ""),
                "status": run.get("status", ""),
                "message": run.get("message", ""),
                "summary": summarize_validation_run(run),
            }
            if include_items:
                row["items"] = run.get("items", [])
            items.append(row)

        return {
            "success": True,
            "total": len(items),
            "runs": items,
        }
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "error": str(e),
                "trace": traceback.format_exc(),
                "runs": [],
            },
        )


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
        if (
            offset == 0
            and safe_str(market).lower() == "all"
            and safe_str(category).lower() == "all"
            and not q.strip()
            and price_min <= 0
            and price_max <= 0
            and should_settle_recommendations(market_status)
        ):
            recs = get_cached_recommendations(
                all_stocks,
                data_date=result["data_date"],
                last_update=result["last_update"],
                top_n=10,
            )
            if recs:
                get_or_create_validation_run(
                    result["data_date"],
                    all_stocks,
                    data_date=result["data_date"],
                    last_update=result["last_update"],
                    recommendations=recs,
                )

        cats = build_categories([s for s in all_stocks if is_main_board_stock(s)])

        focused = find_focused_stock(filtered, q)
        if focused:
            focused = build_historical_analysis_for_stock(focused)
            symbol = focused.get("symbol", "")
            paged = [focused if x.get("symbol") == symbol else x for x in paged]

        twse_total = len([s for s in all_stocks if s.get("market") == "上市"])
        otc_total = len([s for s in all_stocks if s.get("market") == "上櫃"])

        return {
            "success": True,
            "market_status": market_status,
            "data_date": result["data_date"],
            "last_update": result["last_update"],
            "message": result.get("message", ""),
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
