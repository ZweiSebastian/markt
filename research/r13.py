import json, requests
out = {}
H = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"}
def show(k, r):
    out[k] = {"status": r.status_code, "ctype": r.headers.get("content-type"), "n": len(r.content), "head": r.text[:500] if "text" in (r.headers.get("content-type") or "") or "json" in (r.headers.get("content-type") or "") else ""}
    return r
for var in ["GRTR", "STRD"]:
    for code in ["990100", "891800", "939200", "106331", "990300"]:
        u = (f"https://app2.msci.com/products/service/index/indexmaster/downloadLevelData?output=INDEX_LEVELS&currency_symbol=USD&index_variant={var}"
             f"&start_date=19691231&end_date=20261023&data_frequency=END_OF_MONTH&baseValue=false&index_codes={code}")
        try:
            r = show(f"dl_{code}_{var}", requests.get(u, timeout=90, headers=H))
            open(f"out/dl_{code}_{var}.bin", "wb").write(r.content)
        except Exception as e:
            out[f"dl_{code}_{var}"] = str(e)[:200]
for t in ["%5EXNDX", "%5ENDXT", "%5ESX5GT", "%5ESX5T", "%5EN225TR", "%5ESPXNTR", "%5ERUTTR"]:
    u = f"https://query1.finance.yahoo.com/v8/finance/chart/{t}?range=max&interval=1mo"
    try:
        r = requests.get(u, timeout=60, headers=H)
        j = r.json(); res = (j.get("chart") or {}).get("result")
        if res:
            ts = res[0]["timestamp"]; out["yq_" + t] = {"n": len(ts), "first": ts[0], "last": ts[-1]}
            json.dump(res[0], open(f"out/yq_{t}.json", "w"))
        else:
            out["yq_" + t] = {"status": r.status_code, "err": str(j)[:200]}
    except Exception as e:
        out["yq_" + t] = str(e)[:200]
for u in ["https://indexes.nasdaqomx.com/Index/ExportHistory/XNDX?startDate=1999-01-01T00:00:00.000&endDate=2026-10-23T00:00:00.000&timeOfDay=EOD",
          "https://api.nasdaq.com/api/quote/XNDX/historical?assetclass=index&fromdate=1999-01-01&limit=9999&todate=2026-10-23"]:
    try:
        r = show("nq_" + u[:40], requests.get(u, timeout=60, headers=H))
    except Exception as e:
        out["nq_" + u[:40]] = str(e)[:200]
json.dump(out, open("out/r13d.json", "w"), indent=1)
print(json.dumps(out, indent=1)[:5000])
