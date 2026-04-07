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
CACHE_SECONDS = 60  # 從 20 秒改為 60 秒，減少不必要的重抓

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


def is_etf_symbol(symbol: str, name: str) -> bool:
    s = safe_str(symbol)
    n = safe_str(name).upper()
    if s.startswith("00"):
        return True
    if "ETF" in n:
        return True
    return False


def is_valid_stock_symbol(symbol: str, is_etf: bool) -> bool:
    s = safe_str(symbol).upper()
    if not s:
        return False
    if is_etf:
        if len(s) in (4, 5, 6) and s[:4].isdigit():
            return True
        return False
    return len(s) == 4 and s.isdigit()


def merge_stock_lists(*groups: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    dedup: Dict[str, Dict[str, Any]] = {}
    for group in groups:
        for item in group:
            symbol = safe_str(item.get("symbol"))
            if not symbol:
                continue
            dedup[symbol] = item
    return list(dedup.values())


def is_main_board_stock(s: Dict[str, Any]) -> bool:
    market = safe_str(s.get("market"))
    return market in ("上市", "上櫃")


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

    close_near_high = close_position >= 0.85
    close_high = close_position >= 0.68
    close_low = close_position <= 0.35
    close_near_low = close_position <= 0.18

    gap_up = open_price > previous_close > 0
    heavy_volume = volume >= 3000
    very_heavy_volume = volume >= 10000
    extreme_volume = volume >= 30000

    if change_percent >= 6 and very_heavy_volume and close_near_high:
        return {
            "signal": "強勢主升",
            "reason": (
                "該標的今日屬於明確的強勢主升型態，漲幅擴大同時伴隨大量成交，且價格維持在日內高檔區，"
                "代表盤中追價買盤積極，多方對價格的掌控力相當強。"
            ),
        }
    if change_percent >= 4 and heavy_volume and close_near_high:
        return {
            "signal": "放量突破",
            "reason": "價格今日出現帶量上攻，且穩守高檔區，顯示突破並非虛漲，而是有實質買盤推動。",
        }
    if change_percent >= 2 and gap_up and close_high:
        return {
            "signal": "多方控盤",
            "reason": (
                "標的今日以偏強方式開出後，盤中價格重心持續墊高，且維持在相對高檔，"
                "反映多方在盤中節奏掌握上明顯占優。"
            ),
        }
    if change_percent >= 1.5 and heavy_volume and close_high and amplitude_pct <= 5:
        return {
            "signal": "趨勢續強",
            "reason": "價格延續原有偏多結構，盤中雖有波動，但整體重心仍維持上移，且量能未明顯失真。",
        }
    if change_percent > 1 and amplitude_pct <= 4 and close_high:
        return {
            "signal": "穩健走高",
            "reason": "標的今日屬於穩步墊高格局，雖非急攻型走勢，但價格仍能守在相對高位，顯示買盤承接結構穩定。",
        }
    if change_percent >= 0 and amplitude_pct > 4 and heavy_volume and close_high:
        return {
            "signal": "高檔換手",
            "reason": "價格今日盤中震盪明顯，但成交量活絡且仍守住高檔區，顯示市場在相對高位進行換手。",
        }
    if -1 <= change_percent <= 1 and amplitude_pct <= 3:
        return {
            "signal": "區間盤整",
            "reason": "價格目前處於明顯整理格局，日內波動有限，量價表現相對均衡，尚未形成明確攻擊或破位訊號。",
        }
    if -1 <= change_percent <= 1 and amplitude_pct > 4 and heavy_volume:
        return {
            "signal": "籌碼換手",
            "reason": "標的今日盤中振幅偏大，但最終漲跌幅收斂，且成交量顯著放大，反映多空雙方對價格認知分歧。",
        }
    if change_percent <= -2 and change_percent > -5 and close_low and not very_heavy_volume:
        return {
            "signal": "拉回整理",
            "reason": "價格今日出現明顯回檔，且落在日內偏低區，顯示短線上方賣壓開始增加，但量能尚未失控。",
        }
    if change_percent <= -3 and heavy_volume:
        return {
            "signal": "放量修正",
            "reason": "標的今日呈現放量下跌格局，顯示市場調節賣壓明顯升溫，短線籌碼穩定度轉弱。",
        }
    if change_percent <= -6 and very_heavy_volume and close_near_low:
        return {
            "signal": "弱勢破位",
            "reason": "價格今日出現明顯破位下跌，跌幅擴大且伴隨大量成交，原有支撐結構已遭到實質破壞。",
        }
    if extreme_volume and amplitude_pct >= 5:
        return {
            "signal": "爆量震盪",
            "reason": "標的今日成交量顯著放大，且盤中振幅明顯擴大，顯示市場高度聚焦，但多空對方向尚未取得一致共識。",
        }
    if change_percent < 0 and not heavy_volume and not close_near_low and amplitude_pct <= 4:
        return {
            "signal": "弱中透穩",
            "reason": "價格今日雖小幅收低，但跌幅仍屬可控範圍，且未見明顯恐慌性賣壓，市場偏向觀望。",
        }
    if change_percent > 0:
        return {
            "signal": "小幅偏多",
            "reason": "價格今日小幅收高，整體價格結構仍偏正向，顯示短線買盤尚具一定支撐力。",
        }
    if change_percent < 0:
        return {
            "signal": "小幅偏空",
            "reason": "價格今日小幅收低，反映短線追價意願略顯不足，盤面資金態度偏向保守。",
        }
    return {
        "signal": "中性觀望",
        "reason": "目前缺乏明確方向訊號，量價結構尚未形成具辨識度的趨勢優勢，短線仍應以觀察為主。",
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
        extra.append("目前價格貼近當日高點，顯示盤中買盤支撐力道仍在")
    elif pos <= 0.2:
        extra.append("目前價格接近當日低點，短線承接力仍偏弱")
    else:
        extra.append("目前價格位於日內區間中段，市場仍在整理方向")

    if open_price > 0:
        if price > open_price:
            extra.append("價格站穩開盤價之上，日內多方仍略占優勢")
        elif price < open_price:
            extra.append("價格跌破開盤價，顯示追價買盤續航力不足")

    if change_percent >= 6:
        extra.append("短線漲幅已明顯擴大，追價風險需特別留意")
    elif 3 <= change_percent < 6:
        extra.append("漲幅具延續性，若量能維持，仍有續強機會")
    elif -6 < change_percent <= -3:
        extra.append("跌幅偏大，市場短線情緒轉趨保守")
    elif change_percent <= -6:
        extra.append("跌勢已進入壓力測試區，承接買盤是否回流將是關鍵")

    if volume >= 30000:
        extra.append("成交量顯著放大，市場關注度與資金參與度同步提升")
    elif volume >= 10000:
        extra.append("量能維持在活絡水準，有利短線方向延續")
    elif volume < 3000:
        extra.append("成交量偏低，後續動能仍需觀察")

    if amplitude_pct >= 6:
        extra.append("日內振幅偏大，代表波動風險同步上升")
    elif amplitude_pct <= 2:
        extra.append("日內振幅相對收斂，價格結構仍偏向穩定整理")

    if not extra:
        return base_reason + "。"
    return base_reason + "；" + "；".join(extra) + "。"


def build_trade_plan(
    price: float,
    high_price: float,
    low_price: float,
    signal: str,
) -> Dict[str, str]:
    if price <= 0:
        return {"entry_price": "", "target_price": "", "stop_loss": ""}

    intraday_range = max(high_price - low_price, 0.0)
    base_buffer = max(price * 0.015, intraday_range * 0.35, 0.3)
    wider_buffer = max(price * 0.025, intraday_range * 0.55, 0.5)

    bullish_signals = {
        "強勢主升", "放量突破", "多方控盤", "趨勢續強", "穩健走高",
        "高檔換手", "小幅偏多", "多頭趨勢", "主升段延續", "整理後待突破", "轉強反彈",
    }
    bearish_signals = {"放量修正", "弱勢破位", "小幅偏空", "拉回整理", "空頭趨勢"}
    neutral_signals = {"區間盤整", "籌碼換手", "爆量震盪", "中性觀望", "弱中透穩", "區間整理"}

    if signal in bullish_signals:
        if signal in {"強勢主升", "主升段延續"}:
            entry_low = price - wider_buffer
            entry_high = price - base_buffer * 0.2
            target_low = price * 1.05
            target_high = price * 1.09
            stop = price - wider_buffer * 1.05
        elif signal in {"放量突破", "整理後待突破"}:
            entry_low = price - base_buffer * 1.1
            entry_high = price
            target_low = price * 1.04
            target_high = price * 1.07
            stop = price - wider_buffer * 0.95
        else:
            entry_low = max(low_price if low_price > 0 else price * 0.98, price - base_buffer)
            entry_high = price
            target_low = price * 1.03
            target_high = price * 1.06
            stop = max(price - wider_buffer, price * 0.965)
        return {
            "entry_price": format_price_range(entry_low, entry_high),
            "target_price": format_price_range(target_low, target_high),
            "stop_loss": format_price_value(stop),
        }

    if signal in bearish_signals:
        rebound_high = price + base_buffer
        rebound_low = max(price, price + base_buffer * 0.2)
        target_low = max(price - wider_buffer * 1.3, 0.01)
        target_high = max(price - base_buffer * 0.4, target_low)
        stop = price + wider_buffer
        return {
            "entry_price": format_price_range(rebound_low, rebound_high),
            "target_price": format_price_range(target_low, target_high),
            "stop_loss": format_price_value(stop),
        }

    if signal in neutral_signals:
        upper_ref = high_price if high_price > 0 else price * 1.02
        lower_ref = low_price if low_price > 0 else price * 0.98
        breakout_low = upper_ref
        breakout_high = upper_ref + base_buffer * 0.6
        stop = max(lower_ref - base_buffer * 0.35, 0.01)
        return {
            "entry_price": f"突破 {format_price_range(breakout_low, breakout_high)} 後再評估",
            "target_price": format_price_range(upper_ref + base_buffer, upper_ref + wider_buffer * 1.2),
            "stop_loss": format_price_value(stop),
        }

    return {
        "entry_price": format_price_range(price * 0.98, price),
        "target_price": format_price_range(price * 1.03, price * 1.05),
        "stop_loss": format_price_value(price * 0.96),
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

    strong_set = {"強勢主升", "放量突破", "多方控盤", "趨勢續強", "穩健走高", "多頭趨勢", "主升段延續"}
    moderate_set = {"高檔換手", "小幅偏多", "轉強反彈", "整理後待突破"}
    neutral_set = {"區間盤整", "籌碼換手", "爆量震盪", "中性觀望", "弱中透穩", "區間整理"}
    weak_set = {"拉回整理", "放量修正", "弱勢破位", "小幅偏空", "空頭趨勢"}

    if signal in strong_set:
        operation_rating = "A"
        operation_bias = "積極偏多"
        operation_style = "短線偏多 / 拉回布局"
        strategy_action = "以拉回分批承接為主，避免在急拉時追價；若量能延續，可續抱觀察。"
    elif signal in moderate_set:
        operation_rating = "B+"
        operation_bias = "偏多觀察"
        operation_style = "短線偏多 / 不追高"
        strategy_action = "可採拉回承接策略，但須確認高檔區未失守；不建議盤中情緒性追價。"
    elif signal in neutral_set:
        operation_rating = "C"
        operation_bias = "中性觀望"
        operation_style = "等待表態 / 區間操作"
        strategy_action = "先觀察突破或跌破關鍵區間後再動作，目前較適合等待而非提前下注。"
    elif signal in weak_set:
        operation_rating = "D"
        operation_bias = "保守偏空"
        operation_style = "反彈減碼 / 避免摸底"
        strategy_action = "應以風險控管為先，若無明確止穩訊號，不建議過早進場承接。"
    else:
        operation_rating = "C"
        operation_bias = "中性"
        operation_style = "觀察為主"
        strategy_action = "目前訊號辨識度不足，先等結構更清楚再介入。"

    technical_points = []
    if pos >= 0.85:
        technical_points.append("價格維持於日內高檔區，顯示多方仍掌握主導權")
    elif pos <= 0.2:
        technical_points.append("價格貼近日內低檔區，顯示空方壓力尚未有效解除")
    else:
        technical_points.append("價格落在日內中段，市場仍處於方向確認階段")

    if open_price > 0:
        if price > open_price:
            technical_points.append("現價站穩開盤價之上，日內買盤承接仍具延續性")
        elif price < open_price:
            technical_points.append("現價落於開盤價之下，短線追價買盤續航不足")

    if volume >= 30000:
        technical_points.append("成交量屬顯著放大，市場資金參與度高")
    elif volume >= 10000:
        technical_points.append("成交量維持活絡，有利價格延續原有方向")
    else:
        technical_points.append("成交量仍未完全放大，後續續航力需再觀察")

    if amplitude_pct >= 6:
        technical_points.append("日內振幅偏大，代表波動與風險同步放大")
    elif amplitude_pct <= 2:
        technical_points.append("日內振幅收斂，顯示價格結構較穩定")
    else:
        technical_points.append("日內振幅中等，屬正常波動範圍")

    technical_comment = "；".join(technical_points) + "。"

    trend_map = {
        "強勢主升": ("強勢趨勢延續", "短線已進入加速段，若後續量能失衡或跌破強勢支撐區，追價部位需快速收斂風險。"),
        "主升段延續": ("強勢趨勢延續", "短線已進入加速段，若後續量能失衡或跌破強勢支撐區，追價部位需快速收斂風險。"),
        "放量突破": ("突破後續攻", "重點觀察突破區能否轉為有效支撐，若隔日迅速跌回原整理區，需提防假突破。"),
        "整理後待突破": ("突破後續攻", "重點觀察突破區能否轉為有效支撐，若隔日迅速跌回原整理區，需提防假突破。"),
        "多方控盤": ("多方主導盤勢", "若後續失守開盤價與日內主要支撐，多方節奏可能轉弱，不宜過度樂觀。"),
        "多頭趨勢": ("多方主導盤勢", "若後續失守開盤價與日內主要支撐，多方節奏可能轉弱，不宜過度樂觀。"),
        "趨勢續強": ("偏多續航", "雖仍偏多，但若量價開始背離，需留意由續強轉入震盪整理。"),
        "穩健走高": ("偏多續航", "雖仍偏多，但若量價開始背離，需留意由續強轉入震盪整理。"),
        "轉強反彈": ("偏多續航", "雖仍偏多，但若量價開始背離，需留意由續強轉入震盪整理。"),
        "高檔換手": ("高位整理換手", "高檔區若無法完成整理並再度放量上攻，需提防轉入短線修正。"),
        "拉回整理": ("整理修正", "若關鍵支撐無法止穩，整理可能延長，操作上不宜過早視為轉強。"),
        "弱中透穩": ("整理修正", "若關鍵支撐無法止穩，整理可能延長，操作上不宜過早視為轉強。"),
    }

    if signal in trend_map:
        trend_type, risk_note = trend_map[signal]
    elif signal in {"區間盤整", "籌碼換手", "爆量震盪", "區間整理"}:
        trend_type = "等待方向確認"
        risk_note = "現階段方向尚未完全明朗，應避免在區間中段頻繁追單，耐心等待表態。"
    elif signal in {"放量修正", "弱勢破位", "小幅偏空", "空頭趨勢"}:
        trend_type = "弱勢結構"
        risk_note = "在未見量縮止穩、下影承接或重新站回關鍵價位前，應以保守控風險為優先。"
    else:
        trend_type = "中性盤整"
        risk_note = "訊號辨識度仍不足，觀察後續量價變化比預先押方向更重要。"

    return {
        "trend_type": trend_type,
        "technical_comment": technical_comment,
        "operation_rating": operation_rating,
        "operation_bias": operation_bias,
        "operation_style": operation_style,
        "strategy_action": strategy_action,
        "risk_note": risk_note,
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
    close_now: float, ma5: float, ma10: float, ma20: float,
    high20: float, low20: float, vol_ratio5: float,
    rsi14: float, macd_hist: float,
) -> Dict[str, str]:
    near_high20 = high20 > 0 and close_now >= high20 * 0.985
    near_low20 = low20 > 0 and close_now <= low20 * 1.02

    if close_now > ma5 > ma10 > ma20:
        if near_high20 and vol_ratio5 >= 1.15 and macd_hist > 0:
            return {"signal": "主升段延續", "trend_type": "多頭趨勢強化", "pattern": "沿均線上攻並逼近波段高點"}
        return {"signal": "多頭趨勢", "trend_type": "多頭排列", "pattern": "均線多頭排列，屬趨勢延續型"}

    if close_now > ma20 and ma5 >= ma10 and vol_ratio5 >= 1.05 and macd_hist > 0:
        return {"signal": "轉強反彈", "trend_type": "由整理轉強", "pattern": "重新站回中期均線，上攻結構改善"}

    if abs(close_now - ma20) / max(ma20, 1) <= 0.03 and 0.85 <= vol_ratio5 <= 1.2:
        return {"signal": "區間整理", "trend_type": "橫向整理", "pattern": "價格貼近中期均線，暫無明確方向"}

    if near_high20 and vol_ratio5 >= 1.2:
        return {"signal": "整理後待突破", "trend_type": "挑戰壓力區", "pattern": "價格接近波段高點，等待放量確認突破"}

    if close_now < ma5 < ma10 < ma20:
        return {"signal": "空頭趨勢", "trend_type": "空頭排列", "pattern": "均線反壓明確，屬弱勢下行格局"}

    if near_low20 and rsi14 < 35:
        return {"signal": "拉回整理", "trend_type": "低檔修正", "pattern": "接近波段低點，需觀察是否出現止跌承接"}

    return {"signal": "中性觀望", "trend_type": "結構待確認", "pattern": "方向仍在整理，尚未出現明確突破訊號"}


def build_historical_reason(
    name: str, close_now: float, ma5: float, ma10: float, ma20: float,
    high20: float, low20: float, vol_now: int, avg_vol5: float,
    rsi14: float, macd_line: float, signal_line: float, macd_hist: float, pattern_text: str,
) -> str:
    parts: List[str] = []

    if close_now > ma20:
        parts.append("目前價格仍站在20日均線之上，中期結構偏強")
    elif close_now < ma20:
        parts.append("目前價格仍位於20日均線之下，中期結構偏弱")
    else:
        parts.append("目前價格貼近20日均線，中期方向尚未完全拉開")

    if close_now > ma5 > ma10:
        parts.append("短期均線呈現上彎，短線動能維持正向")
    elif close_now < ma5 < ma10:
        parts.append("短期均線下彎，短線仍處修正節奏")
    else:
        parts.append("短期均線糾結，代表短線仍在整理消化")

    if avg_vol5 > 0:
        vol_ratio5 = vol_now / avg_vol5
        if vol_ratio5 >= 1.3:
            parts.append("近一日量能高於5日均量，市場參與度明顯提升")
        elif vol_ratio5 <= 0.8:
            parts.append("近一日量能低於5日均量，追價力道仍偏保守")
        else:
            parts.append("量能與5日均量接近，屬正常換手")

    if high20 > 0 and low20 > 0:
        if close_now >= high20 * 0.985:
            parts.append("價格已逼近近20日高點，市場正測試前波壓力區")
        elif close_now <= low20 * 1.02:
            parts.append("價格接近近20日低點，短線支撐強度將是關鍵")
        else:
            ratio = (close_now - low20) / max(high20 - low20, 1e-9)
            if ratio >= 0.65:
                parts.append("價格位於近20日區間的上緣，偏向強勢整理")
            elif ratio <= 0.35:
                parts.append("價格位於近20日區間的下緣，偏向弱勢整理")
            else:
                parts.append("價格位於近20日區間中段，尚待方向表態")

    if rsi14 >= 70:
        parts.append("RSI 已進入偏熱區，短線續強同時也伴隨追價風險")
    elif rsi14 >= 55:
        parts.append("RSI 位於多方優勢區，多頭動能仍具延續性")
    elif rsi14 <= 30:
        parts.append("RSI 已進入偏弱區，需觀察是否出現超跌後的技術性反彈")
    elif rsi14 <= 45:
        parts.append("RSI 位於弱勢區間，反映買盤動能仍不足")
    else:
        parts.append("RSI 位於中性區間，市場尚未出現極端情緒")

    if macd_hist > 0 and macd_line > signal_line:
        parts.append("MACD 柱狀體維持正值，代表趨勢動能仍偏多")
    elif macd_hist < 0 and macd_line < signal_line:
        parts.append("MACD 柱狀體仍為負值，顯示中短線動能偏弱")
    else:
        parts.append("MACD 正在收斂，代表趨勢可能進入轉折觀察期")

    parts.append(f"整體型態屬於「{pattern_text}」")
    return f"{name} 目前的日K結構顯示，" + "；".join(parts) + "。"


def build_historical_technical_comment(
    ma5: float, ma10: float, ma20: float, avg_vol5: float, avg_vol20: float,
    rsi14: float, macd_line: float, signal_line: float, macd_hist: float,
    high20: float, low20: float, atr14: float,
) -> str:
    return "；".join([
        f"MA5 {format_price_value(ma5)} / MA10 {format_price_value(ma10)} / MA20 {format_price_value(ma20)}",
        f"5日均量 {format_number(avg_vol5)} / 20日均量 {format_number(avg_vol20)}",
        f"RSI14 {rsi14:.2f}",
        f"MACD {macd_line:.3f} / Signal {signal_line:.3f} / Hist {macd_hist:.3f}",
        f"近20日高低區間 {format_price_value(low20)} ~ {format_price_value(high20)}",
        f"ATR14 {format_price_value(atr14)}",
    ]) + "。"


def build_historical_trade_plan(
    price: float, ma5: float, ma20: float,
    high20: float, low20: float, atr14: float, signal: str,
) -> Dict[str, str]:
    buffer_small = max(atr14 * 0.6, price * 0.012, 0.3)
    buffer_large = max(atr14 * 1.0, price * 0.022, 0.6)

    if signal in {"主升段延續", "多頭趨勢", "轉強反彈"}:
        entry_low = max(ma5 - buffer_small, low20, 0.01)
        entry_high = max(ma5 + buffer_small * 0.5, entry_low)
        target_low = max(high20 * 1.01, price * 1.04)
        target_high = max(target_low, price + buffer_large * 2.0)
        stop = max(ma20 - buffer_small, 0.01)
        return {
            "entry_price": format_price_range(entry_low, entry_high),
            "target_price": format_price_range(target_low, target_high),
            "stop_loss": format_price_value(stop),
        }

    if signal == "整理後待突破":
        breakout_low = max(high20, price)
        breakout_high = breakout_low + buffer_small
        stop = max(ma20 - buffer_small, low20 - buffer_small * 0.3, 0.01)
        return {
            "entry_price": f"突破 {format_price_range(breakout_low, breakout_high)} 後再評估",
            "target_price": format_price_range(breakout_high + buffer_small, breakout_high + buffer_large * 1.8),
            "stop_loss": format_price_value(stop),
        }

    if signal in {"空頭趨勢", "拉回整理"}:
        rebound_low = price + buffer_small * 0.3
        rebound_high = price + buffer_large
        target_low = max(low20 - buffer_small, 0.01)
        target_high = max(price - buffer_small, target_low)
        stop = max(ma5 + buffer_small, rebound_high)
        return {
            "entry_price": format_price_range(rebound_low, rebound_high),
            "target_price": format_price_range(target_low, target_high),
            "stop_loss": format_price_value(stop),
        }

    breakout_low = max(high20, price)
    breakout_high = breakout_low + buffer_small
    stop = max(low20 - buffer_small * 0.25, 0.01)
    return {
        "entry_price": f"突破 {format_price_range(breakout_low, breakout_high)} 後再評估",
        "target_price": format_price_range(breakout_high + buffer_small, breakout_high + buffer_large),
        "stop_loss": format_price_value(stop),
    }


def build_historical_strategy(signal: str) -> Dict[str, str]:
    if signal in {"主升段延續", "多頭趨勢"}:
        return {
            "operation_rating": "A",
            "operation_bias": "積極偏多",
            "operation_style": "順勢拉回布局",
            "strategy_action": "以靠近5日線或短線支撐區分批承接為主，若量能維持在5日均量之上，可續抱觀察波段延伸。",
            "risk_note": "若價格跌破5日線後無法迅速收復，或量能明顯萎縮，代表主升段節奏可能轉弱。",
        }
    if signal in {"轉強反彈", "整理後待突破"}:
        return {
            "operation_rating": "B+",
            "operation_bias": "偏多觀察",
            "operation_style": "等突破或拉回確認",
            "strategy_action": "優先等待突破近20日高點或回測5日/10日線不破再介入，避免在壓力區正下方追價。",
            "risk_note": "若突破後量能未跟上，或重新跌回20日均線下方，需提防假突破與整理延長。",
        }
    if signal == "區間整理":
        return {
            "operation_rating": "C",
            "operation_bias": "中性觀望",
            "operation_style": "等待方向表態",
            "strategy_action": "目前較適合觀察區間上緣與下緣的表態結果，未突破前不建議在區間中段積極追單。",
            "risk_note": "整理盤最怕假突破與假跌破，若沒有量能確認，操作勝率通常不高。",
        }
    return {
        "operation_rating": "D",
        "operation_bias": "保守偏空",
        "operation_style": "反彈減碼 / 嚴控風險",
        "strategy_action": "現階段以等待止跌訊號為主，若仍在20日線下方且RSI偏弱，不建議急於摸底。",
        "risk_note": "弱勢標的若未出現量縮止跌或重新站回短中期均線，容易持續沿空方趨勢下修。",
    }


def build_historical_analysis_for_stock(base_stock: Dict[str, Any]) -> Dict[str, Any]:
    symbol = safe_str(base_stock.get("symbol"))
    if not symbol:
        return base_stock

    try:
        history_data = fetch_symbol_daily_candles(symbol)
        candles = history_data.get("candles", [])
        if len(candles) < 25:
            return base_stock

        closes = [safe_float(x.get("close")) for x in candles if safe_float(x.get("close")) > 0]
        highs = [safe_float(x.get("high")) for x in candles if safe_float(x.get("high")) > 0]
        lows = [safe_float(x.get("low")) for x in candles if safe_float(x.get("low")) > 0]
        volumes = [safe_float(x.get("volume")) for x in candles]

        if len(closes) < 25:
            return base_stock

        close_now = safe_float(base_stock.get("price")) or closes[-1]
        ma5 = avg(closes[-5:])
        ma10 = avg(closes[-10:])
        ma20 = avg(closes[-20:])
        high20 = max(highs[-20:]) if len(highs) >= 20 else max(highs)
        low20 = min(lows[-20:]) if len(lows) >= 20 else min(lows)

        vol_now = safe_int(base_stock.get("volume")) or safe_int(volumes[-1])
        avg_vol5 = avg(volumes[-5:])
        avg_vol20 = avg(volumes[-20:])
        vol_ratio5 = (vol_now / avg_vol5) if avg_vol5 > 0 else 1.0

        rsi14 = calc_rsi(closes, 14)
        macd_line, signal_line, macd_hist = calc_macd(closes)
        atr14 = calc_atr(candles, 14)

        pattern_info = classify_daily_pattern(
            close_now=close_now, ma5=ma5, ma10=ma10, ma20=ma20,
            high20=high20, low20=low20, vol_ratio5=vol_ratio5,
            rsi14=rsi14, macd_hist=macd_hist,
        )

        reason = build_historical_reason(
            name=safe_str(base_stock.get("name")),
            close_now=close_now, ma5=ma5, ma10=ma10, ma20=ma20,
            high20=high20, low20=low20, vol_now=vol_now, avg_vol5=avg_vol5,
            rsi14=rsi14, macd_line=macd_line, signal_line=signal_line,
            macd_hist=macd_hist, pattern_text=pattern_info["pattern"],
        )
        technical_comment = build_historical_technical_comment(
            ma5=ma5, ma10=ma10, ma20=ma20, avg_vol5=avg_vol5, avg_vol20=avg_vol20,
            rsi14=rsi14, macd_line=macd_line, signal_line=signal_line,
            macd_hist=macd_hist, high20=high20, low20=low20, atr14=atr14,
        )
        plan = build_historical_trade_plan(
            price=close_now, ma5=ma5, ma20=ma20, high20=high20,
            low20=low20, atr14=atr14, signal=pattern_info["signal"],
        )
        strategy = build_historical_strategy(pattern_info["signal"])
        risk_reward = calc_risk_reward(plan["entry_price"], plan["target_price"], plan["stop_loss"])

        bonus_map = {"主升段延續": 24, "多頭趨勢": 18, "轉強反彈": 12, "整理後待突破": 12, "區間整理": 5}
        bonus = bonus_map.get(pattern_info["signal"], 0.0)
        recommendation_score = round(
            safe_float(base_stock.get("recommendation_score"), 0.0) + bonus + max((rsi14 - 50) * 0.18, -6), 2
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
            "analysis_source": "historical_k",
        })
        return merged

    except Exception:
        return base_stock


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
    is_etf = is_etf_symbol(symbol, name)

    if not is_valid_stock_symbol(symbol, is_etf=is_etf):
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

    if market_label == "興櫃" and not is_etf:
        if volume < 100 or price < 1:
            return None

    open_price = safe_float(row.get("openPrice"))
    high_price = safe_float(row.get("highPrice"))
    low_price = safe_float(row.get("lowPrice"))

    update_time_raw = row.get("lastUpdated") or row.get("time") or 0
    update_time_str = micros_to_taipei_str(update_time_raw)
    category = price_category(price)

    liquidity_bonus = min(volume / 5000, 20)
    volatility_ratio = (max(high_price - low_price, 0) / max(price, 1)) * 10 if price > 0 else 0
    stability_penalty = min(volatility_ratio, 10)
    score = round(abs(change_percent) * 10 + min(volume / 100000, 50), 2)
    base_recommendation_score = max(
        0.0, abs(change_percent) * 6 + liquidity_bonus + 2 - stability_penalty * 0.3
    )

    signal_info = build_signal_and_reason(
        price=price, change=change, change_percent=change_percent,
        volume=volume, high_price=high_price, low_price=low_price,
        open_price=open_price, previous_close=previous_close,
    )
    final_reason = enrich_reason_with_context(
        base_reason=signal_info["reason"], price=price, open_price=open_price,
        high_price=high_price, low_price=low_price, change_percent=change_percent,
        volume=volume, previous_close=previous_close,
    )
    plan = build_trade_plan(price=price, high_price=high_price, low_price=low_price, signal=signal_info["signal"])
    strategy_info = build_strategy_and_risk(
        signal=signal_info["signal"], price=price, open_price=open_price,
        high_price=high_price, low_price=low_price, volume=volume, previous_close=previous_close,
    )
    risk_reward = calc_risk_reward(plan["entry_price"], plan["target_price"], plan["stop_loss"])

    rating_bonus_map = {"A": 18, "B+": 12, "C": 5, "D": 0}
    recommendation_score = round(
        base_recommendation_score + rating_bonus_map.get(strategy_info["operation_rating"], 0), 2
    )

    return {
        "market": "ETF" if is_etf else market_label,
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
        "is_etf": is_etf,
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
# Market Data
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
    # 移除多餘的 COMMONSTOCK 查詢，ALLBUT0999 已涵蓋所有股票
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

    for market_code, market_label in [("TSE", "上市"), ("OTC", "上櫃"), ("ESB", "興櫃")]:
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
    has_price_filter = price_min > 0 or price_max > 0
    has_category_filter = category != "all"

    if market_lower in ("all", ""):
        result = [s for s in result if is_main_board_stock(s)]
    else:
        market_map = {
            "tse": "上市", "otc": "上櫃", "esb": "興櫃",
            "etf": "ETF", "ETF": "ETF", "上市": "上市", "上櫃": "上櫃", "興櫃": "興櫃",
        }
        target_market = market_map.get(market_lower, market)
        result = [s for s in result if s.get("market") == target_market]

    if (has_price_filter or has_category_filter) and market_lower not in ("esb", "etf"):
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
        "score": "score", "recommendation_score": "recommendation_score",
        "price": "price", "change": "change", "change_percent": "change_percent",
        "volume": "volume", "trade_value": "trade_value",
        "symbol": "symbol", "name": "name", "operation_rating": "operation_rating",
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
        and safe_float(s.get("price")) > 0
        and safe_int(s.get("volume")) > 0
    ]
    candidates.sort(
        key=lambda x: (x.get("recommendation_score", 0), x.get("volume", 0), abs(x.get("change_percent", 0))),
        reverse=True,
    )
    top_items = candidates[:top_n]

    # 平行抓歷史 K 線，max_workers=5 避免 API 限流
    result_map: Dict[str, Dict[str, Any]] = {}
    with ThreadPoolExecutor(max_workers=5) as executor:
        future_to_symbol = {
            executor.submit(build_historical_analysis_for_stock, stock): stock["symbol"]
            for stock in top_items
        }
        for future in as_completed(future_to_symbol):
            symbol = future_to_symbol[future]
            try:
                result_map[symbol] = future.result()
            except Exception:
                original = next((s for s in top_items if s["symbol"] == symbol), None)
                if original:
                    result_map[symbol] = original

    return [result_map[s["symbol"]] for s in top_items if s["symbol"] in result_map]


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
    if len(filtered) == 1:
        return filtered[0]
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
        "is_etf": s.get("is_etf", False),
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
            all_stocks, market=market, category=category,
            q=q, price_min=price_min, price_max=price_max,
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

        main_board = [s for s in all_stocks if is_main_board_stock(s)]

        return {
            "success": True,
            "market_status": get_market_status_text(),
            "data_date": result["data_date"],
            "last_update": result["last_update"],
            "message": result.get("message", ""),
            "total": total_filtered,
            "offset": offset,
            "limit": limit,
            # 前端 count 一次到位，不需額外打 3 個請求
            "all_total": len(main_board),
            "esb_total": len([s for s in all_stocks if s.get("market") == "興櫃"]),
            "etf_total": len([s for s in all_stocks if s.get("market") == "ETF"]),
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
