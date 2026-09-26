"""Zweiter Teil: Zölle, Marktbreite, Midterms, Diesel/Gas, Hypothekenzins, Hauspreise – und ein Stress-Zähler.
Liest macro_monthly.csv + weekly.csv. Ausgabe: stress_report.txt (per Umleitung) und stress_monthly.csv."""
import pandas as pd, numpy as np, os

H = os.path.dirname(os.path.abspath(__file__))
df = pd.read_csv(os.path.join(H, "macro_monthly.csv"))
df.index = pd.PeriodIndex(df.month, freq="M")
now = pd.Period("2026-09", "M")
# Stand 25.09.2026 (Web): Fed 3,75-4,00 %, 10J 5,17 %, WTI 92,41, Freddie 7,03 %, Diesel 6,53 $
df.loc[now, ["fedfunds", "gs10", "wti", "mortgage30", "diesel", "cape"]] = [3.88, 5.17, 92.41, 7.03, 6.529, 40.6]
wk = pd.read_csv(os.path.join(H, "weekly.csv"), parse_dates=["t"]).set_index("t")
c = wk.c
cpi = df.cpi.ffill()
pct = lambda s, x: round(float((s.dropna() < x).mean() * 100))

print("=" * 70, "\n1) ZÖLLE (USITC, Zölle in % aller Importe)")
t = pd.read_csv(os.path.join(H, "raw", "usitc_tariff_ratio.csv")).set_index("year").duties_pct_total_imports
print("  2024:", t[2024], " 2025:", t[2025], " 2026 laut Yale (statutarisch): 11,0")
print("  zuletzt ≥ 7,8 %:", t[t >= 7.8].index.max(), "| zuletzt ≥ 11 %:", t[t >= 11].index.max())
for a, b, name in [(1920, 1922, "Fordney-McCumber 1921/22"), (1929, 1932, "Smoot-Hawley 1930")]:
    p0 = c[c.index <= f"{a}-12-31"].iloc[-1] if a >= 1928 else np.nan
    print(f"  {name}: Zollsatz {t[a]} → {t[b]}")
s = c
print("  S&P ab Juni 1930 (Smoot-Hawley unterzeichnet) 2 J.:", f"{s[s.index<='1932-06-17'].iloc[-1]/s[s.index<='1930-06-17'].iloc[-1]*100-100:+.0f} %")
print("  S&P 02.04.2025 (Liberation Day) → jetzt:", f"{s.iloc[-1]/s[s.index<='2025-04-02'].iloc[-1]*100-100:+.0f} %")

print("=" * 70, "\n2) MARKTBREITE (gleichgewichtet vs. kapitalgewichtet)")
r = (df.spx_ew / df.spx).dropna()
rel = (df.rsp / df.spy).dropna()
for n in (12, 36, 60):
    print(f"  RSP vs SPY {n} M.: {(rel.iloc[-1]/rel.iloc[-1-n]-1)*100:+.1f} %")
print("  Verhältnis RSP/SPY jetzt vs. Hoch:", f"{(rel.iloc[-1]/rel.max()-1)*100:.0f} %", "Hoch am", rel.idxmax())
r36 = rel / rel.shift(36) - 1
print("  schlechteste 36M-Relative bisher:", f"{r36.min()*100:.1f} %", r36.idxmin(), "| jetzt", f"{r36.iloc[-1]*100:.1f} %", "Perzentil", pct(r36, r36.iloc[-1]))
print("  FactSet Q2/2026: Gewinnwachstum S&P +50 % (ohne GOOGL/AMZN +32 %), 10 von 11 Sektoren wachsen, Forward-KGV 20,0")

print("=" * 70, "\n3) MIDTERMS")
m = pd.read_csv(os.path.join(H, "ext_midterms.csv"), index_col=0)
mm = m[m.index >= 1946]
print("  12 M nach Midterm-Wahl positiv:", (mm.nach12m > 0).sum(), "von", len(mm), "| Median", f"{mm.nach12m.median()*100:+.0f} %")
print("  Hauswechsel zu D:", m[m.haus == "→D"].nach12m.round(2).to_dict(), " zu R:", m[m.haus == "→R"].nach12m.round(2).to_dict())
print("  Median-Tief im Midterm-Jahr bis zur Wahl:", f"{mm.maxdd_jahr.median()*100:.0f} %")
seg = c[(c.index >= "2026-01-01")]
print("  2026 bisher: ", f"{seg.iloc[-1]/seg.iloc[0]*100-100:+.0f} %, tiefster Rückgang {(seg/seg.cummax()-1).min()*100:.0f} %")

print("=" * 70, "\n4) DIESEL / ERDGAS")
dz = df.diesel; dzr = dz * cpi.iloc[-1] / cpi
print(f"  Diesel jetzt {dz[now]:.2f} $/gal, real: Perzentil {pct(dzr, dzr[now])}, Rekord real {dzr.max():.2f} ({dzr.idxmax()})")
print(f"  Diesel ggü. Vorjahr {(dz[now]/dz[now-12]-1)*100:+.0f} %")
gs = pd.read_csv(os.path.join(H, "ext_eia_gas_storage_weekly.csv"), parse_dates=["Date"]).set_index("Date").iloc[:, 0]
last = gs.index[-1]; wkno = last.isocalendar().week
same = gs[(gs.index.isocalendar().week == wkno) & (gs.index.year >= last.year - 5) & (gs.index.year < last.year)]
print(f"  US-Gasspeicher {last.date()}: {gs.iloc[-1]:.0f} Bcf vs. 5J-Schnitt {same.mean():.0f} ({(gs.iloc[-1]/same.mean()-1)*100:+.1f} %)")
hh = df.henryhub.dropna(); print(f"  Henry Hub {hh.index[-1]}: {hh.iloc[-1]:.2f} $, Perzentil seit 1997 {pct(hh, hh.iloc[-1])}")
# Dieselspitzen und S&P
dy = dz / dz.shift(12) - 1
print("  Diesel ≥ +40 % ggü. Vorjahr, erste Monate:", [str(p) for p in dy[dy >= 0.4].index if dy.get(p - 1, 0) < 0.4])

