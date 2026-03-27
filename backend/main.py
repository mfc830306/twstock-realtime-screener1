from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import requests
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Tuple, Any

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

TWSE_DAY_ALL_URL = "https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL"
TPEX_DAILY_CLOSE_URL = "https://www.tpex.org.tw/openapi/v1/tpex_mainboard_daily_close_quotes?l=zh-tw"
TWSE_MIS_INDEX_URL = "https://mis.twse.com.tw/stock/index.jsp"
TWSE_MIS_API_URL = "https://mis.twse.com.tw/stock/api/getStockInfo.jsp"

HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Accept": "application/json,text/plain,*/*",
    "Referer": "https://mis.twse.com.tw/stock/index.jsp",
}


def tw_now() -> datetime:
    return datetime.now(timezone(timedelta(hours=8)))


def normalize_text(value: Any, default: str = "") -> str:
    if value is None:
        return default
    text = str(value).strip()
    return text if text else default


def to_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        text = str(value).replace(",", "").replace("X", "").replace("--", "").strip()
        if text in ("", "-", "—", "----", "除權", "除息", "除權息"):
            return default
        return float(text)
    except Exception:
        return default


def to_int(value: Any, default: int = 0) -> int:
    try:
        if value is None:
            return default
        text = str(value).replace(",", "").replace("--", "").strip()
        if text in ("", "-", "—", "----"):
            return default
        return int(float(text))
    except Exception:
        return default


def get_first(row: Dict[str, Any], keys: List[str], default=None):
    for key in keys:
        if key in row and row[key] not in (None, ""):
            return row[key]
    return default


def normalize_data_date(raw_date: Any) -> str:
    if raw_date is None:
        return ""

    text = str(raw_date).strip().replace("/", "").replace("-", "")
    digits = "".join(ch for ch in text if ch.isdigit())

    if len(digits) == 8:
        return digits

    if len(digits) == 7:
        try:
            roc_year = int(digits[:3])
            month = digits[3:5]
            day = digits[5:7]
            year = roc_year + 1911
            return f"{year}{month}{day}"
        except Exception:
            return ""

    return ""


def calc_score(change_percent: float, volume: int, price: float) -> int:
    score = 50

    if change_percent >= 6:
        score += 20
    elif change_percent >= 4:
        score += 16
    elif change_percent >= 2:
        score += 12
    elif change_percent >= 0:
        score += 6
    elif change_percent <= -4:
        score -= 8

    if volume >= 30000000:
        score += 18
    elif volume >= 10000000:
        score += 14
    elif volume >= 3000000:
        score += 10
    elif volume >= 1000000:
        score += 6

    if price >= 500:
        score += 5
    elif price >= 100:
        score += 4
    elif price >= 30:
        score += 3
    elif price >= 10:
        score += 2

    return max(1, min(99, round(score)))


def calc_signal(change_percent: float, volume: int) -> str:
    if change_percent >= 2 and volume >= 1000000:
        return "偏多"
    if change_percent <= -2 and volume >= 1000000:
        return "偏空"
    return "中性"


def calc_entry_price(price: float) -> str:
    low = round(price * 0.99, 2)
    high = round(price * 1.01, 2)
    return f"{low} ~ {high}"


def calc_target_price(price: float) -> str:
    return str(round(price * 1.06, 2))


def calc_stop_loss(price: float) -> str:
    return str(round(price * 0.97, 2))


def calc_reason(change_percent: float, volume: int, score: int, signal: str, price: float) -> str:
    if signal == "偏多":
        if change_percent >= 4 and volume >= 10000000:
            return "漲幅強勢、成交量明顯放大，短線多方動能強"
        elif change_percent >= 3 and volume >= 3000000:
            return "股價走強且量能配合，短線續強機率較高"
        elif change_percent >= 2:
            return "股價維持強勢，短線技術面偏多"
        elif score >= 85:
            return "綜合分數高，量價結構穩定，具續攻條件"
        else:
            return "走勢偏多，可觀察是否延續上攻"

    if signal == "偏空":
        if change_percent <= -4 and volume >= 10000000:
            return "跌幅擴大且量能放大，賣壓偏重"
        elif change_percent <= -2:
            return "股價轉弱，短線走勢偏空"
        else:
            return "技術面偏弱，建議保守觀察"

    if score >= 85:
        return "綜合分數高，量價表現穩定，可列入觀察"
    elif volume >= 3000000:
        return "成交量活絡，市場關注度提升"
    elif price >= 500:
        return "高價股波動較大，建議留意風險控管"
    else:
        return "目前走勢中性，建議等待更明確訊號"


def build_stock(
    market: str,
    symbol: str,
    name: str,
    price: float,
    change: float,
    volume: int,
    data_date: str = "",
    open_price: float = 0,
    high_price: float = 0,
    low_price: float = 0,
    prev_close_input: float = 0,
    update_time: str = "--",
) -> Dict[str, Any] | None:
    if not symbol or not name or price <= 0:
        return None

    prev_close = round(prev_close_input, 2) if prev_close_input > 0 else round(price - change, 2)
    change_percent = round((change / prev_close) * 100, 2) if prev_close > 0 else 0.0

    score = calc_score(change_percent, volume, price)
    signal = calc_signal(change_percent, volume)
    entry_price = calc_entry_price(price)
    target_price = calc_target_price(price)
    stop_loss = calc_stop_loss(price)
    reason = calc_reason(change_percent, volume, score, signal, price)

    return {
        "market": market,
        "symbol": symbol,
        "name": name,
        "price": round(price, 2),
        "change": round(change, 2),
        "change_percent": change_percent,
        "volume": volume,
        "score": score,
        "signal": signal,
        "entry_price": entry_price,
        "target_price": target_price,
        "stop_loss": stop_loss,
        "reason": reason,
        "prev_close": prev_close,
        "open": round(open_price, 2) if open_price > 0 else 0,
        "high": round(high_price, 2) if high_price > 0 else 0,
        "low": round(low_price, 2) if low_price > 0 else 0,
        "update_time": update_time,
        "data_date": data_date,
    }


def fetch_twse_day_data() -> Tuple[List[Dict[str, Any]], str]:
    res = requests.get(TWSE_DAY_ALL_URL, headers=HEADERS, timeout=30)
    res.raise_for_status()
    data = res.json()

    if not isinstance(data, list):
        raise ValueError("TWSE 回傳格式異常")

    stocks = []
    detected_data_date = ""

    for row in data:
        try:
            symbol = normalize_text(get_first(row, ["Code", "證券代號"], ""))
            name = normalize_text(get_first(row, ["Name", "證券名稱"], ""))

            raw_date = get_first(row, ["Date", "日期"], "")
            normalized_date = normalize_data_date(raw_date)
            if normalized_date and not detected_data_date:
                detected_data_date = normalized_date

            price = to_float(get_first(row, ["ClosingPrice", "收盤價"], 0))
            change = to_float(get_first(row, ["Change", "漲跌價差"], 0))
            volume = to_int(get_first(row, ["TradeVolume", "成交股數"], 0))
            open_price = to_float(get_first(row, ["OpeningPrice", "開盤價"], 0))
            high_price = to_float(get_first(row, ["HighestPrice", "最高價"], 0))
            low_price = to_float(get_first(row, ["LowestPrice", "最低價"], 0))

            stock = build_stock(
                market="上市",
                symbol=symbol,
                name=name,
                price=price,
                change=change,
                volume=volume,
                data_date=normalized_date,
                open_price=open_price,
                high_price=high_price,
                low_price=low_price,
            )
            if stock:
                stocks.append(stock)
        except Exception:
            continue

    return stocks, detected_data_date


def fetch_tpex_day_data() -> Tuple[List[Dict[str, Any]], str]:
    res = requests.get(TPEX_DAILY_CLOSE_URL, headers=HEADERS, timeout=30)
    res.raise_for_status()
    data = res.json()

    if not isinstance(data, list):
        raise ValueError("TPEX 回傳格式異常")

    stocks = []
    detected_data_date = ""

    for row in data:
        try:
            symbol = normalize_text(get_first(row, ["SecuritiesCompanyCode", "股票代號", "代號", "code"], ""))
            name = normalize_text(get_first(row, ["CompanyName", "名稱", "股票名稱", "name"], ""))

            raw_date = get_first(row, ["Date", "日期", "資料日期", "date"], "")
            normalized_date = normalize_data_date(raw_date)
            if normalized_date and not detected_data_date:
                detected_data_date = normalized_date

            price = to_float(get_first(row, ["Close", "收盤", "收盤價", "ClosePrice"], 0))
            change = to_float(get_first(row, ["Change", "漲跌", "漲跌價差", "PriceChange"], 0))
            volume = to_int(get_first(row, ["TradeShares", "成交股數", "成交量", "Volume"], 0))
            open_price = to_float(get_first(row, ["Open", "開盤", "開盤價"], 0))
            high_price = to_float(get_first(row, ["High", "最高", "最高價"], 0))
            low_price = to_float(get_first(row, ["Low", "最低", "最低價"], 0))

            stock = build_stock(
                market="上櫃",
                symbol=symbol,
                name=name,
                price=price,
                change=change,
                volume=volume,
                data_date=normalized_date,
                open_price=open_price,
                high_price=high_price,
                low_price=low_price,
            )
            if stock:
                stocks.append(stock)
        except Exception:
            continue

    return stocks, detected_data_date


def create_mis_session() -> requests.Session:
    session = requests.Session()
    session.headers.update(HEADERS)

    # 先打 MIS 首頁，讓後續 API 比較穩
    session.get(TWSE_MIS_INDEX_URL, timeout=20)
    return session


def chunk_list(items: List[str], size: int) -> List[List[str]]:
    return [items[i:i + size] for i in range(0, len(items), size)]


def parse_mis_price(item: Dict[str, Any], fallback_price: float) -> float:
    # z: 當盤成交價；若無則取當盤揭示資訊的最高有效買/賣或 fallback
    z = normalize_text(item.get("z", ""))
    if z and z not in ("-", "--", "—"):
        return to_float(z, fallback_price)

    # 若 z 無值，可用最近揭示價做次要備援，但仍盡量不亂估
    for key in ["b", "a"]:
        value = normalize_text(item.get(key, ""))
        if value:
            first = value.split("_")[0].strip()
            p = to_float(first, 0)
            if p > 0:
                return p

    return fallback_price


def parse_mis_volume(item: Dict[str, Any], fallback_volume: int) -> int:
    # v 為累積成交量，tv 為當筆成交量
    v = to_int(item.get("v"), 0)
    if v > 0:
        return v
    return fallback_volume


def fetch_mis_quotes(base_stocks: List[Dict[str, Any]]) -> Tuple[Dict[str, Dict[str, Any]], str]:
    """
    回傳:
    {
      "2330": {
        "price": 950.0,
        "open": 945.0,
        "high": 955.0,
        "low": 940.0,
        "volume": 12345678,
        "change": 10.0,
        "prev_close": 940.0,
        "update_time": "13:30:00"
      }
    }
    """
    quote_map: Dict[str, Dict[str, Any]] = {}
    latest_data_date = ""

    if not base_stocks:
        return quote_map, latest_data_date

    session = create_mis_session()

    ex_ch_list = []
    symbol_meta = {}

    for stock in base_stocks:
        symbol = stock["symbol"]
        market = stock.get("market", "")

        if market == "上市":
            ex_ch = f"tse_{symbol}.tw"
        elif market == "上櫃":
            ex_ch = f"otc_{symbol}.tw"
        else:
            continue

        ex_ch_list.append(ex_ch)
        symbol_meta[ex_ch] = symbol

    for batch in chunk_list(ex_ch_list, 50):
        params = {
            "ex_ch": "|".join(batch),
            "json": "1",
            "delay": "0",
            "_": str(int(datetime.now().timestamp() * 1000)),
        }

        res = session.get(TWSE_MIS_API_URL, params=params, timeout=25)
        res.raise_for_status()
        data = res.json()

        msg_array = data.get("msgArray") or []
        if not isinstance(msg_array, list):
            continue

        for item in msg_array:
            try:
                ex_ch = normalize_text(item.get("ex_ch", ""))
                symbol = symbol_meta.get(ex_ch) or normalize_text(item.get("c", ""))
                if not symbol:
                    continue

                raw_date = normalize_text(item.get("d", ""))
                normalized_date = normalize_data_date(raw_date)
                if normalized_date and normalized_date > latest_data_date:
                    latest_data_date = normalized_date

                # MIS 欄位：
                # z: 當盤成交價
                # o/h/l: 開高低
                # y: 昨收
                # v: 累積成交量
                base_price = 0.0
                price = parse_mis_price(item, base_price)
                prev_close = to_float(item.get("y"), 0)
                open_price = to_float(item.get("o"), 0)
                high_price = to_float(item.get("h"), 0)
                low_price = to_float(item.get("l"), 0)
                volume = parse_mis_volume(item, 0)
                update_time = normalize_text(item.get("t", "")) or normalize_text(item.get("tlong", "")) or "--"

                change = round(price - prev_close, 2) if price > 0 and prev_close > 0 else 0.0

                quote_map[symbol] = {
                    "price": price,
                    "open": open_price,
                    "high": high_price,
                    "low": low_price,
                    "volume": volume,
                    "change": change,
                    "prev_close": prev_close,
                    "update_time": update_time,
                    "data_date": normalized_date,
                }
            except Exception:
                continue

    return quote_map, latest_data_date


def merge_day_and_mis(day_stocks: List[Dict[str, Any]], mis_quotes: Dict[str, Dict[str, Any]], last_fetch_time: str) -> List[Dict[str, Any]]:
    merged = []

    for stock in day_stocks:
        symbol = stock["symbol"]
        mis = mis_quotes.get(symbol)

        if mis and mis.get("price", 0) > 0:
            price = mis["price"]
            prev_close = mis.get("prev_close", 0) or stock.get("prev_close", 0)
            change = mis.get("change", 0.0)
            volume = mis.get("volume", 0) or stock.get("volume", 0)
            open_price = mis.get("open", 0) or stock.get("open", 0)
            high_price = mis.get("high", 0) or stock.get("high", 0)
            low_price = mis.get("low", 0) or stock.get("low", 0)
            data_date = mis.get("data_date") or stock.get("data_date", "")
            update_time = mis.get("update_time") or last_fetch_time

            merged_stock = build_stock(
                market=stock.get("market", ""),
                symbol=stock["symbol"],
                name=stock["name"],
                price=price,
                change=change,
                volume=volume,
                data_date=data_date,
                open_price=open_price,
                high_price=high_price,
                low_price=low_price,
                prev_close_input=prev_close,
                update_time=update_time,
            )
            if merged_stock:
                merged.append(merged_stock)
        else:
            stock_copy = dict(stock)
            stock_copy["update_time"] = last_fetch_time
            merged.append(stock_copy)

    return merged


@app.get("/")
def root():
    return {"message": "TW Stock Realtime Screener backend running (MIS integrated)"}


@app.get("/stocks")
def get_stocks():
    fetch_time = tw_now()
    last_fetch_time = fetch_time.strftime("%Y/%m/%d %H:%M:%S")
    today_str = fetch_time.strftime("%Y%m%d")

    twse_error = ""
    tpex_error = ""
    mis_error = ""

    try:
        twse_stocks, twse_date = fetch_twse_day_data()
    except Exception as e:
        twse_stocks, twse_date = [], ""
        twse_error = str(e)

    try:
        tpex_stocks, tpex_date = fetch_tpex_day_data()
    except Exception as e:
        tpex_stocks, tpex_date = [], ""
        tpex_error = str(e)

    day_stocks = twse_stocks + tpex_stocks

    try:
        mis_quotes, mis_date = fetch_mis_quotes(day_stocks)
    except Exception as e:
        mis_quotes, mis_date = {}, ""
        mis_error = str(e)

    stocks = merge_day_and_mis(day_stocks, mis_quotes, last_fetch_time)

    stocks.sort(
        key=lambda x: (
            x.get("score", 0),
            x.get("change_percent", 0),
            x.get("volume", 0),
        ),
        reverse=True,
    )

    available_dates = [d for d in [mis_date, twse_date, tpex_date] if d]
    final_data_date = max(available_dates) if available_dates else ""

    if final_data_date:
        market_status = "當日資料" if final_data_date == today_str else f"非當日資料（{final_data_date}）"
    else:
        market_status = "資料日期未知"

    success = len(stocks) > 0
    message_parts = []
    if twse_error:
        message_parts.append(f"TWSE 讀取失敗: {twse_error}")
    if tpex_error:
        message_parts.append(f"TPEX 讀取失敗: {tpex_error}")
    if mis_error:
        message_parts.append(f"MIS 讀取失敗: {mis_error}")

    return {
        "success": success,
        "market_status": market_status,
        "data_date": final_data_date,
        "last_fetch_time": last_fetch_time,
        "last_update": last_fetch_time,
        "source_summary": {
            "twse_count": len(twse_stocks),
            "tpex_count": len(tpex_stocks),
            "mis_count": len(mis_quotes),
            "twse_data_date": twse_date,
            "tpex_data_date": tpex_date,
            "mis_data_date": mis_date,
        },
        "message": "；".join(message_parts) if message_parts else "",
        "total": len(stocks),
        "stocks": stocks,
    }
