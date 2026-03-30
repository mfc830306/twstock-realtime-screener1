from typing import Optional
from fastapi import Query

@app.get("/top-recommendations")
def top_recommendations(
    market: Optional[str] = Query(None, description="可選: TSE / OTC / ALL / 上市 / 上櫃"),
    limit: int = Query(10, ge=1, le=50)
):
    try:
        # 取得全部股票資料
        result = get_stocks(limit=5000)

        if not result.get("success"):
            return {
                "success": False,
                "error": "無法取得股票資料",
                "total": 0,
                "stocks": []
            }

        stocks = result.get("stocks", [])

        # 市場篩選
        if market:
            market_text = str(market).strip().upper()

            if market_text in ["TSE", "上市"]:
                stocks = [s for s in stocks if s.get("market") == "上市"]
            elif market_text in ["OTC", "上櫃"]:
                stocks = [s for s in stocks if s.get("market") == "上櫃"]
            elif market_text in ["ETF"]:
                stocks = [s for s in stocks if "ETF" in str(s.get("market", "")).upper()]
            elif market_text in ["ALL", "全部"]:
                pass

        # 排除沒有分數的資料
        valid_stocks = []
        for s in stocks:
            try:
                score = float(s.get("score", 0))
                s["score"] = round(score, 2)
                valid_stocks.append(s)
            except:
                continue

        # 依分數排序，取前 N 檔
        valid_stocks.sort(key=lambda x: x.get("score", 0), reverse=True)
        top_stocks = valid_stocks[:limit]

        return {
            "success": True,
            "market": market if market else "ALL",
            "total": len(top_stocks),
            "stocks": top_stocks
        }

    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "total": 0,
            "stocks": []
        }
