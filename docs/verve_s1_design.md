# S-1 design: a screen of the per-driver `ai_driver_config` families (DRAFT)

**Status: DRAFT design; the supervisor's rulings (#181) are in [verve_s1_prereg.md](verve_s1_prereg.md), which supersedes §3 here. Nothing runs.** Desk work from repo files only (no game, launcher or `swofty`
call). Paths are repo-relative. Nothing here is pre-registered; a prereg follows only if the supervisor approves the
design.

**Why this lever.**
- V-1 (F-48): the six `driver_characteristics` overrides had no measurable effect in GP on 26566308.
- D4 (F-50): the racecraft rating did nothing measurable to start reaction either.
- D1 (F-49): per-driver `ai_driver_config.race_start` reaction bounds DO act in GP on 26566308 (+0.467 / +0.453 s).

So Verve Drivers is built on per-driver `ai_driver_config` rows. S-1 asks which of the other families also act.

## 1. What can be set per driver

Every key is set as `entrants.drivers.driver[_metadata_=<label>].ai_driver_config.<family>.<key>`. A plain `set`
resolves the key by hash (`docs/ai_driver_config_keys.md`, header). 15 keys typed "float" in the catalogue are really
`@v2@` curves and must be written as curves (`docs/stock/README.md`).

**Per driver in stock?** None of these keys varies by driver.
- All 84 keys were identical on default_driver, Verstappen, Bearman and Alonso on 25251167 (`docs/stock/ai_driver_config.csv`).
- The 26566308 re-dump found them identical again, on 9 rows and against 25251167 (`docs/stock/README_26566308.md`, "Not done yet").
- The RE note says they're identical on all 197 rows.

So every family below is **stock-uniform**. Today only a community add-on varies any of them per driver: kizi's
"drivers differ" writes three keys (`docs/community/kizi.ai-driver-behaviour.md`).

**How the reader evidence is labelled.**
- **tick-read**: Swofty's AI guide lists a proven consumer that reads the key every tick (`docs/community/swofty_19_ai_learnings.md` §1).
- **decoded**: our RE notes decode the consumer (F-05, F-07).
- **proven**: a pre-registered batch showed an effect.
- **off**: Swofty found no AI-vs-AI reader.
- **unproven**: no consumer has been found.

Ratings are the catalogue's A/B/C.

