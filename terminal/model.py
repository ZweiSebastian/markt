"""
Einschätzungs-Modell für das Markt Terminal.

Monatliches Regelmodell aus fünf Säulen. Jede Komponente wird nach fester, vorab gewählter Regel auf
-1 … +1 abgebildet (keine Optimierung auf die Vergangenheit), Säulen sind der Mittelwert ihrer
verfügbaren Komponenten, der Gesamtscore der gewichtete Mittelwert der Säulen: 0–100, 50 = neutral.

Säulen und Gewichte
- Bewertung 25 %: Shiller-CAPE gegenüber 20-J.-Ø, Aktien-Risikoprämie (Excess CAPE Yield)
- Trend 25 %: Kurs vs. 10-Monats-Linie, 12-Monats-Momentum (je Zielindex)
- Konjunktur 20 %: Sahm-Regel, Zinskurve 10J−3M (inkl. Wieder-Steilwerden), OECD-Frühindikator, Erstanträge
- Finanzbedingungen 15 %: NFCI, Kreditappetit (HYG/IEF), Fed-Kurs, Dollar
- Stimmung 15 % (konträr): Abstand vom 12-M.-Hoch, VIX, AAII-Umfrage

Danach wird geprüft, was historisch auf ähnliche Scores folgte (Kursrendite ohne Dividenden).
Einschränkung: Konjunkturdaten sind in der heutigen (revidierten) Fassung verwendet, nicht so,
wie man sie damals kannte; der Rückblick ist dadurch etwas zu optimistisch.
"""
import math

import numpy as np
import pandas as pd

WEIGHTS = {"bewertung": 0.25, "trend": 0.25, "konjunktur": 0.20, "finanzen": 0.15, "stimmung": 0.15}
PILLAR_NAMES = {"bewertung": "Bewertung", "trend": "Trend", "konjunktur": "Konjunktur",
                "finanzen": "Finanzbedingungen", "stimmung": "Stimmung (konträr)"}
TARGETS = {"world": ("msci", "MSCI World"), "spx": ("spx", "S&P 500")}
BANDS = [(0, 35, "unter 35"), (35, 45, "35–45"), (45, 55, "45–55"), (55, 65, "55–65"), (65, 101, "ab 65")]


def clip(x, lo=-1.0, hi=1.0):
    return x.clip(lo, hi) if isinstance(x, pd.Series) else max(lo, min(hi, x))


def interp(x, xs, ys):
    """Stückweise linear, außerhalb konstant; NaN bleibt NaN."""
    return x.apply(lambda v: np.nan if pd.isna(v) else float(np.interp(v, xs, ys)))


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


