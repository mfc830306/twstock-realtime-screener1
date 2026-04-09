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
    "twse_total": 0,
    "otc_total": 0,
    "categories": [],
}
CACHE_SECONDS = 60

_RECS_CACHE: Dict[str, Any] = {
    "recommendations": None,
    "fetched_at": None,
}
RECS_CACHE_SECONDS = 120

_HISTORY_CACHE: Dict[str, Dict[str, Any]] = {}
HISTORY_CACHE_HOURS = 6
HISTORY_CACHE_MAX_SIZE = 500

# ✅ fix 4: 改為絕對路徑，並支援環境變數覆蓋
VALIDATION_LOG_FILE = os.getenv(
    "VALIDATION_LOG_FILE",
    "/opt/render/project/src/recommendations_validation.jsonl",
)
VALIDATION_FORWARD_BARS = [1, 3, 5]

# ✅ fix 6: validation 結果短暫 cache，避免同時打兩支 API 重複計算
_VALIDATION_CACHE: Dict[str, Any] = {
    "rows": None,
    "fetched_at": None,
    "lookback_days": None,
    "holding_days": None,
}
VALIDATION_CACHE_SECONDS = 60

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
    if price < 10:   return "0-10"
    if price < 20:   return "10-20"
    if price < 50:   return "20-50"
    if price < 100:  return "50-100"
    if price < 200:  return "100-200"
    if price < 500:  return "200-500"
    if price < 1000: return "500-1000"
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


