from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import requests
from typing import List, Dict, Any
from statistics import median

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
ETF_URL = "https://openapi.twse.com.tw/v1/exchangeReport/etfall"


@app.get("/")
def root():
    return {"message": "TW Stock Realtime Screener is running"}


def safe_float(value, default=0.0):
    try:
        if value is None:
            return default
        s = str(value).replace(",", "").replace("X", "").strip()
        if s in ["", "-", "--", "----", "除權息", "N/A"]:
            return default
        return float(s)
    except:
        return default


def safe_int(value, default=0):
    try:
        if value is None:
            return default
        s = str(value).replace(",", "").strip()
        if s in ["", "-", "--", "----", "N/A"]:
            return default
        return int(float(s))
    except:
        return default


def calc_amplitude(high: float, low: float, prev_close: float) -> float:
    if prev_close <= 0:
        return 0.0
    return round(((high - low) / prev_close) * 100, 2)


def calc_change_percent(price: float, prev_close: float, change: float = None) -> float:
    if prev_close > 0:
        return round(((price - prev_close) / prev_close) * 100, 2)
    if price > 0 and change is not None:
        try:
            return round((change / (price - change)) * 100, 2) if (price - change) != 0 else 0.0
        except:
            return 0.0
    return 0.0


def detect_signal(change_percent: float, price: float, open_price: float, high: float, low: float, volume_ratio: float) -> str:
    if change_percent >= 3 and price >= open_price and volume_ratio >= 1.2:
        return "強勢多方"
    elif change_percent >= 1.5 and price >= open_price:
        return "偏多"
    elif -1.5 < change_percent < 1.5:
        return "區間震盪"
    elif change_percent <= -3 and price <= open_price:
        return "弱勢空方"
    else:
        return "偏空"


def generate_professional_reason(
    stock: Dict[str, Any],
    median_volume: float
) -> str:
    price = stock.get("price", 0)
    open_price = stock.get("open", 0)
    high = stock.get("high", 0)
    low = stock.get("low", 0)
    prev_close = stock.get("prev_close", 0)
    volume = stock.get("volume", 0)
    change_percent = stock.get("change_percent", 0)
    amplitude = stock.get("amplitude", 0)

    volume_ratio = round(volume / median_volume, 2) if median_volume > 0 else 1.0

    reasons = []

    # 1. 價格結構
    if price > open_price > 0:
        if abs(price - high) / price < 0.01:
            reasons.append("股價維持開高走高格局，收斂於當日高檔附近，買盤承接力道偏強")
        else:
            reasons.append("股價位於開盤價之上，盤中多方仍具主導權")
    elif price < open_price and open_price > 0:
        if abs(price - low) / price < 0.01:
            reasons.append("股價貼近當日低檔，短線賣壓仍待進一步消化")
        else:
            reasons.append("股價跌回開盤價下方，盤中追價意願偏保守")
    else:
        reasons.append("股價圍繞平盤附近整理，市場觀望氣氛較濃")

    # 2. 漲跌幅判讀
    if change_percent >= 4:
        reasons.append("漲幅擴大且動能明確，屬盤面強勢表態個股")
    elif change_percent >= 2:
        reasons.append("維持中度以上漲幅，短線趨勢明顯偏多")
    elif change_percent >= 0.8:
        reasons.append("維持溫和上漲結構，多方節奏尚未破壞")
    elif change_percent <= -4:
        reasons.append("跌幅偏深，短線結構明顯轉弱")
    elif change_percent <= -2:
        reasons.append("股價回落幅度擴大，反映短線籌碼偏向保守")
    else:
        reasons.append("漲跌幅尚屬可控，等待方向進一步表態")

    # 3. 量能判讀
    if volume_ratio >= 2.5:
        reasons.append("成交量明顯放大，量能有效支持價格波動，市場關注度高")
    elif volume_ratio >= 1.5:
        reasons.append("量能優於市場中位水準，具備一定換手與推動力")
    elif volume_ratio >= 0.8:
        reasons.append("成交量維持正常水準，量價結構尚屬健康")
    else:
        reasons.append("成交量偏低，短線延續力仍需觀察")

    # 4. 振幅判讀
    if amplitude >= 8:
        reasons.append("日內振幅偏大，代表多空交戰激烈，操作上宜搭配停損控管")
    elif amplitude >= 4:
        reasons.append("具備適度波動空間，短線交易彈性較佳")
    else:
        reasons.append("日內波動收斂，屬相對穩定型走勢")

    # 5. 特殊型態補充
    if high > 0 and low > 0 and price > 0:
        close_near_high = abs(high - price) / price < 0.015
        close_near_low = abs(price - low) / price < 0.015

        if close_near_high and change_percent > 0:
            reasons.append("收盤位置接近當日高點，顯示尾盤買盤未明顯鬆動")
        elif close_near_low and change_percent < 0:
            reasons.append("收盤位置靠近日內低點，反映尾盤承接力道不足")

    # 最後組合，抓 3~4 句，避免太長
    final_reasons = reasons[:4]
    return "；".join(final_reasons) + "。"


def calc_score(stock: Dict[str, Any], median_volume: float) -> float:
    change_percent = stock.get("change_percent", 0)
    amplitude = stock.get("amplitude", 0)
    volume = stock.get("volume", 0)
    price = stock.get("price", 0)
    open_price = stock.get("open", 0)
    high = stock.get("high", 0)

    volume_ratio = volume / median_volume if median_volume > 0 else 1.0

    score = 50.0

    # 漲跌幅
    score += min(max(change_percent * 4, -20), 20)

    # 振幅
    score += min(amplitude * 1.5, 12)

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
    elif price < open_price:
        score -= 5

    # 接近高點
    if high > 0 and abs(high - price) / price < 0.015:
        score += 6

    return round(max(min(score, 99), 1), 2)


