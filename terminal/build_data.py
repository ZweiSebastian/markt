"""
Daten für das Markt Terminal (Mac).

Sammelt Markt- und Makroreihen, rechnet abgeleitete Reihen, den Stress-Zähler (Fortschreibung von
research/stress_analysis.py) und das Einschätzungs-Modell (terminal/model.py).
Ausgabe: out/terminal.json (der Workflow schreibt sie auf den Branch terminal-data).

Speicherung: Tageswerte der letzten 11 Jahre, davor ein Wert pro Woche (Charts "Max" reichen so
je nach Reihe bis 1962/1970 zurück, ohne dass die Datei zu groß wird). Monatsreihen vollständig.

Quellen
- Yahoo Finance (yfinance): Indizes (inkl. MSCI World seit 1972), ETFs, Futures, Währungen, Krypto, VIX
- Federal Reserve H.15 über DBnomics: US-Zinsen täglich seit 1962, 3M-T-Bill monatlich seit 1934
- US-Finanzministerium: aktuelle Zinskurve, reale Renditen (TIPS) seit 2003
- NY Fed: effektiver Fed-Funds-Satz (aktuell)
- EZB: Einlagenzins, 10J-Euro-Zins (AAA), Inflation (HICP), Bilanzsumme
- BLS: Inflation, Kerninflation, Arbeitslosenquote, Beschäftigung (seit 1948)
- Chicago Fed: Finanzbedingungen (NFCI) seit 1971
- OECD: Frühindikator (CLI) USA und OECD gesamt
- US-Arbeitsministerium: Erstanträge auf Arbeitslosenhilfe (wöchentlich)
- AAII: Anlegerstimmung (Bullen minus Bären) seit 1987
- Freddie Mac: 30J-Hypothekenzins; EIA: Diesel; BEA (DBnomics): BIP für den Buffett-Indikator
- MSCI: MSCI World in Euro (Netto, mit Dividenden) seit 2000
- R. Shiller (shillerdata.com): S&P 500, Dividenden, Gewinne, CAPE, CPI seit 1871
- data/markt.json (diese Repo): täglicher CAPE, Einstiegssignal

Langsame Quellen werden aus dem letzten Lauf übernommen, wenn sie jünger als 12 Stunden sind.
Jede Quelle einzeln, Fehler landen in "diag" und brechen den Lauf nicht ab.
"""
import io
import json
import math
import os
import re
import sys
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd
import requests

UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/124 Safari/537.36"}
NOW = datetime.now(timezone.utc)
TODAY = pd.Timestamp(NOW.date())
START = pd.Timestamp("1970-01-01")
DAILY_KEEP = TODAY - pd.Timedelta(days=11 * 365 + 5)     # davor wöchentlich speichern
OUT = "out/terminal.json"
PREV_URL = f"https://raw.githubusercontent.com/ZweiSebastian/markt/{os.environ.get('DATA_BRANCH', 'terminal-data')}/terminal.json"
H = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(H)
sys.path.insert(0, os.path.join(ROOT, "scripts"))
sys.path.insert(0, H)

diag = []          # (quelle, ok, text)
series = {}        # id -> gespeicherte (ggf. ausgedünnte) Reihe
raw = {}           # id -> volle pandas-Reihe für Berechnungen


def note(src, ok, txt=""):
    diag.append({"src": src, "ok": bool(ok), "msg": str(txt)[:300]})
    print(("OK   " if ok else "FEHL ") + src + ("  " + str(txt)[:200] if txt else ""), flush=True)


def get(url, t=40, **kw):
    r = requests.get(url, headers=UA, timeout=t, **kw)
    r.raise_for_status()
    return r


