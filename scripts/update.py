"""
Tägliches Update der Marktdaten für die App "Markt".

- Shiller-CAPE: monatliche Daten von Robert Shiller (shillerdata.com, ie_data.xls).
  Daraus wird pro Monat der 10-Jahres-Gewinn (E10) in Dollar des jeweiligen Monats abgeleitet:
      E10_Monat = Monatsdurchschnittskurs / CAPE_Monat
- Täglicher CAPE = Tagesschlusskurs S&P 500 / E10 des Monats
  (für Tage nach dem letzten Shiller-Monat wird das letzte bekannte E10 verwendet;
   E10 ist ein 10-Jahres-Durchschnitt und bewegt sich pro Monat nur um Bruchteile eines Prozents).
- S&P 500 Tageskurse (Yahoo Finance, ^GSPC) -> Wochenkerzen der letzten 5 Jahre + 200/50-Tage-Linie.

Ergebnis: data/markt.json (wird von der App geladen).
"""
import io
import json
import math
import re
import sys
from datetime import datetime, timezone

import pandas as pd
import requests

UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"}
OUT = "data/markt.json"
# bekannter Link (Stand 09/2026), falls die Seite anders aufgebaut ist
FALLBACK_XLS = ("https://img1.wsimg.com/blobby/go/e5e77e0b-59d1-44d9-ab25-4763ac982e53/downloads/"
                "70fec4f5-727f-4e53-b5f1-179af109c5fa/ie_data.xls")


# ---------------------------------------------------------------- Shiller
def load_shiller():
    page = requests.get("https://shillerdata.com/", headers=UA, timeout=60).text
    page = page.replace("\\u002F", "/").replace("\\/", "/").replace("&amp;", "&")
    urls = [("https:" + u if u.startswith("//") else u)
            for u in re.findall(r'(?:https?:)?//[^"\'\s<>()]+?ie_data\.xls(?:\?[^"\'\s<>()]*)?', page)]
    urls.append(FALLBACK_XLS)
    raw, last_err = None, None
    for url in dict.fromkeys(urls):
        try:
            r = requests.get(url, headers=UA, timeout=120)
            r.raise_for_status()
            if r.content[:4] == b"\xd0\xcf\x11\xe0":  # xls-Signatur
                raw = r.content
                print("Shiller-Datei:", url)
                break
            last_err = f"{url}: keine xls-Datei"
        except Exception as e:  # noqa
            last_err = f"{url}: {e}"
    if raw is None:
        i = page.find("ie_data")
        print("Seitenlänge", len(page), "Ausschnitt:", page[max(0, i - 300):i + 100] if i >= 0 else "-")
        raise RuntimeError(f"ie_data.xls nicht ladbar ({last_err})")
    df = pd.read_excel(io.BytesIO(raw), sheet_name="Data", header=None, engine="xlrd")

    # Kopfzeile suchen (erste Spalte "Date")
    hdr = None
    for i in range(30):
        if str(df.iat[i, 0]).strip() == "Date":
            hdr = i
            break
    if hdr is None:
        raise RuntimeError("Kopfzeile in ie_data.xls nicht gefunden")
    heads = [str(x).strip() for x in df.iloc[hdr]]
    cape_col = next(i for i, h in enumerate(heads) if h.upper() == "CAPE")
    p_col = next(i for i, h in enumerate(heads) if h == "P")
    tr_col = next((i for i, h in enumerate(heads) if h.upper().replace(" ", "") == "TRCAPE"), 14)
    d_col = next((i for i, h in enumerate(heads) if h == "D"), 2)
    cpi_col = next((i for i, h in enumerate(heads) if h.upper() == "CPI"), 4)

    def num(v):
        try:
            v = float(v)
            return v if v == v else float("nan")
        except (TypeError, ValueError):
            return float("nan")

    rows = []
    for i in range(hdr + 1, len(df)):
        d, p, c = df.iat[i, 0], df.iat[i, p_col], df.iat[i, cape_col]
        try:
            d = float(d)
            p = float(p)
        except (TypeError, ValueError):
            continue
        if math.isnan(d) or math.isnan(p):
            continue
        year = int(d)
        month = int(round((d - year) * 100))
        if not 1 <= month <= 12:
            continue
        rows.append((year, month, p, num(c), num(df.iat[i, tr_col]), num(df.iat[i, d_col]), num(df.iat[i, cpi_col])))
    sh = pd.DataFrame(rows, columns=["year", "month", "price", "cape", "trcape", "div", "cpi"])
    sh[["div", "cpi"]] = sh[["div", "cpi"]].ffill()   # Dividende/Inflation kommen mit Verzögerung
    sh = sh[sh["cape"].notna() & (sh["cape"] > 0)]
    sh["key"] = sh["year"] * 100 + sh["month"]
    sh["e10"] = sh["price"] / sh["cape"]
    sh["e10tr"] = sh["price"] / sh["trcape"]
    if len(sh) < 1000:
        raise RuntimeError(f"Zu wenige Shiller-Monate ({len(sh)})")
    return sh


