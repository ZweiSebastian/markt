import json, requests
import yfinance as yf
H = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"}
out = {}
def get(code, var):
    u = (f"https://app2.msci.com/products/service/index/indexmaster/getLevelDataForGraph?currency_symbol=USD"
         f"&index_variant={var}&start_date=19981231&end_date=20261023&data_frequency=END_OF_MONTH&index_codes={code}")
    r = requests.get(u, timeout=90, headers=H)
    try:
        lv = r.json()["indexes"]["INDEX_LEVELS"]; return {str(x["calc_date"]): x["level_eod"] for x in lv}
    except Exception:
        return {"raw": r.text[:300]}
for code in ["990100", "891800", "939200", "990500", "106331", "106332", "984000", "991000", "990300"]:
    for var in ["GRTR", "STRD"]:
        out[f"msci_{code}_{var}"] = get(code, var)
for t in ["^SP500TR", "^RUTTR", "^RUT", "^NDX", "^GSPC"]:
    h = yf.Ticker(t).history(period="max", interval="1mo", auto_adjust=False)
    out["yf_" + t] = {str(d.date()): float(v) for d, v in h["Close"].dropna().items()}
r = requests.get("https://indexes.nasdaqomx.com/Index/ExportHistory/XNDX?startDate=1999-01-01T00:00:00.000&endDate=2026-10-23T00:00:00.000&timeOfDay=EOD", timeout=60, headers=H)
open("out/xndx.xlsx", "wb").write(r.content)
r = requests.get("https://indexes.nasdaqomx.com/Index/ExportHistory/NDX?startDate=1985-01-01T00:00:00.000&endDate=2026-10-23T00:00:00.000&timeOfDay=EOD", timeout=60, headers=H)
open("out/ndx.xlsx", "wb").write(r.content)
json.dump(out, open("out/r13e.json", "w"))
print({k: len(v) for k, v in out.items()})
