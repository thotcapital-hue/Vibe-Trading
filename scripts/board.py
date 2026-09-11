"""Shared board helpers for the put-spread scripts: clusters, earnings, heat.

Imported by put_spread_scan.py and regime_check.py (both run as
``python scripts/<name>.py`` so this directory is already on sys.path).
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path

# Board universe by risk cluster: max ONE open position per cluster, max two
# clusters from {tech/mega, semis, index} combined (QQQ counts as tech).
# Names chosen for penny-wide, deep-OI option chains.
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

# Funds have no earnings; skip the lookup entirely for them.
ETFS = {"QQQ", "SMH", "SPY", "IWM", "DIA", "XLF", "XLV", "XLP", "XLE", "XLI",
        "TLT", "GLD", "SLV", "XLK", "XLY", "XLU", "XLB", "XLRE", "XLC", "RSP"}

# Call-side watch: broken/downtrending names for bear call spreads (v4 two-sided).
CALL_SIDE_WATCH: dict[str, list[str]] = {
    "alt managers (private credit)": ["BX", "KKR", "APO", "ARES", "OWL"],
}

# Regime / breadth inputs used by regime_check.py.
REGIME_SYMBOLS: dict[str, list[str]] = {
    "regime": ["SPY", "RSP", "IWM", "TVC:VIX"],
    "sectors": ["XLK", "XLF", "XLV", "XLP", "XLE", "XLI", "XLY", "XLU", "XLB", "XLRE", "XLC"],
    "mag-7": ["AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "TSLA"],
}

# TradingView exchange prefixes (ETFs listed on NYSE Arca are AMEX: on TradingView).
_NASDAQ = {"AAPL", "MSFT", "GOOGL", "META", "AMZN", "QQQ", "NVDA", "AVGO", "AMD", "SMH",
           "COST", "HON", "TLT", "TSLA", "WMT"}
_AMEX = {"SPY", "IWM", "DIA", "XLF", "XLV", "XLP", "XLE", "XLI", "GLD", "SLV", "RSP",
         "XLK", "XLY", "XLU", "XLB", "XLRE", "XLC"}


def tv_symbol(symbol: str) -> str:
    if ":" in symbol:
        return symbol
    if symbol in _NASDAQ:
        return f"NASDAQ:{symbol}"
    if symbol in _AMEX:
        return f"AMEX:{symbol}"
    return f"NYSE:{symbol}"


def tradingview_watchlist() -> str:
    """TradingView import format: comma-separated symbols, ``###`` section headers."""
    sections: list[tuple[str, list[str]]] = []
    sections += [(f"PUT SIDE — {name}", syms) for name, syms in CLUSTERS.items()]
    sections += [(f"CALL SIDE — {name}", syms) for name, syms in CALL_SIDE_WATCH.items()]
    sections += [(f"REGIME — {name}", syms) for name, syms in REGIME_SYMBOLS.items()]
    parts: list[str] = []
    for title, syms in sections:
        parts.append(f"###{title}")
        parts.append(",".join(tv_symbol(s) for s in syms))
    return ",".join(parts) + "\n"


_AGENT_DIR = Path(__file__).resolve().parent.parent / "agent"


def cluster_of(symbol: str) -> str | None:
    for name, syms in CLUSTERS.items():
        if symbol in syms:
            return name
    return None


def parse_occ(symbol: str) -> tuple[str, date, str, float]:
    """(root, expiration, 'C'/'P', strike) from an OCC option symbol.

    Last 15 chars = yymmdd + C/P + strike*1000 zero-padded to 8; the rest is
    the root. Snapshots and positions key by this symbol and carry no
    strike/expiry fields of their own.
    """
    tail = symbol[-15:]
    return (
        symbol[:-15],
        datetime.strptime(tail[:6], "%y%m%d").date(),
        tail[6],
        int(tail[7:]) / 1000.0,
    )


