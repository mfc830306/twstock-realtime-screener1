import os
import time
import threading
from datetime import datetime
from typing import Any, Dict, List

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

try:
    from fubon_neo.sdk import FubonSDK
except Exception as e:
    FubonSDK = None
    SDK_IMPORT_ERROR = str(e)
else:
    SDK_IMPORT_ERROR = None


app = FastAPI(title="TW Stock Realtime Screener with Fubon API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# =========================
# 基本設定
# =========================
WATCHLIST = ["2330", "2317", "2454", "1301", "1802"]

# 建議把帳密放到 Render Environment
FUBON_ID = os.getenv("FUBON_ID", "").strip()
FUBON_PWD = os.getenv("FUBON_PWD", "").strip()
FUBON_CERT_PWD = os.getenv("FUBON_CERT_PWD", "").strip()

# 支援多種可能路徑，避免 Render / 本機工作目錄不同
CERT_CANDIDATES = [
    "backend/certs/API_20270327.p12",
    "certs/API_20270327.p12",
    "./backend/certs/API_20270327.p12",
    "./certs/API_20270327.p12",
]

# =========================
# 全域狀態
# =========================
state: Dict[str, Any] = {
    "success": False,
    "market_status": "初始化中",
    "data_date": "",
    "last_update": "",
    "message": "尚未啟動",
    "subscribed": [],
    "cert_path": "",
    "cert_exists": False,
    "cert_size": 0,
    "sdk_import_ok": FubonSDK is not None,
    "sdk_import_error": SDK_IMPORT_ERROR,
}

latest_stocks: List[Dict[str, Any]] = []
sdk = None
sdk_accounts = None
login_started = False


# =========================
# 工具函式
# =========================
def now_str() -> str:
    return datetime.now().strftime("%Y/%m/%d %H:%M:%S")


def resolve_cert_path() -> str:
    for path in CERT_CANDIDATES:
        if os.path.exists(path):
            return path
    return CERT_CANDIDATES[0]


def update_cert_debug() -> str:
    cert_path = resolve_cert_path()
    state["cert_path"] = cert_path
    state["cert_exists"] = os.path.exists(cert_path)
    state["cert_size"] = os.path.getsize(cert_path) if os.path.exists(cert_path) else 0
    return cert_path


def debug_print_startup() -> None:
    cert_path = update_cert_debug()
    print("=" * 60)
    print("【FUBON DEBUG】啟動檢查")
    print("目前工作目錄:", os.getcwd())
    print("Python 檔位置:", __file__)
    print("SDK 可用:", state["sdk_import_ok"])
    if not state["sdk_import_ok"]:
        print("SDK import error:", state["sdk_import_error"])
    print("憑證路徑:", cert_path)
    print("憑證存在:", state["cert_exists"])
    print("憑證大小(bytes):", state["cert_size"])
    print("FUBON_ID 有值:", bool(FUBON_ID))
    print("FUBON_PWD 有值:", bool(FUBON_PWD))
    print("FUBON_CERT_PWD 有值:", bool(FUBON_CERT_PWD))
    print("=" * 60)


# =========================
# 富邦登入流程
# =========================
def try_login_fubon() -> None:
    global sdk, sdk_accounts, login_started

    if login_started:
        return

    login_started = True
    debug_print_startup()

    while True:
        try:
            cert_path = update_cert_debug()
            state["last_update"] = now_str()

            if FubonSDK is None:
                state["success"] = False
                state["market_status"] = "初始化失敗"
                state["message"] = f"FubonSDK 匯入失敗: {state['sdk_import_error']}"
                print(state["message"])
                time.sleep(10)
                continue

            if not FUBON_ID or not FUBON_PWD or not FUBON_CERT_PWD:
                state["success"] = False
                state["market_status"] = "等待設定"
                state["message"] = "缺少 Render 環境變數：FUBON_ID / FUBON_PWD / FUBON_CERT_PWD"
                print(state["message"])
                time.sleep(10)
                continue

            if not os.path.exists(cert_path):
                state["success"] = False
                state["market_status"] = "初始化中"
                state["message"] = f"富邦連線失敗，10 秒後重試: cert file not found ({cert_path})"
                print(state["message"])
                time.sleep(10)
                continue

            if os.path.getsize(cert_path) <= 0:
                state["success"] = False
                state["market_status"] = "初始化中"
                state["message"] = f"富邦連線失敗，10 秒後重試: cert file empty ({cert_path})"
                print(state["message"])
                time.sleep(10)
                continue

            print("準備登入富邦...")
            print("帳號:", FUBON_ID)
            print("憑證:", cert_path)

            sdk = FubonSDK()
            sdk_accounts = sdk.login(FUBON_ID, FUBON_PWD, cert_path, FUBON_CERT_PWD)

            # 有些版本 login 成功後 accounts.data 會有內容
            account_count = 0
            if sdk_accounts is not None and hasattr(sdk_accounts, "data") and sdk_accounts.data:
                account_count = len(sdk_accounts.data)

            state["success"] = True
            state["market_status"] = "已登入"
            state["message"] = f"富邦登入成功，account_count={account_count}"
            state["last_update"] = now_str()
            state["subscribed"] = WATCHLIST.copy()

            print(state["message"])

            # 先做最穩定版本：登入成功即可
            # 若後面你要加 websocket 訂閱，再接下一版
            break

        except Exception as e:
            state["success"] = False
            state["market_status"] = "初始化中"
            state["message"] = f"富邦連線失敗，10 秒後重試: {str(e)}"
            state["last_update"] = now_str()
            print(state["message"])
            time.sleep(10)


# =========================
# 啟動事件
# =========================
@app.on_event("startup")
def startup_event():
    thread = threading.Thread(target=try_login_fubon, daemon=True)
    thread.start()


# =========================
# API
# =========================
@app.get("/")
def root():
    update_cert_debug()
    return {
        "message": "TW Stock Realtime Screener with Fubon API is running",
        "status": state,
        "watchlist": WATCHLIST,
    }


@app.get("/health")
def health():
    update_cert_debug()
    return {
        "ok": True,
        "time": now_str(),
        "sdk_import_ok": state["sdk_import_ok"],
        "cert_path": state["cert_path"],
        "cert_exists": state["cert_exists"],
        "cert_size": state["cert_size"],
    }


@app.get("/status")
def get_status():
    update_cert_debug()
    return state


@app.get("/stocks")
def get_stocks():
    update_cert_debug()

    return {
        "success": state["success"],
        "market_status": state["market_status"],
        "data_date": state["data_date"],
        "last_update": state["last_update"],
        "message": state["message"],
        "total": len(latest_stocks),
        "stocks": latest_stocks,
        "watchlist": WATCHLIST,
        "cert_debug": {
            "cert_path": state["cert_path"],
            "cert_exists": state["cert_exists"],
            "cert_size": state["cert_size"],
        },
    }
