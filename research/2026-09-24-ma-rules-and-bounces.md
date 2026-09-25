# Research note — moving-average rules and intraday bounces (2026-09-24)

Scripts: `scripts/backtest_ma.py`, `scripts/backtest_bounce.py`. Data: Alpaca
split-adjusted bars. 20 names (indices, sector funds, mega-caps) for the daily
rules over 6 years; 10 liquid names, 2 years of hourly bars for the bounce test.
Long-only unless stated, 0.05% cost per side, no slippage.

## Rule 1 and the Rule 2 ribbon family (daily)

| rule | avg CAGR | B&H | avg max DD | B&H DD | trades/name | win | time in | beat B&H | lower DD |
|---|---|---|---|---|---|---|---|---|---|
| 1: 20-DMA close > 200-DMA close | 13.3% | 17.8% | -31% | -39% | 6.1 | 59% | 70% | 4/20 | 14/20 |
| 2a: early in / early out (20H>200L in, 20L<200H out) | 9.4% | 17.8% | -28% | -39% | 3.1 | 58% | 47% | 3/20 | 15/20 |
| 2b: fully clear both ways (20L>200H in, 20H<200L out) | 14.9% | 17.8% | -29% | -39% | 3.8 | 59% | 71% | 5/20 | 13/20 |
| 2c: early in, exit fully below | 14.3% | 17.8% | -27% | -39% | 4.6 | 52% | 62% | 5/20 | 16/20 |
| 2d: early out, re-enter fully above | 12.9% | 17.8% | -28% | -39% | 6.6 | 51% | 63% | 3/20 | 16/20 |

Early-warning test: after a 2a exit signal the underlying's NEXT 20-day return
averaged +2.76% (37% negative) vs +1.55% (42% negative) on all days. The
"early warning" is followed by better-than-average returns: it is a dip, not a
warning. Early exits are whipsaws; the cost shows up as 2a's 47% time in market.

Conclusions: (1) every rule cuts drawdown; none beats buy-and-hold on
average; (2) the best return/drawdown mix is "enter on early touch, exit only
when fully below" (2c); (3) the safe re-entry after an early exit is "fully
above again" (2d) but it gives back most of the gain — cheaper not to exit early.

## Rule 3: buy the hourly bounce off a daily average (uptrend only)

Setup: hourly low touches the line (0.15%), hourly close back above it, prior
daily close > 20-DMA > 200-DMA. Stop 1% below the line, target 1.5R, 3-day
time stop. Shorts mirror in downtrends.

| line | side | trades | win | expectancy (R) | gross/yr at 1% risk |
|---|---|---|---|---|---|
| 20-DMA close | long | 220 | 46% | +0.04 | ~+5% |
| 20-DMA close | short | 69 | 33% | -0.19 | ~-6% |
| 20-day LOW ribbon | long | 132 | 48% | +0.11 | ~+7% |
| 20-day LOW ribbon | short | 81 | 41% | -0.06 | ~-2% |
| 50-DMA, 1.5% stop, 1R target | long | 112 | 49% | -0.01 | ~0 |

Raw odds after a touch (reach +1% before -1%): about 50%. The bounce is a coin
flip; the positive long expectancy comes from the 1.5R target, not from the
touch predicting anything. Expected slippage on a 1%-stop hourly trade (~0.05
to 0.10% round trip = 5 to 10% of R) removes most or all of it. Fading bounces
in downtrends (shorts) loses in every variant.

