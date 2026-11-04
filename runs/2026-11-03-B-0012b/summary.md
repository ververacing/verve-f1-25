# B-0012b: race_start tags in a normal Grand Prix (#70)

**Result: PASS, 5 of 5, none invalid. This answers Q-02 (#7): a normal Grand Prix reads per-driver `ai_driver_config.race_start`, as benchmark does.**

Austria, 2025 season, Aston Martin, Stroll, default settings (5 laps), reached through the menus by `harness/sessions/gp_menu_race.plan`, in the save sandbox, unattended, 2026-11-03. Addon `verve.b0012`, unchanged from #57: all four reaction bounds at 0.65 on 9 drivers from 9 teams. Pre-registered on #70 before any data.

## Results

Scored by `tools/b0012_check.py --menu`.

| Start | Cars at 0.650 | Untagged at 0.650 | Reaction lines per car | gamedb | Grid | Player | Result |
|---|---|---|---|---|---|---|---|
| 1 | 9 | 0 | exactly 1 | 88 / 322 | stock 2025 | car 19, Stroll | PASS |
| 2 | 9 | 0 | exactly 1 | 88 / 322 | stock 2025 | car 19, Stroll | PASS |
| 3 | 9 | 0 | exactly 1 | 88 / 322 | stock 2025 | car 19, Stroll | PASS |
| 4 | 9 | 0 | exactly 1 | 88 / 322 | stock 2025 | car 19, Stroll | PASS |
| 5 | 9 | 0 | exactly 1 | 88 / 322 | stock 2025 | car 19, Stroll | PASS |

- **All five ran unattended end to end**, so start 1 counted under #70's plan rule.
- **Each car draws exactly once per start**, 20 lines per start. No re-rolls, unlike the direct-start state (#57), where they came every 30-50 ms. That's what a real start looks like.
- **The game-database count is 88 (52 + 36) in this mode**, so our rows apply here too, despite the session trace reading `f1_custom_team`.
- **Tyler's saves and Steam's records were unchanged on all five**, and matched the last-known-good snapshot afterwards.

## Launch behaviour (exploratory, not pre-registered)

This is the first measured effect of a Verve setting on a real race start. Averages from UDP. Tagged is the 9 cars at 0.650, untagged the other 10 AI cars.

| Start | Speed at 1 s, tagged / untagged | At 3 s | At 6 s | Places gained by 6 s, tagged / untagged |
|---|---|---|---|---|
| 1 | 13.0 / 20.0 km/h | 79.3 / 95.4 | 206.6 / 206.7 | -0.9 / +0.8 |
| 2 | 12.8 / 19.3 | 80.1 / 93.0 | 208.7 / 216.1 | -0.7 / +0.8 |
| 3 | 12.8 / 19.9 | 78.7 / 93.4 | 204.8 / 207.9 | -1.0 / +0.8 |
| 4 | 12.9 / 19.6 | 82.3 / 91.6 | 208.3 / 205.5 | -0.3 / +0.3 |
| 5 | 12.8 / 19.4 | 79.0 / 93.2 | 210.2 / 210.4 | -0.8 / +0.8 |

A slower reaction loses speed and places off the line, in all five starts. **Treat this as a lead for a pre-registered batch, not a finding:** it wasn't the question asked, and 5 starts is few. **The grid changes every race**, so these averages mix different grid slots, and places gained depends on where each car started. (An earlier version of this summary said the grid looks the same each start. That was wrong: slots 6-15 differ in all five.)

## What it doesn't show

- **Keys other than the four `race_start` bounds.** Each still needs its own test in this mode. It's a good sign for per-driver rows in general, not a proof.
- **Career.** #31 stays parked, by the supervisor's ruling.
- **The player's car.** Stroll wasn't tagged. Untagged, the player drew 0.135, 0.124, 0.046, 0.186 and 0.154, and the player car was 19 every time.

## Why the route matters

The menu route races to the flag in the sandbox (`runs/2026-11-03-gp-fixture`: 5 laps, flag at 354 s). It reaches lights out in about 6 min 30 s from launch. Behaviour batches can run on it, which benchmark (a procession) and the direct start (no race) can't support.
