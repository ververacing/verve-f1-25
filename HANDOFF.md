# Verve for F1 25: engineering handoff

**Status:** research complete for v0.1, v0.1 data addon built and statically validated, nothing run in-game yet.
**Date:** 2026-10-30. **Author of this document:** Claude (research session for Tyler / TC Verve).
**Audience:** the coding agent or engineer who picks this up. Everything here is meant to be logged to GitHub
issues or a database; `findings.json` is the machine-readable version of the facts, `docs/ai_driver_config_keys.csv`
the per-key catalogue, `RESEARCH_LOG.md` the dated trail.

Read in this order: this file → `README.md` (the v0.1 mapping) → `docs/ai_driver_config_keys.md` → `findings.json`. Sections 9 to 14 (settings surfaces, My Team presets, My Team applicability and season progression, gaps, autonomous harness, other improvements) were added in the same session after the first bundle.

---

## 0. Provenance

| Item | Value |
|---|---|
| Game | F1 25 (Codemasters / EA), Steam build, `F1_25.exe` SHA-256 `d873a1c8d2044cef2fd76c99c9d5a97649c5b815d055540995105f46619865ae`, image base `0x140000000` |
| Mod loader | Swofty Launcher for F1 25, AGPL-3.0 (SDK and template MIT), https://f1.swofty.net, https://github.com/Swofty-Developments/SwoftyLauncher |
| Repo snapshot used | commit `0a071a43397c34378281b247cc10f4ffdfc90101`, 2026-10-31 01:31 +1100, "feat(std): pit lane, tyre refit and audio queue bindings plus session.lap (#567)" |
| Launcher versions | public OverTake listing 1.5.0 (auto-updates); docs describe up to 1.6.11; 1.6.0 is the first with the registry/event design, most of which "ships later" |
| RE evidence levels (Swofty convention) | L0 named only; L1 named statically (decomp or log string); L2 decompiled with an agreeing verification; L3 confirmed by a runtime trace |
| Modded play | offline only; the launcher disables EA's anticheat itself; launching from Steam stays vanilla; not recommended on EA-app installs |

Every address in this handoff is for the build above. The launcher resolves bindings by signature at load time, so addons must never hard-code them.

---

## 1. TL;DR for whoever builds next

1. **The per-driver personality system exists in the game and is almost unused.** Six characteristics (`aggression, control, mistakes, reaction_speed, speed_in, speed_out`, all 0..1) are derived from three ratings and consumed by eleven bilinear (difficulty x characteristic) parameter maps. The driver row carries override fields the stock game never sets. v0.1 writes those overrides from Verve scalars. Pure database addon, no DLL.
2. **84 more per-driver keys (`ai_driver_config.*`) are identical on all 197 stock drivers.** That is the "same decision every time" complaint. 11 of them are decoded (A), 32 are name-obvious (B), 41 should not be touched blind (C). Catalogue in `docs/ai_driver_config_keys.*`. This is v0.2.
3. **The difficulty slider is data, not code.** `tracks.Track_N.ai_track_difficulties.<package>.{time, difficulty_ratio, mass_ratio, max_dificulty_no_balast_slider_position}` are 10-point tables per track per car package. Above slider 100 the AI car gets *lighter* (`mass_ratio` down to ~0.92). This is a strong candidate explanation for the "AI too fast on straights / unfair traction" complaints and the per-track pace swings, and it is editable per track. Hypothesis, needs one trace (see Q-05).
4. **First thing to do with the game installed:** `swofty db get entrants.drivers.driver[_metadata_=max_verstappen]` and dump the stock values of all 6 characteristics, the 84 `ai_driver_config` keys, the 10 `driver_strategy` keys, and the 6 `distribution` curves on `driver_statistics.driver_statistics.driver_characteristic_overrides`. Half of the open questions close with that one command.
5. **Verification is cheap.** The game's own log channels `RaceStarts`, `CANNED_EVENTS`, `AI_VARIATION`, `QUALI_PACE_DEBUG`, `GARAGECREW` can be copied into `swofty/loader.log` by editing `swofty/session.json` (see §7). `RaceStarts` prints every AI driver's reaction time per start, which is a direct readout of `reaction_speed`.

---

## 2. The engine's AI data model (what a modder can touch)

Layers, outermost first. "Edit" says how an addon changes it today (launcher 1.5 style database ops; the 1.6 registry API is design-only for AI).

### 2.1 Global
- `ai.general_ai_settings.{awareness_time 4.0, max_test_distance 20000, max_test_radius 5000, max_test_speed 134.1, max_test_time 300}`: perception/look-ahead. Resolved once by `Ai_Resolve_GeneralSettings` 0x1405fb920 (L2) into `g_Ai_GeneralSettings` 0x146046c50, ~39 call sites. Edit: db `set`, or hook `ai.settings.resolve` (design).
- `ai.behaviour_system.behaviours` (5): BehaviourRace, BehaviourRetire, BehaviourLostControl, BehaviourRecovery, +1.
- `ai.driver_variation.in_race.graphs.driver_variation_in_race_N` (84 rows): race-form curves (`no_variation_100_*`, `consistent_*`, `inconsistent_*`, `bad_start_good_ending`, `mid_race_mistake`, `fuel_saving_*`, `end_race_peak*`, `great_start_then_drops_off_*`, `bad_race_day_*`, `Qualifying_*`, `practice_steady_*`), each with per-session availability flags and a `PreferredTracks` bool. Consumer `Ai_DriverVariationInRace_Update` 0x1409af4c0 (L1): `addedLapTime = (1 - curve(progress)) * lap_time_variations` (default 4 s), per vehicle, enabled per `game_modes` (TimeTrial off, Practice/Qualifying/OSQ/Race on). **Selection is global; there is no per-driver weighting.** This is the game's Consistency axis. Edit: db for the curves and availability; per-driver weighting needs a native hook on the component (v0.3).
- `ai.adaptive_ai.standard_values` (adaptive AI / super slow mode tuning) and `canned_events.Per-race DNFs` (per fault type min/max/duration/chance; accidents SpinOut/SideSwipe; lock-ups per session). Consumer `Ai_CannedEvents_LoadPerRaceDnfs` 0x1409c2b10 (L1).

### 2.2 Per track (`tracks.Track_N`, 43 rows)
- `ai_track_difficulties.<vehicle_package>.{difficulty_ratio[10], mass_ratio[10], time[10], max_dificulty_no_balast_slider_position=100}` for 46 packages incl. `f1_2025_vehicle_package`, `f1_2026_vehicle_package`, `*_equal_performance_*`, `f2_*`, `f1cg_*` (classic). `time` and the slider position are **proven** read by the exe (`tools/gamedb/meanings.tsv`). Example (f1_2025, one track): `time = 87.83, 85.66, 83.56, 81.37, 79.21, 78.10, …`; `difficulty_ratio = 0.41, 0.455, 0.575, 0.655, 0.805, 0.895, 1, 1, 1, 1`; `mass_ratio = 1 x7, 0.980, 0.960, 0.938`. Reading: points 1-7 span the slider up to 100 (skill ratio rises to 1.0), points 8-10 are above 100 where only mass drops. The exact slider→index mapping is not traced (Q-05).
- `ERSSettings.{deployFactor 0.95..1.1, harvestFactor 0.50..1, hotlapFactor 1..1.3}`: per-track ERS multipliers. Direct lever for the straight-line/ERS complaint, per track.
- `ai_track_config.{crowded_rules(5), formation_lap(3), look_ahead(4), recovery(4), safety_car(2), space_lines(3), yield(3)}`: parsed by `Ai_Parse_TrackConfig` 0x140680250 (L1).
- Track markup (overtake zones, racing limits) lives in the track ERP, not the DB; the "More Aggressive AI" track pack edits it.
- Baked AI tables per track per car package (`environment_package/tracks/<t>/ai/<folder>/`: acpd, brpd, ers_boost_data, vp_times, ~7 MB per team per track). These cap pace: a car faster than its baked set gets no benefit from more grip.

