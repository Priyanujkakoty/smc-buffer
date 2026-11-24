# Asia sweep -> CHoCH -> first FVG, 1m EURUSD

## Source rules

1. Mark Asia high and low.
2. After Asia closes, wait for a sweep of either level. Sweep = wick through
   and close back inside. Penetration beyond the level must be <= 10 pips.
3. CHoCH confirms the opposite direction.
4. Enter the first FVG formed on the 1m CHoCH leg.
5. Stop beyond the sweep extreme.
6. Target the opposite Asia level.

## Library policy

Every concept that exists in `smartmoneyconcepts` is taken from that package:

| Concept | Call |
|---|---|
| Asia session high/low | `smc.sessions(..., "Custom", "20:00", "00:00")` per session |
| Swings | `smc.swing_highs_lows(ohlc, swing_length=2)` |
| CHoCH | `smc.bos_choch(..., close_break=True)` |
| FVG | `smc.fvg(ohlc, join_consecutive=False)` |

Our code is used only for data loading, the sweep wrapper, the causal CHoCH
window, order construction, the fill simulator and the report. Those are not
in the SMC repo.

## Lookahead control

- Asia high/low is registered only after the session closes.
- `smc.swing_highs_lows` and `smc.bos_choch` are recomputed on a rolling
  180-bar window ending at the decision bar, so a CHoCH is only used once the
  four-swing pattern is inside the window.
- `smc.fvg` is causal at C3 close; the future `MitigatedIndex` column is
  ignored.
- The FVG order goes live on the bar after C3 closes.

## Defaults not fixed by the source

| Dial | Default | Why |
|---|---:|---|
| Asia window | 20:00-00:00 NY | Tokyo session, same as the existing flow model |
| Max sweep penetration | 10 pips | source |
| Sweep confirmation | close back inside | standard sweep definition |
| Swing length | 2 bars | 1m chart; repo default 50 is too slow |
| CHoCH search | 30 bars after sweep | source says "confirms", no clock |
| CHoCH window | 180 bars | 3h of 1m context |
| First FVG wait | 10 bars after CHoCH | "first FVG on the leg" |
| Entry | limit at proximal FVG edge | "enter the FVG"; long buys the gap top, short sells the gap bottom |
| Entry expiry | 30 bars | no source clock; 15/30/60 tested identical |
| Stop buffer | 0.0 pip | literal "beyond the sweep extreme" |
| Live stop cap | 1.05R | broker test: a 1R stop loses at most 1.05R |
| Max hold | 1440 bars (24h) | no source exit |
| Costs | 1.0 pip spread + 0.2 pip slippage/side | same as other tests |
| Risk | 0.25% initial balance per R | reporting convention |

## Implementation notes

- The FVG check uses the C3 close, not the CHoCH close. Testing the gap
  against the CHoCH close rejected most valid setups (108 vs 516).
- The proximal edge is where the gap starts. For a bullish FVG that is the
  low of C3, so the limit fills on the next bar in most cases. That is why
  entry expiry (15/30/60 bars) changes nothing.
- Results: `data/scratch/asia_choch_1m/FINDINGS.md`.

## Forks to test

- Asia window: 20:00-00:00 vs 00:00-08:00 NY.
- Penetration cap: 5 / 10 / 20 pips.
- Swing length: 2 / 3 / 5.
- Stop buffer: 0 / 1 pip.
- Entry expiry: 15 / 30 / 60 bars.
