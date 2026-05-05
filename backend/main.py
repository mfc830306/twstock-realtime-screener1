import os
import math
import json
import traceback
import urllib.request
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

# 驗證系統設定
# 使用 Upstash Redis 持久化（免費）
# 需在 Render 設定環境變數：UPSTASH_REDIS_REST_URL、UPSTASH_REDIS_REST_TOKEN
# 若未設定則 fallback 到本地 JSON（部署會清空）
UPSTASH_REDIS_REST_URL = os.getenv("UPSTASH_REDIS_REST_URL", "").strip()
UPSTASH_REDIS_REST_TOKEN = os.getenv("UPSTASH_REDIS_REST_TOKEN", "").strip()
UPSTASH_REDIS_KEY = "twstock:validation_runs"
VALIDATION_STORE_PATH = os.getenv(
    "VALIDATION_STORE_PATH",
    os.path.join(os.getcwd(), "validation_runs.json"),
)
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
) -> Tuple[float, str]:
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
    # ===== 硬性排除（尚未過熱） =====
    if close < ma5:
        return 0.0, "不符條件"   # 跌破5日線
    if close < ma10:
        return 0.0, "不符條件"   # 跌破10日線
    if prev3_change_pct > 10:
        return 0.0, "不符條件"   # 近3天漲太多（已過熱）
    if change_pct > 5.0:
        return 0.0, "不符條件"   # 今日漲幅過大
    if ma_cross["cross"] == "死亡交叉":
        return 0.0, "不符條件"   # 死亡交叉
    if candle_pattern["pattern"] in {"長上影線", "開高走低黑K", "空方吞噬"}:
        return 0.0, "不符條件"   # 明顯出貨訊號
    vol_ratio = vol_pattern.get("vol_ratio", 1.0)
    if vol_pattern["pattern"] == "爆量" and candle_pattern.get("bias") != "偏多":
        return 0.0, "不符條件"   # 爆量但非多方型態

    score = 0.0

    # ===== 條件一：股價站上MA5且MA10（25分）=====
    # 兩個都站上才完整
    if close > ma5 and close > ma10:
        score += 20
        # 剛站上（今日站上）加分
        if dist_from_ma5_pct <= 2.0:
            score += 5   # 剛站上不遠，轉折最佳位置

    # ===== 條件二：MA5接近或黃金交叉MA10（20分）=====
    ma_gap_pct = ((ma5 - ma10) / ma10 * 100) if ma10 > 0 else 0
    if ma_cross["cross"] == "黃金交叉":
        days = ma_cross["days_ago"]
        if days <= 2:
            score += 20   # 剛發生黃金交叉（最強）
        elif days <= 5:
            score += 15   # 近5天內黃金交叉
    elif -0.5 <= ma_gap_pct <= 1.0:
        score += 12   # MA5接近MA10（即將黃金交叉）
    elif 1.0 < ma_gap_pct <= 3.0:
        score += 8    # MA5略高於MA10（已轉多但未過熱）
    elif ma_gap_pct > 3.0:
        score += 3    # MA5遠高於MA10（可能過熱）

    # ===== 條件三：成交量放大（20分）=====
    vol_score_map = {
        "量縮後放量": 20,
        "量穩定放大": 15,
        "量平穩":     8,
        "爆量":       5,
        "量縮":       0,
        "資料不足":   5,
    }
    score += vol_score_map.get(vol_pattern["pattern"], 5)

    # ===== 條件四：MACD剛翻多（15分）=====
    macd_score = 0.0
    if prev_macd_hist < 0 and macd_hist >= 0:
        macd_score = 15   # 剛翻多（最強訊號）
    elif prev_macd_hist < 0 and macd_hist < 0 and macd_hist > prev_macd_hist:
        macd_score = 10   # 負值縮小，即將翻多
    elif macd_hist > 0 and macd_hist > prev_macd_hist:
        macd_score = 8    # 正值擴大，動能持續
    elif macd_hist > 0:
        macd_score = 4    # 正值但縮小
    score += macd_score

    # ===== 條件五：K棒轉強（20分）=====
    k_bonus_map = {
        "多方吞噬":   20,
        "早晨之星":   20,
        "錘子線":     15,
        "紅K收高":    10,
        "十字星":      5,
        "無明顯型態":  5,
    }
    k_score = float(k_bonus_map.get(candle_pattern["pattern"], 5))
    # 今日漲幅適中加分
    if 0.5 <= change_pct <= 3.0:
        k_score += 3
    score += min(k_score, 20.0)

    score = round(clamp(score, 0.0, 100.0), 1)

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
        return score, "準備轉強" if is_turning else "續攻型"
    if score >= 65:
        if is_turning:
            return score, "準備轉強"
        if is_continuation:
            return score, "續攻型"
        return score, "轉強觀察"
    if score >= 50:
        return score, "整理待發"
    return score, "不符條件"


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
) -> str:
    lines = [f"【{name} 技術分析 | {stock_type} | 評分 {setup_score}分】"]

    # 均線
    ma_desc = f"MA5 {format_price_value(ma5)} / MA10 {format_price_value(ma10)} / MA20 {format_price_value(ma20)}"
    lines.append(f"均線結構：{ma_desc}，現價 {format_price_value(close)}（" + ("站上5/10日線 ✓" if close > ma10 else "需關注") + "）")

    # MACD
    if prev_macd_hist < 0 and macd_hist >= 0:
        lines.append(f"MACD：由負翻正（Hist {prev_macd_hist:.3f} → {macd_hist:.3f}），動能轉折訊號最強。")
    elif prev_macd_hist < 0 and macd_hist > prev_macd_hist:
        lines.append(f"MACD：負值縮小中（Hist {prev_macd_hist:.3f} → {macd_hist:.3f}），動能持續改善。")
    elif macd_hist > 0 and macd_hist > prev_macd_hist:
        lines.append(f"MACD：正值擴大（Hist {macd_hist:.3f}），多方動能持續。")
    else:
        lines.append(f"MACD：Hist {macd_hist:.3f}，動能待確認。")

    # 量能
    lines.append(f"量能：{vol_pattern['pattern']}（量比 {vol_pattern.get('vol_ratio', 0):.2f} 倍）。")

    # K棒
    if candle_pattern["pattern"] != "無明顯型態":
        lines.append(f"K棒型態：{candle_pattern['pattern']}（{candle_pattern['bias']}）。")

    # 均線交叉
    if ma_cross["cross"] != "無":
        lines.append(f"均線交叉：{ma_cross['cross']}（{ma_cross['days_ago']} 天前）。")

    # RSI
    lines.append(f"RSI(14)：{rsi14:.1f}{'（健康動能區）' if 50 <= rsi14 <= 70 else '（注意過熱）' if rsi14 > 70 else ''}。")

    return "".join(lines)


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
        setup_score, stock_type = calc_setup_score(
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


def build_recommendations(
    stocks: List[Dict[str, Any]],
    top_n: int = 10,
) -> List[Dict[str, Any]]:
    """
    純技術分析選股
    1. 基本過濾（量、價、漲跌）
    2. 取前80筆做歷史K分析
    3. setup_score >= 65 且型態符合才進推薦
    """
    candidates = [
        s for s in stocks
        if is_main_board_stock(s)
        and safe_float(s.get("price")) >= 8
        and safe_int(s.get("volume")) >= 500
        and -3.0 <= safe_float(s.get("change_percent")) <= 7.0
    ]
    # 先按成交量排序取80筆（流動性夠才有意義）
    candidates.sort(
        key=lambda x: (safe_int(x.get("volume")), safe_float(x.get("change_percent"))),
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

    # 過濾：setup_score >= 65 且型態符合
    qualified = [
        s for s in result_map.values()
        if safe_float(s.get("setup_score")) >= 65
        and s.get("stock_type") in {"準備轉強", "續攻型", "轉強觀察"}
    ]

    qualified.sort(
        key=lambda x: (
            safe_float(x.get("setup_score")),
            1 if x.get("stock_type") == "準備轉強" else 0,
            safe_int(x.get("volume")),
        ),
        reverse=True,
    )
    return qualified[:top_n]


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


@app.post("/admin/reset-validation")
def reset_validation(secret: str = Query("")):
    """
    清空所有驗證資料（月底用）。
    需帶上 ADMIN_SECRET：POST /admin/reset-validation?secret=你的密碼
    """
    admin_secret = os.getenv("ADMIN_SECRET", "").strip()
    if not admin_secret or secret != admin_secret:
        return JSONResponse(status_code=403, content={"error": "forbidden"})
    try:
        if UPSTASH_REDIS_REST_URL and UPSTASH_REDIS_REST_TOKEN:
            _upstash_command("DEL", UPSTASH_REDIS_KEY)
        else:
            save_validation_store({"runs": {}})
        return {"success": True, "message": "驗證資料已清空，下次收盤後重新累積。"}
    except Exception as e:
        return JSONResponse(status_code=500, content={"success": False, "error": str(e)})


@app.get("/validation")
def get_validation(
    date: str = Query("latest"),
    force_refresh: bool = Query(False),
):
    """
    驗證追蹤端點。
    - 收盤後自動保存當日推薦10檔（若尚未保存）
    - 更新所有歷史 run 的追蹤資料
    - 返回指定日期（或最新）的驗證結果
    """
    try:
        result = get_cached_all_stocks(force_refresh=force_refresh)
        all_stocks = result["stocks"]
        market_status = get_market_status_text()
        today_date = normalize_date_key(result["data_date"])
        stock_map = {safe_str(s.get("symbol")): s for s in all_stocks if safe_str(s.get("symbol"))}

        # 收盤後：保存今日推薦（若尚未保存）
        if should_settle_recommendations(market_status):
            store = load_validation_store()
            if today_date and today_date not in store.get("runs", {}):
                recs = get_cached_recommendations(
                    all_stocks,
                    data_date=result["data_date"],
                    last_update=result["last_update"],
                    top_n=10,
                )
                if recs:
                    create_validation_run(today_date, recs, result["last_update"])

            # 更新所有 run（只在 /validation 做，不在 /stocks 做）
            update_all_runs(today_date, stock_map, result["last_update"])

        # 決定要返回哪一天的 run
        store = load_validation_store()
        runs = store.get("runs", {})

        raw_date = safe_str(date).lower()
        if raw_date in ("", "latest", "current", "auto"):
            target_date = get_latest_validation_date()
        else:
            target_date = normalize_date_key(date)

        run = runs.get(target_date)
        if run is None:
            latest = get_latest_validation_date()
            hint = f"目前最新保存日為 {latest}。" if latest else "目前尚未保存任何推薦紀錄。"
            run = {
                "date": target_date or today_date,
                "created_at": "",
                "last_update": result["last_update"],
                "status": "missing",
                "message": f"尚未保存 {target_date or today_date} 的推薦樣本。收盤後呼叫 /validation 即自動保存。{hint}",
                "items": [],
            }

        return {
            "success": True,
            "market_status": market_status,
            "data_date": result["data_date"],
            "last_update": result["last_update"],
            "validation": run,
            "summary": summarize_run(run),
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
            row: Dict[str, Any] = {
                "date": run.get("date", date_key),
                "created_at": run.get("created_at", ""),
                "last_update": run.get("last_update", ""),
                "status": run.get("status", ""),
                "message": run.get("message", ""),
                "summary": summarize_run(run),
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
            # 盤後時順便保存今日推薦（若尚未保存）
            # 不做 update_all_runs，那只在 /validation 做
            if recs:
                today_date = normalize_date_key(result["data_date"])
                store = load_validation_store()
                if today_date and today_date not in store.get("runs", {}):
                    create_validation_run(today_date, recs, result["last_update"])

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
