#!/usr/bin/env python3
"""Fund techniques on top of the regime sleeve: leverage, vol targeting, diversifier.

Stock sleeve = equal-weight SPY/QQQ/IWM, each long only while its 20-day LOW
band is above its 200-day HIGH band, cash otherwise (cash earns the 3m bill).
Variants:
  lever L      L x daily return of each index while in regime, financed at
               the bill rate + 0.5% on the borrowed part (futures/LEAPS-style)
  voltarget V  scale exposure so the sleeve's trailing 20d vol ~ V (cap 2x)
  + DBMF w     add a w% sleeve of the iMGP managed-futures ETF (trend across
               asset classes), rebalanced monthly (data from May 2019)
Cash rate: FRED 3m bill if reachable, else 3%.

Usage: python scripts/backtest_stack.py [--years 6]
"""
from __future__ import annotations

import argparse
import math
import statistics as st
from datetime import date, datetime, timedelta, timezone

from alpaca_rest import AlpacaREST
from spread_scan import load_keys

IDX = ["SPY", "QQQ", "IWM"]


def sma_series(x, n):
    out = [None] * len(x); s = 0.0
    for i, v in enumerate(x):
        s += v
        if i >= n:
            s -= x[i - n]
        if i >= n - 1:
            out[i] = s / n
    return out


def stats(curve):
    yrs = len(curve) / 252; cagr = (curve[-1] / curve[0]) ** (1 / yrs) - 1
    peak = curve[0]; mdd = 0
    for v in curve:
        peak = max(peak, v); mdd = min(mdd, v / peak - 1)
    r = [curve[k] / curve[k - 1] - 1 for k in range(1, len(curve))]
    return cagr, mdd, (st.mean(r) / st.pstdev(r) * math.sqrt(252)) if st.pstdev(r) else 0


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--years", type=int, default=6)
    ap.add_argument("--cash", type=float, default=0.03, help="annual cash / financing base rate")
    args = ap.parse_args()
    cli = AlpacaREST(*load_keys())
    bars = cli.bars(IDX + ["DBMF", "KMLM", "GLD", "TLT"], datetime.now(timezone.utc) - timedelta(days=365 * args.years + 320), "1Day")
    dates = [date.fromisoformat(b["t"][:10]) for b in bars["SPY"]]
    px = {}
    for s, bl in bars.items():
        by = {date.fromisoformat(b["t"][:10]): b for b in bl}; last = None; c = []; h = []; lo = []
        for d in dates:
            b = by.get(d, last); last = b
            if b is None:
                c.append(None); h.append(None); lo.append(None)
            else:
                c.append(float(b["c"])); h.append(float(b["h"])); lo.append(float(b["l"]))
        px[s] = dict(c=c, h=h, l=lo)
    for s in IDX:
        d = px[s]; d["l20"] = sma_series(d["l"], 20); d["h200"] = sma_series(d["h"], 200)
    n0 = 260; daily_cash = (1 + args.cash) ** (1 / 252) - 1

    def in_regime(s, i):
        d = px[s]; return d["l20"][i] is not None and d["h200"][i] is not None and d["l20"][i] > d["h200"][i]

    def sleeve(lever=1.0, voltarget=None, dbmf_w=0.0, name="DBMF"):
        eq = 1.0; curve = [eq]; hist = []
        db_alloc = dbmf_w if (dbmf_w and px[name]["c"][n0] is not None) else 0.0
        for i in range(n0 + 1, len(dates)):
            # index sleeve return
            ret = 0.0
            for s in IDX:
                r = px[s]["c"][i] / px[s]["c"][i - 1] - 1 if in_regime(s, i - 1) else daily_cash
                ret += r / len(IDX)
            # exposure multiplier
            L = lever
            if voltarget and len(hist) >= 20:
                rv = st.pstdev(hist[-20:]) * math.sqrt(252)
                L = min(2.0, max(0.25, voltarget / rv)) if rv > 0 else 1.0
            gross = L * ret - max(0.0, L - 1) * (daily_cash + 0.005 / 252)  # financing on borrowed part
            hist.append(ret)
            if db_alloc and px[name]["c"][i - 1]:
                db_r = px[name]["c"][i] / px[name]["c"][i - 1] - 1
                total = (1 - db_alloc) * gross + db_alloc * db_r
            else:
                total = gross
            eq *= 1 + total; curve.append(eq)
        return curve

    rows = [
        ("buy & hold 3 indices, equal weight", None),
        ("regime sleeve, 1x", sleeve(1.0)),
        ("regime sleeve, 1.5x (futures/LEAPS financing)", sleeve(1.5)),
        ("regime sleeve, 2x", sleeve(2.0)),
        ("regime sleeve, 3x", sleeve(3.0)),
        ("regime sleeve, vol-targeted 15%", sleeve(1.0, 0.15)),
        ("regime sleeve, vol-targeted 20%", sleeve(1.0, 0.20)),
        ("regime 1x + 20% DBMF (managed futures)", sleeve(1.0, None, 0.20)),
        ("regime 1.5x + 20% DBMF", sleeve(1.5, None, 0.20)),
        ("regime vol-target 20% + 20% DBMF", sleeve(1.0, 0.20, 0.20)),
        ("regime 1x + 20% KMLM", sleeve(1.0, None, 0.20, "KMLM")),
    ]
    # buy & hold curve
    bh = [1.0]
    for i in range(n0 + 1, len(dates)):
        bh.append(bh[-1] * (1 + sum(px[s]["c"][i] / px[s]["c"][i - 1] - 1 for s in IDX) / 3))
    rows[0] = (rows[0][0], bh)
    print(f"{'variant':<48} {'CAGR':>7} {'max DD':>7} {'Sharpe':>6}")
    for name, curve in rows:
        c, m, sh = stats(curve); print(f"{name:<48} {c:>7.1%} {m:>7.1%} {sh:>6.2f}")
    # DBMF standalone
    for name in ("DBMF", "KMLM"):
        c = [v for v in px[name]["c"][n0:] if v]
        if len(c) > 300:
            s_ = stats(c); print(f"{name + ' standalone':<48} {s_[0]:>7.1%} {s_[1]:>7.1%} {s_[2]:>6.2f}")
    # correlation of DBMF with the regime sleeve
    reg = sleeve(1.0); db = px["DBMF"]["c"][n0:]
    r1 = [reg[k] / reg[k - 1] - 1 for k in range(1, len(reg))]
    r2 = [db[k] / db[k - 1] - 1 if db[k] and db[k - 1] else None for k in range(1, len(db))]
    pairs = [(a, b) for a, b in zip(r1, r2) if b is not None]
    ma, mb = st.mean(a for a, _ in pairs), st.mean(b for _, b in pairs)
    cov = sum((a - ma) * (b - mb) for a, b in pairs) / len(pairs)
    corr = cov / (st.pstdev([a for a, _ in pairs]) * st.pstdev([b for _, b in pairs]))
    print(f"\ncorrelation of daily returns, regime sleeve vs DBMF: {corr:+.2f}")


if __name__ == "__main__":
    main()
