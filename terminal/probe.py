import requests, time
H1={"User-Agent":"MarktTerminal markt-bot actions@users.noreply.github.com","Accept-Encoding":"gzip, deflate"}
H0={"User-Agent":"Mozilla/5.0"}
def g(u,h):
    t=time.time()
    try:
        r=requests.get(u,headers=h,timeout=40); print(f"{r.status_code} {len(r.content):>9} {time.time()-t:4.1f}s {u[:110]} | {r.text[:160]!r}")
    except Exception as e: print("ERR",type(e).__name__,u[:110],str(e)[:80])
for u in ["https://data.sec.gov/api/xbrl/companyfacts/CIK0001045810.json","https://data.sec.gov/api/xbrl/companyconcept/CIK0001341439/us-gaap/RevenueRemainingPerformanceObligation.json","https://www.sec.gov/files/company_tickers.json"]:
    g(u,H1); time.sleep(0.3)
base="https://www.philadelphiafed.org/-/media/frbp/assets/surveys-and-data/real-time-data/data-files/xlsx/"
for f in ["employmvmd.xlsx","EMPLOYMvMd.xlsx","employMvMd.xlsx","employqvmd.xlsx","rucqvmd.xlsx","cpiqvmd.xlsx","pcpiqvmd.xlsx","nomgdpqvqd.xlsx","noutputqvqd.xlsx"]:
    g(base+f,H0); time.sleep(0.3)
g("https://www.philadelphiafed.org/surveys-and-data/real-time-data-research/employ",H0)
