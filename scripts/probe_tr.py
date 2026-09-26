"""Einmaliger Check: TR-CAPE und reale Total-Return-Renditen aus Shillers ie_data.xls."""
import io, re, sys, json
import numpy as np, pandas as pd, requests
sys.path.insert(0, "scripts")
import update as u
page = requests.get("https://shillerdata.com/", headers=u.UA, timeout=60).text.replace("&amp;", "&")
urls = [("https:" + x if x.startswith("//") else x) for x in re.findall(r'(?:https?:)?//[^"\'\s<>()]+?ie_data\.xls(?:\?[^"\'\s<>()]*)?', page)] + [u.FALLBACK_XLS]
raw = None
for url in urls:
    r = requests.get(url, headers=u.UA, timeout=120)
    if r.ok and r.content[:4] == b"\xd0\xcf\x11\xe0":
        raw = r.content; break
df = pd.read_excel(io.BytesIO(raw), sheet_name="Data", header=None, engine="xlrd")
hdr = next(i for i in range(30) if str(df.iat[i, 0]).strip() == "Date")
heads = [str(x).strip().replace("\n", " ") for x in df.iloc[hdr]]
print("::notice::Spalten: " + " | ".join(f"{i}:{h}" for i, h in enumerate(heads) if h and h != "nan"))
def col(pat):
    for i, h in enumerate(heads):
        if re.search(pat, h, re.I): return i
    return None
ci = {"date": 0, "P": col(r"^P$"), "D": col(r"^D$"), "CPI": col(r"^CPI$"), "cape": col(r"^CAPE$"),
      "trcape": col(r"TR\s*CAPE"), "trp": col(r"Real\s*Total\s*Return\s*Price"), "rp": col(r"^Real\s*Price$")}
print("::notice::Indizes " + json.dumps(ci))
rows = []
for i in range(hdr + 1, len(df)):
    try:
        d = float(df.iat[i, 0])
    except Exception:
        continue
    y = int(d); m = int(round((d - y) * 100))
    if not 1 <= m <= 12: continue
    rec = {"t": pd.Timestamp(y, m, 1)}
    for k, j in ci.items():
        if k == "date" or j is None: continue
        try: rec[k] = float(df.iat[i, j])
        except Exception: rec[k] = np.nan
    rows.append(rec)
s = pd.DataFrame(rows).set_index("t")
s = s[s.index >= "1881-01-01"]
out = []
for k in ("cape", "trcape"):
    x = s[k].dropna()
    if x.empty: continue
    last = x.iloc[-1]
    m20, s20 = x.rolling(240).mean().iloc[-1], x.rolling(240).std().iloc[-1]
    out.append(f"{k}: aktuell {last:.2f} ({x.index[-1]:%Y-%m}) | Ø seit 1881 {x.mean():.2f} | Ø seit 1957 {x['1957':].mean():.2f} | "
               f"20J-Ø {m20:.2f} σ {s20:.2f} z {(last-m20)/s20:+.2f} | höher als {100*(x<last).mean():.0f}% aller Monate | "
               f"aktuell/Ø1881 {last/x.mean():.2f}x")
# reale Total-Return- vs. reale Kursrendite und Dividendenrendite
tr, rp = s["trp"].dropna(), s["rp"].dropna()
for a, b in (("1931", "2026"), ("1957", "2026"), ("1996", "2026")):
    t0, t1 = tr[a:].index[0], tr.index[-1]; yrs = (t1 - t0).days / 365.25
    out.append(f"{a}-{t1:%Y}: real Total Return {((tr[t1]/tr[t0])**(1/yrs)-1)*100:.2f}% p.a. | real nur Kurs {((rp[t1]/rp[t0])**(1/yrs)-1)*100:.2f}% p.a. | "
               f"Inflation {((s['CPI'][t1]/s['CPI'][t0])**(1/yrs)-1)*100:.2f}% p.a.")
dy = (s["D"] / s["P"] * 100).dropna()
out.append("Dividendenrendite: Ø 1931-1990 %.2f%% | Ø 1990-2010 %.2f%% | Ø 2010-heute %.2f%% | aktuell %.2f%%" % (dy["1931":"1990"].mean(), dy["1990":"2010"].mean(), dy["2010":].mean(), dy.iloc[-1]))
# 10-Jahres reale TR-Rendite nach CAPE- und TR-CAPE-Dezil (Vorhersagekraft)
for k in ("cape", "trcape"):
    x = s[k]; f10 = (tr.shift(-120) / tr) ** 0.1 - 1
    d = pd.DataFrame({"v": x, "f": f10}).dropna()
    corr = d.corr(method="spearman").iloc[0, 1]
    out.append(f"{k}: Rangkorrelation mit realer 10J-Total-Return {corr:+.2f} (n={len(d)})")
for l in out: print("::notice::" + l)
