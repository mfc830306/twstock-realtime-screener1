def build_recommendations(stocks: List[Dict[str, Any]], top_n: int = 10) -> List[Dict[str, Any]]:
    """
    🔥 正式版推薦引擎（升級版）
    - 趨勢過濾
    - 評級加權
    - 流動性過濾
    """

    def is_strong_signal(s):
        return s.get("signal") in {
            "強勢主升",
            "主升段延續",
            "放量突破",
            "多方控盤",
            "趨勢續強",
            "多頭趨勢",
            "轉強反彈",
        }

    def calc_final_score(s):
        base = safe_float(s.get("recommendation_score"), 0)

        volume = safe_int(s.get("volume"), 0)
        vol_score = min(volume / 3000, 20)

        momentum = abs(safe_float(s.get("change_percent"), 0)) * 2

        rating_bonus = {
            "A": 20,
            "B+": 12,
            "C": 5,
            "D": 0,
        }.get(s.get("operation_rating"), 0)

        trend_bonus = 0
        signal = s.get("signal")

        if signal in {"強勢主升", "主升段延續"}:
            trend_bonus = 25
        elif signal in {"放量突破", "多頭趨勢"}:
            trend_bonus = 18
        elif signal == "轉強反彈":
            trend_bonus = 10

        return round(base * 1.2 + vol_score + momentum + rating_bonus + trend_bonus, 2)

    # 🔥 過濾條件（重點）
    candidates = [
        s for s in stocks
        if is_main_board_stock(s)
        and safe_float(s.get("price")) > 5
        and safe_int(s.get("volume")) > 2000
        and is_strong_signal(s)
    ]

    # fallback
    if len(candidates) < top_n:
        candidates = [
            s for s in stocks
            if is_main_board_stock(s)
            and safe_float(s.get("price")) > 5
        ]

    candidates.sort(
        key=lambda x: (
            calc_final_score(x),
            x.get("volume", 0),
            abs(x.get("change_percent", 0)),
        ),
        reverse=True,
    )

    top_items = candidates[:top_n]

    result_map: Dict[str, Dict[str, Any]] = {}
    with ThreadPoolExecutor(max_workers=5) as executor:
        future_to_symbol = {
            executor.submit(build_historical_analysis_for_stock, stock): stock["symbol"]
            for stock in top_items
        }

        for future in as_completed(future_to_symbol):
            symbol = future_to_symbol[future]
            try:
                result_map[symbol] = future.result()
            except Exception:
                original = next((s for s in top_items if s["symbol"] == symbol), None)
                if original:
                    result_map[symbol] = original

    return [result_map[s["symbol"]] for s in top_items if s["symbol"] in result_map]