### 2.3 Per car (`entrants.vehicles.vehicle_N.ai_vehicle_config`, 30 groups, 218 keys)
Full list: `docs/ai_vehicle_config_keys.csv`. Parsed by `Sess_Parse_AiHandlingConfig` 0x1406828a0 (L2) into `AiHandlingConfig` at `Sess_Load_VehicleAiConfig` 0x1425027e0, once per session. Highlights:
- `ers_use` (26): battery levels per push reason. Decoded consumer `Ai_Ers_DecidePushReasons` 0x1406487a0: stock build-gap 0.7, close-gap 0.6, in/out-lap 0.47, overtake 0.25/0.15/0.30 (plain/xmode_passive/xmode_enabled), **defend 1.0 (only with a full battery)**; target battery 0.9 - 0.4 x lap progress (0.9 - 0.15 x in overtake mode); mode from the per-track ERS table.
- `exit_fallibility` (4): `max_throttle_error_by_mass / by_grip_dry / by_grip_wet / max_yaw_angle_deg`, the per-car caps on the per-driver error curves (§2.5).
- `traction_control.grip_atc_strength` (curve), `pedal_controller`, `steering_pid_settings`, `lost_control`, `drafting` (vs AI and vs human separately, decoded in `Ai_Drafting_Evaluate` 0x140647e60), `swerve`, `race_start`, `under_safety_car`.
- AI-only physics (VTF data, not DB): `BrakeECU.ASCStrengthForAI 0.0, ASCMaxBrakeAI 0.5, ASCMinYawRatioAI 0.25, ASCMaxYawRatioAI 0.75, BrakeMigrationTorqueAI 450`; tyre `SlipRatioMin/MaxLimitAIDegrees`, `WetnessDownslopeFactorAI`, `SpeedDownslopeFactorAI` (the 2025 VTF sets only the non-AI variants at 0.1, so the AI ones take code defaults); `Vehicle.FineUpdateRateAI`, `TyreContactSubStepCycleAI`. No difficulty-keyed grip/power/drag multiplier exists in code (`re/db/subsystems/car.md#ai`).
- Existing addon on this layer: Kizikafuka's "Collision & AI Tweaks" (`kizi.ai-tweaks`): `buffer_space.vehicle_buffer`, `pedal_controller.lateral_traction_slip_angle_cut_in_proportion`, `lost_control.angle`, steering PID scaling, traction control off, plus native contact handling; 13,371 ops across 599 cars in its 1.5 form.

### 2.4 Per car package (`vehicle_package.ai_vehicle_package_config.driver_parameter_maps`, 43 rows)
Eleven maps, each `{characteristic, low_difficulty_low_characteristic_mapping, low_difficulty_high_…, high_difficulty_low_…, high_difficulty_high_…}`, bilinear. Parsed by `Ai_Parse_DriverParameterMap` 0x14065aec0 (11 calls, name table 0x145639210).

| Map | Characteristic | Stock corners (lo/lo, lo/hi, hi/lo, hi/hi) | Effect |
|---|---|---|---|
| braking_distance_factor | speed_in | 2.74..3.9, 2.63..3.72, 1.15..1.25, 1 | low speed_in brakes 15-25% longer even at high difficulty |
| corner_curvature_factor | speed_out | 0.5888, 0.644, 0.92, 1 | low speed_out takes 8% less curvature at high difficulty |
| follow_speed_factor | aggression | 1.4, 1.3, 1.05, 1 | low aggression follows 5% slower |
| alongside_space_factor | aggression | 1.5, 1.25, 1.15, 1 | low aggression leaves 15% more room |
| throttle_confidence | control | 0.78..1, 0.86..1, 0.96..1, 1 | |
| throttle_exit_fallibility | control | 1, 0.75, 1, 0.75 | high control = 0.75x exit errors at any difficulty |
| throttle_on_time | control | 3.96..6.6, 3.62..6.03, 0.12..0.6, 0 | |
| brake_off_time | control | 0, 0, 0, 0 | dead in stock |
| slide_confidence | control | 1, 1, 1, 1 | dead in stock |
| alongside_awareness | control | 1, 1, 1, 1 | dead in stock |
| wet_weather_ability | control | 1, 1, 1, 1 | **dead in stock**; consumer not found either |

Implication: characteristics still separate drivers at difficulty 110 (the hi/lo vs hi/hi columns differ for 6 of 11 maps). Three maps are no-ops and one (wet) is a no-op with no located consumer: candidates for reviving if the consumer exists (Q-07).

### 2.5 Per driver (`entrants.drivers.driver_N`, 197 rows, 129 fields)
- **Ratings**: `driver_statistics.driver_statistics.DriverStatisticsHolder[driver=<label>].StatisticsDataSet[_metadata_=default|2026].Statistic[_metadata_=experience|racecraft|awareness|pace|focus].evolution`, a curve `@v2@minx:0,maxx:10,miny:0,maxy:100,…` with y = rating/100. Read once at boot; `driver.ratings.read` hook (`Career_Get_DriverStatValue`, before) can change them in career. Frozen per career season at season start. **Whether Grand Prix mode reads the statistics component at all is not reverse-engineered** (Q-02).
- **Rating → characteristic**: six rows of `driver_statistics.driver_statistics.driver_characteristic_overrides.DriverCharacteristicOverride_N` with `driver_statistic` (racecraft | awareness | pace), `driver_characteristic` (enum of the six) and `distribution` (curve 0..1 → 0..1, examples start `0:0,0:0,0.25:…`, `0:0,0:0,0.5:0.3…`). Labels seen: `racecraft_aggression, racecraft_reaction_speed, awareness_control, awareness_mistakes` (+2 presumed `pace_speed_in`, `pace_speed_out`).
- **Characteristic overrides**: `driver_characteristics.{aggression, control, mistakes, reaction_speed, speed_in, speed_out}` on the driver row; RE: "overrides +0x108..+0x11c (negative = none)". In the launcher's key catalogue, so a plain `set` works. **Stock values not yet dumped** (Q-01). `driver_characteristics.preferred_tracks` (list of track labels, 197/197) also exists.
- **Per-driver AI config**: `ai_driver_config.*` (84 keys, §3). Parsed per driver by the entrants loader (`0x142463b40 → 0x14065dc50` at `0x14246671e`; `default_driver` copy at `0x14249a4f0`); stock identical on all 197.
- **Strategy**: `driver_strategy.{fastest_strategy_base_selection_chance 0.15..0.85, fuel_load_max_modifier 0..0.05, fuel_load_min_modifier 0, safety_car_pit_max_laps_early 5, safety_car_pit_min_lap 1, safety_car_pit_wear_max 0.2..0.5, safety_car_pit_wear_min 0.1..0.35, slowest_strategy_selection_time_limit 9..16, weather_change_max_time_percentage 0.1..1, weather_change_min_time_percentage -0.25..0.6}`. Already varies per driver in stock.
- **Live per-car AI driver record** (0x1a0 bytes, built by `0x140658ac0`): raw characteristics +0xf0..+0x104 (reader 0x14065ab10), overrides +0x108..+0x11c, effective +0xa8 aggression, +0xac control, +0xb0 mistakes, +0xb4 reaction_speed, +0xb8 speed_in, +0xbc speed_out, preferred_tracks +0x120, evaluated parameter maps +0xc0..+0xe8 (writer not found).

