import yfinance as yf, pandas as pd
cols = {}
for k, s in {"spx":"^GSPC","nvda":"NVDA","orcl":"ORCL","crwv":"CRWV","sftbk":"9984.T","vix":"^VIX"}.items():
    try:
        h = yf.Ticker(s).history(period="max", auto_adjust=False)
        c = h["Close"]; c.index = c.index.tz_localize(None).normalize(); cols[k] = c
        print(k, c.index[0].date(), c.index[-1].date(), c.tail(8).round(2).to_dict())
    except Exception as e: print(k, "FEHLER", e)
for k, s in {"nvda":"NVDA","orcl":"ORCL"}.items():
    try:
        i = yf.Ticker(s).info; print(k, {x: i.get(x) for x in ["trailingPE","forwardPE","marketCap"]})
    except Exception as e: print(k, "info FEHLER", e)
pd.DataFrame(cols).to_csv("out/closes.csv")
