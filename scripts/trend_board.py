#!/usr/bin/env python3
"""Trend board: 20/50/200-DMA stack, slopes, and a BULLISH / BEARISH / no-comment verdict.

For every board symbol (plus the index and sector funds) print last close, the
three moving averages, price distance to each, the 5-day slope of each
average ("tilt"), the stack order, and a verdict:

  BULLISH   price above all three, 20 > 50 > 200, and both 20- and 50-DMA rising
  BEARISH   price below all three, 20 < 50, and both 20- and 50-DMA falling
  (blank)   anything mixed: no comment, sit out

Also flags names within 1% of their 20-DMA (a decision point) and marks
whether the 20-DMA is above or below the 50 (short-term trend vs medium).
Read-only; Alpaca daily bars. Optional IV rank from tastytrade.

Usage:  python scripts/trend_board.py            # board + indices/sectors
        python scripts/trend_board.py AAPL XLU   # specific symbols
"""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone

from alpaca_rest import AlpacaREST
from board import CALL_SIDE_WATCH, CLUSTERS, cluster_of
from spread_scan import load_keys
from tasty_rest import iv_metrics, tasty_available

INDICES = ["SPY", "QQQ", "IWM", "RSP", "DIA"]
SECTORS = ["XLK", "XLF", "XLV", "XLP", "XLE", "XLI", "XLY", "XLU", "XLB", "XLRE", "XLC", "SMH"]


def sma(x: list[float], n: int, back: int = 0) -> float | None:
    seg = x[len(x) - n - back: len(x) - back] if back else x[-n:]
    return sum(seg) / n if len(seg) == n else None


def arrow(slope: float | None, flat: float = 0.15) -> str:
    if slope is None:
        return "  ?"
    return " up" if slope > flat else ("dn " if slope < -flat else "flat")


def verdict(px: float, m20: float, m50: float, m200: float, s20: float, s50: float) -> str:
    if px > m20 > m50 > m200 and s20 > 0 and s50 > 0:
        return "BULLISH"
    if px < m20 < m50 and px < m200 and s20 < 0 and s50 < 0:
        return "BEARISH"
    return ""


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("symbols", nargs="*")
    args = ap.parse_args()
    board = sorted({s for v in CLUSTERS.values() for s in v} | {s for v in CALL_SIDE_WATCH.values() for s in v})
    syms = [s.upper() for s in args.symbols] or sorted(set(board) | set(INDICES) | set(SECTORS))
    c = AlpacaREST(*load_keys())
    px = c.daily_closes(syms, datetime.now(timezone.utc) - timedelta(days=330), "sip")
    ivm = iv_metrics(syms) if tasty_available() else {}

    rows = []
    for s in syms:
        x = px.get(s)
        if not x or len(x) < 205:
            continue
        last = x[-1]
        m20, m50, m200 = sma(x, 20), sma(x, 50), sma(x, 200)
        s20 = (m20 / sma(x, 20, 5) - 1) * 100
        s50 = (m50 / sma(x, 50, 5) - 1) * 100
        s200 = (m200 / sma(x, 200, 5) - 1) * 100
        v = verdict(last, m20, m50, m200, s20, s50)
        stack = "20>50>200" if m20 > m50 > m200 else ("20<50<200" if m20 < m50 < m200 else ("20>50" if m20 > m50 else "20<50"))
        near = "*" if abs(last / m20 - 1) < 0.01 else " "
        ivr = (ivm.get(s) or {}).get("ivr")
        grp = "index" if s in INDICES else ("sector" if s in SECTORS and s not in board else (cluster_of(s) or "call-watch"))
        rows.append((v, s, last, m20, m50, m200, s20, s50, s200, stack, near, ivr, grp))

    order = {"BULLISH": 0, "": 1, "BEARISH": 2}
    rows.sort(key=lambda r: (order[r[0]], -(r[2] / r[3] - 1)))
    print(f"{'verdict':<8} {'sym':<5} {'last':>8} {'vs20':>6} {'vs50':>6} {'vs200':>6}  {'20-DMA':>5} {'50-DMA':>5} {'200-DMA':>6}  {'stack':<9} {'IVR':>3}  group")
    print(f"{'':<8} {'':<5} {'':>8} {'%':>6} {'%':>6} {'%':>6}  {'tilt':>5} {'tilt':>5} {'tilt':>6}")
    last_v = None
    for v, s, last, m20, m50, m200, s20, s50, s200, stack, near, ivr, grp in rows:
        if v != last_v:
            print("-" * 96)
            last_v = v
        print(f"{v or 'no comment':<8} {s:<5}{near}{last:>8.2f} {(last/m20-1)*100:>+6.1f} {(last/m50-1)*100:>+6.1f} {(last/m200-1)*100:>+6.1f}  "
              f"{arrow(s20):>5} {arrow(s50):>5} {arrow(s200, 0.05):>6}  {stack:<9} {str(max(int(ivr), 0)) if ivr is not None else '-':>3}  {grp}")
    n_b = sum(r[0] == "BULLISH" for r in rows)
    n_s = sum(r[0] == "BEARISH" for r in rows)
    print(f"\n{len(rows)} names: {n_b} BULLISH, {n_s} BEARISH, {len(rows)-n_b-n_s} no comment.  * = within 1% of its 20-DMA (decision point)")
    print("tilt = 5-day change of the average: up > +0.15%, dn < -0.15% (200-DMA: +/-0.05%)")


if __name__ == "__main__":
    main()
