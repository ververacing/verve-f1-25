# V-1 pre-registration (v3): are the driver levers alive? A factorial screen

Status: **v3 for the supervisor's approval** (2026-11-16): every value is filled, and the readback passes. It replaces the v2 draft (#147). It applies the supervisor's
rulings on #147 (A-H), on #148 (bundles, maps, the throttle_exit_fallibility exception), on Phase 0 (size, UDP start
measures, conditional starts session, launch-blocked permutation) and on #155 (mistakes direction, control floor fallback,
corner pace, decision labels, pass null bands). v1_check (#155) is approved; its null simulation gives a false-positive
rate of 4.83% (95% CI 4.26-5.48) over 4,800 null tests. Scope: Verve Drivers (docs/process.md). Evidence base:
[verve_drivers_plan.md](verve_drivers_plan.md).

The **[discovery]** values below come from the Austria discovery launch (16:00-16:06, `runs/2026-11-16-V1-austria-disc`;
2 stock races, both valid). The readback result is below (`runs/2026-11-16-V1-readback`). **The 26566308 stock re-dump (#156) changed nothing** that V-1 uses. The 7 live maps
(all 66 lines), the six characteristics on the 20 f1_2025 seats and the 6 bundle keys on all 21 rows are identical to
25251167, so the tables below stand. **Season:** the 2025 and 2026 grids share the driver rows, so the product keeps
the season option, with 2026 as the default.

**V-1 START RULE** (supervisor): V-1 starts once (i) this v3 is approved, (ii) `@restart` is merged (#153), and (iii) the
v1_make readback passes on 26566308: the package select works, the 235 ops are applied and the gamedb count matches.
v1_check (#155) can follow during the batch, and the supervisor reviews it before any verdict. **No interim looks.**

## Readback (start rule iii): PASS
- **The run:** `tools/v1_run.ps1`, seed 1, launch 1, with the menu-only plan `harness/sessions/v1_readback_menu.plan`
  and the add-on `verve.v1-l01` enabled.
- **check_applied** on its loader.log: 235 ops, **233 applied**:
  - 214 value-checked, including all 7 `vehicle_package_10` map ops, so the package select works, and
    throttle_exit_fallibility at 1.5;
  - 19 overlap_percentage curves written at the right key (the log doesn't show curve values).
- **2 dropped** as equal to stock (reaction_speed), and **0 problems**.
- **gamedb:** 289 overwritten = 56 (the route's stock baseline on 26566308) + 233.
- **Profiles:** the install added a disabled entry to tyler.json and verve-test.json; after the removal both hash
  exactly as before the install. The saves are unchanged.
- **The gamedb count is per launch.** The build drops only some equal-to-stock writes (2 of the 4 here), so each
  launch's expected count comes from its own build check:
  - v1_run runs check_applied after every launch, offline through the 26566308 key cache (#159), and writes
    `gamedb_expected.txt`. v1_check reads it per launch.
  - A failed build check stops the batch (exit 16) and invalidates the launch.

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

## Austria discovery result (runs/2026-11-16-V1-austria-disc, stock, not scored)
- **The plan works at Austria:**
  - The menu path reaches lights out at track 17, difficulty 100, with the weather LOCKED dry.
  - Both races are valid by aionly_check per uid, with 19 of 19 AI finished in each.
- **`@restart` works live** (#153):
  - From race 1's finish to the next race starting took about 26 s.
  - Each race has a new session uid. The grid is the same in both races.
  - The multi-race watcher ended each race on its own uid.
  - The pause menu and the Restart confirm dialog share one screen string (`|pause|#ba16bc16|`), so `@restart` checks
    only that each A press is on the pause stack.
- **Green lap:** 69.8 s and 69.4 s (median of the field). The lap-1 loss is 5.1 s and 5.7 s.
- **Stock net held passes on laps 2+:** 8 and 15 per race, a mean of 11.5. That's inside the supervisor's 4-16 range, so
  the ±0.10 pass bands stand, and there is no pass floor.
- **Off-tracks + spins at stock: 0** in both races, so the control floor fallback is likely (it's decided on the batch
  total only).
- **Start measures** (38 car-starts): reaction 0.33-0.57 s, and launch 16.7-23.3 m. The same driver's launch differs by
  an SD of **1.08 m** from one start to the next (19 drivers × 2 starts).
- **Corners** (race_feel brake onsets): 345, 1276, 2075, 2626, 2956, 3699 and 3926 m. The first is at 345-348 m in both
  races.
- **Launch time:** 8.3 min from launch to race 1's start, then 6.0-6.1 min per race.

## Design
- **Size, fixed before race 1:** **12 launches × 4 races** = 48 races, 5 laps, Austria. Races within a launch share the
  assignment and the grid, so they are correlated replicates. More launches buy more than more races per launch.
- **Assignment per launch:** `tools/v1_make.py draw(seed, launch)`, which is pure and seeded.
  - Each factor is 0/1 per driver.
  - In each of the 9 two-AI teams, one coin flip per factor puts one teammate at 1, so teammates always split and the
    car is controlled for.
  - Alonso alternates 1/0 by launch, with a seeded phase per factor.
  - Each factor therefore has 9 or 10 drivers at 1. Factors are drawn independently.
  - **Seed: 20261117**, fixed here before race 1 and recorded in the batch (`seed.txt`). `assignment.csv` is written per
    launch. The readback used seed 1, so no V-1 assignment has been drawn on the game yet.
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

| Bundle | Key (`ai_driver_config.`) | Stock (26566308, all rows) | 0 | 1 |
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

  The stock corners above are the same on 25251167 and 26566308 (#156). The f1_2026 package (vehicle_package_15)
  differs in one value (throttle_on_time hl is 0.2), but V-1 writes vehicle_package_10 only.
  - **The one exception to the cap (ruling on #148): throttle_exit_fallibility.** The cap would make it a no-op
    (hl = ll = 1). "Rare vs frequent mistakes" is a headline trait for Tyler, so its hl corner is set to 1.5
    (0.75 + 3 × 0.25), past ll. The per-car exit_fallibility caps still bound the error.
  - **Fallback:** if the validity stop trips, the first step down is this map back to 1.0 (`v1_make --no-uncapped`),
    then ×2 overall.

## Validity per race (tools/aionly_check.py, per race uid)
- The finish comes from LapData: the leader at position 1 with resultStatus 3, and **at least 18 AI with status 3**.
- Track 17, difficulty 100, weather LOCKED, no pause cut, and gamedb = that launch's `gamedb_expected.txt` with a clean
  build check (check_applied: every op applied, or dropped only as equal to stock).
- **Amendment (2026-11-16, after launch 1; validity tooling only, #162):** weather is checked per launch capture; a
  non-dry race would invalidate its whole launch. It's stricter than per race, so it can only invalidate more. If a
  launch ever reads NOT LOCKED, the supervisor is told before it's dropped, and may ask for a per-uid check. No measure,
  band or decision rule changes.
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
| mistakes | launch (m) | **longer**: mistakes is a skill, higher = fewer mistakes (F-29, F-37) | ±0.5 m |
| aggression | held passes made, net, laps 2+, per race | more | ±0.10 per race |
| control | off-tracks + spins per race (see below) | fewer | ±0.1 per race |
| speed_in | corner-entry pace, all passes, field-relative (km/h) | faster | ±2 km/h |
| speed_out | corner-exit pace, all passes, field-relative (km/h) | faster | ±2 km/h |
| DEFEND | held passes suffered, net, laps 2+, per race | fewer | ±0.10 per race |
| ATTACK | held passes made, net, laps 2+, per race | more | ±0.10 per race |

- **Pass null bands, ±0.10 per driver-race** (supervisor, #155 review; fixed before any V-1 data, so not a look):
  - The rule: 25% of the stock per-driver-per-race mean.
  - At Austria, stock gives about 7.9 net held passes on laps 2+ per race (B-0016 arm A, 55 in 7 dry races), which is
    0.41 per driver per race, so the band is ±0.10.
  - The v2 band of ±0.25 was 60% of the mean: a 35% change in passing would have read ALIVE-SMALL.
  - If the discovery's stock rate is under 4 or over 16 per race, the supervisor re-fixes the band before race 1.
  - aggression and ATTACK share passes_made, which is fine in a factorial; the report shows the two lines side by side.
  - DEFEND's primary isn't normalised by exposure, which randomisation balances in expectation.
- **Launch null band, ±0.5 m (fixed):**
  - It's about 2.5% of a 20 m launch, and about half the 1.08 m start-to-start SD of one driver's launch (discovery).
  - A 0.5 m change is about a car-length ahead after 2 s only in the extreme, so anything inside it is too small to read
    as personality.
  - With 12 launches × 4 starts per driver, the FE slope's SE for launch is expected to be well under 0.5 m, so the band
    can be resolved.
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
- **Pass floor:** the discovery's two stock races average **11.5** net held passes on laps 2+, which is not under 4, so
  there is no floor.
- **Secondaries, all factors, not scored:**
  - speed at 1 s after lights out;
  - positions gained to T1 (at the first lap-1 lapDistance ≥ `T1_M` = **345 m**, the first brake onset in both
    discovery races) and at the end of lap 1;
  - ATTACK's effect on passes suffered, and DEFEND's on passes made (cross-effects);
  - for DEFEND, the seconds attackers are held: race_feel `train_s_behind`, the seconds other cars spend within 1.0 s
    behind the car on laps 2+;
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
- **One launch** takes about 34 min (discovery timings):
  - 8.3 min from the launch to race 1's start, including the intro and the menu;
  - 4 races of about 6.1 min (5 laps, green lap about 69.6 s);
  - 3 restarts of about 0.5 min each;
  - about 1 min for the quit, guard and add-on removal.
- **12 launches ≈ 6.8 h**, plus skipped-intro retries (the 300 s cool-down, #144) and Tyler's daily 1 h pause.

## Not in V-1
- Realistic values, strength and stacking with community add-ons (item 3, the compat audit).
- Other tracks.
- The other `ai_driver_config` keys, and splitting the bundles' keys (V-2 if a bundle is ALIVE).
- Interaction effects (not scored).
- No interim analysis before the last launch.
