# Sectors when the 10-year is over 5% and the 3-month bill over 4% (2026-09-25)

Script: `scripts/rate_regime_sectors.py`. Data: Fama-French 12 value-weighted industry
portfolios (monthly, 1960-2026), FRED GS10 / TB3MS / CPIAUCSL; SPDR sector ETFs from
Yahoo for the 1999-2026 check (scratch run, numbers below). "Excess" = annualised
industry return minus the equal-weight average of the 12 industries.

## 1. The level alone is not a regime

10y >= 5% and 3m >= 4% describes 372 of 799 months since 1960; 1972-1992 is one
unbroken 234-month stretch. Adding CPI y/y >= 3% (today 3.4%) splits it into seven
episodes of 6+ months: 1967-71, 1971, 1972-83, 1983-86, 1987-91, 1996-97, 2000-01.
2006-07 and Oct-2023 miss the cut (the 10y averaged >= 5% for only two months).

## 2. During the episodes (with CPI >= 3%), average excess return per year and hit rate

| industry (ETF) | during | hit | 12m after | hit |
|---|---|---|---|---|
| Energy (XLE) | +9.5% | 71% | -6.4% | 29% |
| Financials (XLF) | +9.0% | 57% | +9.4% | 57% |
| Utilities (XLU) | +8.6% | 86% | +1.5% | 57% |
| Health (XLV) | +3.7% | 57% | -2.8% | 43% |
| Materials (XLB) | +2.3% | 71% | +2.6% | 57% |
| Staples (XLP) | +1.3% | 57% | +0.9% | 43% |
| Industrials (XLI) | 0.0% | 29% | +1.0% | 57% |
| Durables/autos | -2.3% | 43% | +3.6% | 71% |
| Retail (XLY) | -4.3% | 14% | +1.2% | 57% |
| Other | -5.8% | 14% | -1.2% | 43% |
| Telecom (XLC) | -7.6% | 71% | -4.2% | 57% |
| Tech (XLK) | -13.5% | 14% | -4.5% | 43% |

Market itself: 11.9%/yr during the episodes, +11.3%/yr in the 12 months after (range
-15% after 1983 to +25% after 1991). The "after" column is noisy: the 12-month winners
flipped from episode to episode (utilities and staples after 1983; financials after
1991; retail and financials after 2001).

## 3. Direction beats level

Regime months split by whether the 10y was more than 25 bp above its level six months
earlier (rates still rising) or below (rates falling):

| | rising 10y (131 mo) | falling 10y (88 mo) |
|---|---|---|
| market, annualised | -4.5% | +51.2% |
| Energy | +9.2% | -27.9% |
| Utilities | +4.4% | -12.1% |
| Telecom | +2.4% | -1.5% |
| Health | +1.8% | +14.9% |
| Materials | +1.0% | +0.3% |
| Financials | -3.1% | +4.1% |
| Tech | -3.4% | +1.4% |
| Retail | -4.3% | +3.8% |
| Durables | -7.0% | +5.3% |

The same split on SPDR ETFs 1999-2026 (10y >= 4, 3m >= 3 as the modern equivalent, 97
months): rising-10y months: SPY +13%, XLK +27%, GLD +19%, XLV +12%, XLF +10%, XLE +11%,
XLU -7%; falling-10y months: SPY -8%, XLK -35%, XLE +23%, XLU +21%, GLD +49%, TLT -13%.
The modern "falling" months are mostly 2000-01 and 2007, i.e. rates fell because a
recession arrived; the long sample's falling months are dominated by the 1982-86
disinflation. Which one "after" looks like depends on why rates fall.

## 4. Twelve months after the last hike of a cycle (SPDR total return)

| last hike | SPY | XLE | XLU | XLV | XLF | XLP | XLB | XLI | XLK | XLY | GLD |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 2000-05 | -11% | +6% | +21% | +1% | +16% | +8% | +11% | +6% | -44% | +4% | |
| 2006-06 | +20% | +23% | +26% | +19% | +14% | +14% | +29% | +17% | +27% | +19% | +5% |
| 2018-12 | +31% | +12% | +26% | +20% | +32% | +27% | +24% | +29% | +50% | +28% | +18% |
| 2023-07 | +22% | +10% | +12% | +13% | +26% | +6% | +10% | +18% | +24% | +9% | +24% |

Utilities were up 12-26% in all four; financials 14-32% in all four. Tech is the
coin flip (-44% to +50%). Energy positive in all four but never the leader.

## 5. Read for today (10y 5.1%, bill 4.1%, CPI 3.4%, Fed still hiking, oil shock)

- We are in the "rising 10y inside the regime" cell: historically the market is flat to
  down and the winners are energy, utilities, health care, materials. Losers: durables,
  retail, tech, financials. Energy's edge is an oil-shock artefact (1973, 1979, 1990,
  2000); it has nothing to do with the rate level.
- The switch comes when the 10y turns down. If it turns down because inflation cools
  (1985, 1995, 2019, 2024) the market rips and health care, financials, consumer and
  tech lead while energy and utilities lag badly. If it turns down because growth breaks
  (1990, 2001, 2007) the defensives keep winning and tech gets destroyed.
- Utilities and financials are the only groups that were positive after all four modern
  last hikes; they are the "after" trade with the fewest ways to be wrong. Energy is the
  "during" trade and has been the worst place to be once rates roll over.
- For the board this argues for: XLU/XLV as the sector names to sell puts on if IV rank
  allows (they are in the ABOVE regime and had the best hit rates), XLE only while oil
  is rising, no bull puts on XLY/XLK-heavy names while the 10y is still making highs.
