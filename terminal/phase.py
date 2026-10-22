"""
Marktphase (nur Anzeige, fließt nicht in Rang, Wahrscheinlichkeit oder Einstiegsplan ein).

Ordnet jeden Börsentag des S&P 500 einer von sechs Phasen zu – nach drei einfachen Messgrößen:
Abstand zum 12-Monats-Hoch, Abstand zur 200-Tage-Linie und VIX. Danach: Wie ging es früher
von solchen Tagen aus weiter (Rendite nach 12 Monaten, wie oft es noch einmal mindestens 15 % tiefer ging),
auch getrennt danach, wie lange die Phase schon läuft. Statistik seit 1990 (ab da gibt es den VIX).
Dazu die Kreditwarnung (HYG/IEF gegenüber seiner 10-Monats-Linie) mit ihrer Trefferquote seit 2008.
"""
import numpy as np
import pandas as pd

PHASES = [
    ("euphorie", "Euphorie", "Nahe am Hoch (weniger als 5 % darunter), mehr als 8 % über der 200-Tage-Linie, VIX unter 15"),
    ("sorglos", "Sorglosigkeit", "Über der 200-Tage-Linie, weniger als 10 % unter dem Hoch"),
    ("angst", "Angst", "Unter der 200-Tage-Linie, aber weniger als 20 % unter dem Hoch"),
    ("panik", "Panik", "Mindestens 20 % unter dem Hoch und VIX ab 35"),
    ("depression", "Depression", "Mindestens 20 % unter dem Hoch, unter der 200-Tage-Linie, VIX unter 35"),
    ("hoffnung", "Hoffnung", "Mindestens 10 % unter dem Hoch, aber wieder über der 200-Tage-Linie"),
]
BINS = [(1, 5), (6, 20), (21, 60), (61, None)]
GAP = 10          # kurze Ausreißer bis 10 Börsentage unterbrechen eine Phase nicht
FROM = "1990-01-01"


def classify(dd, d200, vix):
    if dd is None or d200 is None or vix is None or np.isnan(dd) or np.isnan(d200) or np.isnan(vix):
        return None
    if dd <= -20 and vix >= 35:
        return "panik"
    if dd <= -20:
        return "depression" if d200 < 0 else "hoffnung"
    if dd <= -10:
        return "angst" if d200 < 0 else "hoffnung"
    if d200 < 0:
        return "angst"
    if dd > -5 and vix < 15 and d200 > 8:
        return "euphorie"
    return "sorglos"


def episodes(codes):
    """Folgen gleicher Phase; Unterbrechungen bis GAP Tage werden überbrückt. -> [(phase, a, b)]"""
    out, i, n = [], 0, len(codes)
    while i < n:
        k, j, last = codes[i], i, i
        while j < n:
            if codes[j] == k:
                last = j
                j += 1
                continue
            g = j
            while g < n and codes[g] != k and g - last <= GAP:
                g += 1
            if g < n and codes[g] == k and g - last <= GAP:
                j = g
                continue
            break
        out.append((k, i, last))
        i = last + 1
    return out


