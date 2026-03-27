from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
import requests

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
    return {"message": "TWSE backend running"}

@app.get("/stocks")
def get_stocks(
    min_price: float = Query(0),
    max_price: float = Query(999999)
):
    try:
        url = "https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL"
        res = requests.get(url, timeout=20)
        res.raise_for_status()
        data = res.json()

        stocks = []

        for s in data:
            try:
                code = str(s.get("Code", "")).strip()
                name = str(s.get("Name", "")).strip()
                date = str(s.get("Date", "")).strip()
                closing_price_raw = str(s.get("ClosingPrice", "")).replace(",", "").strip()
                change_raw = str(s.get("Change", "")).replace(",", "").strip()
                volume_raw = str(s.get("TradeVolume", "")).replace(",", "").strip()

                if not code or not name or not closing_price_raw:
                    continue

                # 排除 "--" 或空值
                if closing_price_raw in ["--", "-"] or volume_raw in ["--", "-", ""]:
                    continue

                price = float(closing_price_raw)
                volume = int(float(volume_raw))

                # 有些 Change 可能不是純數字，先保守處理
                try:
                    change = float(change_raw)
                except:
                    change = 0.0

                if not (min_price <= price <= max_price):
                    continue

                yesterday_price = price - change
                if yesterday_price != 0:
                    change_percent = round((change / yesterday_price) * 100, 2)
                else:
                    change_percent = 0.0

                # 先保留你原本想要的欄位
                entry_low = round(price * 0.99, 2)
                entry_high = round(price * 1.01, 2)
                target_price = round(price * 1.05, 2)
                stop_loss = round(price * 0.97, 2)

                score = round(
                    abs(change_percent) * 8 + min(volume / 100000, 20),
                    2
                )

                signal = "偏多" if change_percent > 1 else "中性" if change_percent >= -1 else "偏空"

                stocks.append({
                    "date": date,
                    "market": "上市",
                    "symbol": code,
                    "name": name,
                    "price": price,
                    "change": round(change, 2),
                    "change_percent": change_percent,
                    "volume": volume,
                    "score": score,
                    "signal": signal,
                    "entry_price": f"{entry_low} ~ {entry_high}",
                    "target_price": str(target_price),
                    "stop_loss": str(stop_loss),
                })

            except:
                continue

        stocks.sort(key=lambda x: x["score"], reverse=True)

        return {
            "success": True,
            "source": "TWSE",
            "market": "上市",
            "total": len(stocks),
            "stocks": stocks
        }

    except Exception as e:
        return {
            "success": False,
            "source": "TWSE",
            "market": "上市",
            "error": str(e),
            "stocks": []
        }
