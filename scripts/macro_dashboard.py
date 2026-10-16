#!/usr/bin/env python3
"""Daily macro dashboard: the gauges behind the macro read, and what moved in 7 days.

Built for the question "what changed?" rather than "what is the level?".
Every row prints today's value, the value ~7 calendar days ago, the change,
and a signal word from fixed thresholds so the read is repeatable.

Five panels (all read-only, all free):
  RATES      Treasury.gov nominal + real curves -> 3m, 2y, 10y, 30y, 2s10s,
             10y real, 10y breakeven (nominal - real). FRED HY spread if reachable.
  INFLATION  USO (oil), GLD, CPER (copper), UUP (dollar), TIP/IEF ratio.
  GROWTH     XLY/XLP (cyclicals vs defensives), IWM/SPY, HYG/LQD (credit),
             SMH/SPY (semis leadership), XLU/SPY (bond-proxy stress).
  BREADTH    RSP/SPY 20d, % of board above 50/200-DMA, sectors above 50-DMA,
             SPY / QQQ vs 21-DMA.
  VOL        VIX, VIX3M, VIX9D (CBOE, ~1-day lag), term-structure ratio,
             SKEW, SPY 30d ATM IV vs 20d realised (variance risk premium),
             tastytrade IV rank for SPY/QQQ/TLT and the board average.

Appends every value to macro/dashboard.csv (long format) so the 7-day
comparison works from our own history even when a source is down.

Usage:  python scripts/macro_dashboard.py            # print + append
        python scripts/macro_dashboard.py --no-save  # print only
"""

from __future__ import annotations

import argparse
import csv
import io
import math
import urllib.request
import zipfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from alpaca_rest import AlpacaREST
from board import CALL_SIDE_WATCH, CLUSTERS, parse_occ
from spread_scan import load_keys
from tasty_rest import iv_metrics, tasty_available

ROOT = Path(__file__).resolve().parent.parent
CSV_PATH = ROOT / "macro" / "dashboard.csv"
UA = {"User-Agent": "vibe-trading-board/1.0"}
TREASURY = ("https://home.treasury.gov/resource-center/data-chart-center/interest-rates/"
            "daily-treasury-rates.csv/{y}/all?type={t}&field_tdr_date_value={y}&page&_format=csv")
CBOE = "https://cdn.cboe.com/api/global/us_indices/daily_prices/{s}_History.csv"
FRED = "https://fred.stlouisfed.org/graph/fredgraph.csv?id={s}"
SECTORS = ["XLK", "XLF", "XLV", "XLP", "XLE", "XLI", "XLY", "XLU", "XLB", "XLRE", "XLC"]
ETFS = ["SPY", "QQQ", "IWM", "RSP", "XLY", "XLP", "XLU", "SMH", "HYG", "LQD", "TLT", "IEF", "SHY",
        "TIP", "GLD", "USO", "CPER", "UUP"] + SECTORS


# ---- fetch helpers ----------------------------------------------------------
def _get(url: str, timeout: int = 40) -> bytes:
    return urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout).read()


def _csv_rows(raw: bytes) -> list[list[str]]:
    if raw[:2] == b"PK":  # FRED sometimes ships a zip
        z = zipfile.ZipFile(io.BytesIO(raw))
        name = next((n for n in z.namelist() if n.endswith(".csv")), z.namelist()[0])
        raw = z.read(name)
    return list(csv.reader(io.StringIO(raw.decode(errors="replace"))))


def _num(x) -> float | None:
    try:
        return float(str(x).replace(",", ""))
    except (TypeError, ValueError):
        return None


