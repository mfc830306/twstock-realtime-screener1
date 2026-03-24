from fastapi import FastAPI

app = FastAPI()

@app.get("/")
def root():
    return {"message": "API正常運作"}

@app.get("/health")
def health():
    return {"ok": True}