import json, requests
out = {}
H = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"}
def get(code, var, cur, start, freq):
    u = (f"https://app2.msci.com/products/service/index/indexmaster/getLevelDataForGraph?currency_symbol={cur}"
         f"&index_variant={var}&start_date={start}&end_date=20261023&data_frequency={freq}&index_codes={code}")
    r = requests.get(u, timeout=90, headers=H)
    try:
        lv = r.json()["indexes"]["INDEX_LEVELS"]; return {str(x["calc_date"]): x["level_eod"] for x in lv}
    except Exception:
        return {"raw": r.text[:400]}
for freq in ["DAILY", "MONTHLY", "END_OF_MONTH"]:
    for start in ["19691231", "19781229", "19981231", "20001229"]:
        k = f"t_{freq}_{start}"; v = get("990100", "GRTR", "USD", start, freq); out[k] = v if "raw" in v else {"n": len(v), "first": min(v), "last": max(v)}
json.dump(out, open("out/r13b.json", "w"), indent=1)
# volle Reihen, falls eine Variante klappt
best = None
for freq, start in [("END_OF_MONTH", "19691231"), ("MONTHLY", "19691231"), ("DAILY", "19691231"), ("DAILY", "19781229"), ("DAILY", "19981231")]:
    v = get("990100", "GRTR", "USD", start, freq)
    if "raw" not in v and len(v) > 100:
        best = (freq, start); break
res = {"best": best}
if best:
    for code in ["990100", "891800", "939200", "991000", "990300"]:
        for var in ["GRTR", "STRD", "NETR"]:
            res[f"{code}_{var}"] = get(code, var, "USD", best[1], best[0])
json.dump(res, open("out/r13c.json", "w"))
print(json.dumps(out, indent=1)[:3000]); print("best", best, {k: len(v) if isinstance(v, dict) else v for k, v in res.items()})
