from fastapi import FastAPI

app = FastAPI()


@app.get("/")
def root():
    return {"message": "backend running"}


@app.get("/test-fubon")
def test_fubon():
    return {
        "success": True,
        "message": "Fubon API route is working"
    }
