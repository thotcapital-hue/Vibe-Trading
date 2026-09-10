#!/usr/bin/env python3
"""Daily regime + breadth gate for the put-spread income board (Alpaca bars).

Prints GREEN / CAUTION / RED with a size multiplier, from:

* Trend:      SPY vs 50-DMA and 200-DMA; IWM vs 50-DMA (small-cap confirmation).
* Breadth:    RSP/SPY ratio (equal-weight vs cap-weight) 20-day change — the
              index can only be "held up by a few names" if this is falling.
              Sector participation: share of the 11 SPDR sectors above 50-DMA.
* Leadership: share of Mag-7 above 50-DMA and within 3% of 20-day highs.
* Fear:       VIX (pass --vix; else fetched from CBOE's daily history CSV).

Also prints the cluster table for the board so no two positions share a
cluster (QQQ counts as tech). Credentials as in put_spread_scan.py.

Usage:
    python scripts/regime_check.py
    python scripts/regime_check.py --vix 16.1
"""

from __future__ import annotations

import argparse
import csv
import io
import os
import sys
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

ENV_FALLBACK = Path.home() / ".vibe-trading" / ".env"
VIX_CSV = "https://cdn.cboe.com/api/global/us_indices/daily_prices/VIX_History.csv"

MAG7 = ["AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "TSLA"]
SECTORS = ["XLK", "XLF", "XLV", "XLP", "XLE", "XLI", "XLY", "XLU", "XLB", "XLRE", "XLC"]

# Board universe by risk cluster: max ONE open position per cluster, max two
# clusters from {tech, semis, index} combined. Names chosen for penny-wide,
# deep-OI option chains.
CLUSTERS: dict[str, list[str]] = {
    "tech/mega": ["AAPL", "MSFT", "GOOGL", "META", "AMZN", "QQQ"],
    "semis": ["NVDA", "AVGO", "AMD", "SMH"],
    "index": ["SPY", "IWM", "DIA"],
    "financials": ["JPM", "GS", "BAC", "XLF", "V", "MA"],
    "healthcare": ["LLY", "JNJ", "UNH", "XLV"],
    "staples/defensive": ["WMT", "COST", "PG", "KO", "XLP"],
    "energy": ["XOM", "CVX", "XLE"],
    "industrials": ["CAT", "GE", "HON", "XLI"],
    "rates/metals": ["TLT", "GLD", "SLV"],
}


def load_keys() -> tuple[str, str]:
    key, secret = os.getenv("ALPACA_API_KEY"), os.getenv("ALPACA_SECRET_KEY")
    if not (key and secret) and ENV_FALLBACK.exists():
        pairs = {}
        for line in ENV_FALLBACK.read_text().splitlines():
            if "=" in line and not line.strip().startswith("#"):
                k, _, v = line.partition("=")
                pairs[k.strip()] = v.strip().strip("'\"")
        key = key or pairs.get("ALPACA_API_KEY")
        secret = secret or pairs.get("ALPACA_SECRET_KEY")
    if not (key and secret):
        sys.exit("No Alpaca keys in env or ~/.vibe-trading/.env")
    return key, secret


def fetch_closes(client, symbols: list[str], days: int = 320) -> dict[str, list[float]]:
    from alpaca.data.requests import StockBarsRequest
    from alpaca.data.timeframe import TimeFrame

    start = datetime.now(timezone.utc) - timedelta(days=days)
    for feed in ("sip", "iex"):
        try:
            bars = client.get_stock_bars(
                StockBarsRequest(symbol_or_symbols=symbols, timeframe=TimeFrame.Day, start=start, feed=feed)
            )
            return {sym: [float(b.close) for b in blist] for sym, blist in bars.data.items()}
        except Exception as exc:
            if feed == "iex":
                raise
            print(f"[warn] sip bars failed ({exc}); retrying iex")
    return {}


def sma(series: list[float], n: int) -> float | None:
    return sum(series[-n:]) / n if len(series) >= n else None


def fetch_vix() -> float | None:
    try:
        with urllib.request.urlopen(VIX_CSV, timeout=15) as resp:
            rows = list(csv.reader(io.StringIO(resp.read().decode())))
        return float(rows[-1][4])  # DATE, OPEN, HIGH, LOW, CLOSE
    except Exception as exc:
        print(f"[warn] VIX fetch failed ({exc}); pass --vix")
        return None


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--vix", type=float, help="VIX level (skips CBOE fetch)")
    args = ap.parse_args()

    from alpaca.data.historical.stock import StockHistoricalDataClient

    key, secret = load_keys()
    client = StockHistoricalDataClient(key, secret)
    universe = sorted(set(["SPY", "RSP", "IWM"] + MAG7 + SECTORS))
    closes = fetch_closes(client, universe)
    missing = [s for s in universe if s not in closes]
    if missing:
        print(f"[warn] no bars for {missing}")

    flags: list[str] = []
    score = 0  # +1 per healthy signal, -1 per unhealthy

    # ---- trend ------------------------------------------------------------
    spy = closes["SPY"]
    spy_50, spy_200 = sma(spy, 50), sma(spy, 200)
    above_200 = spy_200 is not None and spy[-1] > spy_200
    above_50 = spy_50 is not None and spy[-1] > spy_50
    print(f"SPY {spy[-1]:.2f}  50-DMA {spy_50:.2f} ({'above' if above_50 else 'BELOW'})  "
          f"200-DMA {spy_200:.2f} ({'above' if above_200 else 'BELOW'})")
    score += 1 if above_200 else -2
    score += 1 if above_50 else -1
    if not above_200:
        flags.append("SPY below 200-DMA: regime RED, no new put spreads")

    iwm = closes.get("IWM")
    if iwm:
        iwm_50 = sma(iwm, 50)
        iwm_ok = iwm_50 is not None and iwm[-1] > iwm_50
        print(f"IWM {iwm[-1]:.2f} vs 50-DMA {iwm_50:.2f} ({'above' if iwm_ok else 'BELOW'})")
        score += 1 if iwm_ok else -1

    # ---- breadth ----------------------------------------------------------
    rsp = closes.get("RSP")
    if rsp and len(rsp) > 20 and len(spy) > 20:
        ratio_now = rsp[-1] / spy[-1]
        ratio_20 = rsp[-21] / spy[-21]
        chg = ratio_now / ratio_20 - 1
        print(f"RSP/SPY breadth proxy: {chg:+.2%} over 20d "
              f"({'broadening' if chg > 0.005 else 'NARROWING' if chg < -0.005 else 'flat'})")
        if chg < -0.005:
            score -= 1
            flags.append("breadth narrowing: index held up by few names")
        elif chg > 0.005:
            score += 1

    sect_above = [s for s in SECTORS if s in closes and sma(closes[s], 50) and closes[s][-1] > sma(closes[s], 50)]
    pct_sect = len(sect_above) / len([s for s in SECTORS if s in closes])
    print(f"sectors above 50-DMA: {len(sect_above)}/11 ({pct_sect:.0%})  {sect_above}")
    if pct_sect < 0.4:
        score -= 1
        flags.append("participation < 40% of sectors")
    elif pct_sect > 0.6:
        score += 1

    # ---- leadership -------------------------------------------------------
    lead_above, lead_high = [], []
    for s in MAG7:
        c = closes.get(s)
        if not c or len(c) < 50:
            continue
        if c[-1] > sma(c, 50):
            lead_above.append(s)
        if c[-1] >= max(c[-20:]) * 0.97:
            lead_high.append(s)
    n = len([s for s in MAG7 if s in closes])
    print(f"Mag-7 above 50-DMA: {len(lead_above)}/{n} {lead_above}")
    print(f"Mag-7 within 3% of 20d high: {len(lead_high)}/{n} {lead_high}")
    if len(lead_above) < n / 2:
        score -= 1
        flags.append("leadership override: majority of Mag-7 below 50-DMA")
    if len(lead_high) <= 2:
        flags.append("leaders not making highs: distribution watch")

    # ---- fear -------------------------------------------------------------
    vix = args.vix if args.vix is not None else fetch_vix()
    if vix is not None:
        print(f"VIX {vix:.2f}")
        if vix >= 30:
            score -= 2
            flags.append("VIX >= 30: no new entries until it stabilises")
        elif vix >= 22:
            flags.append("VIX 22-30: premium rich, size half, strikes wider")
        elif vix < 14:
            flags.append("VIX < 14: premium thin, expect gate failures")

    # ---- verdict ----------------------------------------------------------
    if not above_200 or (vix or 0) >= 30 or score <= -2:
        verdict, mult = "RED", 0.0
    elif score >= 3 and not flags:
        verdict, mult = "GREEN", 1.0
    else:
        verdict, mult = "CAUTION", 0.5
    print(f"\nREGIME: {verdict}  size multiplier x{mult}  (score {score:+d})")
    for f in flags:
        print(f"  - {f}")
    if verdict == "RED":
        print("  -> put spreads OFF; bear call spreads on broken names only (v4 two-sided)")

    print("\nBoard clusters (max one open position per cluster):")
    for name, syms in CLUSTERS.items():
        print(f"  {name:<18} {' '.join(syms)}")


if __name__ == "__main__":
    main()
