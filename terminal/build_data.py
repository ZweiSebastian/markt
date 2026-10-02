"""
Daten für das Markt Terminal (Mac).

Sammelt Markt- und Makroreihen, rechnet abgeleitete Reihen (Zinskurve, Realzins, Verhältnisse)
und den Stress-Zähler aus research/stress_analysis.py fort. Ausgabe: out/terminal.json
(wird vom Workflow auf den Branch terminal-data geschrieben).

Quellen
- Yahoo Finance (yfinance): Indizes, ETFs, Rohstoff-Futures, Währungen, Krypto, VIX
- Federal Reserve H.15 über DBnomics: US-Zinsen täglich (3M, 2J, 10J, 30J, Fed Funds)
- US-Finanzministerium: aktuelle Zinskurve + reale Renditen (füllt die letzten Tage)
- NY Fed: effektiver Fed-Funds-Satz
- EZB: Einlagenzins
- BLS: Inflation (CPI, Kern-CPI), Arbeitslosenquote, Beschäftigung
- Freddie Mac: 30J-Hypothekenzins
- EIA: Diesel
- data/markt.json (diese Repo): Shiller-CAPE, Einstiegssignal

Langsame Quellen werden aus dem letzten Lauf übernommen, wenn sie jünger als 12 Stunden sind.
Jede Quelle einzeln, Fehler landen in "diag" und brechen den Lauf nicht ab.
"""
import io
import json
import math
import os
import re
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd
import requests

UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/124 Safari/537.36"}
NOW = datetime.now(timezone.utc)
START = pd.Timestamp("2014-01-01")
OUT = "out/terminal.json"
PREV_URL = "https://raw.githubusercontent.com/ZweiSebastian/markt/terminal-data/terminal.json"
H = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(H)

diag = []          # (quelle, ok, text)
series = {}        # id -> dict


def note(src, ok, txt=""):
    diag.append({"src": src, "ok": bool(ok), "msg": str(txt)[:300]})
    print(("OK   " if ok else "FEHL ") + src + ("  " + str(txt)[:200] if txt else ""), flush=True)


def get(url, t=40, **kw):
    r = requests.get(url, headers=UA, timeout=t, **kw)
    r.raise_for_status()
    return r


# ------------------------------------------------------------------ Katalog
# kind: price (Rendite = log-Änderung), rate (Änderung in Prozentpunkten), level (log-Änderung, z.B. VIX)
YAHOO = [
    # id, ticker, name, gruppe, einheit, kind
    ("spx", "^GSPC", "S&P 500", "aktien", "Pkt", "price"),
    ("ndx", "^NDX", "Nasdaq 100", "aktien", "Pkt", "price"),
    ("rut", "^RUT", "Russell 2000", "aktien", "Pkt", "price"),
    ("world", "URTH", "MSCI World (ETF)", "aktien", "$", "price"),
    ("dax", "^GDAXI", "DAX", "aktien", "Pkt", "price"),
    ("sx5e", "^STOXX50E", "Euro Stoxx 50", "aktien", "Pkt", "price"),
    ("nikkei", "^N225", "Nikkei 225", "aktien", "Pkt", "price"),
    ("em", "EEM", "Schwellenländer (ETF)", "aktien", "$", "price"),
    ("spy", "SPY", "S&P 500 ETF", "aktien", "$", "price"),
    ("rsp", "RSP", "S&P 500 gleichgewichtet", "aktien", "$", "price"),
    ("vix", "^VIX", "VIX", "risiko", "Pkt", "level"),
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
    ("tnx_y", "^TNX", "10J (Yahoo)", "intern", "%", "rate"),
    ("irx_y", "^IRX", "3M (Yahoo)", "intern", "%", "rate"),
]
LIVE = {i: t for i, t, *_ in YAHOO}   # für Live-Kurse in der App


