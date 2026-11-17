# Verve Drivers: lever evidence table (draft)

Draft, 2026-11-16. Built only from files already in `verve-f1-25` (no game, launcher or GitHub access). Paths are
repo-relative.

**Product.** "Verve Drivers" means real-driver personalities by season, written as per-driver values into the game
database. It should work alone or alongside community add-ons. Today the converter (`verve_to_swofty.py`) writes
exactly two things per driver:
- the six `driver_characteristics.*` on the driver row (stock + 0.5 x (signal - grid mean), clamped 0..1);
- the `pace` rating `evolution` curve, shifted, in both the `default` and `2026` datasets.

It writes nothing in `ai_driver_config.*`, `driver_strategy.*`, the parameter maps or the form curves.

## Status rules

| Status | Meaning here |
|---|---|
| **PROVEN IN RACES** | A pre-registered batch passed its own criterion with a measurable effect in a race session. The context (benchmark or Grand Prix) and the build are named. |
| **LOADS BUT UNMEASURED** | The write is applied (gamedb overwrite count, arm check or `check_applied`), but no race effect has been shown. This includes levers that were tested and came out INCONCLUSIVE. An inconclusive batch is not proof either way. |
| **DEAD IN STOCK** | The stock data makes the lever a no-op: all four map corners are equal, so the characteristic can't change the output. |
| **UNKNOWN** | Never written by any batch, or the evidence is static (RE or docs) only. |

**Build caveat, applies to every row.** Every race result below is on build **25251167** (F-33..F-44 and all batches
B-0001..B-0016). The game is now **26566308** (1.0.145).
- Re-dumped on the new build and found identical, line for line: only the converter's two anchors,
  `docs/stock/26566308/driver_characteristics_grid.csv` and `pace_curves_grid.csv` (`docs/stock/README.md`).
- Not re-dumped on 26566308: the parameter maps, the `ai_driver_config` keys and the override curves.
- No Verve write has been run or checked for application on 26566308.
- The harness change on the new build is in `docs/harness.md`: `ai_drives_player` is unavailable on 26566308, so the
  B-0014..B-0016 setup can't be rerun as it was. AI-only racing now uses the spectator garage start (F-45, F-46).

**Context caveat.** Benchmark is a procession: no overtaking, laps limited by the train (F-41,
`runs/2026-10-31-B-0013/summary.md`). Benchmark is valid for race-start draws only. In Grand Prix, only the
`race_start` reaction bounds have a pre-registered pass (B-0012b).

---

## 1. Driver-row characteristics and the rating route