def run(ser, markt, now):
    def mlast(sid):
        s = ser(sid)
        if s is None or not len(s):
            return None
        m = s.groupby(s.index.to_period("M")).last()
        return m

    def mmean(sid):
        s = ser(sid)
        if s is None or not len(s):
            return None
        return s.groupby(s.index.to_period("M")).mean()

    cur = pd.Period(now.strftime("%Y-%m"), "M")
    idx = pd.period_range("1950-01", cur, freq="M")

    def R(s, ffill=3):
        if s is None:
            return pd.Series(np.nan, index=idx)
        s = s.copy()
        if not isinstance(s.index, pd.PeriodIndex):
            s.index = pd.PeriodIndex(s.index, freq="M")
        s = s[~s.index.duplicated(keep="last")]
        s = s.reindex(idx)
        return s.ffill(limit=ffill) if ffill else s

    # ---------- gemeinsame Eingänge (monatlich)
    cape = R(mlast("cape_long"), 2)
    cd = mlast("cape")
    if cd is not None:
        cape = cape.copy()
        cape[cd.index[cd.index.isin(idx)]] = cd[cd.index.isin(idx)].values
    ecy = R(mlast("ecy"), 2)
    y10 = R(mmean("y10"))
    tbill = R(mmean("tbill_m"))
    y3 = R(mmean("y3m"))
    tbill = tbill.where(tbill.notna(), y3)
    tbill = tbill.ffill(limit=3)
    unemp = R(mlast("unemp"), 3)
    ff = R(mmean("effr"))
    ff = ff.where(ff.notna(), R(mmean("ff_long")))
    cli = R(mlast("cli_us"), 3)
    claims = R(mmean("claims"), 2)
    nfci = R(mmean("nfci"), 2)
    hygief = R(mlast("hyg_ief"), 1)
    vix = R(mmean("vix"), 1)
    aaii = R(mmean("aaii"), 2)
    dxy = R(mlast("dxy"), 1)

    comp_common = {}
    meta = {}

    # Bewertung
    z = (cape - cape.rolling(240, min_periods=120).mean()) / cape.rolling(240, min_periods=120).std()
    comp_common["cape_z"] = clip(-z / 2)
    meta["cape_z"] = ("bewertung", "Shiller-KGV ggü. 20-J.-Ø", z, lambda v: f"CAPE {cape.iloc[-1]:.1f} · {v:+.1f} σ")
    ez = (ecy - ecy.rolling(360, min_periods=120).mean()) / ecy.rolling(360, min_periods=120).std()
    comp_common["ecy"] = clip(ez / 2)
    meta["ecy"] = ("bewertung", "Aktien-Risikoprämie (Excess CAPE Yield)", ecy, lambda v: f"{v:.2f} % (Gewinnrendite minus Realzins)")

    # Konjunktur
    u3 = unemp.rolling(3).mean()
    sahm = u3 - u3.shift(1).rolling(12).min()
    comp_common["sahm"] = interp(sahm, [0.1, 0.3, 0.5], [0.5, 0.0, -1.0])
    meta["sahm"] = ("konjunktur", "Sahm-Regel (Arbeitsmarkt)", sahm, lambda v: f"{v:.2f} (Rezessionssignal ab 0,5)")
    curve = y10 - tbill
    inv24 = (curve < 0).astype(float).rolling(24, min_periods=1).max().astype(bool)
    cs = interp(curve, [0, 1, 2], [0.0, 0.3, 0.5])
    cs = cs.where(~(inv24 & (curve >= 0)), -1.0).where(~(curve < 0), -0.5)
    cs[curve.isna()] = np.nan
    comp_common["curve"] = cs
    meta["curve"] = ("konjunktur", "Zinskurve 10J − 3M", curve,
                     lambda v: f"{v:+.2f} Pp." + (" · invertiert" if v < 0 else " · nach Inversion wieder steil" if bool(inv24.iloc[-1]) else ""))
    clich = cli - cli.shift(6)
    comp_common["cli"] = clip(clich / 1.0)
    meta["cli"] = ("konjunktur", "OECD-Frühindikator USA (6 M.)", clich, lambda v: f"{v:+.2f} Pkt. in 6 Monaten")
    cy = claims / claims.shift(12) - 1
    comp_common["claims"] = interp(cy, [-0.1, 0.0, 0.2], [0.5, 0.0, -1.0])
    meta["claims"] = ("konjunktur", "Erstanträge Arbeitslosenhilfe (ggü. Vorjahr)", cy * 100, lambda v: f"{v:+.0f} %")

    # Finanzbedingungen
    nf = 0.5 * clip(-nfci / 0.5) + 0.5 * clip(-(nfci - nfci.shift(3)) / 0.2)
    comp_common["nfci"] = nf
    meta["nfci"] = ("finanzen", "Finanzbedingungen (NFCI)", nfci, lambda v: f"{v:+.2f} (unter 0 = lockerer als üblich)")
    hd = hygief / hygief.rolling(10, min_periods=8).mean() - 1
    comp_common["credit"] = clip(hd / 0.02)
    meta["credit"] = ("finanzen", "Kreditappetit (HYG/IEF ggü. 10-M.-Linie)", hd * 100, lambda v: f"{v:+.1f} %")
    ffc = ff - ff.shift(12)
    comp_common["fed"] = interp(ffc, [-1.0, 0.0, 1.5], [0.25, 0.0, -0.5])
    meta["fed"] = ("finanzen", "Fed-Kurs (Leitzins ggü. Vorjahr)", ffc, lambda v: f"{v:+.2f} Pp.")
    dch = dxy / dxy.shift(12) - 1
    comp_common["dollar"] = clip(-dch / 0.10) * 0.5
    meta["dollar"] = ("finanzen", "Dollar (ggü. Vorjahr)", dch * 100, lambda v: f"{v:+.1f} %")

    # Stimmung
    comp_common["vix"] = interp(vix, [12, 20, 30, 40], [-0.3, 0.0, 0.4, 0.8])
    meta["vix"] = ("stimmung", "Angst (VIX, Monats-Ø)", vix, lambda v: f"{v:.1f}")
    comp_common["aaii"] = interp(aaii, [-20, 7, 35], [0.8, 0.0, -0.6])
    meta["aaii"] = ("stimmung", "Anlegerumfrage AAII (Bullen − Bären)", aaii, lambda v: f"{v:+.0f} Pp.")

    targets = {}
    for key, (sid, tname) in TARGETS.items():
        P = R(mlast(sid), 0)
        if P.notna().sum() < 120:
            continue
        comp = dict(comp_common)
        m2 = dict(meta)
        sma10 = P.rolling(10, min_periods=10).mean()
        d10 = P / sma10 - 1
        comp["sma10"] = clip(d10 / 0.05)
        m2["sma10"] = ("trend", f"{tname} ggü. 10-Monats-Linie", d10 * 100, lambda v: f"{v:+.1f} %")
        mom = P / P.shift(12) - 1 - tbill.fillna(0) / 100
        comp["mom12"] = clip(mom / 0.15)
        m2["mom12"] = ("trend", "12-Monats-Momentum (über Geldmarktzins)", mom * 100, lambda v: f"{v:+.1f} %")
        dd = P / P.rolling(12, min_periods=1).max() - 1
        comp["dd"] = interp(dd, [-0.25, -0.10, 0.0], [1.0, 0.4, 0.0])
        m2["dd"] = ("stimmung", "Abstand vom 12-Monats-Hoch", dd * 100, lambda v: f"{v:+.1f} %")

        C = pd.DataFrame(comp)
        pillars = {}
        for p in WEIGHTS:
            cols = [c for c in C.columns if m2[c][0] == p]
            pillars[p] = C[cols].mean(axis=1, skipna=True)
        Pl = pd.DataFrame(pillars)
        avail = Pl.notna()
        w = pd.Series(WEIGHTS)
        wsum = avail.mul(w, axis=1).sum(axis=1)
        total = Pl.fillna(0).mul(w, axis=1).sum(axis=1) / wsum.replace(0, np.nan)
        ok = (avail.sum(axis=1) >= 3) & P.notna() & avail["trend"]
        score = (50 + 50 * total).where(ok).round(1)

        # ---------- Rückblick
        fw = {}
        for h in (12, 36, 60):
            f = P.shift(-h) / P - 1
            fw[h] = f if h == 12 else (1 + f) ** (12 / h) - 1
        fut_min = pd.concat([P.shift(-i) for i in range(1, 13)], axis=1).min(axis=1)
        mdd12 = fut_min / P - 1
        df = pd.DataFrame({"s": score, "f12": fw[12], "f36": fw[36], "f60": fw[60], "dd": mdd12}).dropna(subset=["s"])
        bt_start = df.index.min()
        bands = []
        for lo, hi, name in BANDS:
            g = df[(df.s >= lo) & (df.s < hi)]
            g12 = g.dropna(subset=["f12"])
            bands.append({
                "band": name, "lo": lo, "hi": hi, "n": int(len(g12)), "share": round(len(g) / max(1, len(df)) * 100, 1),
                "f12": None if not len(g12) else round(float(g12.f12.median() * 100), 1),
                "pos12": None if not len(g12) else round(float((g12.f12 > 0).mean() * 100), 0),
                "worst12": None if not len(g12) else round(float(g12.f12.min() * 100), 0),
                "f36": None if g.f36.dropna().empty else round(float(g.f36.dropna().median() * 100), 1),
                "f60": None if g.f60.dropna().empty else round(float(g.f60.dropna().median() * 100), 1),
                "dd12": None if not len(g12) else round(float(g12.dd.median() * 100), 1),
            })
        def sp(a, b):
            x = pd.concat([a, b], axis=1).dropna()
            return None if len(x) < 60 else round(float(x.iloc[:, 0].corr(x.iloc[:, 1], method="spearman")), 2)
        rank = {"score_f12": sp(df.s, df.f12), "score_f36": sp(df.s, df.f36), "score_f60": sp(df.s, df.f60),
                "pillars": {p: {"f12": sp(Pl[p].reindex(df.index), df.f12), "f36": sp(Pl[p].reindex(df.index), df.f36)} for p in WEIGHTS}}
        base = {"f12": round(float(df.f12.dropna().median() * 100), 1), "pos12": round(float((df.f12.dropna() > 0).mean() * 100), 0),
                "f36": round(float(df.f36.dropna().median() * 100), 1)}

        # ---------- Strategien (monatlich, Kassenanteil verzinst mit T-Bill)
        r = P / P.shift(1) - 1
        cash = (tbill.ffill() / 100 / 12).reindex(idx)
        sidx = df.index
        def strat(expo):
            e = expo.shift(1).reindex(sidx).fillna(0)
            ret = e * r.reindex(sidx) + (1 - e) * cash.reindex(sidx).fillna(0)
            ret = ret.dropna()
            eq = (1 + ret).cumprod()
            yrs = len(ret) / 12
            cagr = eq.iloc[-1] ** (1 / yrs) - 1
            mdd = (eq / eq.cummax() - 1).min()
            vol = ret.std() * math.sqrt(12)
            return {"cagr": round(cagr * 100, 1), "mdd": round(mdd * 100, 0), "vol": round(vol * 100, 1),
                    "expo": round(float(e.mean() * 100), 0), "eq": eq}
        S_bh = strat(pd.Series(1.0, index=idx))
        S_tr = strat((P > sma10).astype(float))
        S_sc = strat(((score - 50) / 30 + 0.5).clip(0, 1))
        def eqser(s):
            e = s.pop("eq")
            step = 1
            return [round(float(v), 4) for v in e.values[::step]]
        strategies = [
            {"id": "bh", "name": "Kaufen und halten", "desc": "immer 100 % investiert", **{k: v for k, v in S_bh.items() if k != "eq"}, "eq": eqser(S_bh)},
            {"id": "trend", "name": "Trendregel 10 Monate", "desc": "investiert, wenn der Kurs über seiner 10-Monats-Linie schließt, sonst Geldmarkt", **{k: v for k, v in S_tr.items() if k != "eq"}, "eq": eqser(S_tr)},
            {"id": "score", "name": "Modell-Quote", "desc": "Score 50 = 50 % investiert, ab 65 = 100 %, bis 35 = 0 %; Rest Geldmarkt", **{k: v for k, v in S_sc.items() if k != "eq"}, "eq": eqser(S_sc)},
        ]

        # ---------- aktueller Stand
        last_i = score.last_valid_index()
        now_score = None if last_i is None else float(score[last_i])
        lab = label(now_score)
        pil_now = []
        for p in WEIGHTS:
            comps = []
            for c in C.columns:
                if m2[c][0] != p:
                    continue
                val_s = m2[c][2]
                v = val_s.loc[:last_i].dropna()
                sc = C[c].loc[:last_i].dropna()
                if not len(sc):
                    comps.append({"id": c, "name": m2[c][1], "text": "keine Daten", "score": None})
                    continue
                vv = float(v.iloc[-1]) if len(v) else None
                try:
                    txt = m2[c][3](vv) if vv is not None else ""
                except Exception:  # noqa
                    txt = ""
                comps.append({"id": c, "name": m2[c][1], "text": txt, "score": round(float(sc.iloc[-1]), 2),
                              "asof": str(sc.index[-1])})
            pv = Pl[p].loc[:last_i].dropna()
            pil_now.append({"id": p, "name": PILLAR_NAMES[p], "weight": WEIGHTS[p],
                            "score": None if not len(pv) else round(float(50 + 50 * pv.iloc[-1]), 0), "comps": comps})

        # Klartext
        def word(s):
            return "stark positiv" if s >= 70 else "positiv" if s >= 58 else "neutral" if s > 42 else "negativ" if s > 30 else "stark negativ"
        pos = [x for x in pil_now if x["score"] is not None and x["score"] >= 58]
        neg = [x for x in pil_now if x["score"] is not None and x["score"] <= 42]
        sent = []
        sent.append(f"Der Gesamtscore für den {tname} liegt bei {now_score:.0f} von 100 – {lab[0].lower()}.")
        if pos:
            sent.append("Dafür spricht: " + ", ".join(f"{x['name']} ({word(x['score'])})" for x in pos) + ".")
        if neg:
            sent.append("Dagegen spricht: " + ", ".join(f"{x['name']} ({word(x['score'])})" for x in neg) + ".")
        b = next((x for x in bands if x["lo"] <= now_score < x["hi"]), None)
        if b and b["n"]:
            sent.append(f"Seit {bt_start.year} lag der Score in {b['n']} Monaten in diesem Bereich ({b['band']}). "
                        f"Ein Jahr später stand der {tname} im Median {b['f12']:+.1f} % (alle Monate: {base['f12']:+.1f} %), "
                        f"in {b['pos12']:.0f} % der Fälle im Plus; der schlechteste Fall war {b['worst12']:+.0f} %.")
        rc = rank["score_f12"]
        if rc is not None:
            q = "kaum" if abs(rc) < 0.1 else "schwach" if abs(rc) < 0.2 else "spürbar" if abs(rc) < 0.35 else "deutlich"
            sent.append(f"Wie gut der Score bisher war: Er hing {q} mit der Rendite der folgenden 12 Monate zusammen "
                        f"(Rangkorrelation {rc:+.2f}; über 5 Jahre {rank['score_f60']:+.2f}).")

        hist_idx = score.dropna().index
        targets[key] = {
            "name": tname,
            "now": {"score": None if now_score is None else round(now_score), "month": str(last_i), "label": lab[0],
                    "cls": lab[1], "action": lab[2], "pillars": pil_now, "text": sent},
            "hist": {"months": [str(p) for p in hist_idx], "score": score[hist_idx].tolist(),
                     "price": [None if pd.isna(x) else round(float(x), 2) for x in P[hist_idx].values],
                     "pillars": {p: [None if pd.isna(x) else round(float(50 + 50 * x), 1) for x in Pl[p][hist_idx].values] for p in WEIGHTS}},
            "bands": bands, "base": base, "rank": rank, "since": str(bt_start),
            "strategies": strategies, "strat_months": [str(p) for p in sidx][:len(strategies[0]["eq"])],
        }

    # ---------- Sebas eigene Regel (200-Wochen-Linie + CAPE-Wende)
    rule = {}
    for key, sid in (("spx", "spx"), ("world", "msci")):
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
            "note": "Kursrenditen ohne Dividenden. Konjunkturdaten in heutiger (revidierter) Fassung. Kein Anlagerat – ein Regelmodell."}
