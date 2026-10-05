"""
Ein- und Ausstiegs-Signale (Reiter „Signale“).

Zustandsautomat auf Tagesbasis: investiert ↔ draußen. Sicherheit hat Vorrang, deshalb wird nicht vorhergesagt,
sondern bestätigt reagiert:
- Ausstieg, wenn der Score an N Tagen in Folge unter einer Schwelle liegt (optional zusätzlich Kurs unter der
  10-Monats-Linie).
- Wiedereinstieg erst, wenn der Score an M Tagen in Folge über einer (höheren) Schwelle liegt und der Kurs über der
  10-Monats-Linie – bewusst spät, um Zwischenerholungen nicht mitzunehmen.
- Nach jedem Wechsel mindestens 20 Börsentage Ruhe (kein Hin und Her).
Entscheidung zum Tagesschluss, gilt ab dem nächsten Tag.

Kalibrierung, rollierend: Für jedes Jahr ab 1990 werden die Regelparameter NUR mit den jeweils letzten 35 Jahren des
S&P 500 gewählt (Ziel: möglichst kleiner größter Verlust, höchstens 2,5 Umschichtungen pro Jahrzehnt, Rendite höchstens
1 Prozentpunkt unter Kaufen und Halten) und gelten dann unverändert für dieses Jahr. So arbeitet die Regel immer mit der
jüngeren Marktgeschichte, und jedes Jahr ab 1990 ist ein echter Vorwärtstest. Vor 1990 gelten die Parameter von 1990
(dort also nicht vorwärts getestet).
"""
import itertools
import math

import numpy as np
import pandas as pd

Y = 252
CAL_END = pd.Timestamp("1989-12-31")
GRID = {
    "exit_s": [35, 40, 45],
    "exit_n": [5, 10, 20],
    "exit_trend": [True, False],
    "entry_s": [45, 50, 55],
    "entry_n": [10, 20, 40],
}
HOLD_MIN = 20
WINDOW = 35
ROLL_FROM = 1990


def simulate(s, above, r, cash, p):
    """s: Score (np, nan = keine Aussage), above: Kurs über 10-M.-Linie (bool), r/cash: Tagesrenditen.
    Gibt Positionsreihe (0/1, gilt am jeweiligen Tag) und Wechsel zurück."""
    n = len(s)
    per = isinstance(p, list)
    P_ = p
    pos = np.ones(n)
    state, cnt_out, cnt_in, since = 1, 0, 0, HOLD_MIN
    switches = []
    for t in range(n):
        pos[t] = state                       # Position am Tag t (Entscheidung vom Vortag)
        p = P_[t] if per else P_
        st = s[t]
        if np.isnan(st):
            continue
        if state == 1:
            cond = st < p["exit_s"] and (not p["exit_trend"] or not above[t])
            cnt_out = cnt_out + 1 if cond else 0
            if cnt_out >= p["exit_n"] and since >= HOLD_MIN:
                state, since, cnt_out, cnt_in = 0, 0, 0, 0
                switches.append((t, 0))
        else:
            cond = st >= p["entry_s"] and above[t]
            cnt_in = cnt_in + 1 if cond else 0
            if cnt_in >= p["entry_n"] and since >= HOLD_MIN:
                state, since, cnt_out, cnt_in = 1, 0, 0, 0
                switches.append((t, 1))
        since += 1
    return pos, switches


def perf(pos, r, cash):
    ret = pos * r + (1 - pos) * cash
    ret = np.nan_to_num(ret)
    eq = np.cumprod(1 + ret)
    yrs = len(ret) / Y
    cagr = eq[-1] ** (1 / yrs) - 1 if yrs > 0 else np.nan
    mdd = float((eq / np.maximum.accumulate(eq) - 1).min())
    return eq, cagr, mdd


def calibrate(score, above, r, cash, start=None, end=None):
    """Parameter nur aus Daten im Fenster [start, end] (Standard: bis CAL_END)."""
    end = CAL_END if end is None else end
    m = (score.index <= end) & score.notna().values
    if start is not None:
        m = m & (score.index >= start)
    idx = np.where(m)[0]
    if len(idx) < 10 * Y:
        return None, None
    a, b = idx[0], idx[-1] + 1
    s_, ab_, r_, c_ = score.values[a:b], above.values[a:b], r.values[a:b], cash.values[a:b]
    _, bh_cagr, bh_mdd = perf(np.ones(b - a), r_, c_)
    yrs = (b - a) / Y
    rows = []
    for combo in itertools.product(*GRID.values()):
        p = dict(zip(GRID.keys(), combo))
        if p["entry_s"] <= p["exit_s"]:
            continue
        pos, sw = simulate(s_, ab_, r_, c_, p)
        _, cg, md = perf(pos, r_, c_)
        trips = sum(1 for _, k in sw if k == 0)
        rows.append((p, cg, md, trips / yrs * 10))
    best = None
    for gap in (0.01, 0.02, 0.03):
        ok = [x for x in rows if x[3] <= 2.5 and x[1] >= bh_cagr - gap]
        if ok:
            best = max(ok, key=lambda x: (round(x[2], 2), x[1]))   # kleinster Verlust, dann höchste Rendite
            break
    if best is None:
        best = max(rows, key=lambda x: x[1] - 0.3 * abs(x[2]))
    info = {"bh_cagr": round(bh_cagr * 100, 1), "bh_mdd": round(bh_mdd * 100, 0), "cagr": round(best[1] * 100, 1),
            "mdd": round(best[2] * 100, 0), "per_decade": round(best[3], 1), "n_tested": len(rows),
            "from": str(score.index[a].date()), "to": str(score.index[b - 1].date())}
    return best[0], info