| # | Verve trait | Game lever | Evidence | Status |
|---|---|---|---|---|
| 1.1 | Launch sharpness (converter: 0.6 Aggression + 0.4 Pace) | `entrants.drivers.driver[...].driver_characteristics.reaction_speed` | **B-0006:** ROW slope -0.109 s per unit, z -4.6; it rests mostly on Tsunoda (`runs/2026-10-30-B-0006/summary.md`). **B-0008:** -0.118 s, z -6.8, every leave-one-level-out slope negative (`runs/2026-10-30-B-0008/summary.md`). **B-0010:** -0.086 s for 0.10 to 0.90, z -10.9 (`runs/2026-10-31-B-0010/summary.md`). F-36. The measured effect is on the logged reaction draw, not on launch speed. | **PROVEN IN RACES**: benchmark starts only, 25251167. Not tested in Grand Prix. |
| 1.2 | Start consistency / mistake resistance (0.6 (1-Risk) + 0.4 Consistency) | `...driver_characteristics.mistakes` (a skill: higher = fewer mistakes, F-29) | **B-0004:** ROW gap +7.79 race_start_performance, z 2.30, marginal; two of five leave-one-start-out drops fall under 2 SE. **B-0009:** b slope -0.059 per unit, z -4.3 (`runs/2026-10-30-B-0009/summary.md`). **B-0010:** -0.060 b, z -5.4. It doesn't move reaction (F-40 rejected by B-0010). F-37, F-38. The only measured effect is on the bad-start draw b, which is an input. Whether b costs time is open (#4). No racecraft or mistake behaviour has been measured. | **PROVEN IN RACES**: benchmark start draw only, 25251167. |
| 1.3 | Aggression (Verve Aggression) | `...driver_characteristics.aggression` | **Loads:** gamedb 60 = 52 + 8 in every B-0014 race, arm check 4+4 (`runs/2026-11-14-B-0014/score.txt`). **B-0014** (Grand Prix, Austria, difficulty 100, 20 races, 1.0 vs 0.05): held-pass coefficient +0.018 (SE 0.154), INCONCLUSIVE, practical null (any effect at most about 15%), F-42. The B-0013c benchmark probe (aggression 1.0 on two cars) showed no pass, but benchmark is a procession. | **LOADS BUT UNMEASURED** (tested; no effect shown) |
| 1.4 | Control / consistency (0.7 Consistency + 0.3 (1-Risk)) | `...driver_characteristics.control` | **Loads:** B-0011 build check, 136 written characteristics value-checked (`runs/2026-10-31-B-0011-check/check_applied.txt`); B-0013c gamedb 62 = 52 + 10. **No race effect:** the only extreme test, B-0013c (control 1.0, benchmark), ran in a procession, so it is invalid for behaviour (`runs/2026-10-31-B-0013/summary.md`). Never written in a Grand Prix batch. | **LOADS BUT UNMEASURED** |
| 1.5 | Entry speed (Pace) | `...driver_characteristics.speed_in` | **Loads:** as 1.4. **B-0013c** (benchmark procession): Alonso at 0.02 averaged 80.13 s vs 79.83 s stock, with order unchanged. Not interpretable (F-41). | **LOADS BUT UNMEASURED** |
| 1.6 | Exit speed (0.8 Pace + 0.2 Consistency) | `...driver_characteristics.speed_out` | As 1.5 (B-0013c: Alonso 0.02; Colapinto and Russell 1.0, never passed). | **LOADS BUT UNMEASURED** |
| 1.7 | (alternative route) ratings to characteristics | `driver_statistics...DriverStatisticsHolder[driver=..].StatisticsDataSet[default,2026].Statistic[racecraft / awareness].evolution` | **STATS arms:** B-0001 Sauber minus Racing Bulls -0.039 s, reversed (`runs/2026-10-30-B-0001/summary.md`); B-0004 awareness gap +5.23, z 0.75; B-0006 slope +0.068, confounded by the untouched rows. The writes applied (64 overwritten). "No rating effect detected, not proven absent" (F-36). The converter doesn't write these. | **LOADS BUT UNMEASURED**: benchmark starts only. Grand Prix untested (Q-02 for ratings). |
| 1.8 | (global) rating-to-characteristic shape | `driver_statistics.driver_statistics.driver_characteristic_overrides.DriverCharacteristicOverride_0..5.distribution` | Dumped only (`docs/stock/driver_characteristic_overrides.txt`). Global, not per driver. Never written. | **UNKNOWN** |

**Precedence ("rows win", F-36).** Supported in benchmark for two characteristics on start draws: reaction_speed
(B-0006, replicated in B-0008) and mistakes (B-0004, B-0009). It is not shown in Grand Prix or career, and not for
aggression, control, speed_in or speed_out on any metric.

The whole Verve Drivers mechanism rests on rows being what the AI reads. In Grand Prix, no batch has yet shown a row
characteristic changing anything.

## 2. Parameter maps (per car package, not per driver)

Path: `entrants.vehicles.vehicle_packages.vehicle_package_N.ai_vehicle_package_config.driver_parameter_maps.<map>.{low,high}_difficulty_{low,high}_characteristic_mapping`.
These are the transfer functions from a driver's characteristic to a controller factor. Verve doesn't write them.
Stock values: `docs/stock/driver_parameter_maps_f1_2025.txt` (vehicle_package_10, build 25251167, not re-dumped on
26566308). Static evidence: F-03, HANDOFF §2.4.

