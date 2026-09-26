"""Einmal-Export für die Score-Forschung: wöchentliche Reihe mit Kurs, 200W, CAPE, TR-CAPE,
realem Gesamtrendite-Index (Dividenden reinvestiert, inflationsbereinigt)."""
import io, re, sys
import numpy as np, pandas as pd, requests
sys.path.insert(0, "scripts")
import update as u

import traceback
try:
    page = requests.get("https://shillerdata.com/", headers=u.UA, timeout=60).text.replace("&amp;", "&")
    urls = [("https:" + x if x.startswith("//") else x) for x in re.findall(r'(?:https?:)?//[^"\'\s<>()]+?ie_data\.xls(?:\?[^"\'\s<>()]*)?', page)] + [u.FALLBACK_XLS]
    raw = None
    for url in urls:
        r = requests.get(url, headers=u.UA, timeout=120)
        if r.ok and r.content[:4] == b"\xd0\xcf\x11\xe0":
            raw = r.content; break
    df = pd.read_excel(io.BytesIO(raw), sheet_name="Data", header=None, engine="xlrd")
    hdr = next(i for i in range(30) if str(df.iat[i, 0]).strip() == "Date")
    rows = []
    for i in range(hdr + 1, len(df)):
        try:
            d = float(df.iat[i, 0])
        except Exception:
            continue
        if d != d:
            continue
        y = int(d); m = int(round((d - y) * 100))
        if not 1 <= m <= 12:
            continue
        def f(j):
            try: return float(df.iat[i, j])
            except Exception: return np.nan
        rows.append({"key": y * 100 + m, "P": f(1), "D": f(2), "CPI": f(4), "CAPE": f(12), "TRCAPE": f(14)})
    sh = pd.DataFrame(rows).set_index("key").sort_index()
    sh[["D", "CPI"]] = sh[["D", "CPI"]].ffill()
    sh.to_csv("research/shiller_monthly.csv")

    px, src = u.load_prices()
    px = px.sort_index(); px = px[~px.index.duplicated(keep="last")]
    ny = pd.Timestamp.now(tz="America/New_York")
    if px.index[-1].date() >= ny.date() and (ny.hour, ny.minute) < (16, 20):
        px = px.iloc[:-1]
    for col in ("Open", "High", "Low"):
        bad = px[col].isna() | (px[col] <= 0)
        px.loc[bad, col] = px.loc[bad, "Close"]
    px["Low"] = px[["Open", "Low", "Close"]].min(axis=1)
    close = px["Close"]
    sma200 = close.rolling(200).mean()
    px["wk"] = px.index.to_period("W-FRI")
    g = px.groupby("wk")
    w = pd.DataFrame({"t": g.apply(lambda x: x.index[0]), "c": g["Close"].last(), "l": g["Low"].min(),
                      "s200": g.apply(lambda x: sma200.loc[x.index[-1]])})
    w["w200"] = w["c"].rolling(200).mean()
    key = w["t"].dt.year * 100 + w["t"].dt.month
    lastkey = sh["CAPE"].dropna().index.max()
    def mget(col, k):
        s = sh[col].dropna()
        k = k if k in s.index else s.index[s.index <= k].max()
        return s.get(k, np.nan)
    # CAPE/TR-CAPE wöchentlich: Monatswert * (Wochenschluss / Monatsdurchschnittskurs Shiller)
    w["P_m"] = [mget("P", k) for k in key]
    w["cape"] = [mget("CAPE", k) for k in key] * (w["c"] / w["P_m"])
    w["trcape"] = [mget("TRCAPE", k) for k in key] * (w["c"] / w["P_m"])
    w["cpi"] = [mget("CPI", k) for k in key]
    w["div"] = [mget("D", k) for k in key]            # Dividende p.a. je Anteil (Shiller)
    tr = [1.0]
    for i in range(1, len(w)):
        tr.append(tr[-1] * (w["c"].iloc[i] + w["div"].iloc[i] / 52) / w["c"].iloc[i - 1])
    w["tr_nom"] = tr
    w["tr_real"] = w["tr_nom"] / w["cpi"] * w["cpi"].iloc[-1]
    w["price_real"] = w["c"] / w["cpi"] * w["cpi"].iloc[-1]
    w = w.drop(columns=["P_m"])
    w["t"] = w["t"].dt.strftime("%Y-%m-%d")
    w.to_csv("research/weekly.csv", index=False, float_format="%.6g")
    print("::notice::OK", len(w), "Wochen,", src)
except Exception:
    for l in traceback.format_exc().splitlines()[-8:]: print("::notice::ERR " + l)
    raise
