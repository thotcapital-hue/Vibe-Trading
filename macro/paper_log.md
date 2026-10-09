# Paper trade log (Alpaca paper account)

One line per event, newest last. Format:
`date | symbol | action | structure | qty | credit | max loss | reason / gates`

2026-09-25 | AVGO | closed | 1 share (not ours, legacy) | 1 | sold 350.10 | - | housekeeping, account flat
2026-09-25 | SPY QQQ IWM | scan, no trade | put spreads Oct 30 | - | QQQ 702/697 0.59 (11.9%), SPY 740/735 0.53 (10.6%) | - | below 12% index gate; IWM below its 20-band (not eligible); paper trading resumed
2026-09-25 | XLV | scan, no trade | bull put Oct 30 / Nov 6 | - | after-hours scan: no positive credit beyond 1-SD floor 160.5 | - | ABOVE regime, IVR 57; rescan in market hours
2026-09-25 | XLU | scan, no trade | put side refused (ribbon BELOW); bear call Oct 30 / Nov 6 no positive credit after hours | - | - | - | IVR 71, price 11% under 200-DMA; history favours utilities in this regime, chart does not
2026-09-28 | QQQ | scan, no trade | bull put 691/686 Oct 30, first tranche x10 | 10 | @ 0.59 credit | 4,405 | ABOVE, IVR 48; mid credit oscillated 11.9-12.1% around the 12% gate; routine retries 3:30 PM
2026-09-28 | SPY | scan, no trade | bull put 733/728 Oct 30 | - | 0.54 (10.8%) | - | ABOVE, IVR 36; below 12% gate
2026-09-28 | XLV | scan, no trade | bull put 160/158 Nov 6 | - | mid 0.34 (17%) but natural 0.00, no OI, indicative feed empty | - | no real market at 1-SD strikes; sector-fund puts too illiquid, do not trade
2026-09-28 | ROUTINE | diagnostic | fresh-session dry run reached step 5 | - | - | - | testing why the 3:30 PM run left no journal line
2026-09-28 | QQQ | submitted, unfilled, cancelled | bull put 694/689 Oct 30, first tranche x10, order e30e7d75 | 10 | 0.60 (12.0%) | 4,400 | passed all gates at 4:01 PM ET (after the 4:00 stock close); no fill by the 4:15 options close; cancelled to keep the book clean. Routine at 3:34 PM did nothing: its session had no repo attached; prompt patched to clone first
2026-09-29 | ROUTINE | no run | 3:30 PM routine fired (87 s) but its fresh session again had no repository attached; no scans, no orders | - | - | - | routine disabled and recreated to fire into a repo-attached session; paper account flat, equity 95,863
2026-09-30 | QQQ | scan PASS, submit blocked, no trade | bull put 702/697 Oct 30, first tranche x10 | 10 | 0.61 (12.2%) | 4,390 | ABOVE, IVR 46, regime CAUTION; passed all gates at 3:31 PM ET; the --submit re-run was denied by the session's permission classifier ("Real-World Transactions"), no order reached Alpaca; paper book confirmed empty
2026-09-30 | SPY | scan, no trade | bull put 736/731 Oct 30 | - | 0.54 (10.8%) | - | ABOVE, IVR 34; below 12% gate
2026-09-30 | IWM | scan, no trade | bull put 263/261 Oct 30 (widths 2,3) | - | 0.23 (11.5%) | - | price 278.86 under its 20-low band 285.28 (not eligible); IVR 26 < 30 (cheap); below 12% gate
2026-10-01 | QQQ | scan PASS, submit blocked, no trade | bull put 695/690 Nov 6, first tranche x10 | 10 | 0.62 (12.4%) | 4,380 | ABOVE, IVR 48, regime CAUTION; passed all gates at 3:33 PM ET; the --submit re-run was denied by the session's permission classifier ("Real-World Transactions") for the second day running; no order reached Alpaca
2026-10-01 | SPY | scan, no trade | bull put 730/725 Nov 6 | - | 0.54 (10.9%) | - | ABOVE, IVR 35; below 12% gate
2026-10-01 | IWM | scan, no trade | put side Nov 6 / Nov 13 (widths 2,3) | - | no positive credit beyond the 1-SD floor 261.67 | - | price 279.25 under its 20-low band 284.46 (not eligible); IVR 30 at the floor (cheap); scanner said Walk
2026-10-02 | QQQ | scan, no trade | bull put 700/695 Nov 6 | - | 0.55 (11.0%) | - | ABOVE, IVR 44, regime CAUTION; below 12% gate (QQQ +0.9% on the day, premium compressed from yesterday's 12.4%)
2026-10-02 | SPY | scan, no trade | bull put 735/730 Nov 6 | - | 0.50 (10.1%) | - | ABOVE, IVR 31; below 12% gate
2026-10-02 | IWM | scan, no trade | bull put 265/262 Nov 6 (widths 2,3) | - | 0.34 (11.5%) | - | price 281.59 under its 20-low band 283.83 (not eligible); IVR 23 < 30 (cheap); below 12% gate
2026-10-05 | QQQ | scan, no trade | bull put 710/705 Nov 6 | - | 0.56 (11.3%) | - | ABOVE, IVR 45, regime CAUTION; below 12% gate
2026-10-05 | SPY | scan, no trade | bull put 745/740 Nov 6 | - | 0.53 (10.6%) | - | ABOVE, IVR 31; below 12% gate (SPY +0.8% to 775.84, IV index 15.5%)
2026-10-05 | IWM | scan, no trade | bull put 267/265 Nov 6 (widths 2,3) | - | 0.23 (11.5%) | - | ribbon eligible again (price 283.59 just above 20-low band 283.16); IVR 24 < 30 (cheap); below 12% gate
2026-10-06 | QQQ | scan PASS, submit blocked, no trade | bull put 708/703 Nov 20, first tranche x10 | 10 | 0.60 (12.0%) | 4,400 | ABOVE, IVR 41, regime CAUTION; passed all gates at 3:33 PM ET (12.0% exactly at the gate, OI 158/164 thin); the --submit re-run was denied by the session's permission classifier ("Real-World Transactions") for the third time; no order reached Alpaca
2026-10-06 | SPY | scan, no trade | bull put 743/738 Nov 20 | - | 0.53 (10.5%) | - | ABOVE but IVR 28 < 30 (cheap, first time under the floor); below 12% gate; IV index 14.9%
2026-10-06 | IWM | scan, no trade | bull put 265/263 Nov 6 (widths 2,3) | - | 0.23 (11.3%) | - | price 280.86 back under its 20-low band 282.49 (not eligible); IVR 24 < 30 (cheap); below 12% gate
2026-10-07 | QQQ | scan PASS, submit not attempted, no trade | bull put 706/701 Nov 20, first tranche x10 | 10 | 0.61 (12.2%) | 4,390 | ABOVE, IVR 41, regime CAUTION; passed all gates at 3:33 PM ET (OI 444/173); --submit was denied by the session's permission classifier on 9/30, 10/1 and 10/6 with an instruction not to retry in later turns; no permission rule has been added, so the routine did not re-attempt; no order reached Alpaca. Sanjay must add a Bash allow rule for the scanner's --submit before the routine can place paper orders
2026-10-07 | SPY | scan, no trade | bull put 748/743 Nov 6 | - | 0.53 (10.6%) | - | ABOVE but IVR 28 < 30 (cheap); below 12% gate; IV index 15.0%
2026-10-07 | IWM | scan, no trade | bull put 258/256 Nov 20 (widths 2,3) | - | 0.23 (11.5%) | - | price 277.85 under its 20-low band 281.81 (not eligible); IVR 26 < 30 (cheap); below 12% gate
2026-10-08 | QQQ | scan PASS, submit not attempted, no trade | bull put 694/689 Nov 20, first tranche x10 | 10 | 0.61 (12.2%) | 4,390 | ABOVE, IVR 45, regime CAUTION; passed all gates at 3:34 PM ET (OI 207/274; QQQ -1.4% on the day, skew widened to +5.3 vol); --submit still blocked by the session's permission classifier (denied 9/30, 10/1, 10/6, told not to retry); no allow rule exists, so not re-attempted; no order reached Alpaca
2026-10-08 | SPY | scan, no trade | bull put 740/735 Nov 13 | - | 0.53 (10.6%) | - | ABOVE, IVR 30 (back at the floor); below 12% gate; IV index 15.3%
2026-10-08 | IWM | scan, no trade | bull put 258/256 Nov 20 (widths 2,3) | - | 0.23 (11.5%) | - | price 277.37 under its 20-low band 281.18 (not eligible); IVR 25 < 30 (cheap); below 12% gate
2026-10-09 | QQQ | scan PASS, submit not attempted, no trade | bull put 703/698 Nov 20, first tranche x10 | 10 | 0.61 (12.2%) | 4,390 | ABOVE, IVR 38, regime CAUTION; passed all gates at 3:34 PM ET (OI 186/395; skew +5.2 vol); --submit still blocked by the session's permission classifier (denied 9/30, 10/1, 10/6, told not to retry); no allow rule exists, so not re-attempted; no order reached Alpaca. Fourth qualifying QQQ setup missed
2026-10-09 | SPY | scan, no trade | bull put 748/743 Nov 13 | - | 0.52 (10.5%) | - | ABOVE but IVR 27 < 30 (cheap); below 12% gate; IV index 14.7%, lowest of the cycle
2026-10-09 | IWM | scan, no trade | bull put 261/259 Nov 20 (widths 2,3) | - | 0.24 (12.0%) | - | credit gate cleared for the first time but price 279.06 under its 20-low band 280.62 (not eligible) and IVR 21 < 30 (cheap)
