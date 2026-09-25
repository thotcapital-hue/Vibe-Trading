#!/usr/bin/env python3
"""Ledger tests 1-3: data reconciliation, asset mix, leverage with tranches (Yahoo data).

Test 1  Why did the 6y regime sleeve read 11.3% on Alpaca bars but 15.1% on Yahoo?
        Same rule on Yahoo price-only vs total-return series, and the two ribbon
        rules ("stack": in only while 20-low > 200-high, else cash; "2b": in on
        20-low > 200-high, out only on 20-high < 200-low).
Test 2  Asset mix x gate x window, 1x, total return, 5 bp costs, cash at T-bill.
Test 3  Leverage 1x / 1.5x / 2x inside the regime (financing at bill + 0.5%),
        with and without Grok-style tranches (1/3 at entry, 1/3 after 3 weeks,
        1/3 after 6 weeks), 19y and 6y; plus the options overlay from the
        exported 19y / 6y curves added on the same $100k.

Signals decided on close i apply to the return on day i+1.

Usage: python scripts/backtest_sleeve_mix.py [--start 2007-04-10] [--start6 2020-09-25]
"""
from __future__ import annotations

import argparse
import csv
import math
import statistics as st
from datetime import date
from pathlib import Path

from backtest_qld_sleeve import load, sma

ROOT = Path(__file__).resolve().parent.parent
TBILL = {2007: 4.4, 2008: 1.4, 2009: 0.15, 2010: 0.14, 2011: 0.05, 2012: 0.09, 2013: 0.06,
         2014: 0.03, 2015: 0.05, 2016: 0.32, 2017: 0.93, 2018: 1.94, 2019: 2.06, 2020: 0.37,
         2021: 0.04, 2022: 2.0, 2023: 5.1, 2024: 5.0, 2025: 4.2, 2026: 3.8}
MIXES = {"QQQ": ["QQQ"], "SPY": ["SPY"], "SPY+QQQ": ["SPY", "QQQ"], "SPY+QQQ+IWM": ["SPY", "QQQ", "IWM"], "IWM": ["IWM"]}


def build(sym, dates, tr=True):
    rows = {r[0]: r for r in load(sym, False)}
    h, l, c = [], [], []
    for d in dates:
        _, hi, lo, cl, adj = rows[d]
        f = adj / cl if tr else 1.0
        h.append(hi * f); l.append(lo * f); c.append(cl * f)
    return dict(c=c, h20=sma(h, 20), l20=sma(l, 20), h200=sma(h, 200), l200=sma(l, 200), c200=sma(c, 200))


def signal(d, gate):
    """pos[i] = 1 if long for the return on day i (decided on close i-1)."""
    n = len(d["c"]); pos = [0] * n; on = 0
    for i in range(1, n):
        j = i - 1
        if d["h200"][j] is None:
            continue
        if gate == "bh":
            on = 1
        elif gate == "sma200":
            on = 1 if d["c"][j] > d["c200"][j] else 0
        elif gate == "stack":
            on = 1 if d["l20"][j] > d["h200"][j] else 0
        elif gate == "2b":
            on = 1 if d["l20"][j] > d["h200"][j] else (0 if d["h20"][j] < d["l200"][j] else on)
        pos[i] = on
    return pos


def tranche_frac(pos, days=15):
    """Grok clock: 1/3 at entry, 2/3 after `days`, 3/3 after 2*days; reset when flat."""
    out = [0.0] * len(pos); since = None
    for i, p in enumerate(pos):
        if not p:
            since = None; continue
        since = 0 if since is None else since + 1
        out[i] = 1 / 3 if since < days else (2 / 3 if since < 2 * days else 1.0)
    return out


