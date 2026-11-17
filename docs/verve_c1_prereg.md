# C-1 pre-registration: start calibration (game-time reaction → UDP reaction and launch_m)

Status: **DRAFT, not approved.** Nothing runs until the supervisor approves it, and only after D4 is done. Written
from repo files only (no game, launcher or `swofty` call). Evidence: [verve_d1_d2_prereg.md](verve_d1_d2_prereg.md)
(D1), `runs/2026-11-17-D1/d1_check/` (D1's result), [verve_v1_prereg.md](verve_v1_prereg.md) (route, validity).

**Why.** D1 PASSED: the four `ai_driver_config.race_start` bounds pinned at 0.65 gave a UDP reaction of **0.9363 s on
all 18 pinned car-launches** (spread < 0.001 s), against stock 0.469 / 0.483 (pinned − stock +0.467 / +0.453 s). So
UDP = game + about **0.29 s at 0.65**. At stock it's about 0.2 s if the stock draw averages about 0.25 s (bounds 0.04-0.28
/ 0.24-0.42 in `docs/stock/v1_key_cache_26566308.csv`; B-0005 drew 0.198-0.345 on 25251167), but 26566308 has no
RaceStarts log, so the stock game-time draw isn't observed. C-1 maps the game-time value to our measures so that V-2 can
set "Max ≈ best on the grid off the line" in real numbers, and it tests whether the offset is constant or grows with
the reaction (e.g. a slower first motion to the 0.3 m threshold).

## Lever and assignment
- **Levels:** all four race_start bounds = one value per car, at **0.20 / 0.35 / 0.65**, plus **stock** as the
  reference arm. No other writes (as D1). 0.20 sits at the fast end of the stock draws, so it tests the resolution.
- **Rotation design** (seed fixed at approval, before launch 1; proposed **2026111705**): a seeded shuffle gives each
  of the 9 two-AI teams an index t = 0..8, and a seeded coin names its teammates X and Y, both fixed for the batch. With
  arms 0 = stock, 1 = 0.20, 2 = 0.35, 3 = 0.65: in launch L, **X gets arm (t + L) mod 4 and Y gets arm (t + L + 2) mod 4**.
  Alonso (no AI teammate) is always stock. Every car moves up one arm in launch 2, and teammates are never in the same arm.

| Arm | Launch 1 | Launch 2 | Car-launches | Car-races (× 10) |
|---|---|---|---|---|
| stock (incl. Alonso) | 5 | 6 | 11 | 110 |
| 0.20 | 5 | 4 | 9 | 90 |
| 0.35 | 4 | 5 | 9 | 90 |
| 0.65 | 5 | 4 | 9 | 90 |

  That's 14 pinned (56 ops) in launch 1 and 13 (52 ops) in launch 2. **Not 6 per level:** with 19 AI cars, 18 pinned
  would leave Alonso as the only stock car. D1 shows that a pinned level reads the same on every car, so a level's mean
  doesn't need many cars. The stock reference and the "best on the grid" figure do.

## Design and validity
- **1-lap races at Austria**, V-1's route unchanged: the spectator garage start, Custom grid with the player last,
  difficulty 100, weather LOCKED, profile verve-test, the save sandbox. **2 launches × 10 races** (race 1 + 9 `@restart`s).
- **Time per launch** ≈ 8.6 min to race 1 (V-1's 8.3, plus the race-length step) + 10 × 1.5-2 min + 9 × 0.5 min +
  about 1 min to quit ≈ **29-34 min**. Both launches take about 65 min.
- **Validity** as D1: aionly_check per race uid (with 1 lap: the leader finished, ≥ 18 AI cars at status 3), the race-1
  session check (100 / 17 / 0), the per-launch build check (check_applied: all 56 or 52 ops applied), the saves guard.
- **The 1-lap length isn't in the stock menus.** No plan sets the lap count: the 5 laps are the GP default (no menu
  step in `v1_austria_4races.plan`). The catalog add-on **twilight.one-lap-race 0.1.2** unlocks "DEV 1 Lap" in the race
  settings, and it isn't in verve-test. So C-1 needs (i) that add-on installed and enabled in verve-test (sha-checked),
  (ii) a menu discovery for the race-length tile, and (iii) **a stock route check before C-1**: 1 launch, 3 races, 1 lap,
  no test add-on, not scored. It must show 1 lap after `@restart`, an LGOT per race, aionly PASS and session check PASS.
