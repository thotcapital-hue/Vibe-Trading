"""Alpaca loader: key-gated US-equity OHLCV via the Market Data API v2.

Alpaca (https://alpaca.markets) serves split/dividend-adjusted stock bars from
a paginated REST endpoint, gated by an API key pair passed as headers:

  https://data.alpaca.markets/v2/stocks/bars?symbols=AAPL&timeframe=1Day&...

Subscribers on the paid market-data plan get consolidated SIP-feed bars —
higher quality than the free IEX-only feed and the unauthenticated public
sources — so this loader leads the ``us_equity`` fallback chain and quietly
steps aside (``is_available() -> False``) when no key pair is configured.
The feed is selected via ``ALPACA_DATA_FEED`` (``iex`` default; set ``sip``
when subscribed — Alpaca returns 403 for an unsubscribed feed).

Symbol convention (Vibe-Trading -> Alpaca):
  * US ``AAPL.US`` -> ``AAPL`` (Alpaca carries US tickers bare)
  * Anything else is passed through uppercased (e.g. a bare ``MSFT``).

Bars come back as a per-symbol list of objects (``t`` RFC3339 timestamp plus
``o``/``h``/``l``/``c``/``v``) with a ``next_page_token`` cursor; pages are
walked until the cursor is exhausted. No market data is ever persisted in the
repo; settled ranges may be cached to the user-home loader cache via
:func:`cached_loader_fetch`.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

import pandas as pd

from backtest.loaders._http import resolve_min_interval, throttled_get_json
from backtest.loaders.base import cached_loader_fetch, validate_date_range
from backtest.loaders.registry import register

logger = logging.getLogger(__name__)

_API_KEY_ENV = "ALPACA_API_KEY"
_SECRET_KEY_ENV = "ALPACA_SECRET_KEY"
_BARS_URL = "https://data.alpaca.markets/v2/stocks/bars"

# Throttle bucket + default minimum spacing (basic plan is 200 req/min; the
# paid plan is far higher, but one shared bucket keeps the process polite).
_HOST_KEY = "alpaca"
_MIN_INTERVAL_ENV = "VIBE_TRADING_ALPACA_MIN_INTERVAL"
_DEFAULT_MIN_INTERVAL_S = 0.3

# Alpaca serves intraday resolutions too, but the project's us_equity fallback
# chain is daily-only, so anything else falls through to the next source.
_TIMEFRAMES = {"1D": "1Day", "1d": "1Day", "D": "1Day", "day": "1Day"}

_PAGE_LIMIT = 10_000
_MAX_PAGES = 50  # backstop against a runaway pagination loop

_OHLCV_COLUMNS = ["open", "high", "low", "close", "volume"]
_ALPACA_TO_OHLCV = {"o": "open", "h": "high", "l": "low", "c": "close", "v": "volume"}


def _min_interval() -> float:
    """Resolve the per-call minimum spacing, honoring the env override."""
    return resolve_min_interval(_MIN_INTERVAL_ENV, _DEFAULT_MIN_INTERVAL_S)


def _to_alpaca_symbol(code: str) -> str:
    """Translate a project symbol into Alpaca's ticker convention.

    Args:
        code: Project-side symbol, e.g. ``AAPL.US`` or a bare ``MSFT``.

    Returns:
        The Alpaca ticker: the ``.US`` suffix stripped, otherwise the
        uppercased symbol unchanged.
    """
    upper = code.strip().upper()
    if upper.endswith(".US"):
        return upper[: -len(".US")]
    return upper


def _to_rfc3339(date_str: str, *, end_of_day: bool) -> str:
    """Convert a ``YYYY-MM-DD`` date to an RFC3339 UTC bound.

    Args:
        date_str: Inclusive date string.
        end_of_day: When ``True`` push the instant to 23:59:59 so the day's
            bar falls inside Alpaca's inclusive ``[start, end]`` window.

    Returns:
        An RFC3339 timestamp string such as ``2024-01-01T00:00:00Z``.
    """
    ts = pd.Timestamp(date_str).normalize()
    if end_of_day:
        ts = ts + pd.Timedelta(hours=23, minutes=59, seconds=59)
    return ts.strftime("%Y-%m-%dT%H:%M:%SZ")


def _rows_from_bars(bars: Any) -> List[Dict[str, Any]]:
    """Normalize one page of Alpaca bar objects into row dicts.

    Args:
        bars: The per-symbol bar list from the decoded JSON body.

    Returns:
        List of ``{trade_date, open, high, low, close, volume}`` dicts where
        ``trade_date`` is the raw RFC3339 string (normalized to a
        ``datetime64[ns]`` index later in :meth:`DataLoader._fetch_one`).
        Empty when ``bars`` is missing or malformed; bars with a missing OHLC
        slot are skipped.
    """
    if not isinstance(bars, list):
        return []
    rows: List[Dict[str, Any]] = []
    for bar in bars:
        if not isinstance(bar, dict) or not bar.get("t"):
            continue
        values = {field: bar.get(key) for key, field in _ALPACA_TO_OHLCV.items()}
        if any(values[field] is None for field in ("open", "high", "low", "close")):
            continue
        row: Dict[str, Any] = {"trade_date": bar["t"]}
        row.update({field: _to_float(values[field]) for field in _OHLCV_COLUMNS})
        rows.append(row)
    return rows


def _to_float(value: Any) -> Optional[float]:
    """Coerce an Alpaca numeric (or ``None``) to ``float``; ``None`` on failure."""
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


@register
class DataLoader:
    """Alpaca US-equity daily OHLCV loader (key-gated, throttled HTTP)."""

    name = "alpaca"
    markets = {"us_equity"}
    requires_auth = True

    def __init__(self) -> None:
        """Initialize the loader without touching the network or credentials.

        Construction never raises on missing keys; availability is reported
        separately via :meth:`is_available` so the fallback chain can keep
        walking when the key pair is absent.
        """
        pass

    def is_available(self) -> bool:
        """Return whether an Alpaca API key pair is present in the environment."""
        from src.config.accessor import get_env_config

        data = get_env_config().data
        return bool(data.alpaca_api_key and data.alpaca_secret_key)

    def fetch(
        self,
        codes: List[str],
        start_date: str,
        end_date: str,
        *,
        interval: str = "1D",
        fields: Optional[List[str]] = None,
    ) -> Dict[str, pd.DataFrame]:
        """Fetch daily OHLCV history keyed by the original project symbols.

        Each symbol is fetched independently through the opt-in loader cache;
        a single failing symbol is logged and skipped so it never aborts the
        batch.

        Args:
            codes: Project symbols such as ``AAPL.US``.
            start_date: Inclusive start date in ``YYYY-MM-DD`` format.
            end_date: Inclusive end date in ``YYYY-MM-DD`` format.
            interval: Backtest interval; only daily (``1D``) is supported —
                other intervals return ``{}`` so the chain can fall through.
            fields: Ignored; included for interface compatibility.

        Returns:
            Mapping of input symbol to a DataFrame indexed by a ``trade_date``
            :class:`~pandas.DatetimeIndex` with float ``open``/``high``/``low``/
            ``close``/``volume`` columns. Symbols without data are omitted.

        Raises:
            ValueError: If ``start_date`` > ``end_date``.
        """
        del fields
        validate_date_range(start_date, end_date)

        timeframe = _TIMEFRAMES.get(interval)
        if timeframe is None:
            logger.warning("alpaca fetch skipped: unsupported interval %r", interval)
            return {}

        from src.config.accessor import get_env_config

        data = get_env_config().data
        if not (data.alpaca_api_key and data.alpaca_secret_key):
            logger.warning(
                "alpaca fetch skipped: %s/%s not set", _API_KEY_ENV, _SECRET_KEY_ENV
            )
            return {}
        headers = {
            "APCA-API-KEY-ID": data.alpaca_api_key,
            "APCA-API-SECRET-KEY": data.alpaca_secret_key,
        }
        feed = (data.alpaca_data_feed or "iex").strip().lower()

        result: Dict[str, pd.DataFrame] = {}
        for code in codes:
            try:
                df = cached_loader_fetch(
                    source=self.name,
                    symbol=code,
                    timeframe=interval,
                    start_date=start_date,
                    end_date=end_date,
                    fields=None,
                    fetch=lambda code=code: self._fetch_one(
                        code, start_date, end_date, timeframe, feed, headers
                    ),
                )
                if df is not None and not df.empty:
                    result[code] = df
            except Exception as exc:  # noqa: BLE001 - one symbol must not abort the batch
                logger.warning("alpaca failed for %s: %s", code, exc)
        return result

    def _fetch_one(
        self,
        code: str,
        start_date: str,
        end_date: str,
        timeframe: str,
        feed: str,
        headers: Dict[str, str],
    ) -> Optional[pd.DataFrame]:
        """Fetch and normalize one symbol's daily bars, walking pagination.

        Args:
            code: Project-side symbol.
            start_date: Inclusive start date (``YYYY-MM-DD``).
            end_date: Inclusive end date (``YYYY-MM-DD``).
            timeframe: Alpaca timeframe string (e.g. ``1Day``).
            feed: Alpaca data feed (``iex`` or ``sip``).
            headers: Auth headers with the key pair.

        Returns:
            A normalized OHLCV DataFrame, or ``None`` when Alpaca reports no
            usable data for the window.
        """
        symbol = _to_alpaca_symbol(code)
        params: Dict[str, Any] = {
            "symbols": symbol,
            "timeframe": timeframe,
            "start": _to_rfc3339(start_date, end_of_day=False),
            "end": _to_rfc3339(end_date, end_of_day=True),
            "adjustment": "all",
            "feed": feed,
            "limit": _PAGE_LIMIT,
            "sort": "asc",
        }

        rows: List[Dict[str, Any]] = []
        for _ in range(_MAX_PAGES):
            payload = throttled_get_json(
                _BARS_URL,
                host_key=_HOST_KEY,
                min_interval=_min_interval(),
                params=params,
                headers=headers,
            )
            if not isinstance(payload, dict):
                break
            bars_by_symbol = payload.get("bars") or {}
            rows.extend(_rows_from_bars(bars_by_symbol.get(symbol)))
            token = payload.get("next_page_token")
            if not token:
                break
            params["page_token"] = token
        else:
            logger.warning("alpaca pagination for %s exceeded %d pages", code, _MAX_PAGES)

        if not rows:
            return None

        df = pd.DataFrame(rows)
        # RFC3339 timestamps -> tz-naive nanosecond DatetimeIndex normalized to
        # the trading date, so the index dtype (``datetime64[ns]``) and daily
        # granularity stay consistent with the other loaders.
        df["trade_date"] = (
            pd.to_datetime(df["trade_date"], utc=True)
            .dt.tz_convert("America/New_York")
            .dt.tz_localize(None)
            .dt.normalize()
            .astype("datetime64[ns]")
        )
        df = df.set_index("trade_date").sort_index()
        df = df[~df.index.duplicated(keep="last")]
        df = df[_OHLCV_COLUMNS].astype(float).dropna(
            subset=["open", "high", "low", "close"]
        )
        return df
