from fastapi import FastAPI
import os
import base64

app = FastAPI()


@app.get("/")
def root():
    return {"message": "backend running"}


@app.get("/test-fubon-cert")
def test_fubon_cert():
    try:
        b64 = os.getenv("FUBON_CERT_BASE64")

        if not b64:
            return {
                "success": False,
                "error": "缺少 FUBON_CERT_BASE64"
            }

        cert_path = "/tmp/fubon_cert.p12"

        with open(cert_path, "wb") as f:
            f.write(base64.b64decode(b64))

        return {
            "success": True,
            "debug": {
                "cert_path": cert_path,
                "file_exists": os.path.exists(cert_path),
                "file_size": os.path.getsize(cert_path)
            }
        }

    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }


@app.get("/test-fubon-login")
def test_fubon_login():
    try:
        from fubon_neo.sdk import FubonSDK

        person_id = os.getenv("FUBON_PERSON_ID")
        password = os.getenv("FUBON_PASSWORD")
        cert_password = os.getenv("FUBON_CERT_PASSWORD")
        cert_b64 = os.getenv("FUBON_CERT_BASE64")

        missing = []
        if not person_id:
            missing.append("FUBON_PERSON_ID")
        if not password:
            missing.append("FUBON_PASSWORD")
        if not cert_password:
            missing.append("FUBON_CERT_PASSWORD")
        if not cert_b64:
            missing.append("FUBON_CERT_BASE64")

        if missing:
            return {
                "success": False,
                "error": f"缺少環境變數: {', '.join(missing)}"
            }

        cert_path = "/tmp/fubon_cert.p12"
        with open(cert_path, "wb") as f:
            f.write(base64.b64decode(cert_b64))

        sdk = FubonSDK()
        result = sdk.login(
            person_id,
            password,
            cert_path,
            cert_password
        )

        result_data = getattr(result, "data", None)
        result_message = getattr(result, "message", None)
        result_success = getattr(result, "is_success", None)

        return {
            "success": True,
            "login_result": {
                "is_success": result_success,
                "message": result_message,
                "has_data": result_data is not None,
                "data": str(result_data) if result_data is not None else None
            },
            "debug": {
                "cert_path": cert_path,
                "file_exists": os.path.exists(cert_path),
                "file_size": os.path.getsize(cert_path)
            }
        }

    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }
