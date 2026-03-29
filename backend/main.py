from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from datetime import datetime
from statistics import median
from typing import Any, Dict, List

import requests

app = FastAPI(title="TW Stock Realtime Screener")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

TWSE_URL = "https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL"
TPEX_URL = "https://www.tpex.org.tw/openapi/v1/tpex_mainboard_daily_close_quotes"


@app.get("/")
def root():
    return {"message": "TW Stock Realtime Screener is running"}


def now_str() -> str:
    return datetime.now().strftime("%Y/%m/%d %H:%M:%S")


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        s = str(value).replace(",", "").replace("X", "").replace("除權息", "").strip()
        if s in ["", "-", "--", "----", "N/A", "nan", "None"]:
            return default
        return float(s)
    except Exception:
        return default


def safe_int(value: Any, default: int = 0) -> int:
    try:
        if value is None:
            return default
        s = str(value).replace(",", "").strip()
        if s in ["", "-", "--", "----", "N/A", "nan", "None"]:
            return default
        return int(float(s))
    except Exception:
        return default


def is_valid_common_stock_symbol(symbol: str) -> bool:
    """
    只保留一般股票常見 4 位數代號
    例：2330、2317、3715
    排除 ETF、權證、牛熊證、其他雜項商品
    """
    return symbol.isdigit() and len(symbol) == 4


def calc_change_percent(price: float, prev_close: float) -> float:
    if prev_close <= 0:
        return 0.0
    return round(((price - prev_close) / prev_close) * 100, 2)


def calc_amplitude(high: float, low: float, prev_close: float) -> float:
    if prev_close <= 0:
        return 0.0
    return round(((high - low) / prev_close) * 100, 2)


def detect_signal(change_percent: float, price: float, open_price: float, volume_ratio: float) -> str:
    if change_percent >= 3 and price >= open_price and volume_ratio >= 1.2:
        return "強勢多方"
    if change_percent >= 1.2 and price >= open_price:
        return "偏多"
    if change_percent <= -3 and price <= open_price:
        return "弱勢空方"
    if change_percent <= -1.2:
        return "偏空"
    return "區間震盪"


def generate_professional_reason(stock: Dict[str, Any], median_volume: float) -> str:
    price = stock.get("price", 0.0)
    open_price = stock.get("open", 0.0)
    high = stock.get("high", 0.0)
    low = stock.get("low", 0.0)
    volume = stock.get("volume", 0)
    change_percent = stock.get("change_percent", 0.0)
    amplitude = stock.get("amplitude", 0.0)

    volume_ratio = round(volume / median_volume, 2) if median_volume > 0 else 1.0

    reasons: List[str] = []

    # 1. 價格結構
    if price > open_price > 0:
        if high > 0 and abs(high - price) / max(price, 0.01) < 0.01:
            reasons.append("股價維持開高走高格局，收斂於當日高檔附近，顯示買盤承接力道偏強")
        else:
            reasons.append("股價位於開盤價之上，盤中多方仍維持主導節奏")
    elif price < open_price and open_price > 0:
        if low > 0 and abs(price - low) / max(price, 0.01) < 0.01:
            reasons.append("股價貼近日內低點，短線賣壓仍待進一步消化")
        else:
            reasons.append("股價跌回開盤價下方，顯示盤中追價意願轉趨保守")
    else:
        reasons.append("股價圍繞平盤附近整理，市場觀望氣氛相對明顯")

    # 2. 漲跌幅
    if change_percent >= 6:
        reasons.append("漲幅明確擴大，屬盤面強勢表態個股")
    elif change_percent >= 3:
        reasons.append("漲幅維持在強勢區間，短線趨勢明顯偏多")
    elif change_percent >= 1:
        reasons.append("維持溫和上漲結構，多方節奏尚未破壞")
    elif change_percent <= -6:
        reasons.append("跌幅偏深，短線結構明顯轉弱")
    elif change_percent <= -3:
        reasons.append("股價回落幅度擴大，反映短線籌碼偏保守")
    else:
        reasons.append("漲跌幅仍在可控範圍內，等待後續方向表態")

    # 3. 量能
    if volume_ratio >= 2.5:
        reasons.append("成交量明顯放大，量能足以支持價格波動，市場關注度高")
    elif volume_ratio >= 1.5:
        reasons.append("量能優於市場中位水準，具備一定換手與推動力")
    elif volume_ratio >= 0.8:
        reasons.append("成交量維持正常水準，量價結構尚屬健康")
    else:
        reasons.append("成交量偏低，短線續航力仍需進一步觀察")

    # 4. 振幅
    if amplitude >= 8:
        reasons.append("日內振幅偏大，代表多空交戰激烈，操作上宜搭配停損控管")
    elif amplitude >= 4:
        reasons.append("具備適度波動空間，短線交易彈性相對較佳")
    else:
        reasons.append("日內波動收斂，整體走勢相對穩定")

    return "；".join(reasons[:4]) + "。"


