# S-1 pre-registration: a screen of six per-driver `ai_driver_config` keys

**Status: APPROVED (supervisor, 2026-11-17)**, with one fix and two additions, applied below. It follows the supervisor's
rulings on #181. Written from repo files only (no game, launcher or `swofty` call). The design, sources and size
reasoning are in [verve_s1_design.md](verve_s1_design.md). The frame is V-1's ([verve_v1_prereg.md](verve_v1_prereg.md),
`tools/v1_check.py`).

**Purpose.** A SCREEN: it finds the keys that are ALIVE at their extremes. It doesn't set out to prove anything DEAD.
DEAD is reported where the bands allow it. Any result other than ALIVE means "not a lever we'll use for now".

**Accepted by the supervisor (2026-11-17):** the COMMIT key, the TRAIN drop, the smoke's HIGH half from
`draw(2026111707, 1)`, stall stepping on the stalled cars' levels, the PENA decision (§6), the seeds, and the order below.

**Order** (each step is gated on the one before):
1. Approval of this prereg (done, 2026-11-17).
2. The key-cache prefill (§7).
3. The **stock baseline** (§3).
4. The **bands amendment PR**, merged; it's committed before S-1 launch 1.
5. The **extremes validity smoke** (§4), plus a levels amendment if any step was taken.
6. **S-1**: 16 launches × 4 races.

No band or level changes once any S-1 race has been seen.

## 1. Factors (6, one key each, no bundles)

HIGH is the "more" end. Levels follow the design's rule: the most extreme value a shipped source uses, else ×0.25 / ×4 of
stock. Stock values are from `docs/stock/ai_driver_config.csv`, which the 26566308 re-dump found identical.

| Factor | Key (`ai_driver_config.`…) | Stock | HIGH | LOW | Source of the levels | Reader |
|---|---|---|---|---|---|---|
| YIELD | `alongside.yield_overtake_rate` | 1 | 0.5 (holds the line) | 2 | lap1-ai R:68; V-1's mirror | tick-read |
| EXIT_ERR | `exit_fallibility.throttle_error_qualifying_race` | curve (design §1) | `@v2@minx:0,maxx:1,miny:-1,maxy:1,0:0,0:0,1:1,1:1` (more errors) | `@v2@minx:0,maxx:1,miny:-1,maxy:1,0:0.48,0:0.48,1:0.48,1:0.48` | the curve's own axes; 0.48 = the stock median level | decoded (F-05) |
| OVERLAP | `overtake.overlap_percentage` | curve 0.567 → 0.05 | flat 0.05 (commits early) | flat 0.9 | lap1-ai R:56; B-0017 draft | tick-read, decoded (F-07) |
| BLK_SPEED | `blocking.blocking_speed_differential` | 0.6 | 0.15 (defends against smaller threats, by hypothesis) | 2.4 | ×0.25 / ×4 (no shipped value) | tick-read, sign unknown |
| BLK_THREAT | `blocking.blocking_threat_time_modifier` | 0.175 | 0.7 (sees threats earlier, by hypothesis) | 0.04375 | ×4 / ×0.25 | tick-read, sign unknown |
| COMMIT | `overtake.braking_zone_abort_overtake_time` | 0.6667 | 0.1 (commits later into the braking zone) | 1.0667 | lap1-ai R:46; kizi Big's passive end (×1.6) | unproven |

Flat curves use V-1's point format (`v1_make.flat_curve`) on each key's own axes.

**Dropped:**
- **BAD_START**: C-1 covers starts.
- **TRAIN**: it doesn't cost nothing, so by the ruling it's out.
  - As designed, it was a 3-key bundle, which the ruling bars.
  - Cut to one key, its only cited extreme is one-sided (lap1-ai), so LOW would be stock.
  - It acts on train escape and passing, the same mechanism and measures as OVERLAP's and COMMIT's primary (passes made). That adds variance there.
  - Its reader is unproven, and its primary (`train_s`) needs new tooling.

