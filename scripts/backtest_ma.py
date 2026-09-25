#!/usr/bin/env python3
"""Backtest moving-average trend rules on daily bars (Rule 1 and Rule 2 family).

Rule 1   long when 20-DMA(close) > 200-DMA(close); flat otherwise.
Rule 2   ribbon rules using averages of HIGHS and LOWS:
  2a  early in / early out (Sanjay): enter when the 20-day HIGH average rises
      above the 200-day LOW average (bands start to touch, coming from fully
      below); exit when the 20-day LOW average falls below the 200-day HIGH
      average (bands start to overlap, coming from fully above). Inside the
      overlap zone the position is held unchanged.
  2b  fully clear both ways: enter when 20L > 200H; exit when 20H < 200L.
  2c  early in, late out: enter as 2a; exit only when 20H < 200L.
  2d  early out, safe re-entry: exit as 2a; (re-)enter only when 20L > 200H.
Also measures whether the 2a exit ("early warning") carries information:
average next-20-day return of the underlying after an exit signal vs. all days.

Long-only, flat when false, cost 0.05% per side, signal on close, fill at
next close. Prices split-adjusted.

Usage: python scripts/backtest_ma.py [--years 6] [SYMS ...]
"""
from __future__ import annotations

import argparse
import statistics as st
from datetime import datetime, timedelta, timezone

from alpaca_rest import AlpacaREST
from spread_scan import load_keys

DEFAULT = ["SPY", "QQQ", "IWM", "AAPL", "MSFT", "GOOGL", "META", "AMZN", "NVDA", "AVGO", "AMD",
           "JPM", "XLE", "XLU", "XLP", "XLV", "TLT", "GLD", "COST", "WMT"]
COST = 5e-4


def sma_series(x: list[float], n: int) -> list[float | None]:
    out: list[float | None] = [None] * len(x)
    s = 0.0
    for i, v in enumerate(x):
        s += v
        if i >= n:
            s -= x[i - n]
        if i >= n - 1:
            out[i] = s / n
    return out


def run(c: list[float], want_fn, n0: int = 200):
    """want_fn(i, pos) -> 0/1 desired position after close i."""
    eq = 1.0; pos = 0; trades = []; entry = None; peak = 1.0; mdd = 0.0; din = 0; exits = []
    for i in range(n0, len(c) - 1):
        want = want_fn(i, pos)
        if want != pos:
            eq *= 1 - COST
            if want:
                entry = c[i + 1]
            else:
                trades.append(c[i + 1] / entry - 1); exits.append(i)
            pos = want
        if pos:
            eq *= c[i + 1] / c[i]; din += 1
        peak = max(peak, eq); mdd = min(mdd, eq / peak - 1)
    if pos and entry:
        trades.append(c[-1] / entry - 1)
    yrs = (len(c) - n0) / 252
    return dict(cagr=eq ** (1 / yrs) - 1, mdd=mdd, n=len(trades),
                win=(sum(t > 0 for t in trades) / len(trades)) if trades else 0.0,
                tin=din / (len(c) - n0), exits=exits)


