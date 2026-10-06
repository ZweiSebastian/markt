"""
Einschätzungs-Modell für das Markt Terminal – Tagesbasis.

Jeder Börsentag bekommt einen Score (0–100) und eine Wahrscheinlichkeit für einen Rückgang von mindestens
15 % innerhalb der folgenden 12 Monate. Gerechnet wird nur mit dem, was an diesem Tag tatsächlich bekannt war:
Monatsdaten erscheinen erst mit ihrer üblichen Veröffentlichungsverzögerung (z. B. Inflation ~6 Wochen nach
Monatsbeginn, Gewinne ~5 Monate), der Stellenaufbau kommt – wo vorhanden – aus dem Echtzeit-Datensatz der
Philadelphia Fed (so, wie er damals veröffentlicht war).

Acht Säulen (Gewichte): Bewertung 15 %, Gewinne 10 %, Trend 20 %, Schwankung 10 %, Marktbreite 10 %,
Konjunktur 15 %, Finanzbedingungen 10 %, Stimmung 10 %. Jede Komponente wird nach fester, vorab gewählter Regel
auf −1 … +1 abgebildet (keine Optimierung auf die Vergangenheit). Score = 50 + 15 × Gesamtwert / bisherige
Streuung (nur Vergangenheit).

Regionen: USA und Welt nutzen US-Daten (Welt zusätzlich G7-Frühindikator); Europa, Japan und Schwellenländer
haben eigene Konjunktur- und Zinsdaten (OECD, EZB, EU-Kommission) und eine Bewertungs-Näherung
(Kurs ggü. 10-Jahres-Durchschnitt), weil es für sie kein frei verfügbares Shiller-KGV gibt.

Wahrscheinlichkeit: logistische Regression auf die acht Säulen, Jahr für Jahr nur mit Daten trainiert, deren
Ausgang zum jeweiligen Zeitpunkt schon bekannt war (Walk-forward), und so außerhalb der Stichprobe geprüft.
"""
import math
import re

import numpy as np
import pandas as pd

try:
    import signals as sig
except Exception:  # noqa
    sig = None

WEIGHTS = {"bewertung": 0.15, "gewinne": 0.10, "trend": 0.20, "schwankung": 0.10, "breite": 0.10,
           "konjunktur": 0.15, "finanzen": 0.10, "stimmung": 0.10}
PILLARS = list(WEIGHTS)
PILLAR_NAMES = {"bewertung": "Bewertung", "gewinne": "Gewinne", "trend": "Trend", "schwankung": "Schwankung",
                "breite": "Marktbreite", "konjunktur": "Konjunktur", "finanzen": "Finanzbedingungen",
                "stimmung": "Stimmung (konträr)"}
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
CRASH = 0.15
PROB_MODE = "score_fb_g7"  # Score + Auslandskäufe US-Aktien + G7-Zinsanstieg bei hoher Bewertung (beides vorwärts getestet). Richtung (score_dir, …) brachte nichts
STRAT_FREQ = "M"       # Entscheidungsrhythmus der Regeln im Test: letzter Handelstag des Monats (getestet: besser als wöchentlich)
TREND_N = 210          # Trendlinie in Börsentagen (210 ≈ 10 Monate)
# Ungefähre Dividendenrendite p.a. für die 2x-Rechnung (Kursindizes); DAX und MSCI World in Euro enthalten Dividenden bereits
DIV_YIELD = {"world": 0.023, "world_eur": 0.0, "spx": 0.02, "ndx": 0.009, "rut": 0.014, "sx5e": 0.033, "dax": 0.0, "nikkei": 0.018, "em": 0.026}
PROB_LAM = 1.0
FBUY_MODE = "on"      # Auslandskäufe US-Aktien in der Säule Stimmung
FBUY_ALL = False
FBUY_DIV = 2.0
G7_CAPE_Z = 1.0     # G7-Zinsanstieg zählt nur bei US-Bewertung über +1σ
DIR_N = 63             # Richtung des Scores: Veränderung über 3 Monate (63 Börsentage)
POOL_MIN_YEARS = 40     # kürzere Historien nutzen das am S&P 500 gelernte Modell
EPISODE = 0.20
Y = 252            # Börsentage pro Jahr
MON = 21
MONTHS = ["Jan.", "Feb.", "März", "Apr.", "Mai", "Juni", "Juli", "Aug.", "Sep.", "Okt.", "Nov.", "Dez."]


def clip(x, lo=-1.0, hi=1.0):
    return x.clip(lo, hi)


def interp(x, xs, ys):
    v = x.values.astype(float)
    out = np.interp(v, xs, ys)
    return pd.Series(np.where(np.isnan(v), np.nan, out), index=x.index)


def label(score):
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


def dname(d):
    return f"{d.day}. {MONTHS[d.month - 1]} {d.year}"


def mname(d):
    return f"{MONTHS[d.month - 1]} {d.year}"


def fit_logit(X, y, lam=3.0, iters=30):
    """Ridge-logistische Regression (IRLS), Achsenabschnitt ungestraft."""
    n, k = X.shape
    w = np.zeros(k)
    pen = np.full(k, lam)
    pen[0] = 0.0
    for _ in range(iters):
        z = np.clip(X @ w, -30, 30)
        p = 1 / (1 + np.exp(-z))
        W = p * (1 - p) + 1e-9
        H = (X * W[:, None]).T @ X + np.diag(pen)
        g = X.T @ (p - y) + pen * w
        step = np.linalg.solve(H, g)
        w -= step
        if np.abs(step).max() < 1e-7:
            break
    return w