**COMMIT is cut to a single key.**
- `braking_zone_abort_overtake_time` is the one key where both shipped sources agree on the sign: lap1-ai 0.1, and kizi's aggressive end ×0.4.
- `close_range_car_lengths_to_start_overtake` alone at 4.0 would break start ≤ continue (stock continue is 2). Keeping that constraint would need a second key, which would make a bundle.

**Ops.** 6 keys × 19 AI drivers = 114 ops per launch. Every driver gets HIGH or LOW for every factor, and no level is
stock. `check_applied` checks the two curves (EXIT_ERR, OVERLAP) by key only, because a curve's value isn't logged. The
gamedb count is 56 + the ops found, per launch.

**Hard rule.** No op touches `cede_position.*`, `yellow_flag_*` or `flying_lap_yield_*`. The FORBIDDEN regex from
`v1_make.py` stays, and the selftest asserts it.

## 2. Design, seeds and size

**Assignment.**
- Per factor, per launch, `draw(seed, launch)`: in each of the 9 two-AI teams, a seeded coin puts one teammate HIGH and the other LOW.
- Alonso alternates HIGH / LOW by launch, with a seeded phase per factor. So each factor has 9 or 10 cars HIGH.
- Factors are drawn independently. `draw` is pure, with the seed string `verve-s1|{seed}|{launch}`.
- Roster and teams are `v1_make.TEAMS`; Stroll is the player.

**Seeds.**
- **S-1: 2026111706.**
- **Extremes smoke: 2026111707**, launch number 1.
- The stock baseline needs none.
- Each seed is recorded in `seed.txt` before its first launch.

