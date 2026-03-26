from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional, Union
import requests
import math

app = FastAPI(title="TW Stock Realtime Screener")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Accept": "application/json,text/plain,*/*",
}

TIMEOUT = 12


class ScanRequest(BaseModel):
    stocks: Union[str, List[str]]


def safe_float(value, default=0.0):
    if value is None:
        return default
    if isinstance(value, (int, float)):
        return float(value)

    s = str(value).strip().replace(",", "")
    if s in {"", "--", "---", "----", "X", "除權息", "N/A", "null", "None"}:
        return default

    # 去掉 + 號
    s = s.replace("+", "")

    # 有些漲跌欄位可能帶箭頭或中文
    s = s.replace("△", "").replace("▲", "").replace("▽", "-").replace("▼", "-")

    try:
        return float(s)
    except Exception:
        return default


def safe_int(value, default=0):
    return int(round(safe_float(value, default)))


def score_stock(price, change_percent, volume, open_price, high_price, low_price):
    score = 50

    # 漲跌幅
    if change_percent >= 6:
        score += 20
    elif change_percent >= 3:
        score += 14
    elif change_percent >= 1:
        score += 8
    elif change_percent <= -6:
        score -= 18
    elif change_percent <= -3:
        score -= 12
    elif change_percent <= -1:
        score -= 6

    # 成交量
    if volume >= 50000000:
        score += 16
    elif volume >= 10000000:
        score += 10
    elif volume >= 3000000:
        score += 6
    elif volume <= 50000:
        score -= 6

    # 日內位置
    if high_price > 0 and low_price > 0 and high_price != low_price:
        position = (price - low_price) / (high_price - low_price)
        if position >= 0.8:
            score += 8
        elif position <= 0.2:
            score -= 6

    # 開盤後表現
    if open_price > 0:
        intraday_change = ((price - open_price) / open_price) * 100
        if intraday_change >= 2:
            score += 8
        elif intraday_change <= -2:
            score -= 8

    return max(1, min(99, int(round(score))))


def build_signal(stock):
    score = stock["score"]
    change_percent = stock["change_percent"]
    price = stock["price"]

    if score >= 80:
        signal = "偏多"
        reason = "股價強勢、量能充足，短線偏多"
    elif score >= 65:
        signal = "中性偏多"
        reason = "走勢穩定，仍有續強機會"
    elif score >= 45:
        signal = "中性"
        reason = "多空力道接近，建議觀望"
    elif score >= 30:
        signal = "中性偏空"
        reason = "動能轉弱，操作宜保守"
    else:
        signal = "偏空"
        reason = "價格弱勢，短線風險較高"

    # 進出場區間
    if price > 0:
        entry_low = round(price * 0.985, 2)
        entry_high = round(price * 1.01, 2)
        target = round(price * (1.04 if score >= 65 else 1.025), 2)
        stop_loss = round(price * (0.965 if score >= 65 else 0.975), 2)
    else:
        entry_low, entry_high, target, stop_loss = 0, 0, 0, 0

    if change_percent >= 7:
        reason += "，但漲幅已大，不宜追高"
    elif change_percent <= -5:
        reason += "，跌勢明顯，需留意續弱"

    stock["signal"] = signal
    stock["reason"] = reason
    stock["entry_price"] = f"{entry_low} ~ {entry_high}"
    stock["target_price"] = str(target)
    stock["stop_loss"] = str(stop_loss)
    return stock


def normalize_twse_item(item):
    symbol = str(item.get("Code", "")).strip()
    name = str(item.get("Name", "")).strip()
    price = safe_float(item.get("ClosingPrice"))
    prev_close = price - safe_float(item.get("Change"))
    if prev_close <= 0:
        prev_close = price

    change_percent = 0.0
    if prev_close > 0 and price > 0:
        change_percent = round(((price - prev_close) / prev_close) * 100, 2)

    open_price = safe_float(item.get("OpeningPrice"))
    high_price = safe_float(item.get("HighestPrice"))
    low_price = safe_float(item.get("LowestPrice"))
    volume = safe_int(item.get("TradeVolume"))

    score = score_stock(price, change_percent, volume, open_price, high_price, low_price)

    return {
        "symbol": symbol,
        "name": name,
        "market": "上市",
        "price": round(price, 2),
        "change_percent": round(change_percent, 2),
        "volume": volume,
        "score": score,
        "prev_close": round(prev_close, 2),
        "open": round(open_price, 2),
        "high": round(high_price, 2),
        "low": round(low_price, 2),
        "last_update": "official",
    }


def normalize_tpex_item(item):
    symbol = str(
        item.get("SecuritiesCompanyCode")
        or item.get("Code")
        or item.get("股票代號")
        or ""
    ).strip()
    name = str(
        item.get("CompanyName")
        or item.get("Name")
        or item.get("股票名稱")
        or ""
    ).strip()

    price = safe_float(
        item.get("Close")
        or item.get("ClosingPrice")
        or item.get("收盤")
    )

    change_value = safe_float(
        item.get("Change")
        or item.get("漲跌")
        or item.get("UpDown")
    )

    prev_close = price - change_value
    if prev_close <= 0:
        prev_close = price

    change_percent = 0.0
    if prev_close > 0 and price > 0:
        change_percent = round(((price - prev_close) / prev_close) * 100, 2)

    open_price = safe_float(item.get("Open") or item.get("OpeningPrice") or item.get("開盤"))
    high_price = safe_float(item.get("High") or item.get("HighestPrice") or item.get("最高"))
    low_price = safe_float(item.get("Low") or item.get("LowestPrice") or item.get("最低"))
    volume = safe_int(
        item.get("TradeShares")
        or item.get("Volume")
        or item.get("成交股數")
        or item.get("成交量")
    )

    score = score_stock(price, change_percent, volume, open_price, high_price, low_price)

    return {
        "symbol": symbol,
        "name": name,
        "market": "上櫃",
        "price": round(price, 2),
        "change_percent": round(change_percent, 2),
        "volume": volume,
        "score": score,
        "prev_close": round(prev_close, 2),
        "open": round(open_price, 2),
        "high": round(high_price, 2),
        "low": round(low_price, 2),
        "last_update": "official",
    }


def fetch_twse_stocks():
    url = "https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL"
    resp = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
    resp.raise_for_status()
    data = resp.json()

    stocks = []
    for item in data:
        symbol = str(item.get("Code", "")).strip()
        if not symbol.isdigit():
            continue
        stock = normalize_twse_item(item)
        if stock["price"] <= 0:
            continue
        stocks.append(stock)

    return stocks


def fetch_tpex_stocks():
    urls = [
        "https://www.tpex.org.tw/openapi/v1/tpex_mainboard_quotes",
        "https://www.tpex.org.tw/openapi/v1/tpex_esb_quotes",
    ]

    stocks = []
    for url in urls:
        try:
            resp = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
            resp.raise_for_status()
            data = resp.json()

            for item in data:
                symbol = str(
                    item.get("SecuritiesCompanyCode")
                    or item.get("Code")
                    or item.get("股票代號")
                    or ""
                ).strip()

                if not symbol or not symbol.isdigit():
                    continue

                stock = normalize_tpex_item(item)
                if stock["price"] <= 0:
                    continue
                stocks.append(stock)
        except Exception:
            continue

    return stocks


def get_all_stocks():
    all_stocks = []

    try:
        all_stocks.extend(fetch_twse_stocks())
    except Exception:
        pass

    try:
        all_stocks.extend(fetch_tpex_stocks())
    except Exception:
        pass

    # 去重：相同代號保留第一筆
    dedup = {}
    for s in all_stocks:
        if s["symbol"] not in dedup:
            dedup[s["symbol"]] = s

    results = list(dedup.values())

    # 補上技術判斷欄位
    results = [build_signal(s) for s in results]

    # 依分數、成交量排序
    results.sort(key=lambda x: (x["score"], x["volume"], x["change_percent"]), reverse=True)
    return results


def in_bucket(price: float, bucket: str) -> bool:
    if bucket == "all":
        return True
    if bucket == "lt10":
        return price < 10
    if bucket == "10_20":
        return 10 <= price < 20
    if bucket == "20_50":
        return 20 <= price < 50
    if bucket == "50_100":
        return 50 <= price < 100
    if bucket == "100_200":
        return 100 <= price < 200
    if bucket == "200_500":
        return 200 <= price < 500
    if bucket == "500_1000":
        return 500 <= price < 1000
    if bucket == "gte1000":
        return price >= 1000
    return True


@app.get("/")
def root():
    return {"message": "backend running"}


@app.get("/health")
def health():
    return {"ok": True}


@app.get("/stocks")
def get_stocks(
    q: str = Query(default=""),
    bucket: str = Query(default="all"),
    limit: Optional[int] = Query(default=None),
):
    try:
        stocks = get_all_stocks()

        q = q.strip().lower()
        if q:
            stocks = [
                s for s in stocks
                if q in s["symbol"].lower() or q in s["name"].lower()
            ]

        stocks = [s for s in stocks if in_bucket(s["price"], bucket)]

        total = len(stocks)

        if limit and limit > 0:
            stocks = stocks[:limit]

        return {
            "success": True,
            "source": "TWSE + TPEx official",
            "count": total,
            "stocks": stocks,
        }
    except Exception as e:
        return {
            "success": False,
            "message": f"抓取股票資料失敗：{str(e)}",
            "count": 0,
            "stocks": [],
        }


@app.post("/scan")
def scan_stocks(payload: ScanRequest):
    try:
        stocks = get_all_stocks()

        if isinstance(payload.stocks, str):
            raw_items = payload.stocks.replace("，", ",").replace("\n", ",").split(",")
            target_symbols = [x.strip() for x in raw_items if x.strip()]
        else:
            target_symbols = [str(x).strip() for x in payload.stocks if str(x).strip()]

        target_set = set(target_symbols)
        result = [s for s in stocks if s["symbol"] in target_set or s["name"] in target_set]

        # 若使用者沒輸入，回傳推薦前10檔
        if not target_symbols:
            result = stocks[:10]

        return result
    except Exception as e:
        return [{"error": f"掃描失敗：{str(e)}"}]
