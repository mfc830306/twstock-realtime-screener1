import os
import math
import json
import traceback
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone, timedelta, date
from typing import Any, Dict, List, Optional, Tuple

from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="TW Stock Realtime Screener")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

# =========================
# Globals
# =========================
_sdk = None
_login_info = None
_marketdata_ready = False

_CACHE: Dict[str, Any] = {
    "stocks": None, "fetched_at": None, "data_date": "",
    "last_update": "", "message": "", "twse_total": 0, "otc_total": 0, "categories": [],
}
CACHE_SECONDS = 60

_RECS_CACHE: Dict[str, Any] = {"recommendations": None, "fetched_at": None}
RECS_CACHE_SECONDS = 120

_HISTORY_CACHE: Dict[str, Dict[str, Any]] = {}
HISTORY_CACHE_HOURS = 6
HISTORY_CACHE_MAX_SIZE = 500

VALIDATION_LOG_FILE = os.getenv(
    "VALIDATION_LOG_FILE",
    "/opt/render/project/src/recommendations_validation.jsonl",
)
VALIDATION_FORWARD_BARS = [1, 3, 5]

_VALIDATION_CACHE: Dict[str, Any] = {
    "rows": None, "fetched_at": None, "lookback_days": None, "holding_days": None,
}
VALIDATION_CACHE_SECONDS = 60

TZ_TAIPEI = timezone(timedelta(hours=8))

# =========================
# 選股哲學常數
# ─────────────────────────
# 真正的波段選股不追強，找「整理完畢、準備啟動」的股票
# 核心條件：均線偏離適中、RSI 在甜蜜區、量能由縮轉放、MACD 動能轉正
# =========================
MIN_AVG_DAILY_VOL  = 1000    # 日均量最低門檻（張），避免流動性不足
MIN_PRICE          = 10.0    # 最低股價，排除雞蛋水餃股
MAX_DIST_FROM_MA20 = 15.0    # 偏離 MA20 超過此值視為過度延伸（%）
IDEAL_RSI_LOW      = 50.0    # RSI 甜蜜區下緣
IDEAL_RSI_HIGH     = 68.0    # RSI 甜蜜區上緣
CHASE_PENALTY_PCT  = 5.0     # 今日漲幅超過此值開始扣分（不追強）
HARD_EXCLUDE_PCT   = 9.0     # 今日漲幅超過此值直接排除


# =========================
# Utils
# =========================
def safe_float(v: Any, default: float = 0.0) -> float:
    try:
        if v is None: return default
        if isinstance(v, str):
            v = v.replace(",", "").replace("%", "").strip()
            if v in ("", "-", "--", "None", "null"): return default
        return float(v)
    except Exception:
        return default


def safe_int(v: Any, default: int = 0) -> int:
    try:
        if v is None: return default
        if isinstance(v, str):
            v = v.replace(",", "").strip()
            if v in ("", "-", "--", "None", "null"): return default
        return int(float(v))
    except Exception:
        return default


def safe_str(v: Any, default: str = "") -> str:
    if v is None: return default
    return str(v).strip()


def now_taipei() -> datetime:
    return datetime.now(TZ_TAIPEI)


def format_dt_taipei(dt: datetime) -> str:
    return dt.astimezone(TZ_TAIPEI).strftime("%Y/%m/%d %H:%M:%S")


def micros_to_taipei_str(v: Any) -> str:
    try:
        iv = int(float(v))
        if iv <= 0: return ""
        dt = datetime.fromtimestamp(iv / 1_000_000, tz=timezone.utc).astimezone(TZ_TAIPEI)
        return dt.strftime("%Y/%m/%d %H:%M:%S")
    except Exception:
        return ""


def micros_to_date_str(v: Any) -> str:
    try:
        iv = int(float(v))
        if iv <= 0: return ""
        dt = datetime.fromtimestamp(iv / 1_000_000, tz=timezone.utc).astimezone(TZ_TAIPEI)
        return dt.strftime("%Y%m%d")
    except Exception:
        return ""


def resolve_cert_path() -> Optional[str]:
    cert_path = os.getenv("FUBON_CERT_PATH", "").strip()
    if not cert_path: return None
    candidates = [
        cert_path, os.path.abspath(cert_path),
        os.path.abspath(os.path.join(os.getcwd(), cert_path)),
        os.path.join("/opt/render/project/src", os.path.basename(cert_path)),
        os.path.join("/opt/render/project/src/certs", os.path.basename(cert_path)),
        os.path.join("/opt/render/project/src/backend", os.path.basename(cert_path)),
        os.path.join("/opt/render/project/src/backend/certs", os.path.basename(cert_path)),
    ]
    seen = set()
    for p in candidates:
        rp = os.path.abspath(p)
        if rp in seen: continue
        seen.add(rp)
        if os.path.exists(rp) and os.path.isfile(rp):
            return rp
    return None


def get_market_status_text() -> str:
    now = now_taipei()
    if now.weekday() >= 5: return "休市"
    minutes = now.hour * 60 + now.minute
    if 9 * 60 <= minutes <= 13 * 60 + 30: return "開盤"
    if minutes > 13 * 60 + 30: return "收盤"
    return "休市"


def price_category(price: float) -> str:
    if price < 10:   return "0-10"
    if price < 20:   return "10-20"
    if price < 50:   return "20-50"
    if price < 100:  return "50-100"
    if price < 200:  return "100-200"
    if price < 500:  return "200-500"
    if price < 1000: return "500-1000"
    return "1000+"


def format_price_value(v: float) -> str:
    if v <= 0: return ""
    rounded = round(v, 2)
    if abs(rounded - int(rounded)) < 0.001: return str(int(rounded))
    return f"{rounded:.2f}"


def format_price_range(low: float, high: float) -> str:
    low = max(low, 0.01)
    high = max(high, low)
    return f"{format_price_value(low)} ~ {format_price_value(high)}"


def calc_position_ratio(price: float, high_price: float, low_price: float) -> float:
    if high_price > low_price:
        return max(0.0, min((price - low_price) / (high_price - low_price), 1.0))
    return 0.5


def calc_amplitude_pct(high_price: float, low_price: float, previous_close: float) -> float:
    intraday_range = max(high_price - low_price, 0.0)
    return (intraday_range / previous_close) * 100 if previous_close > 0 else 0.0


def parse_range_mid(text: str, fallback: float = 0.0) -> float:
    txt = safe_str(text).replace("突破", "").replace("後再評估", "").strip()
    if not txt: return fallback
    nums = []
    for p in txt.split("~"):
        try: nums.append(float(p.strip()))
        except Exception: pass
    return sum(nums) / len(nums) if nums else fallback


