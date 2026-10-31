# B-0007: bad-start bounds and the Race Start performance scale, benchmark Austria (#41)

Addon `harness/addons/verve.b0007` (32 ops: all four `ai_driver_config.race_start` bad-start bounds pinned per driver;
seed 7007 assignment in `arms.csv`), `harness/tests/b0007.test.json`: 4 fresh starts, benchmark Austria, 3 laps,
20 cars, clear. 2026-10-30, all 4 PASS, unattended. Ferrari (vehicles 8, 19) is excluded from the arms and the stock
field.

## Isolation

Every start: **84 overwritten** (52 + 32), 322 created, 0 skipped (`isolation.csv`).

## Result: **the bad-start bounds set the metric exactly: `race_start_performance` = 100 × (1 − bad-start value)**

Every tagged driver's value is **pinned** (identical on all 4 starts), and it equals 100 × (1 − level):

| Level (all 4 bounds) | Drivers (vehicle) | race_start_performance, starts 1-4 |
|---|---|---|
| 0.01 | carlos_sainz-jr (4), liam_lawson (11) | 99, 99, 99, 99 |
| 0.15 | alex_albon (1), andrea-kimi_antonelli (7) | 85, 85, 85, 85 |
| 0.35 | lance_stroll (3), franco_colapinto (17) | 65, 65, 65, 65 |
| 0.60 | lando_norris (12), george_russell (18) | 40, 40, 40, 40 (39.999996) |

Criterion (#41): bootstrap slope of performance_rel vs level, |slope| ≥ 2 SE → the bounds drive the metric; report the
sign. `tools/bootstrap_readout.ps1 -Mode slope -By vehicle -Exclude 8,19 -Metric race_start_performance`: slope
**−100 per unit**, bootstrap SE 0 (the tagged values don't vary). **Passes; the sign is negative**: a higher bad-start
value gives a lower `race_start_performance`.

The stock field fits the same picture. Across B-0004, B-0006 and B-0007, stock cars score 60.3 to 94.8, which is
bad-start values of about 0.05 to 0.40. The stock bounds are min 0.04 / 0.06 and max 0.28 / 0.42
(`docs/stock/ai_driver_config.csv`).

## What the metric means

- `race_start_performance` is **not** an outcome measure. It is the start's drawn bad-start value, logged as
  100 × (1 − value), so 100 = no bad start.
- **Direction:** a higher `race_start_performance` means a smaller bad-start value. If the bad-start value is the
  penalty its name says, then higher = better start. Benchmark gives no position or launch data that could confirm
  this behaviourally; UDP (#4) could.
- **B-0004 (F-37) through this lens.** Row `mistakes` 0.95 vs 0.05 raised the metric by about 7.8, so it lowered the
  drawn bad-start value by about 0.078. Under the reading above, that is a better start for the higher value, so
  `mistakes` is a skill (higher = fewer mistakes), which matches F-29's static decode.
- Equal bounds pin the value, as they did for the reaction bounds (F-33). For #10 this means each AI driver's bad-start
  range can be set directly. A shipping profile should give a range, not a single value, or every start comes out the
  same.

## Reaction time (control): no robust effect

The slope of reaction_rel on level is −0.055 s per unit (SE 0.015, z −3.6), which nominally passes. But it doesn't hold
up:

- **Confounded with the row.** The tagged drivers' stock row `reaction_speed` (read-only `swofty db get`) is
  0.90 / 0.60 at level 0.01, 0.81 / 0.77 at 0.15, 0.60 / 0.72 at 0.35 and 0.81 / 0.90 at 0.60. Its slope on level
  is +0.11, so the row alone predicts about −0.109 × 0.11 = −0.012 s per unit (F-36).
- **Rests on one driver.** Leave-one-driver-out slopes range from −0.028 to −0.077. Dropping liam_lawson (level 0.01,
  row 0.60, median +0.062 s slower than the field) halves the slope, to −0.028 (z −1.4). With only 4 starts the SE is
  unstable: dropping Norris gives z −15.5, which is a bootstrap artefact.

So this batch doesn't show that the bad-start bounds move reaction time. B-0009's reaction control (#45) will check it
again.

## Files

`summary.csv`, `per_vehicle.csv`, `per_start.csv`, `isolation.csv`, `racestarts_1..4.log`, `arms.csv`,
`slope_race_start_performance.csv`, `slope_reaction_time.csv`.
