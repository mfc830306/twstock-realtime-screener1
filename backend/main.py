import os
import base64
from fastapi import FastAPI
from fubon_neo.sdk import FubonSDK

app = FastAPI(title="Fubon Debug Backend")


@app.get("/")
def root():
    return {"message": "Fubon debug backend running"}


@app.get("/test-fubon")
def test_fubon():
    id_no = os.getenv("FUBON_ID")
    password = os.getenv("FUBON_PWD")
    cert_base64 = os.getenv("FUBON_CERT_BASE64")
    cert_password = os.getenv("FUBON_CERT_PWD")

    if not all([id_no, password, cert_base64, cert_password]):
        return {
            "success": False,
            "message": "環境變數不完整",
            "debug": {
                "has_id": bool(id_no),
                "has_password": bool(password),
                "has_cert_base64": bool(cert_base64),
                "has_cert_password": bool(cert_password),
            },
        }

    cert_path = "/tmp/fubon_cert.p12"

    try:
        cert_bytes = base64.b64decode(cert_base64)

        with open(cert_path, "wb") as f:
            f.write(cert_bytes)

        file_exists = os.path.exists(cert_path)
        file_size = os.path.getsize(cert_path) if file_exists else 0

        # 先只測試檔案有沒有成功還原
        return {
            "success": True,
            "debug": {
                "cert_path": cert_path,
                "file_exists": file_exists,
                "file_size": file_size,
            },
        }

    except Exception as e:
        return {
            "success": False,
            "message": str(e),
        }


@app.get("/test-fubon-login")
def test_fubon_login():
    sdk = FubonSDK()

    id_no = os.getenv("FUBON_ID")
    password = os.getenv("FUBON_PWD")
    cert_base64 = os.getenv("FUBON_CERT_BASE64")
    cert_password = os.getenv("FUBON_CERT_PWD")

    if not all([id_no, password, cert_base64, cert_password]):
        return {
            "success": False,
            "message": "環境變數不完整",
            "debug": {
                "has_id": bool(id_no),
                "has_password": bool(password),
                "has_cert_base64": bool(cert_base64),
                "has_cert_password": bool(cert_password),
            },
        }

    cert_path = "/tmp/fubon_cert.p12"

    try:
        cert_bytes = base64.b64decode(cert_base64)

        with open(cert_path, "wb") as f:
            f.write(cert_bytes)

        accounts = sdk.login(id_no, password, cert_path, cert_password)

        if not accounts.is_success:
            return {
                "success": False,
                "message": accounts.message,
            }

        sdk.init_realtime()
        reststock = sdk.marketdata.rest_client.stock
        res = reststock.intraday.quote(symbol="2330")

        return {
            "success": True,
            "stock": {
                "symbol": res.get("symbol"),
                "name": res.get("name"),
                "price": res.get("lastPrice"),
                "change": res.get("change"),
                "change_percent": res.get("changePercent"),
                "open": res.get("openPrice"),
                "high": res.get("highPrice"),
                "low": res.get("lowPrice"),
                "volume": res.get("total", {}).get("tradeVolume", 0),
                "market": res.get("market"),
                "date": res.get("date"),
            },
        }

    except Exception as e:
        return {
            "success": False,
            "message": str(e),
        }

    finally:
        try:
            sdk.logout()
        except Exception:
            pass
