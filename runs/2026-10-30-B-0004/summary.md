# B-0004: mistakes direction + row-vs-rating precedence, benchmark Austria (#35)

Addon `harness/addons/verve.b0004` (12 ops: 4 row + 8 curves; `db/b0004.json` sha256
`A4871679D716A986B4200D0BE4851F55EA2E3C0BD72A6ED9383471FB660646AD`), `harness/tests/b0004.test.json`:
5 fresh starts, benchmark Austria, 3 laps, 20 cars, clear. Run 2026-10-30 22:39 to 23:04 local, all 5 PASS, unattended.

**Pre-pause data excluded.** A first run was aborted by the PAUSE after 2 of 5 starts (comment on #35). Its logs are
kept locally in `pre-pause-excluded/` (not committed; raw logs are gitignored). As the supervisor directed, the verdict
uses only the 5 fresh starts.

Arms are per team (both drivers), chosen before the run (table in #35, edit 1). Ferrari (team 1, vehicles 8 and 19) is
excluded from the arms and the stock field. `arms.csv` has the team ids.

| Arm | Team (team_id) | Change |
|---|---|---|
| ROW_high | Alpine (5) | row `driver_characteristics.mistakes` → 0.95 |
| ROW_low | Aston Martin (4) | row `mistakes` → 0.05 |
| STATS_high | Racing Bulls (6) | awareness → flat 0.95 (default + 2026) |
| STATS_low | Williams (3) | awareness → flat 0.05 (default + 2026) |

## Isolation

Every start: **64 overwritten** (52 + 12), 322 created, 0 skipped (`isolation.csv`).

## Result: **ROW WINS (in benchmark)** by the criterion fixed in #35 (edit 2)

`tools/bootstrap_readout.ps1 -Mode pairs -By team_id -Exclude 1 -N 2000 -Seed 1`. Each sample is relative to its own
start's stock-field median.

| Metric | Gap | Estimate | Bootstrap SE | z | ≥ 2 SE |
|---|---|---|---|---|---|
| **race_start_performance** (primary) | ROW_high − ROW_low | **+7.79** | 3.39 | **+2.30** | **yes** |
| race_start_performance | STATS_high − STATS_low | +5.23 | 6.96 | +0.75 | no |
| reaction_time (secondary) | ROW_high − ROW_low | −0.014 s | 0.028 | −0.50 | no |
| reaction_time | STATS_high − STATS_low | +0.031 s | 0.026 | +1.21 | no |

Criterion: "Row wins if |ROW gap| ≥ 2 SE and |STATS gap| < 2 SE" → **row wins**. The ROW gap is positive: the
high-mistakes row (0.95) gets a higher `race_start_performance`. The scale's direction is still unknown, so whether that
means a *better* start is left to #8 (see Reading).

Per arm, relative to the same start's stock-field median (`arms_relative.csv`; 2 drivers × 5 starts = 10 samples):

| Arm | rsp median | rsp range | reaction median (s) | reaction range (s) |
|---|---|---|---|---|
| ROW_high | +3.94 | −2.64 … +11.09 | −0.028 | −0.068 … +0.093 |
| ROW_low | −3.84 | −22.28 … +14.43 | −0.014 | −0.118 … +0.090 |
| STATS_high | +3.62 | −14.71 … +16.33 | −0.001 | −0.060 … +0.083 |
| STATS_low | −1.61 | −16.47 … +13.04 | −0.032 | −0.070 … +0.053 |

CANNED_EVENTS lock-ups: **0 in every arm**. The channel was open (gate line in each `loader.log`), but no
CANNED_EVENTS line was logged in any of the 5 starts, so the benchmark start doesn't log lock-ups this way.

## Robustness: leave one start out

| Dropped start | ROW gap | z | STATS gap | z |
|---|---|---|---|---|
| 1 | +9.18 | 1.92 | +0.98 | 0.15 |
| 2 | +7.24 | 2.05 | −5.77 | −1.01 |
| 3 | +5.81 | 1.70 | +11.42 | 2.05 |
| 4 | +9.59 | 2.65 | +11.42 | 1.59 |
| 5 | +9.74 | 3.11 | −0.70 | −0.12 |

The ROW gap is positive in all five (+5.8 to +9.7). The STATS gap flips sign twice. With 4 starts the ROW gap falls
just under 2 SE in two of five drops (z 1.70 and 1.92), and the STATS gap reaches 2 SE once (drop 3). So the pass is
real but **marginal**: it counts as *supported*, in line with B-0006 (#39), and not as settled on its own.

## Reading

- **Precedence replicates on a second characteristic.** B-0006 found the row wins for `reaction_speed`. Here the row
  wins for `mistakes` on a different metric (`race_start_performance`), and the rating arm (awareness curve) shows no
  effect that clears its noise. Both batches say the same thing: in benchmark, the driver row is what the start reads.
- **Untouched source is balanced.** The ROW pair's stock curve mistakes are 0.61 / 0.57 (Alpine) vs 0.60 / 0.64
  (Aston), so the rating can't explain the ROW gap. The STATS pair's stock rows are 0.80 / 0.60 (Racing Bulls) vs
  0.70 / 0.80 (Williams), 0.05 apart on average, so "row wins" predicts a STATS gap near zero. Observed: +5.2 ± 7.0.
- **Reaction time doesn't move**, as expected: `mistakes` isn't an input to F-06's reaction formula. This is a useful
  negative control: the row edit changes the start's performance score without touching reaction.
- **Direction of `mistakes` (Q-03, F-29).** If a higher `race_start_performance` is a better start, the high-mistakes
  row starting better confirms "mistakes = skill" at runtime. The scale's sign is still unknown, so this stays
  conditional until #8 pins which way the scale points.
- **The awareness arms also move `control`** (awareness_control curve). This doesn't matter for a start readout, and
  the STATS arms showed no effect anyway.
- Benchmark only: Grand Prix and career are harness gaps 2-3 in `docs/harness.md`.

## Files

`summary.csv`, `per_vehicle.csv`, `per_start.csv`, `isolation.csv`, `racestarts_1..5.log`, `arms.csv`,
`arms_relative.csv`, `bootstrap_race_start_performance.csv`, `bootstrap_reaction_time.csv`.