def buy_hold(c: list[float], n0: int = 200):
    p = c[n0]; m = 0.0
    for v in c[n0:]:
        p = max(p, v); m = min(m, v / p - 1)
    return (c[-1] / c[n0]) ** (252 / (len(c) - n0)) - 1, m


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("symbols", nargs="*")
    ap.add_argument("--years", type=int, default=6)
    args = ap.parse_args()
    syms = [s.upper() for s in args.symbols] or DEFAULT
    cli = AlpacaREST(*load_keys())
    bars = cli.bars(syms, datetime.now(timezone.utc) - timedelta(days=365 * args.years + 30), "1Day")

    rules = ["1: 20c > 200c", "2a: early in/early out", "2b: fully clear both ways",
             "2c: early in, exit fully below", "2d: early out, re-enter fully above"]
    agg: dict[str, list] = {r: [] for r in rules}
    bh_all = []
    warn_fwd: list[float] = []; all_fwd: list[float] = []
    for s in syms:
        b = bars.get(s)
        if not b or len(b) < 260:
            continue
        c = [float(x["c"]) for x in b]; h = [float(x["h"]) for x in b]; lo = [float(x["l"]) for x in b]
        c20, c200 = sma_series(c, 20), sma_series(c, 200)
        h20, l20 = sma_series(h, 20), sma_series(lo, 20)
        h200, l200 = sma_series(h, 200), sma_series(lo, 200)

        def zone(i):  # ribbon relationship
            if l20[i] > h200[i]:
                return "above"
            if h20[i] < l200[i]:
                return "below"
            return "overlap"

        r1 = lambda i, pos: int(c20[i] > c200[i])  # noqa: E731

        def r2a(i, pos):
            z, zp = zone(i), zone(i - 1)
            if zp == "below" and z != "below":
                return 1
            if zp == "above" and z != "above":
                return 0
            return pos

        def r2b(i, pos):
            z = zone(i)
            return 1 if z == "above" else (0 if z == "below" else pos)

        def r2c(i, pos):
            z, zp = zone(i), zone(i - 1)
            if zp == "below" and z != "below":
                return 1
            if z == "below":
                return 0
            return pos

        def r2d(i, pos):
            z, zp = zone(i), zone(i - 1)
            if zp == "above" and z != "above":
                return 0
            if z == "above":
                return 1
            if z == "below":
                return 0
            return pos

        res = {rules[0]: run(c, r1), rules[1]: run(c, r2a), rules[2]: run(c, r2b),
               rules[3]: run(c, r2c), rules[4]: run(c, r2d)}
        bh = buy_hold(c); bh_all.append(bh)
        for r in rules:
            agg[r].append((res[r], bh))
        for i in res[rules[1]]["exits"]:
            if i + 21 < len(c):
                warn_fwd.append(c[i + 21] / c[i + 1] - 1)
        for i in range(200, len(c) - 21):
            all_fwd.append(c[i + 21] / c[i + 1] - 1)
        print(f"{s:<6} B&H {bh[0]:>6.1%} MDD {bh[1]:>6.1%} | " + " | ".join(
            f"{r.split(':')[0]} {res[r]['cagr']:>6.1%}/{res[r]['mdd']:>6.1%} n{res[r]['n']:>2}" for r in rules))

    n = len(bh_all)
    print(f"\n{'rule':<38} {'avg CAGR':>8} {'B&H':>6} {'avg MDD':>8} {'B&H MDD':>8} {'trades':>6} {'win%':>5} {'time in':>7} {'beat B&H':>8} {'lower DD':>8}")
    for r in rules:
        rows = agg[r]
        print(f"{r:<38} {st.mean(x['cagr'] for x, _ in rows):>8.1%} {st.mean(b[0] for _, b in rows):>6.1%} "
              f"{st.mean(x['mdd'] for x, _ in rows):>8.1%} {st.mean(b[1] for _, b in rows):>8.1%} "
              f"{st.mean(x['n'] for x, _ in rows):>6.1f} {st.mean(x['win'] for x, _ in rows):>5.0%} "
              f"{st.mean(x['tin'] for x, _ in rows):>7.0%} {sum(x['cagr'] > b[0] for x, b in rows):>5}/{n:<2} {sum(x['mdd'] > b[1] for x, b in rows):>5}/{n}")
    if warn_fwd:
        print(f"\nEARLY-WARNING TEST (rule 2a exits): next-20-day return after an exit signal "
              f"avg {st.mean(warn_fwd):+.2%} (median {st.median(warn_fwd):+.2%}, {sum(v < 0 for v in warn_fwd) / len(warn_fwd):.0%} negative, n={len(warn_fwd)})  "
              f"vs all days avg {st.mean(all_fwd):+.2%} ({sum(v < 0 for v in all_fwd) / len(all_fwd):.0%} negative)")


if __name__ == "__main__":
    main()