| # | Verve trait expressed through it | Map (input characteristic): stock hi-difficulty low / high | Evidence | Status |
|---|---|---|---|---|
| 2.1 | Entry speed | `braking_distance_factor` (speed_in): 1.15 / 1 | Static only. Never edited. No consumer of the evaluated maps found (HANDOFF §2.5: "+0xc0..+0xe8, writer not found"). | **UNKNOWN** |
| 2.2 | Exit speed | `corner_curvature_factor` (speed_out): 0.92 / 1 | Static only | **UNKNOWN** |
| 2.3 | Aggression | `follow_speed_factor` (aggression): 1.05 / 1 | Static only. Indirect: the B-0014 aggression null (1.3) suggests a small effect on passes. | **UNKNOWN** |
| 2.4 | Aggression | `alongside_space_factor` (aggression): 1.15 / 1 | As 2.3 | **UNKNOWN** |
| 2.5 | Control | `throttle_confidence` (control): 0.96 / 1 | Static only | **UNKNOWN** |
| 2.6 | Control | `throttle_exit_fallibility` (control): 1 / 0.75 | Static only. It scales the exit-error curve (F-05). | **UNKNOWN** |
| 2.7 | Control | `throttle_on_time` (control): 0.6 / 0 | Static only | **UNKNOWN** |
| 2.8 | Control | `brake_off_time` (control): 0 at all four corners | `driver_parameter_maps_f1_2025.txt`; F-03 | **DEAD IN STOCK** |
| 2.9 | Control | `slide_confidence` (control): 1 at all four corners | same | **DEAD IN STOCK** |
| 2.10 | Control | `alongside_awareness` (control): 1 at all four corners | same | **DEAD IN STOCK** |
| 2.11 | Wet skill | `wet_weather_ability` (control): 1 at all four corners | Same. No consumer found either (F-03, Q-07). | **DEAD IN STOCK** |

So of control's seven maps, four are dead in stock and three are untested. The six maps that still separate drivers at
high difficulty (2.1-2.4, 2.6, and 2.5/2.7 weakly) have never been tested in a race.

## 3. Race start (the F-38 / F-39 formula)

