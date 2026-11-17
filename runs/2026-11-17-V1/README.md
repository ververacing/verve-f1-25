# V-1: factorial screen of the driver levers (prereg v3, #160)

Austria, 12 launches × 4 races, 5 laps, seed **20261117**, run with `tools/v1_run.ps1` (one launch per call) on game
build 26566308, Swofty Launcher 1.9.59. Validity only is reported here during the batch. No measures, effects or
per-driver numbers appear before launch 12 is done and `tools/v1_check.py` has run on the full batch.

## v1_check output: REVIEWED 2026-11-17 (supervisor: accepted as scored under prereg v3)

Six traits DEAD; DEFEND, ATTACK and aggression INCONCLUSIVE (underpowered: the pass rate was 2.4x the band's base
rate, and no band was moved after the data); the starts session is not triggered. **F-48** (findings.json) records what
V-1 shows and what it doesn't: whether the overrides reach the per-car AI record is untested, which D1-D3 address.

`python -I tools/v1_check.py runs/2026-11-17-V1 --seed 20261117`:
- 12 launches, **48/48 races valid**. Launch 6's first attempt is in `invalid\` and isn't analysed.
- 10,000 permutations with the launch as the block (21 s; parsing 317 s).
- Per-launch gamedb comes from `gamedb_expected.txt`.
- The full text is in `v1_check/report.txt`; also `summary.json`, `per_race.csv` and `per_driver_launch.csv`.

| Factor | Primary | Pred | Estimate | SE | p | FE slope | SE(FE) | Band | Label |
|---|---|---|---|---|---|---|---|---|---|
| reaction_speed | reaction_s | − | −0.0059 | 0.0035 | 0.094 | −0.0061 | 0.0038 | ±0.02 s | DEAD |
| mistakes | launch_m | + | −0.065 | 0.105 | 0.552 | −0.069 | 0.112 | ±0.5 m | DEAD |
| aggression | passes_made | + | −0.001 | 0.071 | 0.994 | 0.001 | 0.077 | ±0.10 /race | INCONCLUSIVE |
| control | exit_all_kph (floor fallback) | + | 0.010 | 0.238 | 0.968 | 0.020 | 0.258 | ±2 km/h | DEAD |
| speed_in | entry_all_kph | + | 0.009 | 0.307 | 0.973 | 0.021 | 0.332 | ±2 km/h | DEAD |
| speed_out | exit_all_kph | + | −0.089 | 0.241 | 0.711 | −0.084 | 0.261 | ±2 km/h | DEAD |
| DEFEND | passes_suffered | − | 0.156 | 0.109 | 0.153 | 0.164 | 0.118 | ±0.10 /race | INCONCLUSIVE |
| ATTACK | passes_made | + | 0.047 | 0.072 | 0.525 | 0.049 | 0.079 | ±0.10 /race | INCONCLUSIVE |

Notes for the review (facts, not conclusions):
- **Control floor rule:** 3 off-track + spin events in the whole batch (threshold 10), so control's primary is corner-exit
  pace, as registered.
- **The pass rate in V-1** was 18.5 net held passes on laps 2+ per race (8-30; 0.98 per driver-race), against 11.5 in
  the 2-race stock discovery and the 0.41 per driver-race the ±0.10 band was built on. The three pass factors'
  2·SE(FE) is 0.15-0.24, wider than ±0.10, so DEAD was out of reach at this size. No band was changed after the data.
- **Secondaries, not scored, and many were tested:** ATTACK on contacts +0.174 (p 0.002); ATTACK on gain_lap1 +0.208
  (p 0.058); control on offtracks_spins −0.008 (p 0.044, on only 3 events); reaction_speed on launch_m −0.186
  (p 0.078). Everything else had p > 0.1.
- **DEFEND's estimate is in the opposite direction** to the prediction (more passes suffered at 1), but not significant.

**Amendment (2026-11-16, validity tooling only, #162):** weather is checked per launch capture; a non-dry race would
invalidate its whole launch. It's stricter than the prereg's per-race rule, so it can only invalidate more. If a launch
ever reads NOT LOCKED, the supervisor is told before it's dropped. Launches 1 and 2 ran before #162: `weather.txt` in
their folders comes from a hand-run `python -I tools/weather_check.py <launch>/raw/udp.bin --out <launch> --locked`,
the same command #162 adds to v1_run.

**Launch 6, attempt 1: INVALID** (difficulty 99 ≠ 100 in all 4 races; supervisor, 2026-11-16).
- Its data is never analysed, not even as a sensitivity.
- The cause isn't known. The menu presses were identical to launches 1-5 (`pad right 6000`, then 10 × `pad left 200`, the
  same timings), but this boot was a relaunch after a skipped intro (splash after 16 s, then the intro played in 49 s,
  against about 81 s).
