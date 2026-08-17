#!/usr/bin/env python3
"""EM-anchored put-credit-spread scanner + paper executor (Alpaca).

Implements the v4 entry rules for the put-spread income system:

* 30-45 DTE window (hard close planned at 21 DTE, profit take at 50%).
* Short strike must sit BELOW support AND outside the 1-standard-deviation
  expected move (the wider of the ATM straddle mid and S*IV*sqrt(T)).
* Firm credit gate: walk unless mid credit >= --credit-gate of spread width.
* Defined risk sizing: contracts = floor(equity * risk% * conviction / max loss).

Data comes from Alpaca's options snapshot API (Greeks + IV + NBBO quotes,
OPRA feed with automatic fallback to indicative), open interest from the
trading API's contracts endpoint. Order submission (--submit) builds a
multi-leg (mleg) net-credit limit order and is HARDWIRED TO THE PAPER
ENDPOINT — live execution is intentionally not implemented here.

Credentials: ALPACA_API_KEY / ALPACA_SECRET_KEY environment variables, with
fallback to ~/.vibe-trading/.env (never hardcode keys, never pass on argv).

Usage:
    python scripts/put_spread_scan.py AAPL --support 300
    python scripts/put_spread_scan.py AAPL --support 300 --equity 100000
    python scripts/put_spread_scan.py AAPL --support 300 --short 285 --long 280 \
        --exp 2026-09-18 --submit          # place on PAPER after reviewing scan
"""

from __future__ import annotations

import argparse
import math
import os
import sys
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

RISK_FREE_RATE = 0.04
ENV_FALLBACK = Path.home() / ".vibe-trading" / ".env"


def load_keys() -> tuple[str, str]:
    """Resolve Alpaca keys from the environment, else ~/.vibe-trading/.env."""
    key = os.getenv("ALPACA_API_KEY")
    secret = os.getenv("ALPACA_SECRET_KEY")
    if key and secret:
        return key, secret
    if ENV_FALLBACK.exists():
        pairs: dict[str, str] = {}
        for line in ENV_FALLBACK.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                pairs[k.strip()] = v.strip().strip("'\"")
        key = key or pairs.get("ALPACA_API_KEY")
        secret = secret or pairs.get("ALPACA_SECRET_KEY")
    if not (key and secret):
        sys.exit(
            "No Alpaca keys: set ALPACA_API_KEY / ALPACA_SECRET_KEY "
            f"or put them in {ENV_FALLBACK}"
        )
    return key, secret


def parse_occ(symbol: str) -> tuple[str, date, str, float]:
    """Split an OCC option symbol into (root, expiration, C/P, strike).

    Snapshots key by OCC symbol and carry no strike/expiry fields, so the
    symbol itself is the source of truth: last 15 chars = yymmdd + C/P +
    strike*1000 zero-padded to 8.
    """
    tail = symbol[-15:]
    root = symbol[:-15]
    exp = datetime.strptime(tail[:6], "%y%m%d").date()
    cp = tail[6]
    strike = int(tail[7:]) / 1000.0
    return root, exp, cp, strike


def norm_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def bs_put_delta(spot: float, strike: float, iv: float, t_years: float) -> float | None:
    """Black-Scholes put delta fallback for snapshots missing Greeks."""
    if not iv or iv <= 0 or t_years <= 0:
        return None
    d1 = (math.log(spot / strike) + (RISK_FREE_RATE + 0.5 * iv * iv) * t_years) / (
        iv * math.sqrt(t_years)
    )
    return norm_cdf(d1) - 1.0


@dataclass
class Leg:
    symbol: str
    strike: float
    bid: float
    ask: float
    iv: float | None
    delta: float | None
    open_interest: int | None

    @property
    def mid(self) -> float:
        if self.bid > 0 and self.ask > 0:
            return (self.bid + self.ask) / 2.0
        return max(self.bid, 0.0)


@dataclass
class Spread:
    short: Leg
    long: Leg
    expiration: date
    dte: int

    @property
    def width(self) -> float:
        return self.short.strike - self.long.strike

    @property
    def credit_mid(self) -> float:
        return self.short.mid - self.long.mid

    @property
    def credit_natural(self) -> float:
        return self.short.bid - self.long.ask

    @property
    def max_loss(self) -> float:
        return self.width - self.credit_mid

    @property
    def credit_over_width(self) -> float:
        return self.credit_mid / self.width if self.width else 0.0


