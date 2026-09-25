#!/usr/bin/env python3
"""Which industries did well while 10y >= 5% and 3m >= 4%, and in the year after?

Data (research/data/): Fama-French 12 value-weighted industry portfolios, monthly
(12_Industry_Portfolios.csv, Ken French library); FRED GS10 (10-year yield,
monthly avg), TB3MS (3-month bill), CPIAUCSL (CPI, for the inflation filter).

Regime month: GS10 >= --ten (5.0) and TB3MS >= --bill (4.0), optionally CPI
y/y >= --cpi. Episodes = runs of regime months (gaps of <= 2 months bridged).
For each episode: annualised industry return minus the market during the
episode, and over the 12 months after it ends. Also splits regime months by
whether the 10y was higher than 6 months earlier (rates rising vs falling).

Usage: python scripts/rate_regime_sectors.py [--ten 5] [--bill 4] [--cpi 3] [--since 1960]
"""
from __future__ import annotations

import argparse
import csv
import statistics as st
from pathlib import Path

D = Path(__file__).resolve().parent.parent / "research" / "data"
IND = ["NoDur", "Durbl", "Manuf", "Enrgy", "Chems", "BusEq", "Telcm", "Utils", "Shops", "Hlth", "Money", "Other"]
ETF = {"NoDur": "staples XLP", "Durbl": "autos/durables", "Manuf": "industrials XLI", "Enrgy": "energy XLE",
       "Chems": "materials XLB", "BusEq": "tech XLK", "Telcm": "telecom XLC", "Utils": "utilities XLU",
       "Shops": "retail XLY", "Hlth": "health XLV", "Money": "financials XLF", "Other": "other (transport, construction, services)"}


def ff12():
    rows = {}
    with (D / "12_Industry_Portfolios.csv").open() as f:
        block = 0
        for line in f:
            s = line.strip()
            if not s:
                continue
            if s.startswith("Average Value Weighted") or s.startswith("  Average Value"):
                block += 1; continue
            parts = [p.strip() for p in s.split(",")]
            if len(parts) == 13 and parts[0].isdigit() and len(parts[0]) == 6:
                if block <= 1:  # first block = value-weighted monthly
                    rows[parts[0]] = [float(x) / 100 for x in parts[1:]]
            elif parts[0].isdigit() and len(parts[0]) == 4:
                break  # annual blocks start
    return rows


def fred(name):
    out = {}
    with (D / f"{name}.csv").open() as f:
        for r in csv.DictReader(f):
            v = r[name]
            if v not in ("", "."):
                out[r["observation_date"][:7].replace("-", "")] = float(v)
    return out


