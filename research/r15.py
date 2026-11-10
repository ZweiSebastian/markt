import yfinance as yf, pandas as pd
T = {"spx":"^GSPC","ixic":"^IXIC","ndx":"^NDX","sox":"^SOX","vix":"^VIX","rut":"^RUT","dji":"^DJI"}
cols = {}
for k, s in T.items():
    h = yf.Ticker(s).history(period="max", auto_adjust=False)
    c = h["Close"]; c.index = c.index.tz_localize(None).normalize()
    cols[k] = c; print(k, c.index[0].date(), c.index[-1].date(), len(c), c.tail(4).round(2).to_dict())
df = pd.DataFrame(cols); df.to_csv("out/closes.csv")
