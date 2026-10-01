#!/usr/bin/env python3
"""Do Indian-founded / Indian-led US companies beat the S&P 500? A fair version of the test.

Why not "5-year trailing return of today's list": a list assembled from videos about
companies that already did well is picked on the outcome. The fair test measures each
stock only DURING the tenure of the Indian-origin CEO/founder (from the day they took
charge, or the IPO date for founder-led firms) and compares it with the S&P 500 and the
Nasdaq-100 over the same days. It includes the disappointments, not just the winners.

CEO start/end dates are from public knowledge and MUST be verified before relying on
the result (column `verify`). Nationality is a judgement; borderline cases are listed
in CONTROLS and kept out of the main basket.

Usage: python scripts/indian_led_study.py
"""
from __future__ import annotations

import math
import statistics as st
from datetime import date

from backtest_qld_sleeve import load

# ticker, name, role, start, end(None = still in role)
MAIN = [
    ("MSFT", "Microsoft", "Nadella CEO", date(2014, 2, 4), None),
    ("GOOGL", "Alphabet/Google", "Pichai CEO", date(2015, 10, 2), None),
    ("ADBE", "Adobe", "Narayen CEO", date(2007, 12, 1), None),
    ("IBM", "IBM", "Krishna CEO", date(2020, 4, 6), None),
    ("ANET", "Arista", "Ullal CEO (IPO)", date(2014, 6, 6), None),
    ("PANW", "Palo Alto Networks", "Arora CEO", date(2018, 6, 6), None),
    ("ZS", "Zscaler", "Chaudhry founder (IPO)", date(2018, 3, 16), None),
    ("MU", "Micron", "Mehrotra CEO", date(2017, 5, 4), None),
    ("NTAP", "NetApp", "Kurian CEO", date(2015, 6, 1), None),
    ("CDNS", "Cadence", "Devgan CEO", date(2021, 12, 15), None),
    ("SBUX", "Starbucks", "Narasimhan CEO", date(2023, 3, 20), date(2024, 8, 13)),
    ("CTSH", "Cognizant", "Kumar CEO", date(2023, 1, 1), None),
    ("NTNX", "Nutanix", "Ramaswami CEO", date(2020, 12, 15), None),
    ("MDB", "MongoDB", "Ittycheria CEO (IPO)", date(2017, 10, 19), date(2025, 11, 10)),
    ("SNOW", "Snowflake", "Ramaswamy CEO", date(2024, 2, 28), None),
    ("HON", "Honeywell", "Kapur CEO", date(2023, 6, 1), None),
    ("FRSH", "Freshworks", "Mathrubootham founder (IPO)", date(2021, 9, 22), None),
    ("RBRK", "Rubrik", "Sinha founder (IPO)", date(2024, 4, 25), None),
    ("MA", "Mastercard", "Banga CEO", date(2010, 7, 1), date(2021, 12, 31)),
    ("PEP", "PepsiCo", "Nooyi CEO", date(2006, 10, 1), date(2018, 10, 3)),
]
CONTROLS = [
    ("UBER", "Uber", "Khosrowshahi is Iranian-American, NOT Indian", date(2019, 5, 10), None),
    ("WDAY", "Workday", "Bhusri heritage unverified; non-Indian CEO 2020-26", date(2012, 10, 12), None),
]


def series(sym):
    rows = load(sym, False)
    return {r[0]: r[4] for r in rows}


def cagr(vals):
    n = len(vals) - 1
    return (vals[-1] / vals[0]) ** (252 / n) - 1 if n > 0 and vals[0] > 0 else float("nan")


def window(px, start, end):
    ds = sorted(d for d in px if d >= start and (end is None or d <= end))
    return ds


def stats(daily):
    eq = 1.0; peak = 1.0; mdd = 0.0
    for r in daily:
        eq *= 1 + r; peak = max(peak, eq); mdd = min(mdd, eq / peak - 1)
    n = len(daily); sd = st.pstdev(daily)
    return eq ** (252 / n) - 1, mdd, (st.fmean(daily) / sd * math.sqrt(252)) if sd else 0.0


