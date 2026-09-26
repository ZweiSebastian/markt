"""Seltenheits-geordnete Kombinationsanalyse: Ölschock, Fed-Zinserhöhung, 10J-Rendite-Hoch, hohe Bewertung.
Liest macro_monthly.csv und weekly.csv, schreibt macro_episodes.csv und druckt die Auswertung."""
import pandas as pd, numpy as np, os, itertools

HERE = os.path.dirname(os.path.abspath(__file__))
df = pd.read_csv(os.path.join(HERE, "macro_monthly.csv"))
df.index = pd.PeriodIndex(df.month, freq="M")

# Aktueller Stand (25.09.2026): Fed hebt am 16.09. auf 3,75-4,00 % an (effektiv ~3,88), 10J 5,17 %, WTI 92,41 $
now = pd.Period("2026-09", "M")
df.loc[now, ["fedfunds", "gs10", "wti"]] = [3.88, 5.17, 92.41]
df.loc[now, "wti_real"] = 92.41

wk = pd.read_csv(os.path.join(HERE, "weekly.csv"), parse_dates=["t"]).set_index("t")
c = wk.c

# ------------------------------------------------------------------ Merkmale (monatlich)
d = pd.DataFrame(index=df.index)
d["oil12"] = df.wti / df.wti.shift(12) - 1
d["ff3"] = df.fedfunds - df.fedfunds.shift(3)
d["ff12"] = df.fedfunds - df.fedfunds.shift(12)
d["y_hi10"] = df.gs10 >= df.gs10.shift(1).rolling(120, min_periods=100).max()
d["y_hi15"] = df.gs10 >= df.gs10.shift(1).rolling(180, min_periods=150).max()
d["cape"] = df.cape
m = df.trcape.rolling(240, min_periods=120).mean(); s = df.trcape.rolling(240, min_periods=120).std()
d["trz"] = (df.trcape - m) / s
d.loc[now, "cape"] = 40.6
d.loc[now, "trz"] = d.trz.dropna().iloc[-1]

base = d[(d.index >= pd.Period("1955-07", "M"))]  # ab hier sind alle drei Reihen vorhanden

def active(flag, look):
    """Merkmal war in den letzten `look` Monaten (inkl. aktuellem) mindestens einmal wahr."""
    return flag.astype(float).rolling(look, min_periods=1).max().astype(bool)

C = pd.DataFrame(index=base.index)
C["Öl"] = active(base.oil12 >= 0.40, 12)          # Ölpreis +40 % ggü. Vorjahr, Phase 12 Monate
C["Fed"] = active(base.ff3 >= 0.20, 6)             # Fed hat in den letzten 6 Mon. erhöht
C["10J"] = active(base.y_hi10, 6)                  # 10J-Rendite auf 10-Jahres-Hoch (letzte 6 Mon.)
C["Bew"] = base.trz > 1.0                          # TR-CAPE > +1σ über 20J-Schnitt

print("Aktueller Stand:", C.loc[now].to_dict())
print("Rohwerte jetzt:", {k: round(float(v), 2) for k, v in base.loc[now].items()})
H = C[C.index < now]
print("\nHäufigkeit (Anteil der Monate 1955-07..2026-08):")
for k in C:
    print(f"  {k:4s} {H[k].mean()*100:5.1f} %")

# ------------------------------------------------------------------ S&P-Pfad ab Episodenstart
def path(p):
    t0 = p.to_timestamp(how="end").normalize()
    seg = c[(c.index > t0 - pd.Timedelta(days=7)) & (c.index <= t0 + pd.Timedelta(days=5 * 365))]
    if len(seg) < 5:
        return None
    e = seg.iloc[0]
    s3 = seg[seg.index <= seg.index[0] + pd.Timedelta(days=3 * 365)]
    run = s3.cummax(); dd = s3 / run - 1
    tr = dd.idxmin(); pk = s3[:tr].idxmax()
    rec = seg[(seg.index > tr) & (seg >= s3[pk])]
    r = lambda y: (seg[seg.index <= seg.index[0] + pd.Timedelta(days=int(y * 365))].iloc[-1] / e - 1) if seg.index[-1] >= seg.index[0] + pd.Timedelta(days=int(y * 365) - 10) else np.nan
    return dict(start=str(p), entry=round(e, 2),
                vorlauf=round(s3[pk] / e - 1, 3), gipfel=str(pk.date()), maxdd=round(dd.min(), 3),
                tief=str(tr.date()), monate_bis_tief=round((tr - seg.index[0]).days / 30.4, 1),
                tief_vs_einstieg=round(s3.min() / e - 1, 3),
                erholt=str(rec.index[0].date()) if len(rec) else "–",
                r6m=round(r(0.5), 3), r1=round(r(1), 3), r2=round(r(2), 3), r3=round(r(3), 3), r5=round(r(5), 3))

def episodes(mask, gap=12):
    out, last = [], None
    for p in mask[mask].index:
        if last is None or (p - last).n > gap:
            out.append(p)
        last = p
    return out

# Basisrate: jeder Monat
allp = [path(p) for p in H.index[::1]]
allp = pd.DataFrame([a for a in allp if a])
print(f"\nBasisrate (alle Monate): Anteil mit ≥20 % Drawdown in 3 J. = {(allp.maxdd <= -0.2).mean()*100:.0f} %,"
      f" Median maxDD {allp.maxdd.median()*100:.0f} %, Median 1J {allp.r1.median()*100:.1f} %")

