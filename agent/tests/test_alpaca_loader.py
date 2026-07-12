"""Tests for alpaca_loader: symbol mapping, payload parsing, auth gating, pagination.

All HTTP is mocked — no test ever reaches a live Alpaca endpoint. The loader
imports ``throttled_get_json`` from :mod:`backtest.loaders._http` into its own
namespace, so we monkeypatch that name on the ``alpaca_loader`` module.
"""

from __future__ import annotations

from typing import Any, Dict, List

import pandas as pd

from backtest.loaders import alpaca_loader
from backtest.loaders.alpaca_loader import (
    DataLoader,
    _to_alpaca_symbol,
    _to_rfc3339,
)
from backtest.loaders.registry import (
    FALLBACK_CHAINS,
    LOADER_REGISTRY,
    VALID_SOURCES,
    _ensure_registered,
)


def _bar(t: str, o: float, h: float, low: float, c: float, v: float) -> Dict[str, Any]:
    return {"t": t, "o": o, "h": h, "l": low, "c": c, "v": v}


def _ok_payload() -> Dict[str, Any]:
    """Two ascending daily bars in Alpaca's multi-symbol layout."""
    return {
        "bars": {
            "AAPL": [
                _bar("2024-01-02T05:00:00Z", 10.0, 12.0, 9.0, 11.5, 1000),
                _bar("2024-01-03T05:00:00Z", 11.0, 13.0, 10.5, 12.5, 2000),
            ]
        },
        "next_page_token": None,
    }


def _set_keys(monkeypatch) -> None:
    monkeypatch.setenv("ALPACA_API_KEY", "test-key")
    monkeypatch.setenv("ALPACA_SECRET_KEY", "test-secret")


# ---------------------------------------------------------------------------
# Symbol mapping / date bounds
# ---------------------------------------------------------------------------


class TestToAlpacaSymbol:
    """Vibe-Trading -> Alpaca ticker translation."""

    def test_us_suffix_stripped(self):
        assert _to_alpaca_symbol("AAPL.US") == "AAPL"
        assert _to_alpaca_symbol("aapl.us") == "AAPL"

    def test_bare_ticker_uppercased(self):
        assert _to_alpaca_symbol("msft") == "MSFT"
        assert _to_alpaca_symbol(" nvda ") == "NVDA"


class TestToRfc3339:
    """Inclusive date -> RFC3339 UTC bound."""

    def test_start_is_midnight(self):
        assert _to_rfc3339("2024-01-01", end_of_day=False) == "2024-01-01T00:00:00Z"

    def test_end_pushes_to_end_of_day(self):
        assert _to_rfc3339("2024-01-01", end_of_day=True) == "2024-01-01T23:59:59Z"


# ---------------------------------------------------------------------------
# Registry wiring
# ---------------------------------------------------------------------------


class TestRegistryWiring:
    """Alpaca is registered, valid, and leads the us_equity chain."""

    def test_registered_and_valid(self):
        _ensure_registered()
        assert "alpaca" in LOADER_REGISTRY
        assert "alpaca" in VALID_SOURCES

    def test_leads_us_equity_chain(self):
        assert FALLBACK_CHAINS["us_equity"][0] == "alpaca"


# ---------------------------------------------------------------------------
# Availability / auth gating
# ---------------------------------------------------------------------------


class TestAvailability:
    """is_available reflects only the env key pair; __init__ never raises."""

    def test_construct_without_keys_does_not_raise(self, monkeypatch):
        monkeypatch.delenv("ALPACA_API_KEY", raising=False)
        monkeypatch.delenv("ALPACA_SECRET_KEY", raising=False)
        loader = DataLoader()  # must not raise
        assert loader.is_available() is False

    def test_key_without_secret_is_unavailable(self, monkeypatch):
        monkeypatch.setenv("ALPACA_API_KEY", "test-key")
        monkeypatch.delenv("ALPACA_SECRET_KEY", raising=False)
        assert DataLoader().is_available() is False

    def test_key_pair_makes_available(self, monkeypatch):
        _set_keys(monkeypatch)
        assert DataLoader().is_available() is True

    def test_fetch_without_keys_returns_empty(self, monkeypatch):
        monkeypatch.delenv("ALPACA_API_KEY", raising=False)
        monkeypatch.delenv("ALPACA_SECRET_KEY", raising=False)
        called: List[str] = []
        monkeypatch.setattr(
            alpaca_loader,
            "throttled_get_json",
            lambda *a, **k: called.append("hit"),
        )
        assert DataLoader().fetch(["AAPL.US"], "2024-01-01", "2024-01-31") == {}
        assert called == []


# ---------------------------------------------------------------------------
# Fetch / normalization
# ---------------------------------------------------------------------------


