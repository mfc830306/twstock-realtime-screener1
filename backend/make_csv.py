import csv
import twstock

output_path = "tw_stock_listed_otc_database.csv"

rows = []

for code, info in twstock.codes.items():
    if info.market in ("上市", "上櫃") and info.type == "股票":
        rows.append({
            "stock_code": info.code,
            "stock_name": info.name,
            "market": info.market,
            "industry_category": info.group,
        })

rows.sort(key=lambda x: (x["market"], x["stock_code"]))

with open(output_path, "w", newline="", encoding="utf-8-sig") as f:
    writer = csv.DictWriter(
        f,
        fieldnames=["stock_code", "stock_name", "market", "industry_category"]
    )
    writer.writeheader()
    writer.writerows(rows)

print("完成！總筆數：", len(rows))