- Per the prereg, launch 6 is rerun with the same seed and launch number after launch 7 (an order the supervisor
  approved), and attempt 1 moves to `invalid\`.
- From the next merge, a race-1 session check aborts a launch at once if difficulty ≠ 100, track ≠ 17 or weather ≠ 0,
  and reruns the slot once.
- Each launch logs whether its boot was a skip-relaunch (`boot.txt`). If 99 shows up only after skip-relaunches, that's
  the lead for a plan fix (a longer right-hold), which is made only if it recurs.

**Launch 7: SAVES CHANGED stop (guard exit 5), then the display fallback restored** (supervisor, 2026-11-16).
- Tyler's hardware settings ended at 1024x768 instead of 1920x1080, graphics_card/resolution width and height only. The
  game saves were unchanged. It was most likely the game's display fallback while the display slept (unconfirmed).
- The batch stopped. The 1024x768 file was saved as evidence (`settings-snapshots\…display-fallback-20261116-2103.xml`),
  and only those two values were restored. It was verified by value against the reference: 0 changes.
- Launch 7 stands: 4/4 PASS per uid. The saves guard is a safety stop, not a race-validity rule.
- From #168 on, a resolution-only change is restored automatically ("display fallback restored") and reported in the
  launch status. Any other change still stops the batch.

## Per launch

The tyler.json columns are the hash before the install and after the removal (`profile_hashes.txt`); "=" means restored.

| Launch | Valid races | SCAR | Build check (check_applied) | gamedb | Weather | tyler.json before → after | Intro |
|---|---|---|---|---|---|---|---|
| 1 | 4 / 4 | 0 | 235 applied, 0 dropped, 0 problems | 291 = 56 + 235 | LOCKED (by hand) | 80040DD1…E8EA33 = 80040DD1…E8EA33 | played, no retries |
| 2 | 4 / 4 | 0 | 233 applied, 2 dropped (equal to stock), 0 problems | 289 = 56 + 233 | LOCKED (by hand) | 80040DD1…E8EA33 = 80040DD1…E8EA33 | played, no retries |
| 3 | 4 / 4 | 0 | 234 applied, 1 dropped (equal to stock), 0 problems | 290 = 56 + 234 | LOCKED (v1_run) | 80040DD1…E8EA33 = 80040DD1…E8EA33 | played, no retries |
| 4 | 4 / 4 | 0 | 233 applied, 2 dropped (equal to stock), 0 problems | 289 = 56 + 233 | LOCKED (v1_run) | 80040DD1…E8EA33 = 80040DD1…E8EA33 | played, no retries |
| 5 | 4 / 4 | 0 | 234 applied, 1 dropped (equal to stock), 0 problems | 290 = 56 + 234 | LOCKED (v1_run) | 80040DD1…E8EA33 = 80040DD1…E8EA33 | played, no retries |
| 7 | 4 / 4 (stands, the supervisor's ruling; see the note below) | 0 | 235 applied, 0 dropped, 0 problems | 291 = 56 + 235 | LOCKED (v1_run) | 80040DD1…E8EA33 = 80040DD1…E8EA33 | played, no retries |
| 6 (rerun) | 4 / 4 | 0 | 233 applied, 2 dropped (equal to stock), 0 problems | 289 = 56 + 233 | LOCKED (v1_run) | 80040DD1…E8EA33 = 80040DD1…E8EA33 | played, no skip-relaunch; session check ok (difficulty 100, track 17, weather 0) about 8 s after race 1's start |
| 8 | 4 / 4 | 0 | 233 applied, 2 dropped (equal to stock), 0 problems | 289 = 56 + 233 | LOCKED (v1_run) | 80040DD1…E8EA33 = 80040DD1…E8EA33 | played, no skip-relaunch; session check ok |
| 9 | 4 / 4 | 0 | 235 applied, 0 dropped, 0 problems | 291 = 56 + 235 | LOCKED (v1_run) | 80040DD1…E8EA33 = 80040DD1…E8EA33 | played, no skip-relaunch; session check ok |
| 10 | 4 / 4 | 0 | 234 applied, 1 dropped (equal to stock), 0 problems | 290 = 56 + 234 | LOCKED (v1_run) | 80040DD1…E8EA33 = 80040DD1…E8EA33 | played, no skip-relaunch; session check ok |
| 11 | 4 / 4 | 0 | 235 applied, 0 dropped, 0 problems | 291 = 56 + 235 | LOCKED (v1_run) | 80040DD1…E8EA33 = 80040DD1…E8EA33 | played, no skip-relaunch; session check ok |
| 12 | 4 / 4 | 0 | 233 applied, 2 dropped (equal to stock), 0 problems | 289 = 56 + 233 | LOCKED (v1_run) | 80040DD1…E8EA33 = 80040DD1…E8EA33 | played, no skip-relaunch; session check ok |
| 6 (attempt 1) | **0 / 4: INVALID, difficulty 99 (expected 100) in all 4 races** | 0 | 233 applied, 2 dropped, 0 problems | 289 = 56 + 233 | LOCKED (v1_run) | 80040DD1…E8EA33 = 80040DD1…E8EA33 | skipped, then played on the relaunch (49 s) |
