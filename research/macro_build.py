"""Baut research/macro_monthly.csv aus den Rohdaten in research/raw/.

Quellen:
  fedfunds_y.txt   Effective Federal Funds Rate, Monatsdurchschnitt (FRED FEDFUNDS via Alpha Vantage), ab 1954-07
  gs10_y.txt       10-jährige US-Staatsanleihe, Monatsdurchschnitt (FRED GS10 via Alpha Vantage), ab 1953-04
  wtisplc_fred.csv WTI-Rohöl Spotpreis, Monatsdurchschnitt (FRED WTISPLC), ab 1946-01; Jun-Aug 2026 aus Alpha Vantage
  ../research/shiller_monthly.csv  CPI, CAPE, TR-CAPE (Shiller)
  ../research/weekly.csv           S&P-500-Wochenschlusskurse (Yahoo ^GSPC), realer Total-Return-Index
"""
import pandas as pd, numpy as np, os

HERE = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(HERE, "raw")


def year_lines(fn, name):
    rows = {}
    for line in open(os.path.join(RAW, fn)):
        p = line.split()
        if not p:
            continue
        y = int(p[0])
        for m, v in enumerate(p[1:13], 1):
            if v != "x":
                rows[pd.Period(f"{y}-{m:02d}", "M")] = float(v)
    return pd.Series(rows, name=name)


def build():
    ff = year_lines("fedfunds_y.txt", "fedfunds")
    g10 = year_lines("gs10_y.txt", "gs10")
    o = pd.read_csv(os.path.join(RAW, "wtisplc_fred.csv"))
    wti = pd.Series(o.WTISPLC.values, index=pd.PeriodIndex(o.observation_date.str[:7], freq="M"), name="wti")

    sh = pd.read_csv(os.path.join(HERE, "shiller_monthly.csv"))
    sh.index = pd.PeriodIndex([f"{str(k)[:4]}-{str(k)[4:6]}" for k in sh.key], freq="M")
    cpi = sh.CPI.rename("cpi")

    wk = pd.read_csv(os.path.join(HERE, "weekly.csv"), parse_dates=["t"])
    wk["m"] = wk.t.dt.to_period("M")
    mon = wk.groupby("m").agg(spx=("c", "last"), spx_low=("l", "min"), tr_real=("tr_real", "last"))

    df = pd.concat([ff, g10, wti, cpi, sh.CAPE.rename("cape"), sh.TRCAPE.rename("trcape"), mon], axis=1).sort_index()
    df = df[df.index >= pd.Period("1946-01", "M")]
    last_cpi = df.cpi.dropna().iloc[-1]
    df["wti_real"] = df.wti * last_cpi / df.cpi
    df.index.name = "month"
    return df


if __name__ == "__main__":
    df = build()
    df.round(4).to_csv(os.path.join(HERE, "macro_monthly.csv"))
    print(df.tail(4))
    print(len(df), "Monate")
