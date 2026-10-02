# Review of Grok's "QLD Trend Sleeve" (2026-09-25)

Spec under review: `research/external/2026-09-25-grok-qld-trend-sleeve.md`.
Re-test script: `scripts/backtest_qld_sleeve.py` (Yahoo adjusted daily closes,
cached in `research/data/QQQ.csv` and `QLD.csv`; stdlib only).

## 1. Did Grok's arithmetic hold up?  Yes, exactly.

Same sample (2007-04-10 to 2026-09-25, 4,898 days), same 1-day lag, same
rf = 0 Sharpe, independent data pull and independent code:

| strategy | Grok CAGR / MaxDD / Sharpe | ours |
|---|---|---|
| A  QQQ > SMA200 -> 100% QLD, else cash | 21.8% / -45.8% / 0.79, 81% exposure, 59 exits | 21.8% / -45.8% / 0.79, 81%, 59 |
| B  A + SMA20 50% overlay | 17.8% / -39.2% / 0.78 | 17.8% / -39.2% / 0.78 |
| Buy & hold QLD | 25.3% / -83.1% / 0.73 | 25.3% / -83.1% / 0.73 |
| Buy & hold QQQ | 16.5% / -53.4% / 0.80 | 16.5% / -53.4% / 0.80 |

All four sub-period rows in Grok's table 8.2 reproduce to the decimal as well.
The 1-day lag is implemented correctly (a same-close fill would have shown a
look-ahead-inflated 53% CAGR; Grok avoided that classic error). Grok's
rejection of the SMA20 overlay is also confirmed and matches our own
2026-09-24 finding that tight exits cost return without buying much Sharpe.

Robustness checks Grok did not run, none of which change the picture:

| variant | CAGR | MaxDD | Sharpe | exits |
|---|---|---|---|---|
| A with 5 bp costs and T-bill on cash | 21.7% | -45.6% | 0.79 | 59 |
| A signalled on unadjusted QQQ prices (what a chart shows) | 22.3% | -45.5% | 0.81 | 57 |
| A with a 3% exit band below the SMA200 | 21.6% | -47.7% | 0.77 | 24 |
| A-scale: the spec's actual live tranches (10% or 3 weeks) | 20.4% | -38.1% | 0.79 | 59 |
| A-scale with 15% / 4 weeks | 19.7% | -38.1% | 0.78 | 59 |
| Sanjay's ribbon 2b (20L > 200H) driving QLD | 21.8% | -51.7% | 0.75 | 11 |
| Sanjay's ribbon 2a (early in/out) driving QLD | 20.8% | -59.5% | 0.73 | 214 |
| Same SMA200 gate, unlevered QQQ | 12.8% | -26.5% | 0.85 | 59 |

## 2. What the numbers actually say

**It is our trend sleeve at 2x, with a cruder gate.** The same gate on plain
QQQ earns 12.8% with a 26% worst loss and a *higher* Sharpe (0.85 vs 0.79).
Swapping QQQ for QLD roughly doubles both the return and the pain and loses a
little on risk-adjusted terms to volatility decay. Nothing about QLD adds
edge; it adds leverage. Our 2026-09-24 note found the same trade-off with a
1.5x lever (about +3 pts CAGR for +7 pts drawdown).

**The gate is a parachute, not a seatbelt.** Five separate drawdowns of 38% or
worse (2007-09, 2010, 2018-19, 2020, 2021-23). The 2010 peak was not regained
until July 2013. On $100k that is a paper loss of $46k at the worst point and
more than three years under water in the second-worst case.

**Only 12 of 59 round trips made money.** Median hold 4 trading days; 38 trips
lasted 10 days or less and averaged -3.5% each. Every dollar of profit came
from a dozen long trends (2009, 2013-14, 2017, 2020-21, 2023-24). The live
failure mode is behavioural: four or five losing whipsaws in a row (2010-11,
2015-16, 2018) and the trader stops following the rule right before the trend
that pays for everything.

**The pullback tranche rule never fired.** In 19 years, tranche 2 and 3 were
triggered 32 times by the 3-week clock and 0 times by the 10% pullback. A
2x fund falling 10% while QQQ stays above its 200-day average within three
weeks of a fill simply did not happen. The "buy the dip" language is
decorative; the plan is really "one third now, one third in three weeks, one
third in six weeks". That is still a good idea: because most whipsaws end
inside three weeks, scaling in holds only one third through them, which is
why A-scale cuts the worst loss from 46% to 38% and lifts Calmar from 0.48 to
0.53 with almost no cost in CAGR. Grok locked this rule without testing it;
it happens to be the best thing in the spec.

**Entry timing matters and the spec ignores it.** QQQ closed 12.1% above its
SMA200 on 2026-09-25 (744.50 vs 664.14). The exit signal is therefore about
11% away on QQQ, or roughly 22% on QLD, before the rule even reacts. Across
the 1,760 historical days on which QQQ stood 10% or more above its SMA200,
buying QLD and holding to the gate exit returned a median +6.3% but ended
negative 40% of the time, with a median worst point of -9.7% and 8% of
starts suffering a 20%+ loss before the exit (worst -34.5%, February 2020).
Tranche 1 today is a coin flip with a fat left tail.

**Over our own six-year window (2020-09 to 2026-09, 5 bp costs)** A earns
33.1% with a 39% worst loss and Sharpe 1.03; A-scale 30.2% / -28.2% / 1.00
(Calmar 1.07). Our combined 1x regime sleeve plus option overlay from the
2026-09-24 note did 16.1% / -10.9% / 1.23 (Calmar about 1.5). Grok's sleeve
makes roughly twice the money for roughly three times the worst loss.

## 3. Verdict for the "which strategy is best" question

- Grok's backtest is honest and reproducible. Nothing in it is wrong.
- It is not a different strategy from ours; it is the same 200-day trend idea
  with double leverage and no breadth, volatility or IV inputs.
- Choose it only if a 40-50% peak-to-trough loss on the sleeve, and three
  years under water, are genuinely acceptable. Sharpe says it is not better
  per unit of risk than the unlevered version; it is just bigger.
- If used at all: keep the tranches (they are the risk control), treat the
  3-week clock as the real rule, and size the sleeve so that a 45% loss of it
  is a loss you can hold through. A $100k sleeve at 2x is the same market
  exposure as $200k of QQQ; size it like that.
- Better version of the same idea, from our own tests: 1x QQQ or SPY under the
  regime gate, leverage added only inside the regime (1.5x cap), plus the
  index put-spread overlay. Lower raw return, far better Calmar.