def ann(rets):
    g = 1.0
    for r in rets: g *= 1 + r
    return g ** (12 / len(rets)) - 1 if rets else 0.0


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--ten", type=float, default=5.0); ap.add_argument("--bill", type=float, default=4.0)
    ap.add_argument("--cpi", type=float, default=None, help="also require CPI y/y >= this")
    ap.add_argument("--since", type=int, default=1960); ap.add_argument("--after", type=int, default=12)
    args = ap.parse_args()
    ind = ff12(); g10 = fred("GS10"); tb = fred("TB3MS"); cpi = fred("CPIAUCSL")
    months = sorted(m for m in ind if int(m[:4]) >= args.since and m in g10 and m in tb)
    # market proxy = value-weighted average of the 12 industries is not available; use equal-weight of 12 as "market"
    # (close to the VW market for sector comparisons; FF's Mkt-RF not bundled here)
    def cpi_yoy(m):
        y = str(int(m[:4]) - 1) + m[4:]
        return (cpi[m] / cpi[y] - 1) * 100 if m in cpi and y in cpi else None
    inreg = {}
    for m in months:
        ok = g10[m] >= args.ten and tb[m] >= args.bill
        if ok and args.cpi is not None:
            c = cpi_yoy(m); ok = c is not None and c >= args.cpi
        inreg[m] = ok
    # episodes with gaps <= 2 bridged
    eps = []; cur = []; gap = 0
    for m in months:
        if inreg[m]:
            cur.append(m); gap = 0
        elif cur:
            gap += 1
            if gap > 2:
                eps.append(cur); cur = []; gap = 0
    if cur: eps.append(cur)
    eps = [e for e in eps if len(e) >= 6]
    idx = {m: i for i, m in enumerate(months)}
    n_reg = sum(inreg.values())
    print(f"months {months[0]}-{months[-1]}: {n_reg} of {len(months)} in regime (10y >= {args.ten}%, 3m >= {args.bill}%"
          + (f", CPI y/y >= {args.cpi}%" if args.cpi is not None else "") + f"); {len(eps)} episodes of 6+ months")
    mkt = {m: st.fmean(ind[m]) for m in months}

    def table(label, sel):
        rows = []
        for k, name in enumerate(IND):
            ex = ann([ind[m][k] for m in sel]) - ann([mkt[m] for m in sel])
            rows.append((ex, name))
        return sorted(rows, reverse=True)

    print(f"\n{'episode':<18} {'mo':>3} {'10y':>5} {'3m':>5} {'CPI':>5} {'mkt/yr':>7} | best 3 during (excess/yr) | worst 3 during | mkt next {args.after}m | best 3 after | worst 3 after")
    agg_during = {n: [] for n in IND}; agg_after = {n: [] for n in IND}; mkts_after = []
    for e in eps:
        i1 = idx[e[-1]]
        after = months[i1 + 1: i1 + 1 + args.after]
        during = table("d", e); aft = table("a", after) if len(after) >= 6 else []
        for ex, n in during: agg_during[n].append(ex)
        for ex, n in aft: agg_after[n].append(ex)
        m_after = ann([mkt[m] for m in after]) if len(after) >= 6 else None
        if m_after is not None: mkts_after.append(m_after)
        c = [x for x in (cpi_yoy(m) for m in e) if x is not None]
        f3 = lambda t: " ".join(f"{n}{ex:+.0%}" for ex, n in t)
        print(f"{e[0][:4]}-{e[0][4:]}..{e[-1][:4]}-{e[-1][4:]} {len(e):>3} {st.fmean(g10[m] for m in e):>5.1f} {st.fmean(tb[m] for m in e):>5.1f} "
              f"{(st.fmean(c) if c else 0):>5.1f} {ann([mkt[m] for m in e]):>7.1%} | {f3(during[:3])} | {f3(during[-3:])} | "
              f"{(f'{m_after:+.1%}' if m_after is not None else '  n/a'):>8} | {f3(aft[:3])} | {f3(aft[-3:])}")

    print(f"\nAverage excess return vs the equal-weight market, across episodes (hit = share of episodes beating the market)")
    print(f"{'industry':<8} {'(ETF)':<34} {'during /yr':>10} {'hit':>5} {'after /yr':>10} {'hit':>5}")
    for n in IND:
        d, a = agg_during[n], agg_after[n]
        print(f"{n:<8} {ETF[n]:<34} {st.fmean(d):>+10.1%} {sum(x > 0 for x in d) / len(d):>5.0%} "
              f"{(st.fmean(a) if a else 0):>+10.1%} {(sum(x > 0 for x in a) / len(a)) if a else 0:>5.0%}")
    print(f"market itself: during {ann([mkt[m] for e in eps for m in e]):.1%}/yr over all regime months; "
          f"next {args.after}m after an episode averaged {st.fmean(mkts_after):+.1%}/yr" if mkts_after else "")

    # direction split inside the regime
    rising = [m for m in months if inreg[m] and idx[m] >= 6 and g10[m] > g10[months[idx[m] - 6]] + 0.25]
    falling = [m for m in months if inreg[m] and idx[m] >= 6 and g10[m] < g10[months[idx[m] - 6]] - 0.25]
    print(f"\nInside the regime, split by the 10y's 6-month direction: rising ({len(rising)} months, market {ann([mkt[m] for m in rising]):.1%}/yr) "
          f"vs falling ({len(falling)} months, market {ann([mkt[m] for m in falling]):.1%}/yr)")
    tr, tf = dict((n, ex) for ex, n in table("r", rising)), dict((n, ex) for ex, n in table("f", falling))
    print(f"{'industry':<8} {'rising 10y':>11} {'falling 10y':>12}")
    for n in sorted(IND, key=lambda n: -tr[n]):
        print(f"{n:<8} {tr[n]:>+11.1%} {tf[n]:>+12.1%}")


if __name__ == "__main__":
    main()
