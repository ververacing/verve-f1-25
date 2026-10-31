# B-0011: the generator's addon on the 2025 grid vs F-39 (#53)

Benchmark, Austria, 3 laps, 20 cars, 30 starts (all pass, about 4 m 53 s each). Addon `verve.b0011` = the
`verve_to_swofty.py` (#52) build for the 2025 grid, every driver written. Ferrari (vehicles 8, 19) excluded, leaving 18
drivers and 540 samples. Readout: `tools/b0011_readout.py`, output in `readout.txt`.

## Verdict (criterion fixed in #53 edit 2, before the run)

**FAIL: the reaction envelope.** The other three checks pass.

| Check | Result | Needed | |
|---|---|---|---|
| Reaction: r(per-driver median, F-39 prediction) | **0.663** | >= 0.6 | pass |
| Reaction envelope at the per-start k (+-0.005 s) | worst driver **2** misses (Sainz, Tsunoda) | <= 1 of 30 | **FAIL** |
| b envelope [0.06 - 0.02 m, 0.42] | 0 misses | <= 1 of 30 | pass |
| Bad start: pooled fixed-intercept k | **0.477** (boot SE 0.080) | in [0.40, 0.72] | pass |
| Descriptive: per-driver r for b | 0.215 | (power note: ~0.29 expected) | |

The power simulation gave the envelope check P(pass) = 1.00 if F-39 is right, so this fail is not an expected miss.

## What the misses show (`envelope_misses.csv`, descriptive)

11 of 540 samples fall outside, spread over 9 drivers:

- 9 are *below* the lower edge (faster than F-39 allows), by 0.005-0.013 s beyond the 0.005 s tolerance.
- 2 are above (Piastri start 23, Sainz start 30), by 0.005-0.007 s.
- The low misses cluster in starts with a low fitted k (0.42-0.48; batch mean 0.516, sd 0.047).

So the generator's ordering holds (r 0.66). It's F-39's reaction lower edge, `0.28 - 0.24 k rs`, that sits about
0.01 s too high, at least when the field's k comes out low. It may be a different intercept or slope for the lower
edge, or a draw that isn't uniform. 540 samples aren't enough to pick between those.

## Bad-start k

The pooled fixed-intercept k for written rows is 0.48 +- 0.08 here, against 0.70 (B-0009) and 0.93 (B-0010). Those two
were contrasts between 0.10 and 0.90 cells relative to the stock-field median. This one is a level fit over Verve's
narrow m range (0.38-0.98) with the intercept fixed at 0.24, so an intercept error goes straight into k. The
supervisor's "use k_b ~0.8 for written rows" (#54 review) isn't supported by this batch. I've held the generator change
until the supervisor rules on it.

## Isolation and build

- Every start: `gamedb: 215 overwritten, 322 created` = 52 baseline + 163 B-0011 writes, as found by the build check
  (`runs/2026-10-31-B-0011-check/check_applied.txt`; #53 comment). `racestarts_summary.ps1 -ExpectOverwritten 215`
  passed for all 30.
- The build check confirmed all 136 written characteristics. Pace curves were written at the right keys but their
  values aren't logged (needs a UI check, not used here).

## Saves

Tyler's save folder was hashed after the batch, as the master backup (`save-backups\20261031-070733-master`, 07:07). All
10 files are identical to the post-B-0010 hashes. Benchmark again left the saves alone.

## Files

`summary.csv`, `per_start.csv`, `per_vehicle.csv`, `racestarts_*.log`, `readout.txt`, `envelope_misses.csv`.