def main():
    load("SPY", True); load("QQQ", True)
    spy, qqq = series("SPY"), series("QQQ")
    today = max(spy)
    print(f"through {today}. Excess = company CAGR minus index CAGR over the SAME days.\n")
    print(f"{'company':<20}{'role':<28}{'from':<12}{'yrs':>5}{'CAGR':>8}{'SPY':>8}{'QQQ':>8}{'vs SPY':>8}{'vs QQQ':>8}  {'last5y':>7}{'SPY5y':>7}")
    res = {}
    for group, label in ((MAIN, "MAIN"), (CONTROLS, "CONTROLS (not Indian-led or unverified)")):
        if group is CONTROLS: print(f"--- {label}")
        for t, name, role, s, e in group:
            try:
                px = series(t)
            except Exception as ex:
                print(f"{name:<20} no data ({ex})"); continue
            ds = [d for d in window(px, s, e) if d in spy and d in qqq]
            if len(ds) < 60: print(f"{name:<20} too short"); continue
            c = cagr([px[d] for d in ds]); cs = cagr([spy[d] for d in ds]); cq = cagr([qqq[d] for d in ds])
            d5 = [d for d in sorted(px) if d >= date(today.year - 5, today.month, min(today.day, 28)) and d in spy]
            c5 = cagr([px[d] for d in d5]) if len(d5) > 200 else float("nan"); s5 = cagr([spy[d] for d in d5])
            res[t] = (ds, c, cs, cq)
            print(f"{name:<20}{role[:27]:<28}{ds[0]!s:<12}{len(ds) / 252:>5.1f}{c:>8.1%}{cs:>8.1%}{cq:>8.1%}{c - cs:>+8.1%}{c - cq:>+8.1%}  {c5:>7.1%}{s5:>7.1%}")
    main_t = [t for t, *_ in MAIN if t in res]
    wins_spy = sum(res[t][1] > res[t][2] for t in main_t); wins_qqq = sum(res[t][1] > res[t][3] for t in main_t)
    print(f"\nMAIN list: {len(main_t)} companies. Beat SPY during the tenure: {wins_spy}; beat QQQ: {wins_qqq}.")
    ex = [res[t][1] - res[t][2] for t in main_t]
    print(f"Excess vs SPY: median {st.median(ex):+.1%}, mean {st.fmean(ex):+.1%}; vs QQQ median {st.median([res[t][1] - res[t][3] for t in main_t]):+.1%}")

    # tenure-matched equal-weight basket, daily rebalanced, active only while the leader is in charge
    days = sorted(d for d in spy if d >= date(2008, 1, 2))
    price = {t: series(t) for t in main_t}
    basket = []; bd = []
    for i in range(1, len(days)):
        d0, d1 = days[i - 1], days[i]
        rs = []
        for tt in MAIN:
            t = tt[0]
            if t not in res:
                continue
            if d0 >= tt[3] and (tt[4] is None or d1 <= tt[4]) and d0 in price[t] and d1 in price[t]:
                rs.append(price[t][d1] / price[t][d0] - 1)
        if rs:
            basket.append(st.fmean(rs)); bd.append(d1)
    idx = {d: i for i, d in enumerate(days)}
    sp = [spy[d] / spy[days[idx[d] - 1]] - 1 for d in bd]; qq = [qqq[d] / qqq[days[idx[d] - 1]] - 1 for d in bd]
    print(f"\nTenure-matched equal-weight basket ({bd[0]} to {bd[-1]}), names enter at the leader's start and leave at the end:")
    print(f"{'':<22}{'CAGR':>7}{'MaxDD':>8}{'Sharpe':>7}")
    for name, s in (("Indian-led basket", basket), ("SPY", sp), ("QQQ", qq)):
        c, m, sh = stats(s); print(f"{name:<22}{c:>7.1%}{m:>8.1%}{sh:>7.2f}")
    # alpha / beta vs QQQ and SPY
    for nm, bench in (("QQQ", qq), ("SPY", sp)):
        mb, mx = st.fmean(basket), st.fmean(bench)
        beta = sum((a - mx) * (b - mb) for a, b in zip(bench, basket)) / sum((a - mx) ** 2 for a in bench)
        alpha = (mb - beta * mx) * 252
        print(f"vs {nm}: beta {beta:.2f}, annual alpha {alpha:+.1%}")


if __name__ == "__main__":
    main()
