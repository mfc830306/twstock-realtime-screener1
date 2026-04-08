import requests
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from datetime import datetime, timedelta, timezone

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

TZ = timezone(timedelta(hours=8))

CACHE = {
    "data": None,
    "time": None
}
CACHE_SECONDS = 20


def get_twse():
    url = "https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL"
    res = requests.get(url, timeout=10)
    data = res.json()

    stocks = []
    for s in data:
        try:
            price = float(s["ClosingPrice"])
            change = float(s["Change"])
            volume = int(s["TradeVolume"])

            change_percent = (change / price) * 100 if price != 0 else 0

            stocks.append({
                "market": "上市",
                "symbol": s["Code"],
                "name": s["Name"],
                "price": price,
                "change": change,
                "change_percent": round(change_percent, 2),
                "volume": volume,
                "score": round(abs(change_percent) * volume / 1000, 2),
            })
        except:
            continue

    return stocks


def get_tpex():
    url = "https://www.tpex.org.tw/openapi/v1/tpex_mainboard_quotes"
    res = requests.get(url, timeout=10)
    data = res.json()

    stocks = []
    for s in data:
        try:
            price = float(s["Close"])
            change = float(s["Change"])
            volume = int(s["Volume"])

            change_percent = (change / price) * 100 if price != 0 else 0

            stocks.append({
                "market": "上櫃",
                "symbol": s["SecuritiesCompanyCode"],
                "name": s["CompanyName"],
                "price": price,
                "change": change,
                "change_percent": round(change_percent, 2),
                "volume": volume,
                "score": round(abs(change_percent) * volume / 1000, 2),
            })
        except:
            continue

    return stocks


@app.get("/stocks")
def get_stocks():
    now = datetime.now(TZ)

    if CACHE["data"] and CACHE["time"]:
        if (now - CACHE["time"]).seconds < CACHE_SECONDS:
            return CACHE["data"]

    try:
        twse = get_twse()
        tpex = get_tpex()

        all_stocks = twse + tpex

        # 🔥 推薦（依 score）
        recommend = sorted(all_stocks, key=lambda x: x["score"], reverse=True)[:10]

        result = {
            "success": True,
            "total": len(all_stocks),
            "stocks": all_stocks,
            "recommend": recommend,
            "update_time": now.strftime("%Y-%m-%d %H:%M:%S")
        }

        CACHE["data"] = result
        CACHE["time"] = now

        return result

    except Exception as e:
        return {"success": False, "error": str(e)}