def run(ser, markt, now, quality=None, prev=None):
    today = pd.Timestamp(now.date())
    days = pd.bdate_range("1950-01-02", today)

    # ---------- Hilfen: Daten auf das Tagesraster bringen
    def D(sid, limit=7):
        s = ser(sid)
        if s is None or not len(s):
            return pd.Series(np.nan, index=days)
        s = s[~s.index.duplicated(keep="last")].sort_index()
        return s.reindex(days.union(s.index)).ffill(limit=limit).reindex(days)

    def place(s, lag, max_age=120):
        """Monats-/Wochenwerte ab ihrem Veröffentlichungstag (Index + lag Tage) gelten lassen, höchstens max_age Tage."""
        if s is None or not len(s.dropna()):
            return pd.Series(np.nan, index=days)
        s = s.dropna().copy()
        s.index = pd.to_datetime(s.index) + pd.Timedelta(days=lag)
        s = s[~s.index.duplicated(keep="last")].sort_index()
        return s.reindex(days, method="ffill", tolerance=pd.Timedelta(days=max_age))

    def monthly(sid, how="last"):
        s = ser(sid)
        if s is None or not len(s):
            return None
        g = s.groupby(s.index.to_period("M"))
        m = g.last() if how == "last" else g.mean()
        m.index = m.index.to_timestamp()
        return m

    def weekly(sid):
        s = ser(sid)
        if s is None or not len(s):
            return None
        return s.dropna()

    # ---------- Eingänge
    tb_d = D("y3m")
    tbill = tb_d.where(tb_d.notna(), place(monthly("tbill_m"), 31, 70)).ffill(limit=10)
    y10 = D("y10")
    y10 = y10.where(y10.notna(), place(monthly("y10_m"), 31, 70))
    vix = D("vix")
    vix21 = vix.rolling(MON, min_periods=15).mean()
    dxy = D("dxy")
    gold, copper = D("gold"), D("copper")

    def cape_daily():
        c_m = place(monthly("cape_long"), 31, 70)
        c_d = D("cape")
        return c_d.where(c_d.notna(), c_m)
    cape = cape_daily()

    def foreign_buying():
        fl, gd = ser("row_eq_flow"), ser("gdp_z1")
        if fl is None or gd is None or len(fl) < 60:
            return None
        fl, gd = fl.sort_index(), gd.sort_index()
        fq = (fl.rolling(4).mean() / gd.rolling(4).mean() * 100).dropna()
        fq.index = fq.index.to_period("Q").to_timestamp(how="end").normalize()   # Quartalsende, egal wie die Quelle datiert
        fz = (fq - fq.rolling(40, min_periods=20).mean()) / fq.rolling(40, min_periods=20).std()
        return place(fz, 95, 200), place(fq, 95, 200)   # Z.1 erscheint ~10–11 Wochen nach Quartalsende
    fbz = foreign_buying()

    def g7_rates():
        """Lange Zinsen der G7: mittlerer Anstieg in 12 Monaten – zählt nur, wenn die US-Bewertung > 1σ über dem 20-J.-Schnitt liegt."""
        ms = {}
        for k in ("usa", "jpn", "can", "deu", "fra", "gbr", "ita"):
            x = ser("lt10_" + k)
            if x is not None and len(x) > 60:
                x = x.sort_index()
                x.index = x.index.to_period("M").to_timestamp()
                ms[k] = x[~x.index.duplicated(keep="last")]
        if len(ms) < 5:
            return None
        Ym = pd.DataFrame(ms)
        d12 = Ym - Ym.shift(12)
        avg = d12.mean(axis=1).where(d12.notna().sum(axis=1) >= 5).dropna()
        gz = (avg - avg.expanding(60).mean()) / avg.expanding(60).std()
        czd = (cape - cape.rolling(20 * Y, min_periods=10 * Y).mean()) / cape.rolling(20 * Y, min_periods=10 * Y).std()
        gzp = place(gz, 33, 75)                  # Monatsdurchschnitt gilt ab kurz nach Monatsende
        feat = (gzp * (czd > G7_CAPE_Z).astype(float)).where(czd.notna())
        last = d12.dropna(how="all").iloc[-1]
        info = {"avg": None if not len(avg) else round(float(avg.iloc[-1]), 2), "month": None if not len(avg) else str(avg.index[-1].date())[:7],
                "z": None if not len(gz) else round(float(gz.iloc[-1]), 2), "cape_z": round(float(czd.dropna().iloc[-1]), 2),
                "countries": {k: round(float(v), 2) for k, v in last.dropna().items()},
                "active": bool(len(gz) and czd.dropna().iloc[-1] > G7_CAPE_Z and gz.iloc[-1] >= 1)}
        return feat, info
    g7 = g7_rates()

    # ---------- Komponenten-Bausteine (je Region zusammengestellt)
    def comp_us_valuation(C):
        z = (cape - cape.rolling(20 * Y, min_periods=10 * Y).mean()) / cape.rolling(20 * Y, min_periods=10 * Y).std()
        C["cape_z"] = ("bewertung", "Shiller-KGV ggü. 20-J.-Ø (USA)", clip(-z / 2), z, lambda v: f"CAPE {cape.dropna().iloc[-1]:.1f} · {v:+.1f} σ")
        ecy = place(monthly("ecy"), 45, 80)
        ez = (ecy - ecy.rolling(30 * Y, min_periods=10 * Y).mean()) / ecy.rolling(30 * Y, min_periods=10 * Y).std()
        C["ecy"] = ("bewertung", "Aktien-Risikoprämie (Excess CAPE Yield)", clip(ez / 2), ecy, lambda v: f"{v:.2f} % (Gewinnrendite minus Realzins)")
        return z

    def comp_proxy_valuation(C, P):
        d = P / P.rolling(10 * Y, min_periods=8 * Y).mean() - 1
        C["val10"] = ("bewertung", "Kurs ggü. 10-Jahres-Durchschnitt (Näherung)", interp(d, [0.0, 0.4, 0.8], [0.5, 0.0, -1.0]), d * 100,
                      lambda v: f"{v:+.0f} % (kein Shiller-KGV verfügbar)")
        return d / 0.4

    def comp_earnings(C):
        eps = monthly("eps")
        if eps is not None:
            eg = place(eps / eps.shift(12) - 1, 150, 200)
            C["eps_g"] = ("gewinne", "Gewinnwachstum S&P 500 (12 M., Shiller)", interp(eg, [-0.2, 0.0, 0.15], [-1.0, 0.0, 0.5]), eg * 100,
                          lambda v: f"{v:+.0f} % ggü. Vorjahr (Stand mit ~5 Monaten Verzögerung)")

    def comp_quality(C):
        q = quality_score()
        if q is None:
            return
        s = pd.Series(np.nan, index=days)
        s.iloc[-1] = q["score"]
        raw = pd.Series(np.nan, index=days)
        raw.iloc[-1] = q["score"]
        C["quality"] = ("gewinne", "Gewinnqualität der 10 Schwergewichte", s, raw, lambda v: q["text"])

    def comp_us_macro(C, extra_g7=False):
        unemp = monthly("unemp")
        if unemp is not None:
            u3 = unemp.rolling(3).mean()
            sahm = place(u3 - u3.shift(1).rolling(12).min(), 35, 70)
            C["sahm"] = ("konjunktur", "Sahm-Regel (Arbeitsmarkt USA)", interp(sahm, [0.1, 0.3, 0.5], [0.5, 0.0, -1.0]), sahm,
                         lambda v: f"{v:.2f} (Rezessionssignal ab 0,5)")
        curve = y10 - tbill
        inv = (curve < 0).astype(float).rolling(2 * Y, min_periods=1).max().astype(bool)
        cs = interp(curve, [0, 1, 2], [0.0, 0.3, 0.5])
        cs = cs.where(~(inv & (curve >= 0)), -1.0).where(~(curve < 0), -0.5)
        cs[curve.isna()] = np.nan
        C["curve"] = ("konjunktur", "Zinskurve 10J − 3M (USA)", cs, curve,
                      lambda v: f"{v:+.2f} Pp." + (" · invertiert" if v < 0 else " · nach Inversion wieder steil" if bool(inv.iloc[-1]) else ""))
        cli = monthly("cli_us")
        if cli is not None:
            ch = place(cli - cli.shift(6), 70, 100)
            C["cli"] = ("konjunktur", "OECD-Frühindikator USA (6 M.)", clip(ch / 1.0), ch, lambda v: f"{v:+.2f} Pkt. in 6 Monaten")
        if extra_g7:
            g7 = monthly("cli_g7")
            if g7 is not None:
                ch = place(g7 - g7.shift(6), 70, 100)
                C["cli_g7"] = ("konjunktur", "OECD-Frühindikator G7 (6 M.)", clip(ch / 1.0), ch, lambda v: f"{v:+.2f} Pkt. in 6 Monaten")
        cl = weekly("claims")
        if cl is not None:
            cy = place(cl / cl.shift(52) - 1, 5, 21)
            C["claims"] = ("konjunktur", "Erstanträge Arbeitslosenhilfe (ggü. Vorjahr)", interp(cy, [-0.1, 0.0, 0.2], [0.5, 0.0, -1.0]), cy * 100,
                           lambda v: f"{v:+.0f} %")
        prt = monthly("payrolls_rt")
        pr = monthly("payrolls")
        p3 = None
        if pr is not None:
            p3 = place(pr.rolling(3).mean(), 35, 70)
        if prt is not None:
            p3rt = place(prt, 7, 70)
            p3 = p3rt if p3 is None else p3rt.where(p3rt.notna(), p3)
        if p3 is not None:
            C["payrolls"] = ("konjunktur", "Stellenaufbau USA (3-M.-Ø, wie veröffentlicht)", interp(p3, [-50, 0, 100, 250], [-1.0, -0.5, 0.0, 0.3]), p3,
                             lambda v: f"{v:+.0f} Tsd. pro Monat")
        cpi = monthly("cpi")
        if cpi is not None:
            ci = place(cpi - cpi.shift(6), 45, 80)
            C["infl"] = ("konjunktur", "Inflationstrend USA (6 M.)", clip(-ci / 1.5) * 0.6, ci, lambda v: f"{v:+.1f} Pp. (Inflation ggü. Vorjahr)")
        wd = D("wti")
        wm = place(monthly("wti_long", "mean"), 31, 70)
        wy = (wd / wd.shift(Y) - 1)
        wy = wy.where(wy.notna(), wm / wm.shift(Y) - 1)
        C["oil"] = ("konjunktur", "Ölpreis ggü. Vorjahr", interp(wy, [0.2, 0.5, 1.0], [0.0, -0.6, -1.0]), wy * 100, lambda v: f"{v:+.0f} %")

    def comp_region_macro(C, cli_id, cli_name, unemp_id, curve_id, region_name, esi=False, infl_id=None):
        cli = monthly(cli_id)
        if cli is not None:
            ch = place(cli - cli.shift(6), 70, 100)
            C["cli_r"] = ("konjunktur", f"{cli_name} (6 M.)", clip(ch / 1.0), ch, lambda v: f"{v:+.2f} Pkt. in 6 Monaten")
        if unemp_id:
            un = monthly(unemp_id)
            if un is not None:
                u3 = un.rolling(3).mean()
                sh = place(u3 - u3.shift(1).rolling(12).min(), 60, 100)
                C["sahm_r"] = ("konjunktur", f"Arbeitsmarkt {region_name} (Sahm-Regel)", interp(sh, [0.1, 0.3, 0.5], [0.5, 0.0, -1.0]), sh,
                               lambda v: f"{v:.2f} (Signal ab 0,5)")
        if curve_id:
            cv = monthly(curve_id)
            if cv is not None:
                c = place(cv, 31, 70)
                inv = (c < 0).astype(float).rolling(2 * Y, min_periods=1).max().astype(bool)
                cs = interp(c, [0, 1, 2], [0.0, 0.3, 0.5])
                cs = cs.where(~(inv & (c >= 0)), -1.0).where(~(c < 0), -0.5)
                cs[c.isna()] = np.nan
                C["curve_r"] = ("konjunktur", f"Zinskurve 10J − 3M {region_name}", cs, c, lambda v: f"{v:+.2f} Pp.")
        if esi:
            e = place(monthly("esi_ea"), 30, 70)
            C["esi"] = ("konjunktur", "Wirtschaftsstimmung Euroraum (ESI)", interp(e, [90, 100, 108], [-1.0, 0.0, 0.4]), e, lambda v: f"{v:.1f} (100 = langjähriger Schnitt)")
        if infl_id:
            h = monthly(infl_id)
            if h is not None:
                ci = place(h - h.shift(6), 47, 80)
                C["infl_r"] = ("konjunktur", f"Inflationstrend {region_name} (6 M.)", clip(-ci / 1.5) * 0.6, ci, lambda v: f"{v:+.1f} Pp.")

    def comp_finance_global(C, us=True):
        bs = monthly("baa_spread")
        if bs is not None:
            b = place(bs, 31, 70)
            bmed = b.rolling(10 * Y, min_periods=5 * Y).median()
            C["baa"] = ("finanzen", "Kreditaufschlag Baa − 10J", 0.5 * clip(-(b - bmed) / 1.0) + 0.5 * clip(-(b - b.shift(126)) / 0.5), b,
                        lambda v: f"{v:.2f} Pp.")
        nf = weekly("nfci")
        if nf is not None:
            n = place(nf, 5, 21)
            C["nfci"] = ("finanzen", "Finanzbedingungen (NFCI)", 0.5 * clip(-n / 0.5) + 0.5 * clip(-(n - n.shift(63)) / 0.2), n,
                         lambda v: f"{v:+.2f} (unter 0 = lockerer als üblich)")
        hy = D("vwehx")
        hf = hy / hy.rolling(210, min_periods=200).mean() - 1
        C["hyfund"] = ("finanzen", "Hochzinsanleihen im Trend (Fonds seit 1978)", clip(hf / 0.015), hf * 100, lambda v: f"{v:+.1f} % ggü. 10-Monats-Linie")
        hi = D("hyg_ief")
        hd = hi / hi.rolling(210, min_periods=170).mean() - 1
        C["credit"] = ("finanzen", "Kreditappetit (HYG/IEF ggü. 10-M.-Linie)", clip(hd / 0.02), hd * 100, lambda v: f"{v:+.1f} %")
        if us:
            ff = D("effr")
            ff = ff.where(ff.notna(), D("ff_long"))
            ffc = ff - ff.shift(Y)
            C["fed"] = ("finanzen", "Fed-Kurs (Leitzins ggü. Vorjahr)", interp(ffc, [-1.0, 0.0, 1.5], [0.25, 0.0, -0.5]), ffc, lambda v: f"{v:+.2f} Pp.")
            mo = weekly("mort30")
            if mo is not None:
                m_ = place(mo, 0, 14)
                mc = m_ - m_.shift(2 * Y)
                C["mort"] = ("finanzen", "Hypothekenzins USA (2 J.)", interp(mc, [-1.0, 0.0, 1.0, 2.5], [0.3, 0.0, -0.4, -1.0]), mc, lambda v: f"{v:+.2f} Pp.")
            dch = dxy / dxy.shift(Y) - 1
            C["dollar"] = ("finanzen", "Dollar (ggü. Vorjahr)", clip(-dch / 0.10) * 0.5, dch * 100, lambda v: f"{v:+.1f} %")

    def comp_breadth(C, us=True):
        if us:
            sect = D("sect_part")
            C["sect"] = ("breite", "US-Sektoren im Aufwärtstrend", interp(sect, [20, 50, 80], [-1.0, 0.0, 0.6]), sect,
                         lambda v: f"{v:.0f} % der 11 Sektoren über ihrer 200-Tage-Linie")
            ew = D("breadth")
            ed = ew / ew.rolling(210, min_periods=170).mean() - 1
            C["ewcap"] = ("breite", "Gleichgewichtet vs. kapitalgewichtet (RSP/SPY)", clip(ed / 0.03), ed * 100, lambda v: f"{v:+.1f} % ggü. 10-Monats-Linie")
            sl_ = D("small_large")
            sl = sl_ / sl_.shift(126) - 1
            C["smlg"] = ("breite", "Nebenwerte vs. Standardwerte (6 M.)", clip(sl / 0.10) * 0.6, sl * 100, lambda v: f"{v:+.1f} %")
        wp = D("world_part")
        C["wpart"] = ("breite", "Weltbörsen im Aufwärtstrend", interp(wp, [20, 50, 80], [-1.0, 0.0, 0.6]), wp,
                      lambda v: f"{v:.0f} % von 9 großen Indizes über ihrer 200-Tage-Linie")

    def comp_sentiment(C, us=True):
        C["vix"] = ("stimmung", "Angst (VIX, 1-M.-Ø)", interp(vix21, [12, 20, 30, 40], [-0.3, 0.0, 0.4, 0.8]), vix21, lambda v: f"{v:.1f}")
        if us:
            aa = weekly("aaii")
            if aa is not None:
                a = place(aa, 1, 21)
                C["aaii"] = ("stimmung", "Anlegerumfrage AAII (Bullen − Bären)", interp(a, [-20, 7, 35], [0.8, 0.0, -0.6]), a, lambda v: f"{v:+.0f} Pp.")
        if (us or FBUY_ALL) and FBUY_MODE != "off" and fbz is not None:
            # Käufe ausländischer Anleger von US-Aktien (Fed Z.1, Quartal, SAAR) – 4 Quartale, in % des BIP,
            # ggü. den letzten 10 Jahren. Hoch = spätzyklisch (konträr). Veröffentlichung ~10 Wochen nach Quartalsende.
            zp, fp = fbz
            C["fbuy"] = ("stimmung", "Auslandskäufe US-Aktien (4 Quartale, % des BIP)", clip(-zp / FBUY_DIV), fp,
                         lambda v: f"{v:.2f} % des BIP · {zp.dropna().iloc[-1]:+.1f} σ ggü. 10 Jahren")

    def comp_vixterm(C):
        vt = D("vix_term")
        C["vix_term"] = ("schwankung", "VIX-Kurve (1 Monat / 3 Monate)", interp(vt, [0.85, 1.0, 1.15], [0.2, 0.0, -1.0]), vt,
                         lambda v: f"{v:.2f} (über 1 = akuter Stress)")

    # ---------- Gewinnqualität (aktueller Stand, Yahoo-Bilanzen)
    _q_cache = {}

    def quality_score():
        if "q" in _q_cache:
            return _q_cache["q"]
        if not quality or not quality.get("companies"):
            _q_cache["q"] = None
            return None
        rows, tot_w = [], 0.0
        agg = {"cc": 0.0, "rec": 0.0, "capex": 0.0, "inv": 0.0, "fin": 0.0, "nonop": 0.0}
        wsum = {k: 0.0 for k in agg}
        flags = []
        for c in quality["companies"]:
            w = c.get("mc") or 1e11
            sc = {}
            if c.get("cash_op") is not None:          # operativer Cashflow ÷ operativer Gewinn (normal ~1,0–1,3)
                sc["cc"] = float(np.interp(c["cash_op"], [0.7, 1.0, 1.2], [-1.0, 0.0, 0.3]))
            elif c.get("cash_conv") is not None:
                sc["cc"] = float(np.interp(c["cash_conv"], [0.6, 0.9, 1.1], [-1.0, 0.0, 0.3]))
            if c.get("fin_ocf") is not None:          # neue Schulden + neue Aktien im Verhältnis zum Cashflow
                sc["fin"] = float(np.interp(c["fin_ocf"], [0.0, 0.25, 0.8], [0.2, 0.0, -1.0]))
                if c["fin_ocf"] > 0.4:
                    flags.append(f"{c['t']}: braucht frisches Geld – {c.get('debt_iss', 0):.0f} Mrd. $ neue Schulden und {c.get('eq_iss', 0):.0f} Mrd. $ neue Aktien in 12 Monaten ({c['fin_ocf'] * 100:.0f} % des Cashflows)")
            if c.get("nonop") is not None:            # Anteil des Vorsteuergewinns, der nicht aus dem Geschäft stammt
                sc["nonop"] = float(np.interp(c["nonop"], [0.05, 0.15, 0.5], [0.1, 0.0, -1.0]))
                if c["nonop"] > 0.25:
                    flags.append(f"{c['t']}: {c['nonop'] * 100:.0f} % des Gewinns vor Steuern stammen nicht aus dem Geschäft (u. a. Buchgewinne auf Beteiligungen)")
            if c.get("debt_g") is not None and c["debt_g"] > 0.5:
                flags.append(f"{c['t']}: Schulden +{c['debt_g'] * 100:.0f} % in 12 Monaten (jetzt {c.get('debt') or 0:.0f} Mrd. $)")
            if c.get("rec_g") is not None and c.get("rev_g") is not None:
                gap = c["rec_g"] - c["rev_g"]
                sc["rec"] = float(np.interp(gap, [-0.05, 0.05, 0.25], [0.3, 0.0, -1.0]))
                if gap > 0.15:
                    flags.append(f"{c['t']}: Forderungen +{c['rec_g'] * 100:.0f} % bei Umsatz +{c['rev_g'] * 100:.0f} %")
            if c.get("capex_ocf") is not None:
                sc["capex"] = float(np.interp(c["capex_ocf"], [0.4, 0.6, 0.9], [0.2, 0.0, -1.0]))
                if c["capex_ocf"] > 0.8:
                    flags.append(f"{c['t']}: Investitionen fressen {c['capex_ocf'] * 100:.0f} % des operativen Cashflows")
            if c.get("inv_g") is not None:
                sc["inv"] = float(np.interp(c["inv_g"], [0.0, 0.3, 1.0], [0.0, -0.3, -1.0]))
                if c["inv_g"] > 0.5:
                    flags.append(f"{c['t']}: Beteiligungen/Finanzanlagen +{c['inv_g'] * 100:.0f} % in 12 Monaten")
            if c.get("fcf_op") is not None and c["fcf_op"] < 0.2:
                flags.append(f"{c['t']}: vom operativen Gewinn bleiben nur {c['fcf_op'] * 100:.0f} % als freier Cashflow")
            for k, v in sc.items():
                agg[k] += v * w
                wsum[k] += w
            c2 = dict(c)
            c2["score"] = None if not sc else round(float(np.mean(list(sc.values()))), 2)
            rows.append(c2)
        parts = {k: agg[k] / wsum[k] for k in agg if wsum[k] > 0}
        if not parts:
            _q_cache["q"] = None
            return None
        score = float(np.mean(list(parts.values())))
        names = {"cc": "Gewinn durch Cashflow gedeckt", "rec": "Forderungen vs. Umsatz", "capex": "Investitionen vs. Cashflow", "inv": "Beteiligungen",
                 "fin": "Fremdfinanzierung", "nonop": "Buchgewinne"}
        txt = " · ".join(f"{names[k]} {v:+.2f}" for k, v in parts.items())
        _q_cache["q"] = {"score": score, "parts": {k: round(v, 2) for k, v in parts.items()}, "text": dez(txt), "flags": flags, "companies": rows,
                         "at": quality.get("at")}
        return _q_cache["q"]

    # ---------- je Zielindex
    targets = {}
    sig_params, sig_cal = None, None
    pooled = {}           # Jahr -> Koeffizienten aus dem S&P 500 (längste Historie)
    order_ = ["spx"] + [k for k in TARGETS if k != "spx"]
    for key in order_:
        sid, tname, region = TARGETS[key]
        P = D(sid, limit=5)
        P = P.where(P > 0)
        if P.notna().sum() < 8 * Y:
            continue
        C = {}
        cape_raw = None
        us_like = region in ("USA", "Welt")
        if us_like:
            cape_raw = comp_us_valuation(C)
            comp_earnings(C)
            comp_quality(C)
            comp_us_macro(C, extra_g7=(region == "Welt"))
            comp_finance_global(C, us=True)
            comp_breadth(C, us=True)
            comp_sentiment(C, us=True)
            comp_vixterm(C)
        else:
            cape_raw = comp_proxy_valuation(C, P)
            if region == "Europa":
                if sid == "dax":
                    comp_region_macro(C, "cli_de", "OECD-Frühindikator Deutschland", "unemp_de", "curve_de", "Deutschland", esi=True, infl_id="hicp")
                else:
                    has_ea = ser("cli_ea") is not None
                    comp_region_macro(C, "cli_ea" if has_ea else "cli_de", "OECD-Frühindikator Euroraum" if has_ea else "OECD-Frühindikator Deutschland",
                                      "unemp_ea", "curve_ea", "Euroraum", esi=True, infl_id="hicp")
                ecb = D("ecb")
                ec = ecb - ecb.shift(Y)
                C["ecb"] = ("finanzen", "EZB-Kurs (Einlagenzins ggü. Vorjahr)", interp(ec, [-1.0, 0.0, 1.5], [0.25, 0.0, -0.5]), ec, lambda v: f"{v:+.2f} Pp.")
                eu = D("eurusd")
                eg = eu / eu.shift(Y) - 1
                C["eur"] = ("finanzen", "Euro ggü. Dollar (ggü. Vorjahr)", clip(-eg / 0.12) * 0.4, eg * 100, lambda v: f"{v:+.1f} % (starker Euro bremst Exporteure)")
            elif region == "Japan":
                comp_region_macro(C, "cli_jp", "OECD-Frühindikator Japan", "unemp_jp", "curve_jp", "Japan")
                uj = D("usdjpy")
                jg = uj / uj.shift(Y) - 1
                C["yen"] = ("finanzen", "Yen-Schwäche (USD/JPY ggü. Vorjahr)", clip(jg / 0.12) * 0.5, jg * 100, lambda v: f"{v:+.1f} % (schwacher Yen hilft Exporteuren)")
            else:
                comp_region_macro(C, "cli_cn", "OECD-Frühindikator China", None, None, "China")
                dch = dxy / dxy.shift(Y) - 1
                C["dollar"] = ("finanzen", "Dollar (ggü. Vorjahr)", clip(-dch / 0.08), dch * 100, lambda v: f"{v:+.1f} % (starker Dollar belastet Schwellenländer)")
                cg = copper / copper.shift(Y) - 1
                C["copper"] = ("konjunktur", "Kupfer ggü. Vorjahr", clip(cg / 0.25) * 0.6, cg * 100, lambda v: f"{v:+.0f} %")
            comp_finance_global(C, us=False)
            comp_breadth(C, us=False)
            comp_sentiment(C, us=False)

        # Preisbasierte Komponenten (live in der App nachgerechnet)
        sma210 = P.rolling(TREND_N, min_periods=TREND_N).mean()
        d10 = P / sma210 - 1
        C["sma10"] = ("trend", f"{tname} ggü. 10-Monats-Linie", clip(d10 / 0.05), d10 * 100, lambda v: f"{v:+.1f} %")
        mom = P / P.shift(Y) - 1 - tbill.fillna(0) / 100
        C["mom12"] = ("trend", "12-Monats-Momentum (über Geldmarktzins)", clip(mom / 0.15), mom * 100, lambda v: f"{v:+.1f} %")
        sma1000 = P.rolling(1000, min_periods=1000).mean()
        d200 = P / sma1000 - 1
        C["w200"] = ("trend", "Abstand zur 200-Wochen-Linie", interp(d200, [-0.05, 0.10, 0.30, 0.50], [1.0, 0.3, 0.0, -0.4]), d200 * 100,
                     lambda v: f"{v:+.0f} % (weit darüber = überdehnt)")
        dd = P / P.rolling(Y, min_periods=1).max() - 1
        C["dd"] = ("stimmung", "Abstand vom 12-Monats-Hoch", interp(dd, [-0.25, -0.10, 0.0], [1.0, 0.4, 0.0]), dd * 100, lambda v: f"{v:+.1f} %")
        lr = np.log(P).diff()
        rv = lr.rolling(MON, min_periods=MON).std() * math.sqrt(Y)
        rv_med = rv.rolling(3 * Y, min_periods=Y).median()
        ratio = rv / rv_med
        C["rv"] = ("schwankung", "Schwankung ggü. üblich (1 Monat)", interp(ratio, [0.8, 1.25, 2.0], [0.3, 0.0, -1.0]), rv * 100,
                   lambda v: f"{v:.0f} % p.a. (üblich {rv_med.dropna().iloc[-1] * 100:.0f} %)")

        cols = list(C)
        S = pd.DataFrame({c: C[c][2] for c in cols})
        fam = {c: C[c][0] for c in cols}
        Pl = pd.DataFrame({p: S[[c for c in cols if fam[c] == p]].mean(axis=1, skipna=True) if any(fam[c] == p for c in cols) else pd.Series(np.nan, index=days)
                           for p in PILLARS})
        avail = Pl.notna()
        w = pd.Series(WEIGHTS)
        total = Pl.fillna(0).mul(w, axis=1).sum(axis=1) / avail.mul(w, axis=1).sum(axis=1).replace(0, np.nan)
        ok = (avail.sum(axis=1) >= 4) & P.notna() & avail["trend"]
        tv = total.where(ok)
        sdn = np.sqrt((tv ** 2).expanding(min_periods=3 * Y).mean())
        score = (50 + 15 * tv / sdn).clip(0, 100).where(ok & sdn.notna())
        first = score.first_valid_index()
        if first is None:
            continue
        last_i = score.last_valid_index()

        # ---------- Zukunft je Tag
        fut = {h: P.shift(-h) / P - 1 for h in (126, Y, 2 * Y, 3 * Y, 5 * Y)}
        rev = P[::-1]
        fmin = rev.rolling(Y, min_periods=Y).min()[::-1].shift(-1) / P - 1     # tiefster Stand in den nächsten 12 M.
        fmin24 = rev.rolling(2 * Y, min_periods=2 * Y).min()[::-1].shift(-1) / P - 1
        crash = (fmin <= -CRASH).astype(float).where(fmin.notna())

        # Monatsende-Stichprobe für Statistik (unabhängiger als Tageswerte)
        me = score.dropna().groupby(score.dropna().index.to_period("M")).tail(1).index
        df = pd.DataFrame({"s": score[me], "f12": fut[Y][me], "f36": (1 + fut[3 * Y][me]) ** (1 / 3) - 1, "f60": (1 + fut[5 * Y][me]) ** (1 / 5) - 1,
                           "dd": fmin[me]})
        crash_base = float((df.dd.dropna() <= -CRASH).mean() * 100)
        # Rang 0–100: Anteil aller bisherigen Tage mit niedrigerem Score (nur zur Anzeige; Regeln rechnen mit dem Score)
        smap = np.nanpercentile(score.dropna().values, np.arange(101))
        def rk(v):
            return int(round(float(np.interp(v, smap, np.arange(101)))))
        bands = []
        for lo, hi, name in BANDS:
            g = df[(df.s >= lo) & (df.s < hi)]
            g12 = g.dropna(subset=["f12"])
            gd = g.dropna(subset=["dd"])
            bands.append({
                "band": name, "lo": lo, "hi": hi, "rlo": rk(lo), "rhi": rk(min(hi, 100)), "n": int(len(gd)), "share": round(len(g) / max(1, len(df)) * 100, 1),
                "f12": None if not len(g12) else round(float(g12.f12.median() * 100), 1),
                "pos12": None if not len(g12) else round(float((g12.f12 > 0).mean() * 100), 0),
                "worst12": None if not len(g12) else round(float(g12.f12.min() * 100), 0),
                "f36": None if g.f36.dropna().empty else round(float(g.f36.dropna().median() * 100), 1),
                "f60": None if g.f60.dropna().empty else round(float(g.f60.dropna().median() * 100), 1),
                "dd12": None if not len(gd) else round(float(gd.dd.median() * 100), 1),
                "crash12": None if not len(gd) else round(float((gd.dd <= -CRASH).mean() * 100), 0),
            })

        # Richtung: kam der heutige Rang von oben oder von unten? (Rangänderung über 3 Monate, nur Anzeige –
        # als Zusatz im Wahrscheinlichkeitsmodell vorwärts getestet und nicht besser, siehe PROB_MODE)
        direction = None
        try:
            sd = score.dropna()
            r_now, r_ago = rk(sd.iloc[-1]), rk(sd.iloc[-1 - DIR_N])
            dfr = df.copy()
            dfr["r"] = np.interp(dfr.s.values, smap, np.arange(101))
            dfr["d3"] = dfr.r - dfr.r.shift(3)
            bnd = next((b for b in bands if b["rlo"] <= r_now < b["rhi"] or (b["rhi"] == 100 and r_now >= b["rlo"])), None)
            if bnd:
                gb = dfr[(dfr.r >= bnd["rlo"]) & (dfr.r < bnd["rhi"] + (1 if bnd["rhi"] == 100 else 0))].dropna(subset=["d3"])
                rows = []
                for lab, g in (("fallend (Rang −10 oder mehr in 3 Monaten)", gb[gb.d3 <= -10]), ("seitwärts", gb[gb.d3.abs() < 10]),
                               ("steigend (Rang +10 oder mehr)", gb[gb.d3 >= 10])):
                    g12, gd = g.dropna(subset=["f12"]), g.dropna(subset=["dd"])
                    pos = dfr.index.get_indexer(g.index)
                    rows.append({"lab": lab, "n": int(len(gd)), "ep": int(0 if not len(pos) else 1 + (np.diff(pos) > 3).sum()),
                                 "f12": None if not len(g12) else round(float(g12.f12.median() * 100), 1),
                                 "pos12": None if not len(g12) else round(float((g12.f12 > 0).mean() * 100), 0),
                                 "crash12": None if not len(gd) else round(float((gd.dd <= -CRASH).mean() * 100), 0)})
                d_now = r_now - r_ago
                direction = {"now": r_now, "ago": r_ago, "rlo": bnd["rlo"], "rhi": bnd["rhi"], "rows": rows,
                             "cur": 0 if d_now <= -10 else (2 if d_now >= 10 else 1)}
        except Exception:
            direction = None

        def sp(a, b):
            x = pd.concat([a, b], axis=1).dropna()
            return None if len(x) < 60 else round(float(x.iloc[:, 0].rank().corr(x.iloc[:, 1].rank())), 2)
        rank = {"score_f12": sp(df.s, df.f12), "score_f36": sp(df.s, df.f36), "score_f60": sp(df.s, df.f60), "score_dd": sp(df.s, df.dd),
                "pillars": {p: {"f12": sp(Pl[p][me], df.f12), "f36": sp(Pl[p][me], df.f36), "dd": sp(Pl[p][me], df.dd)} for p in PILLARS}}
        base = {"f12": round(float(df.f12.dropna().median() * 100), 1), "pos12": round(float((df.f12.dropna() > 0).mean() * 100), 0),
                "f36": round(float(df.f36.dropna().median() * 100), 1), "dd12": round(float(df.dd.dropna().median() * 100), 1),
                "crash12": round(crash_base, 0)}

        # ---------- Wahrscheinlichkeit (Walk-forward, logistische Regression auf die Säulen)
        if PROB_MODE == "score" or (PROB_MODE in ("score_fb", "score_fb_g7") and fbz is None):
            Xall = pd.DataFrame({"c": 1.0, "t": (tv / sdn).fillna(0.0)}, index=days)
        elif PROB_MODE == "score_vol":
            Xall = pd.DataFrame({"c": 1.0, "t": (tv / sdn).fillna(0.0), "v": Pl["schwankung"].fillna(0), "b": Pl["bewertung"].fillna(0)}, index=days)
        elif PROB_MODE == "score_fb_g7" and fbz is not None and g7 is not None:
            Xall = pd.DataFrame({"c": 1.0, "t": (tv / sdn).fillna(0.0), "f": fbz[0].fillna(0.0), "g": g7[0].fillna(0.0)}, index=days)
        elif PROB_MODE in ("score_fb", "score_fb_g7") and fbz is not None:
            Xall = pd.DataFrame({"c": 1.0, "t": (tv / sdn).fillna(0.0), "f": fbz[0].fillna(0.0)}, index=days)
        elif PROB_MODE in ("score_dir", "score_fall", "score_midfall"):
            t_ = (tv / sdn)
            d_ = (t_ - t_.shift(DIR_N)).fillna(0.0)
            if PROB_MODE == "score_fall":
                d_ = d_.clip(upper=0)
            if PROB_MODE == "score_midfall":
                d_ = d_.clip(upper=0) * ((t_ >= -1 / 3) & (t_ < 1 / 3)).astype(float)
            Xall = pd.DataFrame({"c": 1.0, "t": t_.fillna(0.0), "d": d_}, index=days)
        else:
            Xall = Pl.fillna(0.0)
            Xall.insert(0, "c", 1.0)
        yv = crash
        trows = me
        prob = pd.Series(np.nan, index=days)
        coefs = {}
        use_pool = (today.year - first.year) < POOL_MIN_YEARS and bool(pooled)
        y0 = first.year + 15 if not use_pool else first.year + 1
        for yr in range(y0, today.year + 1):
            if use_pool:
                wv = pooled.get(yr)
                if wv is None:
                    continue
            else:
                cut = pd.Timestamp(yr - 1, 1, 1) - pd.Timedelta(days=366) if yr < today.year else today - pd.Timedelta(days=366)
                tr = [d for d in trows if d <= cut and pd.notna(yv.get(d))]
                if len(tr) < 120 or yv[tr].sum() < 5:
                    continue
                wv = fit_logit(Xall.loc[tr].values, yv[tr].values, lam=PROB_LAM)
                if key == "spx":
                    pooled[yr] = wv
            coefs[yr] = wv
            sel = (days >= pd.Timestamp(yr, 1, 1)) & (days <= pd.Timestamp(yr, 12, 31)) & ok.values
            z = np.clip(Xall.values[sel] @ wv, -30, 30)
            prob[sel] = 1 / (1 + np.exp(-z))
        # Güte außerhalb der Stichprobe
        oos = pd.DataFrame({"p": prob[me], "y": yv[me]}).dropna()
        calib, brier, brier_ref, skill = [], None, None, None
        if len(oos) > 60:
            clim = yv[me].expanding().mean().shift(12).reindex(oos.index)
            brier = float(((oos.p - oos.y) ** 2).mean())
            brier_ref = float(((clim - oos.y) ** 2).dropna().mean())
            skill = None if not brier_ref else round((1 - brier / brier_ref) * 100, 0)
            for lo, hi in [(0, .1), (.1, .2), (.2, .35), (.35, .5), (.5, 1.01)]:
                g = oos[(oos.p >= lo) & (oos.p < hi)]
                calib.append({"lo": round(lo * 100), "hi": round(min(hi, 1) * 100), "n": int(len(g)),
                              "pred": None if not len(g) else round(float(g.p.mean() * 100), 0),
                              "real": None if not len(g) else round(float(g.y.mean() * 100), 0)})
        w_now = coefs.get(today.year)
        prob_now = None if pd.isna(prob.get(last_i)) else round(float(prob[last_i]) * 100, 0)

        # ---------- Regeln im Test (monatlich angepasst, Entscheidung mit dem Score vom letzten Handelstag)
        r = P / P.shift(1) - 1
        cash = (tbill.ffill() / 100 / Y)
        sidx = score.dropna().index

        def weekly_hold(expo):
            e = expo.copy()
            # Entscheidung am letzten Handelstag der Periode, gilt die ganze folgende Periode
            wk = e.where(e.index.isin(e.groupby(e.index.to_period(STRAT_FREQ)).tail(1).index)).ffill()
            return wk.shift(1)

        def strat(expo):
            e = weekly_hold(expo).reindex(sidx).fillna(0)
            ret = (e * (r.reindex(sidx) - 0.002 / Y) + (1 - e) * cash.reindex(sidx).fillna(0)).dropna()   # 0,2 % ETF-Gebühr p.a.
            eq = (1 + ret).cumprod()
            yrs = len(ret) / Y
            # gleiche Regel mit einem 2x-ETF (täglich zurückgesetzt): 2 × Tagesrendite, Finanzierung Geldmarkt + 0,5 %, Gebühr 0,6 % p.a.
            c_ = cash.reindex(sidx).fillna(0)
            # Die Kursreihen enthalten (außer DAX und MSCI World in Euro) keine Dividenden. Ein echter 2x-ETF bekommt die doppelte
            # Dividende; damit der Vergleich zur 1x-Linie (ohne Dividende) fair bleibt, wird eine Dividendenrendite einmal addiert.
            dy = DIV_YIELD.get(key, 0.02)
            if key == "spx":
                dm, pm = ser("div_m"), ser("spx_m")
                if dm is not None and pm is not None:
                    dy_s = (dm / pm).reindex(sidx, method="ffill").fillna(dy)
                    dy = dy_s
            r2 = (2 * r.reindex(sidx) + dy / Y - c_ - 0.005 / Y - 0.006 / Y).clip(lower=-1)
            ret2 = (e * r2 + (1 - e) * c_).dropna()
            eq2 = (1 + ret2).cumprod()
            return {"cagr": round((eq.iloc[-1] ** (1 / yrs) - 1) * 100, 1), "mdd": round(float((eq / eq.cummax() - 1).min()) * 100, 0),
                    "vol": round(float(ret.std() * math.sqrt(Y)) * 100, 1), "expo": round(float(e.mean() * 100), 0), "eq": eq,
                    "_e": e.reindex(eq.index), "_eq2": eq2}
        sched = {
            "bh": ("Kaufen und halten", "immer 100 % investiert", pd.Series(1.0, index=days)),
            "trend": ("Trendregel 10 Monate", "investiert, wenn der Kurs über seiner 10-Monats-Linie liegt, sonst Geldmarkt", (P > sma210).astype(float)),
            "score": ("Modell-Quote", f"Rang {rk(50)} = 50 % investiert, ab Rang {rk(65)} = 100 %, bis Rang {rk(35)} = 0 %, dazwischen fließend; Rest Geldmarkt", ((score - 50) / 30 + 0.5).clip(0, 1)),
            "schutz": ("Schutzregel", f"voll investiert, außer der Rang fällt: unter {rk(45)} nur 50 %, unter {rk(35)} raus",
                       pd.Series(np.select([score >= 45, score >= 35], [1.0, 0.5], 0.0), index=days).where(score.notna())),
        }
        strategies, eqs = [], {}
        for k_, (n_, d_, e_) in sched.items():
            S_ = strat(e_)
            eqs[k_] = S_.pop("eq"); ex_ = S_.pop("_e"); eq2_ = S_.pop("_eq2")
            ew = eqs[k_][eqs[k_].index.isin(me)]
            # je Monat: tiefster Tageswert (für den größten Verlust ab frei gewähltem Start) und mittlere Investitionsquote
            per = eqs[k_].index.to_period("M")
            lo = eqs[k_].groupby(per).min().reindex(ew.index.to_period("M")).values
            exm = ex_.groupby(per).mean().reindex(ew.index.to_period("M")).values
            ew2 = eq2_.reindex(ew.index)
            lo2 = eq2_.groupby(eq2_.index.to_period("M")).min().reindex(ew.index.to_period("M")).values
            strategies.append({"id": k_, "name": n_, "desc": d_, **S_, "eq": [round(float(v), 4) for v in ew.values],
                               "lo": [round(float(v), 4) for v in lo], "ex": [round(float(v), 2) for v in np.nan_to_num(exm)],
                               "eq2": [float(f"{v:.5g}") for v in ew2.values], "lo2": [float(f"{v:.5g}") for v in lo2]})
        strat_months = [str(d.date()) for d in eqs["bh"].index[eqs["bh"].index.isin(me)]]
        # Geldmarktrendite je Monat (für die Steuerrechnung in der App)
        _bi = eqs["bh"].index
        _c = cash.reindex(_bi).fillna(0)
        cash_m = [round(float(v), 6) for v in ((1 + _c).groupby(_bi.to_period("M")).prod() - 1)
                  .reindex(_bi[_bi.isin(me)].to_period("M")).fillna(0).values]

        # ---------- Ein-/Ausstiegs-Signale (Parameter nur aus S&P 500 bis 1989)
        signals_out = None
        if sig is not None:
            try:
                if key == "spx" and sig_params is None:
                    above_ = (P > sma210).fillna(False)
                    cache_ = (prev or {}).get("signal_roll") if isinstance(prev, dict) else None
                    sig_params = sig.rolling(score, above_, (P / P.shift(1) - 1).fillna(0), (tbill.ffill() / 100 / Y).fillna(0),
                                             now.year, cache_)
                    sig_cal = sig_params[max(sig_params, key=int)] if sig_params else None
                if sig_params:
                    signals_out = sig.evaluate(tname, score, P, sma210, tbill, sig_params)
            except Exception as e:  # noqa
                import traceback
                traceback.print_exc()
                signals_out = {"error": str(e)}

        # ---------- große Einbrüche (Tagesschluss)
        episodes = []
        Pv = P.dropna()
        Pv = Pv[Pv.index >= first]
        vals, pidx = Pv.values, list(Pv.index)
        n_, i = len(vals), 0
        while i < n_:
            pk, j, trough = i, i + 1, i
            while j < n_ and vals[j] < vals[pk]:
                if vals[j] < vals[trough]:
                    trough = j
                j += 1
            depth = vals[trough] / vals[pk] - 1
            if depth <= -EPISODE:
                pk_d, tr_d = pidx[pk], pidx[trough]
                win = score.loc[pk_d - pd.Timedelta(days=183):tr_d].dropna()
                warn = win[win < 45]
                first_w = warn.index[0] if len(warn) else None
                pw = prob.loc[pk_d - pd.Timedelta(days=183):tr_d].dropna()
                pwarn = pw[pw >= 0.3]
                ep = {"peak": str(pk_d.date()), "trough": str(tr_d.date()), "depth": round(depth * 100, 0),
                      "months": int(round((tr_d - pk_d).days / 30.44)), "recover": None if j >= n_ else str(pidx[j].date()),
                      "s_peak": None if pd.isna(score.get(pk_d)) else round(float(score[pk_d])),
                      "p_peak": None if pd.isna(prob.get(pk_d)) else round(float(prob[pk_d]) * 100),
                      "warn": None if first_w is None else str(first_w.date()),
                      "lost_at_warn": None if first_w is None else round(float(P[first_w] / P[pk_d] - 1) * 100, 0),
                      "pwarn": None if not len(pwarn) else str(pwarn.index[0].date())}
                for k_ in eqs:
                    if k_ == "bh":
                        continue
                    seg = eqs[k_].loc[pk_d:tr_d]
                    ep["dd_" + k_] = None if len(seg) < 2 else round(float(seg.min() / seg.iloc[0] - 1) * 100, 0)
                episodes.append(ep)
            i = j if j > i else i + 1
        warned = [e for e in episodes if e["warn"] is not None]

        # ---------- Analogien (Monatsenden der Vergangenheit, Merkmale = alle Komponenten)
        F = S.copy()
        F["cape_raw"] = clip(cape_raw / 2.5, -2, 2) if cape_raw is not None else np.nan
        famF = dict(fam)
        famF["cape_raw"] = "bewertung"
        x0 = F.loc[last_i]
        cand = F.loc[F.index.isin(me) & (F.index <= last_i - pd.Timedelta(days=730))]
        acc = pd.Series(0.0, index=cand.index)
        shared = pd.Series(0.0, index=cand.index)
        tot_w = 0.0
        for p in PILLARS:
            cs_ = [c for c in F.columns if famF.get(c) == p and pd.notna(x0[c])]
            if not cs_:
                continue
            tot_w += WEIGHTS[p]
            dif = (cand[cs_] - x0[cs_]) ** 2
            has = dif.notna().any(axis=1)
            acc = acc.add((dif.mean(axis=1, skipna=True) * WEIGHTS[p]).where(has, 0), fill_value=0)
            shared = shared.add(has.astype(float) * WEIGHTS[p], fill_value=0)
        dist = np.sqrt(acc / shared.replace(0, np.nan))
        dist = dist[shared >= 0.6 * tot_w].dropna().sort_values()
        picks = []
        for d_, v_ in dist.items():
            if all(abs((d_ - q).days) >= 548 for q, _ in picks):
                picks.append((d_, v_))
            if len(picks) >= 8:
                break
        Pme = P[me]
        analogs = []
        for d_, v_ in picks:
            k0 = Pme.index.get_loc(d_)
            pth = [None if k0 + h >= len(Pme) or pd.isna(Pme.iloc[k0 + h]) else round(float(Pme.iloc[k0 + h] / Pme.iloc[k0] * 100), 2) for h in range(37)]
            analogs.append({"month": str(d_.date()), "name": mname(d_), "sim": round(float(max(0, 1 - v_ / 1.2) * 100)), "score": round(float(score[d_])),
                            "prob": None if pd.isna(prob.get(d_)) else round(float(prob[d_]) * 100),
                            "pillars": {p: None if pd.isna(Pl[p].get(d_)) else round(float(50 + 50 * Pl[p][d_])) for p in PILLARS},
                            "f6": None if pd.isna(fut[126].get(d_)) else round(float(fut[126][d_]) * 100, 1),
                            "f12": None if pd.isna(fut[Y].get(d_)) else round(float(fut[Y][d_]) * 100, 1),
                            "f24": None if pd.isna(fut[2 * Y].get(d_)) else round(float(fut[2 * Y][d_]) * 100, 1),
                            "dd12": None if pd.isna(fmin.get(d_)) else round(float(fmin[d_]) * 100, 1),
                            "dd24": None if pd.isna(fmin24.get(d_)) else round(float(fmin24[d_]) * 100, 1), "path": pth})

        def med(k_):
            v = [a[k_] for a in analogs if a[k_] is not None]
            return None if not v else round(float(np.median(v)), 1)
        dd12s = [a["dd12"] for a in analogs if a["dd12"] is not None]
        f12s = [a["f12"] for a in analogs if a["f12"] is not None]
        mpath = []
        for h in range(37):
            v = [a["path"][h] for a in analogs if a["path"][h] is not None]
            mpath.append(None if len(v) < 3 else round(float(np.median(v)), 2))
        ana = {"items": analogs, "median_path": mpath, "f12": med("f12"), "f24": med("f24"), "dd12": med("dd12"),
               "pos12": None if not f12s else round(sum(1 for v in f12s if v > 0) / len(f12s) * 100),
               "crash12": None if not dd12s else round(sum(1 for v in dd12s if v <= -CRASH * 100) / len(dd12s) * 100),
               "n": len(analogs), "crash_base": round(crash_base)}

        # ---------- aktueller Stand
        now_score = float(round(score[last_i]))
        lab = label(now_score)
        pil_now = []
        for p in PILLARS:
            comps = []
            for c in cols:
                if fam[c] != p:
                    continue
                sc = C[c][2].loc[:last_i].dropna()
                rv_ = C[c][3].loc[:last_i].dropna()
                if not len(sc):
                    comps.append({"id": c, "name": C[c][1], "text": "keine Daten", "score": None})
                    continue
                vv = float(rv_.iloc[-1]) if len(rv_) else None
                try:
                    txt = C[c][4](vv) if vv is not None else ""
                except Exception:  # noqa
                    txt = ""
                stale = pd.isna(C[c][2].get(last_i))
                comps.append({"id": c, "name": C[c][1], "text": dez(txt), "score": round(float(sc.iloc[-1]), 2),
                              "asof": str(sc.index[-1].date()), "stale": bool(stale), "since": str(sc.index[0].year)})
            pv = Pl[p].loc[:last_i]
            pil_now.append({"id": p, "name": PILLAR_NAMES[p], "weight": WEIGHTS[p],
                            "score": None if pd.isna(pv.iloc[-1]) else round(float(50 + 50 * pv.iloc[-1]), 0), "comps": comps})

        # Klartext
        def word(s):
            return "stark positiv" if s >= 70 else "positiv" if s >= 58 else "neutral" if s > 42 else "negativ" if s > 30 else "stark negativ"
        pos = [x for x in pil_now if x["score"] is not None and x["score"] >= 58]
        neg = [x for x in pil_now if x["score"] is not None and x["score"] <= 42]
        sent = [f"{tname}: Rang {rk(now_score)} von 100 ({lab[0]}) – die Lage ist günstiger als an {rk(now_score)} % aller Tage seit {first.year}" + (f", Wahrscheinlichkeit für einen Rückgang von mindestens {CRASH * 100:.0f} % in den nächsten 12 Monaten {prob_now:.0f} % (im Schnitt {crash_base:.0f} %)." if prob_now is not None else ".")]
        if pos:
            sent.append("Dafür spricht: " + ", ".join(f"{x['name']} ({word(x['score'])})" for x in pos) + ".")
        if neg:
            sent.append("Dagegen spricht: " + ", ".join(f"{x['name']} ({word(x['score'])})" for x in neg) + ".")
        if analogs:
            sent.append(f"Am ähnlichsten war die Gesamtlage {', '.join(a['name'] for a in analogs[:3])}. In den {len(analogs)} ähnlichsten Momenten "
                        f"stand der Index ein Jahr später im Median {ana['f12']:+.1f} %; in {ana['crash12']} % kam es zu einem Rückgang von mindestens {CRASH * 100:.0f} %.")
        cb = [x for x in bands if x["n"]]
        if cb:
            sent.append(f"Je niedriger der Rang, desto häufiger folgte ein Rückgang von {CRASH * 100:.0f} % oder mehr ("
                        + "; ".join(f"Rang {x['rlo']}–{x['rhi']}: {x['crash12']:.0f} %" for x in cb) + ").")
        if skill is not None:
            sent.append(("Sie stützt sich auf den Score, die Käufe ausländischer Anleger von US-Aktien (hoch = spätzyklisch)"
                         + (" und – nur bei hoher Bewertung – gleichzeitig steigende Zinsen in den G7" if "g" in Xall.columns else "") + ". "
                         if "f" in Xall.columns else "")
                        + f"Die Wahrscheinlichkeit wurde Jahr für Jahr nur mit damals bekannten Daten berechnet und ist "
                        + ("besser als der bloße Durchschnitt" if skill > 0 else "nicht besser als der bloße Durchschnitt")
                        + f" (Brier-Skill {skill:+.0f} %).")
        if episodes:
            sent.append(f"Von den {len(episodes)} Einbrüchen von mindestens {EPISODE * 100:.0f} % seit {first.year} zeigte das Modell bei {len(warned)} spätestens bis zum Tief Gegenwind.")
        sb = next(x for x in strategies if x["id"] == "bh")
        ss = next(x for x in strategies if x["id"] == "score")
        sent.append(f"Als Regel (Modell-Quote): {ss['cagr']:+.1f} % p.a. bei höchstens {ss['mdd']:.0f} % Verlust – Kaufen und Halten: {sb['cagr']:+.1f} % p.a. bei {sb['mdd']:.0f} %.")
        sent = [dez(x) for x in sent]

        cb_now = next((x for x in bands if x["lo"] <= now_score < x["hi"]), None)
        risk = {"band": None if not cb_now else cb_now["crash12"], "analog": ana["crash12"], "base": round(crash_base), "prob": prob_now}

        # ---------- Live-Parameter für die App (kursabhängige Teile werden dort mit jedem Kurs neu gerechnet)
        Pl_last = Pl.loc[last_i]
        live_fixed = {c: (fam[c], None if pd.isna(C[c][2].get(last_i)) else round(float(C[c][2][last_i]), 4))
                      for c in cols if c not in ("sma10", "mom12", "w200", "dd", "rv")}
        closes = P.loc[:last_i].dropna().iloc[-1001:]
        live = {"closes": [round(float(v), 4) for v in closes.values], "last": str(closes.index[-1].date()),
                "tbill": None if pd.isna(tbill.get(last_i)) else round(float(tbill[last_i]), 3),
                "rv_med": None if pd.isna(rv_med.get(last_i)) else round(float(rv_med[last_i]), 5),
                "sd": round(float(sdn[last_i]), 6), "fixed": live_fixed,
                "coef": None if w_now is None else [round(float(x), 5) for x in w_now], "pillars": PILLARS, "weights": WEIGHTS,
                "px": None if "f" not in Xall.columns else round(float(Xall["f"].get(last_i, 0.0)), 4),
                "px2": None if "g" not in Xall.columns else round(float(Xall["g"].get(last_i, 0.0)), 4)}

        # Verlauf: Score/Wahrscheinlichkeit/Kurs wöchentlich, Säulen monatlich
        wk = score.dropna()
        wk = wk[wk.index.isin(wk.groupby(wk.index.to_period("W-FRI")).tail(1).index) | (wk.index == last_i)]
        hist = {"days": [str(d.date()) for d in wk.index], "score": [round(float(v), 1) for v in wk.values],
                "prob": [None if pd.isna(prob.get(d)) else round(float(prob[d]) * 100, 1) for d in wk.index],
                "price": [None if pd.isna(P.get(d)) else round(float(P[d]), 2) for d in wk.index],
                "pm_days": [str(d.date()) for d in me],
                "pillars": {p: [None if pd.isna(Pl[p].get(d)) else round(float(50 + 50 * Pl[p][d]), 1) for d in me] for p in PILLARS}}

        targets[key] = {
            "name": tname, "region": region, "sid": sid,
            "now": {"score": int(now_score), "day": str(last_i.date()), "month": str(last_i.date())[:7], "label": lab[0], "cls": lab[1],
                    "action": lab[2], "pillars": pil_now, "text": sent, "risk": risk},
            "hist": hist, "bands": bands, "base": base, "rank": rank, "since": str(first.date()), "smap": [round(float(v), 2) for v in smap],
            "strategies": strategies, "strat_months": strat_months, "cash_m": cash_m, "direction": direction, "episodes": episodes, "analogs": ana,
            "prob": {"now": prob_now, "calib": calib, "pooled": bool(use_pool), "brier": None if brier is None else round(brier, 4),
                     "brier_ref": None if brier_ref is None else round(brier_ref, 4), "skill": skill,
                     "oos_from": None if not len(oos) else str(oos.index[0].date())},
            "live": live, "crash": CRASH, "episode": EPISODE, "signals": signals_out,
        }

    targets = {k: targets[k] for k in TARGETS if k in targets}

    # ---------- Sebas eigene Regel (200-Wochen-Linie + CAPE-Wende)
    rule = {}
    for key, (sid, _n, _r) in TARGETS.items():
        s = ser(sid)
        if s is None:
            continue
        wkk = s.groupby(s.index.to_period("W-FRI")).last()
        sma = wkk.rolling(200, min_periods=200).mean()
        if pd.isna(sma.iloc[-1]):
            continue
        rule[key] = {"close": round(float(wkk.iloc[-1]), 2), "sma200w": round(float(sma.iloc[-1]), 2),
                     "dist": round(float(wkk.iloc[-1] / sma.iloc[-1] * 100 - 100), 1),
                     "lastTouch": next((str(p.end_time.date()) for p, a, b in zip(wkk.index[::-1], wkk.values[::-1], sma.values[::-1])
                                        if not pd.isna(b) and a <= b), None)}
    if markt:
        rule["signalScore"] = markt.get("score")
    q = quality_score()
    return {"weights": WEIGHTS, "pillar_names": PILLAR_NAMES, "targets": targets, "rule": rule, "quality": q, "g7": None if g7 is None else g7[1],
            "signal_params": (sig_cal or {}).get("p"), "signal_cal": sig_cal, "signal_roll": sig_params,
            "note": "Kursrenditen ohne Dividenden (außer MSCI World in Euro). Monatsdaten mit Veröffentlichungsverzögerung; "
                    "Stellenaufbau wie damals veröffentlicht (Philadelphia Fed), übrige Konjunkturdaten in heutiger Fassung. "
                    "Kein Anlagerat – ein Regelmodell."}
