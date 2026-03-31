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
    intraday_range = max(high_price - low_price, 0.0)
    amplitude_pct = (intraday_range / previous_close * 100) if previous_close > 0 else 0.0

    close_position = 0.5
    if high_price > low_price:
        close_position = (price - low_price) / (high_price - low_price)
        close_position = max(0.0, min(close_position, 1.0))

    close_near_high = close_position >= 0.85
    close_high = close_position >= 0.68
    close_mid = 0.35 < close_position < 0.68
    close_low = close_position <= 0.35
    close_near_low = close_position <= 0.18

    gap_up = open_price > previous_close > 0
    gap_down = open_price > 0 and previous_close > 0 and open_price < previous_close

    heavy_volume = volume >= 3000
    very_heavy_volume = volume >= 10000
    extreme_volume = volume >= 30000

    # 1. 強勢主升
    if change_percent >= 6 and very_heavy_volume and close_near_high:
        return {
            "signal": "強勢主升",
            "reason": (
                "該股今日屬於明確的強勢主升型態，漲幅擴大同時伴隨大量成交，且收盤貼近當日高點，"
                "代表盤中追價買盤積極，多方對價格的掌控力相當強。"
                "從量價結構來看，這不是單純的反彈，而較像資金集中後的趨勢推升，"
                "表示市場對後續表現具備延續性預期。"
                "若後續能守住今日強勢區間且量能未明顯失控，短線仍可偏多看待，"
                "但因股價已進入急漲段，操作上不宜過度追價，較適合等拉回再找承接點。"
            ),
        }

    # 2. 放量突破
    if change_percent >= 4 and heavy_volume and close_near_high:
        return {
            "signal": "放量突破",
            "reason": (
                "股價今日出現帶量上攻，且收盤穩守高檔，顯示突破並非虛漲，而是有實質買盤推動的價格重估。"
                "這類型態通常代表前波整理壓力已有被消化的跡象，市場資金開始明確表態站在多方一側。"
                "若後續能持續守在突破區上方，代表支撐開始轉強，短線有機會延續攻勢；"
                "但若隔日迅速跌回突破區下方，則需提防假突破風險。"
            ),
        }

    # 3. 多方控盤
    if change_percent >= 2 and gap_up and close_high:
        return {
            "signal": "多方控盤",
            "reason": (
                "個股今日以偏強方式開出後，盤中價格重心持續墊高，且收盤仍位於日內相對高檔，"
                "反映多方在盤中節奏掌握上明顯占優。"
                "這代表市場對該股短線預期偏正向，買盤不僅有追價意願，也願意在震盪過程中持續承接。"
                "若後續量能維持在健康水位，且未跌破今日主要支撐區，技術面仍偏多解讀。"
            ),
        }

    # 4. 趨勢續強
    if change_percent >= 1.5 and heavy_volume and close_high and amplitude_pct <= 5:
        return {
            "signal": "趨勢續強",
            "reason": (
                "股價延續原有偏多結構，盤中雖有波動，但整體重心仍維持上移，且量能未明顯失真，"
                "顯示市場對該股仍具備穩定承接力。"
                "此類型通常不是剛起漲，而是趨勢股進入續強階段，操作上重點在於是否能守住短線支撐。"
                "若後續未出現爆量長黑或高檔轉弱訊號，短線仍偏向多方優勢。"
            ),
        }

    # 5. 穩健走高
    if change_percent > 1 and amplitude_pct <= 4 and close_high:
        return {
            "signal": "穩健走高",
            "reason": (
                "個股今日屬於穩步墊高格局，雖非急攻型走勢，但收盤仍能守在相對高位，"
                "顯示買盤承接結構穩定，盤勢偏向健康上行。"
                "這類個股往往具備較佳的趨勢延續條件，若接下來量能逐步增溫，"
                "有機會由溫和走強轉入更明確的攻擊段。"
            ),
        }

    # 6. 高檔換手
    if change_percent >= 0 and amplitude_pct > 4 and heavy_volume and close_high:
        return {
            "signal": "高檔換手",
            "reason": (
                "股價今日盤中震盪明顯，但成交量活絡且收盤仍守住高檔區，"
                "顯示市場在相對高位進行換手，多方承接力尚未明顯失守。"
                "這類型常出現在強勢股整理過程，反映短線獲利了結賣壓與新進買盤正在重新平衡。"
                "若整理後能再次帶量上攻，後續仍有續強空間；反之若高檔失守，則需提防轉弱。"
            ),
        }

    # 7. 區間盤整
    if -1 <= change_percent <= 1 and amplitude_pct <= 3:
        return {
            "signal": "區間盤整",
            "reason": (
                "股價目前處於明顯整理格局，日內波動有限，量價表現相對均衡，"
                "顯示市場短線觀望氣氛偏濃，尚未形成明確攻擊或破位訊號。"
                "從分析角度來看，這類個股現階段重點不在追價，而在觀察後續是否能帶量突破區間上緣，"
                "或跌破區間下緣來確認下一步方向。"
            ),
        }

    # 8. 籌碼換手
    if -1 <= change_percent <= 1 and amplitude_pct > 4 and heavy_volume:
        return {
            "signal": "籌碼換手",
            "reason": (
                "個股今日盤中振幅偏大，但最終漲跌幅收斂，且成交量顯著放大，"
                "反映多空雙方對價格認知分歧，市場正處於明顯籌碼換手階段。"
                "這類走勢常見於波段方向即將重新選擇的前夕，後續需觀察股價究竟是向上突破整理壓力，"
                "還是轉弱跌破支撐，才能確認下一段趨勢方向。"
            ),
        }

    # 9. 拉回整理
    if change_percent <= -2 and change_percent > -5 and close_low and not very_heavy_volume:
        return {
            "signal": "拉回整理",
            "reason": (
                "股價今日出現明顯回檔，且收盤落在日內偏低區，顯示短線上方賣壓開始增加，"
                "買盤承接態度轉趨保守。"
                "不過目前量能尚未擴大到失控水位，因此較偏向漲多後的技術性整理，"
                "未必代表趨勢完全翻空。"
                "後續若能在關鍵支撐區附近止穩，仍有機會重新回到原本的上升節奏。"
            ),
        }

    # 10. 放量修正
    if change_percent <= -3 and heavy_volume:
        return {
            "signal": "放量修正",
            "reason": (
                "個股今日呈現放量下跌格局，顯示市場調節賣壓明顯升溫，"
                "價格重心同步下移，短線籌碼穩定度轉弱。"
                "這類型通常代表部分資金開始獲利了結，或市場對短線後勢轉趨保守。"
                "在未看到量縮止穩、下影承接或重新站回關鍵價位之前，操作上宜先保持審慎。"
            ),
        }

    # 11. 弱勢破位
    if change_percent <= -6 and very_heavy_volume and close_near_low:
        return {
            "signal": "弱勢破位",
            "reason": (
                "股價今日出現明顯破位下跌，跌幅擴大且伴隨大量成交，"
                "代表市場恐慌性調節或停損賣壓同步湧現，原有支撐結構已遭到實質破壞。"
                "收盤貼近低檔，說明空方掌控力仍強，短線尚未看到有效止跌訊號。"
                "在技術面未出現重新站穩支撐或量縮止穩前，現階段不宜過早進場承接。"
            ),
        }

    # 12. 爆量震盪
    if extreme_volume and amplitude_pct >= 5:
        return {
            "signal": "爆量震盪",
            "reason": (
                "個股今日成交量顯著放大，且盤中振幅明顯擴大，"
                "顯示市場高度聚焦，但多空對價格方向尚未取得一致共識。"
                "這類型常出現在波段轉折或重大題材反應階段，短線雖有機會快速表態，"
                "但同時也伴隨較高的追價風險。"
                "後續需密切觀察是量增價揚確認轉強，還是失守支撐轉入更深修正。"
            ),
        }

    # 13. 弱中透穩
    if change_percent < 0 and not heavy_volume and not close_near_low and amplitude_pct <= 4:
        return {
            "signal": "弱中透穩",
            "reason": (
                "股價今日雖小幅收低，但跌幅仍屬可控範圍，且未見明顯恐慌性賣壓，"
                "代表市場偏向觀望，而非全面轉空。"
                "這類型個股短線雖然動能不足，但若後續能在支撐區獲得穩定承接，"
                "仍有機會透過整理重新累積反彈條件。"
            ),
        }

    # 14. 小幅偏多
    if change_percent > 0:
        return {
            "signal": "小幅偏多",
            "reason": (
                "股價今日小幅收高，整體價格結構仍偏正向，"
                "顯示短線買盤尚具一定支撐力。"
                "雖然目前尚未形成強勢表態型態，但若後續能搭配量能放大、並持續守在相對高位，"
                "則有機會由溫和走強逐步轉入更明確的偏多架構。"
            ),
        }

    # 15. 小幅偏空
    if change_percent < 0:
        return {
            "signal": "小幅偏空",
            "reason": (
                "股價今日小幅收低，反映短線追價意願略顯不足，盤面資金態度偏向保守。"
                "現階段雖尚未形成明顯破壞性轉弱，但若後續無法在支撐區見到穩定承接，"
                "則需留意整理時間拉長，甚至再度測試前波低點的可能。"
            ),
        }

    return {
        "signal": "中性觀望",
        "reason": (
            "個股目前缺乏明確方向訊號，量價結構尚未形成具辨識度的趨勢優勢，"
            "短線仍應以觀察後續資金流向、成交量變化與關鍵價位表現為主。"
            "在未見有效突破或明顯轉弱之前，現階段評價先維持中性。"
        ),
    }


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
    }
    neutral_signals = {
        "區間盤整",
        "籌碼換手",
        "爆量震盪",
        "中性觀望",
    }

    # 偏多規劃
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

    # 偏空 / 弱勢規劃
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

    # 盤整 / 觀察型
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

    # 其餘保守處理
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
    recommendation_score = round(
        max(
            0.0,
            abs(change_percent) * 6 + liquidity_bonus + 2 - stability_penalty * 0.3,
        ),
        2,
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

    plan = build_trade_plan(
        price=price,
        change_percent=change_percent,
        high_price=high_price,
        low_price=low_price,
        signal=signal_info["signal"],
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
        "reason": signal_info["reason"],
        "entry_price": plan["entry_price"],
        "target_price": plan["target_price"],
        "stop_loss": plan["stop_loss"],
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
    }
    key = allowed.get(sort_by, "score")

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
        "reason": s.get("reason", ""),
        "entry_price": s.get("entry_price", ""),
        "target_price": s.get("target_price", ""),
        "stop_loss": s.get("stop_loss", ""),
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
        }