# ------------------------------------------------------------------ Kaskade nach Seltenheit
order = sorted(C.columns, key=lambda k: H[k].mean())
print("\nReihenfolge nach Seltenheit:", order)
rows = []
for n in range(1, len(order) + 1):
    keys = order[:n]
    mask = C[keys].all(axis=1)
    eps = episodes(mask[mask.index < now])
    print(f"\n=== {' + '.join(keys)}: {mask[mask.index<now].mean()*100:.1f} % der Monate, {len(eps)} Episoden, jetzt={bool(mask.loc[now])}")
    for p in eps:
        a = path(p)
        if a is None:
            continue
        a["kombi"] = "+".join(keys)
        rows.append(a)
        print(f"  {a['start']}  Vorlauf {a['vorlauf']*100:+5.0f}%  bis {a['gipfel']}  maxDD {a['maxdd']*100:5.0f}%  Tief {a['tief']} "
              f"({a['monate_bis_tief']} M)  Tief vs Einstieg {a['tief_vs_einstieg']*100:+4.0f}%  erholt {a['erholt']}  "
              f"1J {a['r1']*100:+5.0f}%  3J {a['r3']*100:+5.0f}%  5J {a['r5']*100:+5.0f}%")

# Alle Paare/Tripel zur Übersicht
print("\nAlle Kombinationen (Monatsanteil / Episoden):")
for n in (2, 3):
    for keys in itertools.combinations(C.columns, n):
        mask = C[list(keys)].all(axis=1)
        mm = mask[mask.index < now]
        eps = episodes(mm)
        res = [path(p) for p in eps]; res = [r for r in res if r]
        dd = np.median([r["maxdd"] for r in res]) if res else np.nan
        hit = np.mean([r["maxdd"] <= -0.2 for r in res]) if res else np.nan
        print(f"  {'+'.join(keys):16s} {mm.mean()*100:5.1f} %  {len(eps):2d} Ep.  jetzt={bool(mask.loc[now])}  med maxDD {dd*100:5.0f}%  ≥20%-Crash {hit*100:4.0f}%")

pd.DataFrame(rows).to_csv(os.path.join(HERE, "macro_episodes.csv"), index=False)

# ------------------------------------------------------------------ Ölschocks (streng): WTI +50 % ggü. Vorjahr UND 3-Jahres-Hoch
w=df.wti; ff=df.fedfunds; y=df.gs10
shock=(w/w.shift(12)-1>=0.5)&(w>=w.shift(1).rolling(36,min_periods=12).max())
shock=shock[shock.index>=pd.Period('1947-01','M')]
eps=episodes(shock,24)
yhi10=y>=y.shift(1).rolling(120,min_periods=60).max()
yhi5=y>=y.shift(1).rolling(60,min_periods=60).max()
hike=(ff-ff.shift(3))>=0.2
trz=d.trz
rows=[]
for p in eps:
    win=[p+i for i in range(-6,13)]
    win=[q for q in win if q in df.index and q<=now]
    sm=[q for q in shock.index if q>=p and q<=p+30 and shock[q]]
    peak=max(win,key=lambda q:w.get(q,0))
    def first(flag):
        f=[q for q in win if q in flag.index and bool(flag.get(q,False))]
        return f"{(f[0]-p).n:+d}" if f else "–"
    both=[q for q in win if bool(hike.get(q,False)) and bool(yhi10.get(q,False))]
    rows.append(dict(start=str(p), wti0=w[p-12], wti_pk=w[peak], oil_max_yoy=round((w/w.shift(12)-1)[win].max()*100),
        ff_start=ff.get(p,np.nan), ff_vor12=round(ff.get(p,np.nan)-ff.get(p-12,np.nan),2) if p-12 in ff.index else np.nan,
        fed_hike=first(hike), y10=y.get(p,np.nan), y10hi10=first(yhi10), y10hi5=first(yhi5),
        cape=round(df.cape.get(p,np.nan),1), trz=round(trz.get(p,np.nan),2)))
t=pd.DataFrame(rows); pd.set_option('display.width',250); print(t.to_string(index=False))
print()
for off in (0,5):
    print("Einstieg = Schockbeginn +",off,"Monate")
    for p in eps[1:-1]:
        a=path(p+off)
        print(f"  {a['start']}  Vorlauf {a['vorlauf']*100:+4.0f}% bis {a['gipfel']}  maxDD {a['maxdd']*100:4.0f}%  Tief {a['tief']} ({a['monate_bis_tief']}M)  Tief vs Einstieg {a['tief_vs_einstieg']*100:+4.0f}%  erholt {a['erholt']}  6M {a['r6m']*100:+4.0f}% 1J {a['r1']*100:+4.0f}% 2J {a['r2']*100:+4.0f}% 3J {a['r3']*100:+4.0f}% 5J {a['r5']*100:+4.0f}%")
# real TR 5y/10y from start+5
tr=wk.tr_real
def rr(p,y):
    t0=(p).to_timestamp(how='end'); s=tr[tr.index>=t0-pd.Timedelta(days=6)]
    t1=s.index[0]+pd.Timedelta(days=int(365.25*y))
    if s.index[-1]<t1-pd.Timedelta(days=10): return np.nan
    return (s[s.index<=t1].iloc[-1]/s.iloc[0])**(1/y)-1
print("\nreal inkl. Div. p.a. ab Schock+5M:")
for p in eps[1:-1]: print(' ',str(p+5), *[f"{y}J {rr(p+5,y)*100:+.1f}%" for y in (3,5,10)])
