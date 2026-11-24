# MONEYCHECK — AquaFunded 2 Step Pro $5,000 — Asia sweep/CHoCH/FVG, buffer 5

Strategy under test: EURUSD 1m, Asia sweep → CHoCH → first FVG, 5-pip stop
buffer, 1.05R live stop cap, target = opposite Asia level. Trade log
`trades_buffer5.csv`, 1,113 fills, 2021-01-01 .. 2026-11-17.

Firm rules: `fx6v2/masters_tests/AQUAFUNDED_RULES_RECON.md` (2026-11-15).
$5k 2 Step Pro: P1 +10% ($5,500), P2 +5% ($5,250), daily DD 5% ($250,
00:00 UTC), max DD 10% ($500) trailing from highest balance, split 90%,
3% payout processing, consistency best day < 50% of cycle profit, 3
qualifying days ≥ $25, 14-day cycles, min payout $111.11 gross, eval fee
$15 refunded at the 4th payout. No time limit. EAs allowed.

Method: 50,000 paths per configuration, weekly block bootstrap of the real
trade sequence (4-week blocks as a serial-dependence control). Sequential
stage machine, not analytic pass rates. `asia_choch_1m_moneycheck.py`.

---

## 1. Verdict

**STRONG CANDIDATE at 0.5%/trade. GOOD CANDIDATE at 0.6%.**
0.75% passes every test on paper but its historical drawdown is 0.95× the
hard limit, which is not a margin. 1.0% is disqualified by evidence.

| | 0.5% | 0.6% | 0.75% | 1.0% |
|---|---:|---:|---:|---:|
| Survival | **99.952%** | 99.836% | 99.134% | 95.838% |
| Grade | Strong | Strong | Strong | Strong |
| Historical DD vs $500 | **0.633×** | 0.760× | 0.950× | **1.266× FAIL** |
| Net cash / 2 years | $1,966 | $2,487 | $3,270 | disqualified |
| Median first payout | 219 d | 190 d | 157 d | 127 d |

The binding constraint is **time**, not survival.

---

## 2. Trading-EV quality

| Metric | Value |
|---|---:|
| Trades | 1,113 |
| Win rate | 61.90% |
| Average win / loss | 1.154R / 1.043R |
| EV per trade | +0.3172R (+2.69 pips) |
| Profit factor | 1.799 |
| Max drawdown (closed) | 12.66R |
| Max losing streak | 7 |
| Average risk | 10.84 pips |
| Median hold | 65 min (mean 175) |

Realised R and pips now agree. The 1.05R stop cap does not manufacture the
edge here; the 5-pip buffer does.

---

## 3-4. Challenge

| | 0.5% | 0.6% | 0.75% | 1.0% |
|---|---:|---:|---:|---:|
| Phase 1 pass | 99.968% | 99.900% | 99.568% | 98.152% |
| Phase 2 given P1 | 99.994% | 99.964% | 99.775% | 98.926% |
| Overall challenge | 99.962% | 99.864% | 99.344% | 97.098% |
| Mean trades to first payout | 123 | 107 | 90 | 73 |

Daily-DD breach is effectively zero at every tested size: worst day is
−2.1R, i.e. $52.50 at 0.5% against a $250 limit (0.21×).

---

## 5-7. Funded stage and hard limits

| | 0.5% | 0.6% | 0.75% | 1.0% |
|---|---:|---:|---:|---:|
| Payout given funded | 99.990% | 99.972% | 99.789% | 98.702% |
| Funded breach, single attempt | 0.010% | 0.028% | 0.210% | 1.260% |
| Trades to first payout (mean) | 123 | 107 | 90 | 73 |

Historical hard-limit check (the whole 2021-2026 record replayed at each
size, §7.3):

| Risk | Max DD $ | vs $500 | Worst day $ | vs $250 | Gate |
|---:|---:|---:|---:|---:|---|
| 0.25% | 158.31 | 0.317× | 26.25 | 0.105× | pass |
| 0.50% | 316.61 | 0.633× | 52.50 | 0.210× | pass |
| 0.60% | 379.94 | 0.760× | 63.00 | 0.252× | pass |
| 0.75% | 474.92 | 0.950× | 78.75 | 0.315× | pass, 5% margin |
| 1.00% | 633.23 | **1.266×** | 105.00 | 0.420× | **FAIL** |

