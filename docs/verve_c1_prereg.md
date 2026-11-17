# C-1 pre-registration: start calibration (game-time reaction → UDP reaction and launch_m)

Status: **design APPROVED by the supervisor (2026-11-17):** the arms, the rotation, Alonso stock, the line-fit
criterion, the shape checks and the 0.65 reproduction check. **Route revised by the supervisor's ruling on the
1-lap gap: start-only restarts.** This revision is a DRAFT awaiting approval. Nothing runs until D4 is done and this
revision is approved, and the smoke test passes first.
Written from repo files only (no game, launcher or `swofty` call). Evidence: [verve_d1_d2_prereg.md](verve_d1_d2_prereg.md)
(D1), `runs/2026-11-17-D1/` (D1's result and captures), `runs/2026-11-16-V1-phase0/`, [verve_v1_prereg.md](verve_v1_prereg.md).

**Why.** D1 PASSED: the four `ai_driver_config.race_start` bounds pinned at 0.65 gave a UDP reaction of **0.9363 s on
all 18 pinned car-launches** (spread < 0.001 s), against stock 0.469 / 0.483 (pinned − stock +0.467 / +0.453 s). So
UDP = game + about **0.29 s at 0.65**. At stock it's about 0.2 s if the stock draw averages about 0.25 s (bounds 0.04-0.28
/ 0.24-0.42 in `docs/stock/v1_key_cache_26566308.csv`; B-0005 drew 0.198-0.345 on 25251167), but 26566308 has no
RaceStarts log, so the stock game-time draw isn't observed. C-1 maps the game-time value to our measures so that V-2 can
set "Max ≈ best on the grid off the line" in real numbers, and it tests whether the offset is constant or grows with
the reaction (e.g. a slower first motion to the 0.3 m threshold).

## Lever and assignment (approved)
- **Levels:** all four race_start bounds = one value per car, at **0.20 / 0.35 / 0.65**, plus **stock** as the
  reference arm. No other writes (as D1). 0.20 sits at the fast end of the stock draws, so it tests the resolution.
- **Rotation design** (seed fixed before launch 1; proposed **2026111705**): a seeded shuffle gives each of the 9 two-AI
  teams an index t = 0..8, and a seeded coin names its teammates X and Y, both fixed for the batch. With arms
  0 = stock, 1 = 0.20, 2 = 0.35, 3 = 0.65: in launch L, **X gets arm (t + L) mod 4 and Y gets arm (t + L + 2) mod 4**.
  Alonso (no AI teammate) is always stock. Every car moves up one arm in launch 2, and teammates are never in the same arm.

| Arm | Cars, launch 1 | Cars, launch 2 | Car-launches | Car-starts (× 20) |
|---|---|---|---|---|
| stock (incl. Alonso) | 5 | 6 | 11 | 220 |
| 0.20 | 5 | 4 | 9 | 180 |
| 0.35 | 4 | 5 | 9 | 180 |
| 0.65 | 5 | 4 | 9 | 180 |

  That's 14 pinned (56 ops) in launch 1 and 13 (52 ops) in launch 2. Each level gets 4-5 cars per launch, not 6: with
  19 AI cars, 18 pinned would leave Alonso as the only stock car. D1 shows that a pinned level reads the same on every
  car, so a level's mean doesn't need many cars. The stock reference and the "best on the grid" figure do.

## Route: start-only restarts (the supervisor's ruling)
- **Race 1** is reached on V-1's menu path unchanged (spectator garage start, Custom grid with the player last,
  difficulty 100, weather LOCKED, profile verve-test, the save sandbox), with the race-1 `@sessioncheck 100 17 0`.
- **Per start:** wait for that race uid's LGOT + **CUTOFF**, then `@restart` (pause → Restart Session → up + A →
  `garage_monitor_container` → `pad a 700`), and repeat. No race finishes, so there's no lap count and no new add-on.
- **CUTOFF = 20 s after LGOT (fixed).** D1's captures (8 races, 19 AI cars each, pinned 0.65 cars included) put the
  slowest AI car at lap-1 lapDistance ≥ T1_M (345 m) **9.11-9.34 s** after LGOT (median car 8.1 s). So 20 s leaves
  more than 10 s of margin over the slowest T1 crossing. It also covers reaction (≤ 1 s), launch_m (first motion
  + 2.0 s) and speed at 1 s. The cut needs no lapDistance logic in the shell.
