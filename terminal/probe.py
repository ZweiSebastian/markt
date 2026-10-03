import requests, time, json
UA={"User-Agent":"MarktTerminal research (github.com/ZweiSebastian/markt) python-requests","Accept-Encoding":"gzip, deflate"}
def show(u, r, t):
    print(f"{r.status_code} {len(r.content):>9} {time.time()-t:4.1f}s {u[:120]} | {r.text[:220]!r}")
U=[
"https://data.sec.gov/api/xbrl/companyfacts/CIK0001045810.json",
"https://data.sec.gov/api/xbrl/frames/us-gaap/RevenueRemainingPerformanceObligation/USD/CY2025Q2I.json",
"https://www.sec.gov/files/company_tickers.json",
"https://www.philadelphiafed.org/-/media/frbp/assets/surveys-and-data/real-time-data/data-files/xlsx/employmx.xlsx",
"https://www.philadelphiafed.org/-/media/frbp/assets/surveys-and-data/real-time-data/data-files/xlsx/rucqvmd.xlsx",
"https://www.philadelphiafed.org/-/media/frbp/assets/surveys-and-data/real-time-data/data-files/xlsx/rucmvmd.xlsx",
"https://sdmx.oecd.org/public/rest/data/OECD.SDD.STES,DSD_STES@DF_CLI,4.1/DEU+JPN+CHN+FRA+GBR+EA19.M.LI...AA...H?startPeriod=2024-01&dimensionAtObservation=AllDimensions&format=csvfilewithlabels",
"https://sdmx.oecd.org/public/rest/data/OECD.SDD.STES,DSD_STES@DF_FINMARK,4.0/DEU+JPN+EA19+USA.M.IR3TIB+IRLT.PA.....?startPeriod=2024-01&dimensionAtObservation=AllDimensions&format=csvfilewithlabels",
"https://sdmx.oecd.org/public/rest/data/OECD.SDD.TPS,DSD_LFS@DF_IALFS_UNE_M,1.0/DEU+JPN+EA20+USA..._Z.Y._T.Y_GE15..M?startPeriod=2024-01&dimensionAtObservation=AllDimensions&format=csvfilewithlabels",
"https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/ei_bssi_m_r2?geo=EA20&indic=BS-ESI-I&s_adj=SA&format=JSON&lang=EN",
"https://data-api.ecb.europa.eu/service/data/YC/B.U2.EUR.4F.G_N_A.SV_C_YM.SR_3M?lastNObservations=3&format=csvdata",
"https://www.stoxx.com/document/Indices/Current/HistoricalData/h_v2tx.txt",
]
for u in U:
    t=time.time()
    try: show(u, requests.get(u,headers=UA,timeout=40), t)
    except Exception as e: print("ERR", type(e).__name__, u[:120], str(e)[:100])
    time.sleep(0.5)
import yfinance as yf
for tk in ["^V2TX","^VSTOXX","^STOXX","^N225","^TOPX","1306.T","EWJ","EZU","VGK","^SPXEW","RSP","^GDAXI","EXS1.DE","^NYA","^DJT"]:
    try:
        h=yf.Ticker(tk).history(period="max",interval="1d")
        print(tk, len(h), h.index.min().date() if len(h) else None, h.index.max().date() if len(h) else None)
    except Exception as e: print(tk,"ERR",e)
    time.sleep(0.7)
