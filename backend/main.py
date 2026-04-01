import os
import traceback
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

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
}
CACHE_SECONDS = 20

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


def is_etf_symbol(symbol: str, name: str) -> bool:
    s = safe_str(symbol)
    n = safe_str(name)
    if s.startswith("00"):
        return True
    if "ETF" in n.upper():
        return True
    return False


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
                "該股今日屬於明確的強勢主升型態，漲幅擴大同時伴隨大量成交，且價格維持在日內高檔區，"
                "代表盤中追價買盤積極，多方對價格的掌控力相當強。"
                "從量價結構來看，這較接近資金集中後的趨勢推升，而非單純技術性反彈。"
            ),
        }

    if change_percent >= 4 and heavy_volume and close_near_high:
        return {
            "signal": "放量突破",
            "reason": (
                "股價今日出現帶量上攻，且價格穩守高檔區，顯示突破並非虛漲，而是有實質買盤推動。"
                "這類型態通常代表前波整理壓力已有被消化的跡象，市場資金開始明確表態偏多。"
            ),
        }

    if change_percent >= 2 and gap_up and close_high:
        return {
            "signal": "多方控盤",
            "reason": (
                "個股今日以偏強方式開出後，盤中價格重心持續墊高，且維持在相對高檔，"
                "反映多方在盤中節奏掌握上明顯占優。"
            ),
        }

    if change_percent >= 1.5 and heavy_volume and close_high and amplitude_pct <= 5:
        return {
            "signal": "趨勢續強",
            "reason": (
                "股價延續原有偏多結構，盤中雖有波動，但整體重心仍維持上移，且量能未明顯失真，"
                "顯示市場對該股仍具備穩定承接力。"
            ),
        }

    if change_percent > 1 and amplitude_pct <= 4 and close_high:
        return {
            "signal": "穩健走高",
            "reason": (
                "個股今日屬於穩步墊高格局，雖非急攻型走勢，但價格仍能守在相對高位，"
                "顯示買盤承接結構穩定，盤勢偏向健康上行。"
            ),
        }

    if change_percent >= 0 and amplitude_pct > 4 and heavy_volume and close_high:
        return {
            "signal": "高檔換手",
            "reason": (
                "股價今日盤中震盪明顯，但成交量活絡且仍守住高檔區，"
                "顯示市場在相對高位進行換手，多方承接力尚未明顯失守。"
            ),
        }

    if -1 <= change_percent <= 1 and amplitude_pct <= 3:
        return {
            "signal": "區間盤整",
            "reason": (
                "股價目前處於明顯整理格局，日內波動有限，量價表現相對均衡，"
                "顯示市場短線觀望氣氛偏濃，尚未形成明確攻擊或破位訊號。"
            ),
        }

    if -1 <= change_percent <= 1 and amplitude_pct > 4 and heavy_volume:
        return {
            "signal": "籌碼換手",
            "reason": (
                "個股今日盤中振幅偏大，但最終漲跌幅收斂，且成交量顯著放大，"
                "反映多空雙方對價格認知分歧，市場正處於明顯籌碼換手階段。"
            ),
        }

    if change_percent <= -2 and change_percent > -5 and close_low and not very_heavy_volume:
        return {
            "signal": "拉回整理",
            "reason": (
                "股價今日出現明顯回檔，且價格落在日內偏低區，顯示短線上方賣壓開始增加，"
                "買盤承接態度轉趨保守，但量能尚未失控，較偏向技術性整理。"
            ),
        }

    if change_percent <= -3 and heavy_volume:
        return {
            "signal": "放量修正",
            "reason": (
                "個股今日呈現放量下跌格局，顯示市場調節賣壓明顯升溫，"
                "價格重心同步下移，短線籌碼穩定度轉弱。"
            ),
        }

    if change_percent <= -6 and very_heavy_volume and close_near_low:
        return {
            "signal": "弱勢破位",
            "reason": (
                "股價今日出現明顯破位下跌，跌幅擴大且伴隨大量成交，"
                "代表市場恐慌性調節或停損賣壓同步湧現，原有支撐結構已遭到實質破壞。"
            ),
        }

    if extreme_volume and amplitude_pct >= 5:
        return {
            "signal": "爆量震盪",
            "reason": (
                "個股今日成交量顯著放大，且盤中振幅明顯擴大，"
                "顯示市場高度聚焦，但多空對價格方向尚未取得一致共識。"
            ),
        }

    if change_percent < 0 and not heavy_volume and not close_near_low and amplitude_pct <= 4:
        return {
            "signal": "弱中透穩",
            "reason": (
                "股價今日雖小幅收低，但跌幅仍屬可控範圍，且未見明顯恐慌性賣壓，"
                "代表市場偏向觀望，而非全面轉空。"
            ),
        }

    if change_percent > 0:
        return {
            "signal": "小幅偏多",
            "reason": (
                "股價今日小幅收高，整體價格結構仍偏正向，"
                "顯示短線買盤尚具一定支撐力。"
            ),
        }

    if change_percent < 0:
        return {
            "signal": "小幅偏空",
            "reason": (
                "股價今日小幅收低，反映短線追價意願略顯不足，盤面資金態度偏向保守。"
            ),
        }

    return {
        "signal": "中性觀望",
        "reason": (
            "個股目前缺乏明確方向訊號，量價結構尚未形成具辨識度的趨勢優勢，"
            "短線仍應以觀察後續資金流向、成交量變化與關鍵價位表現為主。"
        ),
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
            extra.append("股價站穩開盤價之上，日內多方仍略占優勢")
        elif price < open_price:
            extra.append("股價跌破開盤價，顯示追價買盤續航力不足")
        else:
            extra.append("股價貼近開盤價，市場短線多空仍在拉鋸")

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

    return base_reason + "；" + "；".join(extra) + "。"


def build_trade_plan(
    price: float,
    change_percent: float,
    high_price: float,
    low_price: float,
    signal: str,
) -> Dict[str, str]:
    if price <= 0:
        return {
            "entry_price": "",
            "target_price": "",
            "stop_loss": "",
        }

    intraday_range = max(high_price - low_price, 0.0)
    base_buffer = max(price * 0.015, intraday_range * 0.35, 0.3)
    wider_buffer = max(price * 0.025, intraday_range * 0.55, 0.5)

    bullish_signals = {
        "強勢主升",
        "放量突破",
        "多方控盤",
        "趨勢續強",
        "穩健走高",
        "高檔換手",
        "小幅偏多",
    }
    bearish_signals = {
        "放量修正",
        "弱勢破位",
        "小幅偏空",
        "拉回整理",
    }
    neutral_signals = {
        "區間盤整",
        "籌碼換手",
        "爆量震盪",
        "中性觀望",
        "弱中透穩",
    }

    if signal in bullish_signals:
        if signal == "強勢主升":
            entry_low = price - wider_buffer
            entry_high = price - base_buffer * 0.25
            target_low = price * 1.05
            target_high = price * 1.08
            stop = price - wider_buffer * 1.05
        elif signal == "放量突破":
            entry_low = price - base_buffer * 1.2
            entry_high = price
            target_low = price * 1.04
            target_high = price * 1.07
            stop = price - wider_buffer * 0.95
        elif signal == "高檔換手":
            entry_low = max(low_price, price - base_buffer * 1.15)
            entry_high = price - base_buffer * 0.1
            target_low = price * 1.03
            target_high = price * 1.06
            stop = max(low_price - base_buffer * 0.35, price * 0.96)
        else:
            entry_low = max(low_price, price - base_buffer)
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

    entry_low = max(low_price, price - base_buffer)
    entry_high = price
    target_low = price * 1.03
    target_high = price * 1.05
    stop = max(price - wider_buffer, 0.01)

    return {
        "entry_price": format_price_range(entry_low, entry_high),
        "target_price": format_price_range(target_low, target_high),
        "stop_loss": format_price_value(stop),
    }


def build_strategy_and_risk(
    signal: str,
    price: float,
    open_price: float,
    high_price: float,
    low_price: float,
    change_percent: float,
    volume: int,
    previous_close: float,
) -> Dict[str, str]:
    pos = calc_position_ratio(price, high_price, low_price)
    amplitude_pct = calc_amplitude_pct(high_price, low_price, previous_close)

    strong_set = {"強勢主升", "放量突破", "多方控盤", "趨勢續強", "穩健走高"}
    moderate_set = {"高檔換手", "小幅偏多"}
    neutral_set = {"區間盤整", "籌碼換手", "爆量震盪", "中性觀望", "弱中透穩"}
    weak_set = {"拉回整理", "放量修正", "弱勢破位", "小幅偏空"}

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
        else:
            technical_points.append("現價貼近開盤價，短線多空尚未拉開明顯差距")

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

    if signal == "強勢主升":
        trend_type = "強勢趨勢延續"
        risk_note = "短線已進入加速段，若後續量能失衡或跌破強勢支撐區，追價部位需快速收斂風險。"
    elif signal == "放量突破":
        trend_type = "突破後續攻"
        risk_note = "重點觀察突破區能否轉為有效支撐，若隔日迅速跌回原整理區，需提防假突破。"
    elif signal == "多方控盤":
        trend_type = "多方主導盤勢"
        risk_note = "若後續失守開盤價與日內主要支撐，多方節奏可能轉弱，不宜過度樂觀。"
    elif signal in {"趨勢續強", "穩健走高"}:
        trend_type = "偏多續航"
        risk_note = "雖仍偏多，但若量價開始背離，需留意由續強轉入震盪整理。"
    elif signal == "高檔換手":
        trend_type = "高位整理換手"
        risk_note = "高檔區若無法完成整理並再度放量上攻，需提防轉入短線修正。"
    elif signal in {"區間盤整", "籌碼換手", "爆量震盪"}:
        trend_type = "等待方向確認"
        risk_note = "現階段方向尚未完全明朗，應避免在區間中段頻繁追單，耐心等待表態。"
    elif signal in {"拉回整理", "弱中透穩"}:
        trend_type = "整理修正"
        risk_note = "若關鍵支撐無法止穩，整理可能延長，操作上不宜過早視為轉強。"
    elif signal in {"放量修正", "弱勢破位", "小幅偏空"}:
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

    ratio = reward / risk
    return f"1:{ratio:.2f}"


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
        row.get("symbol")
        or row.get("stockNo")
        or row.get("stock_no")
        or row.get("code")
        or row.get("ticker")
    )
    if not symbol:
        return None

    name = safe_str(row.get("name") or row.get("stockName") or row.get("stock_name") or symbol)

    price = safe_float(
        row.get("lastPrice")
        or row.get("closePrice")
        or row.get("tradePrice")
        or row.get("price")
        or row.get("currentPrice")
    )
    if price <= 0:
        return None

    etf = is_etf_symbol(symbol, name)
    if etf:
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
        row.get("tradeVolume")
        or row.get("volume")
        or row.get("totalVolume")
        or row.get("accumulatedVolume")
        or row.get("tradeVolumeAtBid")
    )
    trade_value = safe_int(row.get("tradeValue"))

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
        0.0,
        abs(change_percent) * 6 + liquidity_bonus + 2 - stability_penalty * 0.3,
    )

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

    plan = build_trade_plan(
        price=price,
        change_percent=change_percent,
        high_price=high_price,
        low_price=low_price,
        signal=signal_info["signal"],
    )

    strategy_info = build_strategy_and_risk(
        signal=signal_info["signal"],
        price=price,
        open_price=open_price,
        high_price=high_price,
        low_price=low_price,
        change_percent=change_percent,
        volume=volume,
        previous_close=previous_close,
    )

    risk_reward = calc_risk_reward(
        entry_price=plan["entry_price"],
        target_price=plan["target_price"],
        stop_loss=plan["stop_loss"],
    )

    rating_bonus_map = {
        "A": 18,
        "B+": 12,
        "C": 5,
        "D": 0,
    }
    recommendation_score = round(
        base_recommendation_score + rating_bonus_map.get(strategy_info["operation_rating"], 0),
        2,
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
        "is_etf": False,
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
    }


