# B-0010: crossed reaction_speed x mistakes (#51)

Benchmark, Austria, 3 laps, 20 cars, 20 starts (all pass, 4 m 51 s to 4 m 54 s each). Addon `verve.b0010` writes
row `reaction_speed` and `mistakes` for 8 drivers, two per cell of a 2 x 2 design (levels 0.10 / 0.90, assignment
seed 10010, draw 51; `arms.csv`). Ferrari (vehicles 8, 19) excluded. Each armed car's sample is its draw minus the
median of the same start's stock field. SE = bootstrap over whole starts (2000 resamples, seed 1).
Readout: `tools/b0010_readout.py`, output in `readout.txt`.

## Verdict (criterion fixed on #51 before the run)

**F-40 REJECTED.** The positive control passes; the mistakes effect on reaction time is +0.007 s, with a 2-SE
interval [-0.007, +0.021] s that excludes the -0.015 s the criterion tests (F-40's B-0009 estimate across this
range: about -0.023 s).

| Effect (0.90 minus 0.10) | Reaction time (s) | Bad-start draw b |
|---|---|---|
| reaction_speed main | **-0.086** (SE 0.008, z -10.9) | -0.018 (SE 0.014, z -1.3) |
| mistakes main | +0.007 (SE 0.007, z 1.0) | **-0.060** (SE 0.011, z -5.4) |
| interaction | +0.007 (SE 0.014) | +0.001 (SE 0.030) |

Cell means (relative to the stock-field median):

| Cell | Reaction (s) | b |
|---|---|---|
| rs 0.10, m 0.10 | +0.067 | +0.038 |
| rs 0.10, m 0.90 | +0.071 | -0.022 |
| rs 0.90, m 0.10 | -0.023 | +0.019 |
| rs 0.90, m 0.90 | -0.012 | -0.040 |

## Against the start model (F-39)

- Reaction: F-39 predicts mean 0.35 - 0.21 k rs, so -0.087 s for this rs step at k = 0.52. Observed -0.086 s.
  reaction_speed alone moves reaction; mistakes doesn't.
- Bad start: F-39 predicts mean 0.24 - 0.08 k m, so -0.033 at k = 0.52. Observed -0.060 +- 0.011, an implied k of
  0.93 +- 0.17 for written rows (B-0009's tagged drivers: 0.70 +- 0.12). Written-row bad-start k keeps coming out
  above the stock-field 0.52; the form holds, the scale for written rows is larger.
- Neither draw shows a cross term: rs doesn't move b (z -1.3), and no interaction.

## Isolation

Every start: `gamedb: 68 overwritten, 322 created` = the 52-record baseline + all 16 B-0010 writes. The 16 float
overwrites in `loader.log` are exactly the 16 ops. One of them is Sainz `reaction_speed 0.9 -> 0.9`: the write
equals stock and was still counted. The pre-run expectation of 67 assumed equal writes are dropped (as in the v0.1
sample, `docs/harness.md`); that assumption was wrong here. The analysis ran with `-ExpectOverwritten 68` after the
overwrite list was checked by hand.

## Saves

Tyler's save folder (`Steam\userdata\<steamid>\3059520\remote`, 10 files) hashed mid-run (02:43) and after the run:
all 10 SHA-256 identical, newest file still 2026-10-30 22:37. Benchmark doesn't touch saves.
