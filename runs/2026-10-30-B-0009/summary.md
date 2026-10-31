# B-0009: mistakes -> race start, ROW-only dose-response, 2 drivers per level (#45)

Addon `harness/addons/verve.b0009` (8 ops: row `driver_characteristics.mistakes`; seed 9009, accepted on draw 11;
`arms.csv`), `harness/tests/b0009.test.json`: 30 fresh starts, benchmark Austria, 3 laps, 20 cars, clear.
2026-10-31, all 30 PASS, unattended (~2.5 h). Ferrari (vehicles 8, 19) is excluded from the arms and the stock field.
Design as amended on #45 before the run (power): levels 0.02 / 0.35 / 0.65 / 0.98, 30 starts, expected z ≈ 2.8.

## Isolation

Every start: **60 overwritten** (52 + 8), 322 created, 0 skipped (`isolation.csv`).

## Result: **PASS. Row `mistakes` lowers the bad-start draw (benchmark)**

Criterion (#45, fixed before the run): slope of b_rel on level, |slope| ≥ 2 SE, and every leave-one-level-out slope
with the same sign. b = 1 − race_start_performance/100 (F-38), so slopes in b units are the performance slopes / −100.

`tools/bootstrap_readout.ps1 -Mode slope -By vehicle -Exclude 8,19 -Metric race_start_performance -N 2000 -Seed 1`:

| Statistic | Slope (b per unit) | Bootstrap SE | z |
|---|---|---|---|
| ROW slope, all 8 drivers | **−0.0590** | 0.0136 | **−4.3** |
| drop level 0.02 (tsunoda, sainz) | −0.0421 | 0.0218 | −1.9 |
| drop level 0.35 (bortoleto, alonso) | −0.0632 | 0.0154 | −4.1 |
| drop level 0.65 (lawson, hulkenberg) | −0.0607 | 0.0126 | −4.8 |
| drop level 0.98 (albon, antonelli) | −0.0615 | 0.0307 | −2.0 |

All four leave-one-level-out slopes are negative, so the criterion **passes**. Driver-level check (the 8 drivers'
mean b on level, SE from the 6 df between drivers, so a driver-specific quirk can't carry it): −0.059, SE 0.018,
t −3.3.

Per driver (30 starts; relative = minus that start's stock-field median):

| Level | Driver | Stock row | Median b rel. | Median b | Mean b |
|---|---|---|---|---|---|
| 0.02 | carlos_sainz-jr | 0.80 | +0.084 | 0.312 | 0.273 |
| 0.02 | yuki_tsunoda | 0.875 | +0.021 | 0.206 | 0.220 |
| 0.35 | fernando_alonso | 0.90 | −0.007 | 0.179 | 0.203 |
| 0.35 | gabriel_bortoleto | 0.70 | +0.023 | 0.221 | 0.221 |
| 0.65 | liam_lawson | 0.80 | +0.000 | 0.217 | 0.208 |
| 0.65 | nico_hulkenberg | 0.90 | −0.002 | 0.210 | 0.208 |
| 0.98 | alex_albon | 0.70 | −0.008 | 0.215 | 0.191 |
| 0.98 | andrea-kimi_antonelli | 0.60 | −0.030 | 0.161 | 0.180 |

## Start model check (F-39)

Fixed-intercept k (mean b = 0.24 − 0.08·k·m), pooled over the same 30 starts, bootstrapped over starts
(`analysis/b0009_extra.py`):

| Fit | k | SE |
|---|---|---|
| 8 tagged drivers (m = level) | 0.70 | 0.12 |
| stock field of the same starts (m = stock row) | 0.60 | 0.10 |
| difference | +0.10 | 0.14 (z 0.7) |
| reaction, all non-Ferrari cars | 0.51 | 0.014 |

The OLS slope −0.059 gives k ≈ 0.74 ± 0.17; the prediction from the earlier stock fit was −0.045 (k 0.56). Tagged
and stock cars agree, so the bad-start form of F-39 holds over m = 0.02-0.98, well outside the stock range
(0.51-0.90).

**Same k for both draws?** Per-start k from the two draws (all non-Ferrari cars, the tagged levels make the bad-start
k identifiable per start): corr −0.36 over 30 starts. One shared k would give at most about +0.17 (the reaction k
varies with sd 0.08, the bad-start estimate has sd 0.48). So there is no sign of a shared per-session k; the two
draws look independent per start (the stock-field fit gave −0.23). Not proven: n = 30 and the bad-start k is noisy.

## Surprise: `mistakes` also shortens the reaction time

Control, `-Metric reaction_time`: slope **−0.019 s per unit, SE 0.006, z −3.0**. After removing each car's predicted
reaction from its `reaction_speed` row (0.35 − 0.21·k·rs, k per start), the residual slope on level is
**−0.029 s per unit, SE 0.006, z −4.7**; driver level −0.029, SE 0.008, t −3.7. The adjustment makes it larger, not
smaller (the 0.65 pair has the lowest reaction_speed rows). It isn't carried by the bad-start draw: in the stock
field, b and the reaction residual are uncorrelated (r 0.05, 300 samples). The stock field points the same way:
reaction residual on stock row mistakes −0.047 (naive SE 0.023).

**Leave one level out (supervisor check on #50).** The raw slope is fragile: −0.014 / −0.023 / −0.024 / **−0.004**
dropping 0.02 / 0.35 / 0.65 / 0.98 (`slope_lolo_reaction_time.csv`). Without the 0.98 pair, the 0.65 pair becomes the
top level, and it has the slowest stock reaction_speed rows (lawson 0.60, hulkenberg 0.80), which flattens the raw
slope. The rs-adjusted slope holds: −0.024 / −0.031 / −0.031 / −0.028, z −1.9 / −4.3 / −4.5 / −2.3
(`analysis/b0009_rt_lolo.py`). The adjustment is a post-hoc model over 8 drivers, so this stays a candidate; B-0010
(crossed reaction_speed × mistakes, pre-registered) settles it.

If it holds, F-39's reaction form (reaction_speed only) is incomplete. A row `mistakes` of 1 takes about 0.03 s off the
reaction, a quarter of what reaction_speed does (−0.118 s per unit, B-0008). B-0004 and B-0007 didn't detect it
(z −0.5, and B-0007 pinned b, not mistakes); this is the first batch with the power to. New finding F-40,
**candidate**: one batch, benchmark only, and the form (an extra term in the reaction bounds, or a combined skill)
is unknown.

## Reading

- **F-37 replicates as a dose-response.** Raising row `mistakes` lowers b at about the rate F-39 predicts, with no
  single level or driver carrying it. The weakest drop (level 0.02, z −1.9) still keeps the sign. Sainz's high b is
  +1.8 SE from the model's mean; the 0.02 level as a whole (0.247) matches the prediction (0.239).
- **Mistakes = skill** (F-29) for the start draw: a higher row value gives smaller bad-start values and, it now
  seems, quicker reactions. Whether b costs time on track is still #4.
- **v0.2a:** writing row `mistakes` moves both start draws. Profiles that set it for racecraft reasons change the
  start too, by up to ~0.08·k ≈ 0.05 in b and ~0.03 s in reaction across the full range.
- A fail was possible (power ≈ 80%); it didn't happen.
- Benchmark only: Grand Prix and career are harness gaps 2-3 in `docs/harness.md`.

## Files

`summary.csv`, `per_vehicle.csv`, `per_start.csv`, `isolation.csv`, `racestarts_1..30.log`, `arms.csv`,
`slope_race_start_performance.csv`, `slope_lolo_race_start_performance.csv`, `slope_reaction_time.csv`,
`analysis/` (the three Python checks and their `output.txt`; each takes one folder holding `summary.csv`, `arms.csv`
and `docs/stock/driver_rows_benchmark_austria.csv`).
