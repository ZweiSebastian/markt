"""
Konzentration: Ist das Risiko breit oder steckt es in wenigen Schwergewichten?

1. KGV aufgeteilt: Index gesamt, Top 10, Rest (Index ohne Top 10), gleichgewichtet (RSP). Nur heutiger Stand
   (Yahoo Finance), wird ab jetzt täglich mitgeschrieben.
2. Rückstand der „vielen“: gleichgewichteter S&P 500 (RSP) gegen den normalen (SPY), 6 Monate.
3. Historische Einordnung mit der Datenbibliothek von Kenneth French (USA, Monatsdaten ab 1927):
   größere Hälfte der Aktien gleich gewichtet (verläuft zu 94 % wie RSP) gegen den Gesamtmarkt. Für alle Monate mit Index nahe am Hoch:
   Wie oft folgte binnen 12 Monaten ein Verlust von mindestens 15 %, je nachdem wie weit die vielen zurücklagen?

Fließt bewusst NICHT in den Score: Im Test (trainiert bis 1989, geprüft ab 1990) machte das Merkmal die
Verlust-Prognose schlechter (Brier-Skill 16 % → 8–13 %). Es dient als Hinweis, nicht als Signal.
"""
import io
import zipfile

import numpy as np
import pandas as pd

FF = "https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/"
TOPN = 10
H = 12


def _section(text, title):
    lines = text.splitlines()
    i = next(k for k, l in enumerate(lines) if l.strip().startswith(title))
    hdr = [h.strip() for h in lines[i + 1].split(",")][1:]
    rows = []
    for l in lines[i + 2:]:
        p = l.split(",")
        if len(p[0].strip()) != 6 or not p[0].strip().isdigit():
            break
        rows.append([p[0].strip()] + [float(x) for x in p[1:]])
    df = pd.DataFrame(rows, columns=["d"] + hdr)
    df.index = pd.to_datetime(df.pop("d"), format="%Y%m") + pd.offsets.MonthEnd(0)
    return df.replace([-99.99, -999.0], np.nan)


def _zip_text(get, name):
    r = get(FF + name, 90)
    z = zipfile.ZipFile(io.BytesIO(r.content))
    return z.read(z.namelist()[0]).decode("latin-1")


def french(get):
    """Gesamtmarkt (kapitalgewichtet) und „die vielen“ (Branchen gleich gewichtet), Monatsrenditen."""
    fac_t = _zip_text(get, "F-F_Research_Data_Factors_CSV.zip")
    lines = fac_t.splitlines()
    i = next(k for k, l in enumerate(lines) if l.startswith(",Mkt-RF"))
    rows = []
    for l in lines[i + 1:]:
        p = l.split(",")
        if len(p[0].strip()) != 6:
            break
        rows.append([p[0].strip()] + [float(x) for x in p[1:]])
    fac = pd.DataFrame(rows, columns=["d", "mkt", "smb", "hml", "rf"])
    fac.index = pd.to_datetime(fac.pop("d"), format="%Y%m") + pd.offsets.MonthEnd(0)
    me = _zip_text(get, "Portfolios_Formed_on_ME_CSV.zip")
    big = ["6-Dec", "7-Dec", "8-Dec", "9-Dec", "Hi 10"]          # größere Hälfte, ohne Kleinstwerte (ähnlich RSP)
    r_ew = _section(me, "Average Equal Weighted Returns -- Monthly")[big] / 100
    n = _section(me, "Number of Firms in Portfolios")[big].shift(1)
    cw = (1 + (fac["mkt"] + fac["rf"]) / 100).cumprod()
    ew = (1 + (r_ew * n).sum(axis=1) / n.sum(axis=1)).cumprod().reindex(cw.index)
    return cw, ew


