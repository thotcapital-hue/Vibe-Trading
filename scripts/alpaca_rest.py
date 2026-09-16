"""Minimal, dependency-free Alpaca REST client for the board scripts.

The scanner, regime check and board helpers used to import the ``alpaca-py``
SDK. That SDK (and its pydantic/pandas tree) cannot be installed in locked-down
runners that only allow Alpaca's own hosts, so everything the scripts need is
covered here with ``urllib`` from the standard library:

* market data   https://data.alpaca.markets   (stock trades/bars, option chain)
* trading       https://paper-api.alpaca.markets  (account, positions,
                option contracts, orders) -- HARDWIRED TO PAPER.

Responses are returned as plain dicts/lists exactly as Alpaca serialises them.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime

DATA_URL = "https://data.alpaca.markets"
PAPER_URL = "https://paper-api.alpaca.markets"  # never api.alpaca.markets
TIMEOUT = 30


class APIError(Exception):
    """Non-2xx response from Alpaca (status code + body kept for the caller)."""

    def __init__(self, status: int, body: str, url: str):
        self.status, self.body, self.url = status, body, url
        super().__init__(f"HTTP {status} from {url.split('?')[0]}: {body[:300]}")


def _iso(value) -> str:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return str(value)


class AlpacaREST:
    def __init__(self, key: str, secret: str):
        self._headers = {
            "APCA-API-KEY-ID": key,
            "APCA-API-SECRET-KEY": secret,
            "Accept": "application/json",
        }

    # ---- transport --------------------------------------------------------
    def _request(self, method: str, url: str, params: dict | None = None, body: dict | None = None):
        if params:
            clean = {k: _iso(v) for k, v in params.items() if v is not None}
            url = f"{url}?{urllib.parse.urlencode(clean)}"
        data = json.dumps(body).encode() if body is not None else None
        headers = dict(self._headers)
        if data is not None:
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
                raw = resp.read()
        except urllib.error.HTTPError as exc:
            raise APIError(exc.code, exc.read().decode(errors="replace"), url) from None
        return json.loads(raw) if raw else {}

    def _paged(self, url: str, params: dict, key: str, page_limit: int) -> list:
        """Follow ``next_page_token`` and return the concatenated ``key`` payloads."""
        params = dict(params, limit=page_limit)
        pages: list = []
        while True:
            page = self._request("GET", url, params)
            pages.append(page.get(key))
            token = page.get("next_page_token")
            if not token:
                return pages
            params["page_token"] = token

    # ---- market data ------------------------------------------------------
    def latest_trade(self, symbol: str, feed: str = "sip") -> tuple[float, str]:
        """(price, timestamp) of the latest trade."""
        d = self._request("GET", f"{DATA_URL}/v2/stocks/{symbol}/trades/latest", {"feed": feed})
        return float(d["trade"]["p"]), d["trade"]["t"]

    def daily_closes(self, symbols: list[str], start: datetime, feed: str = "sip") -> dict[str, list[float]]:
        """symbol -> ascending list of daily closes since ``start``."""
        params = {"symbols": ",".join(symbols), "timeframe": "1Day", "start": start, "feed": feed, "sort": "asc"}
        closes: dict[str, list[float]] = {}
        for bars in self._paged(f"{DATA_URL}/v2/stocks/bars", params, "bars", 10000):
            for sym, blist in (bars or {}).items():
                closes.setdefault(sym, []).extend(float(b["c"]) for b in blist)
        return closes

    def option_chain(self, underlying: str, exp_gte: date, exp_lte: date, feed: str = "opra") -> dict[str, dict]:
        """OCC symbol -> snapshot (latestQuote, impliedVolatility, greeks, ...)."""
        params = {"feed": feed, "expiration_date_gte": exp_gte, "expiration_date_lte": exp_lte}
        chain: dict[str, dict] = {}
        for snaps in self._paged(f"{DATA_URL}/v1beta1/options/snapshots/{underlying}", params, "snapshots", 1000):
            chain.update(snaps or {})
        return chain

    # ---- trading (paper) --------------------------------------------------
    def account(self) -> dict:
        return self._request("GET", f"{PAPER_URL}/v2/account")

    def positions(self) -> list[dict]:
        return self._request("GET", f"{PAPER_URL}/v2/positions")

    def option_contracts(self, underlying: str, exp_gte: date, exp_lte: date, contract_type: str, **bounds) -> list[dict]:
        """Contract records (symbol, open_interest, ...) for one underlying/type."""
        params = {
            "underlying_symbols": underlying,
            "expiration_date_gte": exp_gte,
            "expiration_date_lte": exp_lte,
            "type": contract_type,
            **bounds,
        }
        out: list[dict] = []
        for page in self._paged(f"{PAPER_URL}/v2/options/contracts", params, "option_contracts", 10000):
            out.extend(page or [])
        return out

    def submit_mleg_limit_order(self, legs: list[dict], qty: int, limit_price: float) -> dict:
        """One multi-leg DAY limit order. Alpaca convention: negative limit = net credit."""
        body = {
            "order_class": "mleg",
            "type": "limit",
            "time_in_force": "day",
            "qty": str(qty),
            "limit_price": str(limit_price),
            "legs": legs,
        }
        return self._request("POST", f"{PAPER_URL}/v2/orders", body=body)
