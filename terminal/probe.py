import requests, time, json
UA={"User-Agent":"Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"}
U=[
"https://app2.msci.com/products/service/index/indexmaster/getLevelDataForGraph?currency_symbol=USD&index_variant=NETR&start_date=19691231&end_date=20261002&data_frequency=END_OF_MONTH&index_codes=990100",
"https://app2.msci.com/products/service/index/indexmaster/getLevelDataForGraph?currency_symbol=EUR&index_variant=NETR&start_date=19991231&end_date=20261002&data_frequency=DAILY&index_codes=990100",
"https://www.chicagofed.org/-/media/publications/nfci/nfci-data-series-csv.csv",
"https://sdmx.oecd.org/public/rest/data/OECD.SDD.STES,DSD_STES@DF_CLI,4.1/USA+G7+OECD.M.LI...AA...H?startPeriod=1990-01&dimensionAtObservation=AllDimensions&format=csvfilewithlabels",
"https://sca.isr.umich.edu/files/tbmics.csv",
"https://oui.doleta.gov/unemploy/csv/ar539.csv",
"https://www.aaii.com/files/surveys/sentiment.xls",
"https://production.dataviz.cnn.io/index/fearandgreed/graphdata/2020-01-01",
"https://www.finra.org/sites/default/files/2021-03/margin-statistics.xlsx",
"https://api.db.nomics.world/v22/series/FED/H15?q=3-month%20treasury%20bill%20monthly&limit=10&observations=0&format=json",
"https://api.db.nomics.world/v22/series/BEA/NIPA-T10105?q=gross%20domestic%20product&limit=5&observations=0&format=json",
"https://api.db.nomics.world/v22/series/FED/H15/RIFSGFSM03_N.M?observations=1&format=json",
"https://api.db.nomics.world/v22/series/FED/H15/RIFLGFCY10_N.M?observations=1&format=json",
"https://data-api.ecb.europa.eu/service/data/ICP/M.U2.N.000000.4.ANR?lastNObservations=3&format=csvdata",
"https://data-api.ecb.europa.eu/service/data/ILM/W.U2.C.T000000.Z5.Z01?lastNObservations=3&format=csvdata",
"https://cdn.cboe.com/api/global/us_indices/daily_prices/VIX_History.csv",
"https://shillerdata.com/",
"https://www.multpl.com/s-p-500-earnings/table/by-month",
"https://www.ishares.com/de/privatanleger/de/produkte/251882/ishares-msci-world-ucits-etf-acc-fund",
]
for u in U:
    t=time.time()
    try:
        r=requests.get(u,headers=UA,timeout=30)
        print(f"{r.status_code} {len(r.content):>8} {time.time()-t:4.1f}s {u[:110]} | {r.text[:300]!r}")
    except Exception as e:
        print(f"ERR {type(e).__name__} {u[:110]} {str(e)[:80]}")
print("--- yfinance")
import yfinance as yf
for t in ["^VIX3M","^SKEW","^W5000","EUNL.DE","IWDA.AS","URTH","^FTSE","^HSI","IWM","KRE","SMH","XHB","^GSPC","^990100-USD-STRD","ACWI","^VVIX","DX-Y.NYB","GC=F","^TNX"]:
    try:
        h=yf.Ticker(t).history(period="max",interval="1d",auto_adjust=True)
        print(t, len(h), h.index.min().date() if len(h) else None, h.index.max().date() if len(h) else None)
    except Exception as e:
        print(t,"ERR",e)
    time.sleep(0.8)