def parse_any_date(v: Any) -> Optional[date]:
    txt = safe_str(v)
    if not txt:
        return None
    for fmt in ("%Y-%m-%d", "%Y%m%d", "%Y/%m/%d", "%Y/%m/%d %H:%M:%S", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(txt, fmt).date()
        except Exception:
            pass
    try:
        return datetime.fromisoformat(txt.replace("Z", "")).date()
    except Exception:
        return None


# =========================
# Fubon SDK
# =========================
def ensure_fubon_sdk():
    global _sdk, _login_info, _marketdata_ready
    if _sdk is not None and _marketdata_ready:
        return _sdk
    from fubon_neo.sdk import FubonSDK
    fubon_id  = os.getenv("FUBON_ID", "").strip()
    fubon_pwd = (os.getenv("FUBON_PASSWORD") or os.getenv("FUBON_PWD") or "").strip()
    cert_pwd  = (os.getenv("FUBON_CERT_PASSWORD") or os.getenv("FUBON_CERT_PWD") or "").strip()
    cert_path = resolve_cert_path()
    if not fubon_id or not fubon_pwd or not cert_pwd or not cert_path:
        raise Exception("FUBON 環境變數未設定完整")
    if _sdk is None:
        _sdk = FubonSDK()
    if _login_info is None:
        _login_info = _sdk.login(fubon_id, fubon_pwd, cert_path, cert_pwd)
    is_success = getattr(_login_info, "is_success", False)
    if not is_success:
        raise Exception(f"Fubon SDK login failed: {getattr(_login_info, 'message', 'unknown error')}")
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
# 專業分析理由生成
# =========================
def build_signal_and_reason(
    price: float, change: float, change_percent: float, volume: int,
    high_price: float, low_price: float, open_price: float, previous_close: float,
) -> Dict[str, str]:
    amplitude_pct  = calc_amplitude_pct(high_price, low_price, previous_close)
    close_position = calc_position_ratio(price, high_price, low_price)

    close_near_high  = close_position >= 0.85
    close_high       = close_position >= 0.68
    close_low        = close_position <= 0.35
    close_near_low   = close_position <= 0.18
    gap_up           = open_price > previous_close > 0
    heavy_volume     = volume >= 3000
    very_heavy_volume = volume >= 10000
    extreme_volume   = volume >= 30000
    vol_k            = volume / 1000

    if change_percent >= 6 and very_heavy_volume and close_near_high:
        return {"signal": "強勢主升", "reason": (
            f"今日大漲 {change_percent:.2f}%，成交量達 {vol_k:.0f}K 張，量價同步爆發，收盤位置貼近日內高點（收盤位置比 {close_position:.0%}），"
            "顯示全日買盤主導格局未受干擾。此類型態為強勢主升段的典型特徵：追價意願強烈、"
            "空方無力回補，後續若量能維持放大，波段延伸機率高。惟短線漲幅已大，"
            "需留意一旦出現高量長上影線或跳空缺口回補的賣壓訊號。"
        )}
    if change_percent >= 4 and heavy_volume and close_near_high:
        return {"signal": "放量突破", "reason": (
            f"今日上漲 {change_percent:.2f}%，成交量 {vol_k:.0f}K 張，量能顯著放大且收盤守穩高檔，"
            "技術面呈現帶量突破型態。有效突破的關鍵判斷在於「量增價漲、收盤不回吐」，"
            "本標的今日已符合此條件。後續觀察重點：隔日是否出現量縮回測不破突破點，"
            "若成立則為二次進場的低風險機會；反之若盤中迅速跌回整理區，需提防假突破風險。"
        )}
    if change_percent >= 2 and gap_up and close_high:
        return {"signal": "多方控盤", "reason": (
            f"今日跳空高開後維持強勢，漲幅 {change_percent:.2f}%，收盤站穩日內偏高區（位置比 {close_position:.0%}）。"
            "跳空缺口代表市場對正面訊息的即時定價，多方在開盤即取得主導優勢，"
            "盤中未見明顯賣壓回補，顯示籌碼面具備一定支撐。"
            "跳空缺口若未在盤中被回補，通常可視為短線支撐，"
            "操作上以缺口上緣作為停損參考，評估向上延伸空間。"
        )}
    if change_percent >= 1.5 and heavy_volume and close_high and amplitude_pct <= 5:
        return {"signal": "趨勢續強", "reason": (
            f"今日收漲 {change_percent:.2f}%，日內振幅 {amplitude_pct:.2f}%（屬正常換手幅度），"
            f"成交量 {vol_k:.0f}K 張，量價結構健康。價格重心持續上移，"
            "未出現高位震盪或長上影線等轉弱訊號，代表強勢格局延續中。"
            "此類穩健走強型態的優點在於籌碼結構較乾淨，"
            "急漲後的回測風險相對較低，適合以均線扣抵方式追蹤持有。"
        )}
    if change_percent > 1 and amplitude_pct <= 4 and close_high:
        return {"signal": "穩健走高", "reason": (
            f"今日小幅上漲 {change_percent:.2f}%，日內振幅 {amplitude_pct:.2f}%，波動溫和，"
            f"收盤維持於日內偏高位置（位置比 {close_position:.0%}）。"
            "此型態反映市場在相對高位仍有穩定承接意願，非急攻式上漲，"
            "籌碼換手較為充分，不易因短線追高而出現快速修正。"
            "適合觀察短期均線能否持續支撐，以確認趨勢方向。"
        )}
    if change_percent >= 0 and amplitude_pct > 4 and heavy_volume and close_high:
        return {"signal": "高檔換手", "reason": (
            f"今日漲幅 {change_percent:.2f}%，但日內振幅達 {amplitude_pct:.2f}%，成交量 {vol_k:.0f}K 張顯著放大。"
            "盤中出現明顯震盪整理，但最終仍收守高檔，顯示多空雙方積極交鋒，"
            "市場在高位進行籌碼重新分配。高換手後若下一日出現量縮紅 K，"
            "通常代表換手完成、空手浮額消化，有利下一波上攻；"
            "反之若量縮後再度大量下殺，則需警惕高位分配風險。"
        )}
    if -1 <= change_percent <= 1 and amplitude_pct <= 3:
        return {"signal": "區間盤整", "reason": (
            f"今日漲跌幅 {change_percent:+.2f}%，振幅僅 {amplitude_pct:.2f}%，量價平穩，"
            "明顯處於整理蓄積格局。盤整本身並非負面訊號，"
            "市場的橫向整理通常是在消化前期漲幅或為下一波行情累積動能。"
            "關鍵觀察：整理過程中若成交量逐步萎縮（量縮盤整），"
            "代表浮額洗清充分，一旦放量突破整理區上緣，訊號可信度較高。"
        )}
    if -1 <= change_percent <= 1 and amplitude_pct > 4 and heavy_volume:
        return {"signal": "籌碼換手", "reason": (
            f"今日漲跌幅 {change_percent:+.2f}%，但振幅達 {amplitude_pct:.2f}%，"
            f"成交量 {vol_k:.0f}K 張，量大震盪格局明顯。"
            "大量換手但漲跌幅收斂，代表多空雙方對目前價位認知存在顯著分歧，"
            "市場正在進行成本重置。此類型態結束後，通常會出現明確方向選擇，"
            "需觀察量能是否能有效縮量穩定，或者朝單一方向集中突破。"
        )}
    if change_percent <= -2 and change_percent > -5 and close_low and not very_heavy_volume:
        return {"signal": "拉回整理", "reason": (
            f"今日下跌 {abs(change_percent):.2f}%，收盤貼近日內低點（位置比 {close_position:.0%}），"
            f"量能 {vol_k:.0f}K 張尚未出現異常放大。"
            "從技術結構判斷，此為趨勢中的正常回檔整理，"
            "非主力出貨型態（量未顯著放大）。重點觀察：是否有前波支撐能守住，"
            "以及回測過程是否出現下影線承接訊號，若有則為拉回買點評估的參考依據。"
        )}
    if change_percent <= -3 and heavy_volume:
        return {"signal": "放量修正", "reason": (
            f"今日下跌 {abs(change_percent):.2f}%，成交量達 {vol_k:.0f}K 張，量增價跌格局確立。"
            "放量下殺通常代表持股信心動搖，市場出現較明顯的停損或調節賣壓。"
            "短線籌碼穩定度下降，不宜貿然承接。"
            "後續若出現量縮止跌（縮量不破前低），搭配下影線收盤，"
            "方可視為止穩訊號，再評估是否有反彈介入空間。"
        )}
    if change_percent <= -6 and very_heavy_volume and close_near_low:
        return {"signal": "弱勢破位", "reason": (
            f"今日重挫 {abs(change_percent):.2f}%，成交量 {vol_k:.0f}K 張爆量，"
            f"收盤位置貼近日內低點（位置比 {close_position:.0%}），"
            "技術面已出現明確破位訊號。爆量長黑且收低的型態，"
            "代表賣壓性質屬於主動殺盤而非被動承接，原有支撐結構遭到破壞。"
            "此時貿然承接風險極高，應等待量縮止穩且重新站回關鍵均線後，"
            "再重新評估後續機會。"
        )}
    if extreme_volume and amplitude_pct >= 5:
        return {"signal": "爆量震盪", "reason": (
            f"今日成交量達 {vol_k:.0f}K 張（極大量），振幅 {amplitude_pct:.2f}%，"
            f"漲跌幅 {change_percent:+.2f}%。"
            "天量配合大幅震盪，通常是市場對重大消息或技術關卡的激烈反應，"
            "多空雙方均積極表態。此型態後市方向不確定性極高，"
            "不建議追漲殺跌，應等待量能收縮、方向明朗後再行布局。"
        )}
    if change_percent < 0 and not heavy_volume and not close_near_low and amplitude_pct <= 4:
        return {"signal": "弱中透穩", "reason": (
            f"今日小幅收跌 {abs(change_percent):.2f}%，量能 {vol_k:.0f}K 張未見異常，"
            f"收盤距日內低點仍有一段距離（位置比 {close_position:.0%}）。"
            "此種「量縮小跌」格局，代表賣方並非主動出貨，"
            "而是市場觀望氣氛偏濃、買盤略顯保守所致。"
            "若後續能在低量整理後出現紅 K 帶量，則轉強機率上升；"
            "反之若跌幅擴大且量能增加，需重新評估支撐有效性。"
        )}
    if change_percent > 0:
        return {"signal": "小幅偏多", "reason": (
            f"今日小幅收紅 {change_percent:.2f}%，量能 {vol_k:.0f}K 張，"
            "整體價格結構維持正向，短線買盤仍具一定支撐力。"
            "雖漲幅有限，但收盤能守穩代表賣壓可控。"
            "需進一步觀察後續量能是否能逐步放大配合上漲，"
            "以確認買方力道是否具備延續性。"
        )}
    if change_percent < 0:
        return {"signal": "小幅偏空", "reason": (
            f"今日小幅收跌 {abs(change_percent):.2f}%，量能 {vol_k:.0f}K 張，"
            "短線追價意願略顯不足，盤面資金態度偏向保守觀望。"
            "目前跌幅尚屬可控範圍，並未出現明顯恐慌賣壓，"
            "但若後續無法有效止穩並出現紅 K 帶量，"
            "則弱勢結構確立的風險將上升。"
        )}
    return {"signal": "中性觀望", "reason": (
        "目前量價結構均衡，缺乏明確方向性訊號。"
        "市場處於多空拉鋸狀態，尚未形成具辨識度的趨勢優勢。"
        "建議觀察後續成交量是否出現方向性變化，"
        "以及關鍵價位（前高、前低、均線）的支撐壓力表現，再決定操作方向。"
    )}


def enrich_reason_with_context(
    base_reason: str, price: float, open_price: float, high_price: float,
    low_price: float, change_percent: float, volume: int, previous_close: float,
) -> str:
    extra: List[str] = []
    pos = calc_position_ratio(price, high_price, low_price)
    amplitude_pct = calc_amplitude_pct(high_price, low_price, previous_close)

    if pos >= 0.9:   extra.append("收盤幾乎貼近日內最高點，多方全程掌控盤勢，籌碼面偏強")
    elif pos >= 0.75: extra.append("收盤守穩日內偏高位置，買盤承接力道延續至收盤")
    elif pos <= 0.1:  extra.append("收盤逼近日內最低點，空方主導尾盤，賣壓沉重")
    elif pos <= 0.25: extra.append("收盤位於日內偏低區，盤中反彈動能不足以守回中段")
    else:             extra.append("收盤落在日內中段，多空未能明顯分出高下")

    if open_price > 0:
        gap_pct = (open_price - previous_close) / previous_close * 100 if previous_close > 0 else 0
        if gap_pct >= 2:   extra.append(f"今日跳空高開 {gap_pct:.1f}%，代表市場對利多訊息的即時反映")
        elif gap_pct <= -2: extra.append(f"今日跳空低開 {gap_pct:.1f}%，開盤即承受賣壓")
        if price > open_price:   extra.append("收盤高於開盤，日內走勢屬「開低走高」或「高開再漲」，多方主動積極")
        elif price < open_price: extra.append("收盤低於開盤，日內買盤無力撐住開盤價位，賣壓佔優")

    if change_percent >= 7:    extra.append("單日漲幅逼近漲停，籌碼高度集中，後市需觀察是否引發獲利了結潮")
    elif change_percent >= 4:  extra.append("漲幅具延續動能，若次日能以相對溫和量能維持，有利波段發展")
    elif change_percent <= -7: extra.append("單日跌幅逼近跌停，恐慌性賣壓明顯，短線宜觀察而非搶反彈")
    elif change_percent <= -4: extra.append("跌幅偏大，多方信心受損，需待量縮止穩後方可重新評估進場時機")

    if volume >= 50000:   extra.append(f"成交量 {volume/1000:.0f}K 張屬極大量，市場高度關注，主力資金積極參與")
    elif volume >= 20000: extra.append(f"成交量 {volume/1000:.0f}K 張顯著放大，法人或大戶參與度提升")
    elif volume >= 10000: extra.append(f"成交量 {volume/1000:.0f}K 張，量能活絡，有利價格維持趨勢方向")
    elif volume < 2000:   extra.append(f"成交量僅 {volume/1000:.1f}K 張偏低，市場參與度不足，後續動能需進一步觀察")

    if amplitude_pct >= 8:   extra.append(f"日內振幅 {amplitude_pct:.1f}%，波動風險大幅提升，停損設置需相應放寬")
    elif amplitude_pct >= 5: extra.append(f"日內振幅 {amplitude_pct:.1f}%，盤中震盪明顯，建議避免盤中情緒性追單")
    elif amplitude_pct <= 1.5: extra.append(f"日內振幅僅 {amplitude_pct:.1f}%，價格結構高度穩定，整理充分")

    if not extra:
        return base_reason
    return base_reason + "。補充分析：" + "；".join(extra) + "。"


def build_trade_plan(price: float, high_price: float, low_price: float, signal: str) -> Dict[str, str]:
    if price <= 0:
        return {"entry_price": "", "target_price": "", "stop_loss": ""}
    intraday_range = max(high_price - low_price, 0.0)
    base_buffer  = max(price * 0.015, intraday_range * 0.35, 0.3)
    wider_buffer = max(price * 0.025, intraday_range * 0.55, 0.5)
    bullish = {"強勢主升","放量突破","多方控盤","趨勢續強","穩健走高","高檔換手","小幅偏多","多頭趨勢","主升段延續","整理後待突破","轉強反彈"}
    bearish = {"放量修正","弱勢破位","小幅偏空","拉回整理","空頭趨勢"}
    neutral = {"區間盤整","籌碼換手","爆量震盪","中性觀望","弱中透穩","區間整理"}
    if signal in bullish:
        if signal in {"強勢主升","主升段延續"}:
            el, eh = price - wider_buffer, price - base_buffer * 0.2
            tl, th = price * 1.05, price * 1.09
            stop = price - wider_buffer * 1.05
        elif signal in {"放量突破","整理後待突破"}:
            el, eh = price - base_buffer * 1.1, price
            tl, th = price * 1.04, price * 1.07
            stop = price - wider_buffer * 0.95
        else:
            el = max(low_price if low_price > 0 else price * 0.98, price - base_buffer)
            eh = price
            tl, th = price * 1.03, price * 1.06
            stop = max(price - wider_buffer, price * 0.965)
        return {"entry_price": format_price_range(el, eh), "target_price": format_price_range(tl, th), "stop_loss": format_price_value(stop)}
    if signal in bearish:
        rh = price + base_buffer
        rl = max(price, price + base_buffer * 0.2)
        tl = max(price - wider_buffer * 1.3, 0.01)
        th = max(price - base_buffer * 0.4, tl)
        return {"entry_price": format_price_range(rl, rh), "target_price": format_price_range(tl, th), "stop_loss": format_price_value(price + wider_buffer)}
    if signal in neutral:
        ur = high_price if high_price > 0 else price * 1.02
        lr = low_price if low_price > 0 else price * 0.98
        bl, bh = ur, ur + base_buffer * 0.6
        return {"entry_price": f"突破 {format_price_range(bl, bh)} 後再評估", "target_price": format_price_range(ur + base_buffer, ur + wider_buffer * 1.2), "stop_loss": format_price_value(max(lr - base_buffer * 0.35, 0.01))}
    return {"entry_price": format_price_range(price * 0.98, price), "target_price": format_price_range(price * 1.03, price * 1.05), "stop_loss": format_price_value(price * 0.96)}


def build_strategy_and_risk(
    signal: str, price: float, open_price: float, high_price: float,
    low_price: float, volume: int, previous_close: float,
) -> Dict[str, str]:
    pos = calc_position_ratio(price, high_price, low_price)
    amplitude_pct = calc_amplitude_pct(high_price, low_price, previous_close)
    strong   = {"強勢主升","放量突破","多方控盤","趨勢續強","穩健走高","多頭趨勢","主升段延續"}
    moderate = {"高檔換手","小幅偏多","轉強反彈","整理後待突破","拉回整理"}
    neutral  = {"區間盤整","籌碼換手","爆量震盪","中性觀望","弱中透穩","區間整理"}
    weak     = {"放量修正","弱勢破位","小幅偏空","空頭趨勢"}
    if signal in strong:
        rating, bias, style = "A", "積極偏多", "短線偏多 / 拉回布局"
        action = "以拉回至均線支撐或前日高點分批承接為主策略，避免在急拉高點追漲。持倉期間以量能是否萎縮作為觀察依據：量縮守穩則續持，量縮卻跌破短均需提前減碼。"
    elif signal in moderate:
        rating, bias, style = "B+", "偏多觀察", "短線偏多 / 不追高"
        action = "採拉回至前波支撐或日內低點附近逢低介入策略，切勿在高檔情緒性追價。停利目標設在前高或整數關卡，若盤中出現長上影線或收盤跌破進場價，應立即停損。"
    elif signal in neutral:
        rating, bias, style = "C", "中性觀望", "等待表態 / 區間操作"
        action = "等待整理區間的上緣放量突破或下緣量縮止跌後再行介入，在方向明確前不建議在區間中段頻繁進出，以免被雙向震盪磨損成本。"
    elif signal in weak:
        rating, bias, style = "D", "保守偏空", "反彈減碼 / 嚴控風險"
        action = "現階段以風險控管優先，持倉者反彈至短均線壓力區可考慮減碼。未持倉者不建議搶反彈，需等到出現量縮止跌、下影線止穩等明確轉折訊號後再重新評估。"
    else:
        rating, bias, style = "C", "中性", "觀察為主"
        action = "目前訊號辨識度不足，先等待量價結構更清晰後再介入，避免倉位過早暴露於不確定風險中。"

    tp: List[str] = []
    if pos >= 0.85:   tp.append("收盤守穩日內高檔，多方主導格局維持")
    elif pos <= 0.2:  tp.append("收盤壓近日內低點，空方壓力尚未有效解除")
    else:             tp.append(f"收盤位於日內區間 {pos:.0%} 位置，多空尚未明確分出高下")
    if open_price > 0:
        if price > open_price:   tp.append("現價高於開盤，日內走勢屬多方主導，買盤具延續性")
        elif price < open_price: tp.append("現價低於開盤，買盤無法撐回開盤水位，賣壓略占優勢")
    if volume >= 30000:   tp.append(f"成交量 {volume/1000:.0f}K 張極大量，市場資金高度參與")
    elif volume >= 10000: tp.append(f"成交量 {volume/1000:.0f}K 張活絡，有利方向延續")
    elif volume < 3000:   tp.append(f"成交量 {volume/1000:.1f}K 張偏低，動能待觀察")
    if amplitude_pct >= 6:   tp.append(f"日內振幅 {amplitude_pct:.1f}%，波動風險偏高，停損需對應放寬")
    elif amplitude_pct <= 2: tp.append(f"日內振幅 {amplitude_pct:.1f}%，價格結構穩定")
    else:                    tp.append(f"日內振幅 {amplitude_pct:.1f}%，屬正常範圍")

    trend_map = {
        "強勢主升":    ("強勢主升段",   "短線漲幅擴大後易出現急拉急跌，若次日出現高量長上影線或跳空回補，需立即收斂部位。"),
        "主升段延續":  ("強勢主升段",   "短線漲幅擴大後易出現急拉急跌，若次日出現高量長上影線或跳空回補，需立即收斂部位。"),
        "放量突破":    ("突破後續攻",   "突破有效性需以「次日量縮不破突破點」來確認，若快速跌回整理區需提防假突破洗盤。"),
        "整理後待突破":("突破前蓄積",   "整理期間需耐心等待放量突破訊號，切勿在量縮不明時提前押注。"),
        "多方控盤":    ("多方主導",     "開盤跳空缺口若遭回補，多方優勢將受損，需以缺口上緣作為短線停損參考。"),
        "多頭趨勢":    ("多頭趨勢延續", "均線多頭排列結構完整，主要風險為量能萎縮造成的趨勢衰竭，需持續監控。"),
        "趨勢續強":    ("偏多續航",     "量價齊揚的健康上漲，主要風險在量價背離訊號出現，需定期確認量能是否與價格同步。"),
        "穩健走高":    ("溫和偏多",     "穩健走強型態籌碼較乾淨，但需防範盤勢轉弱後出現無量下跌的籌碼鬆動現象。"),
        "轉強反彈":    ("由弱轉強",     "反彈初期力道需要量能驗證，若反彈過程量能遞減，需警惕反彈高度有限。"),
        "高檔換手":    ("高位換手整理", "高量換手後需觀察次日量縮與否，量縮穩定代表換手充分；量未縮且再度大跌則為風險訊號。"),
        "拉回整理":    ("回檔修正",     "正常回檔需觀察前波支撐是否有效守住，若支撐位量縮止跌，可視為整理結束訊號。"),
        "弱中透穩":    ("弱勢整理",     "量縮小跌格局相對穩定，但若後續無法轉紅帶量，弱勢結構恐難在短期扭轉。"),
    }
    if signal in trend_map:
        trend_type, risk_note = trend_map[signal]
    elif signal in {"區間盤整","籌碼換手","爆量震盪","區間整理"}:
        trend_type = "整理等待方向"
        risk_note  = "方向不明朗時最大風險為頻繁進出造成的手續費損耗，耐心等待量能方向性突破最為穩健。"
    elif signal in {"放量修正","弱勢破位","小幅偏空","空頭趨勢"}:
        trend_type = "弱勢修正結構"
        risk_note  = "下跌趨勢中逢低承接的勝率通常偏低，建議以「量縮止跌 + 重新站回關鍵均線」作為重新介入的前提條件。"
    else:
        trend_type = "中性觀望"
        risk_note  = "缺乏明確結構訊號，不確定性風險較高，建議降低部位等待更清晰的操作機會。"

    return {
        "trend_type": trend_type, "technical_comment": "；".join(tp) + "。",
        "operation_rating": rating, "operation_bias": bias, "operation_style": style,
        "strategy_action": action, "risk_note": risk_note,
    }


def calc_risk_reward(entry_price: str, target_price: str, stop_loss: str) -> str:
    entry_mid  = parse_range_mid(entry_price, 0.0)
    target_mid = parse_range_mid(target_price, 0.0)
    stop = safe_float(stop_loss, 0.0)
    if entry_mid <= 0 or target_mid <= 0 or stop <= 0:
        return ""
    reward = abs(target_mid - entry_mid)
    risk   = abs(entry_mid - stop)
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
    if len(_HISTORY_CACHE) >= HISTORY_CACHE_MAX_SIZE:
        cutoff = HISTORY_CACHE_MAX_SIZE * 0.8
        sorted_keys = sorted(
            _HISTORY_CACHE.keys(),
            key=lambda k: _HISTORY_CACHE[k].get("fetched_at", datetime.min),
        )
        for k in sorted_keys[:int(len(sorted_keys) - cutoff)]:
            _HISTORY_CACHE.pop(k, None)
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
    return macd_line_series[-1], signal_series[-1], macd_line_series[-1] - signal_series[-1]


def calc_atr(candles: List[Dict[str, Any]], period: int = 14) -> float:
    if len(candles) < 2:
        return 0.0
    trs: List[float] = []
    prev_close = safe_float(candles[0].get("close"))
    for c in candles[1:]:
        high  = safe_float(c.get("high"))
        low   = safe_float(c.get("low"))
        close = safe_float(c.get("close"))
        trs.append(max(high - low, abs(high - prev_close), abs(low - prev_close)))
        prev_close = close
    return avg(trs[-period:]) if trs else 0.0


def fetch_symbol_daily_candles(symbol: str) -> Dict[str, Any]:
    cached = get_history_cache(symbol)
    if cached:
        return cached
    stock_client = get_stock_rest_client()
    to_date   = now_taipei().strftime("%Y-%m-%d")
    from_date = (now_taipei() - timedelta(days=420)).strftime("%Y-%m-%d")
    resp = stock_client.historical.candles(
        **{"symbol": symbol, "from": from_date, "to": to_date, "timeframe": "D", "sort": "asc"}
    )
    rows = extract_rows(resp)
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
    candles = [x for x in candles if x["close"] > 0]
    if len(candles) > 420:
        candles = candles[-420:]
    data = {"candles": candles}
    set_history_cache(symbol, data)
    return data


def classify_daily_pattern(
    close_now: float, ma5: float, ma10: float, ma20: float,
    high20: float, low20: float, vol_ratio5: float, rsi14: float, macd_hist: float,
) -> Dict[str, str]:
    near_high20 = high20 > 0 and close_now >= high20 * 0.985
    near_low20  = low20  > 0 and close_now <= low20  * 1.02
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
    if close_now > ma5 > ma10 > ma20:
        gap_pct = (close_now - ma20) / ma20 * 100 if ma20 > 0 else 0
        parts.append(f"均線呈完整多頭排列（MA5 {format_price_value(ma5)} > MA10 {format_price_value(ma10)} > MA20 {format_price_value(ma20)}），現價高於 MA20 達 {gap_pct:.1f}%，中短期趨勢結構完整偏強")
    elif close_now > ma20:
        diff_pct = (close_now - ma20) / ma20 * 100 if ma20 > 0 else 0
        parts.append(f"現價（{format_price_value(close_now)}）站在 MA20（{format_price_value(ma20)}）之上 {diff_pct:.1f}%，中期結構偏多，但短期均線尚未完全多頭排列，趨勢回升中")
    elif close_now < ma5 < ma10 < ma20:
        gap_pct = (ma20 - close_now) / ma20 * 100 if ma20 > 0 else 0
        parts.append(f"均線呈空頭排列（MA5 < MA10 < MA20），現價低於 MA20 達 {gap_pct:.1f}%，中短期趨勢結構偏弱，反彈面臨均線壓力")
    else:
        parts.append(f"現價（{format_price_value(close_now)}）相對 MA20（{format_price_value(ma20)}）偏弱，均線結構尚未完整轉多，方向仍在確認中")

    if avg_vol5 > 0:
        vr = vol_now / avg_vol5
        if vr >= 1.5:   parts.append(f"今日量能（{vol_now/1000:.0f}K 張）為 5 日均量的 {vr:.1f} 倍，量能大幅放大顯示主力資金積極介入，市場關注度顯著提升")
        elif vr >= 1.2: parts.append(f"今日量能（{vol_now/1000:.0f}K 張）高於 5 日均量 {(vr-1)*100:.0f}%，量能溫和放大，市場參與度提升")
        elif vr <= 0.6: parts.append(f"今日量能（{vol_now/1000:.0f}K 張）僅為 5 日均量的 {vr:.1f} 倍，量能明顯萎縮，市場觀望氣氛偏濃，後續動能需進一步確認")
        else:           parts.append(f"今日量能（{vol_now/1000:.0f}K 張）與 5 日均量相近（比值 {vr:.2f}），正常換手，量能結構平穩")

    if high20 > 0 and low20 > 0:
        range20 = high20 - low20
        pos20 = (close_now - low20) / range20 if range20 > 0 else 0.5
        if close_now >= high20 * 0.98:    parts.append(f"現價已突破或逼近近 20 日最高點（{format_price_value(high20)}），正在測試前波壓力，若能有效突破將開啟新一波行情空間")
        elif close_now <= low20 * 1.03:   parts.append(f"現價逼近近 20 日最低點（{format_price_value(low20)}），處於重要支撐測試區域，此位置能否守穩將決定後續走向")
        else:                              parts.append(f"現價位於近 20 日高低區間（{format_price_value(low20)} ～ {format_price_value(high20)}）的 {pos20:.0%} 位置，{'偏上緣強勢整理' if pos20 >= 0.6 else '偏下緣弱勢整理' if pos20 <= 0.4 else '中段位置等待突破方向'}")

    if rsi14 >= 75:   parts.append(f"RSI(14) 達 {rsi14:.1f}，進入超買區間，短線技術面過熱，動能雖強但追價風險顯著上升，需留意獲利了結潮出現")
    elif rsi14 >= 60: parts.append(f"RSI(14) {rsi14:.1f}，位於多方優勢區間，動能維持正向，尚未進入過熱區，趨勢延續空間仍在")
    elif rsi14 <= 25: parts.append(f"RSI(14) 僅 {rsi14:.1f}，深入超賣區間，技術面短線跌幅過大，存在技術性反彈機會，但反彈高度需量能配合確認")
    elif rsi14 <= 40: parts.append(f"RSI(14) {rsi14:.1f}，位於弱勢區間，買盤動能不足，反彈可信度有限，需等待 RSI 回升並站上 50 才確認動能轉強")
    else:             parts.append(f"RSI(14) {rsi14:.1f}，位於中性區間，市場尚未出現極端情緒，趨勢方向仍以量能與價格結構為主要判斷依據")

    if macd_hist > 0 and macd_line > signal_line:
        if macd_hist > abs(macd_line) * 0.1: parts.append(f"MACD 柱狀體正值擴大（Hist {macd_hist:.3f}），DIF 與 MACD 死叉空間擴大，中短線上漲動能持續增強")
        else:                                 parts.append(f"MACD 維持正值（Hist {macd_hist:.3f}），多頭動能存在但幅度有限，需觀察是否能持續擴大")
    elif macd_hist < 0 and macd_line < signal_line:
        parts.append(f"MACD 柱狀體負值（Hist {macd_hist:.3f}），DIF 仍在 MACD 之下，中短線動能偏弱，反彈需等待柱狀體由負轉正確認")
    else:
        parts.append(f"MACD 柱狀體趨近零軸（Hist {macd_hist:.3f}），多空動能進入收斂，趨勢轉折訊號即將浮現，需密切關注後續方向選擇")

    parts.append(f"整體日 K 型態屬「{pattern_text}」")
    return f"【{name} 日K技術分析】" + "；".join(parts) + "。"


def build_historical_technical_comment(
    ma5: float, ma10: float, ma20: float, avg_vol5: float, avg_vol20: float,
    rsi14: float, macd_line: float, signal_line: float, macd_hist: float,
    high20: float, low20: float, atr14: float,
) -> str:
    return "；".join([
        f"均線 MA5/{format_price_value(ma5)}  MA10/{format_price_value(ma10)}  MA20/{format_price_value(ma20)}",
        f"5日均量 {format_number(avg_vol5)} 張 / 20日均量 {format_number(avg_vol20)} 張",
        f"RSI(14) = {rsi14:.2f}",
        f"MACD DIF {macd_line:.3f} / Signal {signal_line:.3f} / Hist {macd_hist:.3f}",
        f"近20日波動區間 {format_price_value(low20)} ～ {format_price_value(high20)}",
        f"ATR(14) = {format_price_value(atr14)}（日均波動幅度參考）",
    ]) + "。"


def build_historical_trade_plan(
    price: float, ma5: float, ma20: float,
    high20: float, low20: float, atr14: float, signal: str,
) -> Dict[str, str]:
    bs = max(atr14 * 0.6, price * 0.012, 0.3)
    bl = max(atr14 * 1.0, price * 0.022, 0.6)
    if signal in {"主升段延續","多頭趨勢","轉強反彈"}:
        el = max(ma5 - bs, low20, 0.01)
        eh = max(ma5 + bs * 0.5, el)
        tl = max(high20 * 1.01, price * 1.04)
        th = max(tl, price + bl * 2.0)
        return {"entry_price": format_price_range(el, eh), "target_price": format_price_range(tl, th), "stop_loss": format_price_value(max(ma20 - bs, 0.01))}
    if signal == "整理後待突破":
        bkl = max(high20, price)
        bkh = bkl + bs
        return {"entry_price": f"突破 {format_price_range(bkl, bkh)} 後再評估", "target_price": format_price_range(bkh + bs, bkh + bl * 1.8), "stop_loss": format_price_value(max(ma20 - bs, low20 - bs * 0.3, 0.01))}
    if signal in {"空頭趨勢","拉回整理"}:
        rl = price + bs * 0.3
        rh = price + bl
        tl = max(low20 - bs, 0.01)
        th = max(price - bs, tl)
        return {"entry_price": format_price_range(rl, rh), "target_price": format_price_range(tl, th), "stop_loss": format_price_value(max(ma5 + bs, rh))}
    bkl = max(high20, price)
    bkh = bkl + bs
    return {"entry_price": f"突破 {format_price_range(bkl, bkh)} 後再評估", "target_price": format_price_range(bkh + bs, bkh + bl), "stop_loss": format_price_value(max(low20 - bs * 0.25, 0.01))}


def build_historical_strategy(signal: str) -> Dict[str, str]:
    if signal in {"主升段延續","多頭趨勢"}:
        return {"operation_rating": "A", "operation_bias": "積極偏多", "operation_style": "順勢拉回布局",
                "strategy_action": "以靠近 5 日均線或前一日高點作為短線支撐參考，分批承接為主。持倉標準：量能維持在 5 日均量之上、均線多頭排列不破。目標設在近 20 日高點上方 1-2 個 ATR，停損設在 MA20 下方。",
                "risk_note": "主升段最大風險為「量能衰竭後的急速回落」。若出現 K 線上影線明顯拉長、或量大卻收盤低於開盤的情況，需立即檢視持倉。"}
    if signal in {"轉強反彈","整理後待突破"}:
        return {"operation_rating": "B+", "operation_bias": "偏多觀察", "operation_style": "等突破確認再介入",
                "strategy_action": "優先等待價格有效突破近 20 日高點，且突破當日量能需明顯放大（建議 > 5 日均量 20%）。確認後可於次日回測不破時分批介入，停損設在突破點下方 1 個 ATR。",
                "risk_note": "整理期間最常見陷阱為「假突破後快速跌回」。若突破後次日量縮且收盤跌回突破點以下，需立即停損，避免被洗盤套牢。"}
    if signal == "區間整理":
        return {"operation_rating": "C", "operation_bias": "中性觀望", "operation_style": "等待方向表態",
                "strategy_action": "整理格局中不建議主動建倉。可設定突破上緣（含量能放大確認）與跌破下緣（含量能放大確認）兩個觸發條件，待任一條件成立後再決定操作方向。",
                "risk_note": "區間整理的主要風險為誤判突破方向。建議以量能作為過濾條件：無量突破不追，有量縮期間不做空。"}
    return {"operation_rating": "D", "operation_bias": "保守偏空", "operation_style": "反彈減碼 / 嚴控風險",
            "strategy_action": "弱勢格局中以保護現有獲利或減少虧損為首要目標。持倉者可利用反彈至短均線壓力區逐步減碼；空倉者等待「量縮止跌 + 收紅 K + 站回 MA20」三條件同時成立後再重新評估。",
            "risk_note": "弱勢標的最大風險為「越跌越買」的抄底心態。均線空頭排列期間，每次反彈都是潛在的減碼機會而非加碼機會。"}


def build_historical_analysis_for_stock(base_stock: Dict[str, Any]) -> Dict[str, Any]:
    symbol = safe_str(base_stock.get("symbol"))
    if not symbol:
        return base_stock
    try:
        history_data = fetch_symbol_daily_candles(symbol)
        candles = history_data.get("candles", [])
        if len(candles) < 25:
            return base_stock
        closes  = [safe_float(x.get("close"))  for x in candles if safe_float(x.get("close"))  > 0]
        highs   = [safe_float(x.get("high"))   for x in candles if safe_float(x.get("high"))   > 0]
        lows    = [safe_float(x.get("low"))    for x in candles if safe_float(x.get("low"))    > 0]
        volumes = [safe_float(x.get("volume")) for x in candles]
        if len(closes) < 25:
            return base_stock
        close_now  = safe_float(base_stock.get("price")) or closes[-1]
        ma5, ma10, ma20 = avg(closes[-5:]), avg(closes[-10:]), avg(closes[-20:])
        high20 = max(highs[-20:]) if len(highs) >= 20 else max(highs)
        low20  = min(lows[-20:])  if len(lows)  >= 20 else min(lows)
        vol_now    = safe_int(base_stock.get("volume")) or safe_int(volumes[-1])
        avg_vol5   = avg(volumes[-5:])
        avg_vol20  = avg(volumes[-20:])
        vol_ratio5 = (vol_now / avg_vol5) if avg_vol5 > 0 else 1.0
        rsi14 = calc_rsi(closes, 14)
        macd_line, signal_line, macd_hist = calc_macd(closes)
        atr14 = calc_atr(candles, 14)
        pattern_info = classify_daily_pattern(close_now=close_now, ma5=ma5, ma10=ma10, ma20=ma20, high20=high20, low20=low20, vol_ratio5=vol_ratio5, rsi14=rsi14, macd_hist=macd_hist)
        reason = build_historical_reason(name=safe_str(base_stock.get("name")), close_now=close_now, ma5=ma5, ma10=ma10, ma20=ma20, high20=high20, low20=low20, vol_now=vol_now, avg_vol5=avg_vol5, rsi14=rsi14, macd_line=macd_line, signal_line=signal_line, macd_hist=macd_hist, pattern_text=pattern_info["pattern"])
        technical_comment = build_historical_technical_comment(ma5=ma5, ma10=ma10, ma20=ma20, avg_vol5=avg_vol5, avg_vol20=avg_vol20, rsi14=rsi14, macd_line=macd_line, signal_line=signal_line, macd_hist=macd_hist, high20=high20, low20=low20, atr14=atr14)
        plan     = build_historical_trade_plan(price=close_now, ma5=ma5, ma20=ma20, high20=high20, low20=low20, atr14=atr14, signal=pattern_info["signal"])
        strategy = build_historical_strategy(pattern_info["signal"])
        risk_reward = calc_risk_reward(plan["entry_price"], plan["target_price"], plan["stop_loss"])
        bonus_map = {"主升段延續": 24, "多頭趨勢": 18, "轉強反彈": 12, "整理後待突破": 12, "區間整理": 5}
        bonus = bonus_map.get(pattern_info["signal"], 0.0)
        recommendation_score = round(safe_float(base_stock.get("recommendation_score"), 0.0) + bonus + max((rsi14 - 50) * 0.18, -6), 2)
        merged = dict(base_stock)
        merged.update({"signal": pattern_info["signal"], "trend_type": pattern_info["trend_type"], "reason": reason, "technical_comment": technical_comment, "operation_rating": strategy["operation_rating"], "operation_bias": strategy["operation_bias"], "operation_style": strategy["operation_style"], "strategy_action": strategy["strategy_action"], "entry_price": plan["entry_price"], "target_price": plan["target_price"], "stop_loss": plan["stop_loss"], "risk_reward": risk_reward, "risk_note": strategy["risk_note"], "recommendation_score": recommendation_score, "analysis_source": "historical_k"})
        return merged
    except Exception as e:
        logger.warning(f"[historical_k] {symbol} 分析失敗: {e}\n{traceback.format_exc()}")
        return base_stock


def build_focused_analysis(stock: Dict[str, Any]) -> Dict[str, Any]:
    return {k: stock.get(k, "" if isinstance(v, str) else 0) for k, v in {
        "symbol": "", "name": "", "market": "", "price": 0, "change": 0, "change_percent": 0,
        "volume": 0, "signal": "", "trend_type": "", "operation_rating": "", "operation_bias": "",
        "operation_style": "", "technical_comment": "", "analysis": "", "strategy_action": "",
        "entry_price": "", "target_price": "", "stop_loss": "", "risk_reward": "", "risk_note": "", "update_time": "",
    }.items()} | {"analysis": stock.get("reason", "")}


def normalize_snapshot_row(row: Dict[str, Any], market_label: str) -> Optional[Dict[str, Any]]:
    if not isinstance(row, dict):
        return None
    symbol = safe_str(row.get("symbol") or row.get("stockNo") or row.get("stock_no") or row.get("code") or row.get("ticker"))
    if not symbol:
        return None
    name = safe_str(row.get("name") or row.get("stockName") or row.get("stock_name") or symbol)
    if not is_valid_main_board_symbol(symbol, name):
        return None
    price = safe_float(row.get("lastPrice") or row.get("closePrice") or row.get("tradePrice") or row.get("price") or row.get("currentPrice"))
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
    volume      = safe_int(row.get("tradeVolume") or row.get("volume") or row.get("totalVolume") or row.get("accumulatedVolume") or row.get("tradeVolumeAtBid"))
    trade_value = safe_int(row.get("tradeValue"))
    open_price  = safe_float(row.get("openPrice"))
    high_price  = safe_float(row.get("highPrice"))
    low_price   = safe_float(row.get("lowPrice"))
    update_time_raw = row.get("lastUpdated") or row.get("time") or 0
    category = price_category(price)
    liquidity_bonus   = min(volume / 5000, 20)
    volatility_ratio  = (max(high_price - low_price, 0) / max(price, 1)) * 10 if price > 0 else 0
    stability_penalty = min(volatility_ratio, 10)
    score = round(abs(change_percent) * 10 + min(volume / 100000, 50), 2)
    base_recommendation_score = max(0.0, abs(change_percent) * 6 + liquidity_bonus + 2 - stability_penalty * 0.3)
    signal_info   = build_signal_and_reason(price=price, change=change, change_percent=change_percent, volume=volume, high_price=high_price, low_price=low_price, open_price=open_price, previous_close=previous_close)
    final_reason  = enrich_reason_with_context(base_reason=signal_info["reason"], price=price, open_price=open_price, high_price=high_price, low_price=low_price, change_percent=change_percent, volume=volume, previous_close=previous_close)
    plan          = build_trade_plan(price=price, high_price=high_price, low_price=low_price, signal=signal_info["signal"])
    strategy_info = build_strategy_and_risk(signal=signal_info["signal"], price=price, open_price=open_price, high_price=high_price, low_price=low_price, volume=volume, previous_close=previous_close)
    risk_reward   = calc_risk_reward(plan["entry_price"], plan["target_price"], plan["stop_loss"])
    rating_bonus_map = {"A": 18, "B+": 12, "C": 5, "D": 0}
    recommendation_score = round(base_recommendation_score + rating_bonus_map.get(strategy_info["operation_rating"], 0), 2)
    return {
        "market": market_label, "symbol": symbol, "name": name,
        "price": round(price, 2), "change": round(change, 2), "change_percent": round(change_percent, 2),
        "volume": volume, "trade_value": trade_value, "score": score, "recommendation_score": recommendation_score,
        "prev_close": round(previous_close, 2) if previous_close > 0 else 0,
        "open": round(open_price, 2), "high": round(high_price, 2), "low": round(low_price, 2),
        "update_time": micros_to_taipei_str(update_time_raw), "update_time_raw": update_time_raw, "category": category,
        "signal": signal_info["signal"], "trend_type": strategy_info["trend_type"], "reason": final_reason,
        "technical_comment": strategy_info["technical_comment"], "operation_rating": strategy_info["operation_rating"],
        "operation_bias": strategy_info["operation_bias"], "operation_style": strategy_info["operation_style"],
        "strategy_action": strategy_info["strategy_action"], "entry_price": plan["entry_price"],
        "target_price": plan["target_price"], "stop_loss": plan["stop_loss"], "risk_reward": risk_reward,
        "risk_note": strategy_info["risk_note"], "analysis_source": "snapshot",
    }


# =========================
# Validation / Backtest
# =========================
def append_jsonl(filepath: str, row: Dict[str, Any]) -> None:
    try:
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        with open(filepath, "a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    except Exception as e:
        logger.warning(f"[validation] 寫入失敗: {e}")


def load_jsonl(filepath: str) -> List[Dict[str, Any]]:
    if not os.path.exists(filepath):
        return []
    rows: List[Dict[str, Any]] = []
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rows.append(json.loads(line))
                except Exception:
                    continue
    except Exception as e:
        logger.warning(f"[validation] 讀取失敗: {e}")
    return rows


def determine_trade_direction(signal: str, operation_bias: str) -> str:
    long_signals = {"強勢主升","放量突破","多方控盤","趨勢續強","穩健走高","高檔換手","小幅偏多","多頭趨勢","主升段延續","整理後待突破","轉強反彈","拉回整理"}
    short_signals = {"放量修正","弱勢破位","小幅偏空","空頭趨勢"}
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
        if not symbol:
            continue
        if (today, symbol) in existing_keys:
            continue
        row = {
            "date": today, "symbol": symbol, "name": safe_str(r.get("name")),
            "market": safe_str(r.get("market")), "pick_price": safe_float(r.get("price")),
            "signal": safe_str(r.get("signal")), "trend_type": safe_str(r.get("trend_type")),
            "operation_bias": safe_str(r.get("operation_bias")), "operation_rating": safe_str(r.get("operation_rating")),
            "recommendation_score": safe_float(r.get("recommendation_score")),
            "entry_price": safe_str(r.get("entry_price")), "target_price": safe_str(r.get("target_price")),
            "stop_loss": safe_str(r.get("stop_loss")), "risk_reward": safe_str(r.get("risk_reward")),
        }
        append_jsonl(VALIDATION_LOG_FILE, row)


def find_candle_index_for_pick(candles: List[Dict[str, Any]], pick_date: date) -> int:
    exact_idx = -1
    next_idx  = -1
    for i, c in enumerate(candles):
        c_date = parse_any_date(c.get("date"))
        if not c_date:
            continue
        if c_date == pick_date:
            exact_idx = i
            break
        if c_date > pick_date and next_idx == -1:
            next_idx = i
    return exact_idx if exact_idx >= 0 else next_idx


def calc_directional_return(entry_price: float, exit_price: float, direction: str) -> float:
    if entry_price <= 0 or exit_price <= 0:
        return 0.0
    if direction == "short":
        return ((entry_price - exit_price) / entry_price) * 100
    return ((exit_price - entry_price) / entry_price) * 100


def evaluate_first_hit(
    future_bars: List[Dict[str, Any]],
    direction: str,
    target_price: float,
    stop_price: float,
) -> Dict[str, Any]:
    if direction not in {"long", "short"}:
        return {"first_hit": "not_applicable", "first_hit_day": 0, "target_hit": False, "target_hit_day": 0, "stop_hit": False, "stop_hit_day": 0}

    target_hit_day = 0
    stop_hit_day   = 0

    for idx, bar in enumerate(future_bars, start=1):
        high = safe_float(bar.get("high"))
        low  = safe_float(bar.get("low"))

        if direction == "long":
            hit_target = target_price > 0 and high >= target_price
            hit_stop   = stop_price   > 0 and low  <= stop_price
        else:
            hit_target = target_price > 0 and low  <= target_price
            hit_stop   = stop_price   > 0 and high >= stop_price

        # ✅ fix 3: 先記錄兩個 hit_day，再一起判斷 first_hit，避免 both_same_bar 時漏記
        if hit_target and target_hit_day == 0:
            target_hit_day = idx
        if hit_stop and stop_hit_day == 0:
            stop_hit_day = idx

        if target_hit_day > 0 or stop_hit_day > 0:
            # 一旦有任一個被觸及，後續只需要確認同一根是否兩個都觸及
            if target_hit_day > 0 and stop_hit_day > 0:
                if target_hit_day == stop_hit_day:
                    first_hit     = "both_same_bar"
                    first_hit_day = target_hit_day
                elif target_hit_day < stop_hit_day:
                    first_hit     = "target"
                    first_hit_day = target_hit_day
                else:
                    first_hit     = "stop"
                    first_hit_day = stop_hit_day
                break
            if target_hit_day > 0 and stop_hit_day == 0:
                first_hit     = "target"
                first_hit_day = target_hit_day
                break
            if stop_hit_day > 0 and target_hit_day == 0:
                first_hit     = "stop"
                first_hit_day = stop_hit_day
                break
    else:
        first_hit     = "none"
        first_hit_day = 0

    return {
        "first_hit":      first_hit,
        "first_hit_day":  first_hit_day,
        "target_hit":     target_hit_day > 0,
        "target_hit_day": target_hit_day,
        "stop_hit":       stop_hit_day > 0,
        "stop_hit_day":   stop_hit_day,
    }


def calc_mfe_mae(pick_price: float, future_bars: List[Dict[str, Any]], direction: str) -> Dict[str, float]:
    if pick_price <= 0 or not future_bars:
        return {"mfe_pct": 0.0, "mae_pct": 0.0}
    highs = [safe_float(x.get("high")) for x in future_bars if safe_float(x.get("high")) > 0]
    lows  = [safe_float(x.get("low"))  for x in future_bars if safe_float(x.get("low"))  > 0]
    if not highs or not lows:
        return {"mfe_pct": 0.0, "mae_pct": 0.0}
    max_high = max(highs)
    min_low  = min(lows)
    if direction == "short":
        mfe = ((pick_price - min_low)  / pick_price) * 100
        mae = ((pick_price - max_high) / pick_price) * 100
    else:
        mfe = ((max_high - pick_price) / pick_price) * 100
        mae = ((min_low  - pick_price) / pick_price) * 100
    return {"mfe_pct": round(mfe, 2), "mae_pct": round(mae, 2)}


def evaluate_single_record(record: Dict[str, Any], holding_days: int = 5) -> Optional[Dict[str, Any]]:
    pick_date  = parse_any_date(record.get("date"))
    symbol     = safe_str(record.get("symbol"))
    pick_price = safe_float(record.get("pick_price"))
    if not pick_date or not symbol or pick_price <= 0:
        return None
    history_data = fetch_symbol_daily_candles(symbol)
    candles = history_data.get("candles", [])
    if len(candles) < holding_days + 2:
        return None
    pick_idx = find_candle_index_for_pick(candles, pick_date)
    if pick_idx < 0:
        return None
    future_bars = candles[pick_idx + 1: pick_idx + 1 + holding_days]
    if len(future_bars) < holding_days:
        return None
    direction  = determine_trade_direction(signal=safe_str(record.get("signal")), operation_bias=safe_str(record.get("operation_bias")))
    entry_mid  = parse_range_mid(record.get("entry_price"), pick_price)
    target_mid = parse_range_mid(record.get("target_price"), 0.0)
    stop_price = safe_float(record.get("stop_loss"), 0.0)
    closes_by_n: Dict[int, float] = {}
    returns_by_n: Dict[int, float] = {}
    raw_returns_by_n: Dict[int, float] = {}
    for n in VALIDATION_FORWARD_BARS:
        if len(future_bars) >= n:
            close_n = safe_float(future_bars[n - 1].get("close"))
            closes_by_n[n]      = round(close_n, 2)
            raw_returns_by_n[n] = round(((close_n - pick_price) / pick_price) * 100, 2) if pick_price > 0 else 0.0
            returns_by_n[n]     = round(calc_directional_return(pick_price, close_n, direction), 2)
    hit_info  = evaluate_first_hit(future_bars=future_bars, direction=direction, target_price=target_mid, stop_price=stop_price)
    excursion = calc_mfe_mae(pick_price=pick_price, future_bars=future_bars, direction=direction)
    return {
        "date": safe_str(record.get("date")), "symbol": symbol, "name": safe_str(record.get("name")),
        "market": safe_str(record.get("market")), "signal": safe_str(record.get("signal")),
        "trend_type": safe_str(record.get("trend_type")), "operation_bias": safe_str(record.get("operation_bias")),
        "operation_rating": safe_str(record.get("operation_rating")), "direction": direction,
        "pick_price": round(pick_price, 2), "entry_price": safe_str(record.get("entry_price")),
        "entry_mid": round(entry_mid, 2) if entry_mid > 0 else 0.0,
        "target_price": safe_str(record.get("target_price")), "target_mid": round(target_mid, 2) if target_mid > 0 else 0.0,
        "stop_loss": safe_str(record.get("stop_loss")), "stop_price": round(stop_price, 2) if stop_price > 0 else 0.0,
        "risk_reward": safe_str(record.get("risk_reward")),
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
    """✅ fix 6: validation 結果短暫 cache，details + summary 共用，避免重複計算"""
    now = now_taipei()
    cached = _VALIDATION_CACHE
    if (
        cached["rows"] is not None
        and cached["fetched_at"] is not None
        and cached["lookback_days"] == lookback_days
        and cached["holding_days"] == holding_days
        and (now - cached["fetched_at"]).total_seconds() < VALIDATION_CACHE_SECONDS
    ):
        return cached["rows"]

    records = load_jsonl(VALIDATION_LOG_FILE)
    today   = now.date()
    matured_records = [
        r for r in records
        if (d := parse_any_date(r.get("date"))) and holding_days <= (today - d).days <= lookback_days
    ]

    results: List[Dict[str, Any]] = []
    # ✅ fix 2: max_workers 降到 3，避免 SDK rate limit
    with ThreadPoolExecutor(max_workers=3) as executor:
        future_to_key = {executor.submit(evaluate_single_record, r, holding_days): safe_str(r.get("symbol")) for r in matured_records}
        for future in as_completed(future_to_key):
            try:
                item = future.result()
                if item:
                    results.append(item)
            except Exception as e:
                logger.warning(f"[validation] {future_to_key[future]} 驗證失敗: {e}")

    results.sort(key=lambda x: (safe_str(x.get("date")), safe_float(x.get("strategy_return_t5"))), reverse=True)

    _VALIDATION_CACHE["rows"]         = results
    _VALIDATION_CACHE["fetched_at"]   = now
    _VALIDATION_CACHE["lookback_days"] = lookback_days
    _VALIDATION_CACHE["holding_days"]  = holding_days
    return results


def summarize_by_key(rows: List[Dict[str, Any]], key_name: str) -> List[Dict[str, Any]]:
    stats: Dict[str, Dict[str, Any]] = {}
    for r in rows:
        kv = safe_str(r.get(key_name)) or "未分類"
        if kv not in stats:
            stats[kv] = {key_name: kv, "count": 0, "win_t1": 0, "win_t3": 0, "win_t5": 0,
                         "target_hit": 0, "stop_hit": 0, "both_same_bar": 0,
                         "sum_rt1": 0.0, "sum_rt3": 0.0, "sum_rt5": 0.0,
                         "sum_raw5": 0.0, "sum_mfe": 0.0, "sum_mae": 0.0}
        s = stats[kv]
        s["count"]    += 1
        s["sum_rt1"]  += safe_float(r.get("strategy_return_t1"))
        s["sum_rt3"]  += safe_float(r.get("strategy_return_t3"))
        s["sum_rt5"]  += safe_float(r.get("strategy_return_t5"))
        s["sum_raw5"] += safe_float(r.get("raw_return_t5"))
        s["sum_mfe"]  += safe_float(r.get("mfe_pct_5d"))
        s["sum_mae"]  += safe_float(r.get("mae_pct_5d"))
        if r.get("win_t1"):     s["win_t1"]      += 1
        if r.get("win_t3"):     s["win_t3"]      += 1
        if r.get("win_t5"):     s["win_t5"]      += 1
        if r.get("target_hit"): s["target_hit"]  += 1
        if r.get("stop_hit"):   s["stop_hit"]    += 1
        if safe_str(r.get("first_hit")) == "both_same_bar": s["both_same_bar"] += 1

    output = []
    for _, s in stats.items():
        n = s["count"]
        output.append({
            key_name: s[key_name], "count": n,
            "win_rate_t1": round(s["win_t1"] / n * 100, 2) if n else 0.0,
            "win_rate_t3": round(s["win_t3"] / n * 100, 2) if n else 0.0,
            "win_rate_t5": round(s["win_t5"] / n * 100, 2) if n else 0.0,
            "target_hit_rate_5d":   round(s["target_hit"]   / n * 100, 2) if n else 0.0,
            "stop_hit_rate_5d":     round(s["stop_hit"]     / n * 100, 2) if n else 0.0,
            "both_same_bar_rate_5d":round(s["both_same_bar"] / n * 100, 2) if n else 0.0,
            "avg_strategy_return_t1": round(s["sum_rt1"]  / n, 2) if n else 0.0,
            "avg_strategy_return_t3": round(s["sum_rt3"]  / n, 2) if n else 0.0,
            "avg_strategy_return_t5": round(s["sum_rt5"]  / n, 2) if n else 0.0,
            "avg_raw_return_t5":      round(s["sum_raw5"] / n, 2) if n else 0.0,
            "avg_mfe_5d": round(s["sum_mfe"] / n, 2) if n else 0.0,
            "avg_mae_5d": round(s["sum_mae"] / n, 2) if n else 0.0,
        })
    output.sort(key=lambda x: (x["avg_strategy_return_t5"], x["win_rate_t5"]), reverse=True)
    return output


def summarize_validation_overall(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    n = len(rows)
    if n == 0:
        return {k: 0.0 for k in ["count","win_rate_t1","win_rate_t3","win_rate_t5","target_hit_rate_5d","stop_hit_rate_5d","both_same_bar_rate_5d","avg_strategy_return_t1","avg_strategy_return_t3","avg_strategy_return_t5","avg_raw_return_t5","avg_mfe_5d","avg_mae_5d"]} | {"count": 0}

    win_t1       = sum(1 for x in rows if x.get("win_t1"))
    win_t3       = sum(1 for x in rows if x.get("win_t3"))
    win_t5       = sum(1 for x in rows if x.get("win_t5"))
    target_hit   = sum(1 for x in rows if x.get("target_hit"))
    stop_hit     = sum(1 for x in rows if x.get("stop_hit"))
    # ✅ fix 5: overall 補上 both_same_bar 統計
    both_same_bar = sum(1 for x in rows if safe_str(x.get("first_hit")) == "both_same_bar")

    return {
        "count": n,
        "win_rate_t1": round(win_t1 / n * 100, 2),
        "win_rate_t3": round(win_t3 / n * 100, 2),
        "win_rate_t5": round(win_t5 / n * 100, 2),
        "target_hit_rate_5d":    round(target_hit    / n * 100, 2),
        "stop_hit_rate_5d":      round(stop_hit      / n * 100, 2),
        "both_same_bar_rate_5d": round(both_same_bar / n * 100, 2),
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
            try:
                results_map[label] = future.result()
            except Exception as e:
                errors.append(f"{label} 失敗: {e}")
                logger.warning(f"[snapshot] {label} 失敗: {e}")
    for label in ["上市","上櫃"]:
        if label in results_map:
            all_stocks.extend(results_map[label])
    stocks = merge_stock_lists(all_stocks)
    if not stocks:
        raise Exception("；".join(errors) if errors else "目前無法取得任何市場資料")
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
        if c in counts:
            counts[c] += 1
    return [{"key": k, "label": k, "count": counts[k]} for k in order]


def filter_stocks(stocks: List[Dict[str, Any]], market: str = "all", category: str = "all", q: str = "", price_min: float = 0.0, price_max: float = 0.0) -> List[Dict[str, Any]]:
    result = stocks
    ml = safe_str(market).lower()
    if ml in ("all",""):         result = [s for s in result if is_main_board_stock(s)]
    elif ml in ("tse","上市"):   result = [s for s in result if s.get("market") == "上市"]
    elif ml in ("otc","上櫃"):   result = [s for s in result if s.get("market") == "上櫃"]
    else:                         result = [s for s in result if is_main_board_stock(s)]
    if category != "all":
        result = [s for s in result if s.get("category") == category]
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
    # ✅ fix 1: cache 命中時不再呼叫 save_recommendation_snapshot（避免每次請求都觸發 I/O）
    if (_RECS_CACHE["recommendations"] is not None and _RECS_CACHE["fetched_at"] is not None
            and (now - _RECS_CACHE["fetched_at"]).total_seconds() < RECS_CACHE_SECONDS):
        return _RECS_CACHE["recommendations"]

    candidates = [s for s in stocks if is_main_board_stock(s) and safe_float(s.get("price")) > 0 and safe_int(s.get("volume")) > 0]
    candidates.sort(key=lambda x: (x.get("recommendation_score", 0), x.get("volume", 0), abs(x.get("change_percent", 0))), reverse=True)
    top_items = candidates[:top_n]

    result_map: Dict[str, Dict[str, Any]] = {}
    with ThreadPoolExecutor(max_workers=5) as executor:
        future_to_symbol = {executor.submit(build_historical_analysis_for_stock, stock): stock["symbol"] for stock in top_items}
        for future in as_completed(future_to_symbol):
            symbol = future_to_symbol[future]
            try:
                result_map[symbol] = future.result()
            except Exception as e:
                logger.warning(f"[recommendations] {symbol} 歷史分析失敗: {e}")
                original = next((s for s in top_items if s["symbol"] == symbol), None)
                if original:
                    result_map[symbol] = original

    recs = [result_map[s["symbol"]] for s in top_items if s["symbol"] in result_map]

    # ✅ fix 1: 只在「重新生成推薦」時才寫入 snapshot
    save_recommendation_snapshot(recs)

    _RECS_CACHE["recommendations"] = recs
    _RECS_CACHE["fetched_at"]      = now
    return recs


def find_focused_stock(filtered: List[Dict[str, Any]], q: str) -> Optional[Dict[str, Any]]:
    qq = safe_str(q).lower()
    if not qq:
        return None
    exact_symbol = [s for s in filtered if safe_str(s.get("symbol")).lower() == qq]
    if len(exact_symbol) == 1: return exact_symbol[0]
    exact_name = [s for s in filtered if safe_str(s.get("name")).lower() == qq]
    if len(exact_name) == 1:   return exact_name[0]
    if len(filtered) == 1:     return filtered[0]
    return None


def clean_stock_output(s: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "market": s.get("market",""), "symbol": s.get("symbol",""), "name": s.get("name",""),
        "price": s.get("price",0), "change": s.get("change",0), "change_percent": s.get("change_percent",0),
        "volume": s.get("volume",0), "score": s.get("score",0), "recommendation_score": s.get("recommendation_score",0),
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
def validation_details(
    lookback_days: int = Query(180, ge=5, le=365),
    holding_days:  int = Query(5, ge=1, le=20),
):
    try:
        # ✅ fix 6: 共用 cache，不重複計算
        rows = get_cached_validation_rows(lookback_days=lookback_days, holding_days=holding_days)
        return {"success": True, "lookback_days": lookback_days, "holding_days": holding_days, "count": len(rows), "items": rows}
    except Exception as e:
        return {"success": False, "error": str(e), "trace": traceback.format_exc()}


@app.get("/validation/summary")
def validation_summary(
    lookback_days: int = Query(180, ge=5, le=365),
    holding_days:  int = Query(5, ge=1, le=20),
):
    try:
        # ✅ fix 6: 共用 cache，不重複計算
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