Use: the touch of a daily average is a LOCATION for placing a defined-risk
options structure (short strike beyond the line, in the trend's direction),
not a stand-alone directional trade.

## Addendum: does a "decisive" close past the 200-DMA help? (`scripts/backtest_confirm.py`)

Daily, 6y, 20 names, long when above the 200-DMA, exit mirrored:

| confirmation | avg CAGR | avg MDD | trades/yr | win | beat B&H |
|---|---|---|---|---|---|
| 1 close beyond (baseline) | 12.5% | -32.5% | 4.5 | 40% | 3/20 |
| 5 consecutive closes | 13.3% | -31.7% | 1.4 | 49% | 3/20 |
| 1 close 2% beyond | 12.8% | -31.4% | 1.5 | 45% | 3/20 |
| 3 closes 2% beyond | 13.0% | -31.6% | 1.1 | 53% | 1/20 |

Hourly closes vs the daily 200-DMA, 2y, 10 names: daily-close baseline 8.8%
CAGR, 4.6 trades/yr; first hourly close 9.1% / 7.8 trades/yr; decisive 0.3%
hourly close 8.8% / 4.8; two consecutive hourly closes 10.0% / 5.2 (best,
within noise). None beat buy-and-hold (0/10).

Conclusion: confirmation cuts whipsaws by 60–75% and lifts the win rate from
~40% to ~50%, but returns are unchanged (12.2–13.3% across the whole grid)
because the later entry gives back what the avoided whipsaws save. Use
confirmation to reduce trade count and false entries, not to add return.
Two consecutive closes (daily or hourly) is a reasonable default; margins
beyond 0.5% add nothing.

## Options overlay on the ribbon regime (`scripts/backtest_options_regime.py`)

Model options (Black-Scholes; IV = VIX x stock-RV/SPY-RV, put skew +0.20/ln(S/K)).
6 years, daily marks, 35 DTE, short strike 1 SD below spot, width 2.5% of spot,
entry only when the 20-day LOW band > 200-day HIGH band and close > 20-low band,
exit on 50% profit / 2x-credit stop / regime change (and 21 DTE where noted).
NOT historical quotes: indicative only.

| variant | CAGR | max DD | Sharpe | trades/yr | win | costs/credit |
|---|---|---|---|---|---|---|
| all 20 names, puts+calls+condors, 21-DTE close, $100k | -14.3% | -60% | -4.1 | 251 | 54/60/22% | ~40% |
| all names, no condors, NO costs | +6.2% | -3.0% | 1.75 | 249 | 81% | 0 |
| all names, hold to expiry, NO costs | +9.0% | -5.5% | 1.87 | 118 | 92% | 0 |
| all names, puts only, realistic costs, no 21-DTE churn, 1% risk | +3.1% | -4.4% | 0.83 | 164 | 82% | 24% |
| all names, puts only, 2% risk | +5.6% | -8.6% | 0.86 | 147 | 82% | 22% |
| SPY/QQQ/IWM only, puts only, 1% risk | +0.7% | -0.5% | 1.27 | 13 | 94% | 5% |
| **SPY/QQQ/IWM, puts only, hold to expiry, 5% risk (15% heat)** | **+4.5%** | **-2.7%** | **1.44** | 7 | 93% | 5% |
| same, 50% take-profit instead of expiry | +3.8% | -2.4% | 1.27 | 13 | 94% | 5% |
| SPY/QQQ/IWM, puts only, regime IGNORED (control) | +1.4% | -1.2% | 1.16 | 34 | 88% | 5% |
| 7 ETFs, puts only, 3% risk | +3.6% | -3.0% | 1.00 | 36 | 89% | 19% |
| stock: long in ABOVE regime, equal weight (20 names / 3 indices) | 18.2% / 10.8% | -14.5% / -15.7% | 1.19 / 0.87 | | | |
| stock: buy & hold (20 names / 3 indices) | 24.3% / 13.5% | -29.1% / -29.9% | 1.15 / 0.75 | | | |

Findings
1. The gross edge exists (variance risk premium + regime filter): +6-9%/yr with 3-5% drawdown before costs.
2. Fixed costs decide everything. At 1-SD strikes the credit is ~12-15% of width, so $0.10 slippage + $2.60 commission per spread eats 25-45% of it on single names and turns the edge negative. On SPY/QQQ/IWM with penny markets costs are ~5% of credit and the edge survives.
3. Trade count is the other lever: the "close at 21 DTE" rule churns ~250 trades/yr and loses; holding to expiry (exit only on regime change or stop) is best.
4. Bear calls in the BELOW regime lost money in every costed run (-$87k to -$150k) in this mostly-bull sample; condors in OVERLAP lost badly (22% win, forced regime exits). Puts-only in ABOVE is the edge.
5. Regime gating raises quality (Sharpe 1.44 vs 1.16, win 93% vs 88%) but cuts opportunity; sizing must rise to compensate (5% risk per index trade, 15% heat).
6. Best risk-adjusted: index puts-only, hold to expiry, Sharpe 1.44 at -2.7% DD, vs stock Sharpe 0.75-1.19 at -15 to -30% DD. Absolute return is lower than stock; as an overlay on T-bill collateral (~4%) total ~8-9% at ~3% DD.

## Scaling the index overlay ("juice") and staged entry

SPY/QQQ/IWM, puts only, ABOVE regime, 1 SD, 2.5% width, 35 DTE, hold to expiry, costs 5% of credit.

| variant | overlay CAGR | overlay DD | Sharpe | COMBO (regime stock + overlay) CAGR / DD |
|---|---|---|---|---|
| 5% risk/trade, 15% heat | 4.5% | -2.7% | 1.44 | 13.7% / -14.1% |
| 10% risk, 30% heat | 9.1% | -5.3% | 1.44 | 16.9% / -12.7% |
| 15% risk, 45% heat | 13.8% | -8.0% | 1.45 | 20.4% / -11.6% |
| 15% risk, 45% heat, STAGED (half at signal, half on pullback below 20-DMA while ABOVE) | 12.0% | -5.1% | 1.84 | 19.0% / -11.8% |
| 45% heat with 2x-credit stop | 10.6% | -7.0% | 1.26 | 18.0% / -14.9% |
| 45% heat, staged, with stop | 10.1% | -5.1% | 1.66 | 17.6% / -13.6% |
| 21 / 14 / 7 DTE at the same width | ~0 (gate rarely passes) | | | |
| buy & hold the 3 indices | 13.5% | -29.9% | 0.75 | |

Findings: (1) return scales linearly with heat while Sharpe holds ~1.45 in
this sample: the regime filter kept the book flat through 2022; the
unmodelled risk is a crash that starts from ABOVE (Feb-2020 type, not in
window) where 45% heat can lose most of itself; (2) staged entry (DCA within
a fixed budget) cuts drawdown by a third for ~2 points of return and lifts
Sharpe to 1.84, win 96%: the second tranche gets a lower strike and more
premium; (3) a 2x-credit stop HURTS here (locks in losses on dips that
recovered by expiry) - regime-flip exit is the better stop; (4) shorter DTE
does not pass the credit gate at 2.5% width; the lever is heat and stacking,
not cycle count. Averaging down by ADDING risk beyond budget was not tested
and should not be: it is the classic premium-seller failure mode.

## Fund techniques on the regime sleeve (`scripts/backtest_stack.py`, 6y, SPY/QQQ/IWM)

| variant | CAGR | max DD | Sharpe |
|---|---|---|---|
| buy & hold, equal weight | 13.4% | -29.8% | 0.75 |
| regime sleeve 1x | 11.3% | -13.0% | 0.91 |
| regime 1.5x (futures/LEAPS financing at bills+0.5%) | 14.7% | -21.0% | 0.82 |
| regime 2x | 17.8% | -28.4% | 0.77 |
| regime 3x | 22.6% | -41.6% | 0.73 |
| regime vol-targeted 15% / 20% | 10.8% / 12.4% | -21% / -25% | 0.75 / 0.71 |
| regime 1x + 20% DBMF | 10.2% | -11.8% | 0.92 |
| DBMF standalone | 4.9% | -29.3% | 0.42 (corr to sleeve +0.30) |

Read: leverage inside the regime filter raises return roughly linearly and
costs Sharpe slowly (financing + scaled drawdowns); 1.5-2x is the zone where
the regime-levered sleeve still beats buy-and-hold on both return and
drawdown. Vol targeting hurt in this sample (it levered the calm run-ups
before the 2022/2024 dips). Managed futures added little: DBMF's correlation
to the sleeve was +0.30 here and its own return was weak 2023-26. Every
"trick" reduces to one of: more risk on the same edge, uncorrelated edges,
or cost/tax efficiency. Only the first moved the needle in this sample.

## Drawdown anatomy, exit/re-entry grid, put entry, combined plan (`scripts/backtest_combined.py`)

Regime sleeve (SPY/QQQ/IWM equal weight, exit on ribbon flip, re-enter on ABOVE), 6y, no switch costs in the grid.

Top drawdowns: 2021-11 -> 2023-03, -13.0%, 336 days, only 21% exposure during the fall
(= lag + re-entry whipsaw, not the fall itself); 2024-12 -> 2025-03, -11.3%, 96% exposure;
2024-07 -> 2024-08, -10.2%, 14 days, 100% exposure; 2023-07 -> 2023-10, -9.3%; 2026-01 -> 2026-03, -8.4%.
Four of the five worst drawdowns happened while fully invested and were too fast (2-10 weeks)
for a slow regime signal; the one slow one was mostly re-entry cost.

Exit x re-entry grid (selected): regime flip + re-enter on 2 closes > 20-DMA: 11.8% / -13.0% /
Sharpe 0.95 (free improvement). Close < 20-low band + re-enter on ABOVE: 10.3% / -8.8% / 0.98
but 151 switches/yr (untradeable after costs). Close < 20-DMA exits: 3-7% CAGR, 54-202 switches/yr.
2-day drop > 3% exit + re-enter when clear: 13.7% / -27.3% (exits do nothing if re-entry is instant).
Lesson: tight exits only reduce drawdown when paired with strict re-entry, and the pairing costs
1-5 points of return plus dozens of switches; the drawdown you avoid is the rally you miss.

Put-based entry (21-DTE ATM short put at each regime entry): CAGR 11.1% vs 11.3%, DD -11.3% vs -13.0%,
Sharpe 0.92 vs 0.91; 6 assignments, 8 expiries, ~7.9% of sleeve collected as premium over 6y.

Combined plan (overlay = index puts, 30% heat, staged, exported curve on $100k):
1x + overlay 16.1% / -10.9% / 1.23;  1.5x + overlay 19.0% / -18.0% / 1.05;  2x + overlay 21.5% / -24.7% / 0.94.
