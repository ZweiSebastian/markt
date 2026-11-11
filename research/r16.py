import requests, io, pandas as pd
ids = ["CPATAX","CP","A451RC1Q027SBEA","A455RC1Q027SBEA","A454RC1Q027SBEA","A446RC1Q027SBEA","BOGZ1LM893064105Q","NCBEILQ027S","BOGZ1FL893064105Q","USREC","GDP"]
for sid in ids:
    try:
        r = requests.get(f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={sid}", timeout=60)
        df = pd.read_csv(io.StringIO(r.text)); df.to_csv(f"out/{sid}.csv", index=False)
        print(sid, len(df), df.iloc[0].tolist(), df.iloc[-1].tolist())
    except Exception as e:
        print(sid, "FEHLER", e, r.text[:200] if 'r' in dir() else "")