The 12.66R drawdown is closed-trade equity. With a 0.5R floating pad the
0.75% multiple becomes 0.987×; with 1.0R it becomes 1.025×, a breach.
0.75% therefore sits inside the measurement error of the check. 0.5% and
0.6% do not.

---

## 8-11. Economics

Realistic (payout resets the trailing floor), 50,000 paths:

| | 0.5% | 0.6% | 0.75% |
|---|---:|---:|---:|
| Payouts / 2 years | 9.91 | 10.76 | 11.52 |
| Average payout (net) | $200 | $233 | $285 |
| Gross payouts / 2 years | $1,981 | $2,502 | $3,285 |
| Expected fees | $15.01 | $15.10 | $15.52 |
| **Net cash / 2 years** | **$1,966** | **$2,487** | **$3,270** |
| Per year | $983 | $1,244 | $1,635 |
| Return on $5k | 19.7%/yr | 24.9%/yr | 32.7%/yr |
| Attempts per payout | 1.0005 | 1.0016 | 1.0087 |

Conservative (floor does not reset after a payout; only the cushion above
the floor can be withdrawn):

| | 0.5% | 0.6% | 0.75% |
|---|---:|---:|---:|
| Net cash / 2 years | $1,824 | $2,031 | $2,195 |
| Funded breaches | 35% | 79% | 98% |
| Fees | $20.40 | $29.76 | $45.80 |

Even in the strict-floor regime, cash stays positive and a payout is still
reached on ~100% of paths. The breach rate rises only after the payout has
been taken.

---

## 12-13. Time and failure

| | 0.5% | 0.6% | 0.75% |
|---|---:|---:|---:|
| Median first payout | 219 d | 190 d | 157 d |
| 90th percentile | 330 d | 294 d | 254 d |
| Account failure (single attempt) | 0.05% | 0.16% | 0.87% |

Zero time limit makes the long qualification safe, but 7 months at 0.5%
is the real cost of the smaller size.

---

## 14. Conservative scenario

| Config | Survival | Net cash / attempt |
|---|---:|---:|
| 0.5% PR0 (no floor reset) | 99.968% | +$189 |
| 0.5% PR0 + 0.6 pips extra cost | 99.706% | +$187 |
| 0.5% PR0 + 0.5R floating pad | 99.972% | +$189 |
| 0.5% PR1, 4-week blocks | 99.982% | +$187 |
| 0.6% PR0 + 0.6 pips extra cost | 99.098% | +$219 |

Every stress keeps survival above 99% and cash positive.

---

## 15. Configuration table (all tested, no extrapolation)

| Config | Survival | Payouts | Net cash | First payout |
|---|---:|---:|---:|---:|
| 0.25% PR1 single | 99.972% | 1.00 | $133 | 423 d |
| 0.50% PR1 single | 99.952% | 1.00 | $189 | 219 d |
| 0.60% PR1 single | 99.836% | 1.00 | $224 | 190 d |
| 0.75% PR1 single | 99.134% | 1.00 | $277 | 157 d |
| 1.00% PR1 single | 95.838% | 1.00 | $360 | 127 d |
| 0.50% PR1 career | 99.998% | 9.91 | $1,966 | 220 d |
| 0.60% PR1 career | 99.998% | 10.76 | $2,487 | 190 d |
| 0.75% PR1 career | 99.998% | 11.52 | $3,270 | 161 d |
| 1.00% PR1 career | 100.000% | 12.11 | $4,533 | 129 d |
| 0.50% PR0 single | 99.968% | 1.00 | $189 | 220 d |
| 0.60% PR0 single | 99.794% | 1.00 | $223 | 190 d |
| 0.75% PR0 single | 99.178% | 1.00 | $269 | 157 d |
| 0.50% PR0 career | 99.992% | 9.25 | $1,824 | 220 d |
| 0.60% PR0 career | 99.998% | 8.92 | $2,031 | 190 d |
| 0.75% PR0 career | 99.998% | 8.08 | $2,195 | 161 d |
| 0.50% PR0 +0.6 pip single | 99.706% | 1.00 | $187 | 267 d |
| 0.60% PR0 +0.6 pip single | 99.098% | 1.00 | $219 | 231 d |
| 0.50% PR0 +0.5R pad single | 99.972% | 1.00 | $189 | 220 d |
| 0.50% PR1 bw4 single | 99.982% | 1.00 | $187 | 226 d |
| 0.75% PR1 bw4 single | 99.422% | 1.00 | $275 | 162 d |
| 0.50% PR1 bw4 career | 99.986% | 9.68 | $1,892 | 226 d |
| 0.75% PR1 bw4 career | 99.998% | 11.29 | $3,167 | 162 d |