def treasury_curve(kind: str) -> dict[date, dict[str, float]]:
    """kind: 'daily_treasury_yield_curve' | 'daily_treasury_real_yield_curve'. date -> {tenor: yield}."""
    out: dict[date, dict[str, float]] = {}
    for y in (date.today().year, date.today().year - 1):
        try:
            rows = _csv_rows(_get(TREASURY.format(y=y, t=kind)))
        except Exception as exc:  # noqa: BLE001
            print(f"[warn] treasury {kind} {y}: {exc}")
            continue
        if not rows:
            continue
        hdr = [h.strip().lower() for h in rows[0]]
        for r in rows[1:]:
            if not r or not r[0].strip():
                continue
            try:
                d = datetime.strptime(r[0].strip(), "%m/%d/%Y").date()
            except ValueError:
                continue
            out[d] = {hdr[i]: v for i, c in enumerate(r[1:], start=1) if (v := _num(c)) is not None}
    return out


def cboe_series(sym: str) -> dict[date, float]:
    try:
        rows = _csv_rows(_get(CBOE.format(s=sym)))
    except Exception as exc:  # noqa: BLE001
        print(f"[warn] cboe {sym}: {exc}")
        return {}
    out: dict[date, float] = {}
    for r in rows[1:]:
        try:
            out[datetime.strptime(r[0], "%m/%d/%Y").date()] = float(r[-1])
        except (ValueError, IndexError):
            continue
    return out


def fred_series(sym: str) -> dict[date, float]:
    try:
        rows = _csv_rows(_get(FRED.format(s=sym), timeout=25))
    except Exception as exc:  # noqa: BLE001
        print(f"[warn] fred {sym}: {type(exc).__name__}")
        return {}
    out: dict[date, float] = {}
    for r in rows[1:]:
        if len(r) >= 2 and (v := _num(r[1])) is not None:
            try:
                out[date.fromisoformat(r[0])] = v
            except ValueError:
                continue
    return out


# ---- series utilities ---------------------------------------------------------
def at(series: dict[date, float], d: date, back: int = 6) -> float | None:
    """Value on d or the nearest earlier date within `back` days."""
    for i in range(back + 1):
        v = series.get(d - timedelta(days=i))
        if v is not None:
            return v
    return None


def tenor(curve: dict[date, dict[str, float]], key: str) -> dict[date, float]:
    key = key.lower()
    return {d: row[k] for d, row in curve.items() for k in row if k == key}


def sma(x: list[float], n: int) -> float | None:
    return sum(x[-n:]) / n if len(x) >= n else None


def realised_vol(px: list[float], n: int = 20) -> float | None:
    if len(px) < n + 1:
        return None
    r = [math.log(px[i] / px[i - 1]) for i in range(len(px) - n, len(px))]
    m = sum(r) / n
    return math.sqrt(sum((x - m) ** 2 for x in r) / (n - 1)) * math.sqrt(252)


def spy_atm_iv(client: AlpacaREST, spot: float, today: date) -> float | None:
    """30-day-ish ATM implied vol from the Alpaca SPY chain (nearest expiry to 30 DTE)."""
    try:
        chain = client.option_chain("SPY", today + timedelta(days=25), today + timedelta(days=38), "opra")
    except Exception:  # noqa: BLE001
        return None
    best: tuple[float, float] | None = None  # (strike distance, iv)
    for occ, snap in chain.items():
        _, _exp, _cp, k = parse_occ(occ)
        iv = snap.get("impliedVolatility")
        if iv and (best is None or abs(k - spot) < best[0]):
            best = (abs(k - spot), float(iv))
    return best[1] if best else None


# ---- history (our own csv) ------------------------------------------------
def load_history() -> dict[str, dict[date, float]]:
    hist: dict[str, dict[date, float]] = {}
    if CSV_PATH.exists():
        with CSV_PATH.open() as f:
            for row in csv.DictReader(f):
                try:
                    hist.setdefault(row["metric"], {})[date.fromisoformat(row["date"])] = float(row["value"])
                except (KeyError, ValueError):
                    continue
    return hist


