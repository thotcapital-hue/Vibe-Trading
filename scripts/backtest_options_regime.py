#!/usr/bin/env python3
"""Options overlay on the ribbon regime: model bull puts / bear calls / condors.

Regime from the 20- and 200-day HIGH/LOW ribbons (daily bars):
  ABOVE    20-day LOW avg > 200-day HIGH avg   (bands fully clear, up)
  BELOW    20-day HIGH avg < 200-day LOW avg   (bands fully clear, down)
  OVERLAP  otherwise (trendless)

Structures (35 DTE, one per name at a time, portfolio-level heat cap):
  ABOVE   -> bull put spread: short put 1 SD below spot, long put 2.5% lower,
             only when close is above the 20-day LOW band (trend intact)
  BELOW   -> bear call spread, mirror
  OVERLAP -> iron condor (both), optional
Management: take profit at 50% of credit, stop at 2x credit loss, close at
21 DTE, close if the regime leaves the entry zone. Size: 1% of equity max
loss per position, at most 15 open (15% heat). Costs: $0.10/spread slippage
+ $0.65/leg commission, round trip.

Option prices: Black-Scholes. Implied vol proxy = VIX(t)/100 x (stock 60d
realised vol / SPY 60d realised vol), with a put skew (+0.20 vol per unit of
ln(S/K)) and a milder call skew. THIS IS A MODEL, not historical quotes:
treat results as indicative, not precise.

Compares against: the same regime rule trading stock (equal-weight sleeve,
cash when flat), and buy-and-hold of the equal-weight basket.

Usage: python scripts/backtest_options_regime.py [--years 6] [--no-condor] [--any-regime]
"""
from __future__ import annotations

import argparse
import csv
import io
import math
import statistics as st
import urllib.request
from datetime import date, datetime, timedelta, timezone

from alpaca_rest import AlpacaREST
from spread_scan import load_keys

SYMS = ["SPY", "QQQ", "IWM", "AAPL", "MSFT", "GOOGL", "META", "AMZN", "NVDA", "AVGO", "AMD",
        "JPM", "XLE", "XLU", "XLP", "XLV", "TLT", "GLD", "COST", "WMT"]
VIX_CSV = "https://cdn.cboe.com/api/global/us_indices/daily_prices/VIX_History.csv"
DTE, CLOSE_DTE, WIDTH, Z = 35, 21, 0.025, 1.0
TP, SL = 0.5, 2.0
RISK, MAX_POS = 0.01, 15
SLIP, COMM = 0.10, 0.65 * 4
START_EQ = 100_000.0


def N(x): return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def bs(S, K, T, iv, cp):
    if T <= 0:
        return max(0.0, S - K) if cp == "C" else max(0.0, K - S)
    d1 = (math.log(S / K) + 0.5 * iv * iv * T) / (iv * math.sqrt(T)); d2 = d1 - iv * math.sqrt(T)
    return S * N(d1) - K * N(d2) if cp == "C" else K * N(-d2) - S * N(-d1)


def skewed_iv(iv, S, K, cp):
    m = math.log(S / K)
    return max(0.05, iv + 0.20 * m) if cp == "P" else max(0.05, iv - 0.10 * (-m))


def spread_value(S, T, iv, ks, kl, cp):
    """Value (per share) of a short vertical: short ks, long kl."""
    return bs(S, ks, T, skewed_iv(iv, S, ks, cp), cp) - bs(S, kl, T, skewed_iv(iv, S, kl, cp), cp)


def sma_series(x, n):
    out = [None] * len(x); s = 0.0
    for i, v in enumerate(x):
        s += v
        if i >= n:
            s -= x[i - n]
        if i >= n - 1:
            out[i] = s / n
    return out


def rv_series(c, n=60):
    out = [None] * len(c)
    r = [0.0] + [math.log(c[i] / c[i - 1]) for i in range(1, len(c))]
    for i in range(n, len(c)):
        seg = r[i - n + 1:i + 1]; m = sum(seg) / n
        out[i] = math.sqrt(sum((x - m) ** 2 for x in seg) / (n - 1) * 252)
    return out


def load_vix():
    rows = list(csv.reader(io.StringIO(urllib.request.urlopen(VIX_CSV, timeout=30).read().decode())))
    out = {}
    for r in rows[1:]:
        try:
            out[datetime.strptime(r[0], "%m/%d/%Y").date()] = float(r[4]) / 100
        except (ValueError, IndexError):
            pass
    return out


