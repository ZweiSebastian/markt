import pandas as pd, yfinance as yf, time, json, sys
t = pd.read_csv("sp500/sp500_ticker_start_end.csv")
cur = pd.read_csv("sp500/S&P 500 Historical Components & Changes (Updated).csv").iloc[-1].tickers.split(",")
ticks = sorted(set(t.ticker) | set(cur))
ysym = {x: x.replace(".", "-") for x in ticks}
rows = []; meta = {}
syms = list(ysym.values())
for i in range(0, len(syms), 50):
    ch = syms[i:i+50]
    try:
        df = yf.download(ch, start="1994-12-01", interval="1d", auto_adjust=True, progress=False, threads=True, group_by="ticker")
    except Exception as e:
        print("err", e); continue
    for s in ch:
        try:
            c = df[s]["Close"].dropna()
        except Exception:
            continue
        if len(c) < 5: continue
        m = c.resample("ME").last().dropna()
        for d, v in m.items(): rows.append((s, d.strftime("%Y-%m-%d"), round(float(v), 6)))
        meta[s] = {"first": str(c.index[0].date()), "last": str(c.index[-1].date()), "lastc": float(c.iloc[-1]), "n": len(c)}
    time.sleep(1)
pd.DataFrame(rows, columns=["sym","date","close"]).to_csv("sp_monthly.csv.gz", index=False)
json.dump(meta, open("sp_meta.json","w"))
print(len(ticks), len(meta))