def save_rows(today: date, values: dict[str, float | None]) -> None:
    CSV_PATH.parent.mkdir(parents=True, exist_ok=True)
    new = not CSV_PATH.exists()
    existing = load_history()
    with CSV_PATH.open("a", newline="") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["date", "metric", "value"])
        for k, v in values.items():
            if v is not None and today not in existing.get(k, {}):
                w.writerow([today.isoformat(), k, f"{v:.6g}"])


# ---- signal rules -----------------------------------------------------------
def signal(metric: str, now: float | None, prev: float | None) -> str:
    if now is None:
        return ""
    chg = None if prev is None else now - prev
    r = {
        "10y yield %": lambda: "STRESS >5.5" if now > 5.5 else ("high >5.0" if now > 5.0 else "relief <5.0"),
        "2s10s bp": lambda: "steepening" if chg is not None and chg > 10 else ("flattening" if chg is not None and chg < -10 else ""),
        "10y real %": lambda: "tight >2.5" if now > 2.5 else "",
        "HY OAS bp": lambda: "CREDIT STRESS" if chg is not None and chg > 50 else ("widening" if chg is not None and chg > 20 else ""),
        "WTI proxy USO": lambda: "oil shock +10%" if prev and now / prev - 1 > 0.10 else ("oil relief -10%" if prev and now / prev - 1 < -0.10 else ""),
        "RSP/SPY 20d %": lambda: "NARROW <-3" if now < -3 else ("broadening >1" if now > 1 else ""),
        "board >50DMA %": lambda: "weak <40" if now < 40 else ("healthy >60" if now > 60 else ""),
        "sectors >50DMA": lambda: "weak <5" if now < 5 else ("healthy >7" if now > 7 else ""),
        "HYG/LQD 10d %": lambda: "RISK-OFF <-2" if now < -2 else ("risk-on >1" if now > 1 else ""),
        "XLY/XLP 20d %": lambda: "defensive <-3" if now < -3 else ("cyclical >3" if now > 3 else ""),
        "VIX": lambda: "FEAR >25" if now > 25 else ("elevated >20" if now > 20 else ("complacent <14" if now < 14 else "")),
        "VIX/VIX3M": lambda: "INVERTED >1" if now > 1.0 else ("flat >0.95" if now > 0.95 else "normal"),
        "SPY IV-RV pts": lambda: "sell premium >6" if now > 6 else ("BUY vol <0" if now < 0 else ""),
        "QQQ IVR": lambda: "cheap <20" if now < 20 else ("rich >50" if now > 50 else ""),
        "board avg IVR": lambda: "cheap <30" if now < 30 else ("rich >50" if now > 50 else ""),
        "SPY vs 21DMA %": lambda: "below" if now < 0 else "",
        "QQQ vs 21DMA %": lambda: "below" if now < 0 else "",
    }.get(metric)
    return r() if r else ""


