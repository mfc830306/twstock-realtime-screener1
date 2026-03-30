def fetch_snapshot_quotes(market: str, force: bool = False) -> Dict[str, Any]:
    ensure_fubon_ready()

    now = time.time()
    cached = snapshot_cache.get(market, {"ts": 0, "data": None})
    if not force and cached["data"] is not None and (now - cached["ts"] < CACHE_SECONDS):
        return cached["data"]

    try:
        raw = reststock.snapshot.quotes(market=market, type="ALLBUT0999")
        data = to_dict(raw)
        snapshot_cache[market] = {"ts": now, "data": data}
        return data
    except FugleAPIError as e:
        raise HTTPException(status_code=502, detail=f"富邦 snapshot 讀取失敗: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"snapshot 發生錯誤: {str(e)}")