def calc_score(stock: Dict[str, Any], median_volume: float) -> float:
    change_percent = stock.get("change_percent", 0.0)
    amplitude = stock.get("amplitude", 0.0)
    volume = stock.get("volume", 0)
    price = stock.get("price", 0.0)
    open_price = stock.get("open", 0.0)
    high = stock.get("high", 0.0)

    volume_ratio = volume / median_volume if median_volume > 0 else 1.0

    score = 50.0

    # 漲跌幅
    score += min(max(change_percent * 4, -20), 20)

    # 振幅
    score += min(amplitude * 1.4, 12)

    # 量能
    if volume_ratio >= 3:
        score += 15
    elif volume_ratio >= 2:
        score += 10
    elif volume_ratio >= 1.2:
        score += 6
    elif volume_ratio < 0.6:
        score -= 5

    # 價格位置
    if price > open_price > 0:
        score += 5
    elif open_price > 0 and price < open_price:
        score -= 5

    # 接近高點
    if high > 0 and abs(high - price) / max(price, 0.01) < 0.015:
        score += 6

    return round(max(min(score, 99), 1), 2)


def calc_trade_levels(price: float, amplitude: float, signal: str):
    if price <= 0:
        return "-", "-", "-"

    base_pct = 0.015
    if amplitude >= 8:
        base_pct = 0.03
    elif amplitude >= 5:
        base_pct = 0.025
    elif amplitude >= 3:
        base_pct = 0.02

    entry_low = round(price * (1 - base_pct / 2), 2)
    entry_high = round(price * (1 + base_pct / 2), 2)

    if signal in ["強勢多方", "偏多"]:
        target = round(price * (1 + base_pct * 2.2), 2)
        stop = round(price * (1 - base_pct * 1.4), 2)
    elif signal == "區間震盪":
        target = round(price * (1 + base_pct * 1.2), 2)
        stop = round(price * (1 - base_pct * 1.0), 2)
    else:
        target = round(price * (1 - base_pct * 1.2), 2)
        stop = round(price * (1 + base_pct * 1.0), 2)

    return f"{entry_low} ~ {entry_high}", str(target), str(stop)


def fetch_twse_stocks() -> List[Dict[str, Any]]:
    res = requests.get(TWSE_URL, timeout=20)
    res.raise_for_status()
    data = res.json()

    stocks: List[Dict[str, Any]] = []

    for s in data:
        try:
            symbol = str(s.get("Code", "")).strip()
            name = str(s.get("Name", "")).strip()

            if not is_valid_common_stock_symbol(symbol):
                continue

            price = safe_float(s.get("ClosingPrice"))
            change = safe_float(s.get("Change"))
            volume = safe_int(s.get("TradeVolume"))
            open_price = safe_float(s.get("OpeningPrice"))
            high = safe_float(s.get("HighestPrice"))
            low = safe_float(s.get("LowestPrice"))

            if not name or price <= 0:
                continue

            prev_close = round(price - change, 2) if (price - change) > 0 else 0.0
            if prev_close <= 0:
                continue

            change_percent = calc_change_percent(price, prev_close)
            amplitude = calc_amplitude(high, low, prev_close)

            stocks.append(
                {
                    "market": "上市",
                    "symbol": symbol,
                    "name": name,
                    "price": round(price, 2),
                    "change": round(change, 2),
                    "change_percent": change_percent,
                    "volume": volume,
                    "open": round(open_price, 2),
                    "high": round(high, 2),
                    "low": round(low, 2),
                    "prev_close": prev_close,
                    "amplitude": amplitude,
                }
            )
        except Exception:
            continue

    return stocks


