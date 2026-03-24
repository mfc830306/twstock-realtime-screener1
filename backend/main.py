from fastapi import FastAPI

app = FastAPI()

@app.get("/")
def root():
    return {"message": "API正常運作"}

@app.get("/health")
def health():
    return {"ok": True}

@app.get("/stocks/{stock_id}")
def get_stock(stock_id: str):
    return {
        "stock_id": stock_id,
        "name": "測試股票",
        "price": 100
    }