# ---------------------------------------------------------------- S&P 500 Tageskurse
def load_prices():
    errors = []
    try:
        import yfinance as yf
        df = yf.download("^GSPC", start="1927-12-01", interval="1d", auto_adjust=False,
                         progress=False, threads=False)
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        df = df[["Open", "High", "Low", "Close"]].dropna(subset=["Close"])
        if len(df) > 5000:
            df.index = pd.to_datetime(df.index).tz_localize(None).normalize()
            return df, "Yahoo Finance"
        errors.append(f"yfinance: nur {len(df)} Zeilen")
    except Exception as e:  # noqa
        errors.append(f"yfinance: {e}")

    # Ersatz: Yahoo Chart-API direkt
    try:
        p2 = int(datetime.now(timezone.utc).timestamp()) + 86400
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/%5EGSPC?period1=-1328054400&period2={p2}&interval=1d"
        j = requests.get(url, headers=UA, timeout=60).json()["chart"]["result"][0]
        q = j["indicators"]["quote"][0]
        df = pd.DataFrame({"Open": q["open"], "High": q["high"], "Low": q["low"], "Close": q["close"]},
                          index=pd.to_datetime(j["timestamp"], unit="s")).dropna(subset=["Close"])
        df.index = df.index.normalize()
        df = df[~df.index.duplicated(keep="last")]
        if len(df) > 5000:
            return df, "Yahoo Finance"
        errors.append(f"chart-api: nur {len(df)} Zeilen")
    except Exception as e:  # noqa
        errors.append(f"chart-api: {e}")

    # Ersatz: Stooq
    try:
        txt = requests.get("https://stooq.com/q/d/l/?s=%5Espx&i=d", headers=UA, timeout=60).text
        df = pd.read_csv(io.StringIO(txt), parse_dates=["Date"], index_col="Date")
        df = df[["Open", "High", "Low", "Close"]].dropna(subset=["Close"])
        df = df[df.index >= "1927-12-01"]
        if len(df) > 5000:
            return df, "Stooq"
        errors.append(f"stooq: nur {len(df)} Zeilen")
    except Exception as e:  # noqa
        errors.append(f"stooq: {e}")
    raise RuntimeError("Keine Kursdaten: " + " | ".join(errors))


# ---------------------------------------------------------------- Rechnen
def rating(z):
    if z > 2:
        return "Teuer"
    if z > 1:
        return "Überbewertet"
    if z < -2:
        return "Günstig"
    if z < -1:
        return "Unterbewertet"
    return "Fair"


def r2(x, n=2):
    return None if x is None or (isinstance(x, float) and math.isnan(x)) else round(float(x), n)