- **A mid-lap restart is already shown:** Phase 0 restarted races 78-123 s after LGOT, in lap 1, each a new uid with
  its own LGOT and the same grid (`runs/2026-11-16-V1-phase0`).
- **Size: 20 starts per launch** (race 1 + 19 restarts), **2 launches**, fixed before launch 1. Each start takes about
  1 min (the restart and garage, `pad a`, 20-35 s to lights out, the 20 s cutoff). One launch ≈ 8.3 min to race 1 +
  19 × 1-1.25 min + about 1 min to quit ≈ **28-34 min**. Both launches take about 65 min.

## Validity per start uid (a start-only variant of aionly_check)
A start counts only if:
- (a) the launch's race-1 session check holds;
- (b) the player car has no COLL and no PENA from LGOT to the cutoff;
- (c) all 19 AI cars move (a totalDistance gain ≥ MOVE_M);
- (d) weather is LOCKED;
- (e) the uid is new in the launch;
- (f) *(proposed)* the capture covers LGOT to the cutoff with no gap > 5 s (aionly's live-window rule, ending at the
  cutoff).

Also as approved: the per-launch build check (check_applied: all 56 or 52 ops applied) and the saves guard. The
finish, plausible-finish and lap checks don't apply. The check **prints that explicitly** for every start
("finish checks: not applicable (start-only)"); it doesn't skip them silently.

**Smoke test first** (before C-1, not scored): 1 launch, stock only (no test add-on), race 1 + 3 start-only restarts.
It must show:
- `@restart` works mid-race, with a new uid each time;
- the same grid in every start;
- the garage start holds, with the player re-parked each start (loader "GARAGE: car 19 sent", LapData driverStatus 0);
- the start-only check passes all 4 uids;
- the plan ends cleanly with no finish (quit, saves guard and cleanup run).

**If the smoke test FAILS,** the fallback is V-1's 5-lap plan unchanged, 4 races per launch, with aionly_check as D1.
twilight.one-lap-race is not used unless the supervisor rules again.