def hist_stats(cw, ew):
    """Je Fünftel des Rückstands (nur Monate mit Index höchstens 5 % unter dem 12-Monats-Hoch)."""
    near = cw / cw.rolling(12).max() >= 0.95
    rel6 = ew.pct_change(6) - cw.pct_change(6)
    fw_cw = cw.shift(-H) / cw - 1
    fw_ew = ew.shift(-H) / ew - 1
    v = cw.values
    dd = pd.Series([(v[i + 1:i + H + 1] / v[i]).min() - 1 if i + H < len(v) else np.nan for i in range(len(v))], index=cw.index)
    d = pd.DataFrame({"near": near, "rel6": rel6, "dd": dd, "spread": fw_ew - fw_cw, "fw": fw_cw}).dropna(subset=["rel6"])
    nh = d[d.near]
    edges = list(nh["rel6"].quantile([0.2, 0.4, 0.6, 0.8]).values)
    def bucket(x):
        return int(np.searchsorted(edges, x))
    out = {}
    for lab, sub in (("all", nh), ("1963", nh.loc["1963":])):
        s = sub.dropna(subset=["dd"])
        b = s["rel6"].map(bucket)
        rows = []
        for q in range(5):
            x = s[b == q]
            rows.append({"q": q, "n": int(len(x)), "dd15": round(float((x.dd <= -0.15).mean() * 100), 0) if len(x) else None,
                         "fw": round(float(x.fw.median() * 100), 1) if len(x) else None,
                         "widen": round(float((x.spread < 0).mean() * 100), 0) if len(x) else None})
        out[lab] = {"rows": rows, "base": round(float((s.dd <= -0.15).mean() * 100), 0), "n": int(len(s)),
                    "from": str(s.index[0].date())}
    last = d.index[-1]
    return {"edges": [round(float(e), 4) for e in edges], "stats": out,
            "ff_last": {"d": str(last.date()), "rel6": round(float(d.rel6.iloc[-1]), 4), "near": bool(d.near.iloc[-1]),
                        "q": bucket(float(d.rel6.iloc[-1]))},
            "ff_hist": {"d": [str(x.date()) for x in d.index[-240:]], "v": [round(float(x), 4) for x in d.rel6.values[-240:]]}}


def pe_split():
    """KGV: Index (SPY), Top 10 (größte Positionen im SPY), Rest, gleichgewichtet (RSP)."""
    import yfinance as yf
    import time
    spy = yf.Ticker("SPY")
    info = spy.info or {}
    pe_idx = info.get("trailingPE")
    src_idx = "SPY"
    try:
        eh = spy.funds_data.equity_holdings
        if pe_idx is None and eh is not None:
            pe_idx = float(eh.loc["Price/Earnings"].iloc[0])
            src_idx = "SPY (Morningstar)"
    except Exception:  # noqa
        pass
    th = spy.funds_data.top_holdings
    hold = []
    for sym, row in th.head(TOPN).iterrows():
        w = float(row.get("Holding Percent", np.nan))
        try:
            i = yf.Ticker(sym).info or {}
        except Exception:  # noqa
            i = {}
        hold.append({"t": sym, "name": row.get("Name") or i.get("shortName") or sym, "w": w,
                     "mc": i.get("marketCap"), "pe": i.get("trailingPE"), "fpe": i.get("forwardPE"),
                     "ni": i.get("netIncomeToCommon")})
        time.sleep(0.5)
    try:
        rsp = yf.Ticker("RSP").info or {}
    except Exception:  # noqa
        rsp = {}
    pe_eq = rsp.get("trailingPE")
    ok = [h for h in hold if h["mc"] and h["w"] == h["w"] and h["w"] > 0]
    w_top = sum(h["w"] for h in ok)
    mc_top = sum(h["mc"] for h in ok)
    # Gewinne der Top 10: Börsenwert / KGV, ersatzweise Jahresüberschuss (auch negativ)
    e_top, e_top_f = 0.0, 0.0
    for h in ok:
        e = h["mc"] / h["pe"] if h["pe"] and h["pe"] > 0 else (h["ni"] or 0.0)
        e_top += e
        e_top_f += h["mc"] / h["fpe"] if h["fpe"] and h["fpe"] > 0 else e
    res = {"idx": None, "top": None, "top_f": None, "rest": None, "eq": None, "w_top": round(w_top * 100, 1),
           "src_idx": src_idx, "holdings": [{k: (round(v, 4) if isinstance(v, float) else v) for k, v in h.items() if k != "ni"} for h in hold]}
    sane = lambda x: x is not None and 5 < x < 80   # noqa
    if sane(pe_idx):
        res["idx"] = round(float(pe_idx), 1)
    if e_top > 0:
        res["top"] = round(mc_top / e_top, 1)
    if e_top_f > 0:
        res["top_f"] = round(mc_top / e_top_f, 1)
    if sane(pe_eq):
        res["eq"] = round(float(pe_eq), 1)
    if res["idx"] and w_top > 0.05 and e_top > 0:
        mc_tot = mc_top / w_top
        e_tot = mc_tot / res["idx"]
        if e_tot > e_top:
            r = (mc_tot - mc_top) / (e_tot - e_top)
            res["rest"] = round(r, 1) if sane(r) else None
    return res


