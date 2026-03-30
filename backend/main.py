from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import requests
from typing import List, Dict, Any
from datetime import datetime, timedelta

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def root():
    return {"message": "TW Stock Realtime Screener B is running"}


def safe_float(value, default=0.0):
    try:
        if value in [None, "", "-", "--"]:
            return default
        return float(str(value).replace(",", "").replace("X", "").strip())
    except:
        return default


def safe_int(value, default=0):
    try:
        if value in [None, "", "-", "--"]:
            return default
        return int(float(str(value).replace(",", "").strip()))
    except:
        return default


def get_previous_weekday(date_obj: datetime) -> datetime:
    d = date_obj - timedelta(days=1)
    while d.weekday() >= 5:  # 5=Sat, 6=Sun
        d -= timedelta(days=1)
    return d


def get_market_info():
    now = datetime.now()
    weekday = now.weekday()  # Mon=0 ... Sun=6
    current_hhmm = now.hour * 100 + now.minute

    # 非交易日：週六、週日
    if weekday >= 5:
        last_trading_day = get_previous_weekday(now)
        return {
            "market_status": "非交易日",
            "data_date": last_trading_day.strftime("%Y%m%d"),
            "last_update": now.strftime("%Y/%m/%d %H:%M:%S"),
        }

    # 平日
    if 900 <= current_hhmm <= 1330:
        return {
            "market_status": "開盤中",
            "data_date": now.strftime("%Y%m%d"),
            "last_update": now.strftime("%Y/%m/%d %H:%M:%S"),
        }

    if current_hhmm < 900:
        return {
            "market_status": "開盤前",
            "data_date": now.strftime("%Y%m%d"),
            "last_update": now.strftime("%Y/%m/%d %H:%M:%S"),
        }

    return {
        "market_status": "收盤後資料",
        "data_date": now.strftime("%Y%m%d"),
        "last_update": now.strftime("%Y/%m/%d %H:%M:%S"),
    }


def build_signal_and_reason(price: float, change: float, change_percent: float, volume: int):
    score = 50

    if change_percent >= 9:
        score += 35
    elif change_percent >= 5:
        score += 25
    elif change_percent >= 3:
        score += 18
    elif change_percent > 0:
        score += 8
    elif change_percent <= -5:
        score -= 10

    if volume >= 30000000:
        score += 14
    elif volume >= 10000000:
        score += 10
    elif volume >= 3000000:
        score += 6

    if change > 0:
        score += 5

    score = max(1, min(99, score))

    if score >= 85:
        signal = "強勢多方"
    elif score >= 70:
        signal = "偏多"
    elif score >= 50:
        signal = "中性偏多"
    elif score >= 35:
        signal = "中性"
    else:
        signal = "偏弱"

    reason = "股價維持強勢、量能放大、短線表現活躍"
    if change_percent >= 9:
        reason = "股價維持開高走高格局，收盤於當日高檔附近，顯示買盤承接力道偏強；漲幅明確擴大，屬盤面強勢表態個股，成交量明顯放大，代表市場關注度高。"
    elif change_percent >= 5:
        reason = "漲勢明顯擴大，股價結構偏強，量能表現佳，具短線續強機會。"
    elif change_percent > 0:
        reason = "股價維持紅盤，走勢穩定，量價結構尚可，屬偏多觀察名單。"
    elif change_percent < 0:
        reason = "股價回落，短線動能偏弱，建議觀察支撐與量能變化。"

    entry_low = round(price * 0.99, 2)
    entry_high = round(price * 1.01, 2)
    target_price = round(price * 1.05, 2)
    stop_loss = round(price * 0.96, 2)

    return {
        "score": score,
        "signal": signal,
        "reason": reason,
        "entry_price": f"{entry_low} ~ {entry_high}",
        "target_price": str(target_price),
        "stop_loss": str(stop_loss),
    }


def fetch_twse_stocks() -> List[Dict[str, Any]]:
    url = "https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL"
    res = requests.get(url, timeout=20)
    res.raise_for_status()
    data = res.json()

    stocks = []
    for s in data:
        try:
            symbol = str(s.get("Code", "")).strip()
            name = str(s.get("Name", "")).strip()
            price = safe_float(s.get("ClosingPrice"))
            change_raw = str(s.get("Change", "")).strip()
            volume = safe_int(s.get("TradeVolume"))

            if not symbol or not name or price <= 0:
                continue

            change = safe_float(change_raw, 0.0)
            prev_close = price - change
            change_percent = round((change / prev_close * 100), 2) if prev_close > 0 else 0.0

            extra = build_signal_and_reason(price, change, change_percent, volume)

            stocks.append({
                "market": "上市",
                "symbol": symbol,
                "name": name,
                "price": round(price, 2),
                "change": round(change, 2),
                "change_percent": round(change_percent, 2),
                "volume": volume,
                **extra,
            })
        except:
            continue

    return stocks


def fetch_tpex_stocks() -> List[Dict[str, Any]]:
    urls = [
        "https://www.tpex.org.tw/openapi/v1/tpex_mainboard_quotes",
        "https://www.tpex.org.tw/openapi/v1/tpex_esb_quotes",
    ]

    stocks = []

    for url in urls:
        try:
            res = requests.get(url, timeout=20)
            res.raise_for_status()
            data = res.json()

            for s in data:
                try:
                    symbol = str(s.get("SecuritiesCompanyCode", "") or s.get("Code", "")).strip()
                    name = str(s.get("CompanyName", "") or s.get("Name", "")).strip()

                    price = safe_float(
                        s.get("Close") or s.get("ClosingPrice") or s.get("LatestTradePrice"),
                        0.0
                    )

                    change = safe_float(
                        s.get("Change") or s.get("PriceChange"),
                        0.0
                    )

                    volume = safe_int(
                        s.get("TradingShares") or s.get("TradeVolume") or s.get("Volume"),
                        0
                    )

                    if not symbol or not name or price <= 0:
                        continue

                    prev_close = price - change
                    change_percent = round((change / prev_close * 100), 2) if prev_close > 0 else 0.0

                    extra = build_signal_and_reason(price, change, change_percent, volume)

                    stocks.append({
                        "market": "上櫃",
                        "symbol": symbol,
                        "name": name,
                        "price": round(price, 2),
                        "change": round(change, 2),
                        "change_percent": round(change_percent, 2),
                        "volume": volume,
                        **extra,
                    })
                except:
                    continue
        except:
            continue

    return stocks


@app.get("/stocks")
def get_stocks():
    try:
        twse_stocks = fetch_twse_stocks()
        tpex_stocks = fetch_tpex_stocks()

        all_stocks = twse_stocks + tpex_stocks
        all_stocks.sort(
            key=lambda x: (x.get("score", 0), x.get("volume", 0)),
            reverse=True
        )

        market_info = get_market_info()

        return {
            "success": True,
            "market_status": market_info["market_status"],
            "data_date": market_info["data_date"],
            "last_update": market_info["last_update"],
            "total": len(all_stocks),
            "stocks": all_stocks
        }

    except Exception as e:
        market_info = get_market_info()

        return {
            "success": False,
            "market_status": market_info["market_status"],
            "data_date": market_info["data_date"],
            "last_update": market_info["last_update"],
            "total": 0,
            "stocks": [],
            "message": f"資料抓取失敗: {str(e)}"
        }
