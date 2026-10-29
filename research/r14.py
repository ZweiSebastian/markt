import yfinance as yf, pandas as pd
for t, adj in [("SPY", True), ("QQQ", True), ("^GSPC", False), ("^NDX", False), ("^IRX", False), ("URTH", True), ("EUNL.DE", True)]:
    h = yf.Ticker(t).history(period="max", interval="1d", auto_adjust=adj)
    h.index = h.index.tz_localize(None)
    h[["Open", "High", "Low", "Close", "Volume"]].to_csv(f"out/{t.replace('^','').replace('.','_')}.csv")
    print(t, len(h), h.index[0].date(), h.index[-1].date())