def put(sid, s, name, group, unit, kind, src, freq="d", dec=None):
    s = pd.to_numeric(s, errors="coerce").dropna()
    s = s[~s.index.duplicated(keep="last")].sort_index()
    if len(s) < 3:
        note(sid, False, "zu wenige Werte")
        return
    if dec is None:
        m = float(s.abs().median()) or 1.0
        dec = max(0, min(6, 4 - int(math.floor(math.log10(m)))))
    days = ((s.index - pd.Timestamp("1970-01-01")) // pd.Timedelta(days=1)).astype(int).tolist()
    # Tage als Abstände speichern (erster Wert absolut) – spart ~60 % Größe
    dt = [days[0]] + [b - a for a, b in zip(days, days[1:])]
    series[sid] = {"name": name, "g": group, "u": unit, "k": kind, "src": src, "f": freq,
                   "dt": dt, "v": [round(float(x), dec) for x in s.values]}


def ser(sid):
    d = series.get(sid)
    if not d:
        return None
    days = d["t"] if "t" in d else np.cumsum(d["dt"]).tolist()
    return pd.Series(d["v"], index=pd.Timestamp("1970-01-01") + pd.to_timedelta(days, unit="D"))


# ------------------------------------------------------------------ vorheriger Lauf (Cache)
prev = {}
try:
    prev = get(PREV_URL, 30).json()
    note("vorheriger Lauf", True, prev.get("updated"))
except Exception as e:  # noqa
    note("vorheriger Lauf", False, e)


def cached(key, hours=12):
    """Liefert gespeicherte Reihen einer langsamen Quelle, wenn jung genug."""
    c = (prev.get("cache") or {}).get(key)
    if not c:
        return None
    try:
        age = NOW - datetime.fromisoformat(c["at"].replace("Z", "+00:00"))
    except Exception:  # noqa
        return None
    if age > timedelta(hours=hours):
        return None
    return c


cache_meta = {}


def slow(key, fn, ids):
    """Führt eine langsame Quelle aus oder übernimmt sie aus dem Cache. ids: erzeugte Serien-IDs."""
    c = cached(key)
    if c and all(i in prev.get("series", {}) for i in ids):
        for i in ids:
            series[i] = prev["series"][i]
        cache_meta[key] = c
        note(key, True, "aus Cache " + c["at"])
        return
    try:
        fn()
        cache_meta[key] = {"at": NOW.strftime("%Y-%m-%dT%H:%M:%SZ")}
    except Exception as e:  # noqa
        note(key, False, f"{type(e).__name__}: {e}")
        # alte Werte behalten, besser als nichts
        for i in ids:
            if i in prev.get("series", {}):
                series[i] = prev["series"][i]
        if key in (prev.get("cache") or {}):
            cache_meta[key] = prev["cache"][key]


# ------------------------------------------------------------------ Yahoo
def yahoo():
    import yfinance as yf
    tick = [t for _, t, *_ in YAHOO]
    got = {}
    for chunk in [tick[i:i + 12] for i in range(0, len(tick), 12)]:
        try:
            df = yf.download(chunk, start=START.strftime("%Y-%m-%d"), interval="1d", auto_adjust=True,
                             progress=False, threads=False, group_by="ticker")
            for t in chunk:
                try:
                    c = df[t]["Close"] if isinstance(df.columns, pd.MultiIndex) else df["Close"]
                    c = c.dropna()
                    if len(c) > 20:
                        got[t] = c
                except Exception:  # noqa
                    pass
        except Exception as e:  # noqa
            note("yahoo-block", False, e)
        time.sleep(1.5)
    for t in [t for t in tick if t not in got]:   # Einzelversuch
        try:
            h = yf.Ticker(t).history(start=START.strftime("%Y-%m-%d"), interval="1d", auto_adjust=True)
            if len(h) > 20:
                got[t] = h["Close"]
        except Exception as e:  # noqa
            note("yahoo " + t, False, e)
        time.sleep(1)
    for sid, t, name, g, u, k in YAHOO:
        if t in got:
            s = got[t]
            s.index = pd.to_datetime(s.index)
            if s.index.tz is not None:
                s.index = s.index.tz_localize(None)
            s.index = s.index.normalize()
            put(sid, s, name, g, u, k, "Yahoo Finance")
        else:
            note("yahoo " + t, False, "keine Daten")
            if sid in prev.get("series", {}):
                series[sid] = prev["series"][sid]
    note("yahoo", True, f"{len(got)}/{len(tick)} Ticker")


try:
    yahoo()
except Exception as e:  # noqa
    note("yahoo", False, e)
    for sid, *_ in YAHOO:
        if sid in prev.get("series", {}):
            series[sid] = prev["series"][sid]


# ------------------------------------------------------------------ Zinsen USA
def dbn(code, start="2014-01-01"):
    url = f"https://api.db.nomics.world/v22/series/{code}?observations=1&format=json"
    j = get(url, 60).json()
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
    # Treasury: laufendes + Vorjahr (DBnomics hinkt ein paar Tage hinterher)
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
        if len(s) < 50:   # Notfall: Yahoo
            ys = ser("tnx_y" if sid == "y10" else "irx_y" if sid == "y3m" else "")
            if ys is not None:
                s = ys
        put(sid, s, name, "zinsen", "%", "rate", "Fed H.15 / US Treasury", dec=3)
    # Realzins 10J (TIPS)
    rr = []
    for y in range(max(2014, NOW.year - 12), NOW.year + 1):
        try:
            rr.append(treasury_year(y, "daily_treasury_real_yield_curve")["10 YR"])
        except Exception as e:  # noqa
            note(f"treasury real {y}", False, e)
        time.sleep(0.3)
    if rr:
        put("real10", pd.concat(rr), "US-Realzins 10J (TIPS)", "zinsen", "%", "rate", "US Treasury", dec=3)
    note("zinsen", True, ", ".join(f"{k}:{len(v)}" for k, v in hist.items()))


slow("zinsen", rates, ["y3m", "y2", "y10", "y30", "real10"])
# Treasury hat Tageswerte; im Cache-Fall die letzten Tage frisch nachziehen
if cache_meta.get("zinsen", {}).get("at") != NOW.strftime("%Y-%m-%dT%H:%M:%SZ"):
    try:
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
    j = get(f"https://markets.newyorkfed.org/api/rates/unsecured/effr/search.json?startDate=2014-01-01&endDate={end}", 60).json()
    rows = j["refRates"]
    s = pd.Series([r["percentRate"] for r in rows], index=pd.to_datetime([r["effectiveDate"] for r in rows]))
    put("effr", s, "Fed Funds (effektiv)", "zinsen", "%", "rate", "NY Fed", dec=2)


slow("fedfunds", fedfunds, ["effr"])


def ecb():
    url = ("https://data-api.ecb.europa.eu/service/data/FM/D.U2.EUR.4F.KR.DFR.LEV"
           "?startPeriod=2014-01-01&format=csvdata")
    d = pd.read_csv(io.StringIO(get(url, 60).text))
    s = pd.Series(d["OBS_VALUE"].values, index=pd.to_datetime(d["TIME_PERIOD"]))
    put("ecb", s, "EZB-Einlagenzins", "zinsen", "%", "rate", "EZB", dec=2)
    # Bund 10J (Rendite, EZB-Zinsstrukturkurve AAA? -> Bundesbank wäre genauer; EZB AAA-Kurve 10J)
    url = ("https://data-api.ecb.europa.eu/service/data/YC/B.U2.EUR.4F.G_N_A.SV_C_YM.SR_10Y"
           "?startPeriod=2014-01-01&format=csvdata")
    d = pd.read_csv(io.StringIO(get(url, 60).text))
    s = pd.Series(d["OBS_VALUE"].values, index=pd.to_datetime(d["TIME_PERIOD"]))
    put("eu10", s, "Euro-Zins 10J (AAA-Kurve)", "zinsen", "%", "rate", "EZB", dec=3)


slow("ezb", ecb, ["ecb", "eu10"])


# ------------------------------------------------------------------ Konjunktur (BLS)
BLS = {
    "CUUR0000SA0": "cpi_idx", "CUUR0000SA0L1E": "core_idx", "LNS14000000": "unemp", "CES0000000001": "payrolls",
}


def bls():
    body = {"seriesid": list(BLS), "startyear": str(NOW.year - 9), "endyear": str(NOW.year)}
    j = requests.post("https://api.bls.gov/publicAPI/v1/timeseries/data/", json=body, headers=UA, timeout=60).json()
    if j.get("status") != "REQUEST_SUCCEEDED":
        raise RuntimeError(j.get("message"))
    out = {}
    for s in j["Results"]["series"]:
        rows = [(pd.Timestamp(int(r["year"]), int(r["period"][1:]), 1), float(r["value"]))
                for r in s["data"] if r["period"].startswith("M") and r["period"] != "M13"
                and re.fullmatch(r"-?[0-9.]+", str(r["value"]).strip())]
        out[BLS[s["seriesID"]]] = pd.Series(dict(rows)).sort_index()
    cpi, core = out["cpi_idx"], out["core_idx"]
    put("cpi", (cpi / cpi.shift(12) - 1) * 100, "US-Inflation (CPI, ggü. Vorjahr)", "konjunktur", "%", "rate", "BLS", "m", 2)
    put("core", (core / core.shift(12) - 1) * 100, "US-Kerninflation (ggü. Vorjahr)", "konjunktur", "%", "rate", "BLS", "m", 2)
    put("unemp", out["unemp"], "US-Arbeitslosenquote", "konjunktur", "%", "rate", "BLS", "m", 1)
    put("payrolls", out["payrolls"].diff(), "US-Stellen (Veränderung, Tsd.)", "konjunktur", "Tsd.", "rate", "BLS", "m", 0)
    # Sahm-Regel: 3M-Ø Arbeitslosenquote minus Tief der vorherigen 12 Monate (der 3M-Ø)
    u3 = out["unemp"].rolling(3).mean()
    put("sahm", u3 - u3.shift(1).rolling(12).min(), "Sahm-Regel", "konjunktur", "Pp.", "rate", "BLS (berechnet)", "m", 2)


slow("bls", bls, ["cpi", "core", "unemp", "payrolls", "sahm"])


# ------------------------------------------------------------------ Hypothekenzins, Diesel
def freddie():
    d = pd.read_csv(io.StringIO(get("https://www.freddiemac.com/pmms/docs/PMMS_history.csv", 60).text))
    s = pd.Series(pd.to_numeric(d["pmms30"], errors="coerce").values, index=pd.to_datetime(d["date"]))
    put("mort30", s[s.index >= "2000-01-01"], "US-Hypothekenzins 30J", "konjunktur", "%", "rate", "Freddie Mac", "w", 2)


slow("freddie", freddie, ["mort30"])


def eia():
    r = get("https://www.eia.gov/dnav/pet/hist_xls/EMD_EPD2D_PTE_NUS_DPGw.xls", 90)
    d = pd.read_excel(io.BytesIO(r.content), sheet_name="Data 1", skiprows=2)
    s = pd.Series(pd.to_numeric(d.iloc[:, 1], errors="coerce").values, index=pd.to_datetime(d.iloc[:, 0]))
    put("diesel", s[s.index >= "2000-01-01"], "US-Diesel (Tankstelle)", "rohstoffe", "$/gal", "price", "EIA", "w", 3)


slow("eia", eia, ["diesel"])


# ------------------------------------------------------------------ Fed-Bilanz (H.4.1)
def h41():
    # Erst bekannter Code, sonst Suche im Datensatz
    for code in ["FED/H41/RESPPMA_N.WW", "FED/H41/RESPPMAXCH52NWW_N.WW"]:
        try:
            s = dbn(code, "2014-01-01")
            if len(s) > 100:
                put("fedbs", s / 1e6, "Fed-Bilanzsumme", "konjunktur", "Bio. $", "price", "Fed H.4.1", "w", 3)
                return
        except Exception as e:  # noqa
            note("h41 " + code, False, e)
    j = get("https://api.db.nomics.world/v22/series/FED/H41?q=total%20assets&limit=15&observations=0&format=json", 60).json()
    found = [(d["series_code"], d.get("series_name", "")[:90]) for d in j["series"]["docs"]]
    note("h41 suche", False, json.dumps(found, ensure_ascii=False)[:1500])
    raise RuntimeError("Fed-Bilanz nicht gefunden")


slow("h41", h41, ["fedbs"])


# ------------------------------------------------------------------ abgeleitete Reihen
def align(a, b):
    x, y = ser(a), ser(b)
    if x is None or y is None:
        return None, None
    j = pd.concat([x, y], axis=1, join="inner").dropna()
    return j.iloc[:, 0], j.iloc[:, 1]


def derive(sid, a, b, op, name, group, unit, kind, dec=None):
    x, y = align(a, b)
    if x is None or len(x) < 10:
        note("abgeleitet " + sid, False, f"fehlt {a}/{b}")
        return
    put(sid, op(x, y), name, group, unit, kind, "berechnet", dec=dec)


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
derive("ndx_spx", "ndx", "spx", lambda x, y: x / y, "Tech-Dominanz (NDX/SPX)", "verhaeltnis", "", "price", 4)
derive("disc_stap", "xly", "xlp", lambda x, y: x / y, "Risikoappetit Konsum (XLY/XLP)", "verhaeltnis", "", "price", 4)

# ------------------------------------------------------------------ CAPE & Signal aus markt.json
markt = {}
try:
    m = json.load(open(os.path.join(ROOT, "data", "markt.json")))
    d = m["cape"]["daily"]
    s = pd.Series(d["v"] if "v" in d else d.get("cape"), index=pd.to_datetime(d["t"]))
    put("cape", s, "Shiller-KGV (CAPE)", "bewertung", "", "level", "Shiller / Markt-App", dec=2)
    cw = m["cape"]["windows"]["20"]
    markt = {
        "date": m["date"], "cape": m["cape"]["current"], "mean20": cw["mean"], "sd20": cw["sd"], "z20": cw["z"],
        "rating": cw["rating"], "pct20": cw["percentile"], "trz": m["cape"]["tr"]["z"],
        "vs200w": m["spx"].get("vs200w"), "sma200w": m["spx"].get("sma200w"),
        "score": (m["signal"].get("current") or {}).get("score") if isinstance(m["signal"].get("current"), dict) else m["signal"].get("current"),
        "state": m["signal"].get("state"),
    }
    note("markt.json", True, m["date"])
except Exception as e:  # noqa
    note("markt.json", False, f"{type(e).__name__}: {e}")


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
        s = s[s.index >= pd.Period("2026-01", "M")]   # Forschung bis 2026-08 vollständig, danach live
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
    root = ET.fromstring(txt.encode("utf-8") if isinstance(txt, str) else txt)
    for it in root.iter("item"):
        t = (it.findtext("title") or "").strip()
        link = (it.findtext("link") or "").strip()
        pd_ = it.findtext("pubDate") or it.findtext("{http://purl.org/dc/elements/1.1/}date") or ""
        try:
            ts = pd.Timestamp(pd_).tz_convert("UTC") if pd.Timestamp(pd_).tzinfo else pd.Timestamp(pd_).tz_localize("UTC")
            ts = ts.strftime("%Y-%m-%dT%H:%M:%SZ")
        except Exception:  # noqa
            ts = None
        if t:
            out.append({"t": t, "l": link, "d": ts, "s": src, "c": cat})
    return out


news = []
for src, url, cat in FEEDS:
    try:
        r = get(url, 25)
        news += parse_rss(r.content, src, cat)[:25]
    except Exception as e:  # noqa
        note("rss " + src, False, f"{type(e).__name__}: {e}")
news.sort(key=lambda x: x["d"] or "", reverse=True)
note("news", True, f"{len(news)} Meldungen")

# ------------------------------------------------------------------ schreiben
order = [s for s in series if not s.endswith("_y")]
out = {
    "updated": NOW.strftime("%Y-%m-%dT%H:%M:%SZ"),
    "series": {k: series[k] for k in order},
    "live": {k: LIVE[k] for k in order if k in LIVE},
    "feeds": [{"s": s, "u": u, "c": c} for s, u, c in FEEDS],
    "markt": markt,
    "stress": stress_out,
    "news": news[:120],
    "cache": cache_meta,
    "diag": diag,
}
os.makedirs("out", exist_ok=True)
with open(OUT, "w") as f:
    json.dump(out, f, ensure_ascii=False, separators=(",", ":"))
print(f"OK   fertig: {len(order)} Reihen, {os.path.getsize(OUT) / 1e6:.2f} MB")