print("=" * 70, "\n5) HYPOTHEKEN & HÄUSER")
mo = df.mortgage30
print(f"  30J-Hypothek {mo[now]:.2f} %: zuletzt höher {mo[mo > mo[now]].index.max()}, Perzentil seit 1971 {pct(mo, mo[now])}")
cs = df.caseshiller.dropna(); csy = cs / cs.shift(12) - 1; cpy = (cpi / cpi.shift(12) - 1).reindex(cs.index)
real = csy - cpy
print(f"  Case-Shiller national {cs.index[-1]}: nominal {csy.iloc[-1]*100:+.1f} %, real ca. {real.iloc[-1]*100:+.1f} % ggü. Vorjahr")
print("  NAR Aug 2026: Median +1,6 % ggü. Vorjahr, 4,9 Monate Angebot (höchstes seit >10 J.), 42 % mit Preissenkung")
negr = real[real < 0]
starts = [p for p in negr.index if real.get(p - 1, 1) >= 0]
print("  Beginn realer Hauspreisrückgänge:", [str(p) for p in starts])

# ------------------------------------------------------------------ Stress-Zähler
print("=" * 70, "\n6) STRESS-ZÄHLER: macht MEHR Warnsignale die Zukunft schlechter?")
act = lambda f, n: f.astype(float).rolling(n, min_periods=1).max().astype(bool)
w = df.wti
oil = act((w / w.shift(12) - 1 >= 0.5) & (w >= w.shift(1).rolling(36, min_periods=12).max()), 12)
fed = act((df.fedfunds - df.fedfunds.shift(3)) >= 0.2, 6)
y10 = act(df.gs10 >= df.gs10.shift(1).rolling(120, min_periods=100).max(), 6)
trz = (df.trcape - df.trcape.rolling(240, 120).mean()) / df.trcape.rolling(240, 120).std(); trz[now] = trz.dropna().iloc[-1]
val = trz > 1
mort = (mo - mo.shift(24)) >= 1.0
house = (real.reindex(df.index).ffill(limit=8) < 0)
mid = pd.Series([(p.year % 4 == 2) and p.month <= 10 for p in df.index], index=df.index)
F = pd.DataFrame(dict(oel=oil, fed=fed, zins10=y10, bewertung=val, hypo=mort, haus_real=house, midterm=mid)).loc["1976-01":]
F["n"] = F.sum(axis=1)
print("  jetzt:", F.loc[now].to_dict())

def fwd(p):
    t0 = p.to_timestamp(how="end")
    s = c[c.index > t0 - pd.Timedelta(days=7)]
    if len(s) < 160: return (np.nan, np.nan, np.nan)
    e = s.iloc[0]; s3 = s[s.index <= s.index[0] + pd.Timedelta(days=3 * 365)]
    r1 = s[s.index <= s.index[0] + pd.Timedelta(days=365)].iloc[-1] / e - 1
    dd = (s3 / s3.cummax() - 1).min()
    lo = s3.min() / e - 1
    return (r1, dd, lo)
R = pd.DataFrame([fwd(p) for p in F.index], index=F.index, columns=["r1", "maxdd3", "tief3"])
X = F.join(R).dropna()
print(f"  {'Signale':>8} {'Monate':>7} {'1J Median':>10} {'maxDD 3J Median':>16} {'≥25%-Einbruch':>14} {'Tief<-20% vs Einstieg':>22}")
for k, g in X.groupby(np.minimum(X.n, 5)):
    print(f"  {('≥' if k==5 else '')+str(k):>8} {len(g):7d} {g.r1.median()*100:+9.1f}% {g.maxdd3.median()*100:15.1f}% {(g.maxdd3<=-0.25).mean()*100:13.0f}% {(g.tief3<=-0.2).mean()*100:21.0f}%")
print("  Rangkorrelation Anzahl vs. 1J-Rendite:", round(X.n.corr(X.r1, method="spearman"), 2), "| vs. maxDD:", round(X.n.corr(X.maxdd3, method="spearman"), 2))
print("  Einzelsignale (1J-Median wenn an / aus, ≥25%-Einbruch an / aus):")
for k in F.columns[:-1]:
    a, b = X[X[k]], X[~X[k]]
    print(f"   {k:10s} an {len(a):4d} M: {a.r1.median()*100:+5.1f}% / {b.r1.median()*100:+5.1f}%   {(a.maxdd3<=-0.25).mean()*100:3.0f}% / {(b.maxdd3<=-0.25).mean()*100:3.0f}%")
top = X[X.n >= 5]
print("  Monate mit ≥5 Signalen:", sorted({str(p.year) for p in top.index}))
F.astype(int).to_csv(os.path.join(H, "stress_monthly.csv"))