**Route** (V-1's, unchanged): `harness/sessions/v1_austria_4races.plan`.
- Spectator garage start, Custom grid with the player last, Austria (track 17), 5 laps, difficulty 100, weather LOCKED, profile `verve-test`, the save sandbox.
- A race-1 `@sessioncheck`.
- The launcher at its current pinned version. A change is recorded, and runs pause for the supervisor.

**Size: 16 launches × 4 races = 64 races.** That's about 9.5 h at about 35 min a launch.

**Validity.** Each race is checked as in V-1:
- `tools/aionly_check.py` per race uid;
- the session check (rerun once on a failure; failing twice is a stop);
- weather LOCKED per launch capture;
- the per-launch build check (`check_applied`);
- saves and tyler.json guards;
- an invalid launch is rerun with the same seed and launch number.

The analysis needs all 16 complete launches. No interim looks: `s1_check` exits 3 on a partial batch. `--allow-partial`
prints NOT SCORED on every line.

Stalled AI cars (§4's definition) are reported per race (accepted). They don't invalidate a race (V-1's rules), but more
than one stalled race in a launch stops the batch for the supervisor.

**Stall sensitivity (not scored).** `s1_check` recomputes every factor's result without the races that had a stalled
car: the same statistic, permutation test and labels on the remaining valid races. It prints that result on a
SENSITIVITY line beside each primary. The decision stays the primary's, on all valid races.

## 3. Stock baseline, and the band computation (fixed now; the baseline only plugs in numbers)

**Run.** 2 launches × 4 races, 5 laps, no add-on:

    powershell -File tools/v1_run.ps1 -StockSmoke -Launch <1|2> -Batch runs/<date>-S1-baseline -Plan harness\sessions\v1_austria_4races.plan -LaunchMinutes 80

- `-LaunchMinutes 80` is V-1's default. `-StockSmoke` otherwise defaults to C-1's 16-minute start plan.
- The build check is gamedb 56 with no verve add-on, and the same validity as §2.
- At least 6 of the 8 races must be valid. Otherwise the short launch is rerun once.

**Statistics.** All are over the valid races, the 19 AI cars only (the player car is never scored), and computed with S-1's
own measure code (`s1_check --baseline`, which is v1_check's measures).
- **Per driver-race:** the mean over all (AI car, valid race) pairs, NA excluded. That's up to 19 × 8 = 152 values.
  - `passes_made`: race_feel `held_passes_net_2plus`. Its mean M_p.
  - `held_behind_s`: race_feel `train_s_behind`. Its mean M_h.
  - `contacts`: race_feel per-car `collisions`, i.e. COLL events involving the car. Its mean M_c.
  - `exit_all_kph`: reported. It is relative to the field median, so its mean is about 0 by construction.
- **Per race:** C_race = the mean over the valid races of the race's total COLL events (race_feel summary
  `guards.collisions`). The smoke rule in §4 uses it.

**Bands** (half-widths, applied to the FE slope):

| Primary | Band | V-1-based expectation |
|---|---|---|
| contacts (YIELD) | max(0.15, 0.25 × M_c) | 0.25 × 0.583 = 0.146, so 0.15 |
| exit_all_kph (EXIT_ERR) | max(2.0, 0.25 × \|mean\|) | the mean is about 0, so the floor of 2.0 km/h applies |
| passes_made (OVERLAP, COMMIT) | 0.25 × M_p (no floor ruled) | 0.25 × 0.98 = 0.245 |
| held_behind_s (BLK_SPEED, BLK_THREAT) | max(25, 0.25 × M_h) | 0.25 × 142.7 = 35.7 s |

The amendment PR writes M_p, M_h, M_c, C_race and the four bands, rounded to 3 significant figures, into this file and into
`s1_check`'s NULL_BAND. It's merged before the smoke.

## 4. Extremes validity smoke (validity only, never analysed for effects)

**Run.** One launch, the first 2 races of the V-1 plan, with seed 2026111707:

    v1_run -Make s1 -Launch 1 -Batch runs/<date>-S1-smoke -Seed 2026111707 -Plan <a 2-race copy of the V-1 plan>

**Assignment.** `draw(2026111707, 1)`.
- For each factor, a seeded coin per team puts one teammate HIGH, and Alonso is placed by the seeded phase. That "seeded half" carries the factor's HIGH extreme.
- The other half carries its LOW extreme.
- So every car runs every factor at one of its two extremes, exactly as in an S-1 launch.

**PASS needs all of these, in both races:**
1. **The race finishes:** `aionly_check` PASS for the race uid. That means at least 18 AI cars at LapData status 3, the live checks, no SCAR, and no player COLL or PENA.
2. **No stalled or stuck AI:**
   - A stall is any AI car with less than 1 m of LapData totalDistance gain in any 30 s window, while it isn't in the pit lane (pitStatus 0).
   - The window runs from lights out to that car's finish or the leader's finish, whichever is earlier.
   - An AI car that retires (any non-finished result status) also counts.
3. **Contacts not absurd:** the race's total COLL events must be at most 3 × C_race.
4. **The session check, weather LOCKED, the build check and the saves / tyler.json guards are all OK.** A failure here is a harness failure, not a factor failure: the smoke is rerun once with the same seed, and failing twice is a stop.

**If it fails, step the implicated levels toward stock, then re-smoke with the same seed.**
- **The step:** halve the distance to stock.
  - Scalar keys move in log space: x_new = stock × (x / stock)^0.5.
  - Curves move pointwise in y on the union of the stock and extreme x points: y_new = stock + 0.5 × (y − stock).
  - Each level has at most 2 steps, i.e. 1 → 0.5 → 0.25 of its log or y distance.
  - A level that still fails at 0.25 is set to stock. A factor with both levels at stock is dropped from S-1, and the drop is recorded.
- **Which levels are implicated:**
  - A stall or a race that doesn't finish implicates every factor, at the level the stalled car(s) held.
  - Contacts above 3 × C_race implicate each factor's **predicted contact-raising extreme**, named by value in the table below. EXIT_ERR is excluded: it's implicated only through a stall. The two-sided factors step BOTH extremes.

  | Factor | Contact-raising extreme stepped on excess contacts | Why |
  |---|---|---|
  | YIELD | 0.5 (low yield; §1's HIGH) | yields less when alongside: the predicted contact side (§5) |
  | OVERLAP | flat 0.05 (§1's HIGH) | commits with little overlap |
  | COMMIT | 0.1 (§1's HIGH) | aborts later into the braking zone |
  | BLK_SPEED | both: 0.15 and 2.4 | sign unknown (two-sided) |
  | BLK_THREAT | both: 0.7 and 0.04375 | sign unknown (two-sided) |
  | EXIT_ERR | none (excluded) | throttle errors, no contact mechanism; stall rule only |

**The steps, pre-registered:**

| Factor | Level | Step 1 | Step 2 |
|---|---|---|---|
| YIELD | HIGH 0.5 | 0.707 | 0.841 |
| | LOW 2 | 1.414 | 1.189 |
| OVERLAP | HIGH flat 0.05 | the stock curve's points moved halfway toward 0.05 | a quarter of the way |
| | LOW flat 0.9 | halfway toward 0.9 | a quarter of the way |
| EXIT_ERR | HIGH diagonal | halfway between stock and the diagonal | a quarter of the way |
| | LOW flat 0.48 | halfway toward 0.48 | a quarter of the way |
| BLK_SPEED | HIGH 0.15 | 0.3 | 0.424 |
| | LOW 2.4 | 1.2 | 0.849 |
| BLK_THREAT | HIGH 0.7 | 0.35 | 0.247 |
| | LOW 0.04375 | 0.0875 | 0.124 |
| COMMIT | HIGH 0.1 | 0.258 | 0.415 |
| | LOW 1.0667 | 0.843 | 0.75 |

`s1_make --step` writes the stepped curves exactly. Any level change goes into a second amendment PR before S-1 launch 1.
The smoke's measures are never looked at for effects, and its data never enters S-1.

## 5. Measures and decision rules (as V-1)

Each factor has one primary with its predicted sign at HIGH. The two blocking keys are two-sided.

| Factor | Primary | Predicted (HIGH − LOW) | Secondaries (estimate, SE, p; never a decision) |
|---|---|---|---|
| YIELD | contacts | + | passes_suffered, held_behind_s, costly_contacts, front_wing_added |
| EXIT_ERR | exit_all_kph | − | laptime_sd_s, offtracks_spins, offtracks, spins, entry_all_kph, contacts |
| OVERLAP | passes_made | + | contacts, costly_contacts, gain_lap1, passes_suffered |
| BLK_SPEED | held_behind_s | two-sided (hypothesis +) | passes_suffered, contacts, passes_made |
| BLK_THREAT | held_behind_s | two-sided (hypothesis +) | passes_suffered, contacts, passes_made |
| COMMIT | passes_made | + | contacts, costly_contacts, gain_lap1 |

All factors also get the common secondaries: gain_t1, gain_lap1, laptime_sd_s and penalties. Penalties is the count of PENA
per car of any code, descriptive only (§6). The measure definitions are v1_check's MEASURES and race_feel's columns.

**Statistic and test** (v1_check's `analyse`).
- The launch is the block.
- Per factor: average each driver's measure over the launch's valid races, centre each driver's launch-means across launches (driver fixed effects), then take the mean over launches of (mean centred value at HIGH − mean at LOW).
- The permutation test uses **10,000 redraws**. Each redraw replaces every launch's assignment with `draw(seed_k, launch)` for a fresh seed_k. The p-value is two-sided.
- SE = the SD of the permutation null. The FE slope's SE comes from its own permutation null.
- α = 0.05 per factor. No multiplicity correction, because it's a screen (accepted). **Any ALIVE factor is CONFIRMED in a focused follow-up before it goes into a Verve Drivers release.**

**Labels.** The p-value comes from the centred statistic; the band comparison uses the FE slope.

| Label | Rule |
|---|---|
| ALIVE | p < 0.05, the predicted direction, FE slope outside the band |
| ALIVE-SMALL | p < 0.05, FE slope inside the band (real, but too small to use) |
| ALIVE-REVERSED | p < 0.05, the opposite direction, FE slope outside the band |
| DEAD | FE slope ± 2 SE(FE) entirely inside the band |
| INCONCLUSIVE | anything else |

For the two-sided factors (BLK_SPEED, BLK_THREAT), ALIVE takes either sign and the sign is reported; there's no
ALIVE-REVERSED. Any result other than ALIVE means "not a lever we'll use for now".

**Operating characteristics** (context, not rules). Scaled from V-1's variance components, at 16 × 4 (design §3):

| Primary | SE(FE) | Band (V-1-based) | Effect detected about 80% of the time | Chance of DEAD under a true zero |
|---|---|---|---|---|
| passes_made | 0.068 | 0.245 | 0.30 /race | ≈0.9 |
| held_behind_s | 7.1 s | 35.7 s | 42 s | ≈1.0 |
| contacts | 0.051 | 0.15 | 0.19 /race | ≈0.64 |
| exit_all_kph | 0.23 km/h | 2.0 | 2.2 km/h | ≈1.0 |

## 6. Guards, the PENA reading, and gaps

**PENA: the repo doesn't settle the enum.**
- The decoder reads only the field order: penalty_type, infringement, vehicle, other, time, lap, places (`tools/udp_parse.py:105-107`).
- No file in `tools/` or `docs/` maps the codes to names. The only readings are marked "from memory of the spec" (`runs/2026-11-03-direct-start/summary.md:34`).
- So S-1 uses **no PENA codes**. The only PENA guard is aionly_check's existing "any PENA for the player car, lights out to the end = FAIL" (`tools/aionly_check.py:224-235`).
- The per-car PENA counts (any code) are reported, descriptively only.
- The "5/4 = small-collision warning, 4/12 = yellow-flag time penalty" reading in the design doc is unverified. Nothing here relies on it.

**Gaps, recorded plainly.**
- There is **no per-driver key for wet skill**: `wet_weather_ability` is a dead map and per package, and the wet error cap is per car.
- There is **no per-driver key for tyre management**: `driver_strategy.*` holds pit and strategy choices.
- S-1 can't address either.
- Out of scope, for later: parsing tyre wear from CarDamage. `tyresWear` f32[4] is in the packet (`tools/udp_parse.py:59-61`), but only the summed `tyresDamage` is recorded (`:196`).

## 7. Key-cache prefill and tooling (to build after approval; none is built here)

**Prefill.**
- Create `docs/stock/s1_paths.txt` (with `s1_make --paths`): 19 drivers × 6 keys = 114 `select.field` paths.
- 38 are already in `docs/stock/v1_key_cache_26566308.csv`: overlap_percentage and yield_overtake_rate.
- The other **76** (exit_fallibility, the two blocking keys and the abort time) are read-only `db get`s, about 2 min.
- The 247 in the design doc assumed 8 factors with bundles.
- It runs **in the gap after C-1 launch 2, with nothing running** (no game, launcher or other `swofty`):

      powershell -File tools/check_applied.ps1 -PrefillOnly docs/stock/s1_paths.txt -KeyCache docs/stock/v1_key_cache_26566308.csv

**Tooling needed.**
- **`tools/s1_make.py`**, v1_make-style:
  - the six factors of §1, with `draw(seed, launch)` and the seed string `verve-s1|…`;
  - `assignment.csv` and `expected_ops.csv`; no trait or map ops;
  - `--paths`, and `--step <factor>:<level>:<k>` for the §4 steps;
  - a selftest covering stock values, curve format, FORBIDDEN, teammate split, Alonso's alternation, 114 ops and no bundles.
- **`tools/v1_run.ps1`**: add `s1` to `-Make`'s ValidateSet. `gen\verve.s1-L<LL>` gets the id `verve.s1-l<LL>`.
- **`tools/s1_check.py`**, v1_check-style:
  - the §5 PRIMARY, two-sided labels, secondaries and NULL_BAND;
  - `costly_contacts`, `front_wing_added` and `penalties` taken from race_feel rows;
  - stall reporting, and the stall SENSITIVITY line (§2);
  - `--baseline`, which writes the §3 statistics and the bands.
- **`harness/sessions/s1_smoke_2races.plan`**: V-1's 4-race plan cut to its first 2 races, otherwise unchanged.
- **The smoke check** (`s1_check --smoke`, or `tools/s1_smoke_check.py`): the four PASS rules of §4 per race, the implicated levels on a FAIL, and the next step's values.