# =========================
# Market Data
# =========================
def fetch_snapshot_market(market: str, market_label: str) -> List[Dict[str, Any]]:
    stock_client = get_stock_rest_client()
    resp = stock_client.snapshot.quotes(market=market, type="ALLBUT0999")
    rows = extract_rows(resp)

    result: List[Dict[str, Any]] = []
    for row in rows:
        item = normalize_snapshot_row(row, market_label=market_label)
        if item:
            result.append(item)

    dedup = {}
    for item in result:
        dedup[item["symbol"]] = item

    return list(dedup.values())


def get_all_stocks_raw() -> Dict[str, Any]:
    all_stocks: List[Dict[str, Any]] = []
    errors: List[str] = []

    try:
        all_stocks.extend(fetch_snapshot_market("TSE", "上市"))
    except Exception as e:
        errors.append(f"TSE 失敗: {e}")

    try:
        all_stocks.extend(fetch_snapshot_market("OTC", "上櫃"))
    except Exception as e:
        errors.append(f"OTC 失敗: {e}")

    dedup = {}
    for item in all_stocks:
        dedup[item["symbol"]] = item

    stocks = list(dedup.values())

    if not stocks and errors:
        raise Exception("；".join(errors))

    latest_raw = 0
    for s in stocks:
        latest_raw = max(latest_raw, safe_int(s.get("update_time_raw")))

    data_date = micros_to_date_str(latest_raw) if latest_raw else now_taipei().strftime("%Y%m%d")
    last_update = micros_to_taipei_str(latest_raw) if latest_raw else format_dt_taipei(now_taipei())

    return {
        "stocks": stocks,
        "data_date": data_date,
        "last_update": last_update,
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
        }

    result = get_all_stocks_raw()
    _CACHE["stocks"] = result["stocks"]
    _CACHE["fetched_at"] = now
    _CACHE["data_date"] = result["data_date"]
    _CACHE["last_update"] = result["last_update"]

    return result


