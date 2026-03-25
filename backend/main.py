from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Any, Dict, List, Optional
import requests

app = FastAPI(title="TWSE Stock Backend")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

TWSE_URL = "https://www.twse.com.tw/exchangeReport/STOCK_DAY_ALL?response=json"

session = requests.Session()
session.headers.update(
    {
        "User-Agent": "Mozilla/5.0",
        "Accept": "application/json,text/plain,*/*",
        "Referer": "https://www.twse.com.tw/",
    }
)


class ScanRequest(BaseModel):
    stocks: str = ""


def to_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        s = str(value).replace(",", "").replace("--", "").strip()
        if s == "":
            return default
        return float(s)
    except Exception:
        return default


def to_int(value: Any, default: int = 0) -> int:
    try:
        if value is None:
            return default
        s = str(value).replace(",", "").replace("--", "").strip()
        if s == "":
            return default
        return int(float(s))
    except Exception:
        return default


def calc_score(change_percent: float, volume: int, price: float) -> int:
    score = 50

    if change_percent >= 7:
        score += 25
    elif change_percent >= 4:
        score += 18
    elif change_percent >= 2:
        score += 10
    elif change_percent >= 0:
        score += 5
    elif change_percent <= -5:
        score -= 15
    elif change_percent <= -2:
        score -= 8

    if volume >= 100000:
        score += 18
    elif volume >= 50000:
        score += 12
    elif volume >= 10000:
        score += 8
    elif volume >= 1000:
        score += 4

    if price <= 0:
        score -= 10

    return max(1, min(99, score))


def build_signal(score: int) -> str:
    if score >= 85:
        return "偏多"
    if score >= 70:
        return "中性偏多"
    if score >= 55:
        return "中性"
    if score >= 40:
        return "中性偏空"
    return "偏空"


def build_reason(score: int, change_percent: float, volume: int) -> str:
    reasons = []

    if change_percent >= 4:
        reasons.append("動能偏強")
    elif change_percent >= 1:
        reasons.append("股價表現穩定")
    elif change_percent <= -3:
        reasons.append("短線壓力較大")
    else:
        reasons.append("量價變化普通")

    if volume >= 50000:
        reasons.append("成交量活躍")
    elif volume >= 10000:
        reasons.append("量能尚可")
    else:
        reasons.append("量能一般")

    if score >= 85:
        reasons.append("短線表現相對有利")
    elif score >= 70:
        reasons.append("可持續觀察")
    elif score >= 55:
        reasons.append("暫以整理看待")
    else:
        reasons.append("宜保守應對")

    return "、".join(reasons)


def calc_trade_plan(price: float) -> Dict[str, str]:
    if price <= 0:
        return {
            "entry_price": "-",
            "target_price": "-",
            "stop_loss": "-",
        }

    entry_low = round(price * 0.99, 2)
    entry_high = round(price * 1.01, 2)
    target = round(price * 1.05, 2)
    stop_loss = round(price * 0.97, 2)

    return {
        "entry_price": f"{entry_low:.2f} ~ {entry_high:.2f}",
        "target_price": f"{target:.2f}",
        "stop_loss": f"{stop_loss:.2f}",
    }


def normalize_row(row: Any, fields: List[str]) -> Optional[Dict[str, Any]]:
    item = {}

    if isinstance(row, dict):
        item = row
    elif isinstance(row, list) and fields:
        item = {fields[i]: row[i] if i < len(row) else None for i in range(len(fields))}
    else:
        return None

    code = str(item.get("Code", "")).strip()
    name = str(item.get("Name", "")).strip()

    if not code or not name:
        return None

    # 僅保留證交所常見股票代號
    if not code.isdigit() or len(code) not in (4, 5):
        return None

    price = to_float(item.get("ClosingPrice"))
    volume = to_int(item.get("TradeVolume"))

    change_raw = str(item.get("Change", "")).replace("X", "").replace("+", "").strip()
    change_value = to_float(change_raw, 0.0)

    prev_close = price - change_value
    if prev_close > 0:
        change_percent = round((change_value / prev_close) * 100, 2)
    else:
        change_percent = 0.0

    score = calc_score(change_percent, volume, price)
    signal = build_signal(score)
    reason = build_reason(score, change_percent, volume)
    trade_plan = calc_trade_plan(price)

    return {
        "symbol": code,
        "name": name,
        "market": "上市",
        "price": price,
        "change_percent": change_percent,
        "volume": volume,
        "score": score,
        "signal": signal,
        "reason": reason,
        "entry_price": trade_plan["entry_price"],
        "target_price": trade_plan["target_price"],
        "stop_loss": trade_plan["stop_loss"],
    }


def fetch_all_twse() -> List[Dict[str, Any]]:
    resp = session.get(TWSE_URL, timeout=30)
    resp.raise_for_status()
    payload = resp.json()

    data = payload.get("data", [])
    fields = payload.get("fields", [])

    stocks: List[Dict[str, Any]] = []
    for row in data:
        stock = normalize_row(row, fields)
        if stock:
            stocks.append(stock)

    return stocks


