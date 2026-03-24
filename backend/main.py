from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
from concurrent.futures import ThreadPoolExecutor, as_completed
import statistics
import math
import twstock


app = FastAPI(title="TW Stock Realtime Screener")


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ScanRequest(BaseModel):
    stocks: Optional[List[str]] = None


def safe_float(value, default=0.0):
    try:
        if value is None:
            return default
        if isinstance(value, str):
            value = value.replace(",", "").strip()
            if value == "-":
                return default
        return float(value)
    except Exception:
        return default


def safe_int(value, default=0):
    try:
        if value is None:
            return default
        if isinstance(value, str):
            value = value.replace(",", "").strip()
            if value == "-":
                return default
        return int(float(value))
    except Exception:
        return default


def round2(value: float) -> float:
    return round(value, 2)


def mean_last(values: List[float], count: int) -> float:
    cleaned = [v for v in values if isinstance(v, (int, float)) and v > 0]
    if len(cleaned) < count:
        return 0.0
    return round2(sum(cleaned[-count:]) / count)


def get_all_tw_stocks() -> Dict[str, str]:
    """
    從 twstock.codes 取出台股股票池
    只保留一般 4 位數股票，排除 ETF、權證、指數等非一般股票標的
    """
    result = {}

    for code, info in twstock.codes.items():
        try:
            symbol = str(info.code).strip()
            name = str(info.name).strip()
            market = str(getattr(info, "market", "")).strip()
            type_name = str(getattr(info, "type", "")).strip()

            # 僅保留 4 位數
            if not (symbol.isdigit() and len(symbol) == 4):
                continue

            # 僅保留股票
            # twstock 常見 type 為 股票 / ETF / 指數 / 權證 ...
            if type_name != "股票":
                continue

            # 僅保留上市 / 上櫃
            if market not in ["上市", "上櫃"]:
                continue

            result[symbol] = name
        except Exception:
            continue

    return dict(sorted(result.items(), key=lambda x: x[0]))


def get_realtime_data(symbol: str) -> Dict[str, Any]:
    """
    取即時資料
    """
    try:
        realtime = twstock.realtime.get(symbol)

        success = realtime.get("success", False)
        if not success:
            return {}

        realtime_info = realtime.get("realtime", {}) or {}
        info = realtime.get("info", {}) or {}

        latest_trade_price = safe_float(realtime_info.get("latest_trade_price"))
        open_price = safe_float(realtime_info.get("open"))
        high_price = safe_float(realtime_info.get("high"))
        low_price = safe_float(realtime_info.get("low"))
        accumulated_volume = safe_int(realtime_info.get("accumulate_trade_volume"))
        best_bid_price = realtime_info.get("best_bid_price", [])
        best_ask_price = realtime_info.get("best_ask_price", [])

        if latest_trade_price <= 0:
            # 有些盤中資料可能 latest_trade_price 暫時空值，退而求其次
            bid = safe_float(best_bid_price[0]) if best_bid_price else 0
            ask = safe_float(best_ask_price[0]) if best_ask_price else 0
            if bid > 0 and ask > 0:
                latest_trade_price = round2((bid + ask) / 2)
            elif bid > 0:
                latest_trade_price = bid
            elif ask > 0:
                latest_trade_price = ask

        return {
            "name": info.get("name", ""),
            "price": latest_trade_price,
            "open": open_price,
            "high": high_price,
            "low": low_price,
            "volume": accumulated_volume,
        }
    except Exception:
        return {}


def get_history_data(symbol: str):
    """
    抓歷史資料，計算 MA5 / MA20
    """
    try:
        stock = twstock.Stock(symbol)
        history = stock.fetch_from(2025, 1)

        closes = []
        volumes = []

        for item in history:
            close_price = safe_float(getattr(item, "close", 0))
            volume = safe_int(getattr(item, "capacity", 0))
            if close_price > 0:
                closes.append(close_price)
            if volume > 0:
                volumes.append(volume)

        ma5 = mean_last(closes, 5)
        ma20 = mean_last(closes, 20)

        return {
            "closes": closes,
            "volumes": volumes,
            "ma5": ma5,
            "ma20": ma20,
        }
    except Exception:
        return {
            "closes": [],
            "volumes": [],
            "ma5": 0.0,
            "ma20": 0.0,
        }


