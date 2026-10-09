# QLD Trend Sleeve — Locked Strategy Spec

**Status:** Locked for live guidance (as of 2026-09-25)  
**Owner assistant:** QLD Watch  
**Sleeve size (default):** $100,000 unless changed  
**Execution:** Guidance only — do not auto-place trades. User confirms fills.

---

## 1. Purpose

A rules-based **risk-on / risk-off** sleeve that holds **ProShares Ultra QQQ (QLD)** when the Nasdaq-100 trend (via QQQ) is above its long-term average, and sits in **cash** otherwise. Entries are **scaled in** over three equal tranches. Exits are **all-or-nothing** on the trend filter (no profit targets, trailing stops, or discretionary partial sells in the locked plan).

QLD aims for about **2× the daily** return of the Nasdaq-100. Long holds can path-depend (volatility decay); the SMA200 cash gate is the main risk control, not a fix for leverage mechanics.

---

## 2. Instruments and roles

| Role | Symbol | Notes |
|------|--------|--------|
| Trend signal | **QQQ** | Invesco QQQ Trust (Nasdaq-100). All SMA rules use QQQ. |
| Risk-on vehicle | **QLD** | ProShares Ultra QQQ (~2× daily Nasdaq-100). |
| Risk-off vehicle | **Cash** | Sleeve not invested in QLD. |

---

## 3. Core regime signal (locked)

**Indicators (on QQQ daily closes):**

- **SMA200** = 200-day simple moving average of QQQ closing prices.

**Classification (at each daily close):**

- **Risk-on** if QQQ close **>** SMA200  
- **Risk-off** if QQQ close **≤** SMA200  

**1-day lag (locked):**  
Today’s *actionable* stance follows the **prior session’s** close vs SMA200.  
Example: Thursday’s close decides Friday’s stance. Friday’s close decides Monday’s stance.

**Cadence:** After the US cash equity close on weekdays (report ~1:07pm PT), and anytime on request.

---

## 4. Position rules (locked)

### 4.1 Risk-on

- Vehicle = **QLD**  
- Build exposure via the **scale-in** rules below (never more than the earned tranche total).  
- While risk-on and scale-in not complete, dry powder stays in cash.

### 4.2 Risk-off (exit)

- **Sell all QLD** (every filled tranche).  
- Sleeve → **cash**.  
- **Reset scale-in** to zero filled (T1/T2/T3 unfilled).  
- Wait for the next risk-on (prior close back above SMA200) before T1 is eligible again.

There is **no** profit target, trailing stop, time stop, or QLD-price-only exit in the locked plan. A QLD pullback alone does **not** exit; it only matters for **adding** (T2/T3).

---

## 5. Scale-in (locked)

Sleeve is split into **three equal tranches** (default: **~$33,333** each on a $100k sleeve).

### Tranche 1

- Buy **1/3** of the sleeve on the **first risk-on** after adopting the plan, or after a risk-off **reset**.  
- If already risk-on when the plan is adopted and T1 is unfilled → **T1 is due**.

### Tranche 2

Buy the next **1/3** when **either**:

- QLD is roughly **10–15% below** the tranche-1 fill price, **or**  
- **3–4 weeks** have passed still risk-on after T1 fill.

### Tranche 3

Buy the last **1/3** when **any** of:

- QLD is roughly **10–15% below** the **average** fill of positions already held, **or**  
- Another **3–4 weeks** have passed still risk-on after T2, **or**  
- A **fresh risk-on** arrives with dry powder still available (after a reset path that left powder).

**Tracking:** User reports **fill price, date, and size** after each buy. Clocks and pullback levels start from confirmed fills only. Do not invent fills.

**Reported actions only:** `hold` | `buy tranche N` | `sell all`.

---

## 6. What we tested and did **not** lock

### Candidate overlay (discussed 2026-09-25, not adopted)

While SMA200 risk-on:

- If prior QQQ close **<** QQQ **SMA20** → cut current QLD exposure to **50%**.  
- If prior QQQ close **reclaims** SMA20 (still risk-on) → restore to prior full earned size.  
- SMA200 risk-off still **sells all** and resets.

**Decision after backtest:** Keep the **baseline** (section 3–5). Do **not** add the 20-DMA 50% overlay to the locked live plan. Overlay trimmed drawdowns modestly but reduced CAGR with almost no Sharpe gain, and whipsawed often in strong trends.

---

## 7. Backtest design (what “tested” means)

