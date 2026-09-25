# Working with Sanjay on this repository

## How to explain things

Sanjay is learning options trading and wants full explanations, not shorthand.
This was set on 2026-09-15 and the tone of the reply that re-explained the
Fed-day analysis in plain language is the model to follow.

- Define every trading term the first time it appears in a reply (straddle,
  implied volatility, delta, credit spread, expected move, skew, VIX, dot plot
  and so on). Assume the term is new.
- Spell out the reasoning step by step. Say what a number is, where it came
  from, and what it means for the decision. Do not just state the conclusion.
- When recommending against a trade, explain the mechanism of the risk in
  plain words, not just the rule it breaks.
- Use short sections with plain headers for anything longer than a few
  paragraphs. Tables are fine for levels and comparisons, but every table
  needs a sentence before it saying what to look for.
- Keep the debate-partner posture: examine his ideas critically, give the
  counter-argument, and say plainly when a trade has no edge.

## Daily macro loop (added 2026-09-24)

- Every trading day after the close: run `python scripts/macro_dashboard.py`,
  read the last 7 files in `macro/reads/`, write today's `macro/reads/
  YYYY-MM-DD.md` from the template in `macro/README.md`, commit both.
- The read must say what moved (name the gauge) and move the path odds only
  on named evidence. Compare today against the 7-day-old read explicitly.
- The loop is analysis only: it never scans with --submit or places orders.
  `macro/README.md` holds the gauge table, trigger list and the
  non-directional playbook (variance premium, sector RV, curve RV, calendars).

## Trading rules in force (the "v4" board)

- Scripts live in `scripts/`: `regime_check.py`, `put_spread_scan.py`,
  `call_spread_scan.py`, `spread_scan.py`, `board.py`, `alpaca_rest.py`,
  `tasty_rest.py`, `iv_board.py`, `macro_dashboard.py`. They talk to Alpaca,
  tastytrade, Treasury.gov, CBOE and FRED over plain REST; no SDK needed.
- tastytrade is READ-ONLY (OAuth app created with the `read` scope only;
  env vars TASTY_CLIENT_SECRET / TASTY_REFRESH_TOKEN). It supplies IV rank
  via market-metrics. `tasty_rest.py` must never gain an order function.
- Trading is PAPER only via `paper-api.alpaca.markets`. Never touch the live
  endpoint. Sanjay's real account is at Fidelity; only advise on it, never
  act on it.
- PAPER TRADING RESUMED 2026-09-25 with the "new plan" (research note
  2026-09-24): bull put spreads on SPY/QQQ/IWM only, ribbon regime ABOVE,
  IV rank >= 30, 1-SD short strike, 35-45 DTE, `--risk-pct 10 --max-heat 30
  --conviction full --stage` (10% max loss per index, 30% heat, half size at
  the signal and half on a pullback below the 20-DMA). Hold to expiry; exit
  only on a regime flip or at 3x credit. Index-core credit gate is 12%
  (`--credit-gate 0.12`, the value the model was tested with; costs on index
  options are ~5% of credit); single names keep 15%. The CAUTION half-size
  multiplier does not apply to index-core puts (the ribbon gate, IV-rank floor
  and heat cap replace it); RED still blocks. A weekday 3:30 PM ET routine
  runs the scans and may submit ONLY these three names on the put side with
  exactly these flags; every fill is appended to `macro/paper_log.md`.
- Regime gate: GREEN full size, CAUTION half, RED no new put spreads (bear
  call spreads on broken names only).
- Credit gate: mid credit must be at least 15% of spread width. Short strike
  must sit beyond both the support/resistance level and the 1-SD expected
  move. Risk 1% of equity per trade times conviction. Portfolio heat cap 15%.
  One position per cluster.
- IV-rank floor (added 2026-09-16): do not sell premium on a name whose
  tastytrade IV rank is below 30 (`--min-iv-rank`, override only with
  `--allow-low-ivr`). Rank >= 50 is "rich" and is where scans start.
  `python scripts/iv_board.py` is the morning view sorted by IV rank.
- Ribbon regime gate (added 2026-09-24, from research/2026-09-24-*.md):
  bull puts only when the 20-day LOW band is fully above the 200-day HIGH
  band and price is above the 20-low band; bear calls only in the mirror.
  Override only with `--allow-regime-off`.
- Management (changed 2026-09-24): HOLD TO EXPIRY. No 21-DTE close. Exit
  early only if the spread trades at 3x credit (loss 2x) or the regime flips.
- Concentration (added 2026-09-24): put-selling on SPY/QQQ/IWM
  (`board.INDEX_CORE`). Single names are chart context; sell puts on one only
  when IV rank >= 50 (or `--allow-single-name`). Bear calls in BELOW lost
  money in the 6-year model; treat them as optional, half size.
