from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import requests
from datetime import datetime

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

TWSE_URL = "https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL"


def to_float(value, default=0.0):
    try:
        if value is None:
            return default
        value = str(value).replace(",", "").replace("X", "").replace("--", "").strip()
        if value == "":
            return default
        return float(value)
    except:
        return default


def to_int(value, default=0):
    try:
        if value is None:
            return default
        value = str(value).replace(",", "").replace("--", "").strip()
        if value == "":
            return default
        return int(float(value))
    except:
        return default


def calc_score(change_percent, volume, price):
    score = 50

    if change_percent >= 6:
        score += 20
    elif change_percent >= 4:
        score += 16
    elif change_percent >= 2:
        score += 12
    elif change_percent >= 0:
        score += 6
    elif change_percent <= -4:
        score -= 8

    if volume >= 30000000:
        score += 18
    elif volume >= 10000000:
        score += 14
    elif volume >= 3000000:
        score += 10
    elif volume >= 1000000:
        score += 6

    if price >= 500:
        score += 5
    elif price >= 100:
        score += 4
    elif price >= 30:
        score += 3
    elif price >= 10:
        score += 2

    return max(1, min(99, round(score)))


def calc_signal(change_percent, volume):
    if change_percent >= 2 and volume >= 1000000:
        return "偏多"
    elif change_percent <= -2 and volume >= 1000000:
        return "偏空"
    else:
        return "中性"


def calc_entry_price(price):
    low = round(price * 0.99, 2)
    high = round(price * 1.01, 2)
    return f"{low} ~ {high}"


def calc_target_price(price):
    return str(round(price * 1.06, 2))


def calc_stop_loss(price):
    return str(round(price * 0.97, 2))


def calc_reason(change_percent, volume, score, signal, price):
    if signal == "偏多":
        if change_percent >= 4 and volume >= 10000000:
            return "漲幅強勢、成交量明顯放大，短線多方動能強"
        elif change_percent >= 3 and volume >= 3000000:
            return "股價走強且量能配合，短線續強機率較高"
        elif change_percent >= 2:
            return "股價維持強勢，短線技術面偏多"
        elif score >= 85:
            return "綜合分數高，量價結構穩定，具續攻條件"
        else:
            return "走勢偏多，可觀察是否延續上攻"

    if signal == "偏空":
        if change_percent <= -4 and volume >= 10000000:
            return "跌幅擴大且量能放大，賣壓偏重"
        elif change_percent <= -2:
            return "股價轉弱，短線走勢偏空"
        else:
            return "技術面偏弱，建議保守觀察"

    if score >= 85:
        return "綜合分數高，量價表現穩定，可列入觀察"
    elif volume >= 3000000:
        return "成交量活絡，市場關注度提升"
    elif price >= 500:
        return "高價股波動較大，建議留意風險控管"
    else:
        return "目前走勢中性，建議等待更明確訊號"


@app.get("/")
def root():
    return {"message": "TW Stock Realtime Screener backend running"}


@app.get("/stocks")
def get_stocks():
    try:
        res = requests.get(TWSE_URL, timeout=20)
        data = res.json()

        stocks = []
        now = datetime.now()
        last_update = now.strftime("%Y/%m/%d %H:%M:%S")
        data_date = now.strftime("%Y%m%d")

        for s in data:
            try:
                symbol = str(s.get("Code", "")).strip()
                name = str(s.get("Name", "")).strip()

                if not symbol or not name:
                    continue

                price = to_float(s.get("ClosingPrice"))
                change = to_float(s.get("Change"))
                volume = to_int(s.get("TradeVolume"))

                if price <= 0:
                    continue

                change_percent = round((change / price) * 100, 2) if price != 0 else 0.0
                prev_close = round(price - change, 2)

                score = calc_score(change_percent, volume, price)
                signal = calc_signal(change_percent, volume)

                entry_price = calc_entry_price(price)
                target_price = calc_target_price(price)
                stop_loss = calc_stop_loss(price)
                reason = calc_reason(change_percent, volume, score, signal, price)

                stocks.append({
                    "symbol": symbol,
                    "name": name,
                    "price": round(price, 2),
                    "change": round(change, 2),
                    "change_percent": change_percent,
                    "volume": volume,
                    "score": score,
                    "signal": signal,
                    "entry_price": entry_price,
                    "target_price": target_price,
                    "stop_loss": stop_loss,
                    "reason": reason,
                    "prev_close": prev_close,
                    "open": 0,
                    "high": 0,
                    "low": 0,
                    "update_time": "--",
                })
            except:
                continue

        stocks.sort(key=lambda x: (x["score"], x["change_percent"], x["volume"]), reverse=True)

        return {
            "success": True,
            "market_status": "收盤",
            "data_date": data_date,
            "last_update": last_update,
            "total": len(stocks),
            "stocks": stocks
        }

    except Exception as e:
        return {
            "success": False,
            "message": f"讀取失敗: {str(e)}",
            "stocks": []
        }
