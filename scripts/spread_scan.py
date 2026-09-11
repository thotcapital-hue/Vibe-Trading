#!/usr/bin/env python3
"""Two-sided credit-spread scanner + paper executor (Alpaca) — v4 rules.

--side put   Bull put spread on an uptrending name. Short strike must be BELOW
             support AND outside the 1-SD expected move (spot - EM).
--side call  Bear call spread on a broken/downtrending name ("sell the rip").
             Short strike must be ABOVE resistance AND outside the 1-SD
             expected move (spot + EM). Skipped when 25-delta skew is
             call-lean (greed/squeeze risk) unless --allow-call-lean.

Shared rules: 30-45 DTE window, firm credit gate (mid credit >= 15% of
width), open-interest floor per leg, earnings inside the trade excluded,
portfolio-heat cap and one-position-per-cluster enforced on --submit.
Sizing = floor(equity * risk% * conviction / max loss). Management: take
profit at 50% of credit, hard close at 21 DTE.

Data: Alpaca options snapshots (Greeks/IV/NBBO, OPRA with indicative
fallback); OI from the trading API contracts endpoint. Orders are one
multi-leg (mleg) net-credit DAY limit, HARDWIRED TO THE PAPER ENDPOINT.
Credentials: ALPACA_API_KEY / ALPACA_SECRET_KEY or ~/.vibe-trading/.env.
Talks to Alpaca over plain REST (scripts/alpaca_rest.py) -- no SDK, no
pip install needed beyond the standard library.

Usage:
    python scripts/spread_scan.py AAPL --side put  --level 300
    python scripts/spread_scan.py BX   --side call --level 120 --conviction half
    python scripts/spread_scan.py AAPL --side put  --level 300 --short 300 --long 295 --submit
(put_spread_scan.py / call_spread_scan.py are thin wrappers that preset --side.)
"""

from __future__ import annotations

import argparse
import math
import os
import sys
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from alpaca_rest import APIError, AlpacaREST
from board import ETFS, cluster_of, next_earnings, parse_occ, portfolio_heat, print_heat

RISK_FREE_RATE = 0.04
ENV_FALLBACK = Path.home() / ".vibe-trading" / ".env"

SIDE = {
    "put": {"cp": "P", "delta": (-0.25, -0.05), "level": "support", "thesis": "bullish-above"},
    "call": {"cp": "C", "delta": (0.05, 0.25), "level": "resistance", "thesis": "bearish-below"},
}


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


def norm_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def bs_delta(spot: float, strike: float, iv: float | None, t_years: float, cp: str) -> float | None:
    """Black-Scholes delta fallback for snapshots missing Greeks."""
    if not iv or iv <= 0 or t_years <= 0:
        return None
    d1 = (math.log(spot / strike) + (RISK_FREE_RATE + 0.5 * iv * iv) * t_years) / (
        iv * math.sqrt(t_years)
    )
    n = norm_cdf(d1)
    return n if cp == "C" else n - 1.0


@dataclass
class Leg:
    symbol: str
    strike: float
    bid: float
    ask: float
    iv: float | None
    delta: float | None
    open_interest: int | None = None

    @property
    def mid(self) -> float:
        if self.bid > 0 and self.ask > 0:
            return (self.bid + self.ask) / 2.0
        return max(self.bid, 0.0)


@dataclass
class Spread:
    side: str
    short: Leg
    long: Leg
    expiration: date
    dte: int
    skew: float | None = None  # 25Δ put IV − call IV, vol points (+ = put-lean)

    @property
    def width(self) -> float:
        return abs(self.short.strike - self.long.strike)

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

    @property
    def call_lean(self) -> bool:
        return self.side == "call" and self.skew is not None and self.skew < 0


def fetch_chain(client: AlpacaREST, symbol: str, exp_gte: date, exp_lte: date, feed: str) -> dict[str, dict]:
    """Pull the snapshot chain (both types), falling back to the indicative feed."""
    for attempt_feed in (feed, "indicative"):
        try:
            chain = client.option_chain(symbol, exp_gte, exp_lte, attempt_feed)
            if attempt_feed != feed:
                print(f"[warn] {feed} feed unavailable; using indicative quotes")
            return chain
        except APIError as exc:
            if attempt_feed == "indicative":
                raise
            print(f"[warn] chain fetch on {attempt_feed} failed ({exc}); retrying")
    return {}


