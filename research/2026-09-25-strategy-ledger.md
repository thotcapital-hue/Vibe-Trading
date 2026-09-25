# Strategy ledger (as of 2026-09-25)

Every strategy tested in this repository so far, with its returns, on as
common a footing as the tests allow. Sources: `research/2026-09-24-ma-rules-
and-bounces.md`, `research/2026-09-25-grok-qld-sleeve-review.md`, and a
decomposition run on 2026-09-25 (asset vs gate, Yahoo total-return data).

Footing. "6y" = 2020-09-25 to 2026-09-25. Alpaca-based tests use
split-adjusted PRICE returns (no dividends); Yahoo-based tests use adjusted
TOTAL returns (dividends reinvested), which adds roughly 1 to 1.5 points a
year on SPY/IWM. The two data sources have not yet been reconciled on one
run (see "test next"). Options results are model prices, not historical
quotes. CAGR = compound annual return; MaxDD = worst peak-to-trough loss;
Sharpe = return per unit of volatility (rf = 0 unless noted).

## A. Directional trend sleeves, unlevered, 6y

| # | strategy | asset | data | CAGR | MaxDD | Sharpe | note |
|---|---|---|---|---|---|---|---|
| A1 | buy & hold | SPY/QQQ/IWM eq-wt | Yahoo TR | 16.9% | -29.0% | 0.91 | benchmark |
| A2 | buy & hold | same | Alpaca px | 13.4% | -29.8% | 0.75 | same thing without dividends and on a slightly different rebalance |
| A3 | 200-DMA close gate (Grok's rule) | basket | Yahoo TR | 14.9% | -20.7% | 1.13 | |
| A4 | ribbon 2b (20-low > 200-high in, 20-high < 200-low out) | basket | Yahoo TR | 15.1% | -18.2% | 1.09 | our board's gate |
| A5 | ribbon 2d (exit on flip, re-enter fully above) = "regime sleeve 1x" | basket | Alpaca px | 11.3% | -13.0% | 0.91 | the sleeve used in the leverage and combo tests |
| A6 | A5 + re-enter after 2 closes > 20-DMA | basket | Alpaca px | 11.8% | -13.0% | 0.95 | free improvement, not yet coded |
| A7 | 200-DMA gate | QQQ only | Yahoo TR | 19.1% | -21.1% | 1.14 | Grok's rule at 1x |
| A8 | ribbon 2b | QQQ only | Yahoo TR | 19.6% | -19.7% | 1.15 | |
| A9 | ribbon 2b | SPY only | Yahoo TR | 16.5% | -16.5% | 1.31 | best Sharpe of any 1x sleeve |
| A10 | 200-DMA gate / ribbon 2b | IWM only | Yahoo TR | 10.6% / 8.5% | -27% / -29% | 0.69 / 0.57 | both gates LOSE to IWM buy & hold (13.2%) |
| A11 | Rule 1 (20-DMA > 200-DMA), avg of 20 names | 20 names | Alpaca px | 13.3% | -31% | | beat B&H on 4/20 names |
| A12 | ribbon 2a / 2b / 2c / 2d, avg of 20 names | 20 names | Alpaca px | 9.4 / 14.9 / 14.3 / 12.9% | -28 / -29 / -27 / -28% | | 2c best mix; none beat B&H on average |
| A13 | confirmation filters (2-5 closes, 2% margin) | 20 names | Alpaca px | 12.5 to 13.3% | -31 to -32% | | cut trades 60-75%, return unchanged |
| A14 | long in ABOVE regime, equal weight | 20 names / 3 indices | Alpaca px | 18.2% / 10.8% | -14.5% / -15.7% | 1.19 / 0.87 | from the options test's stock leg |

Read: every gate cuts the worst loss by a third to a half and costs 0 to 3
points of return. Gate choice matters far less than asset choice: QQQ alone
beats the basket by 4 points, and IWM drags whichever gate it is under. The
ribbon and the plain 200-DMA are within noise of each other on the basket;
the ribbon trades far less (11 vs 59 exits on QLD over 19 years).

## B. Leverage on the regime sleeve (A5 base), 6y, Alpaca px

| # | strategy | CAGR | MaxDD | Sharpe |
|---|---|---|---|---|
| B1 | regime 1x | 11.3% | -13.0% | 0.91 |
| B2 | regime 1.5x (financing bills + 0.5%) | 14.7% | -21.0% | 0.82 |
| B3 | regime 2x | 17.8% | -28.4% | 0.77 |
| B4 | regime 3x | 22.6% | -41.6% | 0.73 |
| B5 | vol-targeted 15% / 20% | 10.8% / 12.4% | -21% / -25% | 0.75 / 0.71 |
| B6 | regime 1x + 20% DBMF (managed futures) | 10.2% | -11.8% | 0.92 |
| B7 | Grok: 200-DMA gate on QLD (2x QQQ), full size, 5 bp | 33.1% | -39.2% | 1.03 |
| B8 | Grok: same, scaled in over 3 tranches (the live plan) | 30.2% | -28.2% | 1.00 |
| B9 | ribbon 2b on QLD | 33.9% | -37.2% | 1.04 |

Read: leverage adds return roughly linearly and lowers Sharpe slowly. B7-B9
look better than B3 because they are QQQ-only over a Nasdaq-led window and
count dividends, not because the gate is better (compare A7 vs A3).

## C. Options overlay (index bull put spreads, model prices), 6y

| # | variant | CAGR | MaxDD | Sharpe | trades/yr |
|---|---|---|---|---|---|
| C1 | all 20 names, puts+calls+condors, 21-DTE close, costs | -14.3% | -60% | -4.1 | 251 |
| C2 | all names, hold to expiry, no costs (gross edge) | +9.0% | -5.5% | 1.87 | 118 |
| C3 | all names, puts only, costs, 1% risk | +3.1% | -4.4% | 0.83 | 164 |
| C4 | SPY/QQQ/IWM puts only, 5% risk, 15% heat, hold to expiry | +4.5% | -2.7% | 1.44 | 7 |
| C5 | same, 10% risk, 30% heat | +9.1% | -5.3% | 1.44 | |
| C6 | same, 15% risk, 45% heat | +13.8% | -8.0% | 1.45 | |
| C7 | 15% risk, 45% heat, STAGED | +12.0% | -5.1% | 1.84 | |
| C8 | regime ignored (control) | +1.4% | -1.2% | 1.16 | 34 |
| C9 | bear calls in BELOW, any costed run | loss | | | |
| C10 | put-based entry to the sleeve (ATM 21-DTE short put) | 11.1% vs 11.3% | -11.3% vs -13.0% | 0.92 vs 0.91 | |

Read: the edge (volatility risk premium inside the regime) is real but small
and only survives where costs are ~5% of credit (index ETFs). Return scales
with heat; staging lifts Sharpe to 1.84. Bear calls and condors lose. The live
board runs C5 with staging (10% risk, 30% heat, 12% credit gate).

## D. Combined plans, 6y, Alpaca px, $100k

| # | plan | CAGR | MaxDD | Sharpe |
|---|---|---|---|---|
| D1 | sleeve 1x + overlay 30% heat staged | 16.1% | -10.9% | 1.23 |
| D2 | sleeve 1.5x + overlay | 19.0% | -18.0% | 1.05 |
| D3 | sleeve 2x + overlay | 21.5% | -24.7% | 0.94 |
| D4 | Grok QLD scaled (B8), for comparison | 30.2% | -28.2% | 1.00 |

## E. Short-term tactics (dead ends)

| # | tactic | result |
|---|---|---|
| E1 | hourly bounce off 20-DMA, long, 1.5R target | +0.04R/trade, ~+5%/yr gross, gone after slippage |
| E2 | bounce off 20-day LOW band, long | +0.11R, ~+7%/yr gross, marginal after slippage |
| E3 | any short/fade variant | negative in every version |
| E4 | 50-DMA bounce | zero expectancy |
| E5 | "early warning" ribbon exit (2a) | next-20-day return AFTER the signal was better than average: it is a dip, not a warning |
| E6 | 21-DTE close / 50% take-profit on spreads | churn; hold to expiry beats both |
| E7 | 2x-credit stop on spreads | hurts (locks in dips that recovered) |

## F. Long history (2007-2026, Yahoo TR), Grok's sample

| strategy | CAGR | MaxDD | Sharpe | exits |
|---|---|---|---|---|
| 200-DMA gate on QLD | 21.8% | -45.8% | 0.79 | 59 |
| same, scaled in | 20.4% | -38.1% | 0.79 | 59 |
| ribbon 2b on QLD | 21.8% | -51.7% | 0.75 | 11 |
| 200-DMA gate on QQQ (1x) | 12.8% | -26.5% | 0.85 | 59 |
| buy & hold QLD / QQQ | 25.3% / 16.5% | -83% / -53% | 0.73 / 0.80 | |

Read: the 6y window (2020-26) flatters every trend rule. Over 19 years the
same 1x QQQ gate made 12.8%, not 19%, and the 2x version had five drawdowns
of 38% or more. Any plan sized on 6y numbers should be stress-sized on these.

## What the ledger says

1. The best risk-adjusted thing we have is D1 (16.1% / -10.9% / 1.23) and the
   best raw return per unit of worst loss at higher return is B8/D4 territory
   only if a 30-45% drawdown is acceptable. Nothing in between has been built.
2. Asset choice is under-examined: QQQ-only and SPY-only sleeves both beat the
   basket, and IWM is a drag under every gate. The basket was a diversification
   reflex, not a tested choice.
3. Gate choice is roughly settled: 200-DMA and ribbon 2b are equivalent on
   return; ribbon trades less; ribbon 2d (our current sleeve rule) gives up
   3-4 points for a smaller drawdown. Confirmation filters and early exits do
   not add return.
4. The overlay is the only edge that is not just beta-times-leverage, and it
   is small: 4-12% a year depending on heat, Sharpe 1.4-1.8, model-priced.
5. The live paper board is testing C5-staged in real quotes. Nothing has
   passed the 12% credit gate yet.

## Test next, in order

1. Reconcile data: rerun A5/B1/D1 on Yahoo total-return data so every row in
   this ledger is on one footing (the 11.3% vs 15.1% gap is dividends plus the
   2d vs 2b rule; confirm the split).
2. Asset mix inside the sleeve: SPY+QQQ only vs basket vs QQQ only, 6y and
   19y, under ribbon 2b and 200-DMA. Decide whether IWM stays.
3. Leverage inside the regime at 1.5x on the better asset mix, 19y, with
   Grok-style tranches; target 20%+ CAGR at under 25% worst loss, then see if
   the overlay pushes that to a Sharpe above 1.2.
4. Crash-from-ABOVE stress: replay Feb-Mar 2020 and Jan-Feb 2018 through D1
   at 30% and 45% heat (the overlay's unmodelled risk).
5. Code the two free improvements into the board: re-entry after 2 closes
   above the 20-DMA (A6) and the put-based entry (C10).
6. Real options quotes: log the daily 1-SD SPY/QQQ credits from Alpaca for a
   month and compare to the model's 12-15% of width, to validate C5.
