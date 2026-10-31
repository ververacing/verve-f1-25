# 2026-10-30 smoke: harness, benchmark Austria 3 laps (issue #3)

Vanilla (no Verve addon), `harness/tests/smoke.test.json`, Swofty 1.6.11, F1 25 build 25251167, PC1 (RTX 3060).
Game log channels: `default,RaceStarts:info,AI_VARIATION:info,CANNED_EVENTS:info`.

| Run | Test file | Result | Launch → exit | Notes |
|---|---|---|---|---|
| 1 (`raw/report`, 18:10) | waited on `event race.start` | FAIL (wait timed out at 240 s) | 5 min 25 s | Race ran and finished normally; Swofty's `race.start` event is not fired by the benchmark |
| 2 (`raw/report-2`, 18:17) | waits on the RaceStarts and StateSession-exit log lines | **PASS** | 5 min 7 s | 20 reaction + 20 start-performance lines asserted |

Both: unattended start to exit, game exited with code 0, `swofty doctor` afterwards: `drift: swofty is not part
of the game`. The CLI's exit code was 2 both times only because it could not delete its throwaway profile (run 1:
"only profile"; run 2: overlay cache folder locked, likely by the open Swofty Launcher window). The leftover
profile `test-20261031-011702` is harmless.

## Start data

`reaction_times.csv`: reaction time per vehicle id for both runs. Same grid both times (entrant trace
`teams 2,3,8,4,3,2,9,0,1,4,7,6,8,9,6,7,5,5,0,1`), 20 values per run:

- run 1: 0.109-0.332 s; run 2: 0.095-0.336 s, mean 0.270 s.
- Per-car values vary a lot between runs (vehicle 0: 0.193 / 0.318), and the whole-field mean moved
  (~0.24 → 0.27), consistent with a random draw per start plus a per-session factor (F-06's k).
- With B-0001's predicted ~0.2 s gap between arms and ~0.05 s spread within a U[lo, hi] draw, 5 starts per arm
  separate the arms comfortably.

`racestarts.log`: the RaceStarts lines and session markers from run 2. `loader.log`: run 2's full loader log
(sha256 `015abf044d51cb4b06e0a021db2063ec8c20d67033ea46f1b8b2a9c4178ff651`).

## Open gap found

RaceStarts identifies cars by vehicle id, and the session trace gives only each car's team, so teammates can't
be told apart. See `docs/harness.md` "Gaps".
