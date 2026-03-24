def analyze_stock(stock):
    score = 0

    price = stock["price"]
    ma5 = stock["ma5"]
    ma20 = stock["ma20"]
    volume = stock["volume"]

    # 趨勢
    if price > ma5:
        score += 20
    if price > ma20:
        score += 20

    # 均線排列
    if ma5 > ma20:
        score += 20

    # 成交量（簡化）
    if volume > 1000:
        score += 10

    # 動能
    if stock["change_percent"] > 0:
        score += 10

    # 🔥 趨勢分類
    if score >= 70:
        trend = "強勢"
    elif score >= 40:
        trend = "中性"
    else:
        trend = "弱勢"

    # 🔥 進出場策略
    entry_low = round(ma5 * 0.98, 2)
    entry_high = round(ma5 * 1.02, 2)

    take_profit = round(price * 1.1, 2)
    stop_loss = round(price * 0.95, 2)

    return {
        "symbol": stock["symbol"],
        "name": stock["name"],
        "price": price,
        "score": score,
        "entry_range": f"{entry_low} ~ {entry_high}",
        "take_profit": take_profit,
        "stop_loss": stop_loss,
        "trend": trend
    }