# ------------------------------------------------------------------ Katalog Yahoo
# kind: price (Rendite = log-Änderung), rate (Änderung in Prozentpunkten), level (log-Änderung, z.B. VIX)
YAHOO = [
    # id, ticker, name, gruppe, einheit, kind
    ("spx", "^GSPC", "S&P 500", "aktien", "Pkt", "price"),
    ("msci", "^990100-USD-STRD", "MSCI World", "aktien", "Pkt", "price"),
    ("ndx", "^NDX", "Nasdaq 100", "aktien", "Pkt", "price"),
    ("rut", "^RUT", "Russell 2000", "aktien", "Pkt", "price"),
    ("w5000", "^W5000", "Wilshire 5000 (US-Gesamtmarkt)", "aktien", "Pkt", "price"),
    ("world", "URTH", "MSCI World (ETF, USD)", "aktien", "$", "price"),
    ("eunl", "EUNL.DE", "MSCI World (ETF, EUR)", "aktien", "€", "price"),
    ("acwi", "ACWI", "MSCI All Country (ETF)", "aktien", "$", "price"),
    ("dax", "^GDAXI", "DAX", "aktien", "Pkt", "price"),
    ("sx5e", "^STOXX50E", "Euro Stoxx 50", "aktien", "Pkt", "price"),
    ("ftse", "^FTSE", "FTSE 100", "aktien", "Pkt", "price"),
    ("nikkei", "^N225", "Nikkei 225", "aktien", "Pkt", "price"),
    ("hsi", "^HSI", "Hang Seng", "aktien", "Pkt", "price"),
    ("em", "EEM", "Schwellenländer (ETF)", "aktien", "$", "price"),
    ("spy", "SPY", "S&P 500 ETF", "aktien", "$", "price"),
    ("rsp", "RSP", "S&P 500 gleichgewichtet", "aktien", "$", "price"),
    ("vix", "^VIX", "VIX", "risiko", "Pkt", "level"),
    ("vix3m", "^VIX3M", "VIX 3 Monate", "risiko", "Pkt", "level"),
    ("vvix", "^VVIX", "VVIX (Vola des VIX)", "risiko", "Pkt", "level"),
    ("skew", "^SKEW", "SKEW (Crash-Absicherung)", "risiko", "Pkt", "level"),
    ("move", "^MOVE", "MOVE (Anleihe-Vola)", "risiko", "Pkt", "level"),
    ("tlt", "TLT", "US-Anleihen 20J+ (ETF)", "anleihen", "$", "price"),
    ("ief", "IEF", "US-Anleihen 7–10J (ETF)", "anleihen", "$", "price"),
    ("hyg", "HYG", "Hochzins-Anleihen (ETF)", "anleihen", "$", "price"),
    ("lqd", "LQD", "Unternehmensanleihen IG (ETF)", "anleihen", "$", "price"),
    ("tip", "TIP", "Inflationsgeschützte (ETF)", "anleihen", "$", "price"),
    ("wti", "CL=F", "Öl WTI", "rohstoffe", "$/bbl", "price"),
    ("brent", "BZ=F", "Öl Brent", "rohstoffe", "$/bbl", "price"),
    ("natgas", "NG=F", "Erdgas Henry Hub", "rohstoffe", "$/MMBtu", "price"),
    ("heatoil", "HO=F", "Heizöl/Diesel (Future)", "rohstoffe", "$/gal", "price"),
    ("gold", "GC=F", "Gold", "rohstoffe", "$/oz", "price"),
    ("silver", "SI=F", "Silber", "rohstoffe", "$/oz", "price"),
    ("copper", "HG=F", "Kupfer", "rohstoffe", "$/lb", "price"),
    ("dxy", "DX-Y.NYB", "Dollar-Index", "fx", "Pkt", "price"),
    ("eurusd", "EURUSD=X", "EUR/USD", "fx", "$", "price"),
    ("usdjpy", "USDJPY=X", "USD/JPY", "fx", "¥", "price"),
    ("usdcny", "USDCNY=X", "USD/CNY", "fx", "¥", "price"),
    ("btc", "BTC-USD", "Bitcoin", "krypto", "$", "price"),
    ("eth", "ETH-USD", "Ethereum", "krypto", "$", "price"),
    ("xlk", "XLK", "Technologie", "sektoren", "$", "price"),
    ("xlf", "XLF", "Finanzen", "sektoren", "$", "price"),
    ("xle", "XLE", "Energie", "sektoren", "$", "price"),
    ("xlv", "XLV", "Gesundheit", "sektoren", "$", "price"),
    ("xli", "XLI", "Industrie", "sektoren", "$", "price"),
    ("xly", "XLY", "Zykl. Konsum", "sektoren", "$", "price"),
    ("xlp", "XLP", "Basiskonsum", "sektoren", "$", "price"),
    ("xlu", "XLU", "Versorger", "sektoren", "$", "price"),
    ("xlb", "XLB", "Grundstoffe", "sektoren", "$", "price"),
    ("xlre", "XLRE", "Immobilien", "sektoren", "$", "price"),
    ("xlc", "XLC", "Kommunikation", "sektoren", "$", "price"),
    ("smh", "SMH", "Halbleiter", "sektoren", "$", "price"),
    ("kre", "KRE", "US-Regionalbanken", "sektoren", "$", "price"),
    ("xhb", "XHB", "Hausbau", "sektoren", "$", "price"),
    ("tnx_y", "^TNX", "10J (Yahoo)", "intern", "%", "rate"),
    ("irx_y", "^IRX", "3M (Yahoo)", "intern", "%", "rate"),
]
LIVE = {i: t for i, t, *_ in YAHOO}   # für Live-Kurse in der App