def next_earnings(symbol: str) -> date | None:
    """Next confirmed/estimated earnings date via the repo's Yahoo client.

    Returns None for ETFs and on any failure (the caller decides whether a
    missing date blocks the trade).
    """
    if symbol in ETFS:
        return None
    if str(_AGENT_DIR) not in sys.path:
        sys.path.insert(0, str(_AGENT_DIR))
    try:
        from backtest.loaders import yahoo_client

        summary = yahoo_client.get_quote_summary(symbol, ["calendarEvents"])
        dates = (((summary.get("calendarEvents") or {}).get("earnings") or {})
                 .get("earningsDate") or [])
        today = datetime.now(timezone.utc).date()
        parsed = []
        for d in dates:
            raw = d.get("raw") if isinstance(d, dict) else None
            if raw:
                parsed.append(datetime.fromtimestamp(int(raw), tz=timezone.utc).date())
        future = sorted(x for x in parsed if x >= today)
        return future[0] if future else None
    except Exception as exc:  # noqa: BLE001 — advisory lookup
        print(f"[warn] earnings lookup failed for {symbol}: {exc}")
        return None


@dataclass
class OpenSpread:
    underlying: str
    expiration: date
    kind: str            # "put" | "call" | "NAKED"
    short_strike: float
    long_strike: float | None
    qty: int
    credit: float        # net credit per spread at entry (0 if unknown)

    @property
    def max_loss(self) -> float:
        """Dollars at risk; float('inf') for an unpaired short."""
        if self.long_strike is None:
            return float("inf")
        return (abs(self.short_strike - self.long_strike) - self.credit) * 100 * self.qty

    @property
    def cluster(self) -> str | None:
        return cluster_of(self.underlying)


def portfolio_heat(trading_client) -> list[OpenSpread]:
    """Pair open short options with their long legs into defined-risk spreads.

    Pairing is by underlying, expiration and type: each short leg takes the
    nearest long leg on its protected side (below for puts, above for calls)
    with quantity still unassigned. Anything left unpaired is reported as
    NAKED with infinite max loss so the heat cap fails closed.
    """
    from alpaca.trading.enums import AssetClass

    shorts: dict[tuple, list] = {}
    longs: dict[tuple, list] = {}
    for p in trading_client.get_all_positions():
        if p.asset_class != AssetClass.US_OPTION:
            continue
        root, exp, cp, strike = parse_occ(p.symbol)
        qty = int(float(p.qty))
        price = float(p.avg_entry_price or 0)
        bucket = shorts if qty < 0 else longs
        bucket.setdefault((root, exp, cp), []).append([strike, abs(qty), price])

    spreads: list[OpenSpread] = []
    for key, short_legs in shorts.items():
        root, exp, cp = key
        kind = "put" if cp == "P" else "call"
        pool = longs.get(key, [])
        for s_strike, s_qty, s_price in sorted(short_legs, key=lambda l: -l[0] if cp == "P" else l[0]):
            remaining = s_qty
            protective = [l for l in pool if (l[0] < s_strike if cp == "P" else l[0] > s_strike) and l[1] > 0]
            protective.sort(key=lambda l: abs(l[0] - s_strike))
            for leg in protective:
                if remaining <= 0:
                    break
                take = min(remaining, leg[1])
                leg[1] -= take
                remaining -= take
                spreads.append(OpenSpread(root, exp, kind, s_strike, leg[0], take, s_price - leg[2]))
            if remaining > 0:
                spreads.append(OpenSpread(root, exp, "NAKED", s_strike, None, remaining, s_price))
    return spreads


def print_heat(spreads: list[OpenSpread], equity: float, cap_pct: float) -> float:
    """Print the open book and return total defined max loss in dollars."""
    if not spreads:
        print("open book: none")
        return 0.0
    total = 0.0
    print(f"\n{'open book':<10} {'exp':>10} {'structure':>18} {'qty':>4} {'max loss':>10}  cluster")
    for sp in sorted(spreads, key=lambda s: (s.expiration, s.underlying)):
        long_txt = f"{sp.long_strike:g}" if sp.long_strike is not None else "NAKED"
        loss_txt = f"{sp.max_loss:,.0f}" if sp.max_loss != float("inf") else "UNDEFINED"
        print(f"{sp.underlying:<10} {sp.expiration} {sp.short_strike:>8g}/{long_txt:<9} "
              f"{sp.qty:>4} {loss_txt:>10}  {sp.cluster or '-'}")
        total += sp.max_loss
    pct = total / equity * 100 if equity and total != float("inf") else float("inf")
    status = "OVER CAP" if pct > cap_pct else "ok"
    print(f"portfolio heat: {total:,.0f} = {pct:.1f}% of equity (cap {cap_pct:.0f}%) {status}")
    return total


if __name__ == "__main__":
    # `python scripts/board.py > board_watchlist.txt` — TradingView import file.
    sys.stdout.write(tradingview_watchlist())