| # | Verve trait | Lever | Evidence | Status |
|---|---|---|---|---|
| 3.1 | Launch sharpness and its spread | `...driver[...].ai_driver_config.race_start.{min,max}_reaction_time_{lower,upper}_bound` (stock 0.04 / 0.28, 0.24 / 0.42) | **B-0005** (benchmark): 9 tagged cars at exactly 0.650000 in both starts. Vehicle 19, the player car, ignores the tag (`runs/2026-10-30-B-0005/summary.md`, F-33, F-34). **B-0012** (direct-start Grand Prix): 5/5 pass, but no launch happens in that state. **B-0012b** (menu Grand Prix, pre-registered on #70): 5/5 pass, 9 cars at 0.650, 0 untagged; it answers Q-02 for these keys (`runs/2026-11-03-B-0012b/summary.md`). Equal bounds pin the draw. **D1** (GP, spectator route, 26566308, pre-registered, #170): 0.65 on one teammate per team gave **+0.467 / +0.453 s** UDP reaction vs stock, 8/8 races valid, 36/36 ops value-checked; the pinned cars read an identical 0.936 s in both launches (`runs/2026-11-17-D1/summary.md`, F-49). | **CONFIRMED PER-DRIVER START LEVER**: benchmark and GP on 25251167 (the logged draw), and **GP on 26566308** (D1, measured on track via UDP). C-1 will calibrate game time to UDP reaction and launch distance. |
| 3.2 | Start consistency (bad-start spread) | `...race_start.{min,max}_bad_start_{lower,upper}_bound` (stock 0.04 / 0.06, 0.28 / 0.42) | **B-0007** (benchmark, pre-registered): race_start_performance = 100 x (1 - b) exactly, with pinned values 99 / 85 / 65 / 40 on every start (`runs/2026-10-30-B-0007/summary.md`, F-38). | **PROVEN IN RACES**: benchmark only, 25251167. Never written in Grand Prix. |
| 3.3 | (model) predicted mean start per driver | F-39: reaction ~ U[0.28 - 0.24 k rs, 0.42 - 0.18 k rs]; b ~ U[0.06 - 0.02 k m, 0.42 - 0.14 k m]; k about 0.52 | **Stock-field fit:** 368 samples (`runs/2026-10-30-start-model/summary.md`). **B-0011**, the converter's own addon, 30 starts (`runs/2026-10-31-B-0011/summary.md`): per-driver r 0.663, pass; b k 0.477, pass. | **PROVEN IN RACES** for means and ordering: benchmark, 25251167 |
| 3.4 | (model) exact edges, and b's k for written rows | as 3.3 | **B-0011** reaction envelope **FAIL** (pre-registered): 11 of 540 samples outside, 9 below the lower edge by 0.005-0.013 s. Written-row b k: 0.48 (B-0011), 0.70 (B-0009), 0.93 (B-0010). Unresolved (F-39, #55). | **UNKNOWN** (the exact form failed its check) |
| 3.5 | Does a bad start cost anything? | b draw to launch speed and places | Open (#4). No batch measured it. | **UNKNOWN** |
| 3.6 | Does a slow reaction cost anything? | reaction draw to launch speed and places | B-0012b exploratory UDP, *not pre-registered*: tagged cars (0.650) were at 12.8-13.0 km/h at 1 s vs 19.3-20.0 for the others, and gained -0.3 to -1.0 places by 6 s, in all 5 starts. The grid differs between starts. **D1 secondaries (not scored), GP on 26566308:** −8.18 / −7.60 km/h at 1 s and −1.85 / −1.64 places to T1 for the pinned cars. | **STRONG LEAD**, consistent across two builds (secondaries, not yet pre-registered as primaries) |

The converter's predicted start spread is small: sd 0.014 s for reaction and 0.007 for b over the grid, at gain 0.5
(`README.md`). Even the proven levers give modest differences between drivers as the converter writes them today.

**C-1 calibration (F-51):** UDP reaction = game-time race_start reaction + 0.285 s (slope 0.998, linear over
0.20-0.65 s). The stock game-time draw has a median of about 0.18 s (the fastest per start about 0.10 s, the slowest
about 0.30 s).

**V-2 start design notes** (supervisor, 2026-11-17; notes, not a prereg):
- **Use BOUNDS, not pins**, so starts keep their natural variation. For example:
  - Max [0.06, 0.14];
  - an average driver at about the stock spread, [0.10, 0.30];
  - a weak starter [0.18, 0.40].
  - The exact values come from the season profiles later.
- **Below 0.20 s is untested.** Before V-2 relies on about 0.10 s, a tiny **C-1b** on the start-only route: pins
  0.05 / 0.10 / 0.15 plus stock, 1 launch × 20 starts, with C-1's checks and rules. It's queued after S-1, or in any gap
  where S-1 can't run. It needs a short prereg addendum to C-1 (self-merge OK if it only adds levels and keeps C-1's
  rules).
- **launch_m is a separate input** (C-1: not a pure function of reaction). Open question: does any key move it, perhaps
  race_start's other keys? That's a desk check of the race_start family for launch or throttle keys in the dump.

## 4. Per-driver `ai_driver_config` (84 keys, none written by the converter)

Path: `entrants.drivers.driver[_metadata_=<label>].ai_driver_config.<group>.<key>`. Keys resolve by hash (F-11, F-31).
All 84 are identical on the four dumped rows (`docs/stock/ai_driver_config.csv`, 25251167). Catalogue:
`docs/ai_driver_config_keys.md`.

"Tick-read" and "off" below are Swofty's desk-review claims (`docs/community/swofty_19_ai_learnings.md` §1), not our
measurements.

| # | Verve trait | Keys | Evidence | Status |
|---|---|---|---|---|
| 4.1 | Defending (Aggression) | `blocking.max_blocking_distance` (stock 18) | **Loads:** gamedb 60, arm check 4+4, all 20 races dry. **B-0015** (Grand Prix, Austria, difficulty 100, 45 vs 5): train time -18.7 s (SE 17.0), 2-SE [-52.8, +15.3], INCONCLUSIVE; practical null, an increase above about 8% ruled out (`runs/2026-11-15-B-0015/README.md`, `score.txt`, F-44). Swofty: tick-read. | **LOADS BUT UNMEASURED** (tested; no effect shown) |
| 4.2 | Lap-1 defending | `blocking.max_blocking_distance_at_race_start` (stock 18) | Stock in B-0015. Swofty says it is read until the race-start state machine ends. B-0016 tested swofty.lap1-ai, which sets this key and others as a *live layer*, not a database write: INCONCLUSIVE, weather-confounded, dry-only estimate about 0 (F-43). That is not evidence for a database write. | **UNKNOWN** |
| 4.3 | Defending style | `blocking.{fraction_of_follow_speed, fraction_of_follow_speed_at_race_start, blocking_speed_differential, blocking_threat_time_modifier}` | Swofty: tick-read, proven consumers. Never written by us. | **UNKNOWN** |
| 4.4 | Overtake commitment (Aggression) | `overtake.overlap_percentage` (curve; stock 0.567 at x=0 down to 0.05 at x=1) | Decoded consumer, evaluated at x = effective aggression within 0.5 lap (F-07). Swofty: tick-read. B-0017 is a draft only. | **UNKNOWN** |
| 4.5 | Overtake willingness / risk | the other 18 `overtake.*` keys (close-range windows, abort time, `*_time_adjustment`, pull-out times, concede, opportunist) | No consumer traced (catalogue B/C). Swofty: `oppertunist_overtake_track_speed_difference` is "off". Note: kizi.ai-driver-behaviour writes `close_range_car_lengths_to_start_overtake` and `braking_zone_abort_overtake_time` per driver (`docs/community/kizi.ai-driver-behaviour.md`), so load order decides who wins. | **UNKNOWN** |
| 4.6 | Yielding when alongside | `alongside.{yield_overtake_rate, speed_difference_for_limited_zone_yielding}` | Swofty: tick-read. Never written by us. | **UNKNOWN** |
| 4.7 | (geometry) | the other 6 `alongside.*` keys | C-rated. Swofty: `min_presence_within_buffer` is "off" vs AI. kizi writes it on every row. | **UNKNOWN** |
| 4.8 | Traffic / train behaviour | `space_seeking.*` (13) | No consumer found. Swofty: `remember_crowed` is "off". | **UNKNOWN** |
| 4.9 | Divebomb defence | `divebomb_defense.*` (4) | Swofty: read only by the human-divebomb behaviour, so likely inert AI vs AI. | **UNKNOWN** |
| 4.10 | Corner-exit consistency | `exit_fallibility.throttle_error_qualifying_race`, `throttle_error_practice` (curves) | Decoded consumer, once per corner exit, capped per car (F-05; catalogue A). Never written. Not exposed live. | **UNKNOWN** |
| 4.11 | Line consistency | `offset_variation.*` (7) | Parser not identified (L0) | **UNKNOWN** |
| 4.12 | (rules; never personality) | `cede_position.*` (6), `race_start.stationary_vehicle_space` | Leave stock (HANDOFF §6) | **UNKNOWN** |
| 4.13 | (reported inert) | `blocking.start_blocking_intersection_time`, `blocking.merge_back_to_racing_line` | Swofty: "off", no AI-vs-AI reader | **UNKNOWN** |

Of the 84 keys, only the 8 `race_start` bounds have proven per-driver readers in our data (3.1, 3.2). One more,
`max_blocking_distance`, provably loads.

## 5. Race form and pace evolution

| # | Verve trait | Lever | Evidence | Status |
|---|---|---|---|---|
| 5.1 | Pace (season ranking) | `DriverStatisticsHolder[driver=..].StatisticsDataSet[_metadata_=default].Statistic[_metadata_=pace].evolution` (shifted stock curve) | **B-0011 check:** the curves were written at the right key, but their values aren't logged (`check_applied.txt`: 27 written, 19 dropped as equal to stock). No measurement of any effect. Simulated sessions use ratings per the docs (F-18, static). Ratings don't drive the live start draws (F-36). | **LOADS BUT UNMEASURED** (key level only) |
| 5.2 | Pace, 2026 season | same, `StatisticsDataSet[_metadata_=2026]` (24 holders, F-30) | Written by the converter, and covered by the same check. The set is tagged `game_setup_modes f1_26` / `season_2026`. Which mode reads it is unknown (Q-11). | **LOADS BUT UNMEASURED** (key level only) |
| 5.3 | Season-to-season development | the curve's shape over x = 0..10 seasons | Static only (F-26, `docs/std` per HANDOFF §11). Career is parked (#31). | **UNKNOWN** |
| 5.4 | In-race form | `ai.driver_variation.in_race.graphs.driver_variation_in_race_N` (84 global curves) | Global selection, no per-driver weighting (F-10). A per-driver form trait needs a native hook. Never written. | **UNKNOWN** |

## Status counts (42 rows)

| Status | Rows | Which |
|---|---|---|
| PROVEN IN RACES | 5 | 1.1, 1.2, 3.1, 3.2, 3.3. All are start draws on 25251167. Only 3.1 is proven in Grand Prix. |
| LOADS BUT UNMEASURED | 8 | 1.3-1.7, 4.1, 5.1, 5.2 (1.3 and 4.1 tested, practical nulls) |
| DEAD IN STOCK | 4 | 2.8-2.11 |
| UNKNOWN | 25 | everything else |

No lever has been shown to change on-track racecraft (passing, defending, pace, mistakes) in any race on any build.

---

## What B-0014 and B-0015 did and didn't show for the 8 roster drivers

Both batches used the same roster and the same crossover (`tools/b0014_check.py` G1 / G2, reused by
`tools/b0015_check.py`).
- **Setup:** menu Grand Prix, Austria, 5 laps, 2025 season, difficulty 100, Stroll's car driven by the AI, 20 races,
  build 25251167.
- **Crossover:** odd races = order a (G1 high, G2 low), even races = order b (swapped), so each driver ran 10 races at
  each level.

| Driver (row) | Group | Stock aggression | B-0014 (`driver_characteristics.aggression`) | B-0015 (`ai_driver_config.blocking.max_blocking_distance`, stock 18) |
|---|---|---|---|---|
| carlos_sainz-jr | G1 | 0.85 | 1.0 in a / 0.05 in b | 45 in a / 5 in b |
| gabriel_bortoleto | G1 | 0.70 | 1.0 / 0.05 | 45 / 5 |
| isack_hadjar | G1 | 0.60 | 1.0 / 0.05 | 45 / 5 |
| oliver_bearman | G1 | 0.65 | 1.0 / 0.05 | 45 / 5 |
| alex_albon | G2 | 0.81 | 0.05 / 1.0 | 5 / 45 |
| george_russell | G2 | 0.85 | 0.05 / 1.0 | 5 / 45 |
| nico_hulkenberg | G2 | 0.80 | 0.05 / 1.0 | 5 / 45 |
| pierre_gasly | G2 | 0.85 | 0.05 / 1.0 | 5 / 45 |

Sources: `harness/addons/verve.b0014a/db/b0014a.json`, `harness/addons/verve.b0015a/db/b0015a.json`, and
`docs/stock/driver_characteristics_grid.csv` for stock aggression.

**B-0014 (#71): INCONCLUSIVE** (`runs/2026-11-14-B-0014/score.txt`, F-42).
- **Primary,** held passes laps 2-5: +0.018 per driver-race (SE 0.154). The within-driver high minus low difference
  is +0.000 held passes and -0.187 net positions.
- **Fragile sign:** it doesn't hold at both 5 s and 20 s.
- **Secondaries,** not registered as the verdict: collisions -0.263 (SE 0.145), lap-1 passes made -0.70.
- **Weather** wasn't checked. B-0014 has no `weather.txt`, and the dry rule came only after B-0016 found random
  Grand Prix weather.

**B-0015 (#100 v4): INCONCLUSIVE, practical null** (`runs/2026-11-15-B-0015/README.md`, `score.txt`, F-44).
- **Primary,** train time behind the driver: -18.7 s (SE 17.0, 2-SE [-52.8, +15.3]), against a stock mean of about
  186 s. That points the opposite way to the prediction, not significantly.
- **Secondaries:** passes suffered net -0.05; no contact cost.
- **Validity:** all 20 races dry. The launcher changed after race 1 (1.9.55 to 1.9.56); a not-scored sensitivity
  analysis left the verdict unchanged.

**What can be claimed, per driver.**
- For each of the 8 drivers, the written value was applied in every race of both batches: arm checks 4+4, gamedb 60.
- Pooled over the 8 drivers at Austria, difficulty 100, on 25251167:
  - aggression 1.0 vs 0.05 changed held passes by at most about 15% of baseline;
  - blocking distance 45 vs 5 did not raise train time behind them by more than about 8%.

**What cannot be claimed.**
- **No driver-level effect,** in either direction. Neither batch registered or reported a per-driver estimate. Any
  per-driver split now would be post hoc, on 10 races per arm.
- **No proof of absence.** Neither batch is FAIL-NULL. B-0014's 2-SE interval just exceeds +-0.3, and B-0015's
  reaches past -40 s.
- **Not transferable.** Neither result carries over to other tracks (Austria only), other difficulties, wet races
  (B-0014's weather is unknown), the current build 26566308, or Verve's own values. Verve moves aggression by small
  amounts around stock, not 0.05 to 1.0, and never writes blocking distance.
- **No personality.** Nothing about the 8 drivers' "personality" (e.g. "Russell defends harder") is supported by
  these batches.

---

## Gaps for V-1 (aliveness unproven; test with extremes first)

Run each lever at its extremes (0 vs 1 for characteristics; stock-relative extremes or flat 0 / flat 1 curves for
config keys) in a Grand Prix on 26566308. Use the AI-only garage start (F-46), dry locked, with a pre-registered
criterion. Order follows Verve's dependence on each lever.

1. **Row precedence in Grand Prix:** row `reaction_speed` and `mistakes` 0 vs 1, read from RaceStarts. The whole
   product depends on rows being read outside benchmark. Repeat with STATS arms (racecraft / awareness 0 vs 1) to
   settle Q-02 / Q-17 for Grand Prix. This is cheap and needs no new metric.
2. **Row `speed_in` 0 vs 1:** braking point by lap distance (map 2.1 predicts about 15% longer braking at 0).
3. **Row `speed_out` 0 vs 1:** corner speed / exit, map 2.2.
4. **Row `control` 0 vs 1:** exit throttle ramp and exit errors, maps 2.5-2.7. This also tests whether
   `throttle_exit_fallibility` is live.
5. **`exit_fallibility.throttle_error_qualifying_race`:** a flat-high curve vs a flat-0 curve on the same drivers.
6. **`overtake.overlap_percentage`:** flat 0 vs flat 1 (the B-0017 draft). This is the decoded aggression consumer.
7. **`blocking.max_blocking_distance_at_race_start`:** extremes on lap 1 (the database write, not lap1-ai's live
   layer).
8. **Other tick-read keys:** `blocking_speed_differential`, `blocking_threat_time_modifier`,
   `fraction_of_follow_speed`, `alongside.yield_overtake_rate`.
9. **Bad-start bounds in Grand Prix, and launch cost:** pin b at 0.01 vs 0.60, then measure speed at 1 / 3 s and
   places by 6 s (closes 3.5). Re-run 3.6 as a pre-registered test.
10. **Parameter-map liveness (per package, not per driver):** set one live map's hi-difficulty corners to an
    extreme (e.g. `braking_distance_factor` hi/lo 2.0). Run the Q-07 test (`wet_weather_ability` 0.5 vs 1, wet race)
    for the dead maps.
11. **Pace rating:** does the shifted `pace` curve change simulated or skipped sessions (F-18)? And which mode reads
    the `2026` dataset (Q-11)?
12. **Re-dump on 26566308** before any of the above: the parameter maps, the 84 `ai_driver_config` keys and the
    override curves (only the two converter anchors were re-checked).
13. **Run alongside community add-ons:** kizi.ai-driver-behaviour writes overlapping `ai_driver_config` keys on
    every row. No batch has run Verve together with any community add-on, so "works alongside" is untested.

## After V-1 (supervisor, 2026-11-17)

**V-1 result (F-48, #169):** in GP on 26566308 (the spectator route), the six `driver_characteristics` overrides at 0/1
with ×3 maps showed no measurable effect. Whether the overrides reach the per-car AI record is untested. D1 (a GP
positive control) and D2 (a benchmark replication of B-0008) are pre-registered in
[verve_d1_d2_prereg.md](verve_d1_d2_prereg.md).

**Takeaways from the desk research** ([community/racecraft_research_2026-11-17.md](community/racecraft_research_2026-11-17.md), #171):
- **Racecraft per-vehicle aggression** (`ai::VehicleConfig.racecraft.{overtake,defend}_aggression`) exists on paper
  only ("ships later"), and would be per VEHICLE anyway, shared by teammates. **Dropped.**
- **`cars::live` is OFF on 26566308.** Live per-car layers aren't an option on this build, which blocks any native,
  live approach.
- **The D3 native probe of the per-car AI record is NOT approved:** high risk, layouts proven for the KB build only.
  Revisit only if D1/D2 leave H1 vs H2 open.
- **The AI driver profile is built at session enter, from the entrant's row, after the DB edits apply.** So "our ops
  arrive too late" is ruled out.
- **Three unproven candidates for a GP-only loss of the override:**
  - (a) the in-race driver variation record outranks the override (on in Race, off in Time Trial);
  - (b) `driver_statistics.driver_characteristic_overrides` maps the racecraft/awareness ratings onto the traits;
  - (c) game-mode fields (`benchmark`, `timetrial`, `driver_%s_override`).

### D4 outline: a factorial on the ratings (NOT pre-registered; drafted so it's ready)

The supervisor asks for D4 only if D1/D2 point at lead (b): GP derives the traits from the per-driver ratings. Then the
ratings ARE the personality lever. They're per driver and per season dataset, which fits Tyler's season ask.
- **Lever:** the per-driver `driver_statistics` ratings that the `driver_characteristic_overrides` rows map from: the
  racecraft and awareness ratings (and the others in that table), in BOTH datasets (`default` and `2026`).
  - The exact rating → trait pairs come from `driver_characteristic_overrides`; the re-dump on 26566308 (#156) found
    it unchanged.
- **Design:** V-1's factorial frame (a seeded teammate split, a new draw per launch, Austria spectator route, 4 races
  per launch, a launch-blocked permutation test), with ratings at a low and a high anchor instead of traits at 0/1.
  The anchors are set from the override curves so the mapped trait spans most of its range.
- **Primary measures:** reaction via UDP (V-1's definition) for the rating mapped to reaction_speed. For the others,
  V-1's measures for the trait each one maps to.
- **Prior evidence to weigh:** B-0006 (benchmark, 25251167) found the STATS (racecraft rating) slope on reaction at
  **+0.068 s per unit** (SE 0.029), positive and against the row's −0.109. So in benchmark, the rating didn't act like
  the trait. GP may differ (lead (b) is about GP).
- **Size and bands:** set from V-1's variance (per-car SD and launch-level SE), and pre-registered before any run.
- **Product fit:** writing ratings changes what the career/ratings screens show. The build design must say whether
  Verve accepts that, or writes ratings only in race sessions.