def calc_trade_levels(price: float, amplitude: float, signal: str):
    if price <= 0:
        return "-", "-", "-"

    # 依波動幅度決定進出場距離
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

    entry_text = f"{entry_low} ~ {entry_high}"
    return entry_text, str(target), str(stop)


def fetch_twse_stocks() -> List[Dict[str, Any]]:
    res = requests.get(TWSE_URL, timeout=20)
    data = res.json()
    stocks = []

    for s in data:
        try:
            symbol = str(s.get("Code", "")).strip()
            name = str(s.get("Name", "")).strip()
            price = safe_float(s.get("ClosingPrice"))
            change = safe_float(s.get("Change"))
            volume = safe_int(s.get("TradeVolume"))
            open_price = safe_float(s.get("OpeningPrice"))
            high = safe_float(s.get("HighestPrice"))
            low = safe_float(s.get("LowestPrice"))

            if not symbol or not name or price <= 0:
                continue

            prev_close = round(price - change, 2) if price > 0 else 0
            change_percent = calc_change_percent(price, prev_close, change)
            amplitude = calc_amplitude(high, low, prev_close)

            stocks.append({
                "market": "上市",
                "symbol": symbol,
                "name": name,
                "price": price,
                "change": round(change, 2),
                "change_percent": change_percent,
                "volume": volume,
                "open": open_price,
                "high": high,
                "low": low,
                "prev_close": prev_close,
                "amplitude": amplitude,
            })
        except:
            continue

    return stocks


def fetch_tpex_stocks() -> List[Dict[str, Any]]:
    res = requests.get(TPEX_URL, timeout=20)
    data = res.json()
    stocks = []

    for s in data:
        try:
            symbol = str(s.get("SecuritiesCompanyCode", "")).strip()
            name = str(s.get("CompanyName", "")).strip()
            price = safe_float(s.get("Close"))
            change = safe_float(s.get("Diff"))
            volume = safe_int(s.get("TradingShares"))
            open_price = safe_float(s.get("Open"))
            high = safe_float(s.get("High"))
            low = safe_float(s.get("Low"))

            if not symbol or not name or price <= 0:
                continue

            prev_close = round(price - change, 2) if price > 0 else 0
            change_percent = calc_change_percent(price, prev_close, change)
            amplitude = calc_amplitude(high, low, prev_close)

            stocks.append({
                "market": "上櫃",
                "symbol": symbol,
                "name": name,
                "price": price,
                "change": round(change, 2),
                "change_percent": change_percent,
                "volume": volume,
                "open": open_price,
                "high": high,
                "low": low,
                "prev_close": prev_close,
                "amplitude": amplitude,
            })
        except:
            continue

    return stocks


def fetch_etf_stocks() -> List[Dict[str, Any]]:
    try:
        res = requests.get(ETF_URL, timeout=20)
        data = res.json()
        stocks = []

        for s in data:
            try:
                symbol = str(s.get("Code", "")).strip()
                name = str(s.get("Name", "")).strip()
                price = safe_float(s.get("ClosingPrice"))
                change = safe_float(s.get("Change"))
                volume = safe_int(s.get("TradeVolume"))
                open_price = safe_float(s.get("OpeningPrice"))
                high = safe_float(s.get("HighestPrice"))
                low = safe_float(s.get("LowestPrice"))

                if not symbol or not name or price <= 0:
                    continue

                prev_close = round(price - change, 2) if price > 0 else 0
                change_percent = calc_change_percent(price, prev_close, change)
                amplitude = calc_amplitude(high, low, prev_close)

                stocks.append({
                    "market": "ETF",
                    "symbol": symbol,
                    "name": name,
                    "price": price,
                    "change": round(change, 2),
                    "change_percent": change_percent,
                    "volume": volume,
                    "open": open_price,
                    "high": high,
                    "low": low,
                    "prev_close": prev_close,
                    "amplitude": amplitude,
                })
            except:
                continue

        return stocks
    except:
        return []


def enrich_stocks(stocks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if not stocks:
        return stocks

    volumes = [s["volume"] for s in stocks if s.get("volume", 0) > 0]
    median_volume = median(volumes) if volumes else 1

    for s in stocks:
        volume_ratio = round(s.get("volume", 0) / median_volume, 2) if median_volume > 0 else 1.0
        signal = detect_signal(
            s.get("change_percent", 0),
            s.get("price", 0),
            s.get("open", 0),
            s.get("high", 0),
            s.get("low", 0),
            volume_ratio,
        )

        score = calc_score(s, median_volume)
        reason = generate_professional_reason(s, median_volume)
        entry_price, target_price, stop_loss = calc_trade_levels(
            s.get("price", 0),
            s.get("amplitude", 0),
            signal
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
    try:
        twse_stocks = fetch_twse_stocks()
        tpex_stocks = fetch_tpex_stocks()
        etf_stocks = fetch_etf_stocks()

        all_stocks = twse_stocks + tpex_stocks + etf_stocks
        all_stocks = enrich_stocks(all_stocks)

        # 預設按分數排序
        all_stocks.sort(key=lambda x: (x.get("score", 0), x.get("change_percent", 0), x.get("volume", 0)), reverse=True)

        return {
            "success": True,
            "total": len(all_stocks),
            "stocks": all_stocks,
            "top_recommendations": all_stocks[:10],
        }
    except Exception as e:
        return {
            "success": False,
            "message": str(e),
            "total": 0,
            "stocks": [],
            "top_recommendations": [],
        }
