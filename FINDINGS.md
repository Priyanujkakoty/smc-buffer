# Asia sweep -> CHoCH -> first FVG, 1m EURUSD, 2021-2026

Window: 2021-01-01 .. 2026-11-17. 1,529 Asia sessions, 2,161,919 one-minute
bars. Same rules as the earlier literal-stop run (`METHOD.md`). Live stop cap
1.05R. Costs 1.4 pips round trip.

## Headline

| Metric | Literal + cap | 5-pip buffer + cap | Sweep-only + cap |
|---|---:|---:|---:|
| Trades | 1,174 | 1,113 | 1,140 |
| Win rate | 37.5639% | 61.9048% | 56.84% |
| EV / trade | +0.207686R | +0.317208R | +0.7782R |
| EV in pips | **+0.0313** | **+2.6935** | **+4.77** |
| EV in $ (0.25% of $10k) | +$5.19 | +$7.93 | +$19.46 |
| Profit factor | 1.317227 | 1.798601 | 2.717 |
| Total | +243.82R | +353.05R | +887.14R |
| Max drawdown | -19.98R | -12.66R | -12.52R |
| SD per trade | 2.154R | 1.248R | — |
| t-stat | 3.30 | 8.48 | 14.35 |

Reference, literal rules with no cap: -37.19R, PF 0.965, t = -0.47,
+0.03 pips per trade.

Trades per day:

| Basis | Literal | Buffer 5 |
|---|---:|---:|
| Per Asia session (1,529) | 0.7678 | 0.7279 |
| Per calendar day (2,147) | 0.5468 | 0.5184 |
| Per week | 3.8277 | 3.6288 |
| Per active day (769 / 767) | 1.5267 | 1.4511 |
| Max in one day | 2 | 2 |

## Year by year

Literal + cap:

| Year | n | Win % | Mean R | Sum R | PF |
|---:|---:|---:|---:|---:|---:|
| 2021 | 200 | 34.0 | +0.241 | +48.2 | 1.35 |
| 2022 | 237 | 39.2 | +0.285 | +67.6 | 1.45 |
| 2023 | 193 | 42.5 | +0.206 | +39.8 | 1.34 |
| 2024 | 187 | 39.0 | +0.083 | +15.6 | 1.13 |
| 2025 | 183 | 36.6 | +0.191 | +34.9 | 1.29 |
| 2026 | 174 | 33.3 | +0.218 | +37.9 | 1.31 |

5-pip buffer + cap:

| Year | n | Win % | Mean R | Sum R | PF |
|---:|---:|---:|---:|---:|---:|
| 2021 | 186 | 61.3 | +0.312 | +58.1 | 1.78 |
| 2022 | 227 | 56.4 | +0.308 | +70.0 | 1.67 |
| 2023 | 186 | 65.6 | +0.313 | +58.3 | 1.88 |
| 2024 | 181 | 66.9 | +0.251 | +45.4 | 1.73 |
| 2025 | 174 | 57.5 | +0.292 | +50.9 | 1.65 |
| 2026 | 159 | 65.4 | +0.443 | +70.4 | 2.22 |

Every year positive for both. 2022, a trend year, is not the weak spot.

## Tail dependence

Literal + cap: trim top 5% (59 trades) -> -0.1572R mean. The positive mean
still depends on a small set of large winners.

5-pip buffer + cap: trim top 5% -> +0.1683R; trim top 10% -> +0.0589R. Still
positive after removing 111 winners.

## Direction

Literal + cap: long +75.04R over 577, short +168.78R over 597.

## Funnel

| Stage | Count |
|---|---:|
| Asia sessions | 1,529 |
| Sweeps | 9,012 |
| CHoCH confirmed | 3,143 |
| Setups (first FVG) | 1,649 |
| Filled | 1,174 |

## What changed versus the 2024-2026 run

Nothing structural. The confirmation layer still subtracts value: sweep-only
at a 5-pip buffer earns +4.77 pips per trade against +2.69 for the full
sequence. The literal stop is still a coin flip in price terms; its positive R
comes from the 1.05R cap on sub-2-pip stops.

The buffer result is the only one that survives both the longer sample and the
tail trim. It is also the only one whose R and pip results agree.

## Caveats

- One pair. EURUSD only.
- The 5-pip buffer was selected on 2024-2026. 2021-2024 is out of sample for
  that choice and holds up, but the parameter is not independent of the data.
- Costs are a flat 1.4 pips; real tick mean is 0.41.
- Stop cap 1.05R is only physical when the stop is wider than the round trip.
- No swap, commission, news spread spikes, or partial fills.
- Max losing streak: 10 trades.

## Moneycheck (2026-11-24)

AquaFunded 2 Step Pro , 50,000 paths, weekly block bootstrap.

- 0.5%/trade: survival 99.952%, historical DD 0.633x of the $500 limit,
  net cash +$1,966 per 2 years, median first payout 219 days.
- 0.6%/trade: survival 99.836%, DD 0.760x, +$2,487, 190 days.
- 0.75%/trade: survival 99.134%, DD 0.950x (0.99x with floating), +$3,270.
- 1.0%/trade: DD 1.266x, disqualified by the historical hard-limit check.

Full report: data/scratch/asia_choch_1m_2021/MONEYCHECK.md.
