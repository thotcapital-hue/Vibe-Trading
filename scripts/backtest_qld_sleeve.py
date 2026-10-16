#!/usr/bin/env python3
"""Independent re-test of the Grok "QLD Trend Sleeve" spec (research/external/2026-09-25-grok-qld-trend-sleeve.md).

Rules under test (all signals on QQQ daily ADJUSTED closes, applied with a
1-day lag: the stance for day t is decided by closes through t-1; the sleeve
then earns QLD's close-to-close return on day t; cash earns 0 unless --tbill):

  A   baseline: QQQ close > SMA200 -> 100% QLD, else cash.
  B   A plus overlay: while risk-on, QQQ close < SMA20 -> 50% QLD, back to 100% on reclaim.
  BH  buy and hold QLD / QQQ.

Extensions Grok did not run:
  A-scale   A traded the way the spec says it will be traded live: three equal
            tranches, T1 at the first risk-on, T2/T3 on a pullback of
            --pull % below the last fill / average fill OR after --weeks weeks.
  A-band    A with a hysteresis band: exit below SMA200*(1-b), re-enter above SMA200.
  R2a/R2b   Sanjay's ribbon rules (20-day HIGH/LOW bands vs 200-day HIGH/LOW bands
            on QQQ) driving the same QLD position.
  --costs   5 bp per unit of exposure change (Grok's own illustrative number).

Data: Yahoo chart API (stdlib urllib), cached to research/data/<SYM>.csv.

Usage:
    python scripts/backtest_qld_sleeve.py
    python scripts/backtest_qld_sleeve.py --costs --tbill
    python scripts/backtest_qld_sleeve.py --pull 0.15 --weeks 4
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import statistics as st
import urllib.request
from datetime import date, datetime, timezone
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "research" / "data"
YAHOO = "https://query1.finance.yahoo.com/v8/finance/chart/{sym}?period1=800000000&period2={p2}&interval=1d&events=splits,dividends"


# ---------------------------------------------------------------- data ----
def fetch_yahoo(sym: str) -> list[tuple[date, float, float, float, float]]:
    """(date, high, low, close, adjclose) daily rows, oldest first."""
    url = YAHOO.format(sym=sym, p2=int(datetime.now(timezone.utc).timestamp()) + 86400)
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        res = json.load(resp)["chart"]["result"][0]
    ts = res["timestamp"]
    q = res["indicators"]["quote"][0]
    adj = res["indicators"]["adjclose"][0]["adjclose"]
    rows = []
    for t, h, l, c, a in zip(ts, q["high"], q["low"], q["close"], adj):
        if None in (h, l, c, a):
            continue
        rows.append((datetime.fromtimestamp(t, tz=timezone.utc).date(), h, l, c, a))
    return rows


def load(sym: str, refresh: bool) -> list[tuple[date, float, float, float, float]]:
    DATA.mkdir(parents=True, exist_ok=True)
    f = DATA / f"{sym}.csv"
    if f.exists() and not refresh:
        with f.open() as fh:
            return [(date.fromisoformat(r["date"]), float(r["high"]), float(r["low"]),
                     float(r["close"]), float(r["adjclose"])) for r in csv.DictReader(fh)]
    rows = fetch_yahoo(sym)
    with f.open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["date", "high", "low", "close", "adjclose"])
        for r in rows:
            w.writerow([r[0].isoformat(), f"{r[1]:.6f}", f"{r[2]:.6f}", f"{r[3]:.6f}", f"{r[4]:.6f}"])
    return rows


def sma(x: list[float], n: int) -> list[float | None]:
    out: list[float | None] = [None] * len(x)
    s = 0.0
    for i, v in enumerate(x):
        s += v
        if i >= n:
            s -= x[i - n]
        if i >= n - 1:
            out[i] = s / n
    return out


# ------------------------------------------------------------- engine ----
def simulate(dates, ret, expo, cost=0.0, cash=None):
    """expo[t] = fraction of the sleeve in QLD on day t (decided before t opens).

    Returns dict with equity curve and metrics. cash[t] = daily cash yield (0 default).
    """
    eq = 1.0
    curve = [1.0]
    daily = []
    prev = 0.0
    trades = 0.0
    for t in range(len(ret)):
        e = expo[t]
        turnover = abs(e - prev)
        trades += turnover
        eq *= 1 - cost * turnover
        r = e * ret[t] + (1 - e) * (cash[t] if cash else 0.0)
        eq *= 1 + r
        daily.append(eq / curve[-1] - 1)
        curve.append(eq)
        prev = e
    n = len(ret)
    yrs = n / 252
    cagr = eq ** (1 / yrs) - 1
    peak, mdd, dd_start, dd_trough, cur_start = 1.0, 0.0, None, None, dates[0]
    trough_date = None
    for i, v in enumerate(curve[1:]):
        if v >= peak:
            peak, cur_start = v, dates[i]
        d = v / peak - 1
        if d < mdd:
            mdd, dd_start, trough_date = d, cur_start, dates[i]
    mu, sd = st.fmean(daily), st.pstdev(daily)
    sharpe = mu / sd * math.sqrt(252) if sd else 0.0
    # full exits: exposure goes from >0 to 0
    exits = sum(1 for t in range(1, n) if expo[t] == 0 and expo[t - 1] > 0)
    return dict(cagr=cagr, mdd=mdd, sharpe=sharpe, calmar=cagr / abs(mdd) if mdd else 0,
                vol=sd * math.sqrt(252), expo=st.fmean(expo), exits=exits, turnover=trades,
                curve=curve, daily=daily, dd_start=dd_start, dd_trough=trough_date, end=eq)


def worst_drawdowns(dates, curve, k=5):
    """Top-k peak-to-trough drawdowns with dates (non-overlapping episodes)."""
    eps = []
    peak, pi = curve[1], 0
    trough, ti = curve[1], 0
    for i in range(1, len(curve) - 1):
        v = curve[i + 1]
        if v >= peak:
            if trough < peak:
                eps.append((trough / peak - 1, dates[pi], dates[ti], dates[i]))
            peak, pi, trough, ti = v, i, v, i
        elif v < trough:
            trough, ti = v, i
    if trough < peak:
        eps.append((trough / peak - 1, dates[pi], dates[ti], None))
    return sorted(eps)[:k]


def yearly(dates, daily):
    out: dict[int, float] = {}
    for d, r in zip(dates, daily):
        out[d.year] = out.get(d.year, 1.0) * (1 + r)
    return {y: v - 1 for y, v in out.items()}


# ------------------------------------------------------------- rules ----
def expo_sma200(sig, s200, lag=1, band=0.0):
    """Risk-on when signal close > SMA200 (with optional exit band), 1-day lag."""
    n = len(sig)
    e = [0.0] * n
    on = False
    for t in range(n):
        j = t - lag
        if j < 0 or s200[j] is None:
            continue
        if on:
            on = sig[j] > s200[j] * (1 - band)
        else:
            on = sig[j] > s200[j]
        e[t] = 1.0 if on else 0.0
    return e


def expo_overlay(sig, s200, s20):
    base = expo_sma200(sig, s200)
    e = list(base)
    for t in range(len(sig)):
        j = t - 1
        if base[t] and j >= 0 and s20[j] is not None and sig[j] < s20[j]:
            e[t] = 0.5
    return e


def expo_scale(sig, s200, qld, pull, days):
    """Grok's live tranche rules on top of the SMA200 gate.

    T1 at first risk-on day; T2 when QLD <= T1 fill*(1-pull) or `days` trading
    days after T1; T3 when QLD <= avg fill*(1-pull) or `days` after T2. Fills
    at the close of the day the trigger is seen (next-day stance, like the gate).
    """
    gate = expo_sma200(sig, s200)
    n = len(sig)
    e = [0.0] * n
    fills: list[float] = []
    last_fill_day = None
    for t in range(n):
        if not gate[t]:
            fills, last_fill_day = [], None
            continue
        j = t - 1  # decision uses information through t-1
        if not fills:
            fills, last_fill_day = [qld[j]], j
        elif len(fills) < 3:
            ref = fills[0] if len(fills) == 1 else st.fmean(fills)
            if qld[j] <= ref * (1 - pull) or j - last_fill_day >= days:
                fills.append(qld[j])
                last_fill_day = j
        e[t] = len(fills) / 3
    return e


def expo_ribbon(hi, lo, variant):
    """Sanjay's ribbon rules on the SIGNAL series (QQQ highs/lows), 1-day lag.

    2a early in / early out: enter 20H > 200L (from below), exit 20L < 200H (from above).
    2b fully clear:          enter 20L > 200H, exit 20H < 200L.
    """
    h20, l20, h200, l200 = sma(hi, 20), sma(lo, 20), sma(hi, 200), sma(lo, 200)
    n = len(hi)
    e = [0.0] * n
    on = False
    for t in range(n):
        j = t - 1
        if j < 0 or h200[j] is None:
            continue
        above = l20[j] > h200[j]
        below = h20[j] < l200[j]
        if variant == "2b":
            on = True if above else (False if below else on)
        else:  # 2a
            if on and l20[j] < h200[j]:
                on = False
            elif not on and h20[j] > l200[j]:
                on = True
        e[t] = 1.0 if on else 0.0
    return e


# --------------------------------------------------------------- main ----
def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--refresh", action="store_true", help="re-download from Yahoo")
    ap.add_argument("--costs", action="store_true", help="5 bp per unit of exposure change")
    ap.add_argument("--tbill", action="store_true", help="cash earns 3-month T-bill (approx by year)")
    ap.add_argument("--pull", type=float, default=0.10, help="scale-in pullback trigger (0.10 = 10%%)")
    ap.add_argument("--weeks", type=float, default=3, help="scale-in time trigger in weeks")
    ap.add_argument("--band", type=float, default=0.03, help="hysteresis exit band for A-band")
    ap.add_argument("--start", default="2007-04-10")
    ap.add_argument("--raw-signal", action="store_true", help="SMA200 on unadjusted QQQ closes")
    args = ap.parse_args()

    qqq = load("QQQ", args.refresh)
    qld = load("QLD", args.refresh)
    common = sorted(set(r[0] for r in qqq) & set(r[0] for r in qld))
    qd = {r[0]: r for r in qqq}
    ld = {r[0]: r for r in qld}
    dates = common
    sig = [qd[d][4] if not args.raw_signal else qd[d][3] for d in dates]
    qhi = [qd[d][1] * qd[d][4] / qd[d][3] for d in dates]   # adjust highs/lows by the same factor
    qlo = [qd[d][2] * qd[d][4] / qd[d][3] for d in dates]
    qld_adj = [ld[d][4] for d in dates]
    qqq_adj = [qd[d][4] for d in dates]
    s200, s20 = sma(sig, 200), sma(sig, 20)

    start = date.fromisoformat(args.start)
    i0 = next(i for i, d in enumerate(dates) if d >= start)
    assert s200[i0 - 1] is not None, "SMA200 undefined at start"
    # returns for day t (index i in the sliced arrays refers to dates[i0 + i])
    R = [qld_adj[i] / qld_adj[i - 1] - 1 for i in range(i0, len(dates))]
    RQ = [qqq_adj[i] / qqq_adj[i - 1] - 1 for i in range(i0, len(dates))]
    D = dates[i0:]
    cost = 5e-4 if args.costs else 0.0
    cash = None
    if args.tbill:
        # rough 3-month T-bill by year (annual %), plenty for a "cash earned something" check
        tb = {2007: 4.4, 2008: 1.4, 2009: 0.15, 2010: 0.14, 2011: 0.05, 2012: 0.09, 2013: 0.06,
              2014: 0.03, 2015: 0.05, 2016: 0.32, 2017: 0.93, 2018: 1.94, 2019: 2.06, 2020: 0.37,
              2021: 0.04, 2022: 2.0, 2023: 5.1, 2024: 5.0, 2025: 4.2, 2026: 3.8}
        cash = [tb.get(d.year, 3.0) / 100 / 252 for d in D]

    def sl(x):
        return x[i0:]

    strategies = {
        "A  SMA200 -> QLD (Grok baseline)": sl(expo_sma200(sig, s200)),
        "B  A + SMA20 50% overlay": sl(expo_overlay(sig, s200, s20)),
        "BH QLD": [1.0] * len(R),
        f"A-scale  tranches {args.pull:.0%}/{args.weeks:g}wk": sl(expo_scale(sig, s200, qld_adj, args.pull, int(args.weeks * 5))),
        f"A-band  exit {args.band:.0%} below SMA200": sl(expo_sma200(sig, s200, band=args.band)),
        "R2a ribbon early in/out -> QLD": sl(expo_ribbon(qhi, qlo, "2a")),
        "R2b ribbon fully clear -> QLD": sl(expo_ribbon(qhi, qlo, "2b")),
    }
    results = {k: simulate(D, R, v, cost, cash) for k, v in strategies.items()}
    results["BH QQQ"] = simulate(D, RQ, [1.0] * len(RQ), 0.0, None)
    results["A  SMA200 -> QQQ (1x, same gate)"] = simulate(D, RQ, strategies["A  SMA200 -> QLD (Grok baseline)"], cost, cash)

    print(f"sample {D[0]} -> {D[-1]}  ({len(R)} trading days)  costs={'5bp' if cost else 'none'}  "
          f"cash={'T-bill' if cash else '0'}  signal={'raw' if args.raw_signal else 'adjusted'} QQQ closes")
    print(f"today: QQQ {qd[dates[-1]][3]:.2f}  SMA200(adj) {s200[-1]:.2f}  SMA20(adj) {s20[-1]:.2f}  "
          f"QLD {ld[dates[-1]][3]:.2f}")
    print(f"\n{'strategy':<42} {'CAGR':>6} {'MaxDD':>7} {'Sharpe':>6} {'Calmar':>6} {'vol':>6} {'expo':>5} {'exits':>5} {'$100k->':>10}")
    for k, r in results.items():
        print(f"{k:<42} {r['cagr']:>6.1%} {r['mdd']:>7.1%} {r['sharpe']:>6.2f} {r['calmar']:>6.2f} "
              f"{r['vol']:>6.1%} {r['expo']:>5.0%} {r['exits']:>5d} {100000 * r['end']:>10,.0f}")

    # sub-periods for A and B (Grok table 8.2)
    periods = [("GFC", "2007-04-10", "2009-12-31"), ("2010-2019", "2010-01-04", "2019-12-31"),
               ("2020-2022", "2020-01-02", "2022-12-30"), ("2023-now", "2023-01-03", "2099-01-01")]
    print(f"\n{'period':<10} {'A CAGR':>7} {'B CAGR':>7} {'A MaxDD':>8} {'B MaxDD':>8} {'A Sh':>5} {'B Sh':>5}  scale CAGR/MaxDD")
    for name, a, b in periods:
        a, b = date.fromisoformat(a), date.fromisoformat(b)
        idx = [i for i, d in enumerate(D) if a <= d <= b]
        if not idx:
            continue
        s, e = idx[0], idx[-1] + 1
        ra = simulate(D[s:e], R[s:e], strategies["A  SMA200 -> QLD (Grok baseline)"][s:e], cost, cash[s:e] if cash else None)
        rb = simulate(D[s:e], R[s:e], strategies["B  A + SMA20 50% overlay"][s:e], cost, cash[s:e] if cash else None)
        rs = simulate(D[s:e], R[s:e], list(strategies.values())[3][s:e], cost, cash[s:e] if cash else None)
        print(f"{name:<10} {ra['cagr']:>7.1%} {rb['cagr']:>7.1%} {ra['mdd']:>8.1%} {rb['mdd']:>8.1%} "
              f"{ra['sharpe']:>5.2f} {rb['sharpe']:>5.2f}  {rs['cagr']:.1%} / {rs['mdd']:.1%}")

    # anatomy of the baseline's worst drawdowns
    print("\nA baseline: five worst peak-to-trough drawdowns")
    for dd, p, t, rec in worst_drawdowns(D, results["A  SMA200 -> QLD (Grok baseline)"]["curve"]):
        print(f"  {dd:>7.1%}  peak {p}  trough {t}  recovered {rec or 'not yet'}")

    # calendar years
    ya = yearly(D, results["A  SMA200 -> QLD (Grok baseline)"]["daily"])
    ys = yearly(D, list(results.values())[3]["daily"])
    yq = yearly(D, results["BH QQQ"]["daily"])
    yl = yearly(D, results["BH QLD"]["daily"])
    print(f"\n{'year':<6} {'A':>7} {'A-scale':>8} {'BH QQQ':>7} {'BH QLD':>7}")
    for y in sorted(ya):
        print(f"{y:<6} {ya[y]:>7.1%} {ys[y]:>8.1%} {yq[y]:>7.1%} {yl[y]:>7.1%}")

    # whipsaw census: round trips of the baseline gate
    gate = strategies["A  SMA200 -> QLD (Grok baseline)"]
    trips = []
    entry_i = None
    for t in range(1, len(gate)):
        if gate[t] and not gate[t - 1]:
            entry_i = t
        elif not gate[t] and gate[t - 1] and entry_i is not None:
            pnl = 1.0
            for k in range(entry_i, t):
                pnl *= 1 + R[k]
            trips.append((D[entry_i], D[t], t - entry_i, pnl - 1))
    if gate[-1] and entry_i is not None:
        pnl = 1.0
        for k in range(entry_i, len(R)):
            pnl *= 1 + R[k]
        trips.append((D[entry_i], None, len(R) - entry_i, pnl - 1))
    wins = [x for x in trips if x[3] > 0]
    short = [x for x in trips if x[2] <= 10]
    print(f"\nA baseline round trips: {len(trips)}  winners {len(wins)}  "
          f"median hold {st.median(x[2] for x in trips):.0f} days  "
          f"trips <= 10 days: {len(short)} (avg {st.fmean(x[3] for x in short):+.1%})")
    print(f"  total from winners {sum(x[3] for x in wins):+.1%} of sleeve-units; "
          f"from losers {sum(x[3] for x in trips if x[3] <= 0):+.1%}")
    print("  largest 5 losing trips:")
    for a, b, n, p in sorted(trips, key=lambda x: x[3])[:5]:
        print(f"    {a} -> {b}  {n:>3} days  {p:+.1%}")


if __name__ == "__main__":
    main()