class TestFetch:
    """Payload normalization, feed/adjustment params, and error isolation."""

    def test_fetch_normalizes_frame(self, monkeypatch):
        _set_keys(monkeypatch)
        seen: List[Dict[str, Any]] = []

        def fake_get_json(url: str, **kwargs: Any) -> Dict[str, Any]:
            seen.append({"url": url, **kwargs})
            return _ok_payload()

        monkeypatch.setattr(alpaca_loader, "throttled_get_json", fake_get_json)
        result = DataLoader().fetch(["AAPL.US"], "2024-01-02", "2024-01-03")

        assert set(result) == {"AAPL.US"}
        df = result["AAPL.US"]
        assert list(df.columns) == ["open", "high", "low", "close", "volume"]
        assert isinstance(df.index, pd.DatetimeIndex)
        assert str(df.index.dtype) == "datetime64[ns]"
        # 05:00 UTC on 2024-01-02 is midnight ET on the trading date itself.
        assert df.index[0] == pd.Timestamp("2024-01-02")
        assert df.index.is_monotonic_increasing
        assert df.loc[pd.Timestamp("2024-01-03"), "close"] == 12.5

        params = seen[0]["params"]
        assert params["symbols"] == "AAPL"
        assert params["timeframe"] == "1Day"
        assert params["adjustment"] == "all"
        assert params["feed"] == "iex"  # default when ALPACA_DATA_FEED unset
        headers = seen[0]["headers"]
        assert headers["APCA-API-KEY-ID"] == "test-key"
        assert headers["APCA-API-SECRET-KEY"] == "test-secret"

    def test_feed_env_override(self, monkeypatch):
        _set_keys(monkeypatch)
        monkeypatch.setenv("ALPACA_DATA_FEED", "SIP")
        seen: List[Dict[str, Any]] = []

        def fake_get_json(url: str, **kwargs: Any) -> Dict[str, Any]:
            seen.append(kwargs)
            return _ok_payload()

        monkeypatch.setattr(alpaca_loader, "throttled_get_json", fake_get_json)
        DataLoader().fetch(["AAPL"], "2024-01-02", "2024-01-03")
        assert seen[0]["params"]["feed"] == "sip"

    def test_pagination_walks_next_page_token(self, monkeypatch):
        _set_keys(monkeypatch)
        pages = [
            {
                "bars": {"AAPL": [_bar("2024-01-02T05:00:00Z", 10, 12, 9, 11.5, 1000)]},
                "next_page_token": "tok-1",
            },
            {
                "bars": {"AAPL": [_bar("2024-01-03T05:00:00Z", 11, 13, 10.5, 12.5, 2000)]},
                "next_page_token": None,
            },
        ]
        calls: List[Dict[str, Any]] = []

        def fake_get_json(url: str, **kwargs: Any) -> Dict[str, Any]:
            calls.append(dict(kwargs["params"]))
            return pages[len(calls) - 1]

        monkeypatch.setattr(alpaca_loader, "throttled_get_json", fake_get_json)
        result = DataLoader().fetch(["AAPL"], "2024-01-02", "2024-01-03")

        assert len(calls) == 2
        assert "page_token" not in calls[0]
        assert calls[1]["page_token"] == "tok-1"
        assert len(result["AAPL"]) == 2

    def test_empty_bars_omits_symbol(self, monkeypatch):
        _set_keys(monkeypatch)
        monkeypatch.setattr(
            alpaca_loader,
            "throttled_get_json",
            lambda *a, **k: {"bars": {}, "next_page_token": None},
        )
        assert DataLoader().fetch(["ZZZQ"], "2024-01-02", "2024-01-03") == {}

    def test_one_failing_symbol_does_not_abort_batch(self, monkeypatch):
        _set_keys(monkeypatch)

        def fake_get_json(url: str, **kwargs: Any) -> Dict[str, Any]:
            if kwargs["params"]["symbols"] == "BAD":
                raise RuntimeError("boom")
            return _ok_payload()

        monkeypatch.setattr(alpaca_loader, "throttled_get_json", fake_get_json)
        result = DataLoader().fetch(["BAD", "AAPL.US"], "2024-01-02", "2024-01-03")
        assert set(result) == {"AAPL.US"}

    def test_unsupported_interval_returns_empty(self, monkeypatch):
        _set_keys(monkeypatch)
        called: List[str] = []
        monkeypatch.setattr(
            alpaca_loader,
            "throttled_get_json",
            lambda *a, **k: called.append("hit"),
        )
        assert DataLoader().fetch(["AAPL"], "2024-01-02", "2024-01-03", interval="5m") == {}
        assert called == []

    def test_malformed_bar_rows_skipped(self, monkeypatch):
        _set_keys(monkeypatch)
        payload = {
            "bars": {
                "AAPL": [
                    _bar("2024-01-02T05:00:00Z", 10, 12, 9, 11.5, 1000),
                    {"t": "2024-01-03T05:00:00Z", "o": None, "h": 1, "l": 1, "c": 1},
                    {"no_timestamp": True},
                ]
            },
            "next_page_token": None,
        }
        monkeypatch.setattr(alpaca_loader, "throttled_get_json", lambda *a, **k: payload)
        result = DataLoader().fetch(["AAPL"], "2024-01-02", "2024-01-03")
        assert len(result["AAPL"]) == 1
