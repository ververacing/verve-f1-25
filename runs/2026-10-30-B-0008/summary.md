# B-0008: row precedence replication, ROW-only dose-response, 2 drivers per level (#43)

Addon `harness/addons/verve.b0008` (8 ops: row `driver_characteristics.reaction_speed`; seed 8008, accepted on draw 59;
`arms.csv`), `harness/tests/b0008.test.json`: 6 fresh starts, benchmark Austria, 3 laps, 20 cars, clear.
2026-10-30, all 6 PASS, unattended. Ferrari (vehicles 8, 19) is excluded from the arms and the stock field. The stock
racecraft curve doesn't correlate with level (r = −0.14), so the untouched source can't fake a slope.

## Isolation

Every start: **60 overwritten** (52 + 8), 322 created, 0 skipped (`isolation.csv`).

## Result: **PASS. Row precedence for reaction_speed replicates (benchmark)**

Criterion (#43): slope of reaction_rel on level < 0 and ≥ 2 SE, and every leave-one-level-out slope negative.

`tools/bootstrap_readout.ps1 -Mode slope -By vehicle -Exclude 8,19 -N 2000 -Seed 1`:

| Statistic | Slope (s per unit) | Bootstrap SE | z |
|---|---|---|---|
| ROW slope, all 8 drivers | **−0.1177** | 0.0173 | **−6.8** |
| drop level 0.05 (ocon, bearman) | −0.0999 | 0.0357 | −2.8 |
| drop level 0.35 (stroll, bortoleto) | −0.1197 | 0.0149 | −8.0 |
| drop level 0.65 (norris, hulkenberg) | −0.1144 | 0.0194 | −5.9 |
| drop level 0.99 (piastri, hadjar) | −0.1411 | 0.0192 | −7.4 |

All four leave-one-level-out slopes are negative, so the criterion **passes**.

Per driver (median of 6 starts, relative to that start's stock-field median):

| Level | Driver | Stock row | Median rel. (s) | Median abs. (s) |
|---|---|---|---|---|
| 0.05 | oliver_bearman | 0.65 | +0.110 | 0.356 |
| 0.05 | esteban_ocon | 1.00 | +0.105 | 0.354 |
| 0.35 | gabriel_bortoleto | 0.70 | +0.073 | 0.337 |
| 0.35 | lance_stroll | 0.60 | +0.045 | 0.296 |
| 0.65 | nico_hulkenberg | 0.80 | −0.009 | 0.228 |
| 0.65 | lando_norris | 0.81 | +0.043 | 0.298 |
| 0.99 | oscar_piastri | 0.73 | +0.003 | 0.255 |
| 0.99 | isack_hadjar | 0.60 | −0.049 | 0.210 |

## Reading

- **Replicates B-0006 with no single car carrying it.** B-0006's slope was −0.109 and rested mostly on Tsunoda. Here,
  with two drivers per level and a new assignment, it is −0.118, z −6.8, and dropping any level leaves it between
  −0.100 and −0.141.
- **Effect size matches F-06.** The mean reaction is 0.35 − 0.21·k·r, so the slope −0.118 gives **k ≈ 0.56**.
  B-0006 gave 0.52, the stock-field fit 0.52 (`tools/fit_start_model.ps1`), and B-0003 about 0.5.
- **Control: `race_start_performance` doesn't move with reaction_speed.** Slope +2.18 perf per unit, SE 1.84,
  z +1.2. The bad-start draw doesn't depend on reaction_speed, consistent with F-38 / the start model (it depends on
  `mistakes`).
- Benchmark only: Grand Prix and career are harness gaps 2-3 in `docs/harness.md`.

## Files

`summary.csv`, `per_vehicle.csv`, `per_start.csv`, `isolation.csv`, `racestarts_1..6.log`, `arms.csv`,
`slope_reaction_time.csv`, `slope_race_start_performance.csv`.