# =========================
# Business Logic
# =========================
def build_categories(stocks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    order = ["0-10", "10-20", "20-50", "50-100", "100-200", "200-500", "500-1000", "1000+"]
    counts = {k: 0 for k in order}

    for s in stocks:
        if s.get("is_etf", False):
            continue
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
    include_etf: bool = False,
) -> List[Dict[str, Any]]:
    result = stocks

    if not include_etf:
        result = [s for s in result if not s.get("is_etf", False)]

    if market != "all":
        market_map = {
            "tse": "上市",
            "otc": "上櫃",
            "上市": "上市",
            "上櫃": "上櫃",
        }
        target_market = market_map.get(market.lower(), market)
        result = [s for s in result if s.get("market") == target_market]

    if category != "all":
        result = [s for s in result if s.get("category") == category]

    if q.strip():
        qq = q.strip().lower()
        result = [
            s
            for s in result
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
        return sorted(
            stocks,
            key=lambda x: rating_order.get(x.get("operation_rating", ""), 0),
            reverse=reverse,
        )

    return sorted(stocks, key=lambda x: x.get(key, 0), reverse=reverse)


def build_recommendations(stocks: List[Dict[str, Any]], top_n: int = 10) -> List[Dict[str, Any]]:
    candidates = []
    for s in stocks:
        if s.get("is_etf", False):
            continue
        if safe_float(s.get("price")) <= 0:
            continue
        if safe_int(s.get("volume")) <= 0:
            continue
        candidates.append(s)

    candidates.sort(
        key=lambda x: (
            x.get("recommendation_score", 0),
            x.get("volume", 0),
            abs(x.get("change_percent", 0)),
        ),
        reverse=True,
    )
    return candidates[:top_n]


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
    include_etf: bool = Query(False),
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
            include_etf=include_etf,
        )
        filtered = sort_stocks(filtered, sort_by=sort_by, sort_dir=sort_dir)

        total_filtered = len(filtered)
        paged = filtered[offset : offset + limit]

        recs = build_recommendations(all_stocks, top_n=10)
        cats = build_categories(all_stocks)
        focused = find_focused_stock(filtered, q)

        return {
            "success": True,
            "market_status": get_market_status_text(),
            "data_date": result["data_date"],
            "last_update": result["last_update"],
            "total": total_filtered,
            "offset": offset,
            "limit": limit,
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
