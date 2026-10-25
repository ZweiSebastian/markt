"""S&P 500 rund um US-Midterms seit 1930. Hauswechsel laut Geschichte des US-Repräsentantenhauses."""
import pandas as pd, numpy as np, os
H = os.path.dirname(os.path.abspath(__file__))
c = pd.read_csv(os.path.join(H, "weekly.csv"), parse_dates=["t"]).set_index("t").c
flip = {1930: "→D", 1946: "→R", 1954: "→D", 1994: "→R", 2006: "→D", 2010: "→R", 2018: "→D", 2022: "→R"}
def eday(y):
    d = pd.Timestamp(y, 11, 1)
    while d.weekday() != 0: d += pd.Timedelta(days=1)
    return d + pd.Timedelta(days=1)
def px(t): return c[c.index <= t].iloc[-1]
rows = []
for y in range(1928, 2021, 4):
    y += 2
    e = eday(y); j = pd.Timestamp(y, 1, 1)
    seg = c[(c.index >= j) & (c.index <= e)]
    dd = (seg / seg.cummax() - 1).min()
    rows.append(dict(jahr=y, haus=flip.get(y, "–"), bis_wahl=px(e)/px(j)-1, maxdd_jahr=dd,
                     nach6m=px(e+pd.Timedelta(days=182))/px(e)-1, nach12m=px(e+pd.Timedelta(days=365))/px(e)-1,
                     nach24m=px(e+pd.Timedelta(days=730))/px(e)-1 if e+pd.Timedelta(days=730) < c.index[-1] else np.nan))
df = pd.DataFrame(rows).set_index("jahr")
df.round(3).to_csv(os.path.join(H, "ext_midterms.csv"))
pd.options.display.float_format = lambda x: f"{x*100:+.0f}%"
print(df.to_string())
m = df[df.index >= 1946]
print("\nab 1946 Median: bis Wahl", f"{m.bis_wahl.median()*100:+.1f}%", "maxDD im Jahr", f"{m.maxdd_jahr.median()*100:.1f}%",
      "12M nach Wahl", f"{m.nach12m.median()*100:+.1f}%", "positiv", (m.nach12m > 0).sum(), "/", len(m))
f = df[df.haus != "–"]; print("Hauswechsel:", f.nach12m.round(3).to_dict())
d = df[df.haus == "→D"]; print("Wechsel zu D:", d[['maxdd_jahr','nach6m','nach12m','nach24m']].round(3).to_dict('index'))
# alle Jahre: 12M-Rendite ab Anfang Nov als Basis
base = [px(pd.Timestamp(y,11,5)+pd.Timedelta(days=365))/px(pd.Timestamp(y,11,5))-1 for y in range(1946, 2025)]
print("Basis alle Jahre ab 5.11. 12M: Median", f"{np.median(base)*100:+.1f}%", "positiv", sum(b>0 for b in base), "/", len(base))