def avg(values: List[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def format_number(num: float) -> str:
    try:
        if num is None or math.isnan(num): return "-"
    except Exception:
        pass
    if abs(num - int(num)) < 0.001: return f"{int(num):,}"
    return f"{num:,.2f}"


def is_main_board_stock(s: Dict[str, Any]) -> bool:
    return safe_str(s.get("market")) in ("上市", "上櫃")


def is_valid_main_board_symbol(symbol: str, name: str) -> bool:
    s = safe_str(symbol).upper()
    n = safe_str(name).upper()
    if not s or len(s) != 4 or not s.isdigit(): return False
    if s.startswith("00") or "ETF" in n: return False
    return True


def merge_stock_lists(*groups: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    dedup: Dict[str, Dict[str, Any]] = {}
    for group in groups:
        for item in group:
            symbol = safe_str(item.get("symbol"))
            if symbol: dedup[symbol] = item
    return list(dedup.values())


def parse_any_date(v: Any) -> Optional[date]:
    txt = safe_str(v)
    if not txt: return None
    for fmt in ("%Y-%m-%d", "%Y%m%d", "%Y/%m/%d", "%Y/%m/%d %H:%M:%S", "%Y-%m-%d %H:%M:%S"):
        try: return datetime.strptime(txt, fmt).date()
        except Exception: pass
    try: return datetime.fromisoformat(txt.replace("Z", "")).date()
    except Exception: return None


# =========================
# Fubon SDK
# =========================
def ensure_fubon_sdk():
    global _sdk, _login_info, _marketdata_ready
    if _sdk is not None and _marketdata_ready: return _sdk
    from fubon_neo.sdk import FubonSDK
    fubon_id  = os.getenv("FUBON_ID", "").strip()
    fubon_pwd = (os.getenv("FUBON_PASSWORD") or os.getenv("FUBON_PWD") or "").strip()
    cert_pwd  = (os.getenv("FUBON_CERT_PASSWORD") or os.getenv("FUBON_CERT_PWD") or "").strip()
    cert_path = resolve_cert_path()
    if not fubon_id or not fubon_pwd or not cert_pwd or not cert_path:
        raise Exception("FUBON 環境變數未設定完整")
    if _sdk is None: _sdk = FubonSDK()
    if _login_info is None: _login_info = _sdk.login(fubon_id, fubon_pwd, cert_path, cert_pwd)
    if not getattr(_login_info, "is_success", False):
        raise Exception(f"Fubon SDK login failed: {getattr(_login_info, 'message', 'unknown error')}")
    if not _marketdata_ready:
        _sdk.init_realtime()
        _marketdata_ready = True
    return _sdk


def get_stock_rest_client():
    sdk = ensure_fubon_sdk()
    marketdata = getattr(sdk, "marketdata", None)
    if not marketdata: raise Exception("sdk.marketdata 不存在")
    rest_client = getattr(marketdata, "rest_client", None)
    if not rest_client: raise Exception("sdk.marketdata.rest_client 不存在")
    stock_client = getattr(rest_client, "stock", None)
    if not stock_client: raise Exception("sdk.marketdata.rest_client.stock 不存在")
    return stock_client


# =========================
# Parse
# =========================
def extract_rows(resp: Any) -> List[Dict[str, Any]]:
    if isinstance(resp, list): return resp
    if isinstance(resp, dict):
        for key in ["data", "items", "rows", "quotes", "result"]:
            val = resp.get(key)
            if isinstance(val, list): return val
            if isinstance(val, dict):
                for subkey in ["data", "items", "rows", "quotes"]:
                    subval = val.get(subkey)
                    if isinstance(subval, list): return subval
    if hasattr(resp, "data"):
        data = getattr(resp, "data")
        if isinstance(data, list): return data
        if isinstance(data, dict):
            for key in ["data", "items", "rows", "quotes"]:
                val = data.get(key)
                if isinstance(val, list): return val
    return []


# =========================================================
# ★ 核心選股評分系統（全面重寫）
# ─────────────────────────────────────────────────────────
# 哲學：不追強，找「整理完畢、準備啟動」的股票
#
# 評分維度（滿分 100）：
#   1. 均線結構       25 分  → 多頭排列且斜率向上
#   2. MA20 偏離度    20 分  → 不能偏太遠，要在支撐附近
#   3. RSI 動能位置   20 分  → 50-68 的甜蜜區
#   4. MACD 動能      15 分  → 柱狀體由負轉正或正值擴大
#   5. 量能型態       20 分  → 縮量整理後今日量能轉放
#
# 加分項（Bonus）：
#   + 逼近 20 日高點（壓力測試）
#
# 扣分項（Penalty）：
#   - 今日漲幅 > 5%（不追強）
#   - 流動性不足
#   - RSI > 72（過熱）
# =========================================================

def calc_ma_slope_pct(closes: List[float], period: int = 5) -> float:
    """計算近 period 根收盤的均線斜率（%），正值代表向上"""
    if len(closes) < period + 1:
        return 0.0
    recent = closes[-(period + 1):]
    start  = avg(recent[:period // 2 + 1])
    end    = avg(recent[-(period // 2 + 1):])
    return ((end - start) / start * 100) if start > 0 else 0.0


def calc_vol_contraction_ratio(volumes: List[float], lookback: int = 5) -> float:
    """
    計算近 lookback 天的量能相對 20 日均量的比值。
    比值 < 0.8 代表縮量整理（好的整理型態），比值 > 1.2 代表放量。
    """
    if len(volumes) < 20:
        return 1.0
    avg20 = avg(volumes[-20:])
    if avg20 <= 0:
        return 1.0
    recent_avg = avg(volumes[-lookback:-1]) if len(volumes) > lookback else avg(volumes[-lookback:])
    return recent_avg / avg20


def calc_setup_score(
    close_now: float,
    ma5: float, ma10: float, ma20: float,
    high20: float, low20: float,
    rsi14: float,
    macd_hist: float, macd_line: float, signal_line: float,
    vol_now: int,
    avg_vol5: float, avg_vol20: float,
    vol_contraction_ratio: float,
    ma20_slope_pct: float,
    change_percent: float,
    price: float,
) -> float:
    """
    ★ 選股核心評分：0~100 分
    高分 = 健康整理、準備啟動的股票
    低分 = 已過度延伸、追高風險大的股票
    """
    score = 0.0

    # ── 前置門檻：不符合直接給 0 ──────────────────────
    if price < MIN_PRICE: return 0.0            # 排除雞蛋水餃股
    if close_now <= ma20: return 0.0            # 必須在 MA20 之上
    if avg_vol20 < MIN_AVG_DAILY_VOL: return 0.0   # 流動性不足
    if change_percent >= HARD_EXCLUDE_PCT: return 0.0  # 今日已大漲，不追

    # ── 1. 均線結構（25 分）──────────────────────────
    if close_now > ma5 > ma10 > ma20 and ma20_slope_pct > 0.1:
        score += 25   # 完整多頭排列且 MA20 向上傾斜
    elif close_now > ma5 > ma10 > ma20:
        score += 18   # 多頭排列但 MA20 偏平
    elif close_now > ma10 > ma20 and ma5 >= ma10:
        score += 12   # 短均線開始向上排列
    elif close_now > ma20:
        score += 5    # 站在 MA20 之上但結構未完整

    # ── 2. MA20 偏離度（20 分）───────────────────────
    # 0~3%：理想，代表剛從 MA20 附近啟動
    # 3~6%：可以接受
    # 6~10%：開始偏貴
    # >10%：過度延伸，不追
    dist_pct = (close_now - ma20) / ma20 * 100 if ma20 > 0 else 0.0
    if 0 < dist_pct <= 3.0:   score += 20
    elif 3.0 < dist_pct <= 6.0: score += 14
    elif 6.0 < dist_pct <= 10.0: score += 6
    elif dist_pct > MAX_DIST_FROM_MA20: score += 0  # 太遠，不加分

    # ── 3. RSI 動能位置（20 分）──────────────────────
    # 50~68：甜蜜區，動能健康不過熱
    # 45~50：回到中性，可能蓄積中
    # 68~72：偏熱，開始謹慎
    # >72 或 <45：扣分
    if IDEAL_RSI_LOW <= rsi14 <= IDEAL_RSI_HIGH:
        score += 20
    elif 45.0 <= rsi14 < IDEAL_RSI_LOW:
        score += 12   # 動能偏弱但在回升路上
    elif IDEAL_RSI_HIGH < rsi14 <= 72.0:
        score += 8    # 偏熱但尚可接受
    elif rsi14 > 72.0:
        score -= 8    # 過熱，追高風險大
    else:
        score += 0    # RSI < 45，動能太弱

    # ── 4. MACD 動能方向（15 分）─────────────────────
    # 最佳：柱狀體由負轉正（黃金交叉附近）或正值持續擴大
    if macd_hist > 0 and macd_line > signal_line:
        score += 15   # 多頭動能確立
    elif macd_hist <= 0 and macd_line > signal_line:
        score += 10   # DIF > MACD 但柱狀體還沒轉正，即將確立
    elif macd_hist > 0:
        score += 7    # 柱狀體正值但 DIF 未完全站上
    else:
        score += 0    # 空頭動能，不加分

    # ── 5. 量能型態（20 分）──────────────────────────
    # 理想型態：近期量能縮（vol_contraction_ratio < 0.8）
    # 今日放量（vol_ratio5 > 1.2）= 縮量整理後的啟動訊號
    vol_ratio5 = vol_now / avg_vol5 if avg_vol5 > 0 else 1.0
    is_recent_dry  = vol_contraction_ratio < 0.80   # 近期有量縮整理
    is_today_surge = vol_ratio5 >= 1.20             # 今日量能相對放大

    if is_recent_dry and is_today_surge:
        score += 20   # 最佳型態：縮量整理 → 今日放量啟動
    elif is_recent_dry and vol_ratio5 >= 0.90:
        score += 14   # 縮量整理中，量能開始回升
    elif is_today_surge:
        score += 10   # 今日放量但近期沒明顯縮量
    elif vol_contraction_ratio < 0.70:
        score += 8    # 量能持續萎縮，仍在整理中

    # ── Bonus：逼近 20 日高點（壓力測試）──────────────
    if high20 > 0:
        dist_from_high = (close_now - high20) / high20 * 100
        if -1.5 <= dist_from_high <= 1.0:
            score += 8    # 正在測試突破，高度關注
        elif -4.0 <= dist_from_high < -1.5:
            score += 4    # 接近壓力區

    # ── Penalty：今日漲幅過大（不追強）──────────────
    if change_percent >= CHASE_PENALTY_PCT:
        penalty = (change_percent - CHASE_PENALTY_PCT) * 3.0
        score -= min(penalty, 20.0)  # 最多扣 20 分

    # ── Penalty：今日下跌超過 3%（短線轉弱）──────────
    if change_percent <= -3.0:
        score -= 10

    return max(0.0, round(score, 2))


# =========================
# 訊號與分析理由（顯示用）
# =========================
def classify_daily_pattern(
    close_now: float, ma5: float, ma10: float, ma20: float,
    high20: float, low20: float,
    vol_ratio5: float, vol_contraction_ratio: float,
    rsi14: float, macd_hist: float, ma20_slope_pct: float,
) -> Dict[str, str]:
    """
    ★ 重寫版型態分類：從選股角度命名，聚焦在「值得買」的型態
    """
    near_high20 = high20 > 0 and close_now >= high20 * 0.975
    near_low20  = low20  > 0 and close_now <= low20  * 1.025
    dist_pct    = (close_now - ma20) / ma20 * 100 if ma20 > 0 else 0.0
    is_dry_vol  = vol_contraction_ratio < 0.80
    is_bull_ma  = close_now > ma5 > ma10 > ma20
    ma20_up     = ma20_slope_pct > 0.05

    # ── 強勢型態（已在主升段）──────────────────────
    if is_bull_ma and ma20_up and near_high20 and vol_ratio5 >= 1.2 and macd_hist > 0:
        return {"signal": "主升延續", "trend_type": "主升段", "pattern": "均線多頭排列，量能放大挑戰高點，主升段延續中"}

    if is_bull_ma and ma20_up and macd_hist > 0:
        return {"signal": "多頭趨勢", "trend_type": "多頭排列", "pattern": "均線完整多頭排列，趨勢健康延續"}

    # ── 選股甜蜜點：整理後準備啟動 ───────────────────
    if is_bull_ma and is_dry_vol and vol_ratio5 >= 1.15 and macd_hist > 0 and rsi14 >= 50:
        return {"signal": "蓄積啟動", "trend_type": "縮量整理後放量", "pattern": "縮量整理完畢，今日放量啟動，為高機率進場點"}

    if close_now > ma20 and is_dry_vol and 0 < dist_pct <= 5 and macd_hist >= 0 and rsi14 >= 45:
        return {"signal": "整理蓄積", "trend_type": "量縮價穩", "pattern": "均線上方縮量整理，籌碼沉澱充分，等待放量突破"}

    if is_bull_ma and near_high20 and vol_ratio5 >= 1.2 and rsi14 < 72:
        return {"signal": "突破測試", "trend_type": "挑戰高點", "pattern": "放量測試前高壓力，突破確認後可追"}

    # ── 健康回調：主升後的正常拉回 ───────────────────
    if close_now > ma10 > ma20 and ma20_up and 0 < dist_pct <= 4 and rsi14 >= 45 and rsi14 <= 65:
        return {"signal": "回測支撐", "trend_type": "健康回調", "pattern": "主升後回測均線支撐，量縮不破為買點"}

    # ── 轉強型態：從弱轉強的反彈 ────────────────────
    if close_now > ma20 and ma5 >= ma10 and vol_ratio5 >= 1.1 and macd_hist > 0 and rsi14 >= 50:
        return {"signal": "轉強訊號", "trend_type": "由弱轉強", "pattern": "重新站上均線，量能配合，轉強結構確立"}

    # ── 觀察型態 ─────────────────────────────────────
    if abs(close_now - ma20) / max(ma20, 1) <= 0.025 and 0.85 <= vol_ratio5 <= 1.15:
        return {"signal": "盤整觀察", "trend_type": "橫向整理", "pattern": "量縮貼近均線盤整，等待方向確認"}

    if near_high20 and vol_ratio5 >= 1.15 and rsi14 < 72:
        return {"signal": "高點壓力", "trend_type": "測試壓力", "pattern": "接近前高壓力，放量突破前先觀察"}

    # ── 弱勢型態 ─────────────────────────────────────
    if close_now < ma5 < ma10 < ma20:
        return {"signal": "空頭排列", "trend_type": "均線空頭", "pattern": "均線全面空頭排列，趨勢偏弱"}

    if near_low20 and rsi14 < 35:
        return {"signal": "低檔測試", "trend_type": "支撐測試", "pattern": "測試近期低點支撐，需觀察能否止穩"}

    return {"signal": "結構待確認", "trend_type": "方向未明", "pattern": "目前缺乏明確技術訊號，先觀察"}


def build_setup_reason(
    name: str, close_now: float, setup_score: float,
    ma5: float, ma10: float, ma20: float,
    high20: float, low20: float,
    vol_now: int, avg_vol5: float, avg_vol20: float,
    vol_contraction_ratio: float, vol_ratio5: float,
    rsi14: float, macd_hist: float, macd_line: float, signal_line: float,
    ma20_slope_pct: float, change_percent: float,
    pattern_text: str, atr14: float,
) -> str:
    """
    ★ 以「為什麼這檔值得關注」的角度撰寫分析理由
    聚焦在結構優勢，而非描述今天發生什麼
    """
    parts: List[str] = []
    dist_pct = (close_now - ma20) / ma20 * 100 if ma20 > 0 else 0.0

    # 1. 均線結構說明
    if close_now > ma5 > ma10 > ma20:
        if ma20_slope_pct > 0.2:
            parts.append(
                f"均線呈完整多頭排列（MA5 {format_price_value(ma5)} > MA10 {format_price_value(ma10)} > MA20 {format_price_value(ma20)}），"
                f"且 MA20 斜率向上（+{ma20_slope_pct:.2f}%），中期趨勢結構強健"
            )
        else:
            parts.append(
                f"均線多頭排列結構完整，現價（{format_price_value(close_now)}）高於 MA20 {dist_pct:.1f}%，偏離適中"
            )
    elif close_now > ma20:
        parts.append(
            f"現價（{format_price_value(close_now)}）站穩 MA20（{format_price_value(ma20)}）之上 {dist_pct:.1f}%，"
            f"{'均線開始向上排列，中期結構改善中' if ma5 >= ma10 else '短均線尚未完全排列，趨勢仍在確認'}"
        )

    # 2. 量能結構（★ 重點：縮量整理是好事）
    is_dry = vol_contraction_ratio < 0.80
    if is_dry and vol_ratio5 >= 1.2:
        parts.append(
            f"量能型態優良：近期 5 日均量僅為 20 日均量的 {vol_contraction_ratio:.0%}（量縮整理充分），"
            f"今日量能達 {vol_now/1000:.0f}K 張（5 日均量 {vol_ratio5:.1f} 倍），縮量蓄積後放量啟動"
        )
    elif is_dry:
        parts.append(
            f"近期量能縮至 20 日均量的 {vol_contraction_ratio:.0%}，籌碼正在沉澱整理中，"
            f"浮額洗清有助於後續走勢穩健，等待放量確認"
        )
    elif vol_ratio5 >= 1.3:
        parts.append(
            f"今日量能達 {vol_now/1000:.0f}K 張，為 5 日均量的 {vol_ratio5:.1f} 倍，"
            f"市場參與度提升，資金開始注意此標的"
        )
    else:
        parts.append(
            f"量能平穩（今日 {vol_now/1000:.0f}K 張），無異常放量或量縮，屬正常換手節奏"
        )

    # 3. RSI 分析（強調動能健康度）
    if IDEAL_RSI_LOW <= rsi14 <= IDEAL_RSI_HIGH:
        parts.append(
            f"RSI(14) {rsi14:.1f} 落在最佳動能區間（50-68），"
            "技術面動能充足但未過熱，空間最充裕"
        )
    elif 45 <= rsi14 < IDEAL_RSI_LOW:
        parts.append(
            f"RSI(14) {rsi14:.1f} 在中性偏弱區回升，若能有效突破 50 將確認動能回歸"
        )
    elif rsi14 > 70:
        parts.append(
            f"RSI(14) {rsi14:.1f} 偏高，短線動能強但追價風險上升，建議等回測後再評估"
        )

    # 4. MACD 分析
    if macd_hist > 0 and macd_line > signal_line:
        parts.append(
            f"MACD 動能正向（Hist {macd_hist:.3f}），DIF 站上 MACD，中期多頭動能確立"
        )
    elif macd_hist <= 0 and macd_line > signal_line:
        parts.append(
            f"MACD DIF 已超越 Signal（{macd_line:.3f} vs {signal_line:.3f}），"
            "柱狀體即將由負轉正，動能黃金交叉即將成立"
        )
    else:
        parts.append(
            f"MACD 動能尚未完全轉正（Hist {macd_hist:.3f}），需等待進一步確認"
        )

    # 5. 近 20 日高低位置（描述壓力支撐結構）
    if high20 > 0 and low20 > 0:
        range20 = high20 - low20
        pos20   = (close_now - low20) / range20 if range20 > 0 else 0.5
        if close_now >= high20 * 0.975:
            parts.append(
                f"現價逼近近 20 日最高點（{format_price_value(high20)}），正在突破壓力關卡，"
                "若能收盤站穩代表趨勢確認"
            )
        elif pos20 >= 0.65:
            parts.append(
                f"現價位於近 20 日高低區間上緣（{pos20:.0%} 位置），強勢整理中"
            )
        elif pos20 >= 0.4:
            parts.append(
                f"現價位於區間中段（近 20 日低 {format_price_value(low20)} ～ 高 {format_price_value(high20)}），"
                "距前高仍有空間"
            )

    # 6. 操作建議邏輯
    if setup_score >= 75:
        parts.append(f"整體設置評分 {setup_score:.0f}/100，屬高品質進場候選，結構清晰")
    elif setup_score >= 55:
        parts.append(f"整體設置評分 {setup_score:.0f}/100，結構偏佳，可列入觀察名單")
    else:
        parts.append(f"整體設置評分 {setup_score:.0f}/100，型態屬「{pattern_text}」")

    return f"【{name}】" + "；".join(parts) + "。"


def build_historical_technical_comment(
    ma5: float, ma10: float, ma20: float, avg_vol5: float, avg_vol20: float,
    rsi14: float, macd_line: float, signal_line: float, macd_hist: float,
    high20: float, low20: float, atr14: float,
) -> str:
    return "；".join([
        f"MA5/{format_price_value(ma5)}  MA10/{format_price_value(ma10)}  MA20/{format_price_value(ma20)}",
        f"5日均量 {format_number(avg_vol5)} 張 / 20日均量 {format_number(avg_vol20)} 張",
        f"RSI(14)={rsi14:.2f}",
        f"MACD DIF {macd_line:.3f} / Signal {signal_line:.3f} / Hist {macd_hist:.3f}",
        f"20日區間 {format_price_value(low20)} ～ {format_price_value(high20)}",
        f"ATR(14)={format_price_value(atr14)}",
    ]) + "。"


def build_strategy_for_setup(
    signal: str, setup_score: float,
    price: float, ma5: float, ma20: float,
    high20: float, low20: float, atr14: float,
    rsi14: float, change_percent: float,
) -> Dict[str, str]:
    """★ 根據型態和評分給出具體操作建議"""

    # 進場區間：以 MA5 附近為參考，不在急漲日追高
    bs = max(atr14 * 0.5, price * 0.01, 0.2)
    bl = max(atr14 * 1.0, price * 0.02, 0.5)

    high_quality_signals = {"蓄積啟動", "主升延續", "多頭趨勢", "突破測試", "轉強訊號"}
    medium_signals       = {"整理蓄積", "回測支撐"}
    watch_signals        = {"盤整觀察", "高點壓力", "結構待確認"}
    weak_signals         = {"空頭排列", "低檔測試"}

    if signal in high_quality_signals and setup_score >= 65:
        rating = "A"
        bias   = "積極偏多"
        style  = "拉回布局 / 突破追進"
        action = (
            f"進場策略：若今日為放量突破，可於次日開盤回測 {format_price_value(ma5)} 附近承接；"
            f"若整理中尚未放量，等量能放大突破 {format_price_value(high20)} 後再追進，不搶跑。"
            f"持倉期間以 MA5 能否守穩為關鍵觀察點，量縮守 MA5 則續持，跌破 MA5 且量增則出場。"
        )
        risk = f"主要風險：若突破後次日量縮且收盤跌回壓力區下方，需立即承認假突破，停損在進場價下方 1 個 ATR（≈ {format_price_value(atr14)}）。"

        entry_low  = max(ma5 - bs, low20 * 0.99, price * 0.97, 0.01)
        entry_high = min(ma5 + bs, price * 1.02)
        target_low  = max(high20 * 1.01, price * 1.04)
        target_high = max(target_low, price + bl * 2.2)
        stop = max(ma20 - bs * 0.5, 0.01)

    elif signal in medium_signals or (signal in high_quality_signals and setup_score >= 45):
        rating = "B+"
        bias   = "偏多觀察"
        style  = "等確認後介入"
        action = (
            f"操作策略：優先等待量能放大（今日量 > 5 日均量 20% 以上）且收盤站穩 {format_price_value(high20)} 上方，"
            f"確認突破後可於次日開盤至 {format_price_value(high20 + bs):.2f} 區間介入。"
            f"不搶在突破前佈局，避免假突破損耗。"
        )
        risk = "主要風險：突破後若量縮且無法守穩關鍵價位，立即減碼，不戀戰。"

        entry_low  = max(high20, price * 0.99, 0.01)
        entry_high = max(high20 + bs, entry_low)
        target_low  = max(high20 * 1.03, price * 1.04)
        target_high = max(target_low, price + bl * 1.8)
        stop = max(ma20 - bs, 0.01)

    elif signal in watch_signals:
        rating = "C"
        bias   = "中性觀察"
        style  = "等待表態"
        action = (
            "目前處於整理觀察階段，不建議主動建倉。"
            f"設定兩個觀察觸發點：①收盤放量突破 {format_price_value(high20)}；"
            f"②量縮縮手至 20 日均量 70% 以下後整理穩定。任一條件成立再評估進場。"
        )
        risk = "整理期不宜頻繁進出，耐心等待明確方向訊號的出現。"

        entry_low  = max(high20 * 0.99, 0.01)
        entry_high = high20 + bs
        target_low  = high20 + bs
        target_high = high20 + bl * 1.5
        stop = max(low20 - bs * 0.3, 0.01)

    else:  # weak or unknown
        rating = "D"
        bias   = "保守觀望"
        style  = "不建議操作"
        action = (
            "目前技術結構偏弱，不在選股標準內。"
            "持有者考慮利用反彈至短均線壓力減碼；"
            "空倉者等待量縮止跌、重新站回 MA20 後再評估。"
        )
        risk = "弱勢股逢低承接勝率偏低，以保本為優先。"

        entry_low   = price * 0.99
        entry_high  = price
        target_low  = price * 1.02
        target_high = price * 1.04
        stop = max(low20 - bs, 0.01)

    trend_map = {
        "蓄積啟動":  "縮量蓄積→啟動",
        "主升延續":  "主升段延續",
        "多頭趨勢":  "多頭趨勢",
        "突破測試":  "突破壓力",
        "轉強訊號":  "由弱轉強",
        "整理蓄積":  "整理蓄積",
        "回測支撐":  "回調測試支撐",
        "盤整觀察":  "橫向整理",
        "高點壓力":  "壓力測試",
        "空頭排列":  "弱勢空頭",
        "低檔測試":  "低檔支撐",
        "結構待確認":"方向未明",
    }
    trend_type = trend_map.get(signal, "觀察中")

    return {
        "operation_rating": rating, "operation_bias": bias, "operation_style": style,
        "strategy_action": action, "risk_note": risk, "trend_type": trend_type,
        "entry_price":  format_price_range(entry_low, entry_high),
        "target_price": format_price_range(target_low, target_high),
        "stop_loss":    format_price_value(stop),
    }


def calc_risk_reward(entry_price: str, target_price: str, stop_loss: str) -> str:
    entry_mid  = parse_range_mid(entry_price, 0.0)
    target_mid = parse_range_mid(target_price, 0.0)
    stop = safe_float(stop_loss, 0.0)
    if entry_mid <= 0 or target_mid <= 0 or stop <= 0: return ""
    reward = abs(target_mid - entry_mid)
    risk   = abs(entry_mid - stop)
    if risk <= 0: return ""
    return f"1:{reward / risk:.2f}"


# =========================
# Historical K analysis
# =========================
def get_history_cache(symbol: str) -> Optional[Dict[str, Any]]:
    item = _HISTORY_CACHE.get(symbol)
    if not item: return None
    fetched_at = item.get("fetched_at")
    if not isinstance(fetched_at, datetime): return None
    if (now_taipei() - fetched_at).total_seconds() > HISTORY_CACHE_HOURS * 3600: return None
    return item.get("data")


def set_history_cache(symbol: str, data: Dict[str, Any]) -> None:
    if len(_HISTORY_CACHE) >= HISTORY_CACHE_MAX_SIZE:
        cutoff = int(HISTORY_CACHE_MAX_SIZE * 0.8)
        sorted_keys = sorted(_HISTORY_CACHE, key=lambda k: _HISTORY_CACHE[k].get("fetched_at", datetime.min))
        for k in sorted_keys[:len(sorted_keys) - cutoff]:
            _HISTORY_CACHE.pop(k, None)
    _HISTORY_CACHE[symbol] = {"fetched_at": now_taipei(), "data": data}


def ema(values: List[float], period: int) -> List[float]:
    if not values: return []
    alpha = 2 / (period + 1)
    result = [values[0]]
    for v in values[1:]:
        result.append(v * alpha + result[-1] * (1 - alpha))
    return result


def calc_rsi(closes: List[float], period: int = 14) -> float:
    if len(closes) <= period: return 50.0
    gains, losses = [], []
    for i in range(1, len(closes)):
        diff = closes[i] - closes[i - 1]
        gains.append(max(diff, 0))
        losses.append(abs(min(diff, 0)))
    avg_gain = avg(gains[:period])
    avg_loss = avg(losses[:period])
    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
    if avg_loss == 0: return 100.0
    return 100 - (100 / (1 + avg_gain / avg_loss))


def calc_macd(closes: List[float]) -> Tuple[float, float, float]:
    if len(closes) < 35: return 0.0, 0.0, 0.0
    ema12 = ema(closes, 12)
    ema26 = ema(closes, 26)
    macd_series  = [a - b for a, b in zip(ema12, ema26)]
    signal_series = ema(macd_series, 9)
    return macd_series[-1], signal_series[-1], macd_series[-1] - signal_series[-1]


def calc_atr(candles: List[Dict[str, Any]], period: int = 14) -> float:
    if len(candles) < 2: return 0.0
    trs: List[float] = []
    prev_close = safe_float(candles[0].get("close"))
    for c in candles[1:]:
        h = safe_float(c.get("high"))
        l = safe_float(c.get("low"))
        close = safe_float(c.get("close"))
        trs.append(max(h - l, abs(h - prev_close), abs(l - prev_close)))
        prev_close = close
    return avg(trs[-period:]) if trs else 0.0


def fetch_symbol_daily_candles(symbol: str) -> Dict[str, Any]:
    cached = get_history_cache(symbol)
    if cached: return cached
    stock_client = get_stock_rest_client()
    to_date   = now_taipei().strftime("%Y-%m-%d")
    from_date = (now_taipei() - timedelta(days=420)).strftime("%Y-%m-%d")
    resp  = stock_client.historical.candles(**{"symbol": symbol, "from": from_date, "to": to_date, "timeframe": "D", "sort": "asc"})
    rows  = extract_rows(resp)
    candles: List[Dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict): continue
        candles.append({"date": safe_str(row.get("date")), "open": safe_float(row.get("open")), "high": safe_float(row.get("high")), "low": safe_float(row.get("low")), "close": safe_float(row.get("close")), "volume": safe_int(row.get("volume")), "change": safe_float(row.get("change"))})
    candles = [x for x in candles if x["close"] > 0]
    if len(candles) > 420: candles = candles[-420:]
    data = {"candles": candles}
    set_history_cache(symbol, data)
    return data


def build_historical_analysis_for_stock(base_stock: Dict[str, Any]) -> Dict[str, Any]:
    symbol = safe_str(base_stock.get("symbol"))
    if not symbol: return base_stock

    try:
        history_data = fetch_symbol_daily_candles(symbol)
        candles = history_data.get("candles", [])
        if len(candles) < 30: return base_stock

        closes  = [safe_float(x.get("close"))  for x in candles if safe_float(x.get("close"))  > 0]
        highs   = [safe_float(x.get("high"))   for x in candles if safe_float(x.get("high"))   > 0]
        lows    = [safe_float(x.get("low"))    for x in candles if safe_float(x.get("low"))    > 0]
        volumes = [safe_float(x.get("volume")) for x in candles]

        if len(closes) < 25: return base_stock

        close_now = safe_float(base_stock.get("price")) or closes[-1]
        ma5  = avg(closes[-5:])
        ma10 = avg(closes[-10:])
        ma20 = avg(closes[-20:])
        high20 = max(highs[-20:]) if len(highs) >= 20 else max(highs)
        low20  = min(lows[-20:])  if len(lows)  >= 20 else min(lows)

        vol_now    = safe_int(base_stock.get("volume")) or safe_int(volumes[-1])
        avg_vol5   = avg(volumes[-5:])
        avg_vol20  = avg(volumes[-20:])
        vol_ratio5 = vol_now / avg_vol5 if avg_vol5 > 0 else 1.0

        # ★ 新增：量能縮量比（判斷是否有縮量整理型態）
        vol_contraction_ratio = calc_vol_contraction_ratio(volumes, lookback=5)

        rsi14 = calc_rsi(closes, 14)
        macd_line, signal_line, macd_hist = calc_macd(closes)
        atr14 = calc_atr(candles, 14)

        # ★ 新增：MA20 斜率（判斷趨勢是否真的在向上）
        ma20_series = [avg(closes[max(0, i-19):i+1]) for i in range(len(closes)-1, max(len(closes)-11, 18), -1)]
        ma20_series.reverse()
        ma20_slope_pct = calc_ma_slope_pct(ma20_series, period=5) if len(ma20_series) >= 5 else 0.0

        change_percent = safe_float(base_stock.get("change_percent"))

        # ★ 核心評分：用新的 setup score
        setup_score = calc_setup_score(
            close_now=close_now, ma5=ma5, ma10=ma10, ma20=ma20,
            high20=high20, low20=low20, rsi14=rsi14,
            macd_hist=macd_hist, macd_line=macd_line, signal_line=signal_line,
            vol_now=vol_now, avg_vol5=avg_vol5, avg_vol20=avg_vol20,
            vol_contraction_ratio=vol_contraction_ratio,
            ma20_slope_pct=ma20_slope_pct, change_percent=change_percent, price=close_now,
        )

        # ★ 型態分類（使用新版，考慮縮量型態）
        pattern_info = classify_daily_pattern(
            close_now=close_now, ma5=ma5, ma10=ma10, ma20=ma20,
            high20=high20, low20=low20, vol_ratio5=vol_ratio5,
            vol_contraction_ratio=vol_contraction_ratio,
            rsi14=rsi14, macd_hist=macd_hist, ma20_slope_pct=ma20_slope_pct,
        )

        # ★ 分析理由（以「為什麼值得看」的角度撰寫）
        reason = build_setup_reason(
            name=safe_str(base_stock.get("name")), close_now=close_now, setup_score=setup_score,
            ma5=ma5, ma10=ma10, ma20=ma20, high20=high20, low20=low20,
            vol_now=vol_now, avg_vol5=avg_vol5, avg_vol20=avg_vol20,
            vol_contraction_ratio=vol_contraction_ratio, vol_ratio5=vol_ratio5,
            rsi14=rsi14, macd_hist=macd_hist, macd_line=macd_line, signal_line=signal_line,
            ma20_slope_pct=ma20_slope_pct, change_percent=change_percent,
            pattern_text=pattern_info["pattern"], atr14=atr14,
        )
        technical_comment = build_historical_technical_comment(
            ma5=ma5, ma10=ma10, ma20=ma20, avg_vol5=avg_vol5, avg_vol20=avg_vol20,
            rsi14=rsi14, macd_line=macd_line, signal_line=signal_line, macd_hist=macd_hist,
            high20=high20, low20=low20, atr14=atr14,
        )

        # ★ 策略建議（根據型態和評分給出具體操作）
        strategy_result = build_strategy_for_setup(
            signal=pattern_info["signal"], setup_score=setup_score,
            price=close_now, ma5=ma5, ma20=ma20, high20=high20, low20=low20,
            atr14=atr14, rsi14=rsi14, change_percent=change_percent,
        )
        risk_reward = calc_risk_reward(strategy_result["entry_price"], strategy_result["target_price"], strategy_result["stop_loss"])

        merged = dict(base_stock)
        merged.update({
            "signal":           pattern_info["signal"],
            "trend_type":       strategy_result["trend_type"],
            "reason":           reason,
            "technical_comment": technical_comment,
            "operation_rating": strategy_result["operation_rating"],
            "operation_bias":   strategy_result["operation_bias"],
            "operation_style":  strategy_result["operation_style"],
            "strategy_action":  strategy_result["strategy_action"],
            "entry_price":      strategy_result["entry_price"],
            "target_price":     strategy_result["target_price"],
            "stop_loss":        strategy_result["stop_loss"],
            "risk_reward":      risk_reward,
            "risk_note":        strategy_result["risk_note"],
            "recommendation_score": round(setup_score, 2),  # ★ 直接用 setup score
            "setup_score":      round(setup_score, 2),
            "analysis_source":  "historical_k",
        })
        return merged

    except Exception as e:
        logger.warning(f"[historical_k] {symbol} 分析失敗: {e}\n{traceback.format_exc()}")
        return base_stock


def build_focused_analysis(stock: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "symbol": stock.get("symbol", ""), "name": stock.get("name", ""), "market": stock.get("market", ""),
        "price": stock.get("price", 0), "change": stock.get("change", 0), "change_percent": stock.get("change_percent", 0),
        "volume": stock.get("volume", 0), "signal": stock.get("signal", ""), "trend_type": stock.get("trend_type", ""),
        "operation_rating": stock.get("operation_rating", ""), "operation_bias": stock.get("operation_bias", ""),
        "operation_style": stock.get("operation_style", ""), "technical_comment": stock.get("technical_comment", ""),
        "analysis": stock.get("reason", ""), "strategy_action": stock.get("strategy_action", ""),
        "entry_price": stock.get("entry_price", ""), "target_price": stock.get("target_price", ""),
        "stop_loss": stock.get("stop_loss", ""), "risk_reward": stock.get("risk_reward", ""),
        "risk_note": stock.get("risk_note", ""), "update_time": stock.get("update_time", ""),
    }


# =========================
# Snapshot（即時資料標準化）
# =========================
def normalize_snapshot_row(row: Dict[str, Any], market_label: str) -> Optional[Dict[str, Any]]:
    if not isinstance(row, dict): return None
    symbol = safe_str(row.get("symbol") or row.get("stockNo") or row.get("stock_no") or row.get("code") or row.get("ticker"))
    if not symbol: return None
    name = safe_str(row.get("name") or row.get("stockName") or row.get("stock_name") or symbol)
    if not is_valid_main_board_symbol(symbol, name): return None

    price = safe_float(row.get("lastPrice") or row.get("closePrice") or row.get("tradePrice") or row.get("price") or row.get("currentPrice"))
    if price <= MIN_PRICE: return None  # 排除低價股

    change         = safe_float(row.get("change") or row.get("priceChange") or row.get("changePrice"))
    previous_close = safe_float(row.get("previousClose") or row.get("referencePrice"))
    change_percent = safe_float(row.get("changePercent"))

    if previous_close <= 0 and price > 0 and change != 0:
        prev = price - change
        if prev > 0: previous_close = prev
    if change_percent == 0 and previous_close > 0 and change != 0:
        change_percent = (change / previous_close) * 100

    volume      = safe_int(row.get("tradeVolume") or row.get("volume") or row.get("totalVolume") or row.get("accumulatedVolume") or row.get("tradeVolumeAtBid"))
    trade_value = safe_int(row.get("tradeValue"))
    open_price  = safe_float(row.get("openPrice"))
    high_price  = safe_float(row.get("highPrice"))
    low_price   = safe_float(row.get("lowPrice"))
    update_time_raw = row.get("lastUpdated") or row.get("time") or 0
    category = price_category(price)

    # ★ Snapshot 的基礎評分（不追強，只給基礎分讓歷史分析覆蓋）
    # 這裡不再用 change_percent * 6 的追強公式
    liquidity_score = min(volume / 3000, 15)   # 流動性加分，最高 15
    stability_score = max(0, 10 - abs(change_percent) * 0.5)  # 穩定性，大漲大跌各扣分
    base_score = round(liquidity_score + stability_score, 2)

    # Snapshot 的訊號只做顯示用，不影響推薦排序
    signal = _snapshot_signal(change_percent, volume, calc_position_ratio(price, high_price, low_price))

    return {
        "market": market_label, "symbol": symbol, "name": name,
        "price": round(price, 2), "change": round(change, 2), "change_percent": round(change_percent, 2),
        "volume": volume, "trade_value": trade_value, "score": base_score,
        "recommendation_score": base_score,  # 將被歷史分析的 setup_score 覆蓋
        "prev_close": round(previous_close, 2) if previous_close > 0 else 0,
        "open": round(open_price, 2), "high": round(high_price, 2), "low": round(low_price, 2),
        "update_time": micros_to_taipei_str(update_time_raw), "update_time_raw": update_time_raw,
        "category": category, "signal": signal, "trend_type": "",
        "reason": "", "technical_comment": "", "operation_rating": "C",
        "operation_bias": "", "operation_style": "", "strategy_action": "",
        "entry_price": "", "target_price": "", "stop_loss": "", "risk_reward": "", "risk_note": "",
        "analysis_source": "snapshot",
    }


def _snapshot_signal(change_percent: float, volume: int, close_pos: float) -> str:
    """快照訊號（純顯示，不影響選股）"""
    if change_percent >= 6 and volume >= 10000 and close_pos >= 0.85: return "強勢主升"
    if change_percent >= 3 and close_pos >= 0.75: return "偏多走強"
    if -1 <= change_percent <= 1 and volume < 3000: return "量縮整理"
    if change_percent <= -3 and volume >= 5000: return "放量下跌"
    if change_percent > 0: return "小幅偏多"
    if change_percent < 0: return "小幅偏空"
    return "平盤"


# =========================
# Validation / Backtest
# =========================
def append_jsonl(filepath: str, row: Dict[str, Any]) -> None:
    try:
        os.makedirs(os.path.dirname(filepath) or ".", exist_ok=True)
        with open(filepath, "a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    except Exception as e:
        logger.warning(f"[validation] 寫入失敗: {e}")


def load_jsonl(filepath: str) -> List[Dict[str, Any]]:
    if not os.path.exists(filepath): return []
    rows: List[Dict[str, Any]] = []
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line: continue
                try: rows.append(json.loads(line))
                except Exception: continue
    except Exception as e:
        logger.warning(f"[validation] 讀取失敗: {e}")
    return rows


def determine_trade_direction(signal: str, operation_bias: str) -> str:
    long_signals  = {"蓄積啟動","主升延續","多頭趨勢","突破測試","轉強訊號","整理蓄積","回測支撐","偏多走強","強勢主升","小幅偏多"}
    short_signals = {"空頭排列","放量下跌","低檔測試"}
    if signal in long_signals:  return "long"
    if signal in short_signals: return "short"
    if "偏多" in operation_bias: return "long"
    if "偏空" in operation_bias: return "short"
    return "neutral"


def save_recommendation_snapshot(recs: List[Dict[str, Any]]) -> None:
    today    = now_taipei().strftime("%Y-%m-%d")
    existing = load_jsonl(VALIDATION_LOG_FILE)
    existing_keys = {(safe_str(x.get("date")), safe_str(x.get("symbol"))) for x in existing}
    for r in recs:
        symbol = safe_str(r.get("symbol"))
        if not symbol or (today, symbol) in existing_keys: continue
        row = {
            "date": today, "symbol": symbol, "name": safe_str(r.get("name")),
            "market": safe_str(r.get("market")), "pick_price": safe_float(r.get("price")),
            "signal": safe_str(r.get("signal")), "trend_type": safe_str(r.get("trend_type")),
            "operation_bias": safe_str(r.get("operation_bias")), "operation_rating": safe_str(r.get("operation_rating")),
            "recommendation_score": safe_float(r.get("recommendation_score")),
            "setup_score": safe_float(r.get("setup_score")),
            "entry_price": safe_str(r.get("entry_price")), "target_price": safe_str(r.get("target_price")),
            "stop_loss": safe_str(r.get("stop_loss")), "risk_reward": safe_str(r.get("risk_reward")),
        }
        append_jsonl(VALIDATION_LOG_FILE, row)


def find_candle_index_for_pick(candles: List[Dict[str, Any]], pick_date: date) -> int:
    exact_idx = next_idx = -1
    for i, c in enumerate(candles):
        c_date = parse_any_date(c.get("date"))
        if not c_date: continue
        if c_date == pick_date: exact_idx = i; break
        if c_date > pick_date and next_idx == -1: next_idx = i
    return exact_idx if exact_idx >= 0 else next_idx


def calc_directional_return(entry_price: float, exit_price: float, direction: str) -> float:
    if entry_price <= 0 or exit_price <= 0: return 0.0
    if direction == "short": return ((entry_price - exit_price) / entry_price) * 100
    return ((exit_price - entry_price) / entry_price) * 100


def evaluate_first_hit(
    future_bars: List[Dict[str, Any]], direction: str,
    target_price: float, stop_price: float,
) -> Dict[str, Any]:
    if direction not in {"long", "short"}:
        return {"first_hit": "not_applicable", "first_hit_day": 0, "target_hit": False, "target_hit_day": 0, "stop_hit": False, "stop_hit_day": 0}

    target_hit_day = stop_hit_day = 0
    first_hit = "none"; first_hit_day = 0

    for idx, bar in enumerate(future_bars, start=1):
        high = safe_float(bar.get("high"))
        low  = safe_float(bar.get("low"))
        hit_target = target_price > 0 and (high >= target_price if direction == "long" else low <= target_price)
        hit_stop   = stop_price   > 0 and (low  <= stop_price   if direction == "long" else high >= stop_price)

        if hit_target and target_hit_day == 0: target_hit_day = idx
        if hit_stop   and stop_hit_day   == 0: stop_hit_day   = idx

        if target_hit_day > 0 or stop_hit_day > 0:
            if target_hit_day > 0 and stop_hit_day > 0:
                first_hit = "both_same_bar" if target_hit_day == stop_hit_day else ("target" if target_hit_day < stop_hit_day else "stop")
                first_hit_day = min(target_hit_day, stop_hit_day)
            elif target_hit_day > 0:
                first_hit = "target"; first_hit_day = target_hit_day
            else:
                first_hit = "stop"; first_hit_day = stop_hit_day
            break

    return {"first_hit": first_hit, "first_hit_day": first_hit_day, "target_hit": target_hit_day > 0, "target_hit_day": target_hit_day, "stop_hit": stop_hit_day > 0, "stop_hit_day": stop_hit_day}


def calc_mfe_mae(pick_price: float, future_bars: List[Dict[str, Any]], direction: str) -> Dict[str, float]:
    if pick_price <= 0 or not future_bars: return {"mfe_pct": 0.0, "mae_pct": 0.0}
    highs = [safe_float(x.get("high")) for x in future_bars if safe_float(x.get("high")) > 0]
    lows  = [safe_float(x.get("low"))  for x in future_bars if safe_float(x.get("low"))  > 0]
    if not highs or not lows: return {"mfe_pct": 0.0, "mae_pct": 0.0}
    max_high = max(highs); min_low = min(lows)
    if direction == "short":
        return {"mfe_pct": round((pick_price - min_low)  / pick_price * 100, 2), "mae_pct": round((pick_price - max_high) / pick_price * 100, 2)}
    return {"mfe_pct": round((max_high - pick_price) / pick_price * 100, 2), "mae_pct": round((min_low - pick_price)  / pick_price * 100, 2)}


def evaluate_single_record(record: Dict[str, Any], holding_days: int = 5) -> Optional[Dict[str, Any]]:
    pick_date  = parse_any_date(record.get("date"))
    symbol     = safe_str(record.get("symbol"))
    pick_price = safe_float(record.get("pick_price"))
    if not pick_date or not symbol or pick_price <= 0: return None

    history_data = fetch_symbol_daily_candles(symbol)
    candles = history_data.get("candles", [])
    if len(candles) < holding_days + 2: return None

    pick_idx = find_candle_index_for_pick(candles, pick_date)
    if pick_idx < 0: return None

    future_bars = candles[pick_idx + 1: pick_idx + 1 + holding_days]
    if len(future_bars) < holding_days: return None

    # ★ 用 T+1 開盤價作為實際進場成本（更真實）
    t1_open = safe_float(future_bars[0].get("open")) if future_bars else pick_price
    actual_entry = t1_open if t1_open > 0 else pick_price

    direction  = determine_trade_direction(signal=safe_str(record.get("signal")), operation_bias=safe_str(record.get("operation_bias")))
    target_mid = parse_range_mid(record.get("target_price"), 0.0)
    stop_price = safe_float(record.get("stop_loss"), 0.0)

    closes_by_n: Dict[int, float] = {}
    returns_by_n: Dict[int, float] = {}
    raw_returns_by_n: Dict[int, float] = {}

    for n in VALIDATION_FORWARD_BARS:
        if len(future_bars) >= n:
            close_n = safe_float(future_bars[n - 1].get("close"))
            closes_by_n[n]      = round(close_n, 2)
            raw_returns_by_n[n] = round((close_n - pick_price) / pick_price * 100, 2) if pick_price > 0 else 0.0
            # ★ 用實際進場成本（T+1 開盤）計算報酬
            returns_by_n[n]     = round(calc_directional_return(actual_entry, close_n, direction), 2)

    hit_info  = evaluate_first_hit(future_bars=future_bars, direction=direction, target_price=target_mid, stop_price=stop_price)
    excursion = calc_mfe_mae(pick_price=actual_entry, future_bars=future_bars, direction=direction)

    return {
        "date": safe_str(record.get("date")), "symbol": symbol, "name": safe_str(record.get("name")),
        "market": safe_str(record.get("market")), "signal": safe_str(record.get("signal")),
        "trend_type": safe_str(record.get("trend_type")), "operation_bias": safe_str(record.get("operation_bias")),
        "operation_rating": safe_str(record.get("operation_rating")), "direction": direction,
        "pick_price": round(pick_price, 2), "t1_open": round(t1_open, 2), "actual_entry": round(actual_entry, 2),
        "entry_price": safe_str(record.get("entry_price")), "target_price": safe_str(record.get("target_price")),
        "target_mid": round(target_mid, 2) if target_mid > 0 else 0.0,
        "stop_loss": safe_str(record.get("stop_loss")), "stop_price": round(stop_price, 2) if stop_price > 0 else 0.0,
        "risk_reward": safe_str(record.get("risk_reward")), "setup_score": safe_float(record.get("setup_score")),
        "close_t1": closes_by_n.get(1, 0.0), "close_t3": closes_by_n.get(3, 0.0), "close_t5": closes_by_n.get(5, 0.0),
        "raw_return_t1": raw_returns_by_n.get(1, 0.0), "raw_return_t3": raw_returns_by_n.get(3, 0.0), "raw_return_t5": raw_returns_by_n.get(5, 0.0),
        "strategy_return_t1": returns_by_n.get(1, 0.0), "strategy_return_t3": returns_by_n.get(3, 0.0), "strategy_return_t5": returns_by_n.get(5, 0.0),
        "mfe_pct_5d": excursion["mfe_pct"], "mae_pct_5d": excursion["mae_pct"],
        "first_hit": hit_info["first_hit"], "first_hit_day": hit_info["first_hit_day"],
        "target_hit": hit_info["target_hit"], "target_hit_day": hit_info["target_hit_day"],
        "stop_hit": hit_info["stop_hit"], "stop_hit_day": hit_info["stop_hit_day"],
        "win_t1": returns_by_n.get(1, 0.0) > 0, "win_t3": returns_by_n.get(3, 0.0) > 0, "win_t5": returns_by_n.get(5, 0.0) > 0,
    }


def get_cached_validation_rows(lookback_days: int, holding_days: int) -> List[Dict[str, Any]]:
    now = now_taipei()
    c = _VALIDATION_CACHE
    if (c["rows"] is not None and c["fetched_at"] is not None
            and c["lookback_days"] == lookback_days and c["holding_days"] == holding_days
            and (now - c["fetched_at"]).total_seconds() < VALIDATION_CACHE_SECONDS):
        return c["rows"]

    records = load_jsonl(VALIDATION_LOG_FILE)
    today   = now.date()
    matured = [r for r in records if (d := parse_any_date(r.get("date"))) and holding_days <= (today - d).days <= lookback_days]

    results: List[Dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=3) as executor:
        future_to_symbol = {executor.submit(evaluate_single_record, r, holding_days): safe_str(r.get("symbol")) for r in matured}
        for future in as_completed(future_to_symbol):
            try:
                item = future.result()
                if item: results.append(item)
            except Exception as e:
                logger.warning(f"[validation] {future_to_symbol[future]} 驗證失敗: {e}")

    results.sort(key=lambda x: (safe_str(x.get("date")), safe_float(x.get("strategy_return_t5"))), reverse=True)
    _VALIDATION_CACHE.update({"rows": results, "fetched_at": now, "lookback_days": lookback_days, "holding_days": holding_days})
    return results


def summarize_by_key(rows: List[Dict[str, Any]], key_name: str) -> List[Dict[str, Any]]:
    stats: Dict[str, Dict[str, Any]] = {}
    for r in rows:
        kv = safe_str(r.get(key_name)) or "未分類"
        if kv not in stats:
            stats[kv] = {key_name: kv, "count": 0, "win_t1": 0, "win_t3": 0, "win_t5": 0,
                         "target_hit": 0, "stop_hit": 0, "both_same_bar": 0,
                         "srt1": 0.0, "srt3": 0.0, "srt5": 0.0, "raw5": 0.0, "mfe": 0.0, "mae": 0.0}
        s = stats[kv]; s["count"] += 1
        s["srt1"] += safe_float(r.get("strategy_return_t1")); s["srt3"] += safe_float(r.get("strategy_return_t3")); s["srt5"] += safe_float(r.get("strategy_return_t5"))
        s["raw5"] += safe_float(r.get("raw_return_t5")); s["mfe"] += safe_float(r.get("mfe_pct_5d")); s["mae"] += safe_float(r.get("mae_pct_5d"))
        if r.get("win_t1"): s["win_t1"] += 1
        if r.get("win_t3"): s["win_t3"] += 1
        if r.get("win_t5"): s["win_t5"] += 1
        if r.get("target_hit"): s["target_hit"] += 1
        if r.get("stop_hit"):   s["stop_hit"] += 1
        if safe_str(r.get("first_hit")) == "both_same_bar": s["both_same_bar"] += 1

    output = []
    for _, s in stats.items():
        n = s["count"]
        output.append({
            key_name: s[key_name], "count": n,
            "win_rate_t1": round(s["win_t1"] / n * 100, 2) if n else 0.0,
            "win_rate_t3": round(s["win_t3"] / n * 100, 2) if n else 0.0,
            "win_rate_t5": round(s["win_t5"] / n * 100, 2) if n else 0.0,
            "target_hit_rate_5d":    round(s["target_hit"]    / n * 100, 2) if n else 0.0,
            "stop_hit_rate_5d":      round(s["stop_hit"]      / n * 100, 2) if n else 0.0,
            "both_same_bar_rate_5d": round(s["both_same_bar"] / n * 100, 2) if n else 0.0,
            "avg_strategy_return_t1": round(s["srt1"] / n, 2) if n else 0.0,
            "avg_strategy_return_t3": round(s["srt3"] / n, 2) if n else 0.0,
            "avg_strategy_return_t5": round(s["srt5"] / n, 2) if n else 0.0,
            "avg_raw_return_t5":      round(s["raw5"] / n, 2) if n else 0.0,
            "avg_mfe_5d": round(s["mfe"] / n, 2) if n else 0.0,
            "avg_mae_5d": round(s["mae"] / n, 2) if n else 0.0,
        })
    output.sort(key=lambda x: (x["avg_strategy_return_t5"], x["win_rate_t5"]), reverse=True)
    return output


def summarize_validation_overall(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    n = len(rows)
    if n == 0:
        return {k: 0.0 for k in ["count","win_rate_t1","win_rate_t3","win_rate_t5","target_hit_rate_5d","stop_hit_rate_5d","both_same_bar_rate_5d","avg_strategy_return_t1","avg_strategy_return_t3","avg_strategy_return_t5","avg_raw_return_t5","avg_mfe_5d","avg_mae_5d"]} | {"count": 0}
    return {
        "count": n,
        "win_rate_t1": round(sum(1 for x in rows if x.get("win_t1")) / n * 100, 2),
        "win_rate_t3": round(sum(1 for x in rows if x.get("win_t3")) / n * 100, 2),
        "win_rate_t5": round(sum(1 for x in rows if x.get("win_t5")) / n * 100, 2),
        "target_hit_rate_5d":    round(sum(1 for x in rows if x.get("target_hit"))                     / n * 100, 2),
        "stop_hit_rate_5d":      round(sum(1 for x in rows if x.get("stop_hit"))                       / n * 100, 2),
        "both_same_bar_rate_5d": round(sum(1 for x in rows if safe_str(x.get("first_hit")) == "both_same_bar") / n * 100, 2),
        "avg_strategy_return_t1": round(sum(safe_float(x.get("strategy_return_t1")) for x in rows) / n, 2),
        "avg_strategy_return_t3": round(sum(safe_float(x.get("strategy_return_t3")) for x in rows) / n, 2),
        "avg_strategy_return_t5": round(sum(safe_float(x.get("strategy_return_t5")) for x in rows) / n, 2),
        "avg_raw_return_t5":      round(sum(safe_float(x.get("raw_return_t5"))       for x in rows) / n, 2),
        "avg_mfe_5d": round(sum(safe_float(x.get("mfe_pct_5d")) for x in rows) / n, 2),
        "avg_mae_5d": round(sum(safe_float(x.get("mae_pct_5d")) for x in rows) / n, 2),
    }


# =========================
# Market Data
# =========================
def fetch_snapshot_rows_by_type(stock_client, market: str, market_label: str, quote_type: str) -> List[Dict[str, Any]]:
    resp = stock_client.snapshot.quotes(market=market, type=quote_type)
    rows = extract_rows(resp)
    return [item for row in rows if (item := normalize_snapshot_row(row, market_label=market_label))]


def fetch_snapshot_market(market: str, market_label: str) -> List[Dict[str, Any]]:
    stock_client = get_stock_rest_client()
    try:
        return fetch_snapshot_rows_by_type(stock_client=stock_client, market=market, market_label=market_label, quote_type="ALLBUT0999")
    except Exception as e:
        raise Exception(f"{market_label} snapshot 失敗: {e}")


def get_all_stocks_raw() -> Dict[str, Any]:
    all_stocks: List[Dict[str, Any]] = []
    errors: List[str] = []
    results_map: Dict[str, List[Dict[str, Any]]] = {}
    with ThreadPoolExecutor(max_workers=2) as executor:
        future_to_label = {executor.submit(fetch_snapshot_market, code, label): label for code, label in [("TSE","上市"),("OTC","上櫃")]}
        for future in as_completed(future_to_label):
            label = future_to_label[future]
            try: results_map[label] = future.result()
            except Exception as e:
                errors.append(f"{label} 失敗: {e}")
                logger.warning(f"[snapshot] {label} 失敗: {e}")
    for label in ["上市","上櫃"]:
        if label in results_map: all_stocks.extend(results_map[label])
    stocks = merge_stock_lists(all_stocks)
    if not stocks: raise Exception("；".join(errors) if errors else "目前無法取得任何市場資料")
    latest_raw  = max((safe_int(s.get("update_time_raw")) for s in stocks), default=0)
    data_date   = micros_to_date_str(latest_raw) if latest_raw else now_taipei().strftime("%Y%m%d")
    last_update = micros_to_taipei_str(latest_raw) if latest_raw else format_dt_taipei(now_taipei())
    return {"stocks": stocks, "data_date": data_date, "last_update": last_update, "message": "；".join(errors) if errors else ""}


def get_cached_all_stocks(force_refresh: bool = False) -> Dict[str, Any]:
    now = now_taipei()
    if (not force_refresh and _CACHE["stocks"] is not None and _CACHE["fetched_at"] is not None
            and (now - _CACHE["fetched_at"]).total_seconds() < CACHE_SECONDS):
        return {"stocks": _CACHE["stocks"], "data_date": _CACHE["data_date"], "last_update": _CACHE["last_update"], "message": _CACHE.get("message", "")}
    result = get_all_stocks_raw()
    stocks = result["stocks"]
    _CACHE.update({
        "stocks": stocks, "fetched_at": now, "data_date": result["data_date"],
        "last_update": result["last_update"], "message": result.get("message", ""),
        "twse_total": len([s for s in stocks if s.get("market") == "上市"]),
        "otc_total":  len([s for s in stocks if s.get("market") == "上櫃"]),
        "categories": build_categories([s for s in stocks if is_main_board_stock(s)]),
    })
    return result


# =========================
# Business Logic
# =========================
def build_categories(stocks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    order  = ["0-10","10-20","20-50","50-100","100-200","200-500","500-1000","1000+"]
    counts = {k: 0 for k in order}
    for s in stocks:
        c = s.get("category", "")
        if c in counts: counts[c] += 1
    return [{"key": k, "label": k, "count": counts[k]} for k in order]


def filter_stocks(stocks: List[Dict[str, Any]], market: str = "all", category: str = "all", q: str = "", price_min: float = 0.0, price_max: float = 0.0) -> List[Dict[str, Any]]:
    result = stocks
    ml = safe_str(market).lower()
    if ml in ("all",""):       result = [s for s in result if is_main_board_stock(s)]
    elif ml in ("tse","上市"): result = [s for s in result if s.get("market") == "上市"]
    elif ml in ("otc","上櫃"): result = [s for s in result if s.get("market") == "上櫃"]
    else:                       result = [s for s in result if is_main_board_stock(s)]
    if category != "all": result = [s for s in result if s.get("category") == category]
    if q.strip():
        qq = q.strip().lower()
        result = [s for s in result if qq in safe_str(s.get("symbol")).lower() or qq in safe_str(s.get("name")).lower()]
    if price_min > 0: result = [s for s in result if safe_float(s.get("price")) >= price_min]
    if price_max > 0: result = [s for s in result if safe_float(s.get("price")) <= price_max]
    return result


def sort_stocks(stocks: List[Dict[str, Any]], sort_by: str = "score", sort_dir: str = "desc") -> List[Dict[str, Any]]:
    reverse = sort_dir.lower() != "asc"
    allowed = {"score","recommendation_score","price","change","change_percent","volume","trade_value","symbol","name","operation_rating"}
    key = sort_by if sort_by in allowed else "score"
    if key == "operation_rating":
        ro = {"A": 4, "B+": 3, "C": 2, "D": 1}
        return sorted(stocks, key=lambda x: ro.get(x.get("operation_rating",""), 0), reverse=reverse)
    return sorted(stocks, key=lambda x: x.get(key, 0), reverse=reverse)


def build_recommendations(stocks: List[Dict[str, Any]], top_n: int = 10) -> List[Dict[str, Any]]:
    now = now_taipei()
    if (_RECS_CACHE["recommendations"] is not None and _RECS_CACHE["fetched_at"] is not None
            and (now - _RECS_CACHE["fetched_at"]).total_seconds() < RECS_CACHE_SECONDS):
        return _RECS_CACHE["recommendations"]

    # ★ 嚴格前置過濾：不符合基本條件不進歷史分析
    candidates = [
        s for s in stocks
        if is_main_board_stock(s)
        and safe_float(s.get("price")) >= MIN_PRICE          # 最低股價
        and safe_int(s.get("volume")) >= MIN_AVG_DAILY_VOL   # 最低流動性（今日）
        and abs(safe_float(s.get("change_percent"))) < HARD_EXCLUDE_PCT  # 排除今日大漲大跌
    ]

    if not candidates:
        candidates = [s for s in stocks if is_main_board_stock(s) and safe_float(s.get("price")) > 0]

    # ★ 取前 50 個候選（按基礎分初步排序），交給歷史分析評定 setup_score
    # 故意取多一點（50 個），讓真正的 setup_score 做最終排序
    pre_candidates = sorted(candidates, key=lambda x: x.get("score", 0), reverse=True)[:50]

    result_map: Dict[str, Dict[str, Any]] = {}
    with ThreadPoolExecutor(max_workers=5) as executor:
        future_to_symbol = {executor.submit(build_historical_analysis_for_stock, stock): stock["symbol"] for stock in pre_candidates}
        for future in as_completed(future_to_symbol):
            symbol = future_to_symbol[future]
            try: result_map[symbol] = future.result()
            except Exception as e:
                logger.warning(f"[recommendations] {symbol} 歷史分析失敗: {e}")
                original = next((s for s in pre_candidates if s["symbol"] == symbol), None)
                if original: result_map[symbol] = original

    # ★ 最終排序：用 setup_score（真正的選股評分）
    analyzed = [result_map[s["symbol"]] for s in pre_candidates if s["symbol"] in result_map]
    analyzed.sort(
        key=lambda x: (
            x.get("setup_score", x.get("recommendation_score", 0)),
            x.get("volume", 0),
        ),
        reverse=True,
    )

    recs = analyzed[:top_n]
    save_recommendation_snapshot(recs)  # 只在重新生成時寫入
    _RECS_CACHE["recommendations"] = recs
    _RECS_CACHE["fetched_at"]      = now
    return recs


def find_focused_stock(filtered: List[Dict[str, Any]], q: str) -> Optional[Dict[str, Any]]:
    qq = safe_str(q).lower()
    if not qq: return None
    exact_symbol = [s for s in filtered if safe_str(s.get("symbol")).lower() == qq]
    if len(exact_symbol) == 1: return exact_symbol[0]
    exact_name = [s for s in filtered if safe_str(s.get("name")).lower() == qq]
    if len(exact_name) == 1: return exact_name[0]
    if len(filtered) == 1: return filtered[0]
    return None


def clean_stock_output(s: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "market": s.get("market",""), "symbol": s.get("symbol",""), "name": s.get("name",""),
        "price": s.get("price",0), "change": s.get("change",0), "change_percent": s.get("change_percent",0),
        "volume": s.get("volume",0), "score": s.get("score",0),
        "recommendation_score": s.get("recommendation_score",0),
        "setup_score": s.get("setup_score", 0),
        "prev_close": s.get("prev_close",0), "open": s.get("open",0), "high": s.get("high",0), "low": s.get("low",0),
        "update_time": s.get("update_time",""), "category": s.get("category",""),
        "signal": s.get("signal",""), "trend_type": s.get("trend_type",""), "reason": s.get("reason",""),
        "technical_comment": s.get("technical_comment",""), "operation_rating": s.get("operation_rating",""),
        "operation_bias": s.get("operation_bias",""), "operation_style": s.get("operation_style",""),
        "strategy_action": s.get("strategy_action",""), "entry_price": s.get("entry_price",""),
        "target_price": s.get("target_price",""), "stop_loss": s.get("stop_loss",""),
        "risk_reward": s.get("risk_reward",""), "risk_note": s.get("risk_note",""),
        "analysis_source": s.get("analysis_source","snapshot"),
    }


# =========================
# Startup & Routes
# =========================
@app.on_event("startup")
def startup_event():
    try:
        ensure_fubon_sdk()
        print("✅ Fubon SDK initialized successfully")
    except Exception as e:
        print(f"⚠️ Fubon SDK startup init failed: {e}")


@app.get("/")
def root():
    return {"message": "TW Stock Realtime Screener is running"}


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/stocks")
def get_stocks(
    market: str = Query("all"), category: str = Query("all"), q: str = Query(""),
    sort_by: str = Query("score"), sort_dir: str = Query("desc"),
    limit: int = Query(300, ge=1, le=5000), offset: int = Query(0, ge=0),
    price_min: float = Query(0), price_max: float = Query(0), force_refresh: bool = Query(False),
):
    try:
        result     = get_cached_all_stocks(force_refresh=force_refresh)
        all_stocks = result["stocks"]
        filtered   = filter_stocks(all_stocks, market=market, category=category, q=q, price_min=price_min, price_max=price_max)
        filtered   = sort_stocks(filtered, sort_by=sort_by, sort_dir=sort_dir)
        total_filtered = len(filtered)
        paged = filtered[offset: offset + limit]
        recs  = []
        if offset == 0 and market == "all" and not q.strip():
            recs = build_recommendations(all_stocks, top_n=10)
        cats       = _CACHE.get("categories") or build_categories([s for s in all_stocks if is_main_board_stock(s)])
        twse_total = _CACHE.get("twse_total", 0)
        otc_total  = _CACHE.get("otc_total",  0)
        focused = find_focused_stock(filtered, q)
        if focused:
            focused = build_historical_analysis_for_stock(focused)
            symbol  = focused.get("symbol", "")
            paged   = [focused if x.get("symbol") == symbol else x for x in paged]
        return {
            "success": True, "market_status": get_market_status_text(),
            "data_date": result["data_date"], "last_update": result["last_update"],
            "message": result.get("message",""), "total": total_filtered, "offset": offset, "limit": limit,
            "twse_total": twse_total, "otc_total": otc_total, "all_total": twse_total + otc_total,
            "categories": cats, "recommendations": [clean_stock_output(x) for x in recs],
            "focused_stock": build_focused_analysis(focused) if focused else None,
            "stocks": [clean_stock_output(x) for x in paged],
        }
    except Exception as e:
        return {"success": False, "error": str(e), "trace": traceback.format_exc(), "stocks": [], "recommendations": [], "categories": [], "focused_stock": None}


@app.get("/validation/logs")
def validation_logs(limit: int = Query(100, ge=1, le=5000)):
    try:
        rows = load_jsonl(VALIDATION_LOG_FILE)
        rows = sorted(rows, key=lambda x: (safe_str(x.get("date")), safe_str(x.get("symbol"))), reverse=True)
        return {"success": True, "total": len(rows), "items": rows[:limit]}
    except Exception as e:
        return {"success": False, "error": str(e), "trace": traceback.format_exc()}


@app.get("/validation/details")
def validation_details(lookback_days: int = Query(180, ge=5, le=365), holding_days: int = Query(5, ge=1, le=20)):
    try:
        rows = get_cached_validation_rows(lookback_days=lookback_days, holding_days=holding_days)
        return {"success": True, "lookback_days": lookback_days, "holding_days": holding_days, "count": len(rows), "items": rows}
    except Exception as e:
        return {"success": False, "error": str(e), "trace": traceback.format_exc()}


@app.get("/validation/summary")
def validation_summary(lookback_days: int = Query(180, ge=5, le=365), holding_days: int = Query(5, ge=1, le=20)):
    try:
        rows = get_cached_validation_rows(lookback_days=lookback_days, holding_days=holding_days)
        return {
            "success": True, "lookback_days": lookback_days, "holding_days": holding_days,
            "overall":             summarize_validation_overall(rows),
            "by_signal":           summarize_by_key(rows, "signal"),
            "by_operation_bias":   summarize_by_key(rows, "operation_bias"),
            "by_operation_rating": summarize_by_key(rows, "operation_rating"),
            "by_direction":        summarize_by_key(rows, "direction"),
        }
    except Exception as e:
        return {"success": False, "error": str(e), "trace": traceback.format_exc()}
