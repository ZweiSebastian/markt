"""
Einschätzungs-Modell für das Markt Terminal.

Monatliches Regelmodell aus sechs Säulen. Jede Komponente wird nach fester, vorab gewählter Regel auf
-1 … +1 abgebildet (keine Optimierung auf die Vergangenheit), Säulen sind der Mittelwert ihrer
verfügbaren Komponenten, der Gesamtscore der gewichtete Mittelwert der Säulen: 0–100, 50 = neutral.

Säulen und Gewichte
- Bewertung 20 %: Shiller-CAPE ggü. 20-J.-Ø, Aktien-Risikoprämie (Excess CAPE Yield)
- Trend 20 %: Kurs vs. 10-Monats-Linie, 12-Monats-Momentum, Abstand zur 200-Wochen-Linie (je Zielindex)
- Marktbreite 10 %: Sektoren und Weltbörsen im Aufwärtstrend, gleich- vs. kapitalgewichtet, Nebenwerte vs. Standardwerte
- Konjunktur 20 %: Sahm-Regel, Zinskurve, OECD-Frühindikator, Erstanträge, Stellenaufbau, Inflationstrend, Ölschock
- Finanzbedingungen 15 %: Kreditaufschlag Baa (wenn FRED erreichbar), Hochzinsfonds seit 1978, NFCI, HYG/IEF, Fed-Kurs, Hypothekenzins, Dollar
- Stimmung 15 % (konträr): Abstand vom 12-M.-Hoch, VIX, AAII-Umfrage

Zusätzlich:
- Rückblick nach Score-Bereichen, Regeln im Test, Liste der großen Einbrüche mit Score davor
- Analogien: die Monate der Vergangenheit, deren Gesamtbild dem heutigen am ähnlichsten war, und was danach kam

Einschränkungen: Konjunkturdaten in heutiger (revidierter) Fassung; S&P 500 vor 1970 auf Basis der
Shiller-Monatsdurchschnitte (glättet Rückgänge etwas). Kursrenditen ohne Dividenden.
"""
import math
import re

import numpy as np
import pandas as pd

WEIGHTS = {"bewertung": 0.20, "trend": 0.20, "breite": 0.10, "konjunktur": 0.20, "finanzen": 0.15, "stimmung": 0.15}
PILLAR_NAMES = {"bewertung": "Bewertung", "trend": "Trend", "breite": "Marktbreite", "konjunktur": "Konjunktur",
                "finanzen": "Finanzbedingungen", "stimmung": "Stimmung (konträr)"}
# Zielindizes: (Reihe, Name, Region). Makro-Säulen sind US-lastig und für alle gleich; Trend, Überdehnung und
# Abstand vom Hoch werden je Index berechnet.
TARGETS = {
    "world": ("msci", "MSCI World", "Welt"),
    "world_eur": ("msci_eur", "MSCI World in Euro", "Welt"),
    "spx": ("spx", "S&P 500", "USA"),
    "ndx": ("ndx", "Nasdaq 100", "USA"),
    "rut": ("rut", "Russell 2000", "USA"),
    "sx5e": ("sx5e", "Euro Stoxx 50", "Europa"),
    "dax": ("dax", "DAX", "Europa"),
    "nikkei": ("nikkei", "Nikkei 225", "Japan"),
    "em": ("em", "Schwellenländer-ETF", "Schwellenländer"),
}
BANDS = [(0, 35, "unter 35"), (35, 45, "35–45"), (45, 55, "45–55"), (55, 65, "55–65"), (65, 101, "ab 65")]
CRASH = 0.15          # „größerer Rückgang“ für Wahrscheinlichkeiten: −15 % innerhalb von 12 Monaten
EPISODE = 0.20        # „großer Einbruch“ für die Liste: −20 % vom Hoch (Monatsschluss)


def clip(x, lo=-1.0, hi=1.0):
    return x.clip(lo, hi) if isinstance(x, pd.Series) else max(lo, min(hi, x))


def interp(x, xs, ys):
    """Stückweise linear, außerhalb konstant; NaN bleibt NaN."""
    v = np.interp(x.values.astype(float), xs, ys)
    return pd.Series(np.where(np.isnan(x.values.astype(float)), np.nan, v), index=x.index)