---

## 16. Weaknesses

1. **The edge is in-sample.** Buffer 5 was chosen on 2024-2026. 2021-2024
   holds up, but the parameter is not independent of the data. No prop-rule
   result survives a dead edge.
2. **Time is the cost.** 7 months to first payout at 0.5%. A $200 payout
   every ~74 days on $5k is real money but not a living.
3. **0.75% is at the limit.** 0.95× closed, 0.99× with floating. One worse
   drawdown and the account is gone. Do not treat it as the safe size.
4. **1% is out.** It breaches 10% trailing on the actual 2021-2026 record
   (1.27×). No Monte Carlo can rescue that.
5. **Payout floor semantics.** PR0 costs 7-33% of net cash and multiplies
   funded breaches. The firm's post-payout trailing reset is still the one
   rule that matters most; take payouts manually and keep a $500 cushion.
6. **Costs.** The model charges 1.4 pips round trip against a real tick mean
   of 0.41. Conservative, but the recon's deploy gate (< ~1.1 pips all-in)
   still applies to the live broker.
7. **Swap not modelled.** 13% of trades are held > 8 h (max 24 h). Small,
   but non-zero on a 0.26-0.31 lot.
8. **Consistency rule.** Payouts land every ~74 days, not every 14, because
   a cycle must clear $111 gross and 3 qualifying days. Already modelled.
9. **Firm rule tails.** WaveStop (funded, −2% floating) cannot trigger at
   0.5% with 2 trades/day. News cap ≤ $25/cycle. Both immaterial here.
10. **Tick-scalping clause.** 0.9% of fills are under 2 min; median is 65.
    Not a scalping strategy by any reasonable reading.

---

## 17. Recommendation

Run **0.5% per trade** for the challenge and **0.5-0.6%** funded.

- 0.5%: 99.95% survival, 0.63× of the historical drawdown limit, $1,966
  per 2 years, 7 months to first payout.
- 0.6%: 99.84% survival, 0.76× limit, $2,487 per 2 years, 6 months to
  first payout. Best risk-adjusted choice.
- 0.75%: formally the highest payout that passes, but 5% of margin is not
  a margin.

Fees are irrelevant: $15 per attempt against a 99.96% pass rate. The
challenge is not the risk. The strategy and the wait are.

Reproduce: `python data/scratch/asia_choch_1m_moneycheck.py`
(`MC_PATHS=50000`). Outputs `moneycheck.csv`,
`moneycheck_history.json`, `trades_buffer5.csv`.

---

## 18. Addendum: what an 80%+ win rate costs (2026-11-24)

Question: how fast can the 2-step challenge be passed with a win rate above
80%, and at what risk?

An 80%+ win rate cannot be produced by the strategy as defined. It requires
cutting the take profit. The target rule "opposite Asia level" averages 1.49R;
a fixed 0.5R target produces 80.50% wins on the same 1,113 entries. Nothing
else changes: same Asia sweep, same CHoCH, same FVG entry, same stop, same
1.4-pip cost, same 1.05R live cap. Replay is barrier-by-barrier over each
trade's own holding window, stop wins intrabar ties (`fixed_tp_probe.py`).