### 2.6 Hook points (native plugins, `swofty_api.h` v8)
- `ai.controller.update` (`ai::events::ControllerUpdate`): every frame per AI car, `throttle, brake, steering`; before/after/replace. Core hooks the controller vtable slot 1 (or the record-apply site). **Unverified in 1.6.0, needs in-game check T145.** The only AI item that ships in `swofty/systems/ai.hpp` today.
- `ai.config.load` (per car at session load, live `AiHandlingConfig` pointer) and `ai.settings.resolve`: design, not shipped.
- `driver.ratings.read`: shipped (drivers system).
- Raw mixins: `SWOFTY_WRAP(<binding>, …)` on any L2+ binding in `re/db/functions.tsv`; find by signature, hook `.xtls` only, never patch `.data1`.
- Telemetry: `SwoftyTelemetry` shared-memory feed with per-car `speed, throttle, brake, steer, tyre_temp[4], tyre_wear[4], position, lap, last/current/best lap, sector times, lap_distance, world_pos[3], world_vel[3]` and per-participant name/team/position. This is the measurement harness for every behavioural claim below.

---

## 3. What is built: v0.1 (`verve-f1-addon/`)

`verve_to_swofty.py` turns a CSV of Verve scalars into `db/verve.json` (database `set` ops) plus `swofty.json`. Per driver it writes the six characteristic overrides, three `driver_strategy` keys, the `pace` rating curve in the `default` dataset, and optional `preferred_tracks`. Mapping and weights: `README.md`. Sample input `verve_grid_2025.csv` (illustrative numbers, **not** Verve data), 23 drivers, 232 ops.

Static validation done: all 232 fields exist in the launcher's key catalogue for `entrants.drivers.driver_N` or match the ratings path; all 23 labels appear as driver rows in the Swofty repo; all values inside stock ranges; manifest fields valid (`category: ai` needs launcher ≥1.5.3, set `compat.launcher >=1.5.13`).

Not done: nothing has been built or run against a game install. `swofty build` is the first real test (expect "no such key" if any assumption about the driver row is wrong).

---

## 4. Roadmap

### v0.1 (built) — characteristics + strategy + pace rating
Acceptance: `swofty build` applies with zero "no such key"; Q-01, Q-02, Q-03 answered; a two-driver A/B race shows the expected direction on reaction time (RaceStarts log) and overtake attempts.

### v0.2 — per-driver `ai_driver_config` (the net-new behaviour)
Order of attack, from `docs/ai_driver_config_keys.md`:
1. **A-rated (11 keys), tune now**: `race_start.*` 8 bounds (reaction and bad-start spread per driver = Consistency), `exit_fallibility.throttle_error_practice / _qualifying_race` (per-driver corner-exit error curves = Consistency; capped per car), `overtake.overlap_percentage` (leave stock, aggression already feeds it).
2. **B-rated (32 keys), small steps with A/B races**: overtake initiate/continue/pull-out and opportunist thresholds (Aggression), danger-class thresholds and buffer (Risk), blocking distance/threat/variable offset (Aggression, Consistency), divebomb_defense `max_presence_alongside` / `max_time_to_ignore` (Aggression), space_seeking `time_to_switch_sides`, `total_queue_needed`, `concede_overtake_blocked_by_crowed_time` (Aggression; likely the DRS-train lever), `alongside.yield_overtake_rate`, `offset_variation.max_offset` (Consistency).
3. **C-rated (41 keys)**: leave stock. Rules-related ones (`cede_position.*`, `yellow_flag_ramp_up_time`, `flying_lap_yield_to_human_*`) stay stock permanently for fairness.
Mechanics: same `set` ops; keys resolve by hash. Generator gets a second mapping table. Verify each B key with the telemetry feed before shipping it in a profile.

### v0.3 — native plugin
1. Per-driver weighting of the 84 race-form curves (Consistency as form, not just errors): hook `Ai_DriverVariationInRace_Update` 0x1409af4c0 or the graph index pick (`this+0x18`).
2. `ai.controller.update` based telemetry/verification harness (after-phase only, cheap).
3. Optional: revive the dead parameter maps if their consumers exist (Q-07).

### Balancing track (separate addon, not Verve)
1. Difficulty ceiling and per-track consistency: edit `ai_track_difficulties.<package>.time` and `mass_ratio` top entries per track (Q-05 first).
2. ERS: raise `ers_use.push_to_defend_battery_level` below 1.0 per car, tune per-track `ERSSettings.deployFactor / harvestFactor`.
3. Wet: `exit_fallibility.max_throttle_error_by_grip_wet`, `traction_control.grip_atc_strength`, and the AI-only tyre factors if a path to set them is found (VTF, not DB).
4. Yellow/SC overtaking: track `Ai_Apply_TetherSpeedCap` 0x140669790 and `site_Ai_ScFollowFlagCmp` 0x140642faf; vmknolle's sc-unlapping and red-flag-pit addons already use these.

### QoL: skip all cutscenes including the garage push-in (native)
- Cutscenes proper: `CutsceneManager` name table (`Game_Register_Cutscenes` 0x140213e10): podium, grid, garage, results, terminal_damage, intro_flag, track extras. Scripts expose `requestShutdown` 0x140237150, `testAndClrRequestStop` 0x1402371f0, `setStateShutdown` 0x140235f10, `setStatePlay` 0x1402374a0; manager `playInternal` 0x140227db0 / `stopInternal` 0x140228870. All L1 from log strings (channels CUTSCENE_MANAGER, CUTSCENE_SCRIPT_VERBOSE), so signature-findable. Plan: wrap `playInternal`, and for scene names in a configurable list call the script's `requestShutdown` on the next frame tick.
- Garage push-in is **not** a cutscene: `GarageCrewInstanceLogic` states `StateWaitPushIntoGarage` 0x140386720 → `StateZoomIntoMonitor` 0x140385b80 → `StateCarIsReadyForTrack` 0x140385760 → `StateSendCarToTrack_P3` 0x140386320, driven by `Game_GarageCrew_StateTransition` 0x14043e5a0 ("StateTransition setNextState %s") and the request delegate `Game_Handle_GarageCrewEvent_Thunk` 0x14038cc80 (L2). Pit status chain for the car (session notes): garage 0/9 → WantsToLeave 10 → 11/12 → LeavingGarage 13 → LeavingPitLane 14 → OnTrack 1. Plan: enable `GARAGECREW:info` and `GARAGE:info` log channels, record the state/event sequence once, then wrap `StateTransition` to skip straight to the ready state. Risk: a wrong jump leaves the car stuck in the box; keep it behind an addon option. Keypress variant: poll the key on the frame tick (`events::frame`) or expose it as a setting.