## Measures and analysis (approved)
Per car, v1_check's `start_measures`: **reaction_s** (LGOT arrival → first LapData totalDistance gain ≥ 0.3 m, 1/60 s),
**launch_m** (distance in the 2.0 s after the car's own first movement), **speed_1s_kph** and **gain_t1** (T1_M 345 m).
As D1: each car's mean over the launch's valid starts, then the mean over the arm's cars, per launch.
- **Primary, the calibration line:** per launch, an OLS fit of the three level means of reaction_s on the pinned value,
  giving slope b_L and intercept a_L. Estimate = the mean over the 2 launches, **SE = |b₁ − b₂| / 2** (launch-blocked).
  Also reported: the offset per level (mean − value), launch_m per level, and the stock distribution (car-start values,
  per-start fastest stock car).
- **Offset criterion:**
  - **CONSTANT:** the slope is within **1 ± 0.1** in both launches and pooled.
  - **GROWS:** > 1.1 in both launches and pooled. **SHRINKS:** < 0.9 in both launches and pooled. Otherwise **MIXED**.
  - Predictions: a constant 0.286 offset gives 0.486 / 0.636 / 0.936, and then stock (0.47) inverts to a game draw of
    about 0.19. A stock draw of about 0.25 s gives a slope of about 1.14 (GROWS), with 0.20 reading about 0.42 s.
- **Shape checks:** **LINEAR** if the 0.35 mean is within ±0.02 s (V-1's reaction band) of the chord from 0.20 to 0.65,
  in both launches; else CURVED, and the two segment slopes are reported. **Low end RESOLVED** if 0.20 reads at least
  0.075 s (half its 0.15 s step) below 0.35 in both launches; else **FLOOR**, and the slope is refit on 0.35 / 0.65.
- **For V-2 (reported, not scored):** the median per-start fastest stock reaction, and the stock median, each inverted
  through the line to a game-time value. **launch_m reads "pure delay"** if the three level means are within 0.5 m
  (V-1's launch_m band); otherwise the per-level launch_m is V-2's second input.
- **Reproduction check (not scored):** the 0.65 level must read within one frame (0.017 s) of D1's 0.936 s. If not, the
  start-only route has changed the chain, and that's reported before any calibration claim.
- Secondaries (speed_1s_kph, gain_t1) aren't scored. The Custom grid is the same every start, so a level's launch_m and
  gain_t1 carry its cars' grid slots. The rotation spreads them across the launches.

## Scoring details (supervisor, 2026-11-17)
Rulings on the tooling's five open decisions (#180), all accepted. `tools/c1_check.py` implements exactly these.
1. **FLOOR:** if the low end is FLOOR, the 0.35 / 0.65 two-point line is the line: it is used for the offset
   criterion and for the game-time conversions. Every verdict reached that way is tagged **"(FLOOR: 2-point fit)"**
   wherever it appears (stdout and summary.json), with the 0.20 level's mean printed beside it.
2. **launch_m "pure delay":** the three level means are within 0.5 m of each other (max - min <= 0.5 m) in both
   launches.
3. **The 0.65 reproduction:** within 0.017 s of D1's 0.9363 s in both launches. A miss is reported prominently (a
   "REPRODUCTION MISS" line right after the report's header, repeated at its end, and in summary.json), and stays
   not scored.
4. **An "unverified" race-1 session check** is redone offline ONLY from this launch's own race-1 Session packet (the
   first at or after lights out, else race 1's latest), and all three values must match: difficulty 100, track 17,
   weather 0. A missing packet or any value that differs fails validity (a). The path is recorded per launch, in the
   output and in summary.json: "session check: live" or "session check: offline redo from race-1 Session packet"
   ("none" when there is no session_check.txt or the live check failed).
5. **Smoke "player re-parked":** car 19's LapData driverStatus is 0 (garage) in every frame from LGOT to the cutoff,
   and it has no totalDistance gain >= 0.3 m. The loader's "GARAGE: car 19 sent" lines are reported only (D1 launch 1
   has 2 of them for 4 races).

Non-scoring items, accepted:
- `@startwait` logs each start to `<Out>\udp_starts.txt` (start number, time, exit, uid), not `udp_races.txt`.
- The stall rule: after the LGOT, if the capture doesn't pass LGOT + cutoff within cutoff + 30 s, `@startwait`
  exits 2 and the plan stops.
- The pause-at estimates (`tools/v1_run.ps1 -LaunchMinutes`): 40 min for a C-1 launch, 16 for the smoke test.
- The seed: **2026111705**, fixed before launch 1.

## Tooling (to build after approval, for review; within the current tools)
- `tools/c1_make.py`: d1_make with a level map (arm → value) instead of the fixed 0.65, and the rotation above in place
  of the per-launch coin. Same op checks and FORBIDDEN rule. The key cache already holds the 76 race_start paths (D1).
- **A new shell step `@startwait <cutoff s> [<max s>]`** in `tools/sandbox_shell.ps1`. It waits on the live UDP for a
  new race uid's LGOT (excluding the uids already done), then the cutoff. It adds the uid to the done list and to
  `udp_races.txt`. With no new LGOT within `<max s>` (default 120), the plan stops. It reuses udp_finish_watch.py's
  machinery (a `--start-only <s>` mode).
- `harness/sessions/c1_austria_20starts.plan`: v1_austria_4races.plan's menu part, `@sessioncheck 100 17 0`,
  `@startwait 20`, then 19 × (`@restart`, `@startwait 20`). Plus `c1_smoke_4starts.plan`: the same with 3 restarts.
- **The start-only validity check:** `tools/startonly_check.py`, or a `--start-only <cutoff>` mode of aionly_check,
  covering rules (a)-(f) and the explicit "not applicable" line.
- `tools/c1_check.py`: based on d1_check, with the start-only check as validity. It adds launch_m and the line fit, the
  criterion, the shape checks, the inversions and the D1 reproduction check. A selftest has planted slopes
  1.0 / 1.14 and a floor.
- `tools/v1_run.ps1 -Make c1`: add `c1` to the ValidateSet, a `-LaunchMinutes` default for 20 starts, and a
  stock-only smoke-test mode (no test add-on, the smoke plan).
- Dropped from the first draft: twilight.one-lap-race, the race-length discovery and the 1-lap plan.

No interim looks. Nothing is called a result before the supervisor's review.