**Run date:** 2026-09-25  
**Data:** Yahoo Finance daily **adjusted** closes for QQQ and QLD (`yfinance`, auto-adjust).  
**Sample:** **2007-04-10 → 2026-09-25** (4,898 trading days).  
- QLD listed 2006-06-21; first day with a defined SMA200 signal is 2007-04-10.  
**Timing:** Position for day *t* from closes through *t−1*; apply QLD close-to-close return on day *t*. Cash days earn 0.  
**Costs:** Primary metrics **ignore** commissions/slippage. Illustrative note only: at 5 bps per unit of |Δexposure|, cumulative drag was larger for the overlay because it traded more.  
**Sharpe:** risk-free rate = 0; vol/Sharpe annualized with √252.  
**Calmar:** CAGR / |max drawdown|.

**Strategies compared (full sleeve when invested — scale-in not modeled in this A/B):**

| ID | Rule |
|----|------|
| **A Baseline** | SMA200 risk-on → 100% QLD; risk-off → cash. **= locked regime economics.** |
| **B Overlay** | Same as A, plus SMA20 50% cut/restore while risk-on. |
| BH QLD / BH QQQ | Buy-and-hold references on the same dates. |

Artifacts: `/workspace/qld-backtest/summary.md`, `metrics.csv`, `equity_curves.csv`.

---

## 8. Backtest results

### 8.1 Full sample (2007-04-10 → 2026-09-25)

| Strategy | CAGR | Max drawdown | Sharpe (rf=0) | Calmar | Avg exposure | Full cash exits |
|----------|-----:|-------------:|--------------:|-------:|-------------:|----------------:|
| **A Baseline (locked regime)** | **21.8%** | −45.8% | **0.79** | 0.48 | 81.1% | 59 |
| B Overlay (not locked) | 17.8% | −39.2% | 0.78 | 0.45 | 70.0% | 59 |
| Buy & hold QLD | 25.3% | −83.1% | 0.73 | 0.30 | 100% | 0 |
| Buy & hold QQQ | 16.5% | −53.4% | 0.80 | 0.31 | 100% | 0 |

Overlay half-cuts: **240** episodes, average **~4.5** days each.

**Read:** Same SMA200 gate as live. A compounds more than B; Sharpe nearly tied; B only modestly softer on worst drawdown. Both far better on drawdown than buy-and-hold QLD.

### 8.2 Subperiods (A vs B)

| Period | Window | A CAGR | B CAGR | A MaxDD | B MaxDD | A Sharpe | B Sharpe |
|--------|--------|-------:|-------:|--------:|--------:|---------:|---------:|
| GFC | 2007-04-10 → 2009-12-31 | 14.5% | 9.9% | −45.8% | −39.1% | 0.62 | 0.52 |
| 2010–2019 | 2010-01-04 → 2019-12-31 | 16.4% | 14.7% | −42.3% | −33.3% | 0.68 | 0.73 |
| 2020–2022 | 2020-01-02 → 2022-12-30 | 22.3% | 22.5% | −40.2% | −34.9% | 0.73 | 0.82 |
| 2023–present | 2023-01-03 → 2026-09-25 | 43.4% | 28.9% | −26.2% | −25.9% | 1.22 | 1.03 |

**Overlay helped** in choppier risk-on eras (2010–2019, 2020–2022).  
**Overlay hurt** in strong one-way periods (GFC recovery path in-sample, 2023–present).

### 8.3 Caveats (keep with the numbers)

- Not live fills; close-to-close research lag.  
- Scale-in averaging **not** in the A/B equity curves (those assume full sleeve when “in”). Live scale-in will differ from A’s path.  
- Leveraged ETF decay is inside QLD prices, not modeled separately.  
- Early-2007 before 2007-04-10 not included.  
- Past results do not guarantee future results.

---

## 9. Live operating checklist

1. After US cash close: QQQ close vs SMA200 → classify risk-on / risk-off.  
2. Apply **1-day lag** → today’s / next session’s action.  
3. If **risk-off** → action **sell all**, reset tranches, cash.  
4. If **risk-on** → apply scale-in vs confirmed fills → **hold** or **buy tranche N**.  
5. User executes; replies with fill price/date/size.  
6. Update tracked state; do not invent fills.

---

## 10. Current book state (snapshot 2026-09-25 after close)

- Signal: **Risk-on** (QQQ close ~744.50 vs SMA200 ~664.15; prior day also risk-on).  
- Tranches **1 / 2 / 3:** unfilled until user confirms a fill.  
- Guidance: **Buy tranche 1** (~$33.3k into QLD on default $100k sleeve).  
- 20-DMA overlay: **not** part of live actions.

---

## 11. Change control

Locked rules (sections 3–5) change only when the user explicitly adopts a rewrite.  
Tested-but-rejected ideas (section 6–8) stay documented so we do not rediscover them without new evidence.

**Document version:** 1.0 — 2026-09-25  
