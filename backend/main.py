from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import requests
from datetime import datetime
from zoneinfo import ZoneInfo

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

TAIPEI_TZ = ZoneInfo("Asia/Taipei")


def tw_now():
    return datetime.now(TAIPEI_TZ)


def today_ymd():
    return tw_now().strftime("%Y%m%d")


def today_roc():
    now = tw_now()
    return f"{now.year - 1911}/{now.month:02d}/{now.day:02d}"


def safe_float(v, default=0.0):
    try:
        if v is None:
            return default
        s = str(v).replace(",", "").strip()
        if s in ["", "-", "--", "---", "null", "None"]:
            return default
        return float(s)
    except:
        return default


def safe_int(v, default=0):
    try:
        if v is None:
            return default
        s = str(v).replace(",", "").strip()
        if s in ["", "-", "--", "---", "null", "None"]:
            return default
        return int(float(s))
    except:
        return default


def calc_plan(price, change_percent, volume):
    score = 50

    if change_percent > 0:
        score += min(change_percent * 8, 20)

    if volume > 3000000:
        score += 15
    elif volume > 1000000:
        score += 10
    elif volume > 300000:
        score += 5

    score = round(min(score, 99), 1)

    if score >= 80:
        signal = "偏多"
        target_ratio = 1.06
        stop_ratio = 0.97
    elif score >= 65:
        signal = "中性偏多"
        target_ratio = 1.04
        stop_ratio = 0.975
    elif score >= 50:
        signal = "中性"
        target_ratio = 1.03
        stop_ratio = 0.98
    else:
        signal = "保守"
        target_ratio = 1.02
        stop_ratio = 0.985

    entry_low = round(price * 0.99, 2)
    entry_high = round(price * 1.01, 2)
    target_price = round(price * target_ratio, 2)
    stop_loss = round(price * stop_ratio, 2)

    return {
        "score": score,
        "signal": signal,
        "entry_price": f"{entry_low} ~ {entry_high}",
        "target_price": f"{target_price}",
        "stop_loss": f"{stop_loss}",
    }


def normalize_stock(symbol, name, price, change, volume):
    if price <= 0:
        return None

    change_percent = round((change / price) * 100, 2) if price != 0 else 0.0
    plan = calc_plan(price, change_percent, volume)

    return {
        "symbol": str(symbol).strip(),
        "name": str(name).strip(),
        "price": round(price, 2),
        "change": round(change, 2),
        "change_percent": change_percent,
        "volume": int(volume),
        "score": plan["score"],
        "signal": plan["signal"],
        "entry_price": plan["entry_price"],
        "target_price": plan["target_price"],
        "stop_loss": plan["stop_loss"],
    }


def market_status():
    now = tw_now()
    hhmm = now.hour * 100 + now.minute

    # 台股一般盤約 09:00 ~ 13:30
    if now.weekday() >= 5:
        return "休市"

    if 900 <= hhmm <= 1330:
        return "盤中（準即時）"
    return "收盤"


def fetch_twse_realtime():
    url = "https://mis.twse.com.tw/stock/api/getStockInfo.jsp?ex_ch=tse_t00.tw|otc_o00.tw&json=1&delay=0"
    res = requests.get(url, timeout=15)
    data = res.json()

    stocks = []
    msg_array = data.get("msgArray", [])

    for s in msg_array:
        symbol = s.get("c", "")
        name = s.get("n", "")
        price = safe_float(s.get("z", 0))
        if price <= 0:
            price = safe_float(s.get("y", 0))

        prev_close = safe_float(s.get("y", 0))
        volume = safe_int(s.get("v", 0)) or safe_int(s.get("tv", 0))

        change = 0.0
        if price > 0 and prev_close > 0:
            change = round(price - prev_close, 2)

        item = normalize_stock(symbol, name, price, change, volume)
        if item:
            stocks.append(item)

    return {
        "source": "TWSE MIS",
        "source_date": today_ymd(),
        "stocks": stocks,
    }