def label(score):
    """Grenzen und Texte folgen dem Rückblick: Unter 35 kamen die großen Verluste, darüber
    unterschieden sich die Renditen kaum – der Score taugt vor allem als Risiko-Ampel."""
    if score is None or (isinstance(score, float) and math.isnan(score)):
        return ("–", "neutral", "Zu wenig Daten")
    if score >= 65:
        return ("Rückenwind", "good", "Kaufen – auch größere Beträge")
    if score >= 45:
        return ("Neutral", "neutral", "Normal investieren (Sparplan oder in Raten)")
    if score >= 35:
        return ("Gegenwind", "warn", "Nur in Raten investieren, keine großen Einmalbeträge")
    return ("Gefahrenzone", "crit", "Abwarten – historisch folgten hier meist Verluste")


def dez(t):
    return re.sub(r"(\d)\.(\d)", r"\1,\2", t)


MONTHS = ["Jan.", "Feb.", "März", "Apr.", "Mai", "Juni", "Juli", "Aug.", "Sep.", "Okt.", "Nov.", "Dez."]


def mname(p):
    return f"{MONTHS[p.month - 1]} {p.year}"


def run(ser, markt, now):
    def monthly(sid, how="last"):
        s = ser(sid)
        if s is None or not len(s):
            return None
        g = s.groupby(s.index.to_period("M"))
        return g.last() if how == "last" else g.mean()

    cur = pd.Period(now.strftime("%Y-%m"), "M")
    idx = pd.period_range("1950-01", cur, freq="M")

    def R(s, ffill=3):
        if s is None:
            return pd.Series(np.nan, index=idx)
        s = s.copy()
        if not isinstance(s.index, pd.PeriodIndex):
            s.index = pd.PeriodIndex(s.index, freq="M")
        s = s[~s.index.duplicated(keep="last")].reindex(idx)
        return s.ffill(limit=ffill) if ffill else s

    # ---------- gemeinsame Eingänge (monatlich)
    cape = R(monthly("cape_long"), 2)
    cd = monthly("cape")
    if cd is not None:
        cape = cape.copy()
        ok_ = cd.index.isin(idx)
        cape[cd.index[ok_]] = cd[ok_].values
    ecy = R(monthly("ecy"), 2)
    y10 = R(monthly("y10", "mean"))
    y10 = y10.where(y10.notna(), R(monthly("y10_m")))
    tbill = R(monthly("tbill_m", "mean"))
    tbill = tbill.where(tbill.notna(), R(monthly("y3m", "mean"))).ffill(limit=3)
    unemp = R(monthly("unemp"), 3)
    ff = R(monthly("effr", "mean"))
    ff = ff.where(ff.notna(), R(monthly("ff_long", "mean")))
    cli = R(monthly("cli_us"), 3)
    claims = R(monthly("claims", "mean"), 2)
    payrolls = R(monthly("payrolls"), 3)
    cpi = R(monthly("cpi"), 3)
    wti = R(monthly("wti_long"), 2)
    nfci = R(monthly("nfci", "mean"), 2)
    baa_s = R(monthly("baa_spread"), 2)
    hygief = R(monthly("hyg_ief"), 1)
    hyfund = R(monthly("vwehx"), 1)
    mort = R(monthly("mort30", "mean"), 2)
    vix = R(monthly("vix", "mean"), 1)
    aaii = R(monthly("aaii", "mean"), 2)
    dxy = R(monthly("dxy"), 1)
    sect = R(monthly("sect_part", "mean"), 1)
    wpart = R(monthly("world_part", "mean"), 1)
    ewcap = R(monthly("breadth"), 1)
    smlg = R(monthly("small_large"), 1)

    comp_common, meta = {}, {}

    def add(cid, pillar, name, score, raw, fmt):
        comp_common[cid] = score
        meta[cid] = (pillar, name, raw, fmt)

    # Bewertung
    z = (cape - cape.rolling(240, min_periods=120).mean()) / cape.rolling(240, min_periods=120).std()
    add("cape_z", "bewertung", "Shiller-KGV ggü. 20-J.-Ø", clip(-z / 2), z, lambda v: f"CAPE {cape.dropna().iloc[-1]:.1f} · {v:+.1f} σ")
    ez = (ecy - ecy.rolling(360, min_periods=120).mean()) / ecy.rolling(360, min_periods=120).std()
    add("ecy", "bewertung", "Aktien-Risikoprämie (Excess CAPE Yield)", clip(ez / 2), ecy, lambda v: f"{v:.2f} % (Gewinnrendite minus Realzins)")

    # Marktbreite
    add("sect", "breite", "US-Sektoren im Aufwärtstrend", interp(sect, [20, 50, 80], [-1.0, 0.0, 0.6]), sect,
        lambda v: f"{v:.0f} % der 11 Sektoren über ihrer 200-Tage-Linie")
    add("wpart", "breite", "Weltbörsen im Aufwärtstrend", interp(wpart, [20, 50, 80], [-1.0, 0.0, 0.6]), wpart,
        lambda v: f"{v:.0f} % von 9 großen Indizes über ihrer 200-Tage-Linie")
    ed = ewcap / ewcap.rolling(10, min_periods=8).mean() - 1
    add("ewcap", "breite", "Gleichgewichtet vs. kapitalgewichtet (RSP/SPY)", clip(ed / 0.03), ed * 100,
        lambda v: f"{v:+.1f} % ggü. 10-Monats-Linie")
    sl = smlg / smlg.shift(6) - 1
    add("smlg", "breite", "Nebenwerte vs. Standardwerte (6 M.)", clip(sl / 0.10) * 0.6, sl * 100, lambda v: f"{v:+.1f} %")

    # Konjunktur
    u3 = unemp.rolling(3).mean()
    sahm = u3 - u3.shift(1).rolling(12).min()
    add("sahm", "konjunktur", "Sahm-Regel (Arbeitsmarkt)", interp(sahm, [0.1, 0.3, 0.5], [0.5, 0.0, -1.0]), sahm,
        lambda v: f"{v:.2f} (Rezessionssignal ab 0,5)")
    curve = y10 - tbill
    inv24 = (curve < 0).astype(float).rolling(24, min_periods=1).max().astype(bool)
    cs = interp(curve, [0, 1, 2], [0.0, 0.3, 0.5])
    cs = cs.where(~(inv24 & (curve >= 0)), -1.0).where(~(curve < 0), -0.5)
    cs[curve.isna()] = np.nan
    add("curve", "konjunktur", "Zinskurve 10J − 3M", cs, curve,
        lambda v: f"{v:+.2f} Pp." + (" · invertiert" if v < 0 else " · nach Inversion wieder steil" if bool(inv24.iloc[-1]) else ""))
    clich = cli - cli.shift(6)
    add("cli", "konjunktur", "OECD-Frühindikator USA (6 M.)", clip(clich / 1.0), clich, lambda v: f"{v:+.2f} Pkt. in 6 Monaten")
    cy = claims / claims.shift(12) - 1
    add("claims", "konjunktur", "Erstanträge Arbeitslosenhilfe (ggü. Vorjahr)", interp(cy, [-0.1, 0.0, 0.2], [0.5, 0.0, -1.0]), cy * 100,
        lambda v: f"{v:+.0f} %")
    p3 = payrolls.rolling(3).mean()
    add("payrolls", "konjunktur", "Stellenaufbau (3-M.-Ø)", interp(p3, [-50, 0, 100, 250], [-1.0, -0.5, 0.0, 0.3]), p3,
        lambda v: f"{v:+.0f} Tsd. pro Monat")
    ci = cpi - cpi.shift(6)
    add("infl", "konjunktur", "Inflationstrend (6 M.)", clip(-ci / 1.5) * 0.6, ci, lambda v: f"{v:+.1f} Pp. (Inflation ggü. Vorjahr)")
    wy = wti / wti.shift(12) - 1
    add("oil", "konjunktur", "Ölpreis ggü. Vorjahr", interp(wy, [0.2, 0.5, 1.0], [0.0, -0.6, -1.0]), wy * 100, lambda v: f"{v:+.0f} %")

    # Finanzbedingungen
    bmed = baa_s.rolling(120, min_periods=60).median()
    bsc = 0.5 * clip(-(baa_s - bmed) / 1.0) + 0.5 * clip(-(baa_s - baa_s.shift(6)) / 0.5)
    add("baa", "finanzen", "Kreditaufschlag Baa − 10J", bsc, baa_s, lambda v: f"{v:.2f} Pp. (10-J.-Median {bmed.dropna().iloc[-1]:.2f})")
    add("nfci", "finanzen", "Finanzbedingungen (NFCI)", 0.5 * clip(-nfci / 0.5) + 0.5 * clip(-(nfci - nfci.shift(3)) / 0.2), nfci,
        lambda v: f"{v:+.2f} (unter 0 = lockerer als üblich)")
    hf = hyfund / hyfund.rolling(10, min_periods=10).mean() - 1
    add("hyfund", "finanzen", "Hochzinsanleihen im Trend (Fonds seit 1978)", clip(hf / 0.015), hf * 100, lambda v: f"{v:+.1f} % ggü. 10-Monats-Linie")
    hd = hygief / hygief.rolling(10, min_periods=8).mean() - 1
    add("credit", "finanzen", "Kreditappetit (HYG/IEF ggü. 10-M.-Linie)", clip(hd / 0.02), hd * 100, lambda v: f"{v:+.1f} %")
    ffc = ff - ff.shift(12)
    add("fed", "finanzen", "Fed-Kurs (Leitzins ggü. Vorjahr)", interp(ffc, [-1.0, 0.0, 1.5], [0.25, 0.0, -0.5]), ffc, lambda v: f"{v:+.2f} Pp.")
    mc = mort - mort.shift(24)
    add("mort", "finanzen", "Hypothekenzins (2 J.)", interp(mc, [-1.0, 0.0, 1.0, 2.5], [0.3, 0.0, -0.4, -1.0]), mc, lambda v: f"{v:+.2f} Pp.")
    dch = dxy / dxy.shift(12) - 1
    add("dollar", "finanzen", "Dollar (ggü. Vorjahr)", clip(-dch / 0.10) * 0.5, dch * 100, lambda v: f"{v:+.1f} %")

    # Stimmung
    add("vix", "stimmung", "Angst (VIX, Monats-Ø)", interp(vix, [12, 20, 30, 40], [-0.3, 0.0, 0.4, 0.8]), vix, lambda v: f"{v:.1f}")
    add("aaii", "stimmung", "Anlegerumfrage AAII (Bullen − Bären)", interp(aaii, [-20, 7, 35], [0.8, 0.0, -0.6]), aaii, lambda v: f"{v:+.0f} Pp.")

    targets = {}
    for key, (sid, tname, region) in TARGETS.items():
        P = R(monthly(sid), 0)
        if key == "spx":   # vor den Tageskursen: Shiller-Monatsdurchschnitte (skaliert)
            sm = R(monthly("spx_m"), 0)
            f0 = P.first_valid_index()
            if f0 is not None and pd.notna(sm.get(f0)):
                sm = sm * (P[f0] / sm[f0])
                P = P.where(P.notna() | (P.index > f0), sm)
        if P.notna().sum() < 96:
            continue
        comp, m2 = dict(comp_common), dict(meta)
        sma10 = P.rolling(10, min_periods=10).mean()
        d10 = P / sma10 - 1
        comp["sma10"] = clip(d10 / 0.05)
        m2["sma10"] = ("trend", f"{tname} ggü. 10-Monats-Linie", d10 * 100, lambda v: f"{v:+.1f} %")
        mom = P / P.shift(12) - 1 - tbill.fillna(0) / 100
        comp["mom12"] = clip(mom / 0.15)
        m2["mom12"] = ("trend", "12-Monats-Momentum (über Geldmarktzins)", mom * 100, lambda v: f"{v:+.1f} %")
        d200 = P / P.rolling(46, min_periods=46).mean() - 1
        comp["w200"] = interp(d200, [-0.05, 0.10, 0.30, 0.50], [1.0, 0.3, 0.0, -0.4])
        m2["w200"] = ("trend", "Abstand zur 200-Wochen-Linie", d200 * 100, lambda v: f"{v:+.0f} % (weit darüber = überdehnt)")
        dd = P / P.rolling(12, min_periods=1).max() - 1
        comp["dd"] = interp(dd, [-0.25, -0.10, 0.0], [1.0, 0.4, 0.0])
        m2["dd"] = ("stimmung", "Abstand vom 12-Monats-Hoch", dd * 100, lambda v: f"{v:+.1f} %")

        C = pd.DataFrame(comp)
        Pl = pd.DataFrame({p: C[[c for c in C.columns if m2[c][0] == p]].mean(axis=1, skipna=True) for p in WEIGHTS})
        avail = Pl.notna()
        w = pd.Series(WEIGHTS)
        total = Pl.fillna(0).mul(w, axis=1).sum(axis=1) / avail.mul(w, axis=1).sum(axis=1).replace(0, np.nan)
        ok = (avail.sum(axis=1) >= 3) & P.notna() & avail["trend"]
        # Streuung angleichen: Gesamtwert in Einheiten seiner bisherigen Schwankung (nur Vergangenheit, kein Blick nach vorn).
        # 50 bleibt „alle Komponenten neutral“; 35/65 entsprechen etwa einer Standardabweichung.
        tv = total.where(ok)
        sd = np.sqrt((tv ** 2).expanding(min_periods=36).mean())
        score = (50 + 15 * tv / sd).clip(0, 100).where(ok & sd.notna()).round(1)

        # ---------- Zukunft je Monat
        fw = {h: P.shift(-h) / P - 1 for h in (6, 12, 24, 36, 60)}
        for h in (36, 60):
            fw[h] = (1 + fw[h]) ** (12 / h) - 1
        def fut_min(h):
            return pd.concat([P.shift(-i) for i in range(1, h + 1)], axis=1).min(axis=1, skipna=False) / P - 1
        mdd12, mdd24 = fut_min(12), fut_min(24)
        df = pd.DataFrame({"s": score, "f12": fw[12], "f36": fw[36], "f60": fw[60], "dd": mdd12}).dropna(subset=["s"])
        bt_start = df.index.min()
        crash_base = float((mdd12.reindex(df.index).dropna() <= -CRASH).mean() * 100)

        bands = []
        for lo, hi, name in BANDS:
            g = df[(df.s >= lo) & (df.s < hi)]
            g12 = g.dropna(subset=["f12"])
            gd = g.dropna(subset=["dd"])
            bands.append({
                "band": name, "lo": lo, "hi": hi, "n": int(len(g12)), "share": round(len(g) / max(1, len(df)) * 100, 1),
                "f12": None if not len(g12) else round(float(g12.f12.median() * 100), 1),
                "pos12": None if not len(g12) else round(float((g12.f12 > 0).mean() * 100), 0),
                "worst12": None if not len(g12) else round(float(g12.f12.min() * 100), 0),
                "f36": None if g.f36.dropna().empty else round(float(g.f36.dropna().median() * 100), 1),
                "f60": None if g.f60.dropna().empty else round(float(g.f60.dropna().median() * 100), 1),
                "dd12": None if not len(gd) else round(float(gd.dd.median() * 100), 1),
                "crash12": None if not len(gd) else round(float((gd.dd <= -CRASH).mean() * 100), 0),
            })

        def sp(a, b):
            x = pd.concat([a, b], axis=1).dropna()
            return None if len(x) < 60 else round(float(x.iloc[:, 0].rank().corr(x.iloc[:, 1].rank())), 2)
        rank = {"score_f12": sp(df.s, df.f12), "score_f36": sp(df.s, df.f36), "score_f60": sp(df.s, df.f60),
                "score_dd": sp(df.s, df.dd),
                "pillars": {p: {"f12": sp(Pl[p].reindex(df.index), df.f12), "f36": sp(Pl[p].reindex(df.index), df.f36),
                                "dd": sp(Pl[p].reindex(df.index), df.dd)} for p in WEIGHTS}}
        base = {"f12": round(float(df.f12.dropna().median() * 100), 1), "pos12": round(float((df.f12.dropna() > 0).mean() * 100), 0),
                "f36": round(float(df.f36.dropna().median() * 100), 1), "dd12": round(float(df.dd.dropna().median() * 100), 1),
                "crash12": round(crash_base, 0)}

        # ---------- Regeln im Test (monatlich, Kassenanteil verzinst mit T-Bill)
        r = P / P.shift(1) - 1
        cash = (tbill.ffill() / 100 / 12).reindex(idx)
        sidx = df.index

        def strat(expo):
            e = expo.shift(1).reindex(sidx).fillna(0)
            ret = (e * r.reindex(sidx) + (1 - e) * cash.reindex(sidx).fillna(0)).dropna()
            eq = (1 + ret).cumprod()
            yrs = len(ret) / 12
            return {"cagr": round((eq.iloc[-1] ** (1 / yrs) - 1) * 100, 1), "mdd": round(float((eq / eq.cummax() - 1).min()) * 100, 0),
                    "vol": round(float(ret.std() * math.sqrt(12)) * 100, 1), "expo": round(float(e.mean() * 100), 0),
                    "eq": eq}
        sched = {
            "bh": ("Kaufen und halten", "immer 100 % investiert", pd.Series(1.0, index=idx)),
            "trend": ("Trendregel 10 Monate", "investiert, wenn der Kurs über seiner 10-Monats-Linie schließt, sonst Geldmarkt", (P > sma10).astype(float)),
            "score": ("Modell-Quote", "Score 50 = 50 % investiert, ab 65 = 100 %, bis 35 = 0 %; Rest Geldmarkt", ((score - 50) / 30 + 0.5).clip(0, 1)),
            "schutz": ("Schutzregel", "voll investiert, außer der Score fällt: unter 45 nur 50 %, unter 35 raus", score.apply(lambda v: np.nan if pd.isna(v) else 1.0 if v >= 45 else 0.5 if v >= 35 else 0.0)),
        }
        strategies, eqs = [], {}
        for k_, (n_, d_, e_) in sched.items():
            S_ = strat(e_)
            eqs[k_] = S_.pop("eq")
            strategies.append({"id": k_, "name": n_, "desc": d_, **S_, "eq": [round(float(v), 4) for v in eqs[k_].values]})

        # ---------- große Einbrüche (≥20 % vom Hoch, Monatsschluss) und was der Score vorher zeigte
        episodes = []
        Pv = P.dropna()
        Pv = Pv[Pv.index >= bt_start]
        peak_i, peak_v, i = Pv.index[0], Pv.iloc[0], 0
        vals = Pv.values
        pidx = list(Pv.index)
        n_ = len(vals)
        i = 0
        while i < n_:
            # Hoch suchen, dann Einbruch ≥ EPISODE prüfen
            pk = i
            j = i + 1
            trough = i
            while j < n_ and vals[j] < vals[pk]:
                if vals[j] < vals[trough]:
                    trough = j
                j += 1
            depth = vals[trough] / vals[pk] - 1
            if depth <= -EPISODE:
                pk_p, tr_p = pidx[pk], pidx[trough]
                win = score.loc[pk_p - 6:tr_p].dropna()
                warn = win[win < 45]
                first = warn.index[0] if len(warn) else None
                lost_at = None if first is None else round(float(P[first] / P[pk_p] - 1) * 100, 0)
                ep = {"peak": str(pk_p), "trough": str(tr_p), "depth": round(depth * 100, 0),
                      "months": int((tr_p - pk_p).n), "recover": None if j >= n_ else str(pidx[j]),
                      "s_peak": None if pd.isna(score.get(pk_p)) else round(float(score[pk_p])),
                      "s_min": None if not len(win) else round(float(win.min())),
                      "warn": None if first is None else str(first), "lost_at_warn": lost_at}
                for k_ in ("trend", "score", "schutz"):
                    e_ = eqs[k_]
                    seg = e_.loc[pk_p:tr_p]
                    ep["dd_" + k_] = None if len(seg) < 2 else round(float(seg.min() / seg.iloc[0] - 1) * 100, 0)
                episodes.append(ep)
            i = j if j > i else i + 1
        warned = [e for e in episodes if e["warn"] is not None]

        # ---------- Analogien: ähnlichste Monate der Vergangenheit
        F = C.copy()
        F["cape_raw"] = clip(z / 2.5, -2, 2)          # Bewertung über die Sättigung hinaus unterscheiden
        fam = {c: (m2[c][0] if c in m2 else "bewertung") for c in F.columns}
        last_i = score.last_valid_index()
        x0 = F.loc[last_i]
        cand = F.loc[:last_i - 24]
        cand = cand[score.reindex(cand.index).notna()]
        dist = pd.Series(np.nan, index=cand.index)
        shared_w = pd.Series(0.0, index=cand.index)
        acc = pd.Series(0.0, index=cand.index)
        for p in WEIGHTS:
            cols = [c for c in F.columns if fam[c] == p and pd.notna(x0[c])]
            if not cols:
                continue
            dif = (cand[cols] - x0[cols]) ** 2
            msd = dif.mean(axis=1, skipna=True)
            has = dif.notna().any(axis=1)
            acc = acc.add((msd * WEIGHTS[p]).where(has, 0), fill_value=0)
            shared_w = shared_w.add(has.astype(float) * WEIGHTS[p], fill_value=0)
        tot_w = sum(WEIGHTS[p] for p in WEIGHTS if any(fam[c] == p and pd.notna(x0[c]) for c in F.columns))
        dist = np.sqrt(acc / shared_w.replace(0, np.nan))
        dist = dist[shared_w >= 0.7 * tot_w].dropna()
        order = dist.sort_values()
        picks = []
        for p_, d_ in order.items():
            if all(abs((p_ - q).n) >= 18 for q, _ in picks):
                picks.append((p_, d_))
            if len(picks) >= 8:
                break
        analogs, paths = [], []
        for p_, d_ in picks:
            pth = [None if pd.isna(P.get(p_ + h)) else round(float(P[p_ + h] / P[p_] * 100), 2) for h in range(0, 37)]
            a = {"month": str(p_), "name": mname(p_), "sim": round(float(max(0, 1 - d_ / 1.2) * 100)),
                 "score": round(float(score[p_])),
                 "pillars": {p: None if pd.isna(Pl[p].get(p_)) else round(float(50 + 50 * Pl[p][p_])) for p in WEIGHTS},
                 "f6": None if pd.isna(fw[6].get(p_)) else round(float(fw[6][p_]) * 100, 1),
                 "f12": None if pd.isna(fw[12].get(p_)) else round(float(fw[12][p_]) * 100, 1),
                 "f24": None if pd.isna(fw[24].get(p_)) else round(float(fw[24][p_]) * 100, 1),
                 "dd12": None if pd.isna(mdd12.get(p_)) else round(float(mdd12[p_]) * 100, 1),
                 "dd24": None if pd.isna(mdd24.get(p_)) else round(float(mdd24[p_]) * 100, 1),
                 "path": pth}
            analogs.append(a)
        def med(k_):
            v = [a[k_] for a in analogs if a[k_] is not None]
            return None if not v else round(float(np.median(v)), 1)
        dd12s = [a["dd12"] for a in analogs if a["dd12"] is not None]
        f12s = [a["f12"] for a in analogs if a["f12"] is not None]
        mpath = []
        for h in range(37):
            v = [a["path"][h] for a in analogs if a["path"][h] is not None]
            mpath.append(None if len(v) < 3 else round(float(np.median(v)), 2))
        # zum Vergleich: alle Monate mit ähnlichem Gesamtscore (±5)
        sim_score = df[(df.s - float(score[last_i])).abs() <= 5].dropna(subset=["dd"])
        ana = {"items": analogs, "median_path": mpath,
               "f12": med("f12"), "f24": med("f24"), "dd12": med("dd12"),
               "pos12": None if not f12s else round(sum(1 for v in f12s if v > 0) / len(f12s) * 100),
               "crash12": None if not dd12s else round(sum(1 for v in dd12s if v <= -CRASH * 100) / len(dd12s) * 100),
               "n": len(analogs), "crash_base": round(crash_base),
               "crash_same_score": None if not len(sim_score) else round(float((sim_score.dd <= -CRASH).mean() * 100))}

        # ---------- aktueller Stand
        now_score = None if last_i is None else float(round(score[last_i]))   # gerundet, damit Anzeige, Ampel und Bereich zusammenpassen
        lab = label(now_score)
        pil_now = []
        for p in WEIGHTS:
            comps = []
            for c in C.columns:
                if m2[c][0] != p:
                    continue
                v = m2[c][2].loc[:last_i].dropna()
                sc = C[c].loc[:last_i].dropna()
                if not len(sc):
                    comps.append({"id": c, "name": m2[c][1], "text": "keine Daten", "score": None})
                    continue
                vv = float(v.iloc[-1]) if len(v) else None
                try:
                    txt = m2[c][3](vv) if vv is not None else ""
                except Exception:  # noqa
                    txt = ""
                stale = sc.index[-1] != last_i or pd.isna(C[c].get(last_i))
                comps.append({"id": c, "name": m2[c][1], "text": dez(txt), "score": round(float(sc.iloc[-1]), 2),
                              "asof": str(sc.index[-1]), "stale": bool(stale), "since": str(sc.index[0].year)})
            pv = Pl[p].loc[:last_i].dropna()
            pil_now.append({"id": p, "name": PILLAR_NAMES[p], "weight": WEIGHTS[p],
                            "score": None if not len(pv) else round(float(50 + 50 * pv.iloc[-1]), 0), "comps": comps})

        # ---------- Klartext
        def word(s):
            return "stark positiv" if s >= 70 else "positiv" if s >= 58 else "neutral" if s > 42 else "negativ" if s > 30 else "stark negativ"
        pos = [x for x in pil_now if x["score"] is not None and x["score"] >= 58]
        neg = [x for x in pil_now if x["score"] is not None and x["score"] <= 42]
        sent = [f"Der Gesamtscore für den {tname} liegt bei {now_score:.0f} von 100 ({lab[0]})."]
        if pos:
            sent.append("Dafür spricht: " + ", ".join(f"{x['name']} ({word(x['score'])})" for x in pos) + ".")
        if neg:
            sent.append("Dagegen spricht: " + ", ".join(f"{x['name']} ({word(x['score'])})" for x in neg) + ".")
        if analogs:
            top = ", ".join(a["name"] for a in analogs[:3])
            sent.append(f"Am ähnlichsten war die Gesamtlage {top}. In den {len(analogs)} ähnlichsten Momenten seit {bt_start.year} "
                        f"stand der {tname} ein Jahr später im Median {ana['f12']:+.1f} %; in {ana['crash12']} % davon kam es innerhalb eines Jahres "
                        f"zu einem Rückgang von mindestens {CRASH * 100:.0f} % (über alle Monate: {ana['crash_base']} %).")
        cb = [x for x in bands if x["n"]]
        if cb:
            parts = "; ".join(f"{x['band']}: {x['crash12']:.0f} %" for x in cb)
            sent.append(f"Je niedriger der Score, desto häufiger folgte innerhalb eines Jahres ein Rückgang von {CRASH * 100:.0f} % oder mehr ({parts}). "
                        f"Die Rendite nach einem Jahr unterschied sich oberhalb von 35 dagegen wenig – der Score ist eine Risiko-Ampel, kein Renditeversprechen.")
        if episodes:
            sent.append(f"Von den {len(episodes)} großen Einbrüchen (≥ {EPISODE * 100:.0f} %) seit {bt_start.year} zeigte der Score bei {len(warned)} "
                        f"spätestens bis zum Tief Gegenwind (unter 45) – im Median, als der Index {abs(np.median([e['lost_at_warn'] for e in warned])) if warned else 0:.0f} % unter dem Hoch lag.")
        sb = next(x for x in strategies if x["id"] == "bh")
        ss = next(x for x in strategies if x["id"] == "score")
        sent.append(f"Als feste Regel umgesetzt (Modell-Quote): {ss['cagr']:+.1f} % p.a. bei höchstens {ss['mdd']:.0f} % Verlust – Kaufen und Halten brachte "
                    f"{sb['cagr']:+.1f} % p.a., musste aber {sb['mdd']:.0f} % aushalten.")
        sent = [dez(x) for x in sent]

        cb_now = next((x for x in bands if x["lo"] <= now_score < x["hi"]), None)
        risk = {"band": None if not cb_now else cb_now["crash12"], "analog": ana["crash12"], "base": ana["crash_base"]}
        hist_idx = score.dropna().index
        targets[key] = {
            "name": tname, "region": region, "sid": sid,
            "now": {"score": None if now_score is None else round(now_score), "month": str(last_i), "label": lab[0],
                    "cls": lab[1], "action": lab[2], "pillars": pil_now, "text": sent, "risk": risk},
            "hist": {"months": [str(p) for p in hist_idx], "score": score[hist_idx].tolist(),
                     "price": [None if pd.isna(x) else round(float(x), 2) for x in P[hist_idx].values],
                     "pillars": {p: [None if pd.isna(x) else round(float(50 + 50 * x), 1) for x in Pl[p][hist_idx].values] for p in WEIGHTS}},
            "bands": bands, "base": base, "rank": rank, "since": str(bt_start),
            "strategies": strategies, "strat_months": [str(p) for p in eqs["bh"].index],
            "episodes": episodes, "analogs": ana, "crash": CRASH, "episode": EPISODE,
        }

    # ---------- Sebas eigene Regel (200-Wochen-Linie + CAPE-Wende)
    rule = {}
    for key, (sid, _n, _r) in TARGETS.items():
        s = ser(sid)
        if s is None:
            continue
        wk = s.groupby(s.index.to_period("W-FRI")).last()
        sma = wk.rolling(200, min_periods=200).mean()
        rule[key] = {"close": round(float(wk.iloc[-1]), 2), "sma200w": round(float(sma.iloc[-1]), 2),
                     "dist": round(float(wk.iloc[-1] / sma.iloc[-1] * 100 - 100), 1),
                     "lastTouch": next((str(p.end_time.date()) for p, a, b in zip(wk.index[::-1], wk.values[::-1], sma.values[::-1])
                                        if not pd.isna(b) and a <= b), None)}
    if markt:
        rule["signalScore"] = markt.get("score")
    return {"weights": WEIGHTS, "targets": targets, "rule": rule,
            "note": "Kursrenditen ohne Dividenden. Konjunkturdaten in heutiger (revidierter) Fassung; S&P 500 vor 1970 aus Monatsdurchschnitten (Shiller). Kein Anlagerat – ein Regelmodell."}
