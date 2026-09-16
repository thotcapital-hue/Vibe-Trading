#!/usr/bin/env python3
"""Read-only tastytrade Open API client (stdlib only) + connection self-test.

Why this exists: tastytrade's ``/market-metrics`` endpoint returns implied
volatility RANK and PERCENTILE per symbol (where today's IV sits against the
past year), plus liquidity rating and the next earnings date. Alpaca gives us
current IV but no history, so this is the missing context for the credit gate.

Auth is an OAuth2 "personal grant": a never-expiring refresh token is swapped
for a 15-minute access token on demand. The OAuth app must be created with the
``read`` scope only. THIS MODULE HAS NO ORDER FUNCTIONS BY DESIGN and must not
grow any: Sanjay's real accounts are advise-only.

Env vars (never print them):  TASTY_CLIENT_SECRET, TASTY_REFRESH_TOKEN
Optional: TASTY_SANDBOX=1 to hit api.cert.tastyworks.com instead of production.

Usage:
    python scripts/tasty_rest.py --check AAPL GOOGL AVGO   # what can this account reach?
    python scripts/tasty_rest.py --metrics AAPL GOOGL      # IV rank table
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

PROD_URL = "https://api.tastyworks.com"
SANDBOX_URL = "https://api.cert.tastyworks.com"
USER_AGENT = "vibe-trading-board/1.0"
TIMEOUT = 30


class TastyError(Exception):
    def __init__(self, status: int, body: str, path: str):
        self.status, self.body, self.path = status, body, path
        super().__init__(f"HTTP {status} on {path}: {body[:300]}")


class TastyREST:
    def __init__(self, client_secret: str | None = None, refresh_token: str | None = None, sandbox: bool | None = None):
        self._secret = client_secret or os.getenv("TASTY_CLIENT_SECRET")
        self._refresh = refresh_token or os.getenv("TASTY_REFRESH_TOKEN")
        if not (self._secret and self._refresh):
            sys.exit("No tastytrade credentials: set TASTY_CLIENT_SECRET and TASTY_REFRESH_TOKEN")
        if sandbox is None:
            sandbox = os.getenv("TASTY_SANDBOX", "").strip() not in ("", "0", "false")
        self.base = SANDBOX_URL if sandbox else PROD_URL
        self._token: str | None = None
        self._token_exp = 0.0

    # ---- auth -------------------------------------------------------------
    def _refresh_access_token(self) -> None:
        body = {"grant_type": "refresh_token", "refresh_token": self._refresh, "client_secret": self._secret}
        url = f"{self.base}/oauth/token"
        # Docs show a JSON body; some clients send form-encoded. Try JSON first.
        attempts = (
            (json.dumps(body).encode(), "application/json"),
            (urllib.parse.urlencode(body).encode(), "application/x-www-form-urlencoded"),
        )
        last: TastyError | None = None
        for data, ctype in attempts:
            req = urllib.request.Request(
                url, data=data, method="POST",
                headers={"Content-Type": ctype, "Accept": "application/json", "User-Agent": USER_AGENT},
            )
            try:
                with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
                    tok = json.loads(resp.read())
                self._token = tok["access_token"]
                self._token_exp = time.time() + float(tok.get("expires_in", 900)) - 60
                return
            except urllib.error.HTTPError as exc:
                last = TastyError(exc.code, exc.read().decode(errors="replace"), "/oauth/token")
                if exc.code not in (400, 415, 422):
                    break
        raise last  # type: ignore[misc]

    def _headers(self) -> dict[str, str]:
        if not self._token or time.time() >= self._token_exp:
            self._refresh_access_token()
        return {"Authorization": f"Bearer {self._token}", "Accept": "application/json", "User-Agent": USER_AGENT}

    # ---- transport (GET only) -------------------------------------------
    def get(self, path: str, params: dict | None = None):
        url = f"{self.base}{path}"
        if params:
            url += "?" + urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})
        req = urllib.request.Request(url, headers=self._headers(), method="GET")
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
                return json.loads(resp.read() or b"{}")
        except urllib.error.HTTPError as exc:
            raise TastyError(exc.code, exc.read().decode(errors="replace"), path) from None

    # ---- read-only endpoints ----------------------------------------------
    def accounts(self) -> list[dict]:
        d = self.get("/customers/me/accounts")
        return [it.get("account", it) for it in d.get("data", {}).get("items", [])]

    def market_metrics(self, symbols: list[str]) -> dict[str, dict]:
        """symbol -> metrics (implied-volatility-index-rank, -percentile, liquidity-rating, earnings...)."""
        d = self.get("/market-metrics", {"symbols": ",".join(symbols)})
        return {it["symbol"]: it for it in d.get("data", {}).get("items", [])}

    def quotes(self, equities: list[str]) -> dict[str, dict]:
        d = self.get("/market-data/by-type", {"equity": ",".join(equities)})
        return {it["symbol"]: it for it in d.get("data", {}).get("items", [])}

    def option_chain_compact(self, symbol: str) -> dict:
        return self.get(f"/option-chains/{symbol}/compact").get("data", {})


def tasty_available() -> bool:
    """True when both credentials are present in the environment."""
    return bool(os.getenv("TASTY_CLIENT_SECRET") and os.getenv("TASTY_REFRESH_TOKEN"))


def _pct(x) -> float | None:
    """tastytrade returns rank/percentile as 0-1 fractions; normalise to 0-100."""
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return v * 100.0 if v <= 1.0 else v


def iv_metrics(symbols: list[str], client: "TastyREST | None" = None) -> dict[str, dict]:
    """symbol -> {ivr, ivp, iv, chg5d, liq, earnings}. IV rank/percentile on a 0-100 scale.

    ivr  = IV rank: where today's IV index sits between the 1-year low (0) and high (100).
    ivp  = IV percentile: share of the past year's days with IV below today's.
    iv   = IV index (30-day implied vol, as a fraction, e.g. 0.29 = 29%).
    Chunks requests at 50 symbols; skips silently on per-chunk failure.
    """
    client = client or TastyREST()
    out: dict[str, dict] = {}
    for i in range(0, len(symbols), 50):
        chunk = symbols[i:i + 50]
        try:
            raw = client.market_metrics(chunk)
        except TastyError as exc:
            print(f"[warn] market-metrics failed for {len(chunk)} symbols: HTTP {exc.status}")
            continue
        for sym, it in raw.items():
            try:
                iv = float(it.get("implied-volatility-index"))
            except (TypeError, ValueError):
                iv = None
            try:
                chg = float(it.get("implied-volatility-index-5-day-change"))
            except (TypeError, ValueError):
                chg = None
            out[sym] = {
                "ivr": _pct(it.get("implied-volatility-index-rank")),
                "ivp": _pct(it.get("implied-volatility-percentile")),
                "iv": iv,
                "chg5d": chg,
                "liq": it.get("liquidity-rating"),
                "earnings": (it.get("earnings") or {}).get("expected-report-date"),
            }
    return out


def ivr_label(ivr: float | None, cheap_below: float = 30.0, rich_above: float = 50.0) -> str:
    if ivr is None:
        return "n/a"
    if ivr < cheap_below:
        return "CHEAP"
    if ivr >= rich_above:
        return "rich"
    return "ok"


# ---- CLI ------------------------------------------------------------------
def _f(x, fmt="{:.1f}", none="-"):
    try:
        return fmt.format(float(x))
    except (TypeError, ValueError):
        return none


def print_metrics(client: TastyREST, symbols: list[str]) -> None:
    m = client.market_metrics(symbols)
    print(f"{'symbol':<7} {'IV idx':>7} {'IV rank':>8} {'IV pctl':>8} {'5d chg':>7} {'liq':>4}  next earnings")
    for s in symbols:
        it = m.get(s)
        if not it:
            print(f"{s:<7} {'no data':>7}")
            continue
        ivx = it.get("implied-volatility-index")
        rank = it.get("implied-volatility-index-rank")
        pctl = it.get("implied-volatility-percentile")
        chg = it.get("implied-volatility-index-5-day-change")
        liq = it.get("liquidity-rating")
        earn = (it.get("earnings") or {}).get("expected-report-date", "-")
        # rank/percentile come back as 0-1 fractions
        print(f"{s:<7} {_f(ivx, '{:.1%}'):>7} {_f(rank, '{:.0%}'):>8} {_f(pctl, '{:.0%}'):>8} "
              f"{_f(chg, '{:+.1%}'):>7} {str(liq or '-'):>4}  {earn}")


def run_check(symbols: list[str]) -> None:
    """Probe each read-only endpoint and say which ones this account can reach."""
    client = TastyREST()
    print(f"base URL: {client.base}")
    steps = [
        ("token exchange (refresh -> access)", lambda: client._headers() and "ok"),
        ("accounts (read scope)", lambda: f"{len(client.accounts())} account(s)"),
        ("market-metrics (IV rank)", lambda: f"{len(client.market_metrics(symbols))} symbol(s)"),
        ("quotes by-type", lambda: f"{len(client.quotes(symbols))} symbol(s)"),
        (f"option chain compact {symbols[0]}", lambda: f"{len(client.option_chain_compact(symbols[0]).get('items', []))} chain item(s)"),
    ]
    ok_metrics = False
    for name, fn in steps:
        try:
            res = fn()
            print(f"  OK    {name}: {res}")
            ok_metrics = ok_metrics or name.startswith("market-metrics")
        except TastyError as exc:
            print(f"  FAIL  {name}: HTTP {exc.status} {exc.body[:160]}")
        except Exception as exc:  # noqa: BLE001
            print(f"  FAIL  {name}: {type(exc).__name__}: {exc}")
    if ok_metrics:
        print()
        print_metrics(client, symbols)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("symbols", nargs="*", default=["AAPL", "GOOGL", "AVGO"])
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--check", action="store_true", help="probe endpoints and report access")
    g.add_argument("--metrics", action="store_true", help="print IV rank table")
    args = ap.parse_args()
    syms = [s.upper() for s in args.symbols]
    if args.check:
        run_check(syms)
    else:
        print_metrics(TastyREST(), syms)


if __name__ == "__main__":
    main()