def fetch_twse_close_today():
    date_str = today_ymd()
    url = f"https://www.twse.com.tw/exchangeReport/MI_INDEX?response=json&date={date_str}&type=ALLBUT0999"
    res = requests.get(url, timeout=20)
    data = res.json()

    tables = data.get("tables", [])
    stocks = []

    for table in tables:
        title = table.get("title", "")
        fields = table.get("fields", [])
        rows = table.get("data", [])

        if "證券代號" in fields and "收盤價" in fields:
            idx_code = fields.index("證券代號")
            idx_name = fields.index("證券名稱")
            idx_volume = fields.index("成交股數") if "成交股數" in fields else -1
            idx_close = fields.index("收盤價")
            idx_change = fields.index("漲跌價差") if "漲跌價差" in fields else -1

            for row in rows:
                try:
                    symbol = row[idx_code]
                    name = row[idx_name]
                    price = safe_float(row[idx_close], 0)
                    change = safe_float(row[idx_change], 0) if idx_change >= 0 else 0
                    volume = safe_int(row[idx_volume], 0) if idx_volume >= 0 else 0

                    item = normalize_stock(symbol, name, price, change, volume)
                    if item:
                        stocks.append(item)
                except:
                    continue

    stat = data.get("stat", "")
    return {
        "ok": len(stocks) > 0 and ("很抱歉" not in stat),
        "source": "TWSE MI_INDEX",
        "source_date": date_str,
        "stocks": stocks,
        "stat": stat,
    }


def fetch_tpex_close_today():
    # 這個 openapi 通常會提供當日上櫃報價
    url = "https://www.tpex.org.tw/openapi/v1/tpex_mainboard_quotes"
    res = requests.get(url, timeout=20)
    rows = res.json()

    stocks = []
    detected_date = ""

    for row in rows:
        symbol = row.get("SecuritiesCompanyCode", "") or row.get("股票代號", "")
        name = row.get("CompanyName", "") or row.get("名稱", "")
        price = safe_float(row.get("Close", 0) or row.get("收盤", 0))
        change = safe_float(row.get("Change", 0) or row.get("漲跌", 0))
        volume = safe_int(row.get("TradingShares", 0) or row.get("成交股數", 0))
        detected_date = row.get("Date", detected_date) or row.get("資料日期", detected_date)

        item = normalize_stock(symbol, name, price, change, volume)
        if item:
            stocks.append(item)

    return {
        "ok": len(stocks) > 0,
        "source": "TPEX OpenAPI",
        "source_date": detected_date or today_ymd(),
        "stocks": stocks,
    }


def fetch_close_data_today():
    twse = fetch_twse_close_today()
    tpex = fetch_tpex_close_today()

    stocks = []
    if twse.get("stocks"):
        stocks.extend(twse["stocks"])
    if tpex.get("stocks"):
        stocks.extend(tpex["stocks"])

    return {
        "ok": len(stocks) > 0,
        "source": "收盤資料",
        "source_date": today_ymd(),
        "stocks": stocks,
        "twse_source": twse.get("source"),
        "tpex_source": tpex.get("source"),
    }


@app.get("/")
def root():
    return {"message": "TW Stock backend running"}


@app.get("/stocks")
def get_stocks():
    now = tw_now()
    status = market_status()
    hhmm = now.hour * 100 + now.minute

    try:
        # 盤中抓準即時
        if status == "盤中（準即時）":
            realtime = fetch_twse_realtime()
            stocks = realtime["stocks"]

            stocks.sort(key=lambda x: x["score"], reverse=True)

            return {
                "success": True,
                "market_status": status,
                "data_date": realtime["source_date"],
                "last_update": now.strftime("%Y/%m/%d %H:%M:%S"),
                "total": len(stocks),
                "stocks": stocks,
                "source": realtime["source"],
            }

        # 收盤後抓當日收盤資料
        close_data = fetch_close_data_today()
        stocks = close_data["stocks"]

        # 如果收盤資料抓不到，最後才 fallback 準即時，避免整頁空白
        if not stocks:
            realtime = fetch_twse_realtime()
            stocks = realtime["stocks"]
            source = f"{realtime['source']}（fallback）"
            data_date = realtime["source_date"]
        else:
            source = close_data["source"]
            data_date = close_data["source_date"]

        stocks.sort(key=lambda x: x["score"], reverse=True)

        return {
            "success": True,
            "market_status": status,
            "data_date": data_date,
            "last_update": now.strftime("%Y/%m/%d %H:%M:%S"),
            "total": len(stocks),
            "stocks": stocks,
            "source": source,
        }

    except Exception as e:
        return {
            "success": False,
            "market_status": status,
            "data_date": today_ymd(),
            "last_update": now.strftime("%Y/%m/%d %H:%M:%S"),
            "total": 0,
            "stocks": [],
            "source": "error",
            "error": str(e),
        }
