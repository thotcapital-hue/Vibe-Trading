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