# ---------------------------------------------------------------- Einstiegssignal (Sebas Regel)
SIG_RISE = 0.10      # CAPE muss 10 % über sein Tief seit der Berührung steigen -> Score 100
SIG_DIST = 0.30      # ab 30 % Abstand über der 200-Wochen-Linie ist der Score 0
SIG_WINDOW = 13      # nach einem Signal bleibt der Score 13 Wochen auf 100 (Einstiegsfenster)
SIG_MAXWAIT = 104    # ohne Wende innerhalb von 2 Jahren verfällt die Berührung
# Kombinierter Score (0-90), 100 bleibt der strengen Regel vorbehalten
W_DIST, W_CAPE = 0.35, 0.65   # Gewichtung 200W-Abstand / CAPE (σ zum 20J-Ø)
SPREAD = 20                   # 1 Standardabweichung der Kombination = 20 Punkte um die Mitte 50
CAP = 80                      # Kombi-Score maximal 80; darüber nur die strenge Regel
CAPE_MID, CAPE_WIDTH = 0.5, 0.1   # S-Kurve: CAPE-Teil steigt zwischen 0 und -1σ steil an (Mitte -0,5σ), darunter keine Extrapunkte
Z_MAX_100 = 1.0               # 100 nur, wenn das CAPE beim Signal höchstens +1σ über dem 20J-Ø liegt
TURN_WEEKS = 26               # Wende: CAPE-Erholung vom Tief der letzten 26 Wochen (+10 % = voll)


def signal_model(wc, wl, w200, wcape):
    """Wöchentlicher Score 0-100 und Liste der Episoden.
    wc/wl/w200/wcape: Listen (Schluss, Tief, 200W-Linie, CAPE) je Woche, chronologisch."""
    n = len(wc)
    score = [None] * n
    episodes = []
    ep = None
    run, last_touch = 0, -10 ** 9
    for i in range(n):
        if w200[i] is None or wcape[i] is None:
            continue
        touched = wl[i] <= w200[i]
        new_touch = touched and run >= 26 and i - last_touch > 52
        if ep is not None and ep["signal"] is not None and new_touch:
            ep["end"] = i          # neue Berührung während des Einstiegsfensters -> neue Episode
            ep = None
        if ep is not None:
            ep["min"] = min(ep["min"], wcape[i])
            if ep["signal"] is None:
                rise = wcape[i] / ep["min"] - 1
                score[i] = 50 + 50 * min(1.0, max(0.0, rise) / SIG_RISE)
                if rise >= SIG_RISE:
                    ep["signal"] = i
                    score[i] = 100
                elif i - ep["start"] >= SIG_MAXWAIT:
                    ep["end"] = i
                    ep = None
            elif i - ep["signal"] < SIG_WINDOW:
                score[i] = 100
            else:
                ep["end"] = i
                ep = None
        if ep is None and score[i] is None:
            if new_touch:
                ep = {"start": i, "min": wcape[i], "signal": None, "end": None}
                episodes.append(ep)
                score[i] = 50
            else:
                dist = wc[i] / w200[i] - 1
                score[i] = 50 * min(1.0, max(0.0, 1 - dist / SIG_DIST))
        if touched:
            last_touch = i
        run = run + 1 if wc[i] > w200[i] else 0
    state = {"active": ep is not None, "run": run, "weeksSinceTouch": n - 1 - last_touch}
    if ep is not None:
        state.update({"touch": ep["start"], "capeMin": ep["min"], "signal": ep["signal"]})
    return score, episodes, state


