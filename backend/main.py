@app.get("/test-fubon")
def test_fubon():
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
            }
        }

    cert_path = "/tmp/fubon_cert.p12"

    try:
        cert_bytes = base64.b64decode(cert_base64)

        with open(cert_path, "wb") as f:
            f.write(cert_bytes)

        return {
            "success": True,
            "debug": {
                "cert_path": cert_path,
                "file_exists": os.path.exists(cert_path),
                "file_size": os.path.getsize(cert_path) if os.path.exists(cert_path) else 0
            }
        }

    except Exception as e:
        return {
            "success": False,
            "message": str(e)
        }