| Family | Key group (stock) | Racecraft meaning (plausible) | Reader evidence | Rating |
|---|---|---|---|---|
| overtake (19) | `overlap_percentage` (curve over aggression, 0.567 → 0.05) | overlap needed to commit alongside | **tick-read + decoded** (F-07); V-1 ATTACK bundle INCONCLUSIVE | A |
| | commitment windows: `attacker_close_enough_car_lengths` 3, `close_range_car_lengths_to_start/continue_overtake` 1.5 / 2, `braking_zone_abort_overtake_time` 0.6667 | when an attack starts, continues or aborts | unproven | B |
| | `regular_/danger_overtake_{initiate,continue,full_heat}_time_adjustment` 0.75 / 1.25 / 0.95 and 0.5 / 0.75 / 0.5; `danger_overtake_buffer` 0.5 | timing of a regular or "danger" pass; sign unknown | unproven | B (full_heat C) |
| | `regular_/danger_overtake_pull_out_time` (curves, axis maxy 4) | when the car pulls out of the tow | unproven | B |
| | `concede_speed_diff` (curve), `concede_slowdown_speed_diff` 1.75, `concede_time_vs_behind` (curve) | when an attacker gives up | unproven | B / B / C |
| | `oppertunist_overtake_time` 0.25, `oppertunist_overtake_track_speed_difference` 12 | passing a slow or damaged car | unproven / **off** | B |
| blocking (16) | `max_blocking_distance(_at_race_start)` 18 / 18 | how far back a defender reacts | **tick-read**. F-44: practical null on 25251167. V-1 DEFEND bundle INCONCLUSIVE, leaning the wrong way | B |
| | `fraction_of_follow_speed(_at_race_start)` 0.975 / 0.875 | speed the defender holds while blocking | **tick-read**; in V-1's DEFEND bundle | C |
| | `blocking_speed_differential` 0.6, `blocking_threat_time_modifier` 0.175 | the closing speed or threat time that triggers a block | **tick-read**, sign unknown | B |
| | `start_blocking_maximum_time_to_corner` 8, `start_blocking_minimum_time_to_corner` (curve), `start_blocking_intersection_time` 1.1 | the window in which a block may start (the min is rules-adjacent) | unproven / unproven / **off** | B / C / B |
| | `blocking_offset_from_car_behind`, `end_blocking_time_to_corner_vs_offset`, `merge_back_to_racing_line` (curves); `blocking_variable_offset_fraction` 0.5; merge rates 7 / 3.5; `avoidance_decrease_rate` 1 | block geometry and the merge back to the line | unproven (merge_back **off**) | C (variable_offset B) |
| space_seeking (13) | `total_queue_needed` 3, `car_in_front_needed` 2, `speed_below_follow` 4, `first_speed_below_follow` 2, `time_to_switch_sides` 2, `concede_overtake_blocked_by_crowed_time` 5 | when a car stuck in a train looks for another line | unproven | B (car_in_front C) |
| | `can_start_track_radius` 400, `track_distance_needed` 170, `track_abort_distance` 50, `distance_braking_point` 75, `added_buffer` 0.05, `cars_moving_away_speed_to_ignore` 5, `remember_crowed` 4 | geometry of the space search | unproven (remember_crowed **off**) | C (radius B) |
| alongside (8) | `yield_overtake_rate` 1, `speed_difference_for_limited_zone_yielding` 3 | how fast a car alongside gives way; the second only in limited-overtake zones | **tick-read**; yield was in V-1's ATTACK bundle | B / C |
| | `min_presence_within_buffer` (flat 0.33), `steering_understeer_offset` 0.3, 4 controller curves | what counts as alongside; steering while alongside | **off** / unproven | C |
| divebomb_defense (4) | `max_presence_alongside` (curve), `max_time_to_ignore` 5, `max_track_offset` 1.75, `max_track_radius` 160 | reaction to a divebomb | **off** (read only by the human-divebomb behaviour) | B / B / C / C |
| exit_fallibility (2) | `throttle_error_qualifying_race`, `throttle_error_practice` (curves, x 0..1, y −1..1) | random throttle error once per corner exit. Capped per car, scaled by the control map, suppressed above 23° yaw | **decoded** (F-05), never written, not a live field | A |
| offset_variation (7) | `max_offset` 1.33, `offset_limit_at_corner_start` 0.2, `offset_limit_blend_distance` 250, 4 curves | how far a car wanders off the ideal line | unproven (no parser found, L0); a `cars::live` slot exists | B (max_offset), C |
| race_start (9), for completeness | reaction bounds 0.04 / 0.28, 0.24 / 0.42; bad-start bounds 0.04 / 0.06, 0.28 / 0.42; `stationary_vehicle_space` 0.25 | launch reaction and bad-start size | **proven**: reaction in GP on 26566308 (D1), bad start in benchmark only (B-0007); stationary_vehicle_space: leave stock | A / C |

**Excluded, never written (hard rule):** the whole `cede_position.*` family (6 keys), which includes
`yellow_flag_ramp_up_time` and `flying_lap_yield_to_human_track_speed_diff`, plus any other `yellow_flag_*` or
`flying_lap_yield_*`. The generator's FORBIDDEN regex (`tools/v1_make.py`) stays, and the selftest asserts it.

