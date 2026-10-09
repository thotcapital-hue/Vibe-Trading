#!/usr/bin/env python3
"""Drawdown anatomy, exit/re-entry grid, put-based entry, and the combined plan.

Part 1  Where did the regime sleeve's drawdowns come from? Top episodes with
        dates, depth, and how much was lost while IN the regime vs after
        re-entering (whipsaw).
Part 2  Exit x re-entry grid on the SPY/QQQ/IWM sleeve: faster exits (close
        below 20-DMA, below 20-low band, 2-day drop > 3%, below 50-DMA) vs the
        regime-flip exit, each with re-entry rules (immediately when the exit
        condition clears / after 2 closes back above the 20-DMA / only when
        the ribbon is ABOVE again).
Part 3  Put-based entry ("wheel"): at each regime entry, sell a 21-DTE ATM put
        instead of buying; assigned at K if S<K at expiry, else keep premium
        and buy at expiry price. Black-Scholes with VIX-scaled IV.
Part 4  Combined plan: levered regime sleeve (1x/1.5x/2x, financed at
        bills+0.5%) + the exported options-overlay curve (30% heat, staged).

Usage: python scripts/backtest_combined.py [--years 6] [--overlay research/overlay_curve_100k.csv]
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

IDX = ["SPY", "QQQ", "IWM"]
VIX_CSV = "https://cdn.cboe.com/api/global/us_indices/daily_prices/VIX_History.csv"


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


def N(x): return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def bs_put(S, K, T, iv):
    if T <= 0:
        return max(0.0, K - S)
    d1 = (math.log(S / K) + 0.5 * iv * iv * T) / (iv * math.sqrt(T)); d2 = d1 - iv * math.sqrt(T)
    return K * N(-d2) - S * N(-d1)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--years", type=int, default=6)
    ap.add_argument("--cash", type=float, default=0.03)
    ap.add_argument("--overlay", default="/home/user/Vibe-Trading/research/overlay_curve_100k.csv")
    args = ap.parse_args()
    cli = AlpacaREST(*load_keys())
    bars = cli.bars(IDX, datetime.now(timezone.utc) - timedelta(days=365 * args.years + 320), "1Day")
    dates = [date.fromisoformat(b["t"][:10]) for b in bars["SPY"]]
    px = {}
    for s in IDX:
        by = {date.fromisoformat(b["t"][:10]): b for b in bars[s]}; last = None; c = []; h = []; lo = []
        for d in dates:
            b = by.get(d, last); last = b
            c.append(float(b["c"])); h.append(float(b["h"])); lo.append(float(b["l"]))
        px[s] = dict(c=c, c20=sma_series(c, 20), c50=sma_series(c, 50), l20=sma_series(lo, 20), h200=sma_series(h, 200))
    n0 = 260; daily_cash = (1 + args.cash) ** (1 / 252) - 1
    # VIX for the put-entry model
    vix = {}
    try:
        for r in list(csv.reader(io.StringIO(urllib.request.urlopen(VIX_CSV, timeout=30).read().decode())))[1:]:
            try:
                vix[datetime.strptime(r[0], "%m/%d/%Y").date()] = float(r[4]) / 100
            except (ValueError, IndexError):
                pass
    except Exception as exc:  # noqa: BLE001
        print(f"[warn] VIX unavailable ({exc}); put-entry uses 20% IV")

    def above(s, i):
        d = px[s]; return d["l20"][i] is not None and d["h200"][i] is not None and d["l20"][i] > d["h200"][i]

    # ---------------- Part 2 machinery: state machine per index ----------------
    def run_rule(exit_fn, reentry_fn, lever=1.0):
        """Returns curve, trades/yr, time-in, and per-index positions over time."""
        eq = 1.0; curve = [eq]; pos = {s: above(s, n0) for s in IDX}; trades = 0; days_in = 0
        pos_hist = []
        for i in range(n0 + 1, len(dates)):
            ret = 0.0
            for s in IDX:
                if pos[s]:
                    ret += (px[s]["c"][i] / px[s]["c"][i - 1] - 1) / len(IDX); days_in += 1
                else:
                    ret += daily_cash / len(IDX)
            gross = lever * ret - max(0.0, lever - 1) * (daily_cash + 0.005 / 252)
            eq *= 1 + gross; curve.append(eq); pos_hist.append(dict(pos))
            for s in IDX:  # decide for tomorrow on today's close
                if pos[s] and exit_fn(s, i):
                    pos[s] = False; trades += 1
                elif not pos[s] and reentry_fn(s, i):
                    pos[s] = True; trades += 1
        yrs = (len(dates) - n0) / 252
        return curve, trades / yrs, days_in / ((len(dates) - n0) * len(IDX)), pos_hist

    exits = {
        "regime flip (20L < 200H)": lambda s, i: not above(s, i),
        "close < 20-DMA": lambda s, i: px[s]["c"][i] < px[s]["c20"][i],
        "close < 20-low band": lambda s, i: px[s]["c"][i] < px[s]["l20"][i],
        "2-day drop > 3%": lambda s, i: px[s]["c"][i] / px[s]["c"][i - 2] - 1 < -0.03,
        "close < 50-DMA": lambda s, i: px[s]["c"][i] < px[s]["c50"][i],
    }
    reentries = {
        "when exit clears": None,  # filled per exit
        "2 closes > 20-DMA & ABOVE": lambda s, i: above(s, i) and px[s]["c"][i] > px[s]["c20"][i] and px[s]["c"][i - 1] > px[s]["c20"][i - 1],
        "ABOVE regime only": lambda s, i: above(s, i),
    }

    # ---------------- Part 1: drawdown anatomy of the base sleeve ----------------
    base_curve, tpy, tin, pos_hist = run_rule(exits["regime flip (20L < 200H)"], reentries["ABOVE regime only"])
    print("PART 1  drawdown anatomy: regime sleeve (exit on flip, re-enter on ABOVE), SPY/QQQ/IWM equal weight")
    peak = base_curve[0]; peak_i = 0; episodes = []; in_dd = False
    for k, v in enumerate(base_curve):
        if v >= peak:
            if in_dd:
                episodes.append((peak_i, trough_i, k, trough_v / peak - 1)); in_dd = False
            peak, peak_i = v, k
        else:
            if not in_dd:
                in_dd = True; trough_v, trough_i = v, k
            elif v < trough_v:
                trough_v, trough_i = v, k
    if in_dd:
        episodes.append((peak_i, trough_i, len(base_curve) - 1, trough_v / peak - 1))
    episodes.sort(key=lambda e: e[3])
    print(f"{'peak':>10} {'trough':>10} {'recovered':>10} {'depth':>7} {'days to trough':>14} {'avg names held at trough':>24} {'exposure during fall':>20}")
    for pk, tr, rec, depth in episodes[:5]:
        d0, d1, d2 = dates[n0 + pk], dates[n0 + tr], dates[n0 + rec] if rec < len(base_curve) - 1 else None
        held = st.mean(sum(p.values()) for p in pos_hist[pk:tr + 1]) if tr > pk else sum(pos_hist[pk].values())
        print(f"{d0} {d1} {str(d2) if d2 else 'ongoing':>10} {depth:>7.1%} {tr - pk:>14} {held:>24.1f} {held / 3:>19.0%}")
    print("(exposure = share of the three indices held during the fall; 100% = fully invested, i.e. the loss came while IN the regime)")

    # ---------------- Part 2: exit x re-entry grid ----------------
    print(f"\nPART 2  exit x re-entry grid (unlevered)  benchmark buy&hold: ", end="")
    bh = [1.0]
    for i in range(n0 + 1, len(dates)):
        bh.append(bh[-1] * (1 + sum(px[s]["c"][i] / px[s]["c"][i - 1] - 1 for s in IDX) / 3))
    c, m, sh = stats(bh); print(f"CAGR {c:.1%} DD {m:.1%} Sharpe {sh:.2f}")
    print(f"{'exit rule':<26} {'re-entry rule':<28} {'CAGR':>6} {'max DD':>7} {'Sharpe':>6} {'switches/yr':>11} {'time in':>7}")
    for ex_name, ex in exits.items():
        for re_name, re in reentries.items():
            re_fn = (lambda s, i, ex=ex: not ex(s, i)) if re is None else re
            curve, tpy, tin, _ = run_rule(ex, re_fn)
            c, m, sh = stats(curve)
            print(f"{ex_name:<26} {re_name:<28} {c:>6.1%} {m:>7.1%} {sh:>6.2f} {tpy:>11.1f} {tin:>7.0%}")

    # ---------------- Part 3: put-based entry ----------------
    print("\nPART 3  entering via a 21-DTE at-the-money short put instead of buying at the signal")
    def iv_at(i):
        v = vix.get(dates[i]) or next((vix.get(dates[i] - timedelta(days=k)) for k in range(1, 6) if vix.get(dates[i] - timedelta(days=k))), None)
        return v or 0.20
    def run_wheel():
        eq = 1.0; curve = [eq]; state = {s: ("long" if above(s, n0) else "cash") for s in IDX}; pend = {}
        prem_total = 0.0; assigned = 0; expired = 0
        for i in range(n0 + 1, len(dates)):
            ret = 0.0
            for s in IDX:
                S = px[s]["c"][i]; S0 = px[s]["c"][i - 1]
                if state[s] == "long":
                    ret += (S / S0 - 1) / 3
                else:
                    ret += daily_cash / 3
                if state[s] == "put" and i >= pend[s]["exp"]:
                    K = pend[s]["K"]; prem = pend[s]["prem"]
                    prem_total += prem / K / 3
                    ret += (prem / K) / 3  # premium kept, as a fraction of the notional we were about to buy
                    if S < K:
                        ret += (S / K - 1) / 3; assigned += 1  # assigned at K, marked to S
                    else:
                        expired += 1
                    state[s] = "long"  # own it either way (assigned, or buy at expiry price)
            eq *= 1 + ret; curve.append(eq)
            for s in IDX:
                if state[s] == "long" and not above(s, i):
                    state[s] = "cash"
                elif state[s] == "cash" and above(s, i):
                    S = px[s]["c"][i]; T = 21 / 365; prem = bs_put(S, S, T, iv_at(i) * (px[s]["c20"][i] and 1.0))
                    # QQQ/IWM vol vs SPY: scale by 20d realised ratio
                    state[s] = "put"; pend[s] = dict(K=S, prem=prem, exp=i + 15)
        return curve, assigned, expired, prem_total
    wheel_curve, assigned, expired, prem_total = run_wheel()
    c, m, sh = stats(wheel_curve); c0, m0, sh0 = stats(base_curve)
    print(f"buy at signal:      CAGR {c0:.1%} DD {m0:.1%} Sharpe {sh0:.2f}")
    print(f"sell ATM put first: CAGR {c:.1%} DD {m:.1%} Sharpe {sh:.2f}   ({assigned} entries assigned, {expired} puts expired and we bought at expiry; premium collected ~{prem_total:.1%} of the sleeve over the period)")

    # ---------------- Part 4: combined plan ----------------
    print("\nPART 4  combined plan: levered regime sleeve + options overlay (30% heat, staged, from exported curve)")
    ov = {}
    try:
        with open(args.overlay) as f:
            for row in csv.DictReader(f):
                ov[date.fromisoformat(row["date"])] = float(row["equity"])
    except OSError:
        print("[warn] overlay curve not found; run backtest_options_regime.py --export first"); return
    ov0 = None
    print(f"{'plan':<52} {'CAGR':>6} {'max DD':>7} {'Sharpe':>6}")
    for lever in (1.0, 1.5, 2.0):
        curve, _, _, _ = run_rule(exits["regime flip (20L < 200H)"], reentries["ABOVE regime only"], lever)
        comb = []
        for k in range(len(curve)):
            d = dates[n0 + k]; o = ov.get(d)
            if o is None:
                comb.append(None); continue
            if ov0 is None:
                ov0 = o
            comb.append(curve[k] + (o - ov0) / 100_000.0)  # overlay P&L as fraction of the same $100k
        comb = [v for v in comb if v is not None]
        c1, m1, sh1 = stats(curve); c2, m2, sh2 = stats(comb)
        print(f"{'regime sleeve ' + f'{lever:.1f}x alone':<52} {c1:>6.1%} {m1:>7.1%} {sh1:>6.2f}")
        print(f"{'regime sleeve ' + f'{lever:.1f}x + overlay':<52} {c2:>6.1%} {m2:>7.1%} {sh2:>6.2f}")


if __name__ == "__main__":
    main()
