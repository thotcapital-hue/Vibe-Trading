#!/usr/bin/env python3
"""Backtest Rule 3: buy the intraday bounce off a daily moving average.

Daily averages (20-DMA close, 20-day LOW ribbon, 50-DMA) are computed from
daily bars and carried forward as of the PRIOR close. On hourly bars during
the regular session, in an uptrend (prior close > 20-DMA > 200-DMA):

  setup   hourly LOW touches the line (low <= line * (1 + touch)) and the
          hourly CLOSE is back above the line  -> buy at that close
  stop    line * (1 - stop)         (default 1.0%)
  target  entry + R * (entry - stop) (default R = 1.5)
  time    exit at close after `hold` bars (default 21 = ~3 sessions)
Mirror for shorts in downtrends (prior close < 20-DMA < 200-DMA).
Also reports the RAW bounce odds: after a touch, does price reach +1% before
-1% (long side)? One trade per symbol at a time; 3-bar cooldown after exit.

Usage: python scripts/backtest_bounce.py [--years 2] [--line 20c|20l|50c] [SYMS ...]
"""
from __future__ import annotations

import argparse
import statistics as st
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from alpaca_rest import AlpacaREST
from spread_scan import load_keys

DEFAULT = ["SPY", "QQQ", "AAPL", "MSFT", "NVDA", "META", "GOOGL", "AMZN", "XLE", "XLP"]
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


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("symbols", nargs="*")
    ap.add_argument("--years", type=int, default=2)
    ap.add_argument("--line", default="20c", choices=["20c", "20l", "50c"])
    ap.add_argument("--touch", type=float, default=0.0015)
    ap.add_argument("--stop", type=float, default=0.01)
    ap.add_argument("--rr", type=float, default=1.5)
    ap.add_argument("--hold", type=int, default=21)
    ap.add_argument("--shorts", action="store_true", help="also test fading bounces in downtrends")
    args = ap.parse_args()
    syms = [s.upper() for s in args.symbols] or DEFAULT
    cli = AlpacaREST(*load_keys())
    start = datetime.now(timezone.utc) - timedelta(days=365 * args.years)
    daily = cli.bars(syms, start - timedelta(days=330), "1Day")
    hourly = cli.bars(syms, start, "1Hour")

    print(f"line={args.line} touch={args.touch:.2%} stop={args.stop:.1%} target={args.rr}R hold={args.hold} bars  ({args.years}y hourly, regular session only)")
    print(f"{'sym':<6} {'side':<5} {'touches':>7} {'trades':>6} {'win%':>5} {'avg R':>6} {'exp R':>6} {'timeout%':>8} {'raw +1% first':>13}")
    tot = {"long": [], "short": []}
    for s in syms:
        d = daily.get(s); hb = hourly.get(s)
        if not d or not hb:
            continue
        dc = [float(x["c"]) for x in d]; dl = [float(x["l"]) for x in d]
        m20, m200, m50, l20 = sma_series(dc, 20), sma_series(dc, 200), sma_series(dc, 50), sma_series(dl, 20)
        line_s = {"20c": m20, "20l": l20, "50c": m50}[args.line]
        by_day = {x["t"][:10]: i for i, x in enumerate(d)}
        days = sorted(by_day)

        def prior(day: str):
            """index of the last daily bar strictly before `day`."""
            import bisect
            k = bisect.bisect_left(days, day) - 1
            return by_day[days[k]] if k >= 0 else None

        # regular-session hourly bars only
        H = []
        for x in hb:
            t = datetime.fromisoformat(x["t"].replace("Z", "+00:00")).astimezone(NY)
            if (t.hour, t.minute) >= (9, 30) and t.hour < 16:
                H.append((t.strftime("%Y-%m-%d"), float(x["o"]), float(x["h"]), float(x["l"]), float(x["c"])))
        for side in (["long", "short"] if args.shorts else ["long"]):
            touches = 0; trades = []; timeouts = 0; raw_up = 0; raw_n = 0
            pos = None; cooldown = 0
            for j, (day, o, h, lo, c) in enumerate(H):
                pi = prior(day)
                if pi is None or line_s[pi] is None or m200[pi] is None or m20[pi] is None:
                    continue
                line = line_s[pi]
                up = dc[pi] > m20[pi] > m200[pi]; dn = dc[pi] < m20[pi] < m200[pi]
                if pos:
                    e, stp, tgt, j0 = pos
                    if side == "long":
                        if lo <= stp: trades.append(-1.0); pos = None; cooldown = 3
                        elif h >= tgt: trades.append(args.rr); pos = None; cooldown = 3
                        elif j - j0 >= args.hold: trades.append((c - e) / (e - stp)); timeouts += 1; pos = None; cooldown = 3
                    else:
                        if h >= stp: trades.append(-1.0); pos = None; cooldown = 3
                        elif lo <= tgt: trades.append(args.rr); pos = None; cooldown = 3
                        elif j - j0 >= args.hold: trades.append((e - c) / (stp - e)); timeouts += 1; pos = None; cooldown = 3
                    continue
                if cooldown:
                    cooldown -= 1; continue
                if side == "long" and up and lo <= line * (1 + args.touch) and c > line:
                    touches += 1
                    # raw odds: +1% before -1% from the close
                    for k in range(j + 1, min(j + 1 + args.hold, len(H))):
                        if H[k][3] <= c * 0.99: raw_n += 1; break
                        if H[k][2] >= c * 1.01: raw_up += 1; raw_n += 1; break
                    stp = line * (1 - args.stop); pos = (c, stp, c + args.rr * (c - stp), j)
                elif side == "short" and dn and h >= line * (1 - args.touch) and c < line:
                    touches += 1
                    for k in range(j + 1, min(j + 1 + args.hold, len(H))):
                        if H[k][2] >= c * 1.01: raw_n += 1; break
                        if H[k][3] <= c * 0.99: raw_up += 1; raw_n += 1; break
                    stp = line * (1 + args.stop); pos = (c, stp, c - args.rr * (stp - c), j)
            if trades:
                w = sum(t > 0 for t in trades) / len(trades); avg = st.mean(trades)
                print(f"{s:<6} {side:<5} {touches:>7} {len(trades):>6} {w:>5.0%} {avg:>6.2f} {avg:>6.2f} {timeouts / len(trades):>8.0%} {raw_up / raw_n if raw_n else 0:>13.0%}")
                tot[side].extend(trades)
    for side, tr in tot.items():
        if tr:
            w = sum(t > 0 for t in tr) / len(tr); avg = st.mean(tr)
            print(f"\nALL {side}: {len(tr)} trades, win {w:.0%}, expectancy {avg:+.2f} R per trade  "
                  f"(risking 1% of equity per trade: {avg:+.2f}% per trade, {avg * len(tr) / args.years:+.1f}% per year gross before slippage)")
    print("R = risk unit (entry to stop). Expectancy > 0 means the bounce pays after losers; slippage not included.")


if __name__ == "__main__":
    main()