**Count.** 8 families are settable per driver: 7 beyond race_start, plus race_start. That's 78 keys once cede_position is out.
- tick-read: 9 keys in 3 families (overtake, blocking, alongside): overlap_percentage, the 6 named blocking keys and the 2 alongside yield floats.
- proven in races: 1 family (race_start; reaction in GP on 26566308 by D1).
- decoded but never written: 1 family (exit_fallibility).
- reported "off": 1 whole family (divebomb_defense) and 5 single keys.
- no reader found: everything else.

**What Tyler cares about, mapped to families.**

| Trait | Families that plausibly drive it | Note |
|---|---|---|
| Mistakes / errors | **exit_fallibility** (corner-exit errors); race_start bad-start bounds (start mistakes); offset_variation.max_offset (scrappy lines, unproven) | lock-ups and spins: no per-driver key found. The spin angle `lost_control.angle` is per CAR (`ai_vehicle_config`) |
| Defending | blocking threat keys and follow speed (tick-read); `alongside.yield_overtake_rate` (holding the line when alongside) | max_blocking_distance: F-44 null; divebomb_defense is off |
| Overtaking aggression / commitment | `overtake.overlap_percentage` (tick-read); commitment windows and abort time; space_seeking (leaving a train) | the last two are unproven; kizi and swofty.lap1-ai write some of these |
| Consistency | exit_fallibility (lap-time and exit spread); race_start bound spread (proven); offset_variation; `blocking_variable_offset_fraction` | |
| Wet skill | **no per-driver key found** | `wet_weather_ability` is a dead map and per package. The wet error cap `max_throttle_error_by_grip_wet` is per car. S-1 is dry-locked anyway |
| Tyre management | **no per-driver key found** | `driver_strategy.*` is per driver, but it holds pit and strategy choices (e.g. `safety_car_pit_wear_min/max`), not driving wear |

## 2. What the UDP measures can see

From `tools/race_feel.py`, `tools/v1_check.py` and `tools/udp_parse.py`.
- **Stock-ish level**: the V-1 per-race mean per driver over 912 driver-races (`runs/2026-11-17-V1/v1_check/per_race.csv`). All six traits were DEAD there, but the maps were ×3 and the bundles were on.
- **SE**: V-1's SE(FE) for one balanced factor at 12 launches × 4 races.

| Measure (tool) | V-1 level | V-1 SE | Families it can see (expected sign at the "more" level) |
|---|---|---|---|
| passes made, net held, laps 2+ (`held_passes_net_2plus`) | 0.98 | 0.079 | overtake overlap and commitment (+), space_seeking (+) |
| passes suffered (`held_suffered_net_2plus`) | 0.98 | 0.118 | blocking (−), alongside yield (− when the car yields less) |
| held behind: s others spend within 1 s behind (`train_s_behind`) | 142.7 s | ≈8.2 | blocking (+), yield (+). Relative to its mean, it's about 2× more precise than passes suffered |
| own train time (`train_s`) | not in v1_check | n/a | space_seeking and commitment (−) |
| lap-time SD, laps 2+ | 0.656 s | ≈0.032 | exit_fallibility (+), offset_variation (+) |
| corner exit / entry pace vs the field (`exit_all_kph`, `entry_all_kph`) | ±2 km/h band | 0.26 | exit_fallibility (− exit pace) |
| contacts (COLL); costly contacts, front-wing damage (CarDamage) | 0.583 | ≈0.059 | yield (+ when the car yields less), overlap and commitment (+), blocking (+) |
| penalties (PENA) | rare | n/a | contact-type aggression only (see below) |
| off-tracks (surfaceType ≥ 2 unpaved wheels), spins (slip ≥ 60°) | 3 events in all 48 races | n/a | exit_fallibility (+). Below the floor: V-1 fell back to exit pace |
| start: reaction_s, launch_m, speed_1s_kph, gain_t1 | launch_m band ±0.5 m | 0.11 m | race_start (bad start: − launch_m) |
| lock-ups | **not visible** | | the UDP has no lock-up event, Motion has no per-car wheel slip, and MotionEx is the player's car only |
| tyre wear | **not parsed** | | CarDamage `tyresWear` f32[4] is in the packet, but `udp_parse` logs only the summed `tyresDamage` u8. No per-driver key anyway, and 5 laps is too short |

