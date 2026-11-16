# V-1 pre-registration (v3): are the driver levers alive? A factorial screen

Status: **v3 for the supervisor's approval** (2026-11-16). It replaces the v2 draft (#147). It applies the supervisor's
rulings on #147 (A-H), on #148 (bundles, maps, the throttle_exit_fallibility exception), on Phase 0 (size, UDP start
measures, conditional starts session, launch-blocked permutation) and on #155 (mistakes direction, control floor fallback,
corner pace, decision labels). Scope: Verve Drivers (docs/process.md). Evidence base:
[verve_drivers_plan.md](verve_drivers_plan.md).

The values marked **[discovery]** are filled from the Austria discovery launch, and those marked **[readback]** from the
v1_make readback, both before race 1. The map numbers marked **[re-dump]** are re-checked against the 26566308 stock
dump. If any stock corner differs, the table is regenerated and the supervisor is told.

**V-1 START RULE** (supervisor): V-1 starts once (i) this v3 is approved, (ii) `@restart` is merged (#153), and (iii) the
v1_make readback passes on 26566308: the package select works, the 235 ops are applied and the gamedb count matches.
v1_check (#155) can follow during the batch, and the supervisor reviews it before any verdict. **No interim looks.**

## Question
On game build 26566308 (F1 25 Steam 1.0.145.2472), on the spectator garage route (F-46), do the eight per-driver
factors change behaviour when pushed to 0 vs 1, with the parameter maps amplified ×3? The eight factors are the six
`driver_characteristics` on the 2025 rows plus the DEFEND and ATTACK `ai_driver_config` bundles. "Alive or not" only;
realistic values are V-2. If the traits are dead even amplified, the row-to-map route is dead and we know it in a day.

## Setup
- **Route:**
  - kizi.spectator-hud 0.1.11 with start_garage On, park_teammate Off, keep_race On, bg_run On, auto_on On.
  - msyeett.starting-grid 0.1.4, Custom grid with the player last.
  - gamedb 56 stock, plus this launch's test add-on.
  - Profile verve-test only. Tyler's profile is never selected.
- **Player seat:** `lance_stroll` (car 19, Aston Martin), parked in the garage 2 s after each race.start. That leaves 19
  AI drivers; Alonso is the only AI driver with no AI teammate. Confirmed in Phase 0 and W-0134 (loader: "GARAGE: car 19
  sent").
- **Track (the supervisor's track rule):** **Austria** (Red Bull Ring, UDP track id 17).
  - The measure is net held passes on laps 2+ per race-minute, on stock dry races.
  - Austria (B-0016 arm A, dry races only) gives **1.337**. Hungary (B-0018, 10 dry races) gives **0.353**, so Austria
    is **3.8×** Hungary.
  - The rule was 1.5× or more, so Austria. No other track in our data passes more.
  - The plan: `harness/sessions/v1_austria_4races.plan` (the Austria `_grid_ai` menu from #150, ten rights from
    Australia).
- **Weather:** locked dry. Validity needs weather 0 in every sample and rain% ≤ 5 (#118, second amendment).
- **Laps:** 5 (ruling on #149; on B-0018, laps 2-3 hold 13 of the 24 net held passes on laps 2+).
- **Grid:** it varies between launches, which decorrelates driver from grid slot. It's the same for the 4 races of a
  launch. There is **no GP fixture**; the fixture idea is parked in the plan doc.

## Phase 0 result (runs/2026-11-16-V1-phase0, Hungary)
- **Restart works while spectating.**
  - The path: pause → Restart Session → the confirm dialog (it defaults to Cancel) → up, A → the pre-race garage
    (`garage_monitor_container`, which skips the 125 s rundown) → `pad a 700`.
  - The car is re-parked on every race.start, and the grid is the same within a launch.
  - Each restart is a **new UDP session uid**. Restart to lights out takes about 20-35 s.
- **The RaceStarts game log is gone on 26566308** (no `log_channels.tsv` for this build), so start measures come from UDP.
- **The UDP start measures are sane** on 76 car-starts:
  - reaction 0.351-0.570 s (median 0.468);
  - per-car SD across restarts 0.044 s;
  - launch 16-23 m.
  - For scale: the F-39 model predicts about 0.11 s between reaction_speed 0 and 1, so the resolution is enough.

## Design
- **Size, fixed before race 1:** **12 launches × 4 races** = 48 races, 5 laps, Austria. Races within a launch share the
  assignment and the grid, so they are correlated replicates. More launches buy more than more races per launch.
- **Assignment per launch:** `tools/v1_make.py draw(seed, launch)`, which is pure and seeded.
  - Each factor is 0/1 per driver.
  - In each of the 9 two-AI teams, one coin flip per factor puts one teammate at 1, so teammates always split and the
    car is controlled for.
  - Alonso alternates 1/0 by launch, with a seeded phase per factor.
  - Each factor therefore has 9 or 10 drivers at 1. Factors are drawn independently.
  - The seed is fixed before race 1 and recorded in the batch (`seed.txt`). `assignment.csv` is written per launch.
- **Test add-on per launch:** `verve.v1-l<LL>`, `game_builds [">=26566308"]`, **235 ops** = 19 drivers × (6 traits +
  6 bundle keys) + 7 maps.
  - `tools/v1_run.ps1` installs it, enables it in verve-test for the run only (`-Addon`), and removes it afterwards.
  - Each launch briefly adds and removes a *disabled* entry in tyler.json. That's inside Tyler's standing add-on OK.
  - `profile_hashes.txt` checks the tyler.json hash before the install, after it and after the removal; the runner
    exits 14 on any change.
  - **The batch README carries one line per launch: tyler.json hash before = hash after.**
- **Traits:** `entrants.drivers.driver[_metadata_=<label>].driver_characteristics.<trait>` = 0.0 or 1.0, for
  reaction_speed, mistakes, aggression, control, speed_in and speed_out.
- **Bundles** (approved on #148; tick-read keys only; never `cede_position.*`, `yellow_flag_*` or `flying_lap_yield_*`):

| Bundle | Key (`ai_driver_config.`) | Stock **[re-dump]** | 0 | 1 |
|---|---|---|---|---|
| DEFEND | blocking.max_blocking_distance | 18 | 5 | 45 |
| DEFEND | blocking.max_blocking_distance_at_race_start | 18 | 5 | 45 |
| DEFEND | blocking.fraction_of_follow_speed | 0.975 | 1.0 | 0.7 |
| DEFEND | blocking.fraction_of_follow_speed_at_race_start | 0.875 | 1.0 | 0.6 |
| ATTACK | overtake.overlap_percentage | stock curve | flat 0.9 | flat 0.05 |
| ATTACK | alongside.yield_overtake_rate | 1 | 2 | 0.5 |

- **Amplified maps** (ruling A; a per-package test lever, `entrants.vehicles.vehicle_packages.vehicle_package_10`):
  - For each live map, the high_difficulty_low_characteristic corner (hl) becomes hh + 3 × (hl − hh), capped at the
    low_difficulty_low corner (ll).
  - The 4 dead maps stay untouched.

| Map | Characteristic | hh | hl (stock) | ll | **hl, V-1** |
|---|---|---|---|---|---|
| alongside_space_factor | aggression | 1 | 1.15 | 1.5 | **1.45** |
| braking_distance_factor | speed_in | 1 | 1.15 | 2.74 | **1.45** |
| corner_curvature_factor | speed_out | 1 | 0.92 | 0.5888 | **0.76** |
| follow_speed_factor | aggression | 1 | 1.05 | 1.4 | **1.15** |
| throttle_confidence | control | 1 | 0.96 | 0.78 | **0.88** |
| throttle_exit_fallibility | control | 0.75 | 1 | 1 | **1.5 (uncapped)** |
| throttle_on_time | control | 0 | 0.6 | 6.6 | **1.8** |
| alongside_awareness, brake_off_time, slide_confidence, wet_weather_ability | control | | | | dead, untouched |

  The stock corners above are from the 25251167 dump **[re-dump]**.
  - **The one exception to the cap (ruling on #148): throttle_exit_fallibility.** The cap would make it a no-op
    (hl = ll = 1). "Rare vs frequent mistakes" is a headline trait for Tyler, so its hl corner is set to 1.5
    (0.75 + 3 × 0.25), past ll. The per-car exit_fallibility caps still bound the error.
  - **Fallback:** if the validity stop trips, the first step down is this map back to 1.0 (`v1_make --no-uncapped`),
    then ×2 overall.

## Validity per race (tools/aionly_check.py, per race uid)
- The finish comes from LapData: the leader at position 1 with resultStatus 3, and **at least 18 AI with status 3**.
- Track 17, difficulty 100, weather LOCKED, gamedb as read back, and no pause cut.
- The live window runs from lights out to the first AI finish, with the plausible-finish check.
- Any player COLL or PENA from lights out is a FAIL.
- An invalid race is dropped and listed. The launch keeps its other valid races, and there are no reruns inside a launch.
- A launch with no valid race is rerun in its slot with the **same** seed and launch number.
- The F-47 crash report at every quit is **not** a failure by itself.
- **VALIDITY STOP (ruling F):** this is not an effect look. If two launches in a row give under 18 AI finishers, or a
  safety car in most races, stop and report. Then take the fallback above (throttle_exit_fallibility to 1.0, then ×2),
  on the supervisor's ruling.

## Measures: one primary per factor (tools/v1_check.py, #155)
All measures are per driver per race. **Start measures** come from UDP LapData at 60 Hz, so the resolution is 1/60 s.
They are **relative** measures: there's a constant offset from the UDP send and arrival lag and from the threshold.
They are compared only between levels, never read as absolute times.

- **reaction** = from the LGOT event's arrival wall time to the car's first LapData frame whose totalDistance is at
  least **0.3 m** (`MOVE_M`, fixed) over its last pre-LGOT value.
- **launch** = the totalDistance covered in the **2.0 s after the car's own first movement**. That separates a bad
  launch from a slow reaction.
- **Covariate:** grid side (odd/even gridPosition). All start measures are residualised on it first.

| Factor | Primary | Predicted at 1 | Null band (FE slope) |
|---|---|---|---|
| reaction_speed | reaction (s) | shorter | ±0.02 s |
| mistakes | launch (m) | **longer**: mistakes is a skill, higher = fewer mistakes (F-29, F-37) | ±0.5 m **[discovery]** |
| aggression | held passes made, net, laps 2+, per race | more | ±0.25 per race |
| control | off-tracks + spins per race (see below) | fewer | ±0.1 per race |
| speed_in | corner-entry pace, all passes, field-relative (km/h) | faster | ±2 km/h |
| speed_out | corner-exit pace, all passes, field-relative (km/h) | faster | ±2 km/h |
| DEFEND | held passes suffered, net, laps 2+, per race | fewer | ±0.25 per race |
| ATTACK | held passes made, net, laps 2+, per race | more | ±0.25 per race |

- **Launch null band, ±0.5 m:** it's about 2.5% of a 20 m launch. It will be fixed against the per-car launch SD
  across starts in the discovery launch **[discovery]**, with that reasoning written here before race 1.
- **control: definitions.** UDP has no off-track event, and LapData's currentLapInvalid and cornerCuttingWarnings never
  move for AI cars (0 across 510k car-frames in Phase 0). So:
  - **off-track** = at least 2 wheels on an unpaved CarTelemetry surfaceType (rock, gravel, mud, sand, grass, water).
    An episode ends after 1 s back on a paved surface.
  - **spin** = horizontal speed of at least 5 m/s with a slip angle (Motion velocity against the forward vector) of
    at least 60°. Episodes within 3 s merge.
  - Both count from lights out to the car's own finish, outside the pit lane.
  - It reads 0 at stock (Phase 0), so v1_check reports a floor flag.
  - **FLOOR FALLBACK, decided blind to assignment:** if the whole batch has **fewer than 10** off-track + spin events in
    total (all cars, all races), control's primary becomes **corner-exit pace**: field-relative speed 150 m after the
    apex, all passes, laps 2+. That's the same measure as speed_out; the factors are independent, so the factorial
    separates them. The switch depends only on the total event count, never on which drivers had the events.
    Lap-time SD is reported as a secondary either way.
- **Corner pace** (speed_in, speed_out):
  - The corners are race_feel's brake-onset corners, laps 2+, with no pit lap.
  - Entry = the minimum speed from the onset to 250 m after it (that point is the apex). Exit = the speed 150 m after
    the apex.
  - The value is each car's mean over corners of its median minus the field median, in km/h.
  - **All passes is primary.** The clean-pass version (no car within 2.0 s ahead in the 300 m before the onset) is the
    secondary, because it left only 4 of 19 cars with a value in a train-heavy race.
- **Pass floor:** the stock net held passes on laps 2+ per race come from the discovery launch **[discovery]**. If its
  two races average **under 4**, the supervisor is told before V-1 starts.
- **Secondaries, all factors, not scored:**
  - speed at 1 s after lights out;
  - positions gained to T1 (at the first lap-1 lapDistance ≥ `T1_M` = **[discovery]** m, set from the Austria capture
    at the first braking zone) and at the end of lap 1;
  - ATTACK's effect on passes suffered, and DEFEND's on passes made (cross-effects);
  - contacts (race_feel collisions); lap-time SD (laps 2+, no pit laps);
  - clean-pass corner pace.

## Analysis (v1_check.py)
- **Per launch:** average each driver's measure over that launch's valid races. Races within a launch are never
  independent.
- **Driver fixed effects:** centre each driver's launch-means across launches. Drivers with fewer than 2 launches are
  left out.
- **Statistic** = the mean over launches of (the mean of centred values at 1 − the mean at 0).
- **Permutation test, with the launch as the block:** 10,000 redraws, each replacing every launch's assignment with
  `draw(seed_k, launch)` for a fresh seed (the same constrained randomisation as the real one). p is two-sided:
  p = (1 + #|null| ≥ |observed|) / (K + 1). SE = the SD of the null.
- **FE slope:** a driver-fixed-effects regression slope, used for the band comparison. Centring shrinks the statistic
  to about 11/12 of the true effect, so both are reported.
- **Decision labels (ruling on #155):**
  - **ALIVE:** p < 0.05, in the predicted direction, with the FE slope outside the null band.
  - **ALIVE-SMALL:** p < 0.05, with the FE slope inside the null band. It's real but too small to matter even at
    3× amplification, so it counts as not usable for the go/no-go.
  - **ALIVE-REVERSED:** p < 0.05 in the opposite direction, outside the band.
  - **DEAD:** the 2-SE interval is inside the null band.
  - Otherwise **INCONCLUSIVE**.
  - Every line reports both p and the FE slope.
- **Sensitivity (not scored):** a cluster bootstrap over launches (ruling D).
- v1_check refuses a partial batch unless `--allow-partial` is given, and then prints NOT SCORED on every line.

## Conditional starts session (ruling C, pre-registered, not an interim look)
Only if reaction_speed or mistakes comes out INCONCLUSIVE after the 12 launches: a starts session of 1-lap restarts,
about 2 min each. The same assignment generator, measures and analysis apply. It is sized and approved before it runs.

## Hours
- **One launch** takes about 36 min:
  - launch overhead about 8.7 min, including race 1's rundown;
  - race 1 about 6.5 min (5 laps at Austria, green lap about **[discovery]** s);
  - 3 × (a restart of about 0.5 min + a race of about 6.5 min).
- **12 launches ≈ 7.2 h**, plus skipped-intro retries (the 300 s cool-down, #144) and Tyler's daily 1 h pause.

## Not in V-1
- Realistic values, strength and stacking with community add-ons (item 3, the compat audit).
- Other tracks.
- The other `ai_driver_config` keys, and splitting the bundles' keys (V-2 if a bundle is ALIVE).
- Interaction effects (not scored).
- No interim analysis before the last launch.
