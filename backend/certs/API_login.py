import os
from fubon_neo.sdk import FubonSDK

cert_path = r"D:\富邦API\API_20270327.p12"

print("憑證路徑:", cert_path)
print("檔案存在:", os.path.exists(cert_path))

sdk = FubonSDK()

result = sdk.login(
    "J122755718",
    "Aa0982601962",
    cert_path,
    "a0982601962"
)

print("登入結果:", result.is_success)
print("訊息:", result.message)

if result.is_success:
    print("✅ 登入成功")
else:
    print("❌ 登入失敗")