- **Fallback, if the route check fails:** V-1's 5-lap plan unchanged, 4 races per launch (as D1). It needs no new plan.

## Measures and analysis
Per car, v1_check's `start_measures`: **reaction_s** (LGOT arrival → first LapData totalDistance gain ≥ 0.3 m, 1/60 s),
**launch_m** (distance in the 2.0 s after the car's own first movement), **speed_1s_kph** and **gain_t1** (T1_M 345 m).
As D1: each car's mean over the launch's valid races, then the mean over the arm's cars, per launch.
- **Primary, the calibration line:** per launch, an OLS fit of the three level means of reaction_s on the pinned value,
  giving slope b_L and intercept a_L. Estimate = the mean over the 2 launches, **SE = |b₁ − b₂| / 2** (launch-blocked).
  Also reported: the offset per level (mean − value), launch_m per level, and the stock distribution (car-race values,
  per-race fastest stock car).
- **Offset criterion (pre-registered):**
  - **CONSTANT:** the slope is within **1 ± 0.1** in both launches and pooled.
  - **GROWS:** > 1.1 in both launches and pooled. **SHRINKS:** < 0.9 in both launches and pooled. Otherwise **MIXED**.
  - Predictions: a constant 0.286 offset gives 0.486 / 0.636 / 0.936, and then stock (0.47) inverts to a game draw of
    about 0.19. A stock draw of about 0.25 s gives a slope of about 1.14 (GROWS), with 0.20 reading about 0.42 s.
- **Shape checks:** **LINEAR** if the 0.35 mean is within ±0.02 s (V-1's reaction band) of the chord from 0.20 to 0.65,
  in both launches; else CURVED, and the two segment slopes are reported. **Low end RESOLVED** if 0.20 reads at least
  0.075 s (half its 0.15 s step) below 0.35 in both launches; else **FLOOR**, and the slope is refit on 0.35 / 0.65.
- **For V-2 (reported, not scored):** the median per-race fastest stock reaction, and the stock median, each inverted
  through the line to a game-time value. **launch_m reads "pure delay"** if the three level means are within 0.5 m
  (V-1's launch_m band); otherwise the per-level launch_m is V-2's second input.
- **Replication check (not scored):** the 0.65 level must read within one frame (0.017 s) of D1's 0.936 s. If not, the
  1-lap route has changed the chain, and that's reported before any calibration claim.
- Secondaries (speed_1s_kph, gain_t1) aren't scored. The Custom grid is the same every race, so a level's launch_m and
  gain_t1 carry its cars' grid slots. The rotation spreads them across the launches.

## Tooling (to build after approval, for review; within the current tools)
- `tools/c1_make.py`: d1_make with a level map (arm → value) instead of the fixed 0.65, and the rotation above in place
  of the per-launch coin. Same op checks and FORBIDDEN rule. The key cache already holds the 76 race_start paths (D1).
- `tools/c1_check.py`: based on d1_check (same validity imports), adding launch_m and the line fit, the criterion, the
  shape checks, the inversions and the D1 replication check. A selftest with planted slopes 1.0 / 1.14 and a floor.
- `harness/sessions/c1_austria_10races_1lap.plan`: v1_austria_4races.plan, plus the race-length step (from the
  discovery), and 9 × `@restart` / `@udpfinish`.
- `tools/v1_run.ps1 -Make c1`: add `c1` to the ValidateSet, and a `-LaunchMinutes` default for 10 races.
- Profile: twilight.one-lap-race 0.1.2 in verve-test (catalog install, sha-checked), then the stock route check.

No interim looks. Nothing is called a result before the supervisor's review.
