from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import List, Optional, Dict
import yfinance as yf
import requests
import time

app = FastAPI(title="Taiwan Stock Screener API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 官方資料來源：
# TWSE OpenAPI / TPEx OpenAPI
TWSE_STOCK_LIST_URL = "https://openapi.twse.com.tw/v1/opendata/t187ap03_L"
TPEX_OTC_LIST_URL = "https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap03_O"
TPEX_ESB_LIST_URL = "https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap03_R"

# 啟動後動態載入的股票名稱表
STOCK_NAMES: Dict[str, str] = {}

# 少量預設備援，避免官方清單暫時失敗時整個沒中文
FALLBACK_STOCK_NAMES = {
    "2330": "台積電",
    "2317": "鴻海",
    "2454": "聯發科",
    "2303": "聯電",
    "2603": "長榮",
    "1301": "台塑",
    "1802": "台玻",
}

_LAST_REFRESH_TS = 0.0
_REFRESH_INTERVAL_SECONDS = 60 * 60 * 6  # 6 小時更新一次


class ScanRequest(BaseModel):
    symbols: List[str] = Field(
        default=["2330", "2317", "2454", "2303", "2603", "1301", "1802"]
    )


class StockResult(BaseModel):
    symbol: str
    name: str
    price: Optional[float]
    change_percent: Optional[float]
    volume: Optional[int]
    ma5: Optional[float]
    ma20: Optional[float]
    signal: str
    reason: str


def normalize_symbol(symbol: str) -> str:
    symbol = symbol.strip().replace(".TW", "").replace(".TWO", "")
    if symbol.isdigit():
        return f"{symbol}.TW"
    return symbol


def get_stock_code(symbol: str) -> str:
    return symbol.replace(".TW", "").replace(".TWO", "").strip()


def get_stock_name(stock_code: str) -> str:
    return STOCK_NAMES.get(stock_code, FALLBACK_STOCK_NAMES.get(stock_code, stock_code))


def _safe_get_json(url: str):
    resp = requests.get(url, timeout=20)
    resp.raise_for_status()
    return resp.json()


def _extract_code_name(records: list) -> Dict[str, str]:
    result: Dict[str, str] = {}

    # 官方欄位名稱偶爾會有差異，所以做容錯
    code_keys = ["公司代號", "股票代號", "代號", "SecuritiesCompanyCode", "Code"]
    name_keys = ["公司簡稱", "公司名稱", "名稱", "CompanyName", "Name"]

    for row in records:
        if not isinstance(row, dict):
            continue

        code = None
        name = None

        for k in code_keys:
            if k in row and str(row[k]).strip():
                code = str(row[k]).strip()
                break

        for k in name_keys:
            if k in row and str(row[k]).strip():
                name = str(row[k]).strip()
                break

        if code and name and code.isdigit():
            result[code] = name

    return result


def refresh_stock_names(force: bool = False) -> int:
    global STOCK_NAMES, _LAST_REFRESH_TS

    now = time.time()
    if not force and STOCK_NAMES and (now - _LAST_REFRESH_TS < _REFRESH_INTERVAL_SECONDS):
        return len(STOCK_NAMES)

    merged: Dict[str, str] = {}

    urls = [
        TWSE_STOCK_LIST_URL,   # 上市
        TPEX_OTC_LIST_URL,     # 上櫃
        TPEX_ESB_LIST_URL,     # 興櫃
    ]

    for url in urls:
        try:
            data = _safe_get_json(url)
            merged.update(_extract_code_name(data))
        except Exception:
            # 某一個來源失敗時，不要讓整個 API 掛掉
            continue

    # 保障至少有基本名稱
    merged.update(FALLBACK_STOCK_NAMES)

    STOCK_NAMES = merged
    _LAST_REFRESH_TS = now
    return len(STOCK_NAMES)


@app.on_event("startup")
def startup_load_stock_names():
    refresh_stock_names(force=True)


def fetch_stock_data(symbol: str):
    tw_symbol = normalize_symbol(symbol)
    stock_code = get_stock_code(tw_symbol)
    stock_name = get_stock_name(stock_code)

    try:
        ticker = yf.Ticker(tw_symbol)
        hist = ticker.history(period="3mo")

        if hist.empty:
            return {
                "symbol": stock_code,
                "name": stock_name,
                "price": None,
                "change_percent": None,
                "volume": None,
                "ma5": None,
                "ma20": None,
                "error": "查無歷史資料",
            }

        hist = hist.dropna().copy()
        if len(hist) < 20:
            return {
                "symbol": stock_code,
                "name": stock_name,
                "price": None,
                "change_percent": None,
                "volume": None,
                "ma5": None,
                "ma20": None,
                "error": "歷史資料不足 20 筆",
            }

        close = hist["Close"]
        volume = hist["Volume"]

        latest_close = float(close.iloc[-1])
        prev_close = float(close.iloc[-2])
        latest_volume = int(volume.iloc[-1])

        ma5 = float(close.tail(5).mean())
        ma20 = float(close.tail(20).mean())

        change_percent = round((latest_close - prev_close) / prev_close * 100, 2)

        return {
            "symbol": stock_code,
            "name": stock_name,
            "price": round(latest_close, 2),
            "change_percent": change_percent,
            "volume": latest_volume,
            "ma5": round(ma5, 2),
            "ma20": round(ma20, 2),
        }

    except Exception as e:
        return {
            "symbol": stock_code,
            "name": stock_name,
            "price": None,
            "change_percent": None,
            "volume": None,
            "ma5": None,
            "ma20": None,
            "error": str(e),
        }


def analyze_stock(data: dict) -> StockResult:
    if "error" in data and data["error"]:
        return StockResult(
            symbol=data["symbol"],
            name=data["name"],
            price=data["price"],
            change_percent=data["change_percent"],
            volume=data["volume"],
            ma5=data["ma5"],
            ma20=data["ma20"],
            signal="錯誤",
            reason=f"抓取失敗: {data['error']}",
        )

    price = data["price"]
    ma5 = data["ma5"]
    ma20 = data["ma20"]
    volume = data["volume"]
    change_percent = data["change_percent"]

    signal = "觀察"
    reasons = []

    if price is not None and ma5 is not None and ma20 is not None:
        if price > ma5 > ma20:
            signal = "偏多"
            reasons.append("股價站上 MA5 與 MA20")
        elif price < ma5 < ma20:
            signal = "偏空"
            reasons.append("股價跌破 MA5 與 MA20")
        else:
            reasons.append("均線排列不明確")

    if change_percent is not None:
        if change_percent > 3:
            reasons.append("當日漲幅偏強")
        elif change_percent < -3:
            reasons.append("當日跌幅偏弱")
        else:
            reasons.append("當日波動中性")

    if volume is not None:
        if volume > 3_000_000:
            reasons.append("成交量活躍")
        else:
            reasons.append("成交量普通")

    return StockResult(
        symbol=data["symbol"],
        name=data["name"],
        price=price,
        change_percent=change_percent,
        volume=volume,
        ma5=ma5,
        ma20=ma20,
        signal=signal,
        reason="、".join(reasons),
    )


@app.get("/")
def root():
    return {
        "message": "Taiwan Stock Screener API is running",
        "endpoints": ["/health", "/scan", "/stock-names/status"],
    }


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/stock-names/status")
def stock_names_status():
    count = refresh_stock_names(force=False)
    return {
        "loaded_count": count,
        "sample": {
            "2330": get_stock_name("2330"),
            "2317": get_stock_name("2317"),
            "1802": get_stock_name("1802"),
        },
    }


@app.post("/scan", response_model=List[StockResult])
def scan_stocks(request: ScanRequest):
    refresh_stock_names(force=False)

    results = []
    for symbol in request.symbols:
        stock_data = fetch_stock_data(symbol)
        analyzed = analyze_stock(stock_data)
        results.append(analyzed)

    priority = {"偏多": 0, "觀察": 1, "偏空": 2, "錯誤": 3}
    results.sort(key=lambda x: priority.get(x.signal, 99))
    return results