---

## 5. Open questions, each with the test that closes it

| ID | Question | How to close it | Blocks |
|---|---|---|---|
| Q-01 | What are the stock values of `driver_characteristics.*` on driver rows (expected -1 = no override)? | `swofty db get entrants.drivers.driver[_metadata_=max_verstappen]` | v0.1 confidence |
| Q-02 | Does Grand Prix mode read the statistics component, or only career? | Stock GP race, two drivers with very different ratings; compare reaction times (RaceStarts log) and braking points (telemetry) | whether v0.1 matters outside career |
| Q-03 | Is `mistakes` proneness or resistance? | Dump the `distribution` curve of the `awareness_mistakes` override row (`swofty db get driver_statistics.driver_statistics.driver_characteristic_overrides`); if monotonic increasing it is a skill. Confirm with two drivers at 0.05/0.95 and the RaceStarts "Race Start performance" line | v0.1 sign of one field |
| Q-04 | Do driver-row overrides take effect at session load, or only on a fresh boot/career? | Change one value, rebuild, start a session without restarting the game, read RaceStarts | workflow |
| Q-05 | Slider position → index in the 10-point `ai_track_difficulties` tables; what `difficulty_ratio` scales | Race at slider 80, 100, 110 on one track; log lap times (QUALI_PACE_DEBUG, telemetry); fit against the `time` entries. Static: find the reader of `max_dificulty_no_balast_slider_position` | balancing track |
| Q-06 | Does `mass_ratio` < 1 above slider 100 explain the straight-line speed complaint? | Same race; compare AI top speed at 100 vs 110 with equal wings; the mass drop predicts a top-speed and traction gain, not a cornering gain | balancing |
| Q-07 | Do the dead parameter maps (`wet_weather_ability`, `brake_off_time`, `slide_confidence`, `alongside_awareness`) have consumers? | Set `wet_weather_ability` corners to 0.5/1.0 for one package; wet race; measure. RE: "consumer not found" for wet | v0.3 |
| Q-08 | Which struct do `Ai_Parse_{Overtake,Blocking,SpaceSeeking,CedePosition}Config` fill: per-driver `ai_driver_config` (leaf names match) or per-car `ai_vehicle_config` (function notes' wording)? | Trace the parsers from the entrants loader `0x142463b40` vs the session loader `0x1425027e0`; or just set `overtake.oppertunist_overtake_time` on one driver and watch | v0.2 |
| Q-09 | Sign conventions of the `*_time_adjustment` keys | Trace, or A/B with 2x / 0.5x | v0.2 B keys |
| Q-10 | Is `ai.controller.update` live (T145)? | Subscribe an after-handler that logs once per car; check loader.log | v0.3 harness |
| Q-11 | Which drivers carry a `2026` `StatisticsDataSet`, and does the 2026 season pack read it instead of `default`? | `swofty db get` per holder; a `set` on a missing dataset fails the build, so the generator only writes `default` today | v0.1 with the 2026 pack |
| Q-12 | Does `swofty build` accept `driver_characteristics.preferred_tracks` with `|`-separated input joined to commas? | Build once with one driver's list set | v0.1 nicety |

| Q-13 | Can a `career_setup` page be attached to the **My Team** tile, and what is `next` for its wizard? | Try `career_setup` with `next` set to the My Team wizard's first screen (find it with `swofty` UI debugging, `docs/reference/ui/debugging.html`); ask on the Swofty Discord | option C of §10.4 |
| Q-14 | Can a My Team mode/content tile be made data-only (as the Driver Career "Decades" recipe), and which economy tables are data-group-scoped? | Clone `resource_points.data_group[_metadata_=f1_career_2025]` under a new label, register a `career.content` record with that data group, start a career, check RP totals | option B of §10.4 |
| Q-15 | Do the Hard multipliers produce the intended pacing (max car in ~4 seasons on Hard, ~6 on Hardest, cost cap binding in season 1)? | One simulated season per preset with "simulate all sessions"; log cash, RP and upgrade count per round from the Team HQ screens | §10.3 numbers |
| Q-16 | Stock values of every §10.2 key, especially the 280 MyTeam attribute defaults and `target_mass_adjustment_at_max_upgrade` | `swofty db get attributes.Attributes[_metadata_=MyTeam].attribute_definitions`; `swofty db search cost_cap`; `swofty db get` on the tweakables container | all of §10 |
| Q-17 | Row vs rating precedence, per mode: does the AI use the driver row's `driver_characteristics.*` or the values derived from the ratings through the `driver_characteristic_overrides` curves? Stock rows are curated and differ a lot from the curve output (F-28) | Issue #7: arm ROW (row `reaction_speed` 0.0 / 1.0, ratings stock) and arm STATS (flat `racecraft` evolution 0.0 / 1.0, rows stock) in one race; RaceStarts reaction times over 5 starts, in Grand Prix and in Driver Career (folds in #9 / Q-02) | v0.1 mechanism; #6 design. **Supported for benchmark (B-0006, #39, F-36): the row wins** for reaction_speed; replication pending (B-0008); GP and career open |
---

## 6. Risks and rules

- **Offline only.** The launcher disables anticheat; modded profiles never touch multiplayer. Launching from Steam stays vanilla.
- **Game patches.** DB key paths are stable across patches so far (hashes of names); native hooks are signature-based but still break. The RE build is the Steam build; EA-app builds have different addresses (the launcher handles both).
- **Saves.** Driver-row edits affect careers started with the addon (ratings freeze per season). `saves.affects` is `false` in the manifest; flip it to `true` with a message if v0.2 adds rows (it doesn't today).
- **Year packs.** Classic Seasons protects some fields; a selector layer skips them unless the player enables "Also change year packs". Not relevant to `set` ops on stock 2025/2026 drivers.
- **Stock-identical configs may be identical for a reason.** Codemasters declined to fix qualifying bunching because "attempting a fix risks a broader detrimental impact to AI behaviour". Expect emergent weirdness when 20 drivers stop sharing one config; A/B one key at a time.
- **The 1.6 registry API is design.** The C++ `ai::vehicle_configs.layer(...)` examples in the docs do not run today for AI; use database ops (1.5 style), which the launcher will keep supporting (`docs/std/compatibility.md`).
- **Fairness keys.** `cede_position.flying_lap_yield_to_human_track_speed_diff`, `yellow_flag_ramp_up_time`: never personality knobs.

---

## 7. Verification toolkit

- **Stock values:** `swofty db get <path>` (no `--addon`) prints stock; `swofty db search <query>` finds keys; `swofty db get` on a container lists what it holds. Selector paths work (`entrants.drivers.driver[_metadata_=max_verstappen].driver_characteristics.aggression`).
- **Build check:** `swofty addons install <folder>`, `swofty addons enable verve.driver-profiles`, `swofty build`; read the applying lines in the launcher output. For add-row addons, `cargo run -p swofty-core --example check_add_rows -- --game <F1 25 folder> --addon <addon folder>`.
- **Game log channels:** in `swofty/session.json` (game folder) set `"game_log": { "level": "info", "channels": "default,RaceStarts:info,CANNED_EVENTS:info,AI_VARIATION:info,QUALI_PACE_DEBUG:info,GARAGECREW:info,GARAGE:info" }` (env var `SWOFTY_GAME_LOG_CHANNELS` overrides). Lines land in `swofty/loader.log`. Known formats: `Reaction Time for driver with vehicle id %d: %f`, `Race Start performance for driver with vehicle id %d: %f`, `Vehicle ID: %d, pressure lock up chance %f, time %f`, `vehicleId %d, tyre %d, start %f, end %f, mass %f, tyreType %d, …` (QUALI_PACE_DEBUG; note the `mass` field for Q-06).
- **Telemetry feed:** `SwoftyTelemetry` shared memory (`docs/reference/std/telemetry.md`): per-car throttle/brake/steer/speed/world_pos per frame. A 50-line Python reader is enough to compare two drivers' braking points, exit throttle traces and line offsets.
- **Rate limits:** the game-log copy defaults to 100 lines/s and 20,000 lines per session; raise `rate` and `max_lines` for a full race.

---

## 8. Issue backlog (ready to file)

Labels suggested: `verve`, `f1-25`, `data-addon`, `native`, `research`, `balancing`, `qol`.

1. **[research] Dump stock per-driver AI values** — run `swofty db get` on one driver row, the six override rows, and one `ai_vehicle_config`; commit the dump under `docs/stock/`. Closes Q-01, informs Q-03, Q-08. *Acceptance:* dump committed, Q-01/Q-03 answered in findings.json.
2. **[data-addon] Build v0.1 against the game** — `swofty build` with the generated addon; fix any "no such key"; record the applying lines. *Acceptance:* zero errors, addon visible in ADDON SETTINGS.
3. **[research] GP mode vs career: does personality apply?** — Q-02 protocol. *Acceptance:* findings.json entry with the RaceStarts log excerpt.
4. **[research] mistakes direction** — Q-03. *Acceptance:* generator default flag set correctly, README updated.
5. **[data-addon] v0.2a: A-rated `ai_driver_config` keys** — race_start bounds and exit_fallibility curves driven by Consistency; needs the stock curve from issue 1. *Acceptance:* per-driver spread visible in RaceStarts log over 5 starts.
6. **[data-addon] v0.2b: B-rated overtake/blocking/space_seeking keys** — one key per A/B race, telemetry-measured. *Acceptance:* each shipped key has a before/after number in findings.json.
7. **[research] Slider → `ai_track_difficulties` mapping** — Q-05/Q-06. *Acceptance:* index mapping documented; mass hypothesis confirmed or rejected with top-speed numbers.
8. **[balancing] Difficulty ceiling addon** — raise top `time`/`mass_ratio` entries per track for `f1_2025_vehicle_package` and `f1_2026_vehicle_package`; option slider in `swofty.json`. Depends on 7.
9. **[balancing] ERS defend/deploy addon** — `ers_use.push_to_defend_battery_level` per car + per-track `ERSSettings`. *Acceptance:* AI defends with partial battery in a 10-lap test.
10. **[research] Dead parameter maps** — Q-07.
11. **[native] Per-driver race-form weighting** — v0.3 item 1; needs issue 10's trace tooling.
12. **[native] `ai.controller.update` harness** — Q-10; after-phase logger + Python telemetry reader.
13. **[qol/native] Skip all cutscenes** — wrap `CutsceneManager::playInternal`, configurable scene list.
14. **[qol/native] Skip garage push-in** — trace GARAGECREW state chain, wrap `StateTransition`; option-gated; stuck-car risk documented.
15. **[docs] Resolve the parser attribution discrepancy** — Q-08; update `tools/build_catalogue.py` notes.
16. **[generator] Support the `2026` statistics dataset** — Q-11; per-driver dataset detection from the dump in issue 1.
17. **[career] Dump the My Team economy** — every key in §10.2, committed under `docs/stock/myteam/`. Closes Q-16. *Acceptance:* dump committed; §10.3 multipliers converted to absolute values.
18. **[career/data-addon] My Team difficulty preset, option A** — `myteam_difficulty` choice option, `when`-gated ops for Hard and Hardest from §10.3; ceiling-fairness and AI-RP pacing changes applied to all presets. *Acceptance:* Q-15 protocol passes on one simulated season per preset.
19. **[career/research] Per-career variants** — answer Q-13 and Q-14; decide between options B and C. *Acceptance:* a written decision with the Swofty Discord answer attached.
20. **[career/native] Wizard-step version (option C)** — only after 18 ships and 19 picks C.
21. **[generator] Season progression** — replace the flat pace curve with a shifted stock curve (or CSV start/peak); plan the per-season override rewrite (§11). *Acceptance:* a 3-season simulated career shows the pace rating moving per driver.
22. **[generator/data-addon] "Verve strength" slider** — `db` slider blending overrides toward stock; 0 writes -1 (no override). *Acceptance:* strength 0 produces a build identical to vanilla driver rows.
23. **[data-addon] Conflicts and load order** — `load_after` Driver Manager, Classic Seasons, Progressive; `conflicts.touches` for driver-row fields where exclusive. *Acceptance:* a profile with all four enabled builds without warnings and Verve values win.
24. **[native/tooling] Autonomous test harness** — §13: harness plugin (auto-start, AI control, auto-exit), UDP logger, analysis script, `runs/` layout. *Acceptance:* 10 unattended 5-lap races overnight with per-driver metrics in a CSV.

---

---

## 9. How Verve settings surface in game (and whether a "Verve" category exists)

Short answer: every addon gets its own settings page automatically, and there are four extra places an addon can put options. There is no cross-addon "Verve" category in game; the grouping is per addon, and on the launcher side by `category`.

| Surface | What it is | Declared by | Binds | Per-career? |
|---|---|---|---|---|
| Launcher **Addons** page row | Options on the addon's row; `category` (`ai`, `career`, …) groups and filters the page | `options`, `category` | db or native | No (per profile) |
| **ADDON SETTINGS** in game (home menu, under Career) | One page per enabled addon, same options; `hidden: true` keeps a developer or per-career option off it | `options` | db or native | No |
| **Career setup page** | A page in the CUSTOM SETTINGS look that opens between a career content tile and the new-career wizard: a CONFIRM tile plus a category tile that opens the rows page. This is the "insert a step when you start a campaign" mechanism | `career_setup` { route, title, options, next } (launcher ≥ 1.5.13) | native (live) or db | Values belong to the **profile**; a plugin copies them into the career's storage when the career is created |
| **Team HQ laptop tab** | A tab on the career hub showing 1–6 options, only for careers in a `data_group` | `hub_tab` { name, title, options, data_group } | native or db | Shown per data group |
| **Race MFD page** | An ADDONS page in the in-race MFD with toggle/choice rows | `hud.mfd` (launcher > 1.5.26) | native | No |

Binding semantics decide the UX:
- `binds: "db"`: the value is baked into the game files at build; op files use `{{id}}` substitution and `"when": {"id": value}` gating. Changing it marks the profile for a rebuild; applies after rebuild and restart. Good for "pick a preset, then start a career". Wrong for a wizard step.
- `binds: "native"`: read live by the addon's DLL (`SWOFTY_SETTING` / `SWOFTY_ON_CHANGE`). Required for anything chosen inside the wizard.

Reference implementation: `swofty.progressive` (repo `addons/progressive/swofty.json`): `career_setup` route `career_wizard_driver_career_progressive` with options `start_season` (hidden, native), `rnd_mode`, `team_moves`; `hub_tab` "Progressive Settings" on data group `f1_career_progressive`; 12 DLLs; `saves.affects: true`.

**Caveat for My Team specifically.** The docs describe `career_setup.route` as "a copy of `career_wizard_driver_career_to_f1`, the route a Driver Career tile takes to the season length step", and `next` must be a screen in `flow_career_season_setup.erp`. The My Team wizard has its own steps (team name, livery, the four owner-background questions: ProfessionalBackground, FacilityInvestment, VehicleDevelopment, CashReserves). Whether a `career_setup` page can sit in front of the **My Team** tile, and what `next` should be, is not documented. See Q-13.

For Verve v0.1 (driver personalities) none of this is needed: the addon has no options, it just applies. Add options later for "Verve strength" (a `db` slider that scales how far overrides deviate from stock) and the `mistakes` direction switch.

---

## 10. My Team difficulty presets (Standard / Hard / Hardest)

### 10.1 What players actually complain about

From the EA forums threads "Can we talk about MyTeam now?" and "R&D is broken" (Reddit search returned nothing usable through this session's tools; both EA threads are the same complaints players post on r/F1Game):

1. **Money never binds.** "Cost cap is never a problem"; regulation changes don't hurt because cash is easy.
2. **R&D points pile up.** "Thousands of unusable research points" by season 2–3; the points-free R&D reset made development "nearly irrelevant".
3. **Progression ends in season 1.** All available upgrades bought in the first season ("24 or 27 is not enough"); then a wait of ~2 seasons for phase-3 ultimate upgrades.
4. **AI develops too fast and too far.** AI teams maxed after 2–3 seasons (one report: 8 of 11 teams maxed at the end of season 2); a maxed AI car is ~1 s/lap faster than a maxed player car (Bahrain); player chassis "only reaches halfway". So the mode is simultaneously too easy (economy) and unwinnable later (ceiling).
5. **Regulation changes are toothless.** They touch parts, not whole departments; players want them more often, whole-department, and ~3x the adaptation cost.
6. **Straight-line AI speed** (covered in §2.2 and F-09).

"Harder" therefore means a tighter economy and slower, costlier, riskier progression for the player, **not** faster AI development. Fixing the ceiling asymmetry is a fairness fix that belongs in every preset.

### 10.2 The levers (all game-database rows; stock values to dump before tuning)

| Lever | Keys | Stock (from the catalogue) | Scope |
|---|---|---|---|
| Starting cash | `career.career_setup.CareerSetupDataGroup_N.owner_background_outcomes.InitialCashBackgroundOutcome_N.initial_cash` (NoInitialCash / SomeInitialCash / SignificantInitialCash); `bank.initial_team_cash.InitialTeamCash_N.cash` | 0 / 2.5M / 7.5M; team rows 0..5.5M | per data group / global |
| Starting facilities | `career.my_team_facilities.background_outcomes.FacilitiesBackgroundOutcome_N` (Basic / Advanced / StateOfArt), `…CorporateIncome_N.corporate_income_multiplier` | 1 / 1.25 / 1.5 | global |
| Cash income rate | `bank.settings.cash_rate.CashRateModifiers_N[_metadata_=PlayerTeamCashRateModifier].{reduced_rate_modifier, increased_rate_modifier}` (and `AiTeamCashRateModifier`) | player 0.7 / 1.25; AI 0.6 / 1.25 | global |
| Race cash rewards | `career.my_team_rewards.reward_definitions.MyTeamModOneShotReward_N.{amount, magnitude}` (OnRaceWon, OnRaceFinish, OnRacePodiumAny, OnRaceScorePoints, …, 80 rows); `MyTeamCashReward_N` renown grants (18 rows) | amounts 100k–500k | global |
| Sponsor income | `career.my_team_sponsors.weekly_income_per_decal_thresholds.*.income` (4 tiers by decal count); `income_attributes` → attributes `MyTeam_PrimarySponsor_WeeklyIncome_Mult`, `MyTeam_SecondarySponsor_WeeklyIncome_Mult`, `MyTeam_PrimarySponsor_SeasonalGoalIncome_*` | 5k–25k per tier | per data group (sponsors) / global (attributes) |
| Budget pools / cost cap | `bank.budgets.Budget_N.BudgetPool_N.{cap, ratio, enforce_cap}` (R&D, Facilities, DriverContracts, Activities); `bank.facility_budgets.FacilityBudget_N.cost_cap_fraction_{engineering,workforce}_cutoff`; `base_cost_cap` (container unresolved, find with `swofty db search cost_cap`); game values `game_value_cost_cap_spending_percent`, `game_value_team_breached_cost_cap_{current,prev}_season` exist, so a breach mechanic exists | caps 1.5M–100M, ratios 0–50, cutoffs 0.95 / 0.9 | global |
| Resource points | `resource_points.data_group_N[_metadata_=f1_career_2025|2026].teams.team_N.{num_initial_spendable_resource_points, per_driver_mode.*}` (per team, AI teams included); `resource_points.resource_point_types.resource_point_N.{multiplier, max_cap}` (practice programmes) | 1000–1750 initial; weekly 200–300; multipliers 0–25, caps 0–150 | per data group / global |
| R&D cost, time, risk | `UpgradeDepartmentEntry_N` (containers `{1f304d36c3c2b947}`, `{5e21a18f9f59dbf6}`, one per data group) name attributes `MyTeam_RND_{Research,Development}CostScale{Aero,Chassis,Durability,Engine}`, `*TimeScale*`, `*FailRate*`, `MaxSimultaneous{Research,Development}*`, `RushFailRate*`, `AdaptingCostScale*`, `DualDevelopmentCostScale*`; their defaults live in `attributes.Attributes_N[_metadata_=MyTeam].attribute_definitions.AttributeDefinition_N[_metadata_=<name>].default_value` (280 definitions); loader `Career_Load_DepartmentEntries` 0x1412326e0 (L2) | not dumped | global (attribute defaults) |
| Upgrade prices | `upgrades.*.upgrade_N.cost` (cash 100k–600k by tier; RP 500–1500), `cost_to_develop` | see ranges | per tree |
| Regulation changes | `{13c5d2048aa484f5}.regulation_changes_schedule_N` (21 schedules) `.regulation_change_season_N.{1_season, 2_rumour_weekend, 3_confirmation_weekend, 4_affect_aerodynamics, 4_affect_chassis, 4_affect_durability, 4_affect_engine}` | 4–6 changes per schedule, seasons 0–9 | global |
| AI development pace | `resource_points…teams.team_N` rows for the AI teams; `tweakables.recommended_upgrade.percentage_chance_of_picking_{vehicle,durability}_upgrade`; `AiResourceRateModifiers` (static table in code, `Career_Load_ResourceRateConfig` 0x14122ada0) | not dumped | per data group / code |
| Ceiling fairness | `tweakables.target_mass_adjustment_at_max_upgrade`, `difficulty_mass_adjustment_scalar` + `_enabled` (`Career_Load_RnDTweakables` 0x14353cea0, L2); per package `upgrade_type_metadata_N.{mass_adjustment_fully_upgraded (−34..0 kg), bhp_adjustment_fully_upgraded}` | not dumped | global / per package |
| Driver salaries | `career.generic_contracts.ContractProvider_N.ContractStat_N` (DriverSalary, DriverSigningBonus, performance clauses), `driver_market.driver_perk_salary_bonus` | not dumped | global |
| Race realism lock | `difficulty.settings_N[_metadata_=hardcore]`: aiStrength 110, cockpit_cam, cornerCuttingMode strict, driver_proficiency elite, formationLap on, osdAvailable off, parcFermeRules on, raceStarts off (manual), race_style realistic, recovery_mode none, rules_and_penalties on, safetyCarFrequency standard, tyre_carcass on, vehicleDamage realistic; the `career` row holds the career restrictions | hardcore row shown | global |

### 10.3 Proposed presets (multipliers on stock; tune after the dump)

| Lever | Standard | Hard | Hardest |
|---|---|---|---|
| Starting cash (all three background outcomes) | stock | 0.6x | 0.35x, and SignificantInitialCash capped at SomeInitialCash |
| Player cash rate modifiers | 0.7 / 1.25 | 0.6 / 1.15 | 0.5 / 1.05 |
| Race cash rewards (won / podium / points / finish) | stock | 0.7x | 0.5x |
| Sponsor income per decal tier | stock | 0.75x | 0.5x |
| Budget pool caps | stock | 0.8x | 0.65x |
| Initial spendable RP (player team) | stock | 0.7x | 0.5x |
| Practice-programme RP multipliers / caps | stock | 0.75x | 0.5x |
| Upgrade RP and cash cost | stock | 1.5x | 2.25x RP, 2x cash |
| Research / development time scale | stock | 1.3x | 1.6x |
| Development fail rate, rush fail rate | stock | 1.5x | 2x |
| Max simultaneous research / development | stock | −1 (min 1) | −1 (min 1) |
| Regulation changes | stock | every schedule gains one extra change season; each change affects ≥2 departments | every 2 seasons, whole departments, adapting cost 3x |
| Driver salaries / signing bonuses | stock | 1.25x | 1.5x |
| AI team RP (fairness, all presets) | tune so AI maxes in ~5 seasons, not 2–3 | same | same |
| Ceiling fairness (all presets) | `target_mass_adjustment_at_max_upgrade` aligned so a maxed player car matches a maxed AI car (measure first) | same | same |
| Race realism | player's choice | player's choice | `hardcore` row values copied onto the `career` difficulty row (locks assists and realism) |

Numbers are starting points chosen so Hard roughly doubles the seasons needed to max the car and Hardest triples it, with the cost cap actually biting. Validate against the season-1 playthrough test (Q-15).

### 10.4 Three ways to ship it

| | A. Profile preset (data only) | B. Separate career tiles (data only) | C. Wizard step (native) |
|---|---|---|---|
| UX | Choose Standard/Hard/Hardest in ADDON SETTINGS or the launcher, rebuild, start a career | Three tiles in the career menu: My Team, My Team (Verve Hard), My Team (Verve Hardest) | The step Tyler described: tile → Verve page → wizard |
| Mechanism | One `choice` option `myteam_difficulty` with `binds: db`; every op carries `"when": {"myteam_difficulty": "hard"}` or uses `{{…}}` | `career.mode` + `career.content` records in `registry/career.json` (data-only tiles are supported, `docs/make/career.md` "With no DLL"); each tile's data group gets its own `resource_points` and sponsors rows | `career_setup` page + DLL that copies the choice into career storage and wraps `Career_Load_RnDTweakables` 0x14353cea0, `Career_Load_DepartmentEntries` 0x1412326e0, `Career_Load_ResourceRateConfig` 0x14122ada0 and the cash/reward reads to scale per career |
| Per career? | No: the whole profile. Two careers at different presets need two profiles | Yes, but only for data-group-scoped tables; the global ones (attribute defaults, bank settings, rewards, upgrade prices) still apply to every career in the profile | Yes, fully |
| Effort | Small (an afternoon once the dump exists) | Medium; unknown whether My Team content records are as simple as Driver Career ones (Q-14) | Large; needs the L2 loaders traced for the right struct offsets, and Q-13 |
| Recommendation | **Ship first.** Covers 90% of the value | Only if per-career matters and C is too expensive | The polished version, after A proves the numbers |

---

---

---

## 11. Does Verve apply in My Team? (and the season-progression caveat)

**Yes, by construction, for every AI-driven car in every mode**, with these qualifications:

- The `driver_characteristics.*` overrides live on the driver row and are read when the per-car AI driver record is built at session setup (0x140658ac0, overrides at +0x108..+0x11c). Nothing in that path is career-specific. The `ai_driver_config.*` keys are parsed per driver by the entrants loader at boot. Both reach Driver Career, My Team, Grand Prix and Time Trial alike. Confidence: decoded, not yet run (Q-04 covers "takes effect at session load").
- Only AI-controlled cars read them. The player's car reads nothing unless the AI drives it (`sessions::set_control`). The My Team teammate is an AI car, so it gets its profile.
- Drivers created by Driver Manager or added by year packs copy `default_driver`; Verve has no scalars for them and they stay stock unless the CSV includes their labels. Classic Seasons grids (Rosberg, Vettel, Raikkonen, …) are real driver rows, so Verve's historical profiles can cover them.
- **Season progression caveat (real flaw in v0.1).** In career modes the game evolves ratings by season: each statistic's `evolution` curve runs over x = 0..10 seasons from a start value to a peak (`docs/std/systems/drivers.md`), and the season's ratings freeze at season start. v0.1 writes a *flat* pace curve and *static* characteristic overrides, so in a multi-season career Antonelli never improves and Alonso never declines. Fixes, cheapest first: (1) keep the stock curve's shape and shift it so the peak matches Verve Pace (needs the stock curves dumped, issue 1); (2) let the CSV carry start and peak per driver; (3) a native `driver.ratings.read` handler that scales ratings per season, and a season-start hook (`SWOFTY_EVENT_CAREER_STARTING`, `career.loaded`) that rewrites the overrides from a per-season Verve table. Single-season GP mode and the first season of any career are unaffected. Tracked as issue 21.

---

## 12. What is still missing before an agent builds this

| Gap | Why it matters | Owner |
|---|---|---|
| Stock value dump (issues 1 and 17) | Every multiplier in §10.3 and the `mistakes` sign depend on it | first run with the game |
| Verve's real scalars and the label mapping | The sample CSV is illustrative; the generator needs `label → Pace/Aggression/Risk/Consistency` for the 2025 and 2026 grids, plus any classic grids | Tyler |
| Season progression (§11) | Multi-season careers flatten without it | issue 21 |
| A "Verve strength" slider | A `db` slider 0..100 that blends each override between stock (-1, none) and the Verve value; lets players and tests dial it, and gives a clean A/B | issue 22 |
| Conflict declarations | Driver Manager, Classic Seasons year packs and Progressive write driver rows and ratings; a later addon wins per field. Declare `load_after` for Verve so it applies last, and `conflicts.touches` where exclusive | issue 23 |
| `compat.game_builds` pin | The 2026 season pack changed drivers and datasets (Q-11); pin the builds the dump was taken on | with issue 1 |
| Test harness (§13) | Nothing can be verified faster than real time without it | issue 24 |
| Publishing | `homepage`, `icon`, OverTake listing, publish.f1.swofty.net; keep the Ko-fi link; the addon ships numbers only (no game assets), MIT | Tyler |
| F2 drivers | No Verve data; leave stock | none |

---

## 13. Running the game autonomously (local agent harness)

The constraint: F1 25 is a DirectX 12 game with no headless mode and no built-in race automation. An agent cannot "simulate" AI behaviour offline; the physics only runs in a live session. Career "simulate session" uses baked lap times and ratings (F-18), so it is useful for My Team economy pacing (Q-15) and useless for driving behaviour. Plan around real-time races on a real GPU.

### 13.1 The loop

```
edit addon (CSV or ops)  →  swofty build  →  swofty run --apply --direct  →  harness plugin auto-starts the session
→  telemetry logger (UDP) writes CSV  →  session.end  →  harness quits the game  →  agent analyses CSV  →  next variant
```

- **Launch and teardown:** `swofty run --apply --direct --profile verve-test` installs the profile, launches, follows the logs, prints exit code and crash details, and rolls the game folder back on exit. A stop signal closes the game and rolls back. Steam must be running (`--no-start-store` otherwise).
- **Auto-starting a session:** a small native "harness" plugin that, on `SWOFTY_EVENT_STATE`/`flow.state` reaching the home menu, fires the Grand Prix routes to a fixed track with fixed weather and difficulty, then on `race.start` hands the player's car to the AI with `sessions::set_control(player, Control::ai)` (same mechanism the `kizikafuka.ai-drive` addon uses), and on `session.end`/`results` triggers exit. Route names come from the UI debugging page (`docs/reference/ui/debugging.html`) and the flow logs (`SWOFTY_GAME_LOG_CHANNELS` with the UI/flow channels at info).
- **Fallback without a plugin:** computer-use clicking through menus from screenshots. Workable for a handful of runs, too slow and brittle for overnight batches.

### 13.2 Measurement

- **Official UDP telemetry** (game setting, works offline): per-car lap data (position, lap distance, pit status, penalties), car telemetry (throttle, brake, steer, speed), car status (ERS deployed/stored, fuel), car damage, motion, participants, and the event packet, which since F1 23 carries an Overtake event (overtaking and overtaken vehicle indices) and since F1 24 a Collision event (two vehicle indices). Verify against the attached spec PDF on the EA forum post (12187347); one commenter reports `m_driverStatus` and `m_gridPosition` swapped in LapData. Python readers for the 2023/2024 formats exist and need only the 2025 struct offsets.
- **Swofty telemetry feed** (`SwoftyTelemetry` shared memory): same per-car signals plus world position; no spec drift risk, but needs a reader written against `docs/reference/std/telemetry.md`.
- **Game log channels** (§7): RaceStarts reaction times, CANNED_EVENTS lock-ups and accidents, AI_VARIATION form picks, QUALI_PACE_DEBUG mass and tyre per car.

Metrics per driver per race: reaction time; overtakes made/suffered; collisions; braking point per corner (first brake > 0.2 by lap distance, median over laps); exit throttle ramp; ERS deploy fraction on straights; lap-time spread; DNFs. Compare variant vs control with the same seed conditions.

### 13.3 Noise control

- Fix track, weather (dry, no change), time of day, race length (5 laps at a short circuit ≈ 8 minutes; ~60 races overnight on one machine), difficulty, grid order (set qualifying to a fixed grid or one-shot).
- In the test profile, turn off race-form variation (`ai.driver_variation.in_race.game_modes` race flags) and canned events (`canned_events` per-race DNF min/max to 0) so personality is the only variable; turn them back on for final validation.
- Change one key per batch; 5 to 10 repeats per variant; report medians and ranges, not single races.
- One licensed copy per machine. Steam allows one online session per account; offline mode on a second PC with the same account is unreliable, so parallel nodes need separate accounts/copies.

### 13.4 What an agent should be allowed to do unattended

Build, launch, run, read logs, write reports, open issues. Not: change the preset multipliers without a logged measurement, touch `cede_position.*` or yellow-flag keys, or enable anything online. Keep every run's `loader.log`, the ops file hash, and the telemetry CSV together under `runs/<date>-<variant>/`.

---

## 14. Other improvements the same mod could carry

| Area | Lever found | Effort | Notes |
|---|---|---|---|
| Dirty air ("no dirty air" complaint) | per-car `ai_vehicle_config.downforce_loss.{aero_reduction_scalar, speed_removal_percentage}` | data | AI-only following penalty; player already suffers it |
| AI mistakes and DNF realism | `canned_events.Per-race DNFs` (failures per fault type, spin-outs, side-swipes, lock-ups), `Ai_CannedEvents_*` | data | Make Hard presets include more AI retirements; stock per-race DNF min/max unknown |
| Team personality in R&D | `tweakables.recommended_upgrade.percentage_chance_of_picking_*`, per-team `resource_points` rows | data | Red Bull develops aggressively, Williams conservatively |
| Pit crew variance per team | `Game_PitCrew_GenerateStopSchedule` pre-rolls stops per team (seeded MT19937); `pit_crew_training.mistakes` table | data/native | Per-team stop time distributions |
| Rivalries | `Game_RivalryManager` (0x141261010) | native | Driver rivalries could feed aggression toward a specific car |
| Weather realism | AI sees one global wetness plus the forecast curve, never local wetness (session notes 2026-10-25) | native | Hard to fix; document only |
| Qualifying bunching | Codemasters declined a fix; `ai_track_config.crowded_rules` and `space_lines` per track | data | Risky, their words |
| Ghosting through cars | collision handling; `kizi.ai-tweaks` already does native contact handling | native | Coordinate rather than duplicate |
| Historical grids | Verve's vintage rosters onto Classic Seasons 2016–2024 driver rows | data | Same generator, different CSV |
| Form curves per driver | v0.3 item 1 | native | The Consistency axis the game already has |

## 15. Glossary
- **Characteristic**: one of six 0..1 per-driver values the AI controllers read. **Rating**: one of five 0..100 driver stats shown in the UI. **Distribution**: the curve from rating to characteristic. **Parameter map**: bilinear (difficulty x characteristic) table per car package producing a controller factor. **Track pack**: baked per-track AI data per car. **Form curve**: one of 84 in-race lap-time variation curves. **L1/L2/L3**: Swofty RE evidence levels. **Op**: one database change in an addon's `operations.database` file.
