import yfinance as yf, pandas as pd
cols = {}
for k, s in {"vix3m":"^VIX3M","vix":"^VIX","spx":"^GSPC","vix9d":"^VIX9D"}.items():
    try:
        h = yf.Ticker(s).history(period="max", auto_adjust=False)
        c = h["Close"]; c.index = c.index.tz_localize(None).normalize(); cols[k] = c
        print(k, c.index[0].date(), c.index[-1].date(), len(c))
    except Exception as e: print(k, "FEHLER", e)
pd.DataFrame(cols).to_csv("out/vix.csv")
