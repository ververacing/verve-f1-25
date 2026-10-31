# Start model: reaction and bad-start draws vs driver rows, stock field (F-39)

An analysis of existing runs, with no new game starts. `tools/fit_start_model.ps1` pools every **stock** car from
B-0001, B-0003, B-0004, B-0005, B-0006, B-0007 and B-0008. In each batch, every car that batch modified is left out,
and so is Ferrari (vehicles 8, 19). That gives 368 samples from 33 starts. Stock rows for all 20 cars come from
read-only `swofty db get`: `docs/stock/driver_rows_benchmark_austria.csv`.

## Model

Both draws have the same form. Each min/max bound pair moves from its upper toward its lower bound by t = k·(row
skill), with the stock bounds from `docs/stock/ai_driver_config.csv`:

| Draw | Bounds (stock) | Model |
|---|---|---|
| reaction r (F-06) | min 0.04 / 0.28, max 0.24 / 0.42 | r ~ U[0.28 − 0.24·k·rs, 0.42 − 0.18·k·rs], mean 0.35 − 0.21·k·rs |
| bad start b (F-38) | min 0.04 / 0.06, max 0.28 / 0.42 | b ~ U[0.06 − 0.02·k·m, 0.42 − 0.14·k·m], mean 0.24 − 0.08·k·m |

Here rs is row `reaction_speed`, m is row `mistakes`, and b = 1 − race_start_performance/100.

## Fit

| | Estimate | Bootstrap SE (over starts) |
|---|---|---|
| k from reaction (intercept fixed at 0.35) | **0.529** | 0.015 |
| k from bad start (intercept fixed at 0.24) | **0.520** | 0.067 |

**One pooled k ≈ 0.52 fits both draws.** It also matches the tagged-driver slopes: B-0006 0.52 and B-0008 0.56
(reaction), and B-0004's ROW gap, which is 1.1 SE above the model's +4.0 perf.

Bad-start edges and means by row-mistakes bin, observed vs the model at k = 0.52:

| m bin | n | observed min / max / mean b | model at the bin's mean m: interval, mean |
|---|---|---|---|
| 0.50-0.66 | 104 | 0.060 / 0.371 / 0.216 | m 0.60: U[0.054, 0.377], 0.215 |
| 0.66-0.76 | 109 | 0.065 / 0.364 / 0.211 | m 0.71: U[0.053, 0.368], 0.210 |
| 0.76-0.86 | 72 | 0.052 / 0.357 / 0.212 | m 0.81: U[0.052, 0.361], 0.206 |
| 0.86-1.00 | 83 | 0.054 / 0.356 / 0.198 | m 0.89: U[0.051, 0.355], 0.203 |

- No sample lies outside the k ∈ [0, 1] envelope of either draw. 357 of 368 bad-start values lie inside their own
  start's fitted interval, to within ±0.01.
- **Direction in the stock field alone:** the free OLS fit is b = 0.256 − 0.062·m (SE 0.039, z −1.6). It points the
  same way as B-0004 (higher mistakes → lower b), but **not at 2 SE**. Without B-0008 it was −0.112 (z −2.7), so it
  is sensitive to which drivers are in the pool. The stock spread of m (0.51-0.90) is narrow, which is what B-0009's
  0.02-0.98 levels are for.

## Open

- **Same per-session k for both draws?** Not shown. k from reaction varies by start (sd 0.10) more than its noise.
  k from bad start per start isn't identifiable (sd 0.40, about the sampling noise of 10-18 uniform draws of width
  0.3), and the two don't correlate over starts (r −0.23). Only the pooled values agree.
- **Whether b costs time at the start** is behavioural (#4).
- Benchmark only.

## Use

#6 and #10 get E[reaction] and E[b] as functions of the row values and the bounds:
E[r] = (lo_r + hi_r)/2 and E[b] = (lo_b + hi_b)/2, where each edge = upper bound − (upper − lower)·k·skill, with k ≈ 0.52.

## Files

`start_model_samples.csv` (one row per stock sample), `start_model_per_start.csv` (k per start from each draw),
`fit_output.txt`.
