from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
import requests
import threading
import time

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

live_cache = {}
close_cache = []


def safe_float(v):
    try:
        if v in ["-", "--", "", None]:
            return None
        return float(str(v).replace(",", ""))
    except:
        return None


def safe_int(v):
    try:
        if v in ["-", "--", "", None]:
            return 0
        return int(float(str(v).replace(",", "")))
    except:
        return 0


def get_market_mode():
    now = time.localtime()
    minutes = now.tm_hour * 60 + now.tm_min
    if 9 * 60 <= minutes <= 13 * 60 + 30:
        return "live"
    return "close"


def build_stock_item(code, name, price, change, volume):
    yesterday = price - change if price is not None else 0
    change_percent = round((change / yesterday) * 100, 2) if yesterday else 0

    return {
        "symbol": code,
        "name": name,
        "price": round(price, 2),
        "change": round(change, 2),
        "change_percent": change_percent,
        "volume": volume,
        "score": round(abs(change_percent) * 10, 2),
        "entry_price": f"{round(price * 0.99, 2)} ~ {round(price * 1.01, 2)}",
        "target_price": str(round(price * 1.05, 2)),
        "stop_loss": str(round(price * 0.97, 2)),
    }


def update_live_data():
    global live_cache

    while True:
        try:
            url = "https://mis.twse.com.tw/stock/api/getStockInfo.jsp?ex_ch=tse_all"
            res = requests.get(url, timeout=10)
            data = res.json()

            msg_array = data.get("msgArray", [])
            temp = {}

            for s in msg_array:
                code = s.get("c")
                name = s.get("n")
                price = safe_float(s.get("z"))
                yesterday = safe_float(s.get("y"))
                volume = safe_int(s.get("v"))

                if not code or not name or price is None:
                    continue

                change = round(price - yesterday, 2) if yesterday is not None else 0.0

                temp[code] = build_stock_item(
                    code=code,
                    name=name,
                    price=price,
                    change=change,
                    volume=volume,
                )

            live_cache = temp
            print("更新即時資料:", len(live_cache))

        except Exception as e:
            print("即時錯誤:", e)

        time.sleep(3)


def update_close_data():
    global close_cache

    while True:
        try:
            url = "https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL"
            res = requests.get(url, timeout=20)
            raw_data = res.json()

            temp = []

            for s in raw_data:
                try:
                    code = str(s.get("Code", "")).strip()
                    name = str(s.get("Name", "")).strip()
                    price = safe_float(s.get("ClosingPrice"))
                    change = safe_float(s.get("Change"))
                    volume = safe_int(s.get("TradeVolume"))

                    if not code or not name or price is None:
                        continue

                    if change is None:
                        change = 0.0

                    temp.append(
                        build_stock_item(
                            code=code,
                            name=name,
                            price=price,
                            change=change,
                            volume=volume,
                        )
                    )
                except:
                    continue

            close_cache = temp
            print("更新收盤資料:", len(close_cache))

        except Exception as e:
            print("收盤錯誤:", e)

        time.sleep(600)


@app.get("/")
def root():
    return {"message": "backend running"}


@app.get("/stocks")
def get_stocks(
    min_price: float = Query(0),
    max_price: float = Query(999999),
):
    mode = get_market_mode()

    if mode == "live":
        result = list(live_cache.values())
    else:
        result = close_cache

    filtered = [
        s for s in result
        if s.get("price") is not None and min_price <= s["price"] <= max_price
    ]

    filtered.sort(key=lambda x: x["score"], reverse=True)

    return {
        "success": True,
        "mode": mode,
        "total": len(filtered),
        "stocks": filtered,
    }


threading.Thread(target=update_live_data, daemon=True).start()
threading.Thread(target=update_close_data, daemon=True).start()