def sort_stocks(stocks: List[Dict[str, Any]], sort_by: str, order: str) -> List[Dict[str, Any]]:
    reverse = order == "desc"
    valid_sort_fields = {"symbol", "name", "price", "change_percent", "volume", "score"}
    if sort_by not in valid_sort_fields:
        sort_by = "symbol"

    if sort_by in {"symbol", "name"}:
        stocks.sort(key=lambda x: str(x.get(sort_by, "")), reverse=reverse)
    else:
        stocks.sort(key=lambda x: float(x.get(sort_by, 0)), reverse=reverse)

    return stocks


@app.get("/")
def root():
    return {"message": "backend running"}


@app.get("/stocks")
def get_stocks():
    try:
        stocks = fetch_all_twse()
        return {
            "success": True,
            "source": "TWSE",
            "market": "上市",
            "total": len(stocks),
            "stocks": stocks,
        }
    except Exception as e:
        return {
            "success": False,
            "source": "TWSE",
            "market": "上市",
            "total": 0,
            "stocks": [],
            "error": str(e),
        }


@app.get("/api/stocks/all")
def get_all_stocks(
    q: str = Query("", description="搜尋股票代號或名稱"),
    min_price: float = Query(0, description="最低股價"),
    max_price: float = Query(999999, description="最高股價"),
    sort_by: str = Query("symbol", description="symbol|name|price|change_percent|volume|score"),
    order: str = Query("asc", description="asc|desc"),
):
    try:
        stocks = fetch_all_twse()

        keyword = q.strip().lower()
        if keyword:
            stocks = [
                s for s in stocks
                if keyword in s["symbol"].lower() or keyword in s["name"].lower()
            ]

        stocks = [s for s in stocks if min_price <= s["price"] <= max_price]
        stocks = sort_stocks(stocks, sort_by, order)

        return {
            "success": True,
            "source": "TWSE",
            "market": "上市",
            "total": len(stocks),
            "stocks": stocks,
        }

    except Exception as e:
        return {
            "success": False,
            "source": "TWSE",
            "market": "上市",
            "total": 0,
            "stocks": [],
            "error": str(e),
        }


@app.get("/api/stocks/top")
def get_top_stocks(limit: int = 10):
    try:
        stocks = fetch_all_twse()
        stocks.sort(
            key=lambda x: (x["score"], x["change_percent"], x["volume"]),
            reverse=True
        )

        return {
            "success": True,
            "source": "TWSE",
            "market": "上市",
            "total": len(stocks),
            "top": stocks[:limit],
        }
    except Exception as e:
        return {
            "success": False,
            "source": "TWSE",
            "market": "上市",
            "total": 0,
            "top": [],
            "error": str(e),
        }


@app.get("/api/stocks/price-buckets")
def get_price_buckets():
    try:
        stocks = fetch_all_twse()

        buckets = [
            {"key": "0-20", "label": "20元以下", "min": 0, "max": 20},
            {"key": "20-50", "label": "20~50元", "min": 20, "max": 50},
            {"key": "50-100", "label": "50~100元", "min": 50, "max": 100},
            {"key": "100-200", "label": "100~200元", "min": 100, "max": 200},
            {"key": "200-500", "label": "200~500元", "min": 200, "max": 500},
            {"key": "500-1000", "label": "500~1000元", "min": 500, "max": 1000},
            {"key": "1000+", "label": "1000元以上", "min": 1000, "max": 99999999},
        ]

        result = []
        for bucket in buckets:
            count = sum(
                1 for s in stocks
                if bucket["min"] <= s["price"] < bucket["max"]
            )
            result.append(
                {
                    "key": bucket["key"],
                    "label": bucket["label"],
                    "count": count,
                    "min": bucket["min"],
                    "max": bucket["max"],
                }
            )

        return {
            "success": True,
            "source": "TWSE",
            "market": "上市",
            "total": len(stocks),
            "buckets": result,
        }

    except Exception as e:
        return {
            "success": False,
            "source": "TWSE",
            "market": "上市",
            "total": 0,
            "buckets": [],
            "error": str(e),
        }


@app.post("/scan")
def scan_stocks(req: ScanRequest):
    """
    前端若原本是 POST /scan，可繼續用這支。
    req.stocks 可傳：
    - 空字串：回全部
    - "2330,2317,2454"：回指定股票
    """
    try:
        stocks = fetch_all_twse()

        raw_input = (req.stocks or "").strip()
        if raw_input:
            wanted = {x.strip() for x in raw_input.replace("\n", ",").split(",") if x.strip()}
            stocks = [s for s in stocks if s["symbol"] in wanted or s["name"] in wanted]

        stocks.sort(
            key=lambda x: (x["score"], x["change_percent"], x["volume"]),
            reverse=True
        )

        return stocks

    except Exception as e:
        return [{"error": str(e)}]