def fetch_tpex_stocks() -> List[Dict[str, Any]]:
    res = requests.get(TPEX_URL, timeout=20)
    res.raise_for_status()
    data = res.json()

    stocks: List[Dict[str, Any]] = []

    for s in data:
        try:
            symbol = str(s.get("SecuritiesCompanyCode", "")).strip()
            name = str(s.get("CompanyName", "")).strip()

            if not is_valid_common_stock_symbol(symbol):
                continue

            price = safe_float(s.get("Close"))
            change = safe_float(s.get("Diff"))
            volume = safe_int(s.get("TradingShares"))
            open_price = safe_float(s.get("Open"))
            high = safe_float(s.get("High"))
            low = safe_float(s.get("Low"))

            if not name or price <= 0:
                continue

            prev_close = round(price - change, 2) if (price - change) > 0 else 0.0
            if prev_close <= 0:
                continue

            change_percent = calc_change_percent(price, prev_close)
            amplitude = calc_amplitude(high, low, prev_close)

            stocks.append(
                {
                    "market": "上櫃",
                    "symbol": symbol,
                    "name": name,
                    "price": round(price, 2),
                    "change": round(change, 2),
                    "change_percent": change_percent,
                    "volume": volume,
                    "open": round(open_price, 2),
                    "high": round(high, 2),
                    "low": round(low, 2),
                    "prev_close": prev_close,
                    "amplitude": amplitude,
                }
            )
        except Exception:
            continue

    return stocks


def enrich_stocks(stocks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if not stocks:
        return stocks

    volumes = [s["volume"] for s in stocks if s.get("volume", 0) > 0]
    median_volume = median(volumes) if volumes else 1

    for s in stocks:
        volume_ratio = round(s.get("volume", 0) / median_volume, 2) if median_volume > 0 else 1.0
        signal = detect_signal(
            s.get("change_percent", 0.0),
            s.get("price", 0.0),
            s.get("open", 0.0),
            volume_ratio,
        )
        score = calc_score(s, median_volume)
        reason = generate_professional_reason(s, median_volume)
        entry_price, target_price, stop_loss = calc_trade_levels(
            s.get("price", 0.0),
            s.get("amplitude", 0.0),
            signal,
        )

        s["signal"] = signal
        s["score"] = score
        s["reason"] = reason
        s["entry_price"] = entry_price
        s["target_price"] = target_price
        s["stop_loss"] = stop_loss

    return stocks


@app.get("/stocks")
def get_stocks():
    fetch_time = now_str()

    try:
        twse_stocks = fetch_twse_stocks()
        tpex_stocks = fetch_tpex_stocks()

        all_stocks = twse_stocks + tpex_stocks
        all_stocks = enrich_stocks(all_stocks)

        all_stocks.sort(
            key=lambda x: (
                x.get("score", 0),
                x.get("change_percent", 0),
                x.get("volume", 0),
            ),
            reverse=True,
        )

        # 取資料日期：優先從股票資料抓，抓不到就用今天
        data_date = datetime.now().strftime("%Y%m%d")
        if all_stocks:
            data_date = datetime.now().strftime("%Y%m%d")

        return {
            "success": True,
            "market_status": "收盤資料",
            "data_date": data_date,
            "last_update": fetch_time,
            "total": len(all_stocks),
            "stocks": all_stocks,
            "top_recommendations": all_stocks[:10],
        }

    except Exception as e:
        return {
            "success": False,
            "market_status": "資料同步失敗",
            "data_date": datetime.now().strftime("%Y%m%d"),
            "last_update": fetch_time,
            "total": 0,
            "stocks": [],
            "top_recommendations": [],
            "message": str(e),
        }