def main():
    global Z, WIDTH, TP, SL, SLIP, COMM, CLOSE_DTE
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--years", type=int, default=6)
    ap.add_argument("--no-condor", action="store_true")
    ap.add_argument("--any-regime", action="store_true", help="sell bull puts every day regardless of regime (control)")
    ap.add_argument("--equity", type=float, default=START_EQ)
    ap.add_argument("--no-costs", action="store_true")
    ap.add_argument("--z", type=float, default=Z, help="short strike distance in SDs")
    ap.add_argument("--width", type=float, default=WIDTH, help="spread width as fraction of spot")
    ap.add_argument("--tp", type=float, default=TP); ap.add_argument("--sl", type=float, default=SL)
    ap.add_argument("--no-21dte", action="store_true", help="hold to expiry unless TP/SL/regime")
    ap.add_argument("--gate", type=float, default=0.12, help="min credit/width")
    ap.add_argument("--slip", type=float, default=SLIP, help="slippage per spread per share, round trip")
    ap.add_argument("--comm", type=float, default=COMM, help="commission per spread round trip (4 legs)")
    ap.add_argument("--puts-only", action="store_true", help="no bear calls in BELOW")
    ap.add_argument("--symbols", nargs="*", help="restrict universe (SPY always fetched for vol scaling)")
    ap.add_argument("--risk", type=float, default=RISK, help="max loss per position as fraction of equity")
    args = ap.parse_args()
    SLIP, COMM = args.slip, args.comm
    if args.symbols:
        SYMS[:] = sorted(set(s.upper() for s in args.symbols) | {"SPY"})
    Z, WIDTH, TP, SL = args.z, args.width, args.tp, args.sl
    if args.no_costs: SLIP, COMM = 0.0, 0.0
    if args.no_21dte: CLOSE_DTE = 0
    cli = AlpacaREST(*load_keys())
    bars = cli.bars(SYMS, datetime.now(timezone.utc) - timedelta(days=365 * args.years + 320), "1Day")
    vix = load_vix()

    # align on SPY's calendar
    dates = [date.fromisoformat(b["t"][:10]) for b in bars["SPY"]]
    idx = {d: i for i, d in enumerate(dates)}
    data = {}
    for s in SYMS:
        by = {date.fromisoformat(b["t"][:10]): b for b in bars[s]}
        c = []; h = []; lo = []; last = None
        for d in dates:
            b = by.get(d, last); last = b
            c.append(float(b["c"])); h.append(float(b["h"])); lo.append(float(b["l"]))
        data[s] = dict(c=c, h20=sma_series(h, 20), l20=sma_series(lo, 20), h200=sma_series(h, 200),
                       l200=sma_series(lo, 200), c20=sma_series(c, 20), rv=rv_series(c))
    spy_rv = data["SPY"]["rv"]

    def zone(s, i):
        d = data[s]
        if None in (d["l20"][i], d["h200"][i], d["h20"][i], d["l200"][i]):
            return None
        if d["l20"][i] > d["h200"][i]:
            return "ABOVE"
        if d["h20"][i] < d["l200"][i]:
            return "BELOW"
        return "OVERLAP"

    def iv_of(s, i):
        v = vix.get(dates[i])
        if v is None:
            for k in range(1, 6):
                v = vix.get(dates[i] - timedelta(days=k))
                if v is not None:
                    break
        rv, srv = data[s]["rv"][i], spy_rv[i]
        if v is None or not rv or not srv:
            return None
        return min(1.5, max(0.10, v * rv / srv))

    n0 = 260
    eq = args.equity; cash_curve = []; open_pos = {}; closed = []
    for i in range(n0, len(dates)):
        S_all = {s: data[s]["c"][i] for s in SYMS}
        # ---- manage open positions
        for s in list(open_pos):
            p = open_pos[s]; S = S_all[s]; T = max(0, (p["exp"] - i)) / 252
            iv = iv_of(s, i) or p["iv"]
            val = sum(spread_value(S, T, iv, ks, kl, cp) for ks, kl, cp in p["legs"])  # cost to close per share
            pnl = (p["credit"] - val) * 100 * p["qty"]
            z = zone(s, i)
            reason = None
            if val <= p["credit"] * (1 - TP): reason = "profit"
            elif val >= p["credit"] * (1 + SL): reason = "stop"
            elif (p["exp"] - i) <= CLOSE_DTE * 252 / 365: reason = "21dte"
            elif z != p["zone"]: reason = "regime"
            if reason:
                cost = (SLIP * 100 + COMM) * p["qty"] * (2 if p["kind"] == "condor" else 1)
                eq += pnl - cost; closed.append((s, p["kind"], pnl - cost, reason, i - p["open"], p["credit"] * 100 * p["qty"], p["qty"], cost))
                del open_pos[s]
        # ---- open new positions
        heat = sum(p["maxloss"] for p in open_pos.values())
        for s in SYMS:
            if s in open_pos or len(open_pos) >= MAX_POS:
                continue
            z = zone(s, i); iv = iv_of(s, i); S = S_all[s]; d = data[s]
            if z is None or iv is None:
                continue
            T = DTE / 365; sd = S * (math.exp(Z * iv * math.sqrt(T)) - 1)
            legs = []
            if sd >= S * 0.9:
                continue
            if args.any_regime or (z == "ABOVE" and S > d["l20"][i]):
                ks = S - sd; kl = ks - WIDTH * S; legs.append((ks, kl, "P")); kind = "bullput"
            elif z == "BELOW" and S < d["h20"][i] and not args.puts_only:
                ks = S + sd; kl = ks + WIDTH * S; legs.append((ks, kl, "C")); kind = "bearcall"
            elif z == "OVERLAP" and not args.no_condor:
                legs = [(S - sd, S - sd - WIDTH * S, "P"), (S + sd, S + sd + WIDTH * S, "C")]; kind = "condor"
            else:
                continue
            credit = sum(spread_value(S, T, iv, ks, kl, cp) for ks, kl, cp in legs)
            width = WIDTH * S
            if credit / width < args.gate or credit <= 0:  # credit gate
                continue
            maxloss_per = (width - credit) * 100
            qty = int(eq * args.risk // maxloss_per)
            if qty < 1 or heat + maxloss_per * qty > eq * 0.15:
                continue
            open_pos[s] = dict(kind=kind, legs=legs, credit=credit, qty=qty, exp=i + DTE * 252 // 365,
                               open=i, zone=z if not args.any_regime else zone(s, i), iv=iv, maxloss=maxloss_per * qty)
            heat += maxloss_per * qty
        mtm = eq
        for s, p in open_pos.items():
            T = max(0, (p["exp"] - i)) / 252; iv = iv_of(s, i) or p["iv"]
            val = sum(spread_value(S_all[s], T, iv, ks, kl, cp) for ks, kl, cp in p["legs"])
            mtm += (p["credit"] - val) * 100 * p["qty"]
        cash_curve.append(mtm)

    # ---- stock comparisons on the same dates: equal-weight sleeve per name, cash when flat
    def sleeve_curve(rule):
        curve = []; w = 1 / len(SYMS); vals = {s: args.equity * w for s in SYMS}
        for i in range(n0, len(dates)):
            tot = 0
            for s in SYMS:
                if i > n0 and rule(s, i - 1):
                    vals[s] *= data[s]["c"][i] / data[s]["c"][i - 1]
                tot += vals[s]
            curve.append(tot)
        return curve
    stock_2b = sleeve_curve(lambda s, i: zone(s, i) == "ABOVE")
    bh = sleeve_curve(lambda s, i: True)

    def stats(curve):
        yrs = len(curve) / 252; cagr = (curve[-1] / curve[0]) ** (1 / yrs) - 1
        peak = curve[0]; mdd = 0
        for v in curve:
            peak = max(peak, v); mdd = min(mdd, v / peak - 1)
        rets = [curve[k] / curve[k - 1] - 1 for k in range(1, len(curve))]
        sharpe = (st.mean(rets) / st.pstdev(rets) * math.sqrt(252)) if st.pstdev(rets) else 0
        return cagr, mdd, sharpe

    print(f"{'strategy':<44} {'CAGR':>7} {'max DD':>7} {'Sharpe':>6}")
    for name, curve in (("options overlay on regime (this test)", cash_curve), ("stock: long in ABOVE regime, equal-weight", stock_2b),
                        ("stock: buy & hold equal-weight basket", bh)):
        c, m, sh = stats(curve)
        print(f"{name:<44} {c:>7.1%} {m:>7.1%} {sh:>6.2f}")
    if closed:
        print(f"\noptions trades: {len(closed)}  ({len(closed) / (len(cash_curve) / 252):.0f}/yr)  avg credit collected ${st.mean(x[5] for x in closed):,.0f}  avg contracts {st.mean(x[6] for x in closed):.1f}  avg costs ${st.mean(x[7] for x in closed):.0f} ({st.mean(x[7] for x in closed) / st.mean(x[5] for x in closed):.0%} of credit)")
    for kind in ("bullput", "bearcall", "condor"):
        tr = [x for x in closed if x[1] == kind]
        if not tr:
            continue
        pnl = [x[2] for x in tr]; wins = sum(p > 0 for p in pnl)
        reasons = {r: sum(1 for x in tr if x[3] == r) for r in ("profit", "stop", "21dte", "regime")}
        print(f"  {kind:<9} n={len(tr):>4} win {wins / len(tr):>4.0%} avg ${st.mean(pnl):>7.0f} "
              f"avg win ${st.mean([p for p in pnl if p > 0] or [0]):>6.0f} avg loss ${st.mean([p for p in pnl if p <= 0] or [0]):>7.0f} "
              f"total ${sum(pnl):>9,.0f} | exits {reasons} | avg hold {st.mean(x[4] for x in tr):.0f}d")
    cr = [x for x in closed]
    print(f"\nfinal equity ${cash_curve[-1]:,.0f} from ${args.equity:,.0f}; model options (Black-Scholes, VIX-scaled IV), not historical quotes.")


if __name__ == "__main__":
    main()
