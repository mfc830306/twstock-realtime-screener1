from fastapi import FastAPI
from fubon_neo.sdk import FubonSDK

app = FastAPI()

@app.get("/")
def root():
    return {"message": "Fubon backend running"}

@app.get("/test-stock")
def test_stock():
    sdk = FubonSDK()

    id_no = "J122755718"
    password = "Aa0982601962"
    cert_path = r"D:\富邦API\API_20270327.p12"
    cert_password = "a0982601962"

    try:
        accounts = sdk.login(id_no, password, cert_path, cert_password)

        if not accounts.is_success:
            return {
                "success": False,
                "message": accounts.message
            }

        sdk.init_realtime()

        reststock = sdk.marketdata.rest_client.stock
        res = reststock.intraday.quote(symbol="2330")

        return {
            "success": True,
            "stock": res
        }

    except Exception as e:
        return {
            "success": False,
            "message": str(e)
        }

    finally:
        try:
            sdk.logout()
        except:
            pass