**What the AI actually emits as penalties** (events.csv, all valid races):
- On 25251167:
  - B-0015 had 6 PENA in 20 races: 5 were type 5 / infringement 4 and 1 was 4 / 12.
  - B-0016 had 27 in 20 (26 of type 5 / 4), almost all on lap 1.
- On 26566308:
  - B-0018 had 0 in 10 races.
  - The V-1 Austria discovery had 1 in 2 (4 / 12, lap 1).
- Read with the EA spec enums as we remember them (**not settled by the repo**; the prereg uses no PENA codes, see [verve_s1_prereg.md](verve_s1_prereg.md) §6): 5 / 4 is a warning for a small collision, and 4 / 12 is a 3 s time penalty for ignoring yellow flags.
- No corner-cutting PENA ever appears for the AI, and LapData's cornerCuttingWarnings and currentLapInvalid never move for AI cars (Phase 0, 0 in 510k car-frames).
- So penalties are a guard, never a primary. Contacts carry the "clean" signal.

## 3. Proposed S-1 screen (DRAFT)

**Frame (V-1's, unchanged).**
- 19 AI drivers, Stroll is the player.
- Per factor and per launch, a seeded coin in each of the 9 two-AI teams puts one teammate HIGH and the other LOW. Alonso alternates by launch, so each factor has 9 or 10 cars HIGH.
- Factors are drawn independently. `draw(seed, launch)` is pure.
- Austria, 5 laps, 4 restart-races per launch on the V-1 route (`harness/sessions/v1_austria_4races.plan`): spectator garage start, difficulty 100, dry LOCKED, race-1 session check.
- Driver fixed effects; the launch-blocked permutation test (10,000 redraws); V-1's labels (ALIVE / ALIVE-SMALL / ALIVE-REVERSED / DEAD / INCONCLUSIVE). One primary per factor.
- **No trait writes and no map writes.** Both are DEAD, and the ×3 maps may have inflated V-1's pass rate.

**Level rule.** Each factor uses the most extreme value a shipped source uses: swofty.lap1-ai, kizi, B-0007, B-0015 or the B-0017 draft. With no such source, it uses ×0.25 / ×4 of stock (the catalogue's trace suggestion is ×0.5 / ×2). HIGH = the "more" end (holds the line, errs more, commits earlier).

| Rank | Factor | Key(s) | HIGH / LOW (cited range) | Primary (sign at HIGH) | Null band | Key secondaries | Persona |
|---|---|---|---|---|---|---|---|
| 1 | YIELD | `alongside.yield_overtake_rate` | 0.5 / 2 (lap1-ai R:68; V-1's mirror) | contacts (+) | ±0.15 /race (25% of 0.583) | passes_suffered (−), held_behind_s (+) | Max HIGH (hard to pass); Lewis LOW (clean) |
| 2 | EXIT_ERR | `exit_fallibility.throttle_error_qualifying_race` | diagonal `0:0,0:0,1:1,1:1` / flat 0.48 (on the curve's own axes, y −1..1; stock sits at 0.415-0.55 for u in 0.15-0.92, with tails to 0 and 1) | exit_all_kph (−) | ±2 km/h (prereg) | laptime_sd_s (+), offtracks_spins (+), spins | Max and Lewis LOW (rare mistakes) |
| 3 | OVERLAP | `overtake.overlap_percentage` | flat 0.05 / flat 0.9 (lap1-ai R:56; B-0017) | passes_made (+) | 25% of S-1's stock rate (±0.25 at V-1's 0.98) | contacts (+), gain_lap1 (+), train_s (−) | Lewis LOW (less aggressive) |
| 4 | BLK_SPEED | `blocking.blocking_speed_differential` | 0.15 / 2.4 (×0.25 / ×4; no shipped value) | held_behind_s (+), two-sided | ±25 s (17.5% of 142.7) | passes_suffered (−), contacts | Max HIGH if alive |
| 5 | BLK_THREAT | `blocking.blocking_threat_time_modifier` | 0.7 / 0.044 (×4 / ×0.25) | held_behind_s (+), two-sided | ±25 s | passes_suffered (−), contacts | Max HIGH if alive |
| 6 | BAD_START | `race_start.{min,max}_bad_start_{lower,upper}_bound`, all four equal | 0.60 / 0.01 (B-0007 pins, performance 40-99) | launch_m (−) | ±0.5 m (prereg v3) | speed_1s_kph, gain_t1 | Max LOW (rare start mistakes) |
| 7 | COMMIT | `overtake.braking_zone_abort_overtake_time`, `close_range_car_lengths_to_start_overtake`, `..._to_continue_overtake` | 0.1 / 4.0 / 4.5 (lap1-ai R:46-48) vs 1.067 / 0.825 / 1.1 (kizi Big's passive end: abort ×1.6, start ×0.55; continue ×0.55 by the same ratio) | passes_made (+) | as OVERLAP | contacts (+) | Lewis LOW |
| 8 (optional) | TRAIN | `space_seeking.{time_to_switch_sides, total_queue_needed, concede_overtake_blocked_by_crowed_time}` | 0.3 / 1 / 60 (lap1-ai R:57, 59, 61) vs stock 2 / 3 / 5 | train_s (−) | 25% of the stock-smoke mean | passes_made (+) | either |

Ranks 1-3 have readers (tick-read or decoded) and map straight onto the persona goals. Ranks 4-5 are tick-read but have
an unknown sign, so they're read two-sided. Rank 6 needs only the start, and the reader is proven in benchmark. Ranks 7-8
have no reader found, so a null there means "unproven reader", not "no effect". There are 15 keys, so at most 285 ops
per launch, about 255 in practice (V-1 had 235): TRAIN's LOW is stock, so its LOW cars get no ops.

The EXIT_ERR levels hold whether or not the curve's y values are normalised to its axis (the open question in
`docs/community/swofty.lap1-ai.md`). Flat at the stock median removes the tails, and the diagonal makes large errors
common. `check_applied` checks curves by key, not by value.

**Size.** Scaled from V-1's variance components (driver-centred launch means; `per_race.csv`). The between-launch
share is 40% for passes made, 69% for passes suffered and held_behind, 1% for contacts and 42% for lap-time SD.
- So more launches help everything, and more races per launch help contacts most.
- P(DEAD | true 0) = P(|est| + 2·SE ≤ band).

| Launches × 4 races | SE passes_made | DEAD chance at ±0.10 / ±0.25 | held_behind ±25 s | contacts ±0.15 | lap SD ±0.10 s | Time (≈35 min per launch, D4's 70 min for 2) |
|---|---|---|---|---|---|---|
| 12 (V-1) | 0.079 | 0.00 / 0.76 | 0.70 | 0.40 | 0.72 | ≈7 h |
| **16 (proposed)** | 0.068 | 0.00 / 0.91 | 0.87 | 0.64 | 0.88 | ≈9.5 h |
| 24 | 0.056 | 0.00 / 0.99 | 0.98 | 0.88 | 0.98 | ≈14 h |
| 30 | 0.050 | 0.01 / 1.00 | 0.99 | 0.95 | 1.00 | ≈17.5 h |
| 60 | 0.035 | 0.60 / 1.00 | 1.00 | 1.00 | 1.00 | ≈35 h |

- **A ±0.10 pass band is not resolvable at any practical size.**
  - 2·SE reaches 0.10 only at about 30 launches × 4 races (120 races), and even then DEAD needs an estimate of almost exactly 0.
  - A 60% chance of DEAD needs about **60 × 4** (240 races) or 42 × 8.
  - Passes suffered never resolves ±0.10, even at 60 launches.
- **Recommendation:**
  - Fix the pass bands at 25% of the stock rate. One stock-smoke launch (`v1_run.ps1 -StockSmoke`, 4 races, no add-on) measures that rate blind to any assignment.
  - Use held_behind_s, not passes suffered, as the defending primary.
  - Run **16 launches × 4 races** (plus the smoke, plus a launch-1 readback).
  - If the supervisor wants contacts at about 0.9, run 24.
- These SEs assume V-1-like noise. Several live factors at once would add some.

**Keys not to combine** (so sign-uncertain keys can't cancel; the B-0015 v2 ruling):
- `blocking_speed_differential` and `blocking_threat_time_modifier` (both "trace sign"): separate factors, never one bundle.
- `overlap_percentage` and `yield_overtake_rate`: V-1 bundled them as ATTACK. Its contacts lead (+0.174, p 0.002, an unscored secondary) can't be attributed, so S-1 splits them.
- `max_blocking_distance` and `fraction_of_follow_speed`: V-1's DEFEND leaned the wrong way (+0.16 passes suffered, SE 0.11). If either is retested, do it alone (a swap candidate for TRAIN).
- In space_seeking, `speed_below_follow`, `first_speed_below_follow` and `can_start_track_radius` have lap1-ai's sign opposite to the catalogue's hypothesis. Keep them out of TRAIN.
- Don't bundle the `regular_/danger_*_time_adjustment` keys, or the concede keys (sign unknown).
- Constraints, not cancellations: close-range start ≤ continue; leave `start_blocking_minimum_time_to_corner` stock.
- Don't write `driver_characteristics.control` alongside EXIT_ERR: its map scales the error. Don't write reaction bounds alongside BAD_START: that's C-1's lever.

**Tooling (to build after approval; nothing is built here).**
- `tools/s1_make.py`, forked from `v1_make.py`:
  - FACTORS = the table above; seed string `verve-s1|{seed}|{launch}`; `assignment.csv` and `expected_ops.csv`; no trait or map ops.
  - The selftest checks stock values against `docs/stock/ai_driver_config.csv`, the curve format (`is_value`), the FORBIDDEN regex, teammate splits and Alonso's alternation.
  - It writes no op equal to stock.
  - `--paths` writes `docs/stock/s1_paths.txt`.
- **Key cache:** `docs/stock/v1_key_cache_26566308.csv` already holds `overlap_percentage` and `yield_overtake_rate` for the 19 drivers.
  - The other 13 keys need `check_applied.ps1 -PrefillOnly docs/stock/s1_paths.txt -KeyCache docs/stock/v1_key_cache_26566308.csv`: 247 read-only `db get`s, about 6 min at 1.4 s each.
  - It runs only with nothing running, on the supervisor's go. It doesn't run now.
- **`tools/v1_run.ps1`:** add `s1` to `-Make`'s ValidateSet. The gamedb count is 56 plus the ops found, per launch.
- **`tools/s1_check.py`**, forked from `v1_check.py`:
  - The new PRIMARY, NULL_BAND and secondaries.
  - Add `train_s`, `penalties`, `costly_contacts` and `front_wing_added` from race_feel's rows.
  - Optional, for the supervisor: a grid-slot covariate, which cuts the cell-mean variance by 6-34% here (passes made 12%, held_behind 34%).
  - Band bases read from the stock-smoke output.

**Open for the supervisor:**
- 7 or 8 factors (TRAIN, or a lone `fraction_of_follow_speed`).
- The band rule.
- 16 or 24 launches.
- Whether the ×0.25 / ×4 levels for the two blocking keys need a one-launch validity smoke first, checking DNFs and costly contacts.
