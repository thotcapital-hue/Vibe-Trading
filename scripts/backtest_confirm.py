#!/usr/bin/env python3
"""Does requiring a 'decisive' close past the 200-DMA improve a trend rule?

Part A (daily bars, 6y, 20 names): long when price is above the 200-DMA.
  Confirmation grid: margin m (close must be m% beyond the average) x
  n consecutive daily closes. Exit mirrors entry (n closes m% below).
Part B (hourly bars, 2y, 10 names): same idea using intraday closes vs the
  daily 200-DMA (carried from the prior close): first hourly close above,
  decisive close (0.3% above), 2 or 3 consecutive hourly closes above, vs the
  daily-close baseline. Exit mirrors.
Reports CAGR, max drawdown, trades/yr (whipsaw count), win rate, beat B&H.

Usage: python scripts/backtest_confirm.py [--part A|B|AB]
"""
from __future__ import annotations

import argparse
import statistics as st
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from alpaca_rest import AlpacaREST
from spread_scan import load_keys

DAILY_SYMS = ["SPY", "QQQ", "IWM", "AAPL", "MSFT", "GOOGL", "META", "AMZN", "NVDA", "AVGO", "AMD",
              "JPM", "XLE", "XLU", "XLP", "XLV", "TLT", "GLD", "COST", "WMT"]
HOURLY_SYMS = ["SPY", "QQQ", "AAPL", "MSFT", "NVDA", "META", "GOOGL", "AMZN", "XLE", "XLP"]
COST = 5e-4
NY = ZoneInfo("America/New_York")


def sma_series(x, n):
    out = [None] * len(x); s = 0.0
    for i, v in enumerate(x):
        s += v
        if i >= n:
            s -= x[i - n]
        if i >= n - 1:
            out[i] = s / n
    return out


def simulate(closes, line, margin, need, per_year):
    """Long when `need` consecutive closes > line*(1+margin); flat after `need` closes < line*(1-margin)."""
    eq = 1.0; pos = 0; up = dn = 0; trades = []; entry = None; peak = 1.0; mdd = 0.0; n0 = None
    for i in range(len(closes) - 1):
        if line[i] is None:
            continue
        if n0 is None:
            n0 = i
        c = closes[i]
        up = up + 1 if c > line[i] * (1 + margin) else 0
        dn = dn + 1 if c < line[i] * (1 - margin) else 0
        want = pos
        if not pos and up >= need:
            want = 1
        elif pos and dn >= need:
            want = 0
        if want != pos:
            eq *= 1 - COST
            if want:
                entry = closes[i + 1]
            else:
                trades.append(closes[i + 1] / entry - 1)
            pos = want
        if pos:
            eq *= closes[i + 1] / closes[i]
        peak = max(peak, eq); mdd = min(mdd, eq / peak - 1)
    if pos and entry:
        trades.append(closes[-1] / entry - 1)
    yrs = (len(closes) - (n0 or 0)) / per_year
    bh = (closes[-1] / closes[n0]) ** (1 / yrs) - 1
    p = closes[n0]; bmdd = 0.0
    for v in closes[n0:]:
        p = max(p, v); bmdd = min(bmdd, v / p - 1)
    return dict(cagr=eq ** (1 / yrs) - 1, mdd=mdd, tpy=len(trades) / yrs,
                win=(sum(t > 0 for t in trades) / len(trades)) if trades else 0.0, bh=bh, bmdd=bmdd)


def report(title, results):
    print(f"\n=== {title}")
    print(f"{'confirmation':<34} {'avg CAGR':>8} {'B&H':>6} {'avg MDD':>8} {'B&H MDD':>8} {'trades/yr':>9} {'win%':>5} {'beat B&H':>8} {'lower DD':>8}")
    for name, rows in results:
        n = len(rows)
        print(f"{name:<34} {st.mean(r['cagr'] for r in rows):>8.1%} {st.mean(r['bh'] for r in rows):>6.1%} "
              f"{st.mean(r['mdd'] for r in rows):>8.1%} {st.mean(r['bmdd'] for r in rows):>8.1%} "
              f"{st.mean(r['tpy'] for r in rows):>9.1f} {st.mean(r['win'] for r in rows):>5.0%} "
              f"{sum(r['cagr'] > r['bh'] for r in rows):>5}/{n:<2} {sum(r['mdd'] > r['bmdd'] for r in rows):>5}/{n}")


def part_a(cli):
    bars = cli.bars(DAILY_SYMS, datetime.now(timezone.utc) - timedelta(days=365 * 6 + 30), "1Day")
    grid = [(0.0, 1), (0.0, 2), (0.0, 3), (0.0, 5), (0.005, 1), (0.005, 3), (0.01, 1), (0.01, 3), (0.02, 1), (0.02, 3)]
    results = []
    for m, n in grid:
        rows = []
        for s in DAILY_SYMS:
            c = [float(x["c"]) for x in bars[s]]
            rows.append(simulate(c, sma_series(c, 200), m, n, 252))
        results.append((f"daily: {n} close(s) {m:.1%} beyond 200-DMA", rows))
    report("PART A  daily closes vs 200-DMA, 6 years, 20 names", results)


def part_b(cli):
    start = datetime.now(timezone.utc) - timedelta(days=365 * 2)
    daily = cli.bars(HOURLY_SYMS, start - timedelta(days=330), "1Day")
    hourly = cli.bars(HOURLY_SYMS, start, "1Hour")
    variants = [("hourly: 1st close above", 0.0, 1), ("hourly: decisive close 0.3% above", 0.003, 1),
                ("hourly: 2 consecutive closes above", 0.0, 2), ("hourly: 3 consecutive closes above", 0.0, 3),
                ("hourly: 0.3% AND 2 closes", 0.003, 2)]
    results = {v[0]: [] for v in variants}
    results["daily close (baseline)"] = []
    results["daily: 2 closes 0.5% beyond"] = []
    for s in HOURLY_SYMS:
        d = daily[s]; dc = [float(x["c"]) for x in d]; m200 = sma_series(dc, 200)
        days = [x["t"][:10] for x in d]
        import bisect
        H = []; L = []
        for x in hourly[s]:
            t = datetime.fromisoformat(x["t"].replace("Z", "+00:00")).astimezone(NY)
            if (t.hour, t.minute) >= (9, 30) and t.hour < 16:
                k = bisect.bisect_left(days, t.strftime("%Y-%m-%d")) - 1
                if k >= 0 and m200[k] is not None:
                    H.append(float(x["c"])); L.append(m200[k])
        per_year = len(H) / 2.0
        for name, m, n in variants:
            results[name].append(simulate(H, L, m, n, per_year))
        # daily baselines on the same 2-year window
        i0 = bisect.bisect_left(days, start.strftime("%Y-%m-%d"))
        dc2 = dc[i0:]; l2 = m200[i0:]
        results["daily close (baseline)"].append(simulate(dc2, l2, 0.0, 1, 252))
        results["daily: 2 closes 0.5% beyond"].append(simulate(dc2, l2, 0.005, 2, 252))
    order = ["daily close (baseline)", "daily: 2 closes 0.5% beyond"] + [v[0] for v in variants]
    report("PART B  intraday closes vs daily 200-DMA, 2 years, 10 names", [(k, results[k]) for k in order])


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--part", default="AB")
    args = ap.parse_args()
    cli = AlpacaREST(*load_keys())
    if "A" in args.part.upper():
        part_a(cli)
    if "B" in args.part.upper():
        part_b(cli)


if __name__ == "__main__":
    main()