# ---- main -------------------------------------------------------------------
def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--no-save", action="store_true")
    args = ap.parse_args()
    today = datetime.now(timezone.utc).date()
    week_ago = today - timedelta(days=7)
    client = AlpacaREST(*load_keys())

    # -- prices
    board = sorted({s for v in CLUSTERS.values() for s in v} | {s for v in CALL_SIDE_WATCH.values() for s in v})
    syms = sorted(set(ETFS) | set(board))
    px = client.daily_closes(syms, datetime.now(timezone.utc) - timedelta(days=330), "sip")

    def last(s: str, back: int = 0) -> float | None:
        x = px.get(s)
        return x[-1 - back] if x and len(x) > back else None

    def ratio_chg(a: str, b: str, n: int) -> tuple[float | None, float | None]:
        xa, xb = px.get(a), px.get(b)
        if not xa or not xb or len(xa) <= n + 5 or len(xb) <= n + 5:
            return None, None
        now = (xa[-1] / xb[-1]) / (xa[-1 - n] / xb[-1 - n]) - 1
        prev = (xa[-6] / xb[-6]) / (xa[-6 - n] / xb[-6 - n]) - 1
        return now * 100, prev * 100

    def pct_above(n: int, universe: list[str], back: int = 0) -> float | None:
        ok = tot = 0
        for s in universe:
            x = px.get(s)
            if not x or len(x) < n + back + 1:
                continue
            xs = x[: len(x) - back] if back else x
            m = sma(xs, n)
            if m:
                tot += 1
                ok += xs[-1] > m
        return 100 * ok / tot if tot else None

    def vs_ma(s: str, n: int, back: int = 0) -> float | None:
        x = px.get(s)
        if not x or len(x) < n + back + 1:
            return None
        xs = x[: len(x) - back] if back else x
        m = sma(xs, n)
        return (xs[-1] / m - 1) * 100 if m else None

    # -- rates (Treasury.gov)
    nom = treasury_curve("daily_treasury_yield_curve")
    real = treasury_curve("daily_treasury_real_yield_curve")
    y3m, y2, y10, y30 = tenor(nom, "3 mo"), tenor(nom, "2 yr"), tenor(nom, "10 yr"), tenor(nom, "30 yr")
    r10 = tenor(real, "10 yr")
    hy = fred_series("BAMLH0A0HYM2")

    def pair(series: dict[date, float]) -> tuple[float | None, float | None]:
        return at(series, today), at(series, week_ago)

    def diff(a: dict[date, float], b: dict[date, float], scale: float = 1.0) -> tuple[float | None, float | None]:
        a1, a0 = pair(a)
        b1, b0 = pair(b)
        return ((a1 - b1) * scale if a1 is not None and b1 is not None else None,
                (a0 - b0) * scale if a0 is not None and b0 is not None else None)

    # -- vol (CBOE)
    vix, vix3m, vix9d, skew = cboe_series("VIX"), cboe_series("VIX3M"), cboe_series("VIX9D"), cboe_series("SKEW")
    spy_spot = last("SPY")
    iv = spy_atm_iv(client, spy_spot, today) if spy_spot else None
    rv = realised_vol(px["SPY"]) if "SPY" in px else None
    rv_prev = realised_vol(px["SPY"][:-5]) if "SPY" in px else None

    # -- tastytrade IV rank
    ivm = iv_metrics(sorted(set(board) | {"SPY", "QQQ", "TLT"})) if tasty_available() else {}
    def ivr(s: str) -> float | None:
        return (ivm.get(s) or {}).get("ivr")
    board_ivr = [v["ivr"] for s, v in ivm.items() if s in board and v.get("ivr") is not None]

    hist = load_history()
    def h(metric: str) -> float | None:
        return at(hist.get(metric, {}), week_ago, back=3)

    # -- assemble rows: (panel, metric, now, prev, fmt)
    rows: list[tuple[str, str, float | None, float | None, str]] = []
    def add(panel, metric, now, prev, fmt="{:.2f}"):
        if prev is None:
            prev = h(metric)
        rows.append((panel, metric, now, prev, fmt))

    add("RATES", "3m bill %", *pair(y3m))
    add("RATES", "2y yield %", *pair(y2))
    add("RATES", "10y yield %", *pair(y10))
    add("RATES", "30y yield %", *pair(y30))
    add("RATES", "2s10s bp", *diff(y10, y2, 100), "{:.0f}")
    add("RATES", "10y real %", *pair(r10))
    add("RATES", "10y breakeven %", *diff(y10, r10))
    add("RATES", "HY OAS bp", *(tuple(v * 100 if v is not None else None for v in pair(hy))), "{:.0f}")
    add("RATES", "TLT", last("TLT"), last("TLT", 5))

    add("INFLATION", "WTI proxy USO", last("USO"), last("USO", 5))
    add("INFLATION", "GLD", last("GLD"), last("GLD", 5))
    add("INFLATION", "copper CPER", last("CPER"), last("CPER", 5))
    add("INFLATION", "dollar UUP", last("UUP"), last("UUP", 5))
    add("INFLATION", "TIP/IEF 20d %", *ratio_chg("TIP", "IEF", 20))

    add("GROWTH", "XLY/XLP 20d %", *ratio_chg("XLY", "XLP", 20))
    add("GROWTH", "IWM/SPY 20d %", *ratio_chg("IWM", "SPY", 20))
    add("GROWTH", "HYG/LQD 10d %", *ratio_chg("HYG", "LQD", 10))
    add("GROWTH", "SMH/SPY 20d %", *ratio_chg("SMH", "SPY", 20))
    add("GROWTH", "XLU/SPY 20d %", *ratio_chg("XLU", "SPY", 20))

    add("BREADTH", "RSP/SPY 20d %", *ratio_chg("RSP", "SPY", 20))
    add("BREADTH", "board >50DMA %", pct_above(50, board), pct_above(50, board, 5), "{:.0f}")
    add("BREADTH", "board >200DMA %", pct_above(200, board), pct_above(200, board, 5), "{:.0f}")
    add("BREADTH", "sectors >50DMA", (pct_above(50, SECTORS) or 0) * 11 / 100, (pct_above(50, SECTORS, 5) or 0) * 11 / 100, "{:.0f}")
    add("BREADTH", "SPY vs 21DMA %", vs_ma("SPY", 21), vs_ma("SPY", 21, 5))
    add("BREADTH", "QQQ vs 21DMA %", vs_ma("QQQ", 21), vs_ma("QQQ", 21, 5))

    add("VOL", "VIX", *pair(vix))
    add("VOL", "VIX3M", *pair(vix3m))
    add("VOL", "VIX9D", *pair(vix9d))
    v1, v0 = pair(vix)
    m1, m0 = pair(vix3m)
    add("VOL", "VIX/VIX3M", v1 / m1 if v1 and m1 else None, v0 / m0 if v0 and m0 else None, "{:.3f}")
    add("VOL", "SKEW", *pair(skew), "{:.1f}")
    add("VOL", "SPY 30d IV %", iv * 100 if iv else None, None)
    add("VOL", "SPY 20d RV %", rv * 100 if rv else None, rv_prev * 100 if rv_prev else None)
    add("VOL", "SPY IV-RV pts", (iv - rv) * 100 if iv and rv else None, None)
    add("VOL", "SPY IVR", ivr("SPY"), None, "{:.0f}")
    add("VOL", "QQQ IVR", ivr("QQQ"), None, "{:.0f}")
    add("VOL", "TLT IVR", ivr("TLT"), None, "{:.0f}")
    add("VOL", "board avg IVR", sum(board_ivr) / len(board_ivr) if board_ivr else None, None, "{:.0f}")

    # -- print
    print(f"MACRO DASHBOARD  {today}   (prev = ~7 days earlier; sources: Treasury.gov, CBOE, FRED, Alpaca, tastytrade)")
    print(f"{'panel':<9} {'metric':<18} {'now':>9} {'7d ago':>9} {'change':>9}  signal")
    panel_prev = None
    for panel, metric, now, prev, fmt in rows:
        if panel != panel_prev:
            print("-" * 72)
            panel_prev = panel
        n = fmt.format(now) if now is not None else "n/a"
        p = fmt.format(prev) if prev is not None else "n/a"
        c = ("+" if now - prev >= 0 else "") + fmt.format(now - prev) if now is not None and prev is not None else ""
        print(f"{panel:<9} {metric:<18} {n:>9} {p:>9} {c:>9}  {signal(metric, now, prev)}")

    # -- composite read
    flags = [f"{m}: {signal(m, n, p)}" for _, m, n, p, _ in rows if signal(m, n, p) and any(
        w in signal(m, n, p) for w in ("STRESS", "INVERTED", "RISK-OFF", "NARROW", "FEAR", "shock", "relief", "BUY vol", "sell premium"))]
    print("\nflags:", "; ".join(flags) if flags else "none")

    if not args.no_save:
        save_rows(today, {m: n for _, m, n, _, _ in rows})
        print(f"saved -> {CSV_PATH.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
