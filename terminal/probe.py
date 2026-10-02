import requests, time
UA={"User-Agent":"Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"}
U=[
"https://fred.stlouisfed.org/graph/fredgraph.csv?id=DGS2",
"https://fred.stlouisfed.org/graph/fredgraph.csv?id=BAMLH0A0HYM2",
"https://fred.stlouisfed.org/graph/fredgraph.csv?id=WALCL&cosd=2015-01-01",
"https://api.db.nomics.world/v22/series/FED/H15/RIFLGFCY02_N.B?observations=1&format=json",
"https://home.treasury.gov/resource-center/data-chart-center/interest-rates/daily-treasury-rates.csv/2026/all?type=daily_treasury_yield_curve&field_tdr_date_value=2026&page&_format=csv",
"https://markets.newyorkfed.org/api/rates/unsecured/effr/last/5.json",
"https://query1.finance.yahoo.com/v8/finance/chart/%5EGSPC?range=5d&interval=1d",
"https://query2.finance.yahoo.com/v8/finance/chart/2YY=F?range=1y&interval=1d",
"https://query1.finance.yahoo.com/v8/finance/chart/DX-Y.NYB?range=5d&interval=1d",
"https://www.cnbc.com/id/20910258/device/rss/rss.html",
"https://feeds.content.dowjones.io/public/rss/mw_topstories",
"https://finance.yahoo.com/news/rssindex",
"https://www.federalreserve.gov/feeds/press_all.xml",
"https://www.tagesschau.de/wirtschaft/index~rss2.xml",
"https://www.handelsblatt.com/contentexport/feed/finanzen",
"https://www.ft.com/markets?format=rss",
"https://data-api.ecb.europa.eu/service/data/FM/D.U2.EUR.4F.KR.DFR.LEV?lastNObservations=3&format=csvdata",
"https://api.bls.gov/publicAPI/v1/timeseries/data/LNS14000000",
"https://www.eia.gov/dnav/pet/hist_xls/EMD_EPD2D_PTE_NUS_DPGw.xls",
"https://raw.githubusercontent.com/ZweiSebastian/markt/main/data/markt.json",
"https://www.investing.com/rss/news_25.rss",
"https://www.spglobal.com/spdji/en/util/redesign/index-data/get-performance-data-for-datawidget-redesign.dot?indexId=340",
"https://www.wsj.com/xml/rss/3_7031.xml",
]
for u in U:
    t=time.time()
    try:
        r=requests.get(u,headers=UA,timeout=25)
        print(f"{r.status_code} {len(r.content):>8} {time.time()-t:4.1f}s {u[:90]} | {r.text[:120]!r}")
    except Exception as e:
        print(f"ERR {type(e).__name__} {u[:90]} {str(e)[:80]}")
