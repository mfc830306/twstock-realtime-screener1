from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from typing import List, Dict, Any
import requests
import time
import re

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

HEADERS = {"User-Agent": "Mozilla/5.0"}

CACHE = {
    "list": {"time": 0, "data": []},
    "price": {"time": 0, "data": {}},
}

CACHE_TIME = 60 * 60
PRICE_CACHE = 30


def safe_float(x):
    try:
        return float(str(x).replace(",", ""))
    except:
        return 0


def fetch_stock_list():
    now = time.time()
    if now - CACHE["list"]["time"] < CACHE_TIME:
        return CACHE["list"]["data"]

    url = "https://isin.twse.com.tw/isin/C_public.jsp?strMode=2"
    r = requests.get(url, headers=HEADERS)
    r.encoding = "big5"

    matches = re.findall(r'>(\d{4})　([^<]+)<', r.text)

    stocks = []
    for code, name in matches:
        if code.isdigit():
            stocks.append({"symbol": code, "name": name})

    CACHE["list"]["time"] = now
    CACHE["list"]["data"] = stocks
    return stocks


def fetch_prices():
    now = time.time()
    if now - CACHE["price"]["time"] < PRICE_CACHE:
        return CACHE["price"]["data"]

    url = "https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL"
    r = requests.get(url)
    data = r.json()

    result = {}
    for row in data:
        code = row.get("Code")
        price = safe_float(row.get("ClosingPrice"))
        change = safe_float(row.get("Change"))
        volume = safe_float(row.get("TradeVolume"))

        prev = price - change if price else 0
        change_percent = (change / prev * 100) if prev else 0

        result[code] = {
            "price": price,
            "change_percent": round(change_percent, 2),
            "volume": volume,
        }

    CACHE["price"]["time"] = now
    CACHE["price"]["data"] = result
    return result


@app.get("/")
def root():
    return {"message": "backend running"}


@app.get("/stocks")
def stocks():
    stock_list = fetch_stock_list()
    price_map = fetch_prices()

    result = []

    for s in stock_list:
        p = price_map.get(s["symbol"], {})
        result.append({
            "symbol": s["symbol"],
            "name": s["name"],
            "price": p.get("price", 0),
            "change_percent": p.get("change_percent", 0),
            "volume": p.get("volume", 0),
            "score": int((p.get("change_percent", 0) or 0) * 2 + 50),
        })

    return {"stocks": result}
