# B-0001: row vs rating precedence, per-team arms, benchmark Austria (#30)

Addon `harness/addons/verve.b0001` (12 ops), `harness/tests/b0001.test.json`: 5 fresh starts, benchmark Austria,
3 laps, 20 cars, clear. 2026-10-30 19:44–20:09, all 5 PASS, unattended.
Arms (both drivers of each team): ROW_slow Alpine (row reaction_speed 0.05), ROW_fast McLaren (row 0.99),
STATS_slow Sauber (racecraft flat 0.05, default + 2026), STATS_fast Racing Bulls (racecraft flat 0.99).
Readout rule fixed in #30 before the run (edit 3).

## Isolation

Every start: **64 overwritten** (52 baseline + 12), 322 created, 0 skipped (`isolation.csv`).

## Result: **INCONCLUSIVE by the pre-set criterion, leaning "row wins"**

`tools/b0001_readout.ps1` (`arms.csv`, `stock_field.csv`). Each sample is relative to its start's stock-field
median (Ferrari and the four arm teams excluded):

| Arm | Team | n | Median rel. | Range rel. | Median abs. | Predicted rel. if ROW wins | Predicted rel. if RATINGS win |
|---|---|---|---|---|---|---|---|
| ROW_slow | Alpine | 10 | **+0.042** | −0.024 … +0.147 | 0.326 | +0.075 | −0.01 |
| ROW_fast | McLaren | 10 | **−0.014** | −0.077 … +0.037 | 0.271 | −0.015 | −0.01 |
| STATS_slow | Sauber | 10 | **−0.003** | −0.088 … +0.072 | 0.278 | +0.005 | +0.075 |
| STATS_fast | Racing Bulls | 10 | **+0.036** | −0.085 … +0.088 | 0.306 | +0.03 | −0.015 |

(Predicted rel. = the k = 0.5 means from #30 minus a stock-field mean of ~0.27 s.)

- **ROW pair gap (Alpine − McLaren): +0.056 s.** Predicted direction, just under the 0.06 s bar (predicted ~0.10 s).
- **STATS pair gap (Sauber − Racing Bulls): −0.039 s, reversed.** "Ratings win" predicted +0.10 s. That is clearly
  not what happened; "row wins" predicted −0.015 s.
- By the rule fixed in advance ("winner ≥ 0.06 s, loser < 0.03 s or reversed"), the ROW pair misses by 0.004 s, so
  the verdict is **inconclusive**. The STATS half points away from the ratings: racecraft at 0.05 vs 0.99 made no
  difference in the predicted direction.
- Per sample, Alpine was slower than its start's stock field in 9 of 10, but by about half the predicted margin
  (+0.042 vs +0.075). Either k is lower here, the row value is only part of what the start uses, or something
  else (e.g. the race_start bounds in `ai_driver_config`) caps the effect.
- Vehicle 19 (Ferrari) again: 0.096, 0.209, 0.220, 0.149, 0.055 s. The fastest non-Ferrari per start was 0.166–0.199 s.

## Holds for

Benchmark mode, Austria, f1_2025 list, season x = 0 only (docs/harness.md, review finding 2). Q-04 isn't tested
(fresh launch per start).

## What would settle it

- **B-0005 (#37)**, running next: if `ai_driver_config.race_start` is read per driver, it gives the vehicle → driver map,
  so a rerun can use per-driver arms and drop the teammate averaging.
- Or more repeats of this exact batch, with the combined criterion fixed before they run.