def fetch_open_interest(client: AlpacaREST, symbol: str, side: str, exp_gte: date, exp_lte: date, level: float) -> dict[str, int]:
    """OCC symbol -> open interest for legs beyond the level (best effort)."""
    oi: dict[str, int] = {}
    bound = {"strike_price_lte": str(level)} if side == "put" else {"strike_price_gte": str(level)}
    try:
        for c in client.option_contracts(symbol, exp_gte, exp_lte, side, **bound):
            if c.get("open_interest") is not None:
                oi[c["symbol"]] = int(float(c["open_interest"]))
    except Exception as exc:  # OI is advisory; never kill the scan over it
        print(f"[warn] open-interest lookup failed: {exc}")
    return oi


def expected_move(spot: float, puts: dict[float, Leg], calls: dict[float, Leg], t_years: float) -> tuple[float, float, float]:
    """1-SD expected move: the wider of ATM straddle mid and S*IV*sqrt(T)."""
    atm_put = min(puts.values(), key=lambda l: abs(l.strike - spot), default=None)
    atm_call = min(calls.values(), key=lambda l: abs(l.strike - spot), default=None)
    straddle = (atm_put.mid if atm_put else 0.0) + (atm_call.mid if atm_call else 0.0)
    ivs = [l.iv for l in (atm_put, atm_call) if l and l.iv]
    atm_iv = sum(ivs) / len(ivs) if ivs else 0.0
    return max(straddle, spot * atm_iv * math.sqrt(t_years)), straddle, atm_iv


def skew_25d(spot: float, puts: dict[float, Leg], calls: dict[float, Leg], t_years: float) -> float | None:
    """25Δ put IV minus 25Δ call IV in vol points. Positive = put-lean (fear)."""
    def nearest(legs: dict[float, Leg], target: float, cp: str) -> Leg | None:
        best, best_d = None, 1.0
        for l in legs.values():
            if not l.iv:
                continue
            d = l.delta if l.delta is not None else bs_delta(spot, l.strike, l.iv, t_years, cp)
            if d is not None and abs(d - target) < best_d:
                best, best_d = l, abs(d - target)
        return best

    p, c = nearest(puts, -0.25, "P"), nearest(calls, 0.25, "C")
    if p is None or c is None:
        return None
    return (p.iv - c.iv) * 100.0


def build_candidates(
    side: str,
    spot: float,
    level: float,
    by_exp: dict[date, dict[str, dict[float, Leg]]],
    today: date,
    earnings: date | None,
    widths: list[float],
    delta_band: tuple[float, float],
    oi_map: dict[str, int],
    min_oi: int,
    log=print,
) -> list[Spread]:
    """Apply the v4 strike rules per expiry and return every positive-credit spread."""
    cp = SIDE[side]["cp"]
    candidates: list[Spread] = []
    for exp in sorted(by_exp):
        dte = (exp - today).days
        if earnings and today <= earnings <= exp:
            log(f"\n{exp} ({dte} DTE): skipped — earnings {earnings} falls inside the trade")
            continue
        t_years = dte / 365.0
        puts, calls = by_exp[exp]["P"], by_exp[exp]["C"]
        em, straddle, atm_iv = expected_move(spot, puts, calls, t_years)
        skew = skew_25d(spot, puts, calls, t_years)
        if side == "put":
            bound = min(spot - em, level)
            legs, order, sign = puts, True, -1.0
            bound_txt = f"short-strike floor {bound:.2f}"
        else:
            bound = max(spot + em, level)
            legs, order, sign = calls, False, 1.0
            bound_txt = f"short-strike ceiling {bound:.2f}"
        skew_txt = "n/a" if skew is None else f"{skew:+.1f} vol ({'put-lean' if skew >= 0 else 'CALL-LEAN'})"
        log(f"\n{exp} ({dte} DTE): ATM IV {atm_iv:.1%}, straddle {straddle:.2f}, "
            f"1-SD EM {em:.2f} -> {bound_txt}; 25Δ skew {skew_txt}")
        for strike in sorted(legs, reverse=order):
            short = legs[strike]
            beyond = strike <= bound if side == "put" else strike >= bound
            if not beyond or short.bid <= 0:
                continue
            delta = short.delta if short.delta is not None else bs_delta(spot, strike, short.iv, t_years, cp)
            if delta is None or not (delta_band[0] <= delta <= delta_band[1]):
                continue
            short.delta = delta
            short.open_interest = oi_map.get(short.symbol)
            for width in widths:
                long = legs.get(strike + sign * width)
                if long is None or long.ask <= 0:
                    continue
                long.open_interest = oi_map.get(long.symbol)
                sp = Spread(side=side, short=short, long=long, expiration=exp, dte=dte, skew=skew)
                if sp.credit_mid <= 0:
                    continue
                if min_oi > 0 and oi_map and (
                    (short.open_interest or 0) < min_oi or (long.open_interest or 0) < min_oi
                ):
                    continue
                candidates.append(sp)
    return candidates


