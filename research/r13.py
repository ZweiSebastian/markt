import json, requests, io, sys
import yfinance as yf
out = {}
def msci(code, var, cur="USD", start="19691231"):
    u = (f"https://app2.msci.com/products/service/index/indexmaster/getLevelDataForGraph?currency_symbol={cur}"
         f"&index_variant={var}&start_date={start}&end_date=20261023&data_frequency=END_OF_MONTH&index_codes={code}")
    try:
        r = requests.get(u, timeout=90, headers={"User-Agent": "Mozilla/5.0"})
        lv = r.json()["indexes"]["INDEX_LEVELS"]
        return {str(x["calc_date"]): x["level_eod"] for x in lv}
    except Exception as e:
        return {"error": str(e)[:200], "status": getattr(locals().get('r'), 'status_code', None)}
for code in ["990100", "891800", "939200", "984000", "990300", "106331", "991000"]:
    for var in ["GRTR", "STRD", "NETR"]:
        out[f"msci_{code}_{var}"] = msci(code, var)
for t in ["^SP500TR", "^XNDX", "^RUTTR", "^SX5GT", "^SX5T", "^STOXX50E", "^N225TR", "^NDX", "^RUT", "^GSPC", "^990100-USD-GRTR", "^990100-USD-STRD"]:
    try:
        h = yf.Ticker(t).history(period="max", interval="1mo", auto_adjust=False)
        out["yf_" + t] = {str(d.date()): float(v) for d, v in h["Close"].dropna().items()}
    except Exception as e:
        out["yf_" + t] = {"error": str(e)[:200]}
for u in ["https://www.stoxx.com/document/Indices/Current/HistoricalData/h_sx5t.txt",
          "https://www.stoxx.com/document/Indices/Current/HistoricalData/h_sx5gt.txt",
          "https://www.stoxx.com/document/Indices/Current/HistoricalData/h_3msx5t.txt"]:
    try:
        r = requests.get(u, timeout=60, headers={"User-Agent": "Mozilla/5.0"}); out["stoxx_" + u.rsplit("/", 1)[1]] = {"status": r.status_code, "head": r.text[:300], "tail": r.text[-300:], "n": len(r.text)}
    except Exception as e:
        out["stoxx_" + u.rsplit("/", 1)[1]] = {"error": str(e)[:200]}
json.dump(out, open("out/r13.json", "w"))
print({k: (len(v) if isinstance(v, dict) else v) for k, v in out.items()})
