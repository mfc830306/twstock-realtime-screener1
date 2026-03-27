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

# 🔥 即時資料快取
live_cache = {}

# 🔥 收盤資料快取
close_cache = []

# =========================
# 工具
# =========================
def safe_float(v):
    try:
        if v in ["-", "--", ""]:
            return None
        return float(v)
    except:
        return None

def get_market_mode():
    now = time.localtime()
    minutes = now.tm_hour * 60 + now.tm_min
    if 9 * 60 <= minutes <= 13 * 60 + 30:
        return "live"
    return "close"

# =========================
# 🔥 MIS 即時資料（盤中）
# =========================
def update_live_data():
    global live_cache

    while True:
        try:
            url = "https://mis.twse.com.tw/stock/api/getStockInfo.jsp?ex_ch=tse_all"
            res = requests.get(url, timeout=10)
            data = res.json()

            if "msgArray" not in data:
                time.sleep(5)
                continue

            temp = {}

            for s in data["msgArray"]:
                price = safe_float(s.get("z"))  # 最新成交價
                if price is None:
                    continue

                code = s.get("c")
                name = s.get("n")

                y = safe_float(s.get("y"))  # 昨收
                change = round(price - y, 2) if y else 0
                change_percent = round((change / y) * 100, 2) if y else 0

                volume = int(s.get("v", 0))

                temp[code] = {
                    "symbol": code,
                    "name": name,
                    "price": price,
                    "change": change,
                    "change_percent": change_percent,
                    "volume": volume,
                    "score": abs(change_percent) * 10,
                    "entry_price": f"{round(price*0.99,2)} ~ {round(price*1.01,2)}",
                    "target_price": str(round(price*1.05,2)),
                    "stop_loss": str(round(price*0.97,2)),
                }

            live_cache = temp

            print("更新即時資料:", len(live_cache))

        except Exception as e:
            print("即時錯誤:", e)

        time.sleep(3)

# =========================
# 🔥 TWSE 收盤資料
# =========================
def update_close_data():
    global close_cache

    while True:
        try:
            url = "https://www.twse.com.tw/rwd/zh/afterTrading/STOCK_DAY_ALL?response=json"
            res = requests.get(url, timeout=20)
            data = res.json()

            if "data" not in data:
                time.sleep(60)
                continue

            temp = []

            for s in data["data"]:
                try:
                    code = s[0]
                    name = s[1]
                    price = float(s[7])
                    change = float(s[8].replace("+", "").replace("-", "")) if s[8] not in ["--"] else 0
                    volume = int(s[2].replace(",", ""))

                    change_percent = round((change / (price - change)) * 100, 2) if price else 0

                    temp.append({
                        "symbol": code,
                        "name": name,
                        "price": price,
                        "change": change,
                        "change_percent": change_percent,
                        "volume": volume,
                        "score": abs(change_percent) * 10,
                        "entry_price": f"{round(price*0.99,2)} ~ {round(price*1.01,2)}",
                        "target_price": str(round(price*1.05,2)),
                        "stop_loss": str(round(price*0.97,2)),
                    })
                except:
                    continue

            close_cache = temp
            print("更新收盤資料:", len(close_cache))

        except Exception as e:
            print("收盤錯誤:", e)

        time.sleep(600)

# =========================
# 🔥 API
# =========================
@app.get("/stocks")
def get_stocks(
    min_price: float = Query(0),
    max_price: float = Query(999999)
):
    mode = get_market_mode()

    data = live_cache if mode == "live" else close_cache

    result = [
        s for s in data.values() if mode == "live"
        else data
    ]

    filtered = [
        s for s in result
        if min_price <= s["price"] <= max_price
    ]

    return {
        "success": True,
        "mode": mode,
        "total": len(filtered),
        "stocks": sorted(filtered, key=lambda x: x["score"], reverse=True)
    }

# =========================
# 啟動背景任務
# =========================
threading.Thread(target=update_live_data, daemon=True).start()
threading.Thread(target=update_close_data, daemon=True).start()