def put(sid, s, name, group, unit, kind, src, freq="d", dec=None):
    s = pd.to_numeric(s, errors="coerce").dropna()
    s.index = pd.to_datetime(s.index)
    s = s[~s.index.duplicated(keep="last")].sort_index()
    s = s[s.index <= TODAY + pd.Timedelta(days=1)]
    if len(s) < 3:
        note(sid, False, "zu wenige Werte")
        return
    raw[sid] = s
    st = s
    if freq == "d":   # älter als 11 Jahre: letzter Wert je Woche
        old, new = s[s.index < DAILY_KEEP], s[s.index >= DAILY_KEEP]
        if len(old):
            old = old[~old.index.to_period("W-FRI").duplicated(keep="last")]
            st = pd.concat([old, new])
    if dec is None:
        m = float(s.tail(500).abs().median()) or 1.0
        dec = max(0, min(6, 4 - int(math.floor(math.log10(m)))))
    days = ((st.index - pd.Timestamp("1970-01-01")) // pd.Timedelta(days=1)).astype(int).tolist()
    # Tage als Abstände speichern (erster Wert absolut)
    dt = [days[0]] + [b - a for a, b in zip(days, days[1:])]
    series[sid] = {"name": name, "g": group, "u": unit, "k": kind, "src": src, "f": freq,
                   "dt": dt, "v": [round(float(x), dec) for x in st.values]}


def ser(sid):
    if sid in raw:
        return raw[sid]
    d = series.get(sid)
    if not d:
        return None
    days = d["t"] if "t" in d else np.cumsum(d["dt"]).tolist()
    s = pd.Series(d["v"], index=pd.Timestamp("1970-01-01") + pd.to_timedelta(days, unit="D"))
    return s


# ------------------------------------------------------------------ vorheriger Lauf (Cache)
CACHE_VERSION = 2
cache_meta = {}
prev = {}
try:
    prev = get(PREV_URL, 30).json()
    note("vorheriger Lauf", True, prev.get("updated"))
except Exception as e:  # noqa
    note("vorheriger Lauf", False, e)


def cached(key, hours=12):
    c = (prev.get("cache") or {}).get(key)
    if not c:
        return None
    try:
        age = NOW - datetime.fromisoformat(c["at"].replace("Z", "+00:00"))
    except Exception:  # noqa
        return None
    if age > timedelta(hours=hours) or c.get("v") != CACHE_VERSION:
        return None
    return c




def slow(key, fn, ids, hours=12):
    """Führt eine langsame Quelle aus oder übernimmt sie aus dem Cache. ids: erzeugte Serien-IDs."""
    c = cached(key, hours)
    if c and all(i in prev.get("series", {}) for i in ids):
        for i in ids:
            series[i] = prev["series"][i]
        cache_meta[key] = c
        note(key, True, "aus Cache " + c["at"])
        return
    try:
        fn()
        cache_meta[key] = {"at": NOW.strftime("%Y-%m-%dT%H:%M:%SZ"), "v": CACHE_VERSION}
    except Exception as e:  # noqa
        note(key, False, f"{type(e).__name__}: {e}")
        for i in ids:
            if i in prev.get("series", {}) and i not in series:
                series[i] = prev["series"][i]
        if key in (prev.get("cache") or {}):
            cache_meta[key] = prev["cache"][key]


# ------------------------------------------------------------------ Yahoo
def prev_series(sid):
    d = (prev.get("series") or {}).get(sid)
    if not d:
        return None
    days = d["t"] if "t" in d else np.cumsum(d["dt"]).tolist()
    return pd.Series(d["v"], index=pd.Timestamp("1970-01-01") + pd.to_timedelta(days, unit="D"))


def yahoo():
    """Volle Historie höchstens alle 20 Std., sonst nur die letzten 40 Tage an den letzten Lauf anhängen."""
    import yfinance as yf
    full = cached("yahoo_full", 20) is None or any(prev_series(sid) is None for sid, *_ in YAHOO)
    start = START if full else TODAY - pd.Timedelta(days=40)
    tick = [t for _, t, *_ in YAHOO]
    got = {}
    for chunk in [tick[i:i + 10] for i in range(0, len(tick), 10)]:
        try:
            df = yf.download(chunk, start=start.strftime("%Y-%m-%d"), interval="1d", auto_adjust=True,
                             progress=False, threads=False, group_by="ticker")
            for t in chunk:
                try:
                    c = df[t]["Close"] if isinstance(df.columns, pd.MultiIndex) else df["Close"]
                    c = c.dropna()
                    if len(c) > (20 if full else 2):
                        got[t] = c
                except Exception:  # noqa
                    pass
        except Exception as e:  # noqa
            note("yahoo-block", False, e)
        time.sleep(1.5)
    for t in [t for t in tick if t not in got]:   # Einzelversuch
        try:
            h = yf.Ticker(t).history(start=start.strftime("%Y-%m-%d"), interval="1d", auto_adjust=True)
            if len(h) > (20 if full else 2):
                got[t] = h["Close"]
        except Exception as e:  # noqa
            note("yahoo " + t, False, e)
        time.sleep(1)
    for sid, t, name, g, u, k in YAHOO:
        old = prev_series(sid)
        if t in got:
            s = got[t]
            s.index = pd.to_datetime(s.index)
            if s.index.tz is not None:
                s.index = s.index.tz_localize(None)
            s.index = s.index.normalize()
            if not full and old is not None:
                # Kursanpassungen (Dividenden/Splits) an der Nahtstelle ausgleichen
                ov = s.index.intersection(old.index)
                if len(ov):
                    f = float(s[ov[0]] / old[ov[0]]) if old[ov[0]] else 1.0
                    old = old * f if abs(f - 1) > 1e-6 else old
                s = pd.concat([old[old.index < s.index.min()], s])
            put(sid, s, name, g, u, k, "Yahoo Finance")
        else:
            note("yahoo " + t, False, "keine Daten")
            if old is not None:
                put(sid, old, name, g, u, k, "Yahoo Finance (alt)")
    if full:
        cache_meta["yahoo_full"] = {"at": NOW.strftime("%Y-%m-%dT%H:%M:%SZ"), "v": CACHE_VERSION}
    elif "yahoo_full" in (prev.get("cache") or {}):
        cache_meta["yahoo_full"] = prev["cache"]["yahoo_full"]
    note("yahoo", True, f"{len(got)}/{len(tick)} Ticker ({'voll' if full else 'Ergänzung'})")


try:
    yahoo()
except Exception as e:  # noqa
    note("yahoo", False, e)
    for sid, *_ in YAHOO:
        if sid in prev.get("series", {}):
            series[sid] = prev["series"][sid]


# ------------------------------------------------------------------ Zinsen USA
def dbn(code, start="1970-01-01"):
    url = f"https://api.db.nomics.world/v22/series/{code}?observations=1&format=json"
    j = get(url, 90).json()
    doc = j["series"]["docs"][0]
    s = pd.Series(doc["value"], index=pd.to_datetime(doc["period"]))
    s = pd.to_numeric(s.replace("NA", np.nan), errors="coerce").dropna()
    return s[s.index >= start]


def treasury_year(y, kind="daily_treasury_yield_curve"):
    url = (f"https://home.treasury.gov/resource-center/data-chart-center/interest-rates/daily-treasury-rates.csv/"
           f"{y}/all?type={kind}&field_tdr_date_value={y}&page&_format=csv")
    d = pd.read_csv(io.StringIO(get(url, 40).text))
    d.index = pd.to_datetime(d["Date"])
    return d.sort_index()


H15 = {
    "y3m": ("FED/H15/RIFLGFCM03_N.B", "US-Zins 3 Monate", "3 Mo"),
    "y2": ("FED/H15/RIFLGFCY02_N.B", "US-Zins 2 Jahre", "2 Yr"),
    "y10": ("FED/H15/RIFLGFCY10_N.B", "US-Zins 10 Jahre", "10 Yr"),
    "y30": ("FED/H15/RIFLGFCY30_N.B", "US-Zins 30 Jahre", "30 Yr"),
}


def rates():
    hist = {}
    for sid, (code, name, col) in H15.items():
        try:
            hist[sid] = dbn(code)
        except Exception as e:  # noqa
            note("dbnomics " + sid, False, e)
            hist[sid] = pd.Series(dtype=float)
    tr = []
    for y in (NOW.year - 1, NOW.year):
        try:
            tr.append(treasury_year(y))
        except Exception as e:  # noqa
            note(f"treasury {y}", False, e)
    tr = pd.concat(tr) if tr else pd.DataFrame()
    for sid, (code, name, col) in H15.items():
        s = hist[sid]
        if len(tr) and col in tr:
            s = pd.concat([s, tr[col].dropna()])
            s = s[~s.index.duplicated(keep="last")]
        if len(s) < 50:
            ys = ser("tnx_y" if sid == "y10" else "irx_y" if sid == "y3m" else "")
            if ys is not None:
                s = ys
        put(sid, s, name, "zinsen", "%", "rate", "Fed H.15 / US Treasury", dec=3)
    rr = []
    for y in range(2003, NOW.year + 1):
        try:
            rr.append(treasury_year(y, "daily_treasury_real_yield_curve")["10 YR"])
        except Exception as e:  # noqa
            note(f"treasury real {y}", False, e)
        time.sleep(0.25)
    if rr:
        put("real10", pd.concat(rr), "US-Realzins 10J (TIPS)", "zinsen", "%", "rate", "US Treasury", dec=3)
    # 3M-T-Bill monatlich seit 1934 (für das Modell)
    put("tbill_m", dbn("FED/H15/RIFSGFSM03_N.M", "1934-01-01"), "US-T-Bill 3M (monatlich)", "intern", "%", "rate", "Fed H.15", "m", 2)
    # Fed Funds täglich (lange Historie)
    put("ff_long", dbn("FED/H15/RIFSPFF_N.B", "1970-01-01"), "Fed Funds (H.15)", "intern", "%", "rate", "Fed H.15", dec=2)
    note("zinsen", True, ", ".join(f"{k}:{len(v)}" for k, v in hist.items()))


slow("zinsen", rates, ["y3m", "y2", "y10", "y30", "real10", "tbill_m", "ff_long"])
if cache_meta.get("zinsen", {}).get("at") != NOW.strftime("%Y-%m-%dT%H:%M:%SZ"):
    try:   # im Cache-Fall die letzten Tage frisch nachziehen
        tr = treasury_year(NOW.year)
        for sid, (code, name, col) in H15.items():
            s = ser(sid)
            if s is not None and col in tr:
                s = pd.concat([s, tr[col].dropna()])
                s = s[~s.index.duplicated(keep="last")]
                put(sid, s, name, "zinsen", "%", "rate", "Fed H.15 / US Treasury", dec=3)
    except Exception as e:  # noqa
        note("treasury aktuell", False, e)


def fedfunds():
    end = NOW.strftime("%Y-%m-%d")
    j = get(f"https://markets.newyorkfed.org/api/rates/unsecured/effr/search.json?startDate=2016-03-01&endDate={end}", 60).json()
    rows = j["refRates"]
    s = pd.Series([r["percentRate"] for r in rows], index=pd.to_datetime([r["effectiveDate"] for r in rows]))
    old = ser("ff_long")
    if old is not None:
        s = pd.concat([old[old.index < s.index.min()], s])
    put("effr", s, "Fed Funds (effektiv)", "zinsen", "%", "rate", "NY Fed / Fed H.15", dec=2)


slow("fedfunds", fedfunds, ["effr"])


def ecb_csv(key, start="1990-01-01"):
    url = f"https://data-api.ecb.europa.eu/service/data/{key}?startPeriod={start}&format=csvdata"
    d = pd.read_csv(io.StringIO(get(url, 60).text))
    tp = d["TIME_PERIOD"].astype(str)
    if tp.str.contains("-W").any():   # Wochenangaben wie 1999-W01 -> Freitag der Woche
        dt = pd.to_datetime(tp + "-5", format="%G-W%V-%u")
    else:
        dt = pd.to_datetime(tp)
    return pd.Series(d["OBS_VALUE"].values, index=dt)


def ecb():
    put("ecb", ecb_csv("FM/D.U2.EUR.4F.KR.DFR.LEV", "1999-01-01"), "EZB-Einlagenzins", "zinsen", "%", "rate", "EZB", dec=2)
    put("eu10", ecb_csv("YC/B.U2.EUR.4F.G_N_A.SV_C_YM.SR_10Y", "2004-01-01"), "Euro-Zins 10J (AAA-Kurve)", "zinsen", "%", "rate", "EZB", dec=3)
    put("hicp", ecb_csv("ICP/M.U2.N.000000.4.ANR", "1997-01-01"), "Euro-Inflation (HICP)", "konjunktur", "%", "rate", "EZB", "m", 1)
    put("ecbbs", ecb_csv("ILM/W.U2.C.T000000.Z5.Z01", "1999-01-01") / 1e6, "EZB-Bilanzsumme", "konjunktur", "Bio. €", "price", "EZB", "w", 3)


slow("ezb", ecb, ["ecb", "eu10", "hicp", "ecbbs"])


# ------------------------------------------------------------------ Konjunktur (BLS, lange Historie)
BLS = {"CUUR0000SA0": "cpi_idx", "CUUR0000SA0L1E": "core_idx", "LNS14000000": "unemp", "CES0000000001": "payrolls"}


def bls():
    out = {k: {} for k in BLS.values()}
    for y0 in range(1948, NOW.year + 1, 10):
        body = {"seriesid": list(BLS), "startyear": str(y0), "endyear": str(min(y0 + 9, NOW.year))}
        j = requests.post("https://api.bls.gov/publicAPI/v1/timeseries/data/", json=body, headers=UA, timeout=60).json()
        if j.get("status") != "REQUEST_SUCCEEDED":
            raise RuntimeError(j.get("message"))
        for s in j["Results"]["series"]:
            for r in s["data"]:
                if r["period"].startswith("M") and r["period"] != "M13" and re.fullmatch(r"-?[0-9.]+", str(r["value"]).strip()):
                    out[BLS[s["seriesID"]]][pd.Timestamp(int(r["year"]), int(r["period"][1:]), 1)] = float(r["value"])
        time.sleep(0.5)
    out = {k: pd.Series(v).sort_index() for k, v in out.items()}
    cpi, core = out["cpi_idx"], out["core_idx"]
    put("cpi", (cpi / cpi.shift(12) - 1) * 100, "US-Inflation (CPI, ggü. Vorjahr)", "konjunktur", "%", "rate", "BLS", "m", 2)
    put("core", (core / core.shift(12) - 1) * 100, "US-Kerninflation (ggü. Vorjahr)", "konjunktur", "%", "rate", "BLS", "m", 2)
    put("unemp", out["unemp"], "US-Arbeitslosenquote", "konjunktur", "%", "rate", "BLS", "m", 1)
    put("payrolls", out["payrolls"].diff(), "US-Stellen (Veränderung, Tsd.)", "konjunktur", "Tsd.", "rate", "BLS", "m", 0)
    u3 = out["unemp"].rolling(3).mean()
    put("sahm", u3 - u3.shift(1).rolling(12).min(), "Sahm-Regel", "konjunktur", "Pp.", "rate", "BLS (berechnet)", "m", 2)


slow("bls", bls, ["cpi", "core", "unemp", "payrolls", "sahm"])


# ------------------------------------------------------------------ Finanzbedingungen, Frühindikatoren, Stimmung
def nfci():
    d = pd.read_csv(io.StringIO(get("https://www.chicagofed.org/-/media/publications/nfci/nfci-data-series-csv.csv", 60).text))
    idx = pd.to_datetime(d.iloc[:, 0], format="%m/%d/%Y")
    put("nfci", pd.Series(d["NFCI"].values, index=idx), "Finanzbedingungen (NFCI)", "risiko", "", "rate", "Chicago Fed", "w", 3)
    put("anfci", pd.Series(d["ANFCI"].values, index=idx), "Finanzbedingungen bereinigt (ANFCI)", "risiko", "", "rate", "Chicago Fed", "w", 3)


slow("nfci", nfci, ["nfci", "anfci"])


def oecd():
    url = ("https://sdmx.oecd.org/public/rest/data/OECD.SDD.STES,DSD_STES@DF_CLI,4.1/USA+G7+OECD.M.LI...AA...H"
           "?startPeriod=1960-01&dimensionAtObservation=AllDimensions&format=csvfilewithlabels")
    d = pd.read_csv(io.StringIO(get(url, 90).text))
    for area, sid, name in [("USA", "cli_us", "OECD-Frühindikator USA"), ("G7", "cli_g7", "OECD-Frühindikator G7")]:
        x = d[d["REF_AREA"] == area]
        s = pd.Series(x["OBS_VALUE"].values, index=pd.to_datetime(x["TIME_PERIOD"]))
        put(sid, s, name, "konjunktur", "", "rate", "OECD", "m", 2)


slow("oecd", oecd, ["cli_us", "cli_g7"])


def claims():
    d = pd.read_csv(io.StringIO(get("https://oui.doleta.gov/unemploy/csv/ar539.csv", 120).text), usecols=["st", "rptdate", "c3"])
    d["rptdate"] = pd.to_datetime(d["rptdate"], errors="coerce")
    s = d.dropna().groupby("rptdate")["c3"].sum()
    s = s[s.index >= "1971-01-01"]
    s = s[s > s.rolling(52, min_periods=10).median() * 0.3]   # unvollständige Wochen entfernen
    put("claims", s.rolling(4).mean() / 1000, "US-Erstanträge Arbeitslosenhilfe (4-W.-Ø, Tsd.)", "konjunktur", "Tsd.", "price", "US-Arbeitsministerium (unbereinigt)", "w", 1)


slow("claims", claims, ["claims"])


def aaii():
    r = get("https://www.aaii.com/files/surveys/sentiment.xls", 60)
    x = pd.read_excel(io.BytesIO(r.content), sheet_name=0, header=None, engine="xlrd")
    hdr = next(i for i in range(20) if any("bull" in str(v).lower() for v in x.iloc[i]) and any("bear" in str(v).lower() for v in x.iloc[i]))
    cols = [str(v).strip().lower() for v in x.iloc[hdr]]
    ib = next(i for i, c in enumerate(cols) if c.startswith("bull"))
    ir = next(i for i, c in enumerate(cols) if c.startswith("bear"))
    d = x.iloc[hdr + 1:]
    dt = pd.to_datetime(d.iloc[:, 0], errors="coerce")
    bull = pd.to_numeric(d.iloc[:, ib], errors="coerce")
    bear = pd.to_numeric(d.iloc[:, ir], errors="coerce")
    if bull.dropna().median() < 1.5:   # Anteile 0..1 -> Prozent
        bull, bear = bull * 100, bear * 100
    s = pd.Series((bull - bear).values, index=dt).dropna()
    s = s[s.index.notna()]
    put("aaii", s.rolling(4).mean(), "Anlegerstimmung AAII (Bullen − Bären, 4-W.-Ø)", "risiko", "Pp.", "rate", "AAII", "w", 1)


slow("aaii", aaii, ["aaii"])


def msci_eur():
    end = NOW.strftime("%Y%m%d")
    url = ("https://app2.msci.com/products/service/index/indexmaster/getLevelDataForGraph?currency_symbol=EUR"
           f"&index_variant=NETR&start_date=20001229&end_date={end}&data_frequency=DAILY&index_codes=990100")
    j = get(url, 90).json()
    lv = j["indexes"]["INDEX_LEVELS"]
    s = pd.Series([x["level_eod"] for x in lv], index=pd.to_datetime([str(x["calc_date"]) for x in lv], format="%Y%m%d"))
    put("msci_eur", s, "MSCI World in Euro (mit Dividenden)", "aktien", "Pkt", "price", "MSCI", dec=2)


slow("msci_eur", msci_eur, ["msci_eur"])


def gdp():
    j = get("https://api.db.nomics.world/v22/series/BEA/NIPA-T10105?q=gross%20domestic%20product&limit=20&observations=0&format=json", 60).json()
    docs = j["series"]["docs"]
    cand = [d for d in docs if d["series_code"].endswith("-Q") and "gross domestic product" in d.get("series_name", "").lower()]
    if not cand:
        raise RuntimeError("BIP-Reihe nicht gefunden: " + ", ".join(d["series_code"] for d in docs[:10]))
    code = sorted(cand, key=lambda d: len(d["series_code"]))[0]["series_code"]
    s = dbn("BEA/NIPA-T10105/" + code, "1970-01-01")
    if s.median() > 1e6:   # BEA liefert Mio. $
        s = s / 1000
    put("gdp", s, "US-BIP nominal (Jahresrate, Mrd. $)", "intern", "Mrd. $", "price", "BEA", "m", 0)
    note("gdp", True, code)


slow("gdp", gdp, ["gdp"])


def freddie():
    d = pd.read_csv(io.StringIO(get("https://www.freddiemac.com/pmms/docs/PMMS_history.csv", 60).text))
    s = pd.Series(pd.to_numeric(d["pmms30"], errors="coerce").values, index=pd.to_datetime(d["date"]))
    put("mort30", s, "US-Hypothekenzins 30J", "konjunktur", "%", "rate", "Freddie Mac", "w", 2)


slow("freddie", freddie, ["mort30"])


def eia():
    r = get("https://www.eia.gov/dnav/pet/hist_xls/EMD_EPD2D_PTE_NUS_DPGw.xls", 90)
    d = pd.read_excel(io.BytesIO(r.content), sheet_name="Data 1", skiprows=2)
    s = pd.Series(pd.to_numeric(d.iloc[:, 1], errors="coerce").values, index=pd.to_datetime(d.iloc[:, 0]))
    put("diesel", s, "US-Diesel (Tankstelle)", "rohstoffe", "$/gal", "price", "EIA", "w", 3)


slow("eia", eia, ["diesel"])


def h41():
    s = dbn("FED/H41/RESPPMA_N.WW", "2002-01-01")
    put("fedbs", s / 1e6, "Fed-Bilanzsumme", "konjunktur", "Bio. $", "price", "Fed H.4.1", "w", 3)


slow("h41", h41, ["fedbs"])


# ------------------------------------------------------------------ Shiller (S&P 500 seit 1871)
shiller = None


def shiller_long():
    global shiller
    import update as upd
    sh = upd.load_shiller()
    sh = sh.copy()
    sh.index = pd.to_datetime(dict(year=sh.year, month=sh.month, day=1))
    shiller = sh
    # realer Gesamtertrag (Dividenden reinvestiert), in heutiger Kaufkraft
    p, dv, cpi = sh.price, sh["div"] / 12, sh.cpi
    tr = (p + dv) / p.shift(1)
    tr.iloc[0] = 1
    real = tr.cumprod() * cpi.iloc[-1] / cpi
    put("spx_real", real / real.iloc[-1] * 100, "S&P 500 real mit Dividenden seit 1871 (heute = 100)", "bewertung", "", "price", "R. Shiller", "m", 4)
    put("cape_long", sh.cape, "Shiller-KGV (CAPE) seit 1881", "bewertung", "", "level", "R. Shiller", "m", 2)
    put("spx_m", sh.price, "S&P 500 (Monats-Ø, Shiller)", "intern", "Pkt", "price", "R. Shiller", "m", 2)
    put("cpi_long", sh.cpi, "US-CPI-Index (Shiller)", "intern", "", "price", "R. Shiller", "m", 3)
    put("div_m", sh["div"], "S&P 500 Dividende (Jahresrate)", "intern", "", "price", "R. Shiller", "m", 3)


slow("shiller", shiller_long, ["spx_real", "cape_long", "spx_m", "cpi_long", "div_m"], hours=20)


# ------------------------------------------------------------------ abgeleitete Reihen
def align(a, b):
    x, y = ser(a), ser(b)
    if x is None or y is None:
        return None, None
    j = pd.concat([x, y], axis=1, join="inner").dropna()
    return j.iloc[:, 0], j.iloc[:, 1]


def derive(sid, a, b, op, name, group, unit, kind, dec=None, freq="d"):
    x, y = align(a, b)
    if x is None or len(x) < 10:
        note("abgeleitet " + sid, False, f"fehlt {a}/{b}")
        return
    put(sid, op(x, y), name, group, unit, kind, "berechnet", freq, dec=dec)


derive("curve10_2", "y10", "y2", lambda x, y: x - y, "Zinskurve 10J − 2J", "zinsen", "Pp.", "rate", 3)
derive("curve10_3m", "y10", "y3m", lambda x, y: x - y, "Zinskurve 10J − 3M", "zinsen", "Pp.", "rate", 3)
derive("breakeven", "y10", "real10", lambda x, y: x - y, "Inflationserwartung 10J", "zinsen", "%", "rate", 3)
derive("us_eu10", "y10", "eu10", lambda x, y: x - y, "Zinsabstand USA − Euro 10J", "zinsen", "Pp.", "rate", 3)
derive("cu_au", "copper", "gold", lambda x, y: x / y * 1000, "Kupfer/Gold-Verhältnis", "verhaeltnis", "×1000", "price", 4)
derive("hyg_ief", "hyg", "ief", lambda x, y: x / y, "Kreditappetit (HYG/IEF)", "verhaeltnis", "", "price", 4)
derive("breadth", "rsp", "spy", lambda x, y: x / y, "Marktbreite (RSP/SPY)", "verhaeltnis", "", "price", 4)
derive("small_large", "rut", "spx", lambda x, y: x / y, "Small/Large Caps (RUT/SPX)", "verhaeltnis", "", "price", 4)
derive("gold_spx", "gold", "spx", lambda x, y: x / y, "Gold/S&P 500", "verhaeltnis", "", "price", 4)
derive("btc_ndx", "btc", "ndx", lambda x, y: x / y, "Bitcoin/Nasdaq", "verhaeltnis", "", "price", 4)
derive("brent_wti", "brent", "wti", lambda x, y: x - y, "Brent − WTI", "rohstoffe", "$", "rate", 2)
derive("vix_move", "vix", "move", lambda x, y: x / y, "VIX/MOVE (Aktien- vs Anleihe-Angst)", "verhaeltnis", "", "level", 4)
derive("vix_term", "vix", "vix3m", lambda x, y: x / y, "VIX-Kurve (1M/3M)", "risiko", "", "level", 3)
derive("ndx_spx", "ndx", "spx", lambda x, y: x / y, "Tech-Dominanz (NDX/SPX)", "verhaeltnis", "", "price", 4)
derive("disc_stap", "xly", "xlp", lambda x, y: x / y, "Risikoappetit Konsum (XLY/XLP)", "verhaeltnis", "", "price", 4)
derive("world_us", "msci", "spx", lambda x, y: x / y, "MSCI World / S&P 500", "verhaeltnis", "", "price", 4)
derive("gold_eur", "gold", "eurusd", lambda x, y: x / y, "Gold in Euro", "rohstoffe", "€/oz", "price", 1)
derive("spx_eur", "spx", "eurusd", lambda x, y: x / y, "S&P 500 in Euro", "aktien", "Pkt", "price", 1)

# Buffett-Indikator: Wilshire 5000 (≈ Mrd. $ Marktwert) / BIP
try:
    w, g = ser("w5000"), ser("gdp")
    if w is not None and g is not None:
        gq = g.copy()
        gq.index = gq.index + pd.offsets.QuarterEnd(0)   # Quartal gilt ab Quartalsende
        gd = gq.reindex(w.index, method="ffill")
        put("buffett", (w / gd * 100).dropna(), "Buffett-Indikator (Marktwert/BIP, Näherung)", "bewertung", "%", "level", "Wilshire/BEA (berechnet)", dec=1)
except Exception as e:  # noqa
    note("buffett", False, e)

# CAPE täglich & Signal aus markt.json
markt = {}
try:
    m = json.load(open(os.path.join(ROOT, "data", "markt.json")))
    d = m["cape"]["daily"]
    put("cape", pd.Series(d["v"], index=pd.to_datetime(d["t"])), "Shiller-KGV (CAPE)", "bewertung", "", "level", "Shiller / Markt-App", dec=2)
    cw = m["cape"]["windows"]["20"]
    cur = m["signal"].get("current")
    markt = {
        "date": m["date"], "cape": m["cape"]["current"], "mean20": cw["mean"], "sd20": cw["sd"], "z20": cw["z"],
        "rating": cw["rating"], "pct20": cw["percentile"], "trz": m["cape"]["tr"]["z"],
        "vs200w": m["spx"].get("vs200w"), "sma200w": m["spx"].get("sma200w"),
        "score": cur.get("score") if isinstance(cur, dict) else cur, "state": m["signal"].get("state"),
    }
    note("markt.json", True, m["date"])
except Exception as e:  # noqa
    note("markt.json", False, f"{type(e).__name__}: {e}")

# Excess CAPE Yield: Gewinnrendite (1/CAPE) minus realer 10J-Zins (10J minus Inflation der letzten 10 J. p.a.)
try:
    cl, cpil = ser("cape_long"), ser("cpi_long")
    gs = pd.read_csv(os.path.join(ROOT, "research", "macro_monthly.csv"))
    gs.index = pd.to_datetime(gs.month + "-01")
    y10m = gs.gs10.dropna()
    y10l = ser("y10")
    if y10l is not None:
        mm = y10l.groupby(y10l.index.to_period("M")).mean()
        mm.index = mm.index.to_timestamp()
        y10m = pd.concat([y10m[y10m.index < mm.index.min()], mm])
    capem = cl.copy()
    cd = ser("cape")
    if cd is not None:
        cm = cd.groupby(cd.index.to_period("M")).last()
        cm.index = cm.index.to_timestamp()
        capem = pd.concat([capem[capem.index < cm.index.min()], cm])
    infl10 = ((cpil / cpil.shift(120)) ** (1 / 10) - 1) * 100
    idx = capem.index.union(y10m.index)
    infl10 = infl10.reindex(idx).ffill()
    ecy = (100 / capem.reindex(idx) - (y10m.reindex(idx) - infl10)).dropna()
    put("ecy", ecy[ecy.index >= "1953-01-01"], "Aktien-Risikoprämie (Excess CAPE Yield)", "bewertung", "%", "rate", "Shiller/berechnet", "m", 2)
except Exception as e:  # noqa
    note("ecy", False, f"{type(e).__name__}: {e}")


# ------------------------------------------------------------------ Stress-Zähler (Fortschreibung der Forschung)
def stress():
    mm = pd.read_csv(os.path.join(ROOT, "research", "macro_monthly.csv"))
    mm.index = pd.PeriodIndex(mm.month, freq="M")
    sm = pd.read_csv(os.path.join(ROOT, "research", "stress_monthly.csv"))
    sm.index = pd.PeriodIndex(sm.month, freq="M")

    def monthly(sid):
        s = ser(sid)
        if s is None:
            return None
        return s.groupby(s.index.to_period("M")).mean()

    live = {"fedfunds": monthly("effr"), "gs10": monthly("y10"), "wti": monthly("wti"), "mortgage30": monthly("mort30")}
    cur = pd.Period(NOW.strftime("%Y-%m"), "M")
    idx = pd.period_range(mm.index.min(), cur, freq="M")
    df = mm.reindex(idx)
    for col, s in live.items():
        if s is None:
            continue
        s = s[s.index >= pd.Period("2026-01", "M")]
        for p, v in s.items():
            if p in df.index and (pd.isna(df.at[p, col]) or p >= pd.Period("2026-08", "M")):
                df.at[p, col] = v
    for col in ["fedfunds", "gs10", "wti", "mortgage30"]:
        df[col] = df[col].ffill(limit=2)

    act = lambda f, n: f.astype(float).rolling(n, min_periods=1).max().astype(bool)
    w = df.wti
    oil = act((w / w.shift(12) - 1 >= 0.5) & (w >= w.shift(1).rolling(36, min_periods=12).max()), 12)
    fed = act((df.fedfunds - df.fedfunds.shift(3)) >= 0.2, 6)
    y10 = act(df.gs10 >= df.gs10.shift(1).rolling(120, min_periods=100).max(), 6)
    mort = (df.mortgage30 - df.mortgage30.shift(24)) >= 1.0
    mid = pd.Series([(p.year % 4 == 2) and p.month <= 10 for p in df.index], index=df.index)
    val = sm.bewertung.reindex(idx).astype(float)
    if markt.get("trz") is not None:
        val[cur] = float(markt["trz"] > 1)
    val = val.ffill().astype(bool)
    house = sm.haus_real.reindex(idx).astype(float).ffill().astype(bool)
    F = pd.DataFrame(dict(oel=oil, fed=fed, zins10=y10, bewertung=val, hypo=mort, haus_real=house, midterm=mid)).loc["1976-01":]
    F["n"] = F.sum(axis=1)
    spx = df.spx.copy()
    sx = ser("spx")
    if sx is not None:
        sm_ = sx.groupby(sx.index.to_period("M")).last()
        for p, v in sm_.items():
            if p in spx.index and p >= pd.Period("2026-09", "M"):
                spx[p] = v
    last = F.iloc[-1]
    return {
        "months": [str(p) for p in F.index],
        "n": F.n.astype(int).tolist(),
        "flags": {k: F[k].astype(int).tolist() for k in F.columns if k != "n"},
        "spx": [None if pd.isna(x) else round(float(x), 1) for x in spx.reindex(F.index).values],
        "now": {k: int(last[k]) for k in F.columns},
        "inputs": {
            "wti_yoy": None if pd.isna(w.iloc[-1]) or pd.isna(w.iloc[-13]) else round(float(w.iloc[-1] / w.iloc[-13] - 1) * 100, 1),
            "ff_3m": None if pd.isna(df.fedfunds.iloc[-1]) else round(float(df.fedfunds.iloc[-1] - df.fedfunds.iloc[-4]), 2),
            "gs10": None if pd.isna(df.gs10.iloc[-1]) else round(float(df.gs10.iloc[-1]), 2),
            "gs10_max10y": round(float(df.gs10.iloc[-121:-1].max()), 2),
            "mort_24m": None if pd.isna(df.mortgage30.iloc[-1]) else round(float(df.mortgage30.iloc[-1] - df.mortgage30.iloc[-25]), 2),
            "trz": markt.get("trz"),
        },
    }


try:
    stress_out = stress()
    note("stress", True, f"jetzt {stress_out['now']['n']} Signale")
except Exception as e:  # noqa
    stress_out = (prev.get("stress") or None)
    note("stress", False, f"{type(e).__name__}: {e}")

# ------------------------------------------------------------------ Einschätzungs-Modell
model_out = None
try:
    import model as mdl
    model_out = mdl.run(ser, markt, NOW)
    note("modell", True, " · ".join(f"{k}: {v['now']['score']}" for k, v in model_out["targets"].items()))
except Exception as e:  # noqa
    import traceback
    traceback.print_exc()
    model_out = prev.get("model")
    note("modell", False, f"{type(e).__name__}: {e}")


# ------------------------------------------------------------------ News (Ersatz, falls die App offline lädt)
FEEDS = [
    ("CNBC", "https://www.cnbc.com/id/20910258/device/rss/rss.html", "us"),
    ("MarketWatch", "https://feeds.content.dowjones.io/public/rss/mw_topstories", "us"),
    ("Yahoo Finance", "https://finance.yahoo.com/news/rssindex", "us"),
    ("FT Markets", "https://www.ft.com/markets?format=rss", "us"),
    ("Investing.com", "https://www.investing.com/rss/news_25.rss", "us"),
    ("Federal Reserve", "https://www.federalreserve.gov/feeds/press_all.xml", "fed"),
    ("Handelsblatt", "https://www.handelsblatt.com/contentexport/feed/finanzen", "de"),
    ("tagesschau", "https://www.tagesschau.de/wirtschaft/index~rss2.xml", "de"),
]


def parse_rss(txt, src, cat):
    out = []
    root = ET.fromstring(txt)
    for it in root.iter("item"):
        t = (it.findtext("title") or "").strip()
        link = (it.findtext("link") or "").strip()
        pd_ = it.findtext("pubDate") or it.findtext("{http://purl.org/dc/elements/1.1/}date") or ""
        try:
            ts = pd.Timestamp(pd_)
            ts = (ts.tz_convert("UTC") if ts.tzinfo else ts.tz_localize("UTC")).strftime("%Y-%m-%dT%H:%M:%SZ")
        except Exception:  # noqa
            ts = None
        if t:
            out.append({"t": t, "l": link, "d": ts, "s": src, "c": cat})
    return out


news = []
for src, url, cat in FEEDS:
    try:
        news += parse_rss(get(url, 25).content, src, cat)[:25]
    except Exception as e:  # noqa
        note("rss " + src, False, f"{type(e).__name__}: {e}")
news.sort(key=lambda x: x["d"] or "", reverse=True)
note("news", True, f"{len(news)} Meldungen")

# ------------------------------------------------------------------ schreiben
order = [s for s in series if series[s]["g"] != "intern"]
out = {
    "updated": NOW.strftime("%Y-%m-%dT%H:%M:%SZ"),
    "series": {k: series[k] for k in order},
    "live": {k: LIVE[k] for k in order if k in LIVE},
    "feeds": [{"s": s, "u": u, "c": c} for s, u, c in FEEDS],
    "markt": markt,
    "stress": stress_out,
    "model": model_out,
    "news": news[:120],
    "cache": cache_meta,
    "diag": diag,
}
# interne Reihen nur für den Cache mitschreiben (App ignoriert sie)
out["series"].update({k: series[k] for k in series if series[k]["g"] == "intern"})
os.makedirs("out", exist_ok=True)
with open(OUT, "w") as f:
    json.dump(out, f, ensure_ascii=False, separators=(",", ":"))
print(f"OK   fertig: {len(order)} Reihen, {os.path.getsize(OUT) / 1e6:.2f} MB")