def run(dates, data, syms, gate, i0, lever=1.0, tranches=False, cash=None, cost=5e-4, tr=True):
    n = len(dates); w = 1 / len(syms)
    pos = {s: signal(data[s], gate) for s in syms}
    frac = {s: (tranche_frac(pos[s]) if tranches else [float(p) for p in pos[s]]) for s in syms}
    eq = 1.0; curve = [1.0]; daily = []; prev = {s: 0.0 for s in syms}; exits = 0
    for i in range(i0, n):
        cr = (cash if cash is not None else TBILL.get(dates[i].year, 3.0) / 100) / 252
        r = 0.0
        for s in syms:
            e = frac[s][i] * lever
            r += w * (e * (data[s]["c"][i] / data[s]["c"][i - 1] - 1) + (1 - min(e, 1.0)) * cr
                      - max(0.0, e - 1) * (cr + 0.005 / 252))
            eq *= 1 - cost * abs(e - prev[s]) * w
            if prev[s] > 0 and e == 0: exits += 1
            prev[s] = e
        eq *= 1 + r; daily.append(eq / curve[-1] - 1); curve.append(eq)
    yrs = (n - i0) / 252; cagr = eq ** (1 / yrs) - 1
    peak = 1.0; mdd = 0.0; eps = []; pk_i = 0; tr_v = 1.0; tr_i = 0
    for k, v in enumerate(curve):
        if v >= peak:
            if tr_v < peak: eps.append((tr_v / peak - 1, dates[i0 + pk_i - 1] if pk_i else dates[i0], dates[i0 + tr_i - 1]))
            peak, pk_i, tr_v, tr_i = v, k, v, k
        elif v < tr_v:
            tr_v, tr_i = v, k
        mdd = min(mdd, v / peak - 1)
    if tr_v < peak: eps.append((tr_v / peak - 1, dates[i0 + pk_i - 1], dates[i0 + tr_i - 1]))
    sd = st.pstdev(daily); sharpe = st.fmean(daily) / sd * math.sqrt(252) if sd else 0
    return dict(cagr=cagr, mdd=mdd, sharpe=sharpe, calmar=cagr / abs(mdd) if mdd else 0, exits=exits / yrs,
                curve=curve, worst=sorted(eps)[:3], expo=st.fmean(st.fmean(frac[s][i] for s in syms) for i in range(i0, n)))


def fmt(name, r):
    return f"{name:<46} {r['cagr']:>6.1%} {r['mdd']:>7.1%} {r['sharpe']:>6.2f} {r['calmar']:>6.2f} {r['exits']:>5.1f} {r['expo']:>5.0%}"


HDR = f"{'strategy':<46} {'CAGR':>6} {'MaxDD':>7} {'Sharpe':>6} {'Calmar':>6} {'ex/yr':>5} {'expo':>5}"


