# Stock value dumps

Raw output of `swofty db get` on unmodded game data (no `--addon`). Swofty 1.6.11, F1 25 Steam build 25251167
(`F1_25.exe` sha256 `d873a1c8…`, the build the RE notes cover), dumped 2026-10-30. Regenerate with
`tools/dump_stock.ps1` (any path, recursive) and `tools/dump_ai_driver_config.ps1` (the 84 per-driver keys).

| File | Path dumped |
|---|---|
| `driver_<label>.txt` | `entrants.drivers.driver[_metadata_=<label>]` for max_verstappen, oliver_bearman (rookie), fernando_alonso (veteran) |
| `stats_<label>.txt` | `driver_statistics.driver_statistics.DriverStatisticsHolder[driver=<label>]`, both datasets, all five rating curves |
| `driver_characteristic_overrides.txt` | the six rating -> characteristic `distribution` curves |
| `ai_driver_config.csv` | all 84 `ai_driver_config.*` keys for default_driver and the three drivers above |
| `statistics_datasets.csv` | dataset labels of all 117 `DriverStatisticsHolder` rows |
| `ai_vehicle_config_redbull_2025.txt` | `entrants.vehicles.vehicle[_metadata_=redbull_2025].ai_vehicle_config` |
| `driver_parameter_maps_f1_2025.txt` | `vehicle_package_10` (f1_2025) `ai_vehicle_package_config.driver_parameter_maps` |
| `ai_track_difficulties_austria_f1_2025.txt` | `tracks.Track[_metadata_=austria].ai_track_difficulties.f1_2025_vehicle_package` |

## What the dump answers

**Q-01: stock `driver_characteristics.*` values are set per driver, not -1.** Every driver row carries
hand-tuned values. The handoff expected "no override".

| Driver | aggression | control | mistakes | reaction_speed | speed_in | speed_out |
|---|---|---|---|---|---|---|
| max_verstappen | 1 | 0.96 | 0.75 | 0.85 | 1 | 0.99 |
| fernando_alonso | 0.93 | 0.97 | 0.90 | 1.0 | 0.93 | 0.94 |
| oliver_bearman | 0.65 | 0.765 | 0.65 | 0.65 | 0.68 | 0.78 |

These don't match what the rating curves would produce, often by a lot (row / curve at season x=0):

| Driver | aggression | control | mistakes | reaction_speed | speed_in | speed_out |
|---|---|---|---|---|---|---|
| max_verstappen | 1.00 / 0.96 | 0.96 / 0.74 | 0.75 / 0.70 | 0.85 / 0.96 | 1.00 / 0.90 | 0.99 / 0.90 |
| fernando_alonso | 0.93 / 0.90 | 0.97 / 0.69 | 0.90 / 0.64 | 1.00 / 0.90 | 0.93 / 0.70 | 0.94 / 0.70 |
| oliver_bearman | 0.65 / 0.84 | 0.77 / 0.49 | 0.65 / 0.41 | 0.65 / 0.84 | 0.68 / 0.49 | 0.78 / 0.49 |

**Which source the AI uses is unknown (Q-17).** The curve table is named `driver_characteristic_overrides`, and
the RE note puts raw values (+0xf0, from the row) and overrides (+0x108, negative = none) in the live record, so
the ratings may well override the row for every driver with a statistics holder, which is the whole 2025 grid.
In that case v0.1's row writes would be no-ops for them. Issue #7 decides; #6 waits on it.

**Q-03 (static half): `mistakes` is a skill (higher = fewer mistakes).** The `awareness_mistakes` curve rises
steadily (0→0, 0.5→0.2, 0.85→0.7, 1→1), so a more aware driver gets a higher value. The row values agree:
Alonso 0.90 > Verstappen 0.75 > rookie Bearman 0.65. The generator default (proneness) is therefore backwards.
Issue 8 (race batch) settles it at runtime.

**Q-11: 24 drivers carry a `2026` dataset:** the 2025 grid plus arvid_lindblad (max_verstappen, sergio_perez,
oscar_piastri, lando_norris, charles_leclerc, lewis_hamilton, george_russell, andrea-kimi_antonelli, lance_stroll,
fernando_alonso, yuki_tsunoda, liam_lawson, esteban_ocon, oliver_bearman, alexander_albon, carlos_sainz-jr,
pierre_gasly, jack_doohan, valtteri_bottas, nico_hulkenberg, gabriel_bortoleto, franco_colapinto, isack_hadjar,
arvid_lindblad). 71 holders have only `default`, and 22 F2 holders have `default|f2_2026`. The `2026` set is
tagged `game_setup_modes f1_26`, `seasons season_2026`, so it is what the 2026 season pack reads; its curves
differ slightly from `default` (Verstappen experience 0.88 vs 0.87, awareness and pace second points).

## Other facts the dump turned up

- **`ai_driver_config.*` exists on every driver row, but `db get` on the row doesn't list it.** The 84 names
  aren't in the launcher's name catalogue, so `db get <row>.ai_driver_config` reports "not in the game
  database". A full leaf path resolves by hash and works for `get` (and so for a `set` op). All 84 keys are
  identical for default_driver, Verstappen, Bearman and Alonso.
- **Race-start bounds, corrected:** `min_reaction_time_{lower,upper}_bound` = 0.04 / 0.28,
  `max_reaction_time_{lower,upper}_bound` = 0.24 / 0.42, `min_bad_start` = 0.04 / 0.06, `max_bad_start` = 0.28 / 0.42.
  The handoff wrote min = [0.28, 0.42], max = [0.04, 0.24] (labels swapped).
- **15 keys typed `float` in `docs/ai_driver_config_keys.*` are curves** (`@v2@…`): overtake `concede_speed_diff`,
  `concede_time_vs_behind`, `danger_overtake_pull_out_time`, `regular_overtake_pull_out_time`; blocking
  `blocking_offset_from_car_behind`, `end_blocking_time_to_corner_vs_offset`, `merge_back_to_racing_line`,
  `start_blocking_minimum_time_to_corner`; divebomb `max_presence_alongside`; cede `max/min_cede_time_ratio`;
  alongside `min_presence_within_buffer`, `off_target_angle_interpolation`, `steering_understeer_slip_max_throttle`,
  `trailbrake_speed_reduction_scalar`; offset_variation `blend_rate_inside/outside_of_curve`. A `set` with a plain
  number on these would change the type or fail; treat them as curves.
- **Label mismatches.** The sample CSV's `kimi_antonelli` is not a driver row; the row is `andrea-kimi_antonelli`.
  Five stats holders use a label with no matching driver row: `alexander_albon` (driver row `alex_albon`),
  `micheal_schumacher`, `aryton_senna`, `nilola_tsolov`, `john_benneet`. The generator assumes
  holder label == row label, so the v0.1 build would fail on Antonelli (row) and Albon (pace rating). The crosswalk
  needs both labels per driver. 197 driver rows vs 117 holders: 80 rows have no ratings at all.
- **Austria difficulty table** matches the handoff's shape: `difficulty_ratio` reaches 1 at point 7, `mass_ratio`
  drops below 1 only at points 8–10 (0.978, 0.955, 0.935); `time` 74.71 → 64.35 s.
- **f1_2025 parameter maps** match the handoff's table exactly (four dead maps: alongside_awareness, brake_off_time,
  slide_confidence, wet_weather_ability).
