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
        try:
            c = float(c)
        except (TypeError, ValueError):
            c = float("nan")
        rows.append((year, month, p, c))
    sh = pd.DataFrame(rows, columns=["year", "month", "price", "cape"])
    sh = sh[sh["cape"].notna() & (sh["cape"] > 0)]
    sh["key"] = sh["year"] * 100 + sh["month"]
    sh["e10"] = sh["price"] / sh["cape"]
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

    last_close = float(close.iloc[-1])
    w200_now = float(sma200w.iloc[-1])
    out = {
        "updated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "date": last_day.strftime("%Y-%m-%d"),
        "priceSource": src,
        "cape": {
            "current": r2(cur),
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
            "weeks": weeks,
        },
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
          f"(CAPE {out['cape']['shillerCape']}) | SMA200W {w200_now:.2f} | Quelle {src}")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"::error::{e}")
        raise
