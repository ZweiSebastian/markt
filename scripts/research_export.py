"""Einmal-Export: zusätzliche Reihen für die Forschung (nicht für die App).
Jede Quelle einzeln, kurze Timeouts; was fehlschlägt, wird nur gemeldet. Ausgabe: research/ext_*.csv"""
import io, os, traceback
import pandas as pd, requests

os.makedirs("research", exist_ok=True)
UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"}


def note(s):
    print("::notice::" + s, flush=True)


def get(url, t=30):
    r = requests.get(url, headers=UA, timeout=t)
    r.raise_for_status()
    return r


def save(name, obj):
    obj.to_csv(f"research/ext_{name}.csv")
    note(f"{name}: {len(obj)} Zeilen, {obj.index.min()} bis {obj.index.max()}")


def job(name, fn):
    try:
        fn()
    except Exception as e:
        note(f"{name} FEHLER: {type(e).__name__}: {str(e)[:200]}")


# ---------------------------------------------------------------- Yahoo (yfinance)
def yahoo():
    import yfinance as yf
    out = {}
    for sym in ["SPY", "RSP", "^SPXEW", "^SP500EW", "NG=F", "HO=F", "RB=F", "CL=F", "BZ=F", "XHB", "ITB", "^TNX"]:
        try:
            h = yf.Ticker(sym).history(period="max", interval="1mo", auto_adjust=True)
            if len(h):
                out[sym] = h["Close"].tz_localize(None) if h.index.tz is not None else h["Close"]
                note(f"{sym}: {h.index.min():%Y-%m} bis {h.index.max():%Y-%m}")
        except Exception as e:
            note(f"{sym} FEHLER {e}")
    df = pd.DataFrame(out)
    df.index = pd.to_datetime(df.index).to_period("M")
    df = df.groupby(level=0).last()
    save("yahoo_monthly", df)


# ---------------------------------------------------------------- FRED (kurz versuchen)
FRED = {
    "MORTGAGE30US": "30J-Hypothekenzins (Freddie Mac, wöchentlich)",
    "MSACSR": "Monatsangebot neue Häuser",
    "HOSINVUSM495N": "Bestand bestehender Häuser",
    "HOSSUPUSM673N": "Monatsangebot bestehende Häuser (NAR)",
    "GASDESW": "Diesel Einzelhandel wöchentlich",
    "DHHNGSP": "Henry Hub Erdgas täglich",
    "B235RC1Q027SBEA": "Zolleinnahmen (Quartal, annualisiert)",
    "IEAMGSN": "Warenimporte (Quartal)",
    "CSUSHPINSA": "Case-Shiller national",
    "PERMIT": "Baugenehmigungen",
}


def fred():
    out = {}
    for sid in FRED:
        try:
            r = get(f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={sid}", 25)
            d = pd.read_csv(io.StringIO(r.text))
            d.columns = ["date", sid]
            s = pd.to_numeric(d[sid], errors="coerce")
            s.index = pd.to_datetime(d["date"]).dt.to_period("M")
            out[sid] = s.groupby(level=0).mean()
            note(f"FRED {sid} ok")
        except Exception as e:
            note(f"FRED {sid} FEHLER {type(e).__name__}")
    if out:
        save("fred_monthly", pd.DataFrame(out))


# ---------------------------------------------------------------- Freddie Mac direkt
def freddie():
    for url in ["https://www.freddiemac.com/pmms/docs/PMMS_history.csv",
                "https://www.freddiemac.com/pmms/docs/historicalweeklydata.xlsx"]:
        try:
            r = get(url, 30)
            if url.endswith(".csv"):
                d = pd.read_csv(io.StringIO(r.text))
            else:
                d = pd.read_excel(io.BytesIO(r.content), skiprows=4)
            d.to_csv("research/ext_freddie_raw.csv", index=False)
            note(f"Freddie ok {url} {d.shape} Spalten {list(d.columns)[:5]}")
            return
        except Exception as e:
            note(f"Freddie FEHLER {url} {type(e).__name__}")


# ---------------------------------------------------------------- Shiller Hauspreise seit 1890
def shiller_home():
    for url in ["http://www.econ.yale.edu/~shiller/data/Fig3-1.xls",
                "https://img1.wsimg.com/blobby/go/e5e77e0b-59d1-44d9-ab25-4763ac982e53/downloads/Fig3-1.xls"]:
        try:
            r = get(url, 40)
            x = pd.read_excel(io.BytesIO(r.content), sheet_name=None, header=None)
            for k, v in x.items():
                v.to_csv(f"research/ext_shiller_home_{k.replace(' ', '_')}.csv", index=False)
            note(f"Shiller Home ok {url} Blätter {list(x)}")
            return
        except Exception as e:
            note(f"Shiller Home FEHLER {url} {type(e).__name__}")


# ---------------------------------------------------------------- EIA Diesel / Erdgas (xls-Historie)
def eia():
    for name, url in [("diesel_weekly", "https://www.eia.gov/dnav/pet/hist_xls/EMD_EPD2D_PTE_NUS_DPGw.xls"),
                      ("henryhub_monthly", "https://www.eia.gov/dnav/ng/hist_xls/RNGWHHDm.xls"),
                      ("resid_gas_monthly", "https://www.eia.gov/dnav/ng/hist_xls/N3010US3m.xls"),
                      ("gas_storage_weekly", "https://www.eia.gov/dnav/ng/hist_xls/NW2_EPG0_SWO_R48_BCFw.xls")]:
        try:
            r = get(url, 40)
            d = pd.read_excel(io.BytesIO(r.content), sheet_name="Data 1", skiprows=2)
            d.to_csv(f"research/ext_eia_{name}.csv", index=False)
            note(f"EIA {name} ok {d.shape}")
        except Exception as e:
            note(f"EIA {name} FEHLER {type(e).__name__}")


for n, f in [("yahoo", yahoo), ("freddie", freddie), ("shiller_home", shiller_home), ("eia", eia), ("fred", fred)]:
    job(n, f)
note("fertig")
