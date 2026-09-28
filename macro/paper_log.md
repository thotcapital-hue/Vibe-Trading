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
