from fastapi import FastAPI
import requests

app = FastAPI()

@app.get("/")
def root():
    return {"message": "backend running"}

@app.get("/stocks")
def get_stocks():
    try:
        url = "https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL"
        res = requests.get(url, timeout=10)
        data = res.json()

        stocks = []

        for s in data:
            try:
                price = float(s["ClosingPrice"])
                change = float(s["Change"])
                volume = int(s["TradeVolume"])

                change_percent = (change / price) * 100 if price != 0 else 0

                stocks.append({
                    "symbol": s["Code"],
                    "name": s["Name"],
                    "price": price,
                    "change_percent": round(change_percent, 2),
                    "volume": volume,
                    "score": round(abs(change) * 10, 2),
                })
            except:
                continue

        return {
            "success": True,
            "total": len(stocks),
            "stocks": stocks
        }

    except Exception as e:
        return {"success": False, "error": str(e), "stocks": []}
