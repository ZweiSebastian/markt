"""Einmal-Export: Makro-Reihen für die Forschung (FRED + Shiller GS10)."""
import io, os, re, sys, traceback
import pandas as pd, requests
os.makedirs("research", exist_ok=True)
UA = {"User-Agent": "Mozilla/5.0"}
try:
    out = {}
    for sid in ("FEDFUNDS", "WTISPLC", "GS10", "CPIAUCSL", "INTDSRUSM193N"):
        r = requests.get(f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={sid}", headers=UA, timeout=60)
        r.raise_for_status()
        df = pd.read_csv(io.StringIO(r.text))
        df.columns = ["date", sid]
        df["date"] = pd.to_datetime(df["date"])
        df[sid] = pd.to_numeric(df[sid], errors="coerce")
        out[sid] = df.set_index("date")[sid]
        print(f"::notice::{sid}: {df['date'].min():%Y-%m} bis {df['date'].max():%Y-%m}, {len(df)} Werte")
    m = pd.concat(out.values(), axis=1)
    m = m.resample("MS").mean()
    m.to_csv("research/macro_monthly.csv", float_format="%.4g")
    print("::notice::OK", len(m))
except Exception:
    for l in traceback.format_exc().splitlines()[-8:]:
        print("::notice::ERR " + l)
    raise
