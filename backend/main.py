from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import yfinance as yf
import pandas as pd
from typing import Optional, List

app = FastAPI(title="TW Stock Screener API")


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ScanRequest(BaseModel):
    symbols: Optional[List[str]] = None


# 先用大型權值 + 常見熱門股當預設池
# 之後你要我再幫你升級成全台股版
DEFAULT_STOCKS = [
    "2330.TW", "2317.TW", "2454.TW", "2303.TW", "2603.TW",
    "1301.TW", "1802.TW", "2882.TW", "2881.TW", "2891.TW",
    "1101.TW", "1216.TW", "2002.TW", "3008.TW", "3034.TW",
    "3711.TW", "5880.TW", "5871.TW", "2382.TW", "2327.TW",
    "2408.TW", "2886.TW", "6505.TW", "2207.TW", "2615.TW",
    "4904.TW", "3481.TW", "2357.TW", "2379.TW", "8069.TWO"
]


STOCK_NAME_MAP = {
    "2330": "台積電",
    "2317": "鴻海",
    "2454": "聯發科",
    "2303": "聯電",
    "2603": "長榮",
    "1301": "台塑",
    "1802": "台玻",
    "2882": "國泰金",
    "2881": "富邦金",
    "2891": "中信金",
    "1101": "台泥",
    "1216": "統一",
    "2002": "中鋼",
    "3008": "大立光",
    "3034": "聯詠",
    "3711": "日月光投控",
    "5880": "合庫金",
    "5871": "中租-KY",
    "2382": "廣達",
    "2327": "國巨",
    "2408": "南亞科",
    "2886": "兆豐金",
    "6505": "台塑化",
    "2207": "和泰車",
    "2615": "萬海",
    "4904": "遠傳",
    "3481": "群創",
    "2357": "華碩",
    "2379": "瑞昱",
    "8069": "元太",
}


def normalize_symbol(symbol: str) -> str:
    symbol = symbol.strip().upper()
    if not symbol:
        return ""
    if symbol.endswith(".TW") or symbol.endswith(".TWO"):
        return symbol
    # 先預設上市
    return f"{symbol}.TW"


def get_stock_name(symbol: str) -> str:
    code = symbol.replace(".TW", "").replace(".TWO", "")
    return STOCK_NAME_MAP.get(code, code)


def safe_float(v, default=0.0):
    try:
        if pd.isna(v):
            return default
        return float(v)
    except:
        return default


def analyze_stock(symbol: str):
    try:
        df = yf.download(symbol, period="3mo", interval="1d", progress=False, auto_adjust=False)

        if df.empty or len(df) < 25:
            return None

        close_series = df["Close"]
        volume_series = df["Volume"]

        if isinstance(close_series, pd.DataFrame):
            close_series = close_series.iloc[:, 0]
        if isinstance(volume_series, pd.DataFrame):
            volume_series = volume_series.iloc[:, 0]

        close_series = close_series.dropna()
        volume_series = volume_series.dropna()

        if len(close_series) < 25 or len(volume_series) < 25:
            return None

        price = safe_float(close_series.iloc[-1])
        prev_price = safe_float(close_series.iloc[-2])
        ma5 = safe_float(close_series.rolling(5).mean().iloc[-1])
        ma10 = safe_float(close_series.rolling(10).mean().iloc[-1])
        ma20 = safe_float(close_series.rolling(20).mean().iloc[-1])
        vol = safe_float(volume_series.iloc[-1])
        vol5 = safe_float(volume_series.rolling(5).mean().iloc[-1])

        if prev_price == 0:
            change_percent = 0
        else:
            change_percent = round((price - prev_price) / prev_price * 100, 2)

        score = 0
        reasons = []

        # 價格在均線之上
        if price > ma5:
            score += 2
            reasons.append("站上MA5")
        if price > ma10:
            score += 2
            reasons.append("站上MA10")
        if price > ma20:
            score += 3
            reasons.append("站上MA20")

        # 均線多頭排列
        if ma5 > ma10:
            score += 1
            reasons.append("MA5大於MA10")
        if ma10 > ma20:
            score += 2
            reasons.append("MA10大於MA20")

        # 量能
        if vol > vol5:
            score += 2
            reasons.append("成交量高於5日均量")

        # 當日動能
        if change_percent > 0:
            score += 1
            reasons.append("今日收漲")
        if change_percent > 3:
            score += 1
            reasons.append("漲幅大於3%")

        # 訊號分類
        if score >= 10:
            signal = "強勢多方"
        elif score >= 6:
            signal = "偏多觀察"
        else:
            signal = "中性"

        entry_price = round(price, 2)
        stop_loss = round(price * 0.97, 2)
        target_price = round(price * 1.05, 2)

        return {
            "symbol": symbol.replace(".TW", "").replace(".TWO", ""),
            "name": get_stock_name(symbol),
            "price": round(price, 2),
            "change_percent": change_percent,
            "volume": int(vol),
            "ma5": round(ma5, 2),
            "ma10": round(ma10, 2),
            "ma20": round(ma20, 2),
            "signal": signal,
            "score": score,
            "reason": "、".join(reasons) if reasons else "無明確訊號",
            "entry_price": entry_price,
            "stop_loss": stop_loss,
            "target_price": target_price,
        }

    except Exception as e:
        return {
            "symbol": symbol.replace(".TW", "").replace(".TWO", ""),
            "name": get_stock_name(symbol),
            "price": 0,
            "change_percent": 0,
            "volume": 0,
            "ma5": 0,
            "ma10": 0,
            "ma20": 0,
            "signal": "資料錯誤",
            "score": 0,
            "reason": f"錯誤: {str(e)}",
            "entry_price": 0,
            "stop_loss": 0,
            "target_price": 0,
        }


@app.get("/")
def root():
    return {
        "message": "TW Stock Screener API is running",
        "mode": "default pool top 10"
    }


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/scan")
def scan_stocks(req: ScanRequest):
    raw_symbols = req.symbols if req.symbols else []

    # 有輸入就分析輸入
    # 沒輸入就掃預設池
    if raw_symbols:
        symbols = []
        for s in raw_symbols:
            s = normalize_symbol(s)
            if s:
                symbols.append(s)
    else:
        symbols = DEFAULT_STOCKS

    results = []
    for symbol in symbols:
        r = analyze_stock(symbol)
        if r:
            results.append(r)

    results = sorted(
        results,
        key=lambda x: (x["score"], x["change_percent"], x["volume"]),
        reverse=True
    )[:10]

    return results