# Batch: data reconciliation, asset mix, leverage with tranches (2026-09-25)

Scripts: `scripts/backtest_sleeve_mix.py` (tests 1-3), `scripts/backtest_options_regime.py --yahoo`
(overlay model on 19 years of Yahoo bars). Data: Yahoo daily, cached in `research/data/`.
Windows: 19y = 2007-04-10 to 2026-09-25 (Grok's sample), 6y = 2020-09-25 to 2026-09-25.
Costs 5 bp per unit of exposure change; cash earns the 3-month T-bill by year; signals on
close i act on day i+1. CAGR = compound annual return, MaxDD = worst peak-to-trough loss,
Sharpe = return / volatility (rf 0), Calmar = CAGR / |MaxDD|.

## Test 1: why the sleeve read 11.3% on Alpaca and 15.1% on Yahoo

Basket SPY/QQQ/IWM, 6y, "stack" rule (long only while the 20-day low band is above the
200-day high band, else cash at 3%), the rule behind every "regime sleeve 1x" row so far.

| data | CAGR | MaxDD | Sharpe |
|---|---|---|---|
| Alpaca bars, price only (the ledger's 11.3%) | 11.3% | -13.0% | 0.91 |
| Yahoo bars, price only | 13.6% | -13.1% | 1.04 |
| Yahoo bars, total return (dividends reinvested) | 15.1% | -11.3% | 1.14 |

Split: about 1.5 points from dividends, about 2.3 points from the bar source and the
exact start day (a few weeks in late 2020 matter). The ranking of rules is identical on
every footing. From here on every row is Yahoo total return. Overlay model: identical
results on Alpaca and Yahoo bars for the same flags (4.7% / -4.5% / 1.2 both ways), so
the earlier overlay rows were not a data artefact. They were a flag artefact: the
exported 6y curve (7.4% CAGR) was run with `--tp 0.99 --sl 99 --slip 0.03 --comm 1.30`;
with default $0.10 slippage the same run gives 4.7%. The ledger's 9.1% row is not
reproducible with any flags found; treat 7.3% as the 6y overlay number.

## Test 2: asset mix x gate, 1x

Read the 19y block first; the 6y block flatters every trend rule by 5 to 8 points.

| mix | gate | 19y CAGR | 19y MaxDD | 19y Calmar | 6y CAGR | 6y MaxDD | 6y Calmar |
|---|---|---|---|---|---|---|---|
| QQQ | buy & hold | 16.5% | -53.4% | 0.31 | 19.5% | -35.1% | 0.56 |
| QQQ | 200-DMA | 12.8% | -26.2% | 0.49 | 19.7% | -19.3% | 1.02 |
| QQQ | stack | 11.9% | -28.6% | 0.42 | 19.4% | -15.5% | 1.25 |
| QQQ | ribbon 2b | 13.6% | -28.6% | 0.48 | 20.3% | -17.7% | 1.14 |
| SPY | 200-DMA | 8.9% | -20.9% | 0.43 | 14.7% | -19.2% | 0.76 |
| SPY | stack | 9.0% | -27.4% | 0.33 | 14.6% | -10.2% | 1.44 |
| SPY+QQQ | 200-DMA | 10.9% | -22.3% | 0.49 | 17.3% | -18.4% | 0.94 |
| SPY+QQQ | stack | 10.6% | -27.4% | 0.39 | 17.1% | -12.6% | 1.36 |
| SPY+QQQ | ribbon 2b | 11.6% | -28.8% | 0.40 | 18.7% | -16.1% | 1.17 |
| SPY+QQQ+IWM | 200-DMA | 9.2% | -23.9% | 0.39 | 15.6% | -19.1% | 0.82 |
| SPY+QQQ+IWM | stack (current board sleeve) | 8.5% | -25.7% | 0.33 | 15.1% | -12.0% | 1.26 |
| SPY+QQQ+IWM | ribbon 2b | 8.7% | -30.2% | 0.29 | 15.8% | -16.3% | 0.97 |
| IWM | 200-DMA / stack / 2b | 5.5 / 4.0 / 2.6% | -28 / -41 / -46% | | 11.6 / 10.6 / 9.6% | -25 / -23 / -26% | |

Findings
- IWM is a drag under every gate in both windows: dropping it adds 2 to 3 points a year
  and costs nothing on drawdown. The three-fund basket should become SPY+QQQ.
- QQQ alone is the best single asset in both windows; SPY+QQQ gives up about 2 points of
  CAGR for a similar drawdown, i.e. it is not diversifying much (correlation ~0.9).
- Gate choice over 19 years: the plain 200-DMA has the best Calmar on every mix (it exits
  sooner, at the price of 3 to 10 exits a year); ribbon 2b has the highest CAGR but the
  deepest drawdown; "stack" sits between. Over 6 years the order reverses because 2020-26
  had few whipsaws. Neither window says any gate is clearly better; the ribbon trades
  5 to 10 times less often.

## Test 3: leverage inside the regime, with and without tranches

Tranches = 1/3 at entry, 1/3 after 3 weeks, 1/3 after 6 weeks, reset on exit (Grok's
clock, the one that actually fired). Financing on the borrowed part at bill + 0.5%.

Target was CAGR >= 20% with MaxDD no worse than -25% over 19 years. **No combination
meets it.** The 19y frontier:

| sleeve | CAGR | MaxDD | Sharpe | Calmar | worst episodes |
|---|---|---|---|---|---|
| SPY+QQQ, 200-DMA, 1x, tranches | 10.5% | -16.7% | 0.89 | 0.63 | Feb-Mar 2020 -16.7%; 2010 -15.5%; 2018-19 -14.6% |
| QQQ, 200-DMA, 1x, tranches | 12.3% | -20.0% | 0.88 | 0.62 | 2007-09 -20.0%; 2020 -19.6%; 2018-19 -19.5% |
| SPY+QQQ, 200-DMA, 1.5x, tranches | 14.5% | -24.2% | 0.84 | 0.60 | 2020 -24.2%; 2010 -22.7%; 2018-19 -22.0% |
| QQQ, 200-DMA, 1.5x, tranches | 17.0% | -29.8% | 0.84 | 0.57 | |
| SPY+QQQ, 200-DMA, 2x, tranches | 18.1% | -31.2% | 0.81 | 0.58 | |
| QQQ, 200-DMA, 2x, tranches | 21.3% | -38.6% | 0.81 | 0.55 | |
| QQQ, ribbon 2b, 1.5x (tranches make no difference) | 18.5% | -40.9% | 0.79 | 0.45 | |
| Grok: QLD (2x QQQ), 200-DMA, tranches (from the review) | 20.4% | -38.1% | 0.79 | 0.53 | |

Findings
- Return and worst loss move together almost exactly: every extra 0.5x of leverage buys
  about 4 to 5 points of CAGR for 7 to 9 points of drawdown, and Sharpe drifts down.
  There is no free lunch in the leverage dial; the "missing middle" plan does not exist
  with these tools over 19 years. Over 6 years alone, eleven combinations "meet" the
  target, which is exactly why the 6y numbers must not be used for sizing.
- Tranches help a lot with the 200-DMA gate (worst loss 26% -> 20% at 1x on QQQ, 22% ->
  17% on SPY+QQQ) because that gate re-enters often and the tranches hold only a third
  through the whipsaws. They do nothing for the ribbon gate, whose worst losses all
  happen while fully invested months after entry.
- Even at 1x with tranches, February-March 2020 took 17% off SPY+QQQ in three weeks
  before the gate closed. A crash that starts from a healthy trend is the risk no daily
  moving-average rule can remove; only smaller size or a hedge can.

## Test 3b: the options overlay over 19 years

Index bull put spreads, 1 SD short strike, 35 DTE, hold to expiry, exit on regime flip,
10% risk per fund, 30% heat, staged, penny-market costs (the exported-curve flags).

| window | overlay CAGR | overlay MaxDD | Sharpe | trades/yr | costs / credit |
|---|---|---|---|---|---|
| 6y (2020-26) | 7.3% | -3.3% | 1.85 | 12 | 5% |
| 9y (2017-26) | 6.3% | -4.1% | 1.60 | | |
| 13y (2013-26) | 4.5% | -4.1% | 1.37 | | |
| 19y (2007-26) | 3.3% | -5.0% | 0.97 | 7 | 9% |
| 19y, no costs at all | 3.7% | -4.5% | 1.11 | | |

Added to the SPY+QQQ ribbon sleeve on the same $100k: over 19 years the overlay adds
0.4 to 0.5 points of CAGR and shaves half a point off the worst loss (11.6% -> 12.1%,
-28.8% -> -28.3%); over 6 years it adds 2.1 points and cuts the worst loss by 2 points
(18.7% -> 20.8%, -16.1% -> -14.0%, Sharpe 1.29 -> 1.46).

Finding: the overlay's edge is real but small and concentrated in the last nine years,
when implied volatility ran well above realised. Before 2013 the regime was off more
often (fewer trades) and the premium was thinner. It is a modest Sharpe improver, not a
return engine, and the live paper board is the right place to find out whether real
quotes pay even the model's 12 to 15% of width.

## What this changes

1. Sleeve composition: SPY+QQQ (drop IWM) is a 2 to 3 point free improvement.
2. Gate: keep the ribbon for the options overlay (few flips, which is what a 35-day
   spread needs). For the stock sleeve the 200-DMA with tranches has the better 19y
   Calmar; the ribbon has the better 6y Calmar and a fifth of the trades. Not decided.
3. Leverage: 1.5x on SPY+QQQ with tranches is the most anyone should run who cannot
   sit through -25%; 1x with tranches for -17%. Grok's 2x is a -38% to -46% plan.
4. Expectations: honest 19y numbers are 10 to 12% at 1x and 14 to 17% at 1.5x, plus
   0.5 to 2 points from the overlay. The 16%+ figures in the ledger are 6y numbers.

## Test next

- Uncorrelated trend sleeves: the same gate on GLD and TLT (and later managed futures)
  alongside SPY+QQQ, 19y. This is the only untested lever that can raise Calmar rather
  than trade return for drawdown.
- Crash-from-above hedge: cost of a rolling 3-month 10%-OTM index put on the 1.5x sleeve
  vs the drawdown it removes in 2020 and 2018.
- Real-quote validation of the overlay from the paper board's daily credit log.
