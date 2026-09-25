#!/usr/bin/env python3
"""Morning IV-rank board: which names have premium worth selling today?

Pulls tastytrade market metrics for every board and call-watch symbol and
prints them sorted by IV rank (0-100). Rank >= 50 is "rich" (sell premium
here first), 30-50 "ok", < 30 "CHEAP" (the scanner refuses to sell these
without --allow-low-ivr). Also flags earnings inside the 30-45 DTE window.

Read-only; needs TASTY_CLIENT_SECRET / TASTY_REFRESH_TOKEN.

Usage:
    python scripts/iv_board.py
    python scripts/iv_board.py --min 40        # only show rank >= 40
"""

from __future__ import annotations

import argparse
import sys
from datetime import date, datetime, timezone

from board import CALL_SIDE_WATCH, CLUSTERS, cluster_of
from tasty_rest import iv_metrics, ivr_label, tasty_available


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--min", type=float, default=0.0, help="hide rows with IV rank below this")
    ap.add_argument("symbols", nargs="*", help="override the board with these symbols")
    args = ap.parse_args()
    if not tasty_available():
        sys.exit("tastytrade credentials missing: set TASTY_CLIENT_SECRET / TASTY_REFRESH_TOKEN")

    syms = [s.upper() for s in args.symbols] or sorted(
        {s for v in CLUSTERS.values() for s in v} | {s for v in CALL_SIDE_WATCH.values() for s in v}
    )
    m = iv_metrics(syms)
    today = datetime.now(timezone.utc).date()
    rows = []
    for s in syms:
        it = m.get(s)
        if not it or it.get("ivr") is None:
            continue
        earn = it.get("earnings")
        try:
            edays = (date.fromisoformat(earn) - today).days if earn else None
        except ValueError:
            edays = None
        rows.append((s, it, edays))
    rows.sort(key=lambda r: -r[1]["ivr"])

    print(f"IV rank board  {today}   ({len(rows)}/{len(syms)} symbols returned)")
    print(f"{'symbol':<7} {'IVR':>4} {'IVpct':>5} {'IV idx':>7} {'5d chg':>7} {'liq':>3}  {'label':<5} "
          f"{'earnings':>10} {'in 45d':>6}  cluster")
    for s, it, edays in rows:
        if it["ivr"] < args.min:
            continue
        iv = f"{it['iv']:.1%}" if it.get("iv") is not None else "-"
        chg = f"{it['chg5d']:+.1%}" if it.get("chg5d") is not None else "-"
        ivp = f"{it['ivp']:.0f}" if it.get("ivp") is not None else "-"
        flag = "YES" if edays is not None and 0 <= edays <= 45 else ""
        cl = cluster_of(s) or ("call-watch" if any(s in v for v in CALL_SIDE_WATCH.values()) else "-")
        print(f"{s:<7} {it['ivr']:>4.0f} {ivp:>5} {iv:>7} {chg:>7} {str(it.get('liq') or '-'):>3}  "
              f"{ivr_label(it['ivr']):<5} {str(it.get('earnings') or '-'):>10} {flag:>6}  {cl}")
    missing = [s for s in syms if s not in m]
    if missing:
        print(f"\nno metrics for: {' '.join(missing)}")


if __name__ == "__main__":
    main()
