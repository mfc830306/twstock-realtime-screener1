from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
import os
import base64
import time
from typing import Any, Dict, List, Optional

import requests
from fubon_neo.sdk import FubonSDK

try:
    from fubon_neo.fugle_marketdata.rest.base_rest import FugleAPIError
except Exception:
    FugleAPIError = Exception


app = FastAPI(title="TW Stock Fubon Backend FINAL", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ===== 全域 =====
sdk: Optional[FubonSDK] = None
login_accounts = None
reststock = None
cert_path = "/tmp/fubon_cert.p12"

snapshot_cache = {
    "TSE": {"ts": 0, "data": None},
    "OTC": {"ts": 0, "data": None},
}

name_cache = {"ts": 0, "data": {}}

CACHE_SECONDS = 15
NAME_CACHE_SECONDS = 60 * 60 * 6


# ===== 基本工具 =====
def env_required(name: str) -> str:
    val = os.getenv(name)
    if not val:
        raise RuntimeError(f"缺少環境變數: {name}")
    return val


def write_cert():
    b64 = env_required("FUBON_CERT_BASE64")
    with open(cert_path, "wb") as f:
        f.write(base64.b64decode(b64))


def safe_get(obj, key, default=None):
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def to_dict(obj):
    if isinstance(obj, dict):
        return obj
    if hasattr(obj, "__dict__"):
        return vars(obj)
    return obj


# ===== 富邦初始化 =====
def ensure_fubon():
    global sdk, login_accounts, reststock

    if sdk and reststock:
        return

    person_id = env_required("FUBON_PERSON_ID")
    password = env_required("FUBON_PASSWORD")
    cert_pwd = env_required("FUBON_CERT_PASSWORD")

    write_cert()

    sdk = FubonSDK()
    res = sdk.login(person_id, password, cert_path, cert_pwd)

    if not safe_get(res, "is_success", False):
        raise RuntimeError(safe_get(res, "message", "登入失敗"))

    login_accounts = safe_get(res, "data", None)

    sdk.init_realtime()
    reststock = sdk.marketdata.rest_client.stock


# ===== 股票名稱 =====
def fetch_twse():
    url = "https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL"
    res = requests.get(url, timeout=20).json()
    return {r["Code"]: r["Name"] for r in res if "Code" in r}


def fetch_tpex():
    url = "https://www.tpex.org.tw/openapi/v1/tpex_mainboard_daily_close_quotes"
    res = requests.get(url, timeout=20).json()
    return {r["SecuritiesCompanyCode"]: r["CompanyName"] for r in res if "SecuritiesCompanyCode" in r}


def get_name_map(force=False):
    now = time.time()
    if not force and name_cache["data"] and now - name_cache["ts"] < NAME_CACHE_SECONDS:
        return name_cache["data"]

    m = {}
    m.update(fetch_twse())
    m.update(fetch_tpex())

    name_cache["ts"] = now
    name_cache["data"] = m
    return m


def get_name(symbol, fallback=""):
    return get_name_map().get(symbol, fallback)


# ===== 格式化 =====
def normalize(item, market):
    symbol = str(safe_get(item, "symbol", ""))
    raw_name = str(safe_get(item, "name", ""))
    name = get_name(symbol, raw_name)

    price = safe_get(item, "lastPrice", 0) or 0
    change = safe_get(item, "change", 0) or 0
    pct = safe_get(item, "changePercent", 0) or 0

    total = safe_get(item, "total", {}) or {}
    vol = safe_get(total, "tradeVolume", 0) or 0

    return {
        "market": market,
        "symbol": symbol,
        "name": name,
        "price": price,
        "change": change,
        "change_percent": pct,
        "volume": vol,
        "score": round(abs(pct) * 10 + vol / 1_000_000, 2),
    }


# ===== snapshot =====
def fetch_snapshot(market, force=False):
    ensure_fubon()

    now = time.time()
    cache = snapshot_cache[market]

    if not force and cache["data"] and now - cache["ts"] < CACHE_SECONDS:
        return cache["data"]

    # 🔥 修正重點在這裡
    raw = reststock.snapshot.quotes(market=market, type="ALLBUT0999")

    data = to_dict(raw)

    snapshot_cache[market] = {"ts": now, "data": data}
    return data


# ===== API =====
@app.get("/")
def root():
    return {"msg": "Fubon backend running"}


@app.get("/test-fubon-login")
def login_test():
    ensure_fubon()
    return {"success": True}


@app.get("/fubon-quote/{symbol}")
def quote(symbol: str):
    ensure_fubon()
    data = to_dict(reststock.intraday.quote(symbol=symbol))

    data["name"] = get_name(symbol, data.get("name", ""))

    return {"success": True, "quote": data}


@app.get("/stocks")
def stocks(limit: int = 50):
    try:
        tse = fetch_snapshot("TSE")
        otc = fetch_snapshot("OTC")

        data = []

        for i in tse.get("data", []):
            data.append(normalize(i, "上市"))

        for i in otc.get("data", []):
            data.append(normalize(i, "上櫃"))

        data.sort(key=lambda x: x["change_percent"], reverse=True)

        return {
            "success": True,
            "total": len(data),
            "stocks": data[:limit],
        }

    except Exception as e:
        return {"success": False, "error": str(e)}
