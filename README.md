# SMC buffer — Asia sweep → CHoCH → FVG on EURUSD 1m

EURUSD 1-minute intraday model. The Asia session high/low is swept, market
structure shifts the other way, and the first fair value gap on the shift leg
is the entry. Stop sits beyond the sweep extreme plus a **5-pip buffer**.
Target is the opposite Asia level. Sizing is fixed-fractional and the
deliverable is a prop-firm qualification study on AquaFunded 2 Step Pro
$5,000.

## Rules

| Item | Value |
|---|---|
| Pair / timeframe | EURUSD, 1m |
| Asia session | 20:00–00:00 America/New_York |
| Sweep | wick through Asia high/low, close back inside |
| Max penetration | 10 pips |
| Shift | `smc.bos_choch(close_break=True)` beyond last confirmed opposing swing |
| Entry | first FVG on the shift leg, proximal edge, limit live next bar |
| Stop | sweep extreme ± 5 pips (`STOP_BUFFER_PIPS`) |
| Target | opposite Asia level |
| Live stop cap | 1.05R (broker risk on a stop is at most 1.05R) |
| Costs | 1.0 pip spread + 0.2 pip slippage = 1.4 pips round trip |

Session and structure detection use
[`smartmoneyconcepts`](https://github.com/joshyattridge/smart-money-concepts).
`METHOD.md` lists every rule, default and unresolved fork.

## Results, 2021-01-01 → 2026-11-17

1,649 setups, 1,174 fills, 1,113 trades on the buffer-5 variant.

| Metric | Value |
|---|---:|
| Net | +353.05R |
| EV per trade | +0.3172R (+2.69 pips) |
| Win rate | 61.90% |
| Profit factor | 1.799 |
| Max drawdown (closed) | 12.66R |
| Max losing streak | 7 |
| Median hold | 65 min |

Prop-firm economics (AquaFunded 2 Step Pro, $5,000, 50,000 bootstrap paths):

| Risk | Pass rate | Median days to pass | Net cash / 2 yr | Historical DD vs $500 |
|---:|---:|---:|---:|---:|
| 0.50% | 99.97% | 175 | $1,966 | 0.63× |
| 0.60% | 99.85% | 143 | $2,487 | 0.76× |
| 0.75% | 99.35% | 113 | $3,270 | 0.95× |
| 1.00% | 97.1% | 84 | n/a | 1.27× fail |
| 1.75% | 84.2% | 42 | n/a | 2.22× fail |

Recommendation: **0.5–0.6% per trade**. Every size that reaches an 80% pass
rate breaches the firm's 10% trailing drawdown on the actual record.
Full discussion in `MONEYCHECK.md`; year-by-year tables in `FINDINGS.md`.

## Reproduce

Data: EURUSD M1, 2010-01-01 → 2026-11-17, 6,234,609 bars, read from
`aqua/cache/eurusd_m1_clean.parquet` with columns `dt, open, high, low,
close`. That file is not in this repo. Point `PATH` in
`asia_choch_1m_proto.py` at your own copy.

```
pip install -r requirements.txt

# full prop-firm grid, 50k paths (uses data/trades_buffer5.csv)
set ASIA_OUT=data
python asia_choch_1m_moneycheck.py
```

Results go to `ASIA_OUT/moneycheck.csv` and `ASIA_OUT/moneycheck_history.json`;
the committed copies are in `results/`.

Regenerate the trade log from raw bars (needs the parquet, ~1,530 sessions):

```
set ASIA_START=2021-01-01
set ASIA_END=2026-11-18
set ASIA_OUT=data
python asia_choch_1m_run.py
```

`asia_choch_1m_risk_sweep.py` reproduces the risk-vs-pass-rate table above.

## Layout

```
asia_choch_1m_proto.py        session/sweep/CHoCH/FVG detection
asia_choch_1m_sensitivity.py  bars container, order construction
asia_choch_1m_exact.py        exact fill simulation (buffer, 1.05R cap)
asia_choch_1m_run.py          end-to-end run + base report
asia_choch_1m_moneycheck.py   prop-firm Monte Carlo (numba)
asia_choch_1m_risk_sweep.py   risk size vs pass rate / time to pass
strategies/ict_baseline/      shared simulator, config, stats
data/trades_buffer5.csv       1,113 fills
results/                      moneycheck outputs
```

## Caveats

- The 5-pip buffer was selected on 2024–2026. The prop study is in-sample
  with respect to that choice.
- No lookahead: orders are created on the signal bar and filled from the next
  bar. Nothing repaints.
- Swap is not modelled. 13% of trades are held over 8 hours (max 24 h).
- The payout model assumes the trailing floor resets after a withdrawal.
  `MONEYCHECK.md` also reports the strict-floor variant.