def fetch_chain(data_client, symbol: str, exp_gte: date, exp_lte: date, feed: str):
    """Pull the snapshot chain, falling back to the free indicative feed."""
    from alpaca.common.exceptions import APIError
    from alpaca.data.requests import OptionChainRequest

    for attempt_feed in (feed, "indicative"):
        try:
            req = OptionChainRequest(
                underlying_symbol=symbol,
                expiration_date_gte=exp_gte,
                expiration_date_lte=exp_lte,
                feed=attempt_feed,
            )
            chain = data_client.get_option_chain(req)
            if attempt_feed != feed:
                print(f"[warn] {feed} feed unavailable; using indicative quotes")
            return chain
        except APIError as exc:
            if attempt_feed == "indicative":
                raise
            print(f"[warn] chain fetch on {attempt_feed} failed ({exc}); retrying")
    return {}


def fetch_open_interest(
    trading_client, symbol: str, exp_gte: date, exp_lte: date, strike_lte: float
) -> dict[str, int]:
    """Map OCC symbol -> open interest via the contracts endpoint (best effort)."""
    from alpaca.trading.enums import ContractType
    from alpaca.trading.requests import GetOptionContractsRequest

    oi: dict[str, int] = {}
    token = None
    try:
        while True:
            req = GetOptionContractsRequest(
                underlying_symbols=[symbol],
                expiration_date_gte=exp_gte,
                expiration_date_lte=exp_lte,
                strike_price_lte=str(strike_lte),
                type=ContractType.PUT,
                limit=10000,
                page_token=token,
            )
            resp = trading_client.get_option_contracts(req)
            for c in resp.option_contracts or []:
                if c.open_interest is not None:
                    oi[c.symbol] = int(c.open_interest)
            token = resp.next_page_token
            if not token:
                break
    except Exception as exc:  # OI is advisory; never kill the scan over it
        print(f"[warn] open-interest lookup failed: {exc}")
    return oi


def expected_move(
    spot: float, puts: dict[float, Leg], calls: dict[float, Leg], t_years: float
) -> tuple[float, float, float]:
    """1-SD expected move: the wider of ATM straddle mid and S*IV*sqrt(T)."""
    atm_put = min(puts.values(), key=lambda l: abs(l.strike - spot), default=None)
    atm_call = min(calls.values(), key=lambda l: abs(l.strike - spot), default=None)
    straddle = (atm_put.mid if atm_put else 0.0) + (atm_call.mid if atm_call else 0.0)
    ivs = [l.iv for l in (atm_put, atm_call) if l and l.iv]
    atm_iv = sum(ivs) / len(ivs) if ivs else 0.0
    em_iv = spot * atm_iv * math.sqrt(t_years)
    return max(straddle, em_iv), straddle, atm_iv


