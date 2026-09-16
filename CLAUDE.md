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

## Trading rules in force (the "v4" board)

- Scripts live in `scripts/`: `regime_check.py`, `put_spread_scan.py`,
  `call_spread_scan.py`, `spread_scan.py`, `board.py`, `alpaca_rest.py`,
  `tasty_rest.py`, `iv_board.py`. They talk to Alpaca and tastytrade over
  plain REST; no SDK install is needed.
- tastytrade is READ-ONLY (OAuth app created with the `read` scope only;
  env vars TASTY_CLIENT_SECRET / TASTY_REFRESH_TOKEN). It supplies IV rank
  via market-metrics. `tasty_rest.py` must never gain an order function.
- Trading is PAPER only via `paper-api.alpaca.markets`. Never touch the live
  endpoint. Sanjay's real account is at Fidelity; only advise on it, never
  act on it.
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