def build_signal_and_reason(price: float, change_percent: float, volume: int, ma5: float, ma20: float):
    reasons = []

    if price > 0 and ma5 > 0 and ma20 > 0:
        if price > ma5 and price > ma20:
            reasons.append("股價站上 MA5 與 MA20")
        elif price > ma5 and price <= ma20:
            reasons.append("股價站上 MA5、接近 MA20")
        elif price < ma5 and price < ma20:
            reasons.append("股價跌破 MA5 與 MA20")
        else:
            reasons.append("股價位於均線之間")

        if ma5 > ma20:
            reasons.append("短期均線強於中期均線")
        elif ma5 < ma20:
            reasons.append("短期均線弱於中期均線")

    if change_percent >= 3:
        reasons.append("當日漲幅強勢")
    elif change_percent > 0:
        reasons.append("當日走勢偏強")
    elif change_percent <= -3:
        reasons.append("當日跌幅偏大")
    elif change_percent < 0:
        reasons.append("當日走勢偏弱")

    if volume >= 10000000:
        reasons.append("成交量非常活躍")
    elif volume >= 3000000:
        reasons.append("成交量活躍")
    elif volume > 0:
        reasons.append("成交量普通")

    bullish = price > ma5 > 0 and price > ma20 > 0 and ma5 >= ma20
    breakout = change_percent >= 3 and volume >= 3000000
    bearish = price < ma5 and price < ma20 and ma5 > 0 and ma20 > 0

    if breakout:
        signal = "強勢突破"
    elif bullish:
        signal = "偏多"
    elif bearish:
        signal = "偏空"
    else:
        signal = "觀望"

    if not reasons:
        reasons.append("資料不足")

    return signal, "、".join(reasons)


def analyze_stock(symbol: str, name_map: Dict[str, str]) -> Optional[Dict[str, Any]]:
    try:
        realtime_data = get_realtime_data(symbol)
        history_data = get_history_data(symbol)

        price = safe_float(realtime_data.get("price"))
        volume = safe_int(realtime_data.get("volume"))
        ma5 = safe_float(history_data.get("ma5"))
        ma20 = safe_float(history_data.get("ma20"))

        if price <= 0:
            return None

        prev_close_candidates = history_data.get("closes", [])
        prev_close = 0.0

        if len(prev_close_candidates) >= 1:
            prev_close = safe_float(prev_close_candidates[-1])

            # 如果最後一筆歷史剛好就是今天 close 或接近現價，仍可接受
            # 但若前一收太異常則保守處理
            if prev_close <= 0:
                prev_close = 0.0

        change_percent = 0.0
        if prev_close > 0:
            change_percent = round2(((price - prev_close) / prev_close) * 100)

        signal, reason = build_signal_and_reason(
            price=price,
            change_percent=change_percent,
            volume=volume,
            ma5=ma5,
            ma20=ma20,
        )

        return {
            "symbol": symbol,
            "name": realtime_data.get("name") or name_map.get(symbol, ""),
            "price": round2(price),
            "change_percent": round2(change_percent),
            "volume": volume,
            "ma5": round2(ma5),
            "ma20": round2(ma20),
            "signal": signal,
            "reason": reason,
        }
    except Exception:
        return None


@app.get("/")
def root():
    return {"message": "TW Stock Realtime Screener API is running"}


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/scan")
def scan_stocks(req: ScanRequest):
    name_map = get_all_tw_stocks()

    if req.stocks and len(req.stocks) > 0:
        stock_list = []
        for s in req.stocks:
            symbol = str(s).strip()
            if symbol.isdigit() and len(symbol) == 4:
                stock_list.append(symbol)
        stock_list = list(dict.fromkeys(stock_list))
    else:
        stock_list = list(name_map.keys())

    results = []

    # 全台股一起掃，避免太慢，用執行緒加速
    max_workers = 16 if len(stock_list) > 200 else 8

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_map = {
            executor.submit(analyze_stock, symbol, name_map): symbol
            for symbol in stock_list
        }

        for future in as_completed(future_map):
            item = future.result()
            if item:
                results.append(item)

    # 依股票代號排序，讓前端可自行再依分數排序
    results.sort(key=lambda x: x["symbol"])
    return results
