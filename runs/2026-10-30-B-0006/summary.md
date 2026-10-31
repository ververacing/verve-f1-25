# B-0006: reaction dose-response, row vs rating, per driver, benchmark Austria (#39)

Addon `harness/addons/verve.b0006` (12 ops; seed 6006 assignment in `arms.csv`), `harness/tests/b0006.test.json`:
6 fresh starts, benchmark Austria, 3 laps, 20 cars, clear. 2026-10-30, all 6 PASS, unattended.
Vehicle ids from B-0005's map (#37); Ferrari (vehicles 8, 19) excluded from the arms and the stock field.

## Isolation

Every start: **64 overwritten** (52 + 12), 322 created, 0 skipped (`isolation.csv`).

## Result: **ROW WINS (in benchmark)** by the criterion fixed in #39

`tools/bootstrap_readout.ps1 -Mode slope -By vehicle -Exclude 8,19 -N 2000 -Seed 1` → `slopes.csv`:

| Source | Slope of reaction_rel on level (s per unit) | Bootstrap SE | z | Criterion ("negative and ≥ 2 SE") |
|---|---|---|---|---|
| ROW (driver row `reaction_speed`) | **−0.1087** | 0.0236 | −4.6 | **passes** |
| STATS (racecraft rating, default + 2026) | **+0.0683** | 0.0286 | +2.4 | does not pass (positive) |

Criterion: "Row wins: the ROW slope passes and the STATS slope doesn't." → **row wins in benchmark**.

Per level (`levels.csv`; median of 6 samples relative to that start's stock-field median):

| Source | Level | Driver (vehicle) | Stock row | Stock curve | Median rel. | Median abs. |
|---|---|---|---|---|---|---|
| ROW | 0.05 | lando_norris (12) | 0.81 | 0.89 | +0.036 | 0.313 |
| ROW | 0.35 | george_russell (18) | 0.90 | 0.92 | +0.060 | 0.325 |
| ROW | 0.65 | esteban_ocon (10) | 1.00 | 0.86 | +0.013 | 0.295 |
| ROW | 0.99 | yuki_tsunoda (0) | 0.79 | 0.78 | −0.065 | 0.205 |
| STATS | 0.05 | fernando_alonso (9) | **1.00** | 0.90 | −0.075 | 0.192 |
| STATS | 0.35 | nico_hulkenberg (13) | 0.80 | 0.86 | +0.010 | 0.279 |
| STATS | 0.65 | pierre_gasly (16) | 0.89 | 0.88 | −0.006 | 0.257 |
| STATS | 0.99 | lance_stroll (3) | **0.60** | 0.81 | +0.013 | 0.280 |

## Reading

- **Effect size.** The ROW slope (−0.109 s per unit of reaction_speed) matches F-06's formula with k ≈ 0.52: the mean
  is 0.35 − 0.21·k·r, so d(mean)/dr = −0.21k. That fits the k ≈ 0.5 fitted from B-0003's stock field. B-0001's
  half-size effect (F-35) now looks like noise from team-averaged arms, not a second input.
- **The positive STATS slope is the row talking.** The STATS drivers' untouched *row* values run against their
  levels: Alonso (rating 0.05, row 1.00) was the fastest of the four, Stroll (rating 0.99, row 0.60) among the
  slowest. The regression of their stock row on level is −0.36 per unit, so "row wins" predicts a STATS slope of about
  −0.109 × −0.36 = **+0.039**. Observed +0.068 ± 0.029, within ~1 SE. A stronger design would match stock rows across
  the STATS levels; this one wasn't built to, so the STATS slope reads as confounded, not as a rating effect.
- **Q-17, in benchmark: the driver row's `driver_characteristics.reaction_speed` drives the start reaction; the
  racecraft rating (through `racecraft_reaction_speed`) shows no effect of its own.** For #6 that means writing driver
  rows, as v0.1 does, works in benchmark. Grand Prix and career are unconfirmed (harness gaps 2 and 3).
- Vehicle 19 again: 0.196, 0.115, 0.062, 0.083, 0.119, 0.122 s.