def size_position(equity: float, risk_pct: float, conviction: float, max_loss: float) -> int:
    if max_loss <= 0:
        return 0
    return max(int(equity * (risk_pct / 100.0) * conviction // (max_loss * 100.0)), 0)


def submit_paper_order(client: AlpacaREST, spread: Spread, qty: int, limit_credit: float) -> dict:
    """Place the spread as one mleg net-credit DAY limit order on PAPER.

    Alpaca's multi-leg convention: negative limit price = net credit received.
    Leg roles are identical for both sides: sell the short strike to open,
    buy the protective strike to open.
    """
    legs = [
        {"symbol": spread.short.symbol, "ratio_qty": "1", "side": "sell", "position_intent": "sell_to_open"},
        {"symbol": spread.long.symbol, "ratio_qty": "1", "side": "buy", "position_intent": "buy_to_open"},
    ]
    return client.submit_mleg_limit_order(legs, qty, -round(limit_credit, 2))


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("symbol", help="underlying, e.g. AAPL")
    ap.add_argument("--side", choices=list(SIDE), default="put")
    ap.add_argument("--level", "--support", "--resistance", dest="level", type=float, required=True,
                    help="support (put) or resistance (call) level the short strike must be beyond")
    ap.add_argument("--dte-min", type=int, default=30)
    ap.add_argument("--dte-max", type=int, default=45)
    ap.add_argument("--widths", default="5,10", help="comma-separated spread widths")
    ap.add_argument("--delta-min", type=float, help="short-leg delta band low (side default)")
    ap.add_argument("--delta-max", type=float, help="short-leg delta band high (side default)")
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
    ap.add_argument("--earnings", help="override next earnings date YYYY-MM-DD")
    ap.add_argument("--no-earnings-check", action="store_true", help="skip the earnings lookup")
    ap.add_argument("--max-heat", type=float, default=15.0, help="cap on total max loss, %% of equity")
    ap.add_argument("--allow-cluster-dup", action="store_true", help="permit a second position in an occupied cluster")
    ap.add_argument("--allow-call-lean", action="store_true", help="call side: submit even when 25Δ skew is call-lean")
    return ap


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    side = args.side
    cfg = SIDE[side]
    delta_band = (
        args.delta_min if args.delta_min is not None else cfg["delta"][0],
        args.delta_max if args.delta_max is not None else cfg["delta"][1],
    )

    key, secret = load_keys()
    client = AlpacaREST(key, secret)  # trading calls go to the paper endpoint only, by design

    symbol = args.symbol.upper()
    today = datetime.now(timezone.utc).date()
    exp_gte = today + timedelta(days=args.dte_min)
    exp_lte = today + timedelta(days=args.dte_max)

    # ---- spot -------------------------------------------------------------
    try:
        spot, spot_ts = client.latest_trade(symbol, "sip")
    except APIError:
        spot, spot_ts = client.latest_trade(symbol, "iex")
    print(f"{symbol} {side.upper()} side  spot {spot:.2f}  ({spot_ts})  {cfg['level']} {args.level:.2f}")
    thesis_off = spot <= args.level if side == "put" else spot >= args.level
    if thesis_off:
        print(f"[warn] spot is on the wrong side of {cfg['level']} — {cfg['thesis']}-{args.level:g} thesis not active")

    # ---- earnings ---------------------------------------------------------
    earnings: date | None = None
    if not args.no_earnings_check:
        earnings = date.fromisoformat(args.earnings) if args.earnings else next_earnings(symbol)
        if earnings:
            inside = "  (inside DTE window: those expiries are skipped)" if earnings <= exp_lte else ""
            print(f"next earnings: {earnings}{inside}")
        elif symbol not in ETFS:
            print("[warn] earnings date unknown — confirm manually before entry")

    # ---- equity + open book ----------------------------------------------
    equity = args.equity
    if equity is None:
        try:
            equity = float(client.account()["equity"])
            print(f"paper account equity: {equity:,.0f}")
        except Exception:
            equity = 100_000.0
            print("[warn] could not read account equity; sizing on 100,000")
    conviction = 1.0 if args.conviction == "full" else 0.5
    try:
        book = portfolio_heat(client)
    except Exception as exc:
        print(f"[warn] could not read open positions: {exc}")
        book = []
    heat = print_heat(book, equity, args.max_heat)
    cluster = cluster_of(symbol)
    occupied = {sp.cluster for sp in book if sp.cluster}
    if cluster and cluster in occupied:
        print(f"[cluster] {cluster} already has an open position — new entry needs --allow-cluster-dup")

    # ---- chain ------------------------------------------------------------
    chain = fetch_chain(client, symbol, exp_gte, exp_lte, args.feed)
    by_exp: dict[date, dict[str, dict[float, Leg]]] = {}
    for occ, snap in chain.items():
        _, exp, cp, strike = parse_occ(occ)
        q = snap.get("latestQuote")
        if not q:
            continue
        greeks = snap.get("greeks") or {}
        by_exp.setdefault(exp, {"P": {}, "C": {}})[cp][strike] = Leg(
            symbol=occ,
            strike=strike,
            bid=float(q.get("bp") or 0),
            ask=float(q.get("ap") or 0),
            iv=snap.get("impliedVolatility"),
            delta=greeks.get("delta"),
        )
    if not by_exp:
        sys.exit("no contracts returned in the DTE window")

    oi_map = (
        fetch_open_interest(client, symbol, side, exp_gte, exp_lte, args.level)
        if args.min_oi > 0 else {}
    )
    widths = [float(w) for w in args.widths.split(",") if w.strip()]
    candidates = build_candidates(
        side, spot, args.level, by_exp, today, earnings, widths, delta_band, oi_map, args.min_oi
    )
    if not candidates:
        sys.exit(f"\nNo {side} spreads beyond the strike bound with positive credit. Walk.")

    candidates.sort(key=lambda s: s.credit_over_width, reverse=True)
    print(
        f"\n{'exp':>10} {'dte':>4} {'short/long':>14} {'Δ':>7} {'cr mid':>7} "
        f"{'cr nat':>7} {'cr/w':>6} {'maxL':>7} {'qty':>4} {'OI s/l':>11}  gate"
    )
    for sp in candidates[:12]:
        qty = size_position(equity, args.risk_pct, conviction, sp.max_loss)
        gate = "PASS" if sp.credit_over_width >= args.credit_gate else "thin"
        if sp.call_lean:
            gate += " call-lean"
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
            (s for s in candidates
             if s.short.strike == args.short and s.long.strike == args.long
             and (not args.exp or str(s.expiration) == args.exp)),
            None,
        )
        if pick is None:
            sys.exit("\npinned strikes not found among candidates")
    else:
        pick = candidates[0]

    qty = size_position(equity, args.risk_pct, conviction, pick.max_loss)
    credit = args.limit if args.limit is not None else round(pick.credit_mid, 2)
    label = "bull put" if side == "put" else "bear call"
    print(
        f"\nSELECTED: {symbol} {pick.expiration} {pick.short.strike:g}/{pick.long.strike:g} "
        f"{label} credit spread x{qty} @ {credit:.2f} credit "
        f"(max loss {pick.max_loss * 100 * max(qty, 1):,.0f} on {max(qty, 1)} lots)"
    )
    print(f"management: take profit at {credit / 2:.2f} debit (50%), hard close at 21 DTE")
    new_risk = pick.max_loss * 100 * qty
    heat_after = heat + new_risk
    heat_after_pct = heat_after / equity * 100 if heat_after != float("inf") else float("inf")
    print(f"heat after entry: {heat_after:,.0f} = {heat_after_pct:.1f}% of equity (cap {args.max_heat:.0f}%)")
    if pick.credit_over_width < args.credit_gate:
        print(f"[gate] credit/width {pick.credit_over_width:.1%} < {args.credit_gate:.0%} "
              "— v4 says WALK (or wait for a red day / vol pop)")
    if pick.call_lean:
        print(f"[skew] 25Δ skew {pick.skew:+.1f} vol is CALL-LEAN — v4 says skip bear calls (squeeze risk)")

    if not args.submit:
        print("\ndry run (pass --submit to place on PAPER)")
        return
    if qty < 1:
        sys.exit("sized to 0 contracts; refusing to submit")
    if thesis_off:
        sys.exit(f"thesis not active: spot on the wrong side of {cfg['level']}; refusing")
    if pick.credit_over_width < args.credit_gate and args.limit is None:
        sys.exit("credit gate failed; refusing to submit without an explicit --limit")
    if pick.call_lean and not args.allow_call_lean:
        sys.exit("call-lean skew; refusing bear call spread without --allow-call-lean")
    if heat_after_pct > args.max_heat:
        sys.exit(f"heat cap: entry would put {heat_after_pct:.1f}% of equity at risk (> {args.max_heat:.0f}%); refusing")
    if cluster and cluster in occupied and not args.allow_cluster_dup:
        sys.exit(f"cluster cap: {cluster} already occupied; pass --allow-cluster-dup to override")
    order = submit_paper_order(client, pick, qty, credit)
    print(f"\nPAPER order submitted: id={order['id']} status={order['status']}")


if __name__ == "__main__":
    main()
