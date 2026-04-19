import os
import math
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional, Tuple

from fastapi import FastAPI, Query
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
CACHE_SECONDS = 60

_HISTORY_CACHE: Dict[str, Dict[str, Any]] = {}
HISTORY_CACHE_HOURS = 6

TZ_TAIPEI = timezone(timedelta(hours=8))


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


def avg(values: List[float]) -> float:
    if not values:
        return 0.0
    return sum(values) / len(values)


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
    from_date = (now_taipei() - timedelta(days=140)).strftime("%Y-%m-%d")

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
    if len(candles) > 120:
        candles = candles[-120:]
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
    healthy_momentum = 0.6 <= day_change_pct <= 4.2
    healthy_volume = 1.15 <= vol_ratio5 <= 2.7
    healthy_rsi = 50 <= rsi14 <= 67

    if (
        above_ma20
        and ma5_turn_up
        and ma10_support
        and close_above_ma5
        and healthy_momentum
        and healthy_volume
        and healthy_rsi
        and 1.0 <= distance_to_high20 <= 4.5
        and macd_hist >= 0
    ):
        return {
            "signal": "突破前夕",
            "trend_type": "短線潛力最強",
            "pattern": "站上中期均線、量增靠近波段高點，且短均線結構完整",
        }

    if (
        above_ma20
        and ma5_turn_up
        and close_above_ma5
        and 0.5 <= day_change_pct <= 4.0
        and 1.1 <= vol_ratio5 <= 2.6
        and 48 <= rsi14 <= 68
        and macd_hist >= -0.02
    ):
        return {
            "signal": "量增轉強",
            "trend_type": "短線準備發動",
            "pattern": "價格轉強、量能溫和放大，短線結構開始成形",
        }

    if (
        above_ma20
        and ma5 >= ma20
        and 1.2 <= distance_to_high20 <= 6.5
        and 0.85 <= vol_ratio5 <= 1.35
        and 48 <= rsi14 <= 61
        and macd_hist >= -0.05
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


def build_historical_analysis_for_stock(base_stock: Dict[str, Any]) -> Dict[str, Any]:
    try:
        symbol = safe_str(base_stock.get("symbol"))
        if not symbol:
            return base_stock

        data = fetch_symbol_daily_candles(symbol)
        candles = data.get("candles", [])
        if len(candles) < 35:
            return base_stock

        closes = [safe_float(x.get("close")) for x in candles]
        volumes = [safe_int(x.get("volume")) for x in candles]
        close_now = closes[-1]
        prev_close = closes[-2]
        vol_now = volumes[-1]

        ma5 = avg(closes[-5:])
        ma10 = avg(closes[-10:])
        ma20 = avg(closes[-20:])
        avg_vol5 = avg(volumes[-5:])
        avg_vol20 = avg(volumes[-20:])
        high20 = max(safe_float(x.get("high")) for x in candles[-20:])
        low20 = min(safe_float(x.get("low")) for x in candles[-20:])
        rsi14 = calc_rsi(closes, 14)
        macd_line, signal_line, macd_hist = calc_macd(closes)
        atr14 = calc_atr(candles, 14)

        vol_ratio5 = (vol_now / avg_vol5) if avg_vol5 > 0 else 1.0
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
            vol_now=vol_now,
            avg_vol5=avg_vol5,
            rsi14=rsi14,
            macd_hist=macd_hist,
        )

        merged = dict(base_stock)
        merged.update({
            "price": round(close_now, 2),
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
            "score": recommendation_score,
            "analysis_source": "historical_k",
        })
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
        "recommendation_score": recommendation_score,
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


def build_recommendations(stocks: List[Dict[str, Any]], top_n: int = 10) -> List[Dict[str, Any]]:
    candidates = [
        s for s in stocks
        if is_main_board_stock(s)
        and safe_float(s.get("price")) >= 8
        and safe_int(s.get("volume")) >= 1500
        and 0.2 <= safe_float(s.get("change_percent")) <= 4.8
        and safe_float(s.get("recommendation_score")) >= 22
        and safe_float(s.get("price")) >= safe_float(s.get("open"))
        and safe_float(s.get("price")) >= safe_float(s.get("low"))
        and safe_float(s.get("change_percent")) >= -0.2
        and safe_str(s.get("signal")) not in {"短線過熱", "偏弱整理"}
    ]

    candidates.sort(
        key=lambda x: (
            x.get("recommendation_score", 0),
            x.get("score", 0),
            x.get("volume", 0),
        ),
        reverse=True,
    )
    seed_items = candidates[:35]

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

    analyzed = [
        s for s in analyzed
        if s.get("signal") in {"突破前夕", "量增轉強", "整理待發", "溫和轉強"}
        and safe_float(s.get("recommendation_score")) >= 35
        and safe_str(s.get("operation_rating")) in {"A", "B+"}
    ]

    analyzed.sort(
        key=lambda x: (
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
        if offset == 0 and market == "all" and not q.strip():
            recs = build_recommendations(all_stocks, top_n=10)

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
            "market_status": get_market_status_text(),
            "data_date": result["data_date"],
            "last_update": result["last_update"],
            "message": result.get("message", ""),
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
        return {
            "success": False,
            "error": str(e),
            "trace": traceback.format_exc(),
            "stocks": [],
            "recommendations": [],
            "categories": [],
            "focused_stock": None,
        }