def size_position(equity: float, risk_pct: float, conviction: float, max_loss: float) -> int:
    if max_loss <= 0:
        return 0
    return max(int(equity * (risk_pct / 100.0) * conviction // (max_loss * 100.0)), 0)


def submit_paper_order(trading_client, spread: Spread, qty: int, limit_credit: float):
    """Place the spread as one mleg net-credit DAY limit order on PAPER.

    Alpaca's multi-leg convention: negative limit price = net credit received.
    """
    from alpaca.trading.enums import (
        OrderClass,
        OrderSide,
        PositionIntent,
        TimeInForce,
    )
    from alpaca.trading.requests import LimitOrderRequest, OptionLegRequest

    order = LimitOrderRequest(
        qty=qty,
        limit_price=-round(limit_credit, 2),
        order_class=OrderClass.MLEG,
        time_in_force=TimeInForce.DAY,
        legs=[
            OptionLegRequest(
                symbol=spread.short.symbol,
                ratio_qty=1,
                side=OrderSide.SELL,
                position_intent=PositionIntent.SELL_TO_OPEN,
            ),
            OptionLegRequest(
                symbol=spread.long.symbol,
                ratio_qty=1,
                side=OrderSide.BUY,
                position_intent=PositionIntent.BUY_TO_OPEN,
            ),
        ],
    )
    return trading_client.submit_order(order)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("symbol", help="underlying, e.g. AAPL")
    ap.add_argument("--support", type=float, required=True, help="support level; short strike must be below it")
    ap.add_argument("--dte-min", type=int, default=30)
    ap.add_argument("--dte-max", type=int, default=45)
    ap.add_argument("--widths", default="5,10", help="comma-separated spread widths")
    ap.add_argument("--delta-min", type=float, default=-0.25, help="short-leg delta floor")
    ap.add_argument("--delta-max", type=float, default=-0.05, help="short-leg delta ceiling")
    ap.add_argument("--credit-gate", type=float, default=0.15, help="min mid credit / width")
    ap.add_argument("--min-oi", type=int, default=100, help="min open interest per leg (0 = off)")
    ap.add_argument("--risk-pct", type=float, default=1.0, help="equity %% at risk per trade")
    ap.add_argument("--conviction", choices=["full", "half"], default="full")
    ap.add_argument("--equity", type=float, help="override account equity for sizing")
    ap.add_argument("--feed", default="opra", choices=["opra", "indicative"])
    ap.add_argument("--exp", help="pin expiration YYYY-MM-DD (with --short/--long)")
    ap.add_argument("--short", type=float, help="pin short strike")
    ap.add_argument("--long", type=float, help="pin long strike")
    ap.add_argument("--limit", type=float, help="override net-credit limit for --submit")
    ap.add_argument("--submit", action="store_true", help="submit top/pinned spread to PAPER")
    args = ap.parse_args()

    from alpaca.data.historical.option import OptionHistoricalDataClient
    from alpaca.data.historical.stock import StockHistoricalDataClient
    from alpaca.data.requests import StockLatestTradeRequest
    from alpaca.trading.client import TradingClient

    key, secret = load_keys()
    data_client = OptionHistoricalDataClient(key, secret)
    stock_client = StockHistoricalDataClient(key, secret)
    trading_client = TradingClient(key, secret, paper=True)  # paper only, by design

    symbol = args.symbol.upper()
    today = datetime.now(timezone.utc).date()
    exp_gte = today + timedelta(days=args.dte_min)
    exp_lte = today + timedelta(days=args.dte_max)

    # ---- spot -------------------------------------------------------------
    try:
        trade = stock_client.get_stock_latest_trade(
            StockLatestTradeRequest(symbol_or_symbols=symbol, feed="sip")
        )[symbol]
    except Exception:
        trade = stock_client.get_stock_latest_trade(
            StockLatestTradeRequest(symbol_or_symbols=symbol, feed="iex")
        )[symbol]
    spot = float(trade.price)
    print(f"{symbol} spot {spot:.2f}  ({trade.timestamp})  support {args.support:.2f}")
    if spot <= args.support:
        print(f"[warn] spot is AT/BELOW support — bullish-above-{args.support:g} thesis not active")

    # ---- chain ------------------------------------------------------------
    chain = fetch_chain(data_client, symbol, exp_gte, exp_lte, args.feed)
    by_exp: dict[date, dict[str, dict[float, Leg]]] = {}
    for occ, snap in chain.items():
        _, exp, cp, strike = parse_occ(occ)
        q = snap.latest_quote
        if q is None:
            continue
        greeks = getattr(snap, "greeks", None)
        leg = Leg(
            symbol=occ,
            strike=strike,
            bid=float(q.bid_price or 0),
            ask=float(q.ask_price or 0),
            iv=getattr(snap, "implied_volatility", None),
            delta=getattr(greeks, "delta", None) if greeks else None,
            open_interest=None,
        )
        by_exp.setdefault(exp, {"P": {}, "C": {}})[cp][strike] = leg
    if not by_exp:
        sys.exit("no contracts returned in the DTE window")

    oi_map = (
        fetch_open_interest(trading_client, symbol, exp_gte, exp_lte, args.support)
        if args.min_oi > 0
        else {}
    )

    widths = [float(w) for w in args.widths.split(",") if w.strip()]
    candidates: list[Spread] = []

    for exp in sorted(by_exp):
        dte = (exp - today).days
        t_years = dte / 365.0
        puts, calls = by_exp[exp]["P"], by_exp[exp]["C"]
        em, straddle, atm_iv = expected_move(spot, puts, calls, t_years)
        floor = min(spot - em, args.support)
        print(
            f"\n{exp} ({dte} DTE): ATM IV {atm_iv:.1%}, straddle {straddle:.2f}, "
            f"1-SD EM {em:.2f} -> short-strike floor {floor:.2f}"
        )
        for strike in sorted(puts, reverse=True):
            short = puts[strike]
            if strike > floor or short.bid <= 0:
                continue
            delta = short.delta or bs_put_delta(spot, strike, short.iv, t_years)
            if delta is None or not (args.delta_min <= delta <= args.delta_max):
                continue
            short.delta = delta
            short.open_interest = oi_map.get(short.symbol)
            for width in widths:
                long = puts.get(strike - width)
                if long is None or long.ask <= 0:
                    continue
                long.open_interest = oi_map.get(long.symbol)
                sp = Spread(short=short, long=long, expiration=exp, dte=dte)
                if sp.credit_mid <= 0:
                    continue
                if args.min_oi > 0 and oi_map and (
                    (short.open_interest or 0) < args.min_oi
                    or (long.open_interest or 0) < args.min_oi
                ):
                    continue
                candidates.append(sp)

    if not candidates:
        sys.exit("\nNo spreads under the strike floor with positive credit. Walk.")

    equity = args.equity
    if equity is None:
        try:
            equity = float(trading_client.get_account().equity)
            print(f"\npaper account equity: {equity:,.0f}")
        except Exception:
            equity = 100_000.0
            print("\n[warn] could not read account equity; sizing on 100,000")
    conviction = 1.0 if args.conviction == "full" else 0.5

    candidates.sort(key=lambda s: s.credit_over_width, reverse=True)
    print(
        f"\n{'exp':>10} {'dte':>4} {'short/long':>14} {'Δ':>7} {'cr mid':>7} "
        f"{'cr nat':>7} {'cr/w':>6} {'maxL':>7} {'qty':>4} {'OI s/l':>11}  gate"
    )
    for sp in candidates[:12]:
        qty = size_position(equity, args.risk_pct, conviction, sp.max_loss)
        gate = "PASS" if sp.credit_over_width >= args.credit_gate else "thin"
        oi_s = sp.short.open_interest if sp.short.open_interest is not None else "-"
        oi_l = sp.long.open_interest if sp.long.open_interest is not None else "-"
        print(
            f"{sp.expiration} {sp.dte:>4} {sp.short.strike:>7.1f}/{sp.long.strike:<6.1f} "
            f"{sp.short.delta:>7.3f} {sp.credit_mid:>7.2f} {sp.credit_natural:>7.2f} "
            f"{sp.credit_over_width:>6.1%} {sp.max_loss:>7.2f} {qty:>4} "
            f"{str(oi_s):>5}/{str(oi_l):<5}  {gate}"
        )

    # ---- pick + (optionally) submit --------------------------------------
    if args.short and args.long:
        pick = next(
            (
                s
                for s in candidates
                if s.short.strike == args.short
                and s.long.strike == args.long
                and (not args.exp or str(s.expiration) == args.exp)
            ),
            None,
        )
        if pick is None:
            sys.exit("\npinned strikes not found among candidates")
    else:
        pick = candidates[0]

    qty = size_position(equity, args.risk_pct, conviction, pick.max_loss)
    credit = args.limit if args.limit is not None else round(pick.credit_mid, 2)
    print(
        f"\nSELECTED: {symbol} {pick.expiration} {pick.short.strike:g}/{pick.long.strike:g} "
        f"put credit spread x{qty} @ {credit:.2f} credit "
        f"(max loss {pick.max_loss * 100 * max(qty, 1):,.0f} on {max(qty,1)} lots)"
    )
    print(f"management: take profit at {credit / 2:.2f} debit (50%), hard close at 21 DTE")
    if pick.credit_over_width < args.credit_gate:
        print(
            f"[gate] credit/width {pick.credit_over_width:.1%} < {args.credit_gate:.0%} "
            "— v4 says WALK (or wait for a red day / vol pop)"
        )

    if not args.submit:
        print("\ndry run (pass --submit to place on PAPER)")
        return
    if qty < 1:
        sys.exit("sized to 0 contracts; refusing to submit")
    if pick.credit_over_width < args.credit_gate and args.limit is None:
        sys.exit("credit gate failed; refusing to submit without an explicit --limit")
    order = submit_paper_order(trading_client, pick, qty, credit)
    print(f"\nPAPER order submitted: id={order.id} status={order.status}")


if __name__ == "__main__":
    main()
