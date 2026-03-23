from pathlib import Path
from fastapi import FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import pandas as pd
import requests
import urllib3
from requests.exceptions import RequestException

app = FastAPI(title="台股API完整版")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

BASE_DIR = Path(__file__).resolve().parent
CSV_FILE = BASE_DIR / "tw_stock_listed_otc_database.csv"


def load_stocks_df() -> pd.DataFrame:
    df = pd.read_csv(CSV_FILE, encoding="utf-8-sig")
    df["stock_code"] = df["stock_code"].astype(str)
    df["stock_name"] = df["stock_name"].astype(str)
    df["market"] = df["market"].astype(str)
    df["industry_category"] = df["industry_category"].astype(str)
    return df


def to_yahoo_symbol(code: str, market: str) -> str:
    return f"{code}.TW" if market == "上市" else f"{code}.TWO"


def fetch_yahoo_quotes(symbols: list[str]) -> dict:
    if not symbols:
        return {}

    url = "https://query1.finance.yahoo.com/v7/finance/quote"
    params = {"symbols": ",".join(symbols)}

    try:
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

        r = requests.get(
            url,
            params=params,
            timeout=10,
            verify=False,
            headers={"User-Agent": "Mozilla/5.0"},
        )
        r.raise_for_status()
        data = r.json()

        result = {}
        for item in data.get("quoteResponse", {}).get("result", []):
            result[item.get("symbol")] = {
                "price": item.get("regularMarketPrice"),
                "change": item.get("regularMarketChange"),
                "change_percent": item.get("regularMarketChangePercent"),
                "open": item.get("regularMarketOpen"),
                "high": item.get("regularMarketDayHigh"),
                "low": item.get("regularMarketDayLow"),
                "volume": item.get("regularMarketVolume"),
                "prev_close": item.get("regularMarketPreviousClose"),
                "market_time": item.get("regularMarketTime"),
            }
        return result

    except RequestException as e:
        print("Yahoo 報價抓取失敗：", e)
        return {}
    except Exception as e:
        print("Yahoo 報價解析失敗：", e)
        return {}


@app.get("/")
def home():
    return {"message": "API正常運作"}


@app.get("/api/stocks")
def get_stocks(
    keyword: str = Query(default=""),
    industry: str = Query(default="全部"),
    limit: int = Query(default=2000),
):
    df = load_stocks_df()

    if keyword.strip():
        k = keyword.strip().lower()
        mask = (
            df["stock_code"].str.lower().str.contains(k, na=False)
            | df["stock_name"].str.lower().str.contains(k, na=False)
            | df["market"].str.lower().str.contains(k, na=False)
            | df["industry_category"].str.lower().str.contains(k, na=False)
        )
        df = df[mask]

    if industry.strip() and industry != "全部":
        df = df[df["industry_category"] == industry]

    df = df.head(limit).copy()
    df["price"] = None
    df["change"] = None

    return df.to_dict(orient="records")


@app.get("/api/industries")
def get_industries():
    df = load_stocks_df()
    industries = sorted(df["industry_category"].dropna().unique().tolist())
    return ["全部"] + industries


@app.get("/api/stock_detail")
def get_stock_detail(code: str = Query(...)):
    df = load_stocks_df()
    row = df[df["stock_code"] == str(code)]

    if row.empty:
        raise HTTPException(status_code=404, detail="找不到股票代號")

    item = row.iloc[0]
    symbol = to_yahoo_symbol(item["stock_code"], item["market"])
    quotes = fetch_yahoo_quotes([symbol])
    quote = quotes.get(symbol, {})

    return {
        "stock_code": item["stock_code"],
        "stock_name": item["stock_name"],
        "market": item["market"],
        "industry_category": item["industry_category"],
        "price": quote.get("price"),
        "change": quote.get("change"),
        "change_percent": quote.get("change_percent"),
        "open": quote.get("open"),
        "high": quote.get("high"),
        "low": quote.get("low"),
        "volume": quote.get("volume"),
        "prev_close": quote.get("prev_close"),
        "market_time": quote.get("market_time"),
    }


@app.get("/api/recommend/short")
def get_short_recommend():
    base = [
        {
            "stock_code": "3231",
            "stock_name": "緯創",
            "market": "上市",
            "industry_category": "AI伺服器",
            "entry_price": 105,
            "target_price": 110,
            "stop_loss": 101,
            "reason": "AI伺服器族群偏強，量價結構佳，適合短線觀察。",
        },
        {
            "stock_code": "2382",
            "stock_name": "廣達",
            "market": "上市",
            "industry_category": "AI伺服器",
            "entry_price": 260,
            "target_price": 272,
            "stop_loss": 254,
            "reason": "趨勢偏多，族群續強，短線有延續機會。",
        },
        {
            "stock_code": "3017",
            "stock_name": "奇鋐",
            "market": "上市",
            "industry_category": "散熱",
            "entry_price": 560,
            "target_price": 585,
            "stop_loss": 545,
            "reason": "散熱族群強勢，短線動能延續。",
        },
        {
            "stock_code": "3037",
            "stock_name": "欣興",
            "market": "上市",
            "industry_category": "PCB",
            "entry_price": 168,
            "target_price": 176,
            "stop_loss": 163,
            "reason": "PCB族群回溫，技術面轉強。",
        },
        {
            "stock_code": "2603",
            "stock_name": "長榮",
            "market": "上市",
            "industry_category": "航運",
            "entry_price": 220,
            "target_price": 230,
            "stop_loss": 214,
            "reason": "航運族群轉強，籌碼結構穩定。",
        },
    ]

    symbols = [to_yahoo_symbol(item["stock_code"], item["market"]) for item in base]
    quotes = fetch_yahoo_quotes(symbols)

    result = []
    for item in base:
        symbol = to_yahoo_symbol(item["stock_code"], item["market"])
        quote = quotes.get(symbol, {})

        result.append({
            **item,
            "price": quote.get("price"),
            "change": quote.get("change"),
            "change_percent": quote.get("change_percent"),
        })

    return result