def rolling(score, above, r, cash, last_year, cache=None):
    """Je Jahr ab ROLL_FROM: Parameter aus den WINDOW Jahren davor. cache: früher berechnete Jahre (unverändert)."""
    out = {}
    for Y in range(ROLL_FROM, last_year + 1):
        k = str(Y)
        if cache and k in cache and cache[k].get("p"):
            out[k] = cache[k]
            continue
        p, info = calibrate(score, above, r, cash, pd.Timestamp(f"{Y - WINDOW}-01-01"), pd.Timestamp(f"{Y - 1}-12-31"))
        if p is None:
            continue
        out[k] = {"p": p, **info}
    return out


def schedule(index, roll):
    """Parameter je Tag aus dem Jahresplan (vor dem ersten Jahr: erstes Jahr, danach: letztes)."""
    ys = sorted(int(k) for k in roll)
    first, last = ys[0], ys[-1]
    return [roll[str(min(max(d.year, first), last))]["p"] for d in index]


def evaluate(name, score, P, sma210, cash_rate, params, episodes_min=0.20):
    """Signale für einen Index mit festen Parametern; Kennzahlen vor/nach 1990, Bilanz je Einbruch."""
    days = score.index
    above = (P > sma210).fillna(False)
    r = (P / P.shift(1) - 1).fillna(0)
    cash = (cash_rate.ffill() / 100 / Y).fillna(0)
    ok = score.notna()
    if ok.sum() < 3 * Y:
        return None
    first = score.first_valid_index()
    sel = days >= first
    d = days[sel]
    s_, ab_, r_, c_ = score.values[sel], above.values[sel], r.values[sel], cash.values[sel]
    if isinstance(params, dict) and "exit_s" not in params:      # rollierender Jahresplan
        plist = schedule(d, params)
        pcur = plist[-1]
    else:
        plist, pcur = params, params
    pos, sw = simulate(s_, ab_, r_, c_, plist)
    eq, cagr, mdd = perf(pos, r_, c_)
    eqbh, bcagr, bmdd = perf(np.ones(len(pos)), r_, c_)
    pos_s = pd.Series(pos, index=d)
    Pd = P[sel]

    def block(mask):
        if mask.sum() < Y:
            return None
        e1, c1, m1 = perf(pos[mask], r_[mask], c_[mask])
        e0, c0, m0 = perf(np.ones(mask.sum()), r_[mask], c_[mask])
        yrs = mask.sum() / Y
        dmask = d[mask]
        n_exit = sum(1 for t, k in sw if k == 0 and d[t] >= dmask[0] and d[t] <= dmask[-1])
        return {"from": str(dmask[0].date()), "to": str(dmask[-1].date()), "cagr": round(c1 * 100, 1), "mdd": round(m1 * 100, 0),
                "bh_cagr": round(c0 * 100, 1), "bh_mdd": round(m0 * 100, 0), "exits": n_exit,
                "per_decade": round(n_exit / yrs * 10, 1), "invested": round(float(pos[mask].mean() * 100), 0)}
    is_ = block(d <= CAL_END)
    oos = block(d > CAL_END)

    # Wechsel als Liste mit Kurs
    trades = []
    for t, k in sw:
        trades.append({"d": str(d[t].date()), "k": "ein" if k == 1 else "aus", "p": round(float(Pd.iloc[t]), 2)})
    # Fehlalarme: Ausstieg, nach dem der Wiedereinstieg teurer war als der Ausstieg
    pairs = []
    for i, tr in enumerate(trades):
        if tr["k"] == "aus":
            nxt = next((x for x in trades[i + 1:] if x["k"] == "ein"), None)
            low = Pd.loc[tr["d"]:(nxt["d"] if nxt else None)].min()
            pairs.append({"aus": tr["d"], "ein": nxt["d"] if nxt else None, "p_aus": tr["p"], "p_ein": nxt["p"] if nxt else None,
                          "chg": None if not nxt else round((nxt["p"] / tr["p"] - 1) * 100, 1),
                          "low": round(float(low / tr["p"] - 1) * 100, 1)})
    useful = [x for x in pairs if x["chg"] is not None and x["chg"] < 0]
    false_ = [x for x in pairs if x["chg"] is not None and x["chg"] >= 0]

    # Bilanz je großem Einbruch (Tagesschluss, ≥ 20 %)
    eps = []
    vals, pidx = Pd.values, list(Pd.index)
    n_, i = len(vals), 0
    while i < n_:
        pk, j, tr_ = i, i + 1, i
        while j < n_ and vals[j] < vals[pk]:
            if vals[j] < vals[tr_]:
                tr_ = j
            j += 1
        depth = vals[tr_] / vals[pk] - 1
        if depth <= -episodes_min:
            pk_d, tr_d = pidx[pk], pidx[tr_]
            already_out = pos_s.get(pk_d, 1) == 0
            if already_out:   # schon vor dem Hoch draußen: letzten Ausstieg davor nehmen
                exit_ = next((x for x in reversed(trades) if x["k"] == "aus" and pd.Timestamp(x["d"]) <= pk_d), None)
            else:
                exit_ = next((x for x in trades if x["k"] == "aus" and pd.Timestamp(x["d"]) >= pk_d and pd.Timestamp(x["d"]) <= tr_d), None)
            entry_ = None
            if exit_:
                entry_ = next((x for x in trades if x["k"] == "ein" and pd.Timestamp(x["d"]) > pd.Timestamp(exit_["d"])), None)
            seg = pd.Series(eq, index=d).loc[pk_d:tr_d]
            eps.append({"peak": str(pk_d.date()), "trough": str(tr_d.date()), "depth": round(depth * 100, 0),
                        "exit": exit_["d"] if exit_ else None,
                        "exit_vs_peak": None if not exit_ else round((exit_["p"] / vals[pk] - 1) * 100, 1),
                        "entry": entry_["d"] if entry_ else None,
                        "entry_vs_trough": None if not entry_ else round((entry_["p"] / vals[tr_] - 1) * 100, 1),
                        "strat_dd": None if len(seg) < 2 else round(float(seg.min() / seg.iloc[0] - 1) * 100, 0),
                        "already_out": bool(already_out),
                        "oos": bool(pk_d > CAL_END)})
        i = j if j > i else i + 1

    # aktueller Zustand und was bis zum nächsten Wechsel fehlt
    st = int(pos_s.iloc[-1])
    last_sw = trades[-1] if trades else None
    s_now = float(score.dropna().iloc[-1])
    ab_now = bool(above.iloc[-1])
    run = 0
    for v, a_ in zip(score.dropna().values[::-1], above.loc[score.dropna().index].values[::-1]):
        cond = (v < pcur["exit_s"] and (not pcur["exit_trend"] or not a_)) if st == 1 else (v >= pcur["entry_s"] and a_)
        if not cond:
            break
        run += 1
    # die heutige Entscheidung gilt ab morgen – der Zustand nach heutigem Schluss:
    pl2 = plist + [pcur] if isinstance(plist, list) else plist
    pos_next, _ = simulate(np.append(s_, np.nan), np.append(ab_, False), np.append(r_, 0), np.append(c_, 0), pl2)
    st_next = int(pos_next[-1])
    eqm = pd.Series(eq, index=d)
    eqbm = pd.Series(eqbh, index=d)
    me = eqm.groupby(eqm.index.to_period("M")).tail(1).index
    return {
        "state": st_next, "since": last_sw["d"] if last_sw else str(d[0].date()),
        "score": round(s_now), "above": ab_now, "run": run,
        "need": pcur["exit_n"] if st_next == 1 else pcur["entry_n"],
        "all": {"cagr": round(cagr * 100, 1), "mdd": round(mdd * 100, 0), "bh_cagr": round(bcagr * 100, 1), "bh_mdd": round(bmdd * 100, 0),
                "invested": round(float(pos.mean() * 100), 0), "from": str(d[0].date())},
        "is": is_, "oos": oos, "trades": trades[-60:], "n_trades": len(trades), "pairs": pairs[-40:],
        "useful": len(useful), "false": len(false_),
        "false_cost": None if not false_ else round(float(np.median([x["chg"] for x in false_])), 1),
        "useful_gain": None if not useful else round(float(np.median([-x["chg"] for x in useful])), 1),
        "episodes": eps,
        "eq": {"days": [str(x.date()) for x in me], "sig": [round(float(v), 4) for v in eqm[me].values], "bh": [round(float(v), 4) for v in eqbm[me].values]},
    }
