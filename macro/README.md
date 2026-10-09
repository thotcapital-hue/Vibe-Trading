# Macro desk: daily read, dashboard, and non-directional playbook

This folder is the fund-economist layer above the options board. The board
answers "is this spread worth selling?"; this layer answers "what regime are
we in, what changed in the last week, and which structures fit it?".

## The daily loop (every trading day, after the close)

1. `python scripts/macro_dashboard.py` — pulls the gauges below, prints
   today vs ~7 days ago with signal words, appends to `macro/dashboard.csv`.
2. Read the last 7 files in `macro/reads/` (newest first). Note what moved.
3. Write `macro/reads/YYYY-MM-DD.md` using the template at the bottom:
   state of the world, regime label, three paths with odds, positioning,
   dates, what would change my mind. Odds must move only when a gauge or a
   dated print moved; say which one.
4. Commit both files. Nothing in this loop places or scans trades.

## The gauges and why each one is there

| Panel | Gauge | Question it answers | Signal thresholds |
|---|---|---|---|
| RATES | 10y yield | Is the discount rate still rising? | >5.0 high, >5.5 stress, <5.0 relief |
| RATES | 2s10s (10y minus 2y) | Curve shape: steepening from the long end = term premium, not Fed | ±10bp/week |
| RATES | 10y real yield | The true cost of holding non-yielding assets (gold, long-duration tech) | >2.5 tight |
| RATES | 10y breakeven | Inflation the bond market prices (nominal minus real) | rising = inflation fear |
| RATES | HY OAS (FRED, best effort) | Credit stress, the thing that turns a correction into a bear | +20bp widening, +50bp stress |
| INFLATION | USO, GLD, CPER, UUP | Oil shock vs relief; gold as real-rate barometer; copper as growth; dollar squeeze | USO ±10% in a week |
| INFLATION | TIP/IEF 20d | Inflation-protected vs nominal bonds: is inflation fear rising? | trend |
| GROWTH | XLY/XLP 20d | Cyclicals vs defensives: risk appetite | <-3 defensive, >3 cyclical |
| GROWTH | IWM/SPY 20d | Small caps vs large: domestic growth confidence | trend |
| GROWTH | HYG/LQD 10d | Junk vs investment-grade bonds: the earliest risk-off tell | <-2 RISK-OFF |
| GROWTH | SMH/SPY 20d | Semis leadership: the AI trade's pulse | rollover = tech losing immunity |
| GROWTH | XLU/SPY 20d | Bond-proxy stress: how hard rates are hitting yield stocks | trend |
| BREADTH | RSP/SPY 20d | Equal- vs cap-weight: is the index held up by a few names? | <-3 NARROW, >1 broadening |
| BREADTH | % board >50/200 DMA, sectors >50 DMA | Participation | <40% weak, >60% healthy |
| BREADTH | SPY/QQQ vs 21 DMA | The fast trend line the board uses | below = trend at risk |
| VOL | VIX, VIX3M, VIX9D, VIX/VIX3M | Fear level and term structure; inversion (>1) = stress now | <14 complacent, >20 elevated, >25 fear |
| VOL | SKEW | Tail-risk demand (put skew on SPX) | >150 heavy hedging |
| VOL | SPY 30d IV minus 20d realised | Variance risk premium: are options rich vs actual movement? | >6 sell premium, <0 buy vol |
| VOL | IV rank SPY/QQQ/TLT, board average | Where premium is rich/cheap relative to each name's year | <20 cheap, >50 rich |

## What changes the view (the trigger list)

- **Toward RELIEF**: 10y closes < 5.0%; USO falls > 10% in a week; hike odds
  < 50%; RSP/SPY 20d turns positive; XLU/SPY stops falling.
- **Toward SHOCK**: HYG/LQD 10d < -2%; VIX > 20 with VIX/VIX3M > 1; USO
  +10% in a week; NFP < 100k together with CPI > 3.5%; 10y > 5.5%.
- **Tech breaks**: QQQ closes below its 21-DMA with SMH/SPY 20d rolling
  negative; QQQ IVR jumps > 30 (insurance suddenly bid).
- **Premium regime**: board avg IVR > 45 and SPY IV-RV > 6 => sell-premium
  environment (iron condors, credit spreads pass gates). IV-RV < 0 => stop
  selling, own convexity.

## Trading without directional risk: the playbook

An economist at a fund does not need to know whether the S&P goes up. They
need to know which *relationships* are mispriced. Structures that pay without
a market call:

1. **Variance risk premium harvesting**: when SPY IV exceeds realised by > 6
   points and VIX/VIX3M is normal, sell delta-neutral premium (iron condors
   on SPY/QQQ, strikes beyond the 1-SD expected move both sides). Edge = the
   gap between what options price and what the index actually moves.
   Stop when IV-RV < 0 or term structure inverts.
2. **Sector relative value**: the macro says rates crush bond proxies and
   spare healthcare/energy. Long XLV or XLE against short XLU/XLP in equal
   dollars is market-neutral: it pays if the *gap* keeps widening regardless
   of the index. Options version: bull put spread on the strong leg, bear
   call spread on the weak leg, both beyond 1-SD.
3. **Curve / rates relative value**: TLT vs IEF or SHY expresses "long end
   sells off more" (term premium) without a view on the Fed. Options
   version: bear call spread on TLT financed by a bull put spread on IEF.
4. **Vol term-structure trades**: when the front week is rich into an event
   (Fed, CPI) but the back month is not, sell the front straddle and buy the
   back (calendar). Pays on the post-event vol crush, not on direction.
5. **Dispersion light**: when index IVR is far below single-name IVR (QQQ 6
   vs board names 50+), index protection is the cheap leg. Buy index put
   spreads, sell single-name premium where it is rich. Net vega near flat.
6. **Event-neutral positioning**: never carry a 30–45 DTE credit spread
   across earnings or a Fed/CPI date. The scanner enforces the earnings
   part; the dashboard's date list covers the macro prints.

Sizing for all of the above follows the board: 1% of equity per structure
times the regime multiplier, 15% heat cap, one position per cluster.

## Read template

```
# Macro read — YYYY-MM-DD
## One-paragraph state of the world
## Regime label   (GREEN/CAUTION/RED · breadth · vol · rates · oil)
## What moved in 7 days   (from the dashboard; name the gauge)
## Three paths and my odds   (table; odds move only on named evidence)
## Positioning view   (own / against / avoid / later)
## Dates that decide it
## What would change my mind
## Housekeeping   (paper book, scripts paused/active)
```