def live_lag(rsp, spy):
    """Rückstand des gleichgewichteten S&P 500 über 6 Monate (126 Börsentage), täglich."""
    a = pd.concat([rsp, spy], axis=1, join="inner").dropna()
    a.columns = ["rsp", "spy"]
    return (a.rsp / a.rsp.shift(126) - a.spy / a.spy.shift(126)).dropna()


def build(get, rsp, spy, spx, prev, now, refresh_pe, refresh_ff, note):
    out = dict(prev or {})
    if refresh_ff or not out.get("hist"):
        try:
            cw, ew = french(get)
            out["hist"] = hist_stats(cw, ew)
            out["ff_at"] = now.strftime("%Y-%m-%d")
            note("konzentration French", True, f"bis {out['hist']['ff_last']['d']}")
        except Exception as e:  # noqa
            note("konzentration French", False, f"{type(e).__name__}: {e}")
    if refresh_pe or not out.get("pe"):
        try:
            out["pe"] = pe_split()
            out["pe_at"] = now.strftime("%Y-%m-%d")
            p = out["pe"]
            note("konzentration KGV", True, f"Index {p['idx']} Top10 {p['top']} Rest {p['rest']} gleich {p['eq']} Gewicht {p['w_top']}%")
        except Exception as e:  # noqa
            note("konzentration KGV", False, f"{type(e).__name__}: {e}")
    lag = None
    if rsp is not None and spy is not None:
        lg = live_lag(rsp, spy)
        if len(lg):
            lag = lg
            # Einordnung über Perzentil innerhalb der eigenen Historie (nur Tage mit S&P nahe Hoch)
            sp = spx.reindex(lg.index).ffill() if spx is not None else None
            if sp is not None:
                nearm = (sp / sp.rolling(252, min_periods=60).max() >= 0.95)
                ref = lg[nearm.fillna(False)]
            else:
                ref = lg
            pct = float((ref < lg.iloc[-1]).mean()) if len(ref) > 250 else None
            q = None if pct is None else min(4, int(pct * 5))
            near_now = bool(sp is not None and sp.iloc[-1] / sp.tail(252).max() >= 0.95)
            out["lag"] = {"d": str(lg.index[-1].date()), "v": round(float(lg.iloc[-1]), 4), "pct": None if pct is None else round(pct * 100, 0),
                          "q": q, "near": near_now}
    # Warnhinweis
    st = (out.get("hist") or {}).get("stats", {}).get("1963")
    L, P = out.get("lag") or {}, out.get("pe") or {}
    flags = []
    if L.get("q") == 0 and L.get("near") and st:
        r0 = st["rows"][0]
        flags.append(f"Die vielen hinken stark hinterher (gleichgewichteter S&P {L['v'] * 100:+.1f} % ggü. normalem in 6 Monaten) – "
                     f"in solchen Lagen folgte seit 1963 in {r0['dd15']:.0f} % der Fälle binnen 12 Monaten ein Verlust von 15 % oder mehr "
                     f"(übrige Lagen: {_rest_rate(st):.0f} %).")
    if P.get("top") and P.get("rest") and P["top"] / P["rest"] >= 1.5:
        flags.append(f"Bewertung konzentriert: Top 10 mit KGV {P['top']:.0f}, der Rest mit {P['rest']:.0f}.")
    out["flags"] = flags
    # mitschreiben (ein Eintrag je Tag)
    tr = [x for x in (out.get("track") or []) if x.get("d") != now.strftime("%Y-%m-%d")]
    tr.append({"d": now.strftime("%Y-%m-%d"), "idx": P.get("idx"), "top": P.get("top"), "rest": P.get("rest"), "eq": P.get("eq"),
               "w": P.get("w_top"), "lag": L.get("v")})
    out["track"] = tr[-3000:]
    return out, lag


def _rest_rate(st):
    rows = [r for r in st["rows"][1:] if r["n"]]
    n = sum(r["n"] for r in rows)
    return sum(r["dd15"] * r["n"] for r in rows) / n if n else 0