def overlay_combo(dates, i0, sleeve_curve, csv_path):
    ov = {}
    with open(csv_path) as f:
        for row in csv.DictReader(f):
            ov[date.fromisoformat(row["date"])] = float(row["equity"])
    comb = []; ov0 = None; ds = []
    for k, v in enumerate(sleeve_curve):
        d = dates[i0 + k - 1] if k else dates[i0 - 1]
        o = ov.get(d)
        if o is None: continue
        if ov0 is None: ov0 = o
        comb.append(v + (o - ov0) / 100_000); ds.append(d)
    daily = [comb[k] / comb[k - 1] - 1 for k in range(1, len(comb))]
    yrs = len(daily) / 252; cagr = (comb[-1] / comb[0]) ** (1 / yrs) - 1
    peak = comb[0]; mdd = 0
    for v in comb: peak = max(peak, v); mdd = min(mdd, v / peak - 1)
    sd = st.pstdev(daily)
    return dict(cagr=cagr, mdd=mdd, sharpe=st.fmean(daily) / sd * math.sqrt(252) if sd else 0,
                calmar=cagr / abs(mdd) if mdd else 0, exits=0, expo=0, span=(ds[0], ds[-1]))


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--start", default="2007-04-10"); ap.add_argument("--start6", default="2020-09-25")
    args = ap.parse_args()
    syms = ["SPY", "QQQ", "IWM"]
    dates = sorted(set.intersection(*[set(r[0] for r in load(s, False)) for s in syms]))
    data = {s: build(s, dates) for s in syms}
    data_px = {s: build(s, dates, tr=False) for s in syms}
    i19 = next(i for i, d in enumerate(dates) if d >= date.fromisoformat(args.start))
    i6 = next(i for i, d in enumerate(dates) if d >= date.fromisoformat(args.start6))
    print(f"data: Yahoo daily, {dates[0]} -> {dates[-1]}; 19y window from {dates[i19]}, 6y window from {dates[i6]}")

    print("\nTEST 1  reconciliation, basket SPY/QQQ/IWM, 6y, cash 3% flat (as backtest_stack), 5 bp costs")
    print("Alpaca reference (backtest_stack, 'regime sleeve 1x' = stack rule, price-only): 11.3% / -13.0% / 0.91\n" + HDR)
    for gate in ("stack", "2b", "sma200"):
        print(fmt(f"{gate:<7} price-only (no dividends)", run(dates, data_px, syms, gate, i6, cash=0.03)))
        print(fmt(f"{gate:<7} total return (dividends reinvested)", run(dates, data, syms, gate, i6, cash=0.03)))
    print(fmt("buy & hold price-only", run(dates, data_px, syms, "bh", i6, cash=0.03)))
    print(fmt("buy & hold total return", run(dates, data, syms, "bh", i6, cash=0.03)))

    print("\nTEST 2  asset mix x gate, 1x, total return, cash at T-bill, 5 bp costs")
    for label, i0 in (("19y", i19), ("6y", i6)):
        print(f"\n-- {label} window\n" + HDR)
        for mix, ms in MIXES.items():
            bh = run(dates, data, ms, "bh", i0)
            print(fmt(f"{mix:<12} buy & hold", bh))
            for gate in ("sma200", "stack", "2b"):
                print(fmt(f"{mix:<12} {gate}", run(dates, data, ms, gate, i0)))

    print("\nTEST 3  leverage inside the regime, with/without tranches (1/3 now, 1/3 at 3 wks, 1/3 at 6 wks)")
    cands = []
    for label, i0 in (("19y", i19), ("6y", i6)):
        print(f"\n-- {label} window\n" + HDR)
        for mix in ("QQQ", "SPY+QQQ", "SPY+QQQ+IWM"):
            for gate in ("2b", "sma200"):
                for lev in (1.0, 1.5, 2.0):
                    for trn in (False, True):
                        r = run(dates, data, MIXES[mix], gate, i0, lever=lev, tranches=trn)
                        name = f"{mix:<12} {gate:<6} {lev:.1f}x {'tranches' if trn else 'full    '}"
                        flag = " <- target" if r["cagr"] >= 0.20 and r["mdd"] >= -0.25 else ""
                        print(fmt(name, r) + flag)
                        if label == "19y": cands.append((name, r))
    print("\n19y candidates meeting CAGR >= 20% and MaxDD >= -25%: " +
          (", ".join(n.strip() for n, r in cands if r["cagr"] >= 0.20 and r["mdd"] >= -0.25) or "none"))
    best = sorted(cands, key=lambda x: -x[1]["calmar"])[:5]
    print("top 5 by Calmar (19y):")
    for n, r in best:
        print("  " + fmt(n, r))
        for dd, p, t in r["worst"]:
            print(f"      {dd:>7.1%} from {p} to {t}")

    print("\nTEST 3b  add the options overlay (index bull puts, 10% risk, 30% heat, staged, hold to expiry) on the same $100k")
    for label, i0, csvp in (("19y", i19, ROOT / "research/overlay_curve_19y_100k.csv"), ("6y", i6, ROOT / "research/overlay_curve_100k.csv")):
        if not csvp.exists():
            print(f"[skip] {csvp} missing"); continue
        print(f"\n-- {label} window, overlay from {csvp.name}\n" + HDR)
        for mix in ("SPY+QQQ", "SPY+QQQ+IWM"):
            for lev in (1.0, 1.5):
                for trn in (False, True):
                    r = run(dates, data, MIXES[mix], "2b", i0, lever=lev, tranches=trn)
                    c = overlay_combo(dates, i0, r["curve"], csvp)
                    print(fmt(f"{mix:<12} 2b {lev:.1f}x {'tranches' if trn else 'full    '} sleeve alone", r))
                    print(fmt(f"{'':<12}    {'':<4} {'':<8} + overlay ({c['span'][0].year}-{c['span'][1].year})", c))


if __name__ == "__main__":
    main()
