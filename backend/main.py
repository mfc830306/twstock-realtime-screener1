from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import requests
from datetime import datetime, timedelta, timezone

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

HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Accept": "application/json,text/plain,*/*",
}


def tw_now():
    return datetime.now(timezone(timedelta(hours=8)))


def normalize_text(value, default=""):
    if value is None:
        return default
    text = str(value).strip()
    return text if text else default


def to_float(value, default=0.0):
    try:
        if value is None:
            return default
        text = str(value).replace(",", "").replace("X", "").replace("--", "").strip()
        if text in ("", "-", "—", "----", "除權", "除息", "除權息"):
            return default
        return float(text)
    except Exception:
        return default


def to_int(value, default=0):
    try:
        if value is None:
            return default
        text = str(value).replace(",", "").replace("--", "").strip()
        if text in ("", "-", "—", "----"):
            return default
        return int(float(text))
    except Exception:
        return default


def get_first(row, keys, default=None):
    for key in keys:
        if key in row and row[key] not in (None, ""):
            return row[key]
    return default


def normalize_data_date(raw_date):
    if raw_date is None:
        return ""

    text = str(raw_date).strip().replace("/", "").replace("-", "")
    digits = "".join(ch for ch in text if ch.isdigit())

    # 西元 yyyyMMdd
    if len(digits) == 8:
        return digits

    # 民國 yyyMMdd -> 西元 yyyyMMdd
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


def calc_score(change_percent, volume, price):
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


def calc_signal(change_percent, volume):
    if change_percent >= 2 and volume >= 1000000:
        return "偏多"
    if change_percent <= -2 and volume >= 1000000:
        return "偏空"
    return "中性"


def calc_entry_price(price):
    low = round(price * 0.99, 2)
    high = round(price * 1.01, 2)
    return f"{low} ~ {high}"


def calc_target_price(price):
    return str(round(price * 1.06, 2))


def calc_stop_loss(price):
    return str(round(price * 0.97, 2))


def calc_reason(change_percent, volume, score, signal, price):
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
    market,
    symbol,
    name,
    price,
    change,
    volume,
    data_date="",
    open_price=0,
    high_price=0,
    low_price=0,
):
    if not symbol or not name or price <= 0:
        return None

    prev_close = round(price - change, 2)
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
        "data_date": data_date,
    }


def fetch_twse_data():
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

            stock = build_stock(
                market="上市",
                symbol=symbol,
                name=name,
                price=price,
                change=change,
                volume=volume,
                data_date=normalized_date,
                open_price=to_float(get_first(row, ["OpeningPrice", "開盤價"], 0)),
                high_price=to_float(get_first(row, ["HighestPrice", "最高價"], 0)),
                low_price=to_float(get_first(row, ["LowestPrice", "最低價"], 0)),
            )
            if stock:
                stocks.append(stock)
        except Exception:
            continue

    return stocks, detected_data_date


def fetch_tpex_data():
    res = requests.get(TPEX_DAILY_CLOSE_URL, headers=HEADERS, timeout=30)
    res.raise_for_status()
    data = res.json()

    if not isinstance(data, list):
        raise ValueError("TPEX 回傳格式異常")

    stocks = []
    detected_data_date = ""

    for row in data:
        try:
            symbol = normalize_text(
                get_first(row, ["SecuritiesCompanyCode", "股票代號", "代號", "code"], "")
            )
            name = normalize_text(
                get_first(row, ["CompanyName", "名稱", "股票名稱", "name"], "")
            )

            raw_date = get_first(row, ["Date", "日期", "資料日期", "date"], "")
            normalized_date = normalize_data_date(raw_date)
            if normalized_date and not detected_data_date:
                detected_data_date = normalized_date

            price = to_float(
                get_first(row, ["Close", "收盤", "收盤價", "ClosePrice"], 0)
            )
            change = to_float(
                get_first(row, ["Change", "漲跌", "漲跌價差", "PriceChange"], 0)
            )
            volume = to_int(
                get_first(row, ["TradeShares", "成交股數", "成交量", "Volume"], 0)
            )

            stock = build_stock(
                market="上櫃",
                symbol=symbol,
                name=name,
                price=price,
                change=change,
                volume=volume,
                data_date=normalized_date,
                open_price=to_float(get_first(row, ["Open", "開盤", "開盤價"], 0)),
                high_price=to_float(get_first(row, ["High", "最高", "最高價"], 0)),
                low_price=to_float(get_first(row, ["Low", "最低", "最低價"], 0)),
            )
            if stock:
                stocks.append(stock)
        except Exception:
            continue

    return stocks, detected_data_date


@app.get("/")
def root():
    return {"message": "TW Stock Realtime Screener backend running"}


@app.get("/stocks")
def get_stocks():
    fetch_time = tw_now()
    last_fetch_time = fetch_time.strftime("%Y/%m/%d %H:%M:%S")
    today_str = fetch_time.strftime("%Y%m%d")

    try:
        twse_stocks, twse_date = fetch_twse_data()
    except Exception as e:
        twse_stocks, twse_date = [], ""
        twse_error = str(e)
    else:
        twse_error = ""

    try:
        tpex_stocks, tpex_date = fetch_tpex_data()
    except Exception as e:
        tpex_stocks, tpex_date = [], ""
        tpex_error = str(e)
    else:
        tpex_error = ""

    stocks = twse_stocks + tpex_stocks

    stocks.sort(
        key=lambda x: (
            x.get("score", 0),
            x.get("change_percent", 0),
            x.get("volume", 0),
        ),
        reverse=True,
    )

    data_dates = [d for d in [twse_date, tpex_date] if d]
    final_data_date = max(data_dates) if data_dates else ""

    if final_data_date:
        market_status = "收盤" if final_data_date == today_str else f"非當日資料（{final_data_date}）"
    else:
        market_status = "資料日期未知"

    success = len(stocks) > 0
    message_parts = []
    if twse_error:
        message_parts.append(f"TWSE 讀取失敗: {twse_error}")
    if tpex_error:
        message_parts.append(f"TPEX 讀取失敗: {tpex_error}")

    return {
        "success": success,
        "market_status": market_status,
        "data_date": final_data_date,
        "last_fetch_time": last_fetch_time,
        "last_update": last_fetch_time,
        "source_summary": {
            "twse_count": len(twse_stocks),
            "tpex_count": len(tpex_stocks),
            "twse_data_date": twse_date,
            "tpex_data_date": tpex_date,
        },
        "message": "；".join(message_parts) if message_parts else "",
        "total": len(stocks),
        "stocks": stocks,
    }