| Take profit | Win rate | EV/trade | PF | Max DD | Net R |
|---|---:|---:|---:|---:|---:|
| Asia level (1.49R avg) | 61.90% | +0.3172R | 1.799 | 12.66R | +353.1 |
| 2.00R | 64.42% | +0.3106R | 1.838 | 9.26R | +345.7 |
| 1.50R | 67.12% | +0.2903R | 1.848 | 7.36R | +323.1 |
| 1.00R | 70.89% | +0.2020R | 1.667 | 6.84R | +224.8 |
| 0.75R | 74.39% | +0.1365R | 1.513 | 6.28R | +151.9 |
| 0.60R | 77.81% | +0.0989R | 1.430 | 6.46R | +110.1 |
| **0.50R** | **80.50%** | **+0.0699R** | **1.346** | **8.78R** | **+77.8** |
| 0.45R | 82.48% | +0.0605R | 1.334 | 10.23R | +67.4 |
| 0.40R | 84.19% | +0.0447R | 1.274 | 9.16R | +49.7 |
| 0.30R | 88.41% | +0.0160R | 1.134 | 13.02R | +17.8 |
| 0.25R | 90.66% | -0.0008R | 0.992 | 14.68R | -0.9 |

The 80% threshold sits exactly at 0.5R. Cutting from 1.49R to 0.5R removes
78% of the edge per trade (0.3172R to 0.0699R) and lifts the profit factor
from 1.799 to only 1.346.

### Pass time, 20,000 paths, 1,825-day horizon

| Config | Risk | Pass | Median | 90th pct | Hist DD vs $500 |
|---|---:|---:|---:|---:|---:|
| Asia target | 0.50% | 99.98% | 171 d | 273 d | 0.63x |
| Asia target | 0.60% | 99.86% | **142 d** | 233 d | 0.76x |
| Asia target | 0.75% | 99.34% | 114 d | 196 d | 0.95x |
| 0.5R TP (80.5%) | 0.50% | 98.54% | 751 d | 1213 d | 0.44x |
| 0.5R TP (80.5%) | 0.75% | 95.57% | 476 d | 829 d | 0.66x |
| **0.5R TP (80.5%)** | **1.00%** | **89.45%** | **331 d** | **596 d** | **0.88x** |
| 0.5R TP (80.5%) | 1.14% | 85.43% | 276 d | 506 d | 1.00x (no margin) |
| 0.5R TP (80.5%) | 1.50% | 76.44% | 185 d | 337 d | 1.32x FAIL |

### Answer

Fastest defensible 80%+ configuration: **1.0% per trade, median 331 days
(about 11 months), 90th percentile 596 days, pass probability 89.5%**.

The maximum risk is about **1.1%**, not because of the win rate but because
the 0.5R target lowers the R-multiple drawdown to 8.78R; 1.14% puts that
drawdown at exactly the $500 limit, leaving no margin.

### Why it is still the slower choice

Passing needs $750 of net profit. At 1.0% risk the 0.5R variant earns
$3.50 per trade, so it needs about 215 trades, roughly 1.1 years at the
190-trade annual cadence. The Asia-target strategy at 0.75% needs about 63
trades and passes in a median 114 days. Win rate is not a speed lever.
Expectancy per trade is.

### Fragility

Cost headroom collapses with the target. An extra 0.6 pips of round-trip cost
drops EV from +0.0699R to +0.0200R; an extra 1.0 pip makes it negative
(-0.0133R, PF 0.934). The Asia-target version survives about 3 pips of extra
cost before breakeven. A 0.5R target on a 10.8-pip stop leaves almost no room
for a worse broker.

### Caveats

1. The 0.5R level is selected on the same 2021-2026 record that measures it.
   Treat the win rate and pass times as optimistic.
2. The intrabar tie rule is pessimistic (stop first). Resolving ties in favour
   of the target gives 80.77% and +0.0736R, so the result is not an artefact.
3. This variant is a different strategy. It abandons the "target = opposite
   Asia level" rule, which is the stated definition of the setup.

Reproduce: `python data/scratch/fixed_tp_probe.py` and
`python data/scratch/pass_time_probe.py` (`PT_PATHS=20000`).