def main():
    sh = load_shiller()
    px, src = load_prices()
    px = px.sort_index()
    px = px[~px.index.duplicated(keep="last")]
    # Laufenden Handelstag weglassen (nur fertige Schlusskurse verwenden)
    ny = pd.Timestamp.now(tz="America/New_York")
    if px.index[-1].date() >= ny.date() and (ny.hour, ny.minute) < (16, 20):
        px = px.iloc[:-1]

    # --- täglicher CAPE
    e10 = dict(zip(sh["key"], sh["e10"]))
    last_key = int(sh["key"].max())
    first_key = int(sh["key"].min())
    close = px["Close"]
    keys = close.index.year * 100 + close.index.month
    e10_series = []
    for k in keys:
        k = int(k)
        if k > last_key:
            e10_series.append(e10[last_key])
        elif k in e10:
            e10_series.append(e10[k])
        else:
            e10_series.append(float("nan"))
    cape = (close / pd.Series(e10_series, index=close.index)).dropna()

    # --- täglicher TR-CAPE (rückkaufbereinigt, Shiller) – Grundlage für den Einstiegs-Score
    shtr = sh[sh["trcape"].notna() & (sh["trcape"] > 0)]
    e10tr = dict(zip(shtr["key"], shtr["e10tr"]))
    last_key_tr = int(shtr["key"].max())
    trc = []
    for k in keys:
        k = int(k)
        trc.append(e10tr[last_key_tr] if k > last_key_tr else e10tr.get(k, float("nan")))
    trcape = (close / pd.Series(trc, index=close.index)).dropna()
    cur_tr = float(trcape.iloc[-1])

    last_day = cape.index[-1]
    cur = float(cape.iloc[-1])
    start20 = last_day - pd.DateOffset(years=20)

    windows = {}
    for y in (5, 10, 20):
        s = cape[cape.index > last_day - pd.DateOffset(years=y)]
        mu, sd = float(s.mean()), float(s.std())
        z = (cur - mu) / sd
        windows[str(y)] = {
            "mean": r2(mu), "sd": r2(sd), "z": r2(z),
            "rating": rating(z),
            "percentile": r2((s < cur).mean() * 100, 0),
        }
    longrun = float(sh["cape"].mean())

    # --- rollierende Ø/σ (graue Kanäle): täglich (letzte 20 J.) und monatlich (seit 1881)
    daily = {"t": [d.strftime("%Y-%m-%d") for d in cape.index[cape.index > start20]]}
    daily["v"] = [r2(v) for v in cape[cape.index > start20].values]
    for y in (5, 10, 20):
        roll = cape.rolling(f"{int(y * 365.25)}D", min_periods=int(y * 252 * 0.95))
        m, sd = roll.mean(), roll.std()
        daily[f"m{y}"] = [r2(v) for v in m[m.index > start20].values]
        daily[f"s{y}"] = [r2(v) for v in sd[sd.index > start20].values]

    mon = sh.set_index("key")["cape"].astype(float).copy()
    cur_key = last_day.year * 100 + last_day.month
    mon.loc[cur_key] = cur          # laufender Monat = aktueller Tageswert
    mon = mon.sort_index()
    monthly = {"t": [f"{k // 100}-{k % 100:02d}-01" for k in mon.index], "v": [r2(v) for v in mon.values]}
    for y in (5, 10, 20):
        roll = mon.rolling(12 * y, min_periods=12 * y)
        monthly[f"m{y}"] = [r2(v) for v in roll.mean().values]
        monthly[f"s{y}"] = [r2(v) for v in roll.std().values]

    # --- Kurs: 200/50-Tage-Linie, 200-Wochen-Linie, Wochenkerzen 20 Jahre
    sma200 = close.rolling(200).mean()
    sma50 = close.rolling(50).mean()
    wk = px.copy()
    # Alte Yahoo-Daten (vor ~1962) haben nur Schlusskurse: fehlende/Null-Werte mit dem Schlusskurs auffüllen
    for col in ("Open", "High", "Low"):
        bad = wk[col].isna() | (wk[col] <= 0)
        wk.loc[bad, col] = wk.loc[bad, "Close"]
    wk["High"] = wk[["Open", "High", "Close"]].max(axis=1)
    wk["Low"] = wk[["Open", "Low", "Close"]].min(axis=1)
    wk["wk"] = wk.index.to_period("W-FRI")
    wclose = wk.groupby("wk")["Close"].last()
    sma200w = wclose.rolling(200).mean()
    weeks = []
    for per, g in wk.groupby("wk"):
        last = g.index[-1]
        weeks.append({
            "t": g.index[0].strftime("%Y-%m-%d"),
            "o": r2(g["Open"].iloc[0]), "h": r2(g["High"].max()),
            "l": r2(g["Low"].min()), "c": r2(g["Close"].iloc[-1]),
            "s200": r2(sma200.loc[last]), "s50": r2(sma50.loc[last]), "w200": r2(sma200w.loc[per]),
        })

    # --- Einstiegssignal
    wcape_s = trcape.groupby(trcape.index.to_period("W-FRI")).last()
    pers = list(wk.groupby("wk").groups.keys())
    wcape = [float(wcape_s[p]) if p in wcape_s.index else None for p in pers]
    wc_ = [w["c"] for w in weeks]
    score, episodes, sstate = signal_model(wc_, [w["l"] for w in weeks], [w["w200"] for w in weeks], wcape)
    mon_tr = shtr.set_index("key")["trcape"].astype(float).copy()
    mon_tr.loc[last_day.year * 100 + last_day.month] = cur_tr
    mon_tr = mon_tr.sort_index()
    mroll = mon_tr.rolling(240, min_periods=240)
    mmean, msd = mroll.mean(), mroll.std()

    sh_k = sh.set_index("key")
    div_m, cpi_m = sh_k["div"], sh_k["cpi"]

    def mval(series, k):
        if k in series.index:
            return float(series[k])
        return float(series[series.index <= k].iloc[-1])

    wkeys = [pd.Timestamp(w_["t"]).year * 100 + pd.Timestamp(w_["t"]).month for w_ in weeks]
    trn = [1.0]
    for i in range(1, len(wc_)):
        trn.append(trn[-1] * (wc_[i] + mval(div_m, wkeys[i]) / 52) / wc_[i - 1])
    cpis = [mval(cpi_m, k) for k in wkeys]
    trr = [trn[i] / cpis[i] for i in range(len(trn))]
    scale = wc_[-1] / trr[-1]
    trr = [x * scale for x in trr]          # in heutiger Kaufkraft, letzter Wert = aktueller Kurs
    for i, w_ in enumerate(weeks):
        w_["tr"] = r2(trr[i])

    def fwd(i, n):
        # reale Gesamtrendite p.a. (inkl. reinvestierter Dividenden, nach US-Inflation)
        return r2(((trr[i + n] / trr[i]) ** (52 / n) - 1) * 100, 1) if i + n < len(trr) else None

    def dd1(i):
        lows = [w["l"] for w in weeks[i + 1:i + 53]]
        return r2((min(lows) / wc_[i] - 1) * 100, 1) if lows else None

    def zval(i):
        t = pd.Timestamp(weeks[i]["t"])
        k = t.year * 100 + t.month
        k = k if k in mmean.index else mmean.index[mmean.index <= k].max()
        m_, s_ = mmean.get(k), msd.get(k)
        return r2((wcape[i] - m_) / s_) if m_ == m_ and s_ else None

    signals = []
    for ep in episodes:
        if ep["signal"] is None:
            continue
        i = ep["signal"]
        signals.append({"touch": weeks[ep["start"]]["t"], "t": weeks[i]["t"], "c": wc_[i], "cape": r2(wcape[i]),
                        "z": zval(i), "r1": fwd(i, 52), "r3": fwd(i, 156), "r5": fwd(i, 260), "r10": fwd(i, 520), "r20": fwd(i, 1040), "r30": fwd(i, 1560), "dd": dd1(i),
                        "wait": i - ep["start"]})
        signals[-1]["ok"] = signals[-1]["z"] is not None and signals[-1]["z"] <= Z_MAX_100

    # --- Kombinierter Score: 200W-Abstand + CAPE (Glockenform um 50), Wende-Filter, 100 = strenge Regel
    n_ = len(wc_)
    zw = [None] * n_
    for i in range(n_):
        if wcape[i] is None:
            continue
        t = pd.Timestamp(weeks[i]["t"])
        k = t.year * 100 + t.month
        k = k if k in mmean.index else mmean.index[mmean.index <= k].max()
        m_, s_ = mmean.get(k), msd.get(k)
        if m_ == m_ and s_ == s_ and s_:
            zw[i] = (wcape[i] - m_) / s_
    def cape_shape(zv):
        # über dem Ø linear (teurer = schlechter), darunter S-Kurve: ab ca. -1σ voll, noch billiger bringt nichts extra
        return zv if zv >= 0 else -1.0 / (1.0 + math.exp(-((-zv) - CAPE_MID) / CAPE_WIDTH))

    zf = [None if v is None else cape_shape(v) for v in zw]
    distw = [(wc_[i] / weeks[i]["w200"] - 1) * 100 if weeks[i]["w200"] else None for i in range(n_)]
    ok = [i for i in range(n_) if zw[i] is not None and distw[i] is not None]
    dmu = sum(distw[i] for i in ok) / len(ok)
    dsd = (sum((distw[i] - dmu) ** 2 for i in ok) / len(ok)) ** 0.5
    zmu = sum(zf[i] for i in ok) / len(ok)
    zsd = (sum((zf[i] - zmu) ** 2 for i in ok) / len(ok)) ** 0.5
    comp = {i: -(W_DIST * (distw[i] - dmu) / dsd + W_CAPE * (zf[i] - zmu) / zsd) for i in ok}
    csd = (sum(v * v for v in comp.values()) / len(comp)) ** 0.5
    new_score = [None] * n_
    for i in ok:
        raw = 50 + SPREAD * comp[i] / csd
        mn = min(x for x in wcape[max(0, i - TURN_WEEKS + 1):i + 1] if x is not None)
        turn = min(1.0, max(0.0, (wcape[i] / mn - 1) / SIG_RISE))
        v = 50 + (raw - 50) * turn if raw > 50 else raw
        v = min(CAP, max(0.0, v))
        new_score[i] = v
    for ep in episodes:
        si = ep["signal"]
        if si is None:
            continue
        zs_ = zval(si)
        if zs_ is None or zs_ > Z_MAX_100:
            continue
        stop = ep["end"] if ep["end"] is not None else min(n_, si + SIG_WINDOW)
        for i in range(si, stop):
            if new_score[i] is not None:
                new_score[i] = 100.0

    # Rückblick: Einstieg beim ersten Erreichen einer Schwelle (nach mind. 26 Wochen darunter)
    def firsts(thr):
        ent, below = [], 10 ** 6
        for i in range(n_):
            v = new_score[i]
            if v is None:
                continue
            if v >= thr - 1e-9 and below >= 26:
                ent.append(i)
            below = below + 1 if v < thr - 1e-9 else 0
        return ent

    base1 = [fwd(i, 52) for i in ok if fwd(i, 52) is not None]
    def med(a):
        a = sorted(a)
        k = len(a)
        return None if k == 0 else (a[k // 2] if k % 2 else (a[k // 2 - 1] + a[k // 2]) / 2)

    def agg(idx):
        r1 = [fwd(i, 52) for i in idx if fwd(i, 52) is not None]
        r5 = [fwd(i, 260) for i in idx if fwd(i, 260) is not None]
        r10 = [fwd(i, 520) for i in idx if fwd(i, 520) is not None]
        r20 = [fwd(i, 1040) for i in idx if fwd(i, 1040) is not None]
        r30 = [fwd(i, 1560) for i in idx if fwd(i, 1560) is not None]
        return {"n": len(idx),
                "r1": r2(med(r1), 1) if r1 else None,
                "pos": r2(100 * sum(x > 0 for x in r1) / len(r1), 0) if r1 else None,
                "r5": r2(med(r5), 1) if r5 else None,
                "r10": r2(med(r10), 1) if r10 else None,
                "r20": r2(med(r20), 1) if r20 else None,
                "r30": r2(med(r30), 1) if r30 else None,
                "w10": r2(min(r10), 1) if r10 else None,
                "stat": "median",
                "n10": len(r10), "n20": len(r20), "n30": len(r30)}

    thresholds = [dict(score="Jede Woche", **agg(ok))]
    for thr in (50, 60, 70, 80, 100):
        thresholds.append(dict(score=thr, **agg(firsts(thr))))
    # Verteilung: wie viel Prozent aller Wochen in welchem Bereich lagen
    bands = []
    for lo in list(range(0, 100, 10)) + [100]:
        hi = lo + 10 if lo < 100 else 101
        idx = [i for i in ok if lo <= new_score[i] < hi]
        if idx:
            bands.append(dict(lo=lo, hi=hi, share=r2(100 * len(idx) / len(ok), 1), **agg(idx)))
    if sstate.get("active"):
        sstate["touch"] = weeks[sstate["touch"]]["t"]
        si_ = sstate["signal"]
        sstate["signalOk"] = si_ is not None and zval(si_) is not None and zval(si_) <= Z_MAX_100
        sstate["signal"] = weeks[si_]["t"] if si_ is not None else None
        sstate["capeMin"] = r2(sstate["capeMin"])
    last_k = mmean.index.max()
    sig_out = {
        "rule": {"rise": SIG_RISE, "dist": SIG_DIST, "window": SIG_WINDOW, "maxWait": SIG_MAXWAIT,
                 "wDist": W_DIST, "wCape": W_CAPE, "spread": SPREAD, "cap": CAP, "turnWeeks": TURN_WEEKS, "zMax100": Z_MAX_100, "e10tr": round(float(close.iloc[-1]) / cur_tr, 4), "base": "TR-CAPE", "capeMid": CAPE_MID, "capeWidth": CAPE_WIDTH,
                 "dMu": round(dmu, 4), "dSd": round(dsd, 4), "zMu": round(zmu, 4), "zSd": round(zsd, 4),
                 "cSd": round(csd, 4), "m20": round(float(mmean[last_k]), 4), "s20": round(float(msd[last_k]), 4),
                 "capeLast": [None if x is None else round(x, 4) for x in wcape[-TURN_WEEKS:]]},
        "score": [None if x is None else round(x) for x in new_score],
        "oldCurrent": round(score[-1]) if score[-1] is not None else None,
        "signals": signals, "thresholds": thresholds, "bands": bands, "state": sstate,
        "horizon": {str(y): weeks[len(weeks) - 1 - 52 * y]["t"] for y in (10, 20, 30)},
        "current": round(new_score[-1]) if new_score[-1] is not None else None,
        "parts": {"dist": r2(distw[-1], 1), "z": r2(zw[-1]), "tr": r2(cur_tr)},
    }

    last_close = float(close.iloc[-1])
    w200_now = float(sma200w.iloc[-1])
    out = {
        "updated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "date": last_day.strftime("%Y-%m-%d"),
        "priceSource": src,
        "cape": {
            "current": r2(cur),
            # E10 in heutigen Dollar: Live-CAPE = Live-Kurs / e10
            "e10": round(last_close / cur, 4),
            "tr": {"current": r2(cur_tr), "m20": r2(float(mmean.iloc[-1])), "s20": r2(float(msd.iloc[-1])),
                   "z": r2((cur_tr - float(mmean.iloc[-1])) / float(msd.iloc[-1])), "longrun": r2(float(mon_tr.mean())),
                   "e10": round(last_close / cur_tr, 4)},
            "windows": windows,
            "daily": daily,
            "monthly": monthly,
            "longrunMean": r2(longrun),
            "longrunSince": first_key // 100,
            "shillerMonth": f"{last_key // 100}-{last_key % 100:02d}",
            "shillerCape": r2(float(sh.loc[sh["key"] == last_key, "cape"].iloc[0])),
        },
        "spx": {
            "close": r2(last_close),
            "change1d": r2((last_close / float(close.iloc[-2]) - 1) * 100),
            "sma200": r2(sma200.iloc[-1]), "sma50": r2(sma50.iloc[-1]), "sma200w": r2(w200_now),
            "vs200": r2((last_close / sma200.iloc[-1] - 1) * 100),
            "vs50": r2((last_close / sma50.iloc[-1] - 1) * 100),
            "vs200w": r2((last_close / w200_now - 1) * 100),
            # für die Live-Berechnung in der App: letzte 199 Tagesschlusskurse
            "d199": [r2(v) for v in close.iloc[-199:].values],
            "weeks": weeks,
        },
        "signal": sig_out,
    }
    cape20 = daily["v"]

    # Plausibilitätsprüfung, damit nie Unsinn in der App landet
    assert 5 < cur < 80, f"CAPE unplausibel: {cur}"
    assert len(weeks) > 2000, f"zu wenige Wochen: {len(weeks)}"
    assert len(cape20) > 4500, f"zu wenige CAPE-Tage: {len(cape20)}"

    import os
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, separators=(",", ":"))
    print(f"OK {out['date']}: CAPE {cur:.2f} | 20J-Ø {windows['20']['mean']} ({windows['20']['rating']}) | "
          f"S&P {last_close:.2f}, vs SMA200 {out['spx']['vs200']}% | Shiller bis {out['cape']['shillerMonth']} "
          f"(CAPE {out['cape']['shillerCape']}) | SMA200W {w200_now:.2f} | Score {sig_out['current']} | "
          f"Signale {len(signals)}: {', '.join(x['t'][:7] for x in signals)} | Quelle {src}")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"::error::{e}")
        raise
