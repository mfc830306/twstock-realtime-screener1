from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional
import csv
import os
import statistics
import twstock

app = FastAPI(title="TW Stock Realtime Screener B")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

CSV_FILE = "tw_stock_listed_otc_database.csv"


class ScanRequest(BaseModel):
    stocks: List[str] = Field(default_factory=list)


def load_stock_database() -> Dict[str, str]:
    mapping: Dict[str, str] = {}

    if not os.path.exists(CSV_FILE):
        return mapping

    with open(CSV_FILE, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            symbol = str(
                row.get("symbol")
                or row.get("code")
                or row.get("股票代號")
                or row.get("代號")
                or ""
            ).strip()
            name = str(
                row.get("name")
                or row.get("股票名稱")
                or row.get("名稱")
                or ""
            ).strip()

            if symbol:
                mapping[symbol] = name or symbol

    return mapping


STOCK_NAME_MAP = load_stock_database()


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value in [None, "", "-", "--"]:
            return default
        return float(str(value).replace(",", ""))
    except Exception:
        return default


def get_stock_name(symbol: str) -> str:
    if symbol in STOCK_NAME_MAP:
        return STOCK_NAME_MAP[symbol]

    try:
        if symbol in twstock.codes:
            return twstock.codes[symbol].name
    except Exception:
        pass

    return symbol


def moving_average(values: List[float], period: int) -> Optional[float]:
    if len(values) < period:
        return None
    return round(sum(values[-period:]) / period, 2)


def get_realtime_price_and_volume(symbol: str) -> tuple[Optional[float], float, float]:
    """
    回傳:
    price, volume, change_percent
    """
    price = None
    volume = 0.0
    change_percent = 0.0

    try:
        rt = twstock.realtime.get(symbol)
        if rt and rt.get("success"):
            realtime = rt.get("realtime", {})
            info = rt.get("info", {})

            latest_trade_price = safe_float(realtime.get("latest_trade_price"), 0.0)
            open_price = safe_float(realtime.get("open"), 0.0)
            best_bid_price = safe_float(
                realtime.get("best_bid_price", [0])[0]
                if isinstance(realtime.get("best_bid_price"), list) and realtime.get("best_bid_price")
                else realtime.get("best_bid_price"),
                0.0
            )
            best_ask_price = safe_float(
                realtime.get("best_ask_price", [0])[0]
                if isinstance(realtime.get("best_ask_price"), list) and realtime.get("best_ask_price")
                else realtime.get("best_ask_price"),
                0.0
            )

            price_candidates = [latest_trade_price, best_bid_price, best_ask_price, open_price]
            price_candidates = [p for p in price_candidates if p > 0]
            if price_candidates:
                price = price_candidates[0]

            volume = safe_float(realtime.get("accumulate_trade_volume"), 0.0)

            reference = safe_float(info.get("yesterday_close"), 0.0)
            if price and reference > 0:
                change_percent = round((price - reference) / reference * 100, 2)

    except Exception:
        pass

    return price, volume, change_percent


def get_stock_data(symbol: str) -> Optional[Dict[str, Any]]:
    symbol = str(symbol).strip()

    try:
        stock = twstock.Stock(symbol)
        history = stock.fetch_from(2025, 1)
    except Exception:
        return None

    if not history:
        return None

    closes = [d.close for d in history if d.close is not None]
    volumes = [float(d.capacity) / 1000 for d in history if d.capacity is not None]

    if len(closes) < 5:
        return None

    ma5 = moving_average(closes, 5)
    ma20 = moving_average(closes, 20) if len(closes) >= 20 else None

    last_close = round(closes[-1], 2)
    avg_volume_5 = round(sum(volumes[-5:]) / min(len(volumes[-5:]), 5), 2) if volumes else 0.0

    price, realtime_volume, change_percent = get_realtime_price_and_volume(symbol)

    if price is None or price <= 0:
        price = last_close

    if realtime_volume <= 0:
        realtime_volume = avg_volume_5

    if change_percent == 0 and len(closes) >= 2 and closes[-2] > 0:
        change_percent = round((price - closes[-2]) / closes[-2] * 100, 2)

    return {
        "symbol": symbol,
        "name": get_stock_name(symbol),
        "price": round(price, 2),
        "change_percent": round(change_percent, 2),
        "volume": round(realtime_volume, 2),
        "ma5": ma5,
        "ma20": ma20 if ma20 is not None else ma5,
        "last_close": last_close,
        "avg_volume_5": avg_volume_5,
        "history_closes": closes[-20:],
    }


def analyze_stock(data: Dict[str, Any]) -> Dict[str, Any]:
    price = safe_float(data.get("price"))
    ma5 = safe_float(data.get("ma5"))
    ma20 = safe_float(data.get("ma20"))
    volume = safe_float(data.get("volume"))
    avg_volume_5 = safe_float(data.get("avg_volume_5"))
    change_percent = safe_float(data.get("change_percent"))
    closes = data.get("history_closes", [])

    score = 0
    reasons: List[str] = []

    if price > ma5 > 0:
        score += 20
        reasons.append("股價站上MA5")
    else:
        reasons.append("股價未站上MA5")

    if price > ma20 > 0:
        score += 20
        reasons.append("股價站上MA20")
    else:
        reasons.append("股價未站上MA20")

    if ma5 > ma20 > 0:
        score += 20
        reasons.append("MA5在MA20之上")
    else:
        reasons.append("均線排列偏弱")

    if change_percent > 0:
        score += 10
        reasons.append("當日漲幅為正")
    elif change_percent < 0:
        reasons.append("當日漲幅為負")

    if avg_volume_5 > 0 and volume >= avg_volume_5:
        score += 10
        reasons.append("成交量高於近5日均量")
    else:
        reasons.append("成交量未放大")

    if len(closes) >= 10:
        recent_low = min(closes[-10:])
        recent_high = max(closes[-10:])
        if recent_low < price < recent_high:
            score += 10
            reasons.append("股價位於近10日區間中上緣")
        elif price >= recent_high:
            score += 15
            reasons.append("接近近10日新高")

    volatility = 0.0
    if len(closes) >= 5:
        pct_changes = []
        for i in range(1, len(closes[-5:])):
            prev = closes[-5:][i - 1]
            curr = closes[-5:][i]
            if prev > 0:
                pct_changes.append((curr - prev) / prev * 100)
        if pct_changes:
            volatility = round(statistics.pstdev(pct_changes), 2)

    if volatility <= 3 and volatility > 0:
        score += 5
        reasons.append("短線波動適中")

    score = max(0, min(100, score))

    if score >= 75:
        trend = "強勢"
    elif score >= 50:
        trend = "中性偏強"
    elif score >= 30:
        trend = "中性"
    else:
        trend = "弱勢"

    entry_base = ma5 if ma5 > 0 else price
    entry_low = round(entry_base * 0.98, 2)
    entry_high = round(entry_base * 1.02, 2)
    take_profit = round(price * 1.10, 2)
    stop_loss = round(price * 0.95, 2)

    return {
        "symbol": data["symbol"],
        "name": data["name"],
        "price": round(price, 2),
        "change_percent": round(change_percent, 2),
        "volume": round(volume, 2),
        "ma5": round(ma5, 2),
        "ma20": round(ma20, 2),
        "score": score,
        "trend": trend,
        "entry_range": f"{entry_low} ~ {entry_high}",
        "take_profit": take_profit,
        "stop_loss": stop_loss,
        "reason": "、".join(reasons[:4]),
    }


@app.get("/")
def root():
    return {"message": "TW Stock Realtime Screener B is running"}


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/scan")
def scan(request: ScanRequest):
    results: List[Dict[str, Any]] = []

    for symbol in request.stocks:
        data = get_stock_data(symbol)
        if not data:
            continue
        results.append(analyze_stock(data))

    results.sort(key=lambda x: x["score"], reverse=True)
    return results


@app.get("/scan_all")
def scan_all(limit: int = 50):
    """
    掃描 CSV 裡全部股票，預設回傳前 50 名
    """
    results: List[Dict[str, Any]] = []

    symbols = list(STOCK_NAME_MAP.keys())
    if not symbols:
        return []

    for symbol in symbols:
        data = get_stock_data(symbol)
        if not data:
            continue
        results.append(analyze_stock(data))

    results.sort(key=lambda x: x["score"], reverse=True)
    return results[:limit]
