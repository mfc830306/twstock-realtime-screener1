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
    if minutes < 9 * 60:
        return "開盤前"
    if 9 * 60 <= minutes <= 13 * 60 + 30:
        return "開盤"
    return "收盤"


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

    heavy_volume = volume >= 3000
    very_heavy_volume = volume >= 10000
    extreme_volume = volume >= 30000

    close_near_high = close_position >= 0.8
    close_mid_high = close_position >= 0.65
    close_near_low = close_position <= 0.25
    close_mid_low = close_position <= 0.35

    gap_up = open_price > previous_close > 0
    gap_down = open_price > 0 and previous_close > 0 and open_price < previous_close

    # 1. 強勢主升
    if change_percent >= 6 and very_heavy_volume and close_near_high:
        return {
            "signal": "強勢主升",
            "reason": (
                "個股今日呈現主升段加速型態，漲幅明顯擴大且成交量同步放大，"
                "收盤價貼近當日高點，代表盤中追價買盤積極，資金集中效果明確。"
                "從量價結構來看，多方不僅成功推升價格重心，亦有效吸收短線獲利了結賣壓，"
                "顯示趨勢延續性佳，屬於盤面具領漲特徵的強勢股。"
            ),
        }

    # 2. 放量突破
    if change_percent >= 4 and heavy_volume and close_near_high:
        return {
            "signal": "放量突破",
            "reason": (
                "股價今日出現明確突破走勢，價格推升同時伴隨量能擴增，"
                "顯示市場資金進場態度積極，且突破後收盤仍能穩守高檔。"
                "這代表上方賣壓已獲一定程度消化，多方掌控盤勢能力提升，"
                "若後續成交量維持健康水準，短線仍具續攻與挑戰波段高點的條件。"
            ),
        }

    # 3. 多方控盤
    if change_percent >= 2 and gap_up and close_mid_high:
        return {
            "signal": "多方控盤",
            "reason": (
                "個股今日開盤即展現偏強企圖，盤中價格重心持續墊高，"
                "收盤仍維持在相對高位，顯示多方對節奏掌控度佳。"
                "此類型走勢通常意味市場對後續表現預期偏正向，"
                "短線若能再配合量能放大，將有機會進一步強化上攻動能。"
            ),
        }

    # 4. 穩健走強
    if change_percent > 1 and amplitude_pct <= 4 and close_mid_high:
        return {
            "signal": "穩健走強",
            "reason": (
                "股價呈現穩步走高格局，雖非急漲型態，但日內波動控制得宜，"
                "價格重心持續上移，代表買盤承接結構穩定。"
                "這類型個股通常具備較佳的趨勢延續基礎，"
                "若後續量價配合持續改善，仍具中短線續強空間。"
            ),
        }

    # 5. 高檔換手
    if change_percent >= 0 and amplitude_pct > 4 and close_mid_high and heavy_volume:
        return {
            "signal": "高檔換手",
            "reason": (
                "個股盤中震盪幅度偏大，但成交量活絡且收盤仍守在相對高檔，"
                "反映高檔換手過程中，多方承接力道仍具一定優勢。"
                "此現象通常代表市場對該股關注度提升，"
                "若後續能完成震盪整理並再度放量上攻，走勢仍有再轉強的可能。"
            ),
        }

    # 6. 整理待發
    if -1 <= change_percent <= 1 and amplitude_pct <= 3:
        return {
            "signal": "整理待發",
            "reason": (
                "股價目前處於區間整理階段，日內波動有限，量價表現偏向均衡，"
                "顯示市場觀望氣氛較濃，尚未出現明確方向性表態。"
                "此類型個股重點在於後續是否能透過量能增溫與價格突破，"
                "進一步確認下一波趨勢發展。"
            ),
        }

    # 7. 籌碼換手
    if -1 <= change_percent <= 1 and amplitude_pct > 4 and heavy_volume:
        return {
            "signal": "籌碼換手",
            "reason": (
                "個股今日呈現高波動但漲跌幅收斂的型態，且成交量放大，"
                "顯示市場多空分歧加劇，籌碼進入明顯換手階段。"
                "這類走勢常出現在波段轉折或方向醞釀期，"
                "後續需觀察股價是向上突破整理區間，或轉弱跌破關鍵支撐。"
            ),
        }

    # 8. 拉回整理
    if change_percent <= -2 and change_percent > -5 and close_mid_low:
        return {
            "signal": "拉回整理",
            "reason": (
                "股價今日出現明顯拉回，且收盤落在日內相對低檔區，"
                "反映短線上方賣壓升溫，買盤承接意願相對保守。"
                "現階段走勢已由強攻轉入整理，"
                "後續若無法快速收復重要價位，股價可能延續震盪修正節奏。"
            ),
        }

    # 9. 放量修正
    if change_percent <= -3 and heavy_volume:
        return {
            "signal": "放量修正",
            "reason": (
                "個股今日呈現放量下跌走勢，顯示市場調節賣壓明顯升溫，"
                "價格重心同步下移，短線籌碼穩定度轉弱。"
                "此類型通常代表短期風險偏高，"
                "在未出現量縮止穩或有效支撐訊號前，宜保守看待。"
            ),
        }

    # 10. 弱勢破位
    if change_percent <= -6 and very_heavy_volume and close_near_low:
        return {
            "signal": "弱勢破位",
            "reason": (
                "股價今日出現明顯破位型下跌，跌幅擴大且伴隨大量成交，"
                "代表市場恐慌性調節或停損賣壓同步湧現。"
                "收盤貼近低檔顯示空方掌控力強，"
                "短線結構已明顯轉弱，在未出現止跌訊號前，應以風險控管為優先。"
            ),
        }

    # 11. 爆量震盪
    if extreme_volume and amplitude_pct >= 5:
        return {
            "signal": "爆量震盪",
            "reason": (
                "個股今日成交量明顯放大，且盤中振幅擴大，"
                "顯示市場高度聚焦，但多空對價格認知差異亦明顯提升。"
                "這通常代表波段方向即將重新選擇，"
                "後續應密切觀察是否由量增價揚確認轉強，或由失守支撐轉為偏弱整理。"
            ),
        }

    # 12. 小幅偏多
    if change_percent > 0:
        return {
            "signal": "小幅偏多",
            "reason": (
                "股價今日小幅收高，整體價格結構仍維持偏正向發展，"
                "顯示短線買盤仍具一定支撐力。"
                "雖然目前尚未達到強勢表態程度，"
                "但若後續可搭配量能放大與高檔續收，仍有機會進一步提升技術面評價。"
            ),
        }

    # 13. 小幅偏空
    if change_percent < 0:
        return {
            "signal": "小幅偏空",
            "reason": (
                "股價今日小幅收低，反映短線追價意願不足，"
                "盤面資金態度略趨保守。"
                "若後續無法在支撐區看到明確承接，"
                "則需留意整理時間拉長，甚至再度測試前波低點的可能。"
            ),
        }

    # 14. 中性觀望
    return {
        "signal": "中性觀望",
        "reason": (
            "個股目前缺乏明確方向訊號，量價結構尚未形成具辨識度的趨勢優勢，"
            "短線仍以觀察後續資金流向、量能變化與關鍵價位表現為主。"
            "在未見有效突破或轉弱之前，評價暫維持中性。"
        ),
    }


def build_trade_plan(
    price: float,
    change_percent: float,
    high_price: float,
    low_price: float,
) -> Dict[str, str]:
    if price <= 0:
        return {
            "entry_price": "",
            "target_price": "",
            "stop_loss": "",
        }

    swing = max(high_price - low_price, price * 0.02)
    entry_low = max(price - swing * 0.25, 0.01)
    entry_high = price

    if change_percent >= 5:
        target = price * 1.06
        stop = price * 0.96
    elif change_percent >= 0:
        target = price * 1.04
        stop = price * 0.97
    else:
        target = price * 1.03
        stop = price * 0.95

    return {
        "entry_price": f"{round(entry_low, 2)} ~ {round(entry_high, 2)}",
        "target_price": f"{round(target, 2)}",
        "stop_loss": f"{round(stop, 2)}",
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