def build(spx, vix, now):
    p = spx.dropna()
    p = p[~p.index.duplicated(keep="last")].sort_index()
    v = vix.dropna().reindex(p.index).ffill(limit=5)
    dd = (p / p.rolling(252, min_periods=1).max() - 1) * 100
    d200 = (p / p.rolling(200).mean() - 1) * 100
    ph = pd.Series([classify(a, b, c) for a, b, c in zip(dd.values, d200.values, v.values)], index=p.index)
    x = ph.loc[FROM:].dropna()
    codes, idx = list(x.values), x.index
    ep = episodes(codes)
    pos = np.zeros(len(codes), dtype=int)
    for _, a, b in ep:
        pos[a:b + 1] = np.arange(b - a + 1) + 1
    f12 = (p.shift(-252) / p - 1).reindex(idx) * 100
    lo = p[::-1].rolling(253, min_periods=253).min()[::-1]          # tiefster Kurs der nächsten 12 Monate (inkl. heute)
    mn = (lo / p - 1).reindex(idx) * 100
    ok = f12.notna().values
    hit = (mn <= -15).values
    cd = np.array(codes)

    def st(mask):
        m = mask & ok
        n = int(m.sum())
        if n < 20:
            return {"n": n}
        a = f12.values[m]
        return {"n": n, "f12": round(float(np.median(a)), 1), "pos": round(float((a > 0).mean() * 100)),
                "dd15": round(float(hit[m].mean() * 100))}

    stats = []
    eps = pd.DataFrame(ep, columns=["ph", "a", "b"])
    eps["len"] = eps.b - eps.a + 1
    tot = len(codes)
    for k, name, desc in PHASES:
        mk = cd == k
        g = eps[eps.ph == k]
        row = {"id": k, "name": name, "desc": desc, "share": round(float(mk.sum() / tot * 100)), "ep": int(len(g)),
               "dur": int(g.len.median()) if len(g) else None, "longest": int(g.len.max()) if len(g) else None, **st(mk)}
        row["bins"] = [{"lo": a, "hi": b, **st(mk & (pos >= a) & (pos <= (b or 10 ** 9)))} for a, b in BINS]
        stats.append(row)

    cur = eps.iloc[-1]
    k = cur.ph
    g = eps[eps.ph == k].iloc[:-1]
    now_ = {"ph": k, "since": idx[int(cur.a)].strftime("%Y-%m-%d"), "days": int(cur.len),
            "longer": int((g.len > cur.len).sum()), "of": int(len(g)),
            "dd": round(float(dd.iloc[-1]), 1), "d200": round(float(d200.iloc[-1]), 1), "vix": round(float(v.iloc[-1]), 1),
            "day": p.index[-1].strftime("%Y-%m-%d")}
    recent = [{"ph": r.ph, "from": idx[int(r.a)].strftime("%Y-%m-%d"), "to": idx[int(r.b)].strftime("%Y-%m-%d"), "len": int(r.len)}
              for r in eps.tail(8).itertuples()]
    return {"now": now_, "stats": stats, "all": st(np.ones(len(codes), dtype=bool)), "recent": recent, "from": idx[0].strftime("%Y-%m-%d"), "gap": GAP,
            "bins": [[a, b] for a, b in BINS]}


def credit(r, spx, n=210, crash=15):
    """Kreditwarnung: HYG/IEF gegenüber seiner 10-Monats-Linie und wie es früher nach Brüchen nach unten weiterging."""
    r = r.dropna()
    r = r[~r.index.duplicated(keep="last")].sort_index()
    m = r.rolling(n, min_periods=n).mean()
    below = (r < m) & m.notna()
    p = spx.dropna()
    lo = p[::-1].rolling(253, min_periods=253).min()[::-1]
    mn = (lo / p - 1) * 100
    ev = []
    for i in range(20, len(r)):
        if below.iloc[i] and not below.iloc[i - 20:i].any():
            d = r.index[i]
            j = p.index.searchsorted(d)
            if j >= len(p):
                continue
            x = mn.iloc[j]
            ev.append({"d": d.strftime("%Y-%m-%d"), "hit": None if np.isnan(x) else bool(x <= -crash),
                       "min": None if np.isnan(x) else round(float(x), 1)})
    done = [e for e in ev if e["hit"] is not None]
    base = mn.loc[r.index[n]:].dropna()
    since = None
    if below.iloc[-1]:
        k = len(below) - 1
        while k > 0 and below.iloc[k - 1]:
            k -= 1
        since = r.index[k].strftime("%Y-%m-%d")
    return {"pct": round(float((r.iloc[-1] / m.iloc[-1] - 1) * 100), 2), "below": bool(below.iloc[-1]), "since": since,
            "day": r.index[-1].strftime("%Y-%m-%d"), "n": len(done), "hits": sum(e["hit"] for e in done),
            "base": round(float((base <= -crash).mean() * 100)), "from": r.index[n].strftime("%Y-%m-%d"),
            "events": ev[-30:], "crash": crash}
