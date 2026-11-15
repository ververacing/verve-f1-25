# AI Driver Behaviour

| | |
|---|---|
| Id | `kizi.ai-driver-behaviour` |
| Version | 0.1.9 (catalog latest and installed copy). The public GitHub repo is at 0.1.8 (its `swofty.json`). `res/dll.rc` in both still says 0.1.8. |
| Author | Kizi |
| Licence | MIT (manifest, `LICENSE` in the repo, SPDX headers in the source) |
| Source | https://github.com/Kizikafuka/f1-25-ai-driver-behaviour (catalog `repository`, manifest `repository`). The installed copy also ships `source_code\`. |
| Game build | Not stated. Manifest `compat.game` is `f1_25` with no `game_builds`. README: "F1 25 on Steam". |
| Launcher | `>=1.8.19` (manifest and catalog). The README still says "1.7.0 or newer". |
| Requires | `swofty.core >=0.1.0` |
| Kind | native + database |

Sources read: catalog entry (2026-11-14); installed `%LOCALAPPDATA%\Swofty\addons\kizi.ai-driver-behaviour\` (`swofty.json`, `registry.json`, `README.md`, `db/racecraft.json`, `source_code/tools/make_ops.py`, `source_code/native/src/ai_driver_behaviour.cpp`, `source_code/common/*.hpp`, `source_code/res/dll.rc`); the GitHub repo's files at `main`. The repo's `db/racecraft.json` and `tools/make_ops.py` are identical to the installed copy (line endings aside). Stock values: `docs/stock/ai_driver_config.csv` and `docs/stock/ai_vehicle_config_redbull_2025.txt` (Swofty 1.6.11 dump, build 25251167).

## What it changes

Database edits only. The DLL does nothing but log one line (`ai_driver_behaviour.cpp` lines 11-14). `db/racecraft.json` holds 17,131 `set` ops, each gated by an option. They are applied at game boot, so changes need a game restart ("rebuild" in `swofty settings list`).

- **Close racing:** the gap every AI car keeps to other cars; how far a car must be alongside before the AI makes room; optionally a fixed per-driver spread of that value plus attack distance and commitment to a pass.
- **Slides:** weaker steering correction, less or no traction control, later throttle lift in a slide, an earlier spin angle.
- **Damage:** damaged cars slow down less and keep a higher speed with a puncture.

Rows touched: every `entrants.vehicles.vehicle` row that has the field (413 rows, safety-car rows included) and every `entrants.drivers.driver` row (197 rows). Rows are picked by `_metadata_` label (`make_ops.py` lines 32-36, 69-90, 100-132).

**The catalog description is out of date.** It still lists two "Pace" settings (`ai.grip_scale` live layers) and a "Recommended settings" list. Pace was removed in 0.1.7. The AI planned corner speeds from more grip than the car had and hit the barriers on tight tracks such as Monaco (`ai_driver_behaviour.cpp` lines 4-6; installed README). The installed manifest has no Pace options. The grip-layer code survives, unused, in `common/kizi_grip.hpp`.

## Settings (installed manifest)

| Option id | Label | Values (label = value) | Default |
|---|---|---|---|
| `spacing` | Close racing: gap to other cars | Stock 0.35, Closer 0.25, Tight 0.15, Very tight 0.08, Extreme 0.04, None 0 | Tight (0.15) |
| `alongside` | Close racing: when they make room | Stock 0.33, Later 0.5, Much later 0.7, Very late 0.85, Almost never 0.95 | Much later (0.7) |
| `variety` | Close racing: drivers differ | Off, Small, Medium, Big | Medium |
| `steer_correction` | Slides: steering correction | Stock, 75 %, 50 %, 25 % | 25 % |
| `traction_control` | Slides: traction control | Stock, Half, Off | Half |
| `throttle_cut` | Slides: when they lift off | Stock 0.5, Later 0.75, Much later 1.0 | Much later (1.0) |
| `give_up` | Slides: when they lose the car | Stock 0.4 (23 deg), Sooner 0.3 (17 deg), Much sooner 0.2 (11 deg) | Sooner (0.3) |
| `damaged_driving` | Damage: speed with a damaged car | Careful (game), Pushing, Flat out | Pushing |

The catalog's "Recommended settings (what we tested)" differ from these defaults: it says drivers differ Small, steering 50 %, traction control Off, lift-off Later. The manifest defaults are Medium, 25 %, Half and Much later.

## Keys it touches

Provenance: **M** = manifest option values; **P:n** = `source_code/tools/make_ops.py` line n; **J:n** = first op for that field in `db/racecraft.json` at line n. Stock: Red Bull 2025 vehicle row and the per-driver rows from our dump (driver values are identical on all rows dumped).

### Per car (`entrants.vehicles.vehicle[...]`)

| Key (`ai_vehicle_config.`...) | Stock | Addon value per option | Provenance |
|---|---|---|---|
| `buffer_space_settings.vehicle_buffer` | curve, 0.35 at every speed | curve, flat at the `spacing` value (0.35 / 0.25 / 0.15 / 0.08 / 0.04 / 0). Always written. | M, P:25-26, J:7 |
| `pedal_controller.lateral_traction_slip_angle_cut_in_proportion` | 0.5 | `throttle_cut` value (0.5 / 0.75 / 1.0). Always written. | M, P:28, J:2485 |
| `lost_control.angle` | 0.4 (rad, about 23 deg) | `give_up` value (0.4 / 0.3 / 0.2). Always written. | M, P:29, J:4963 |
| `steering_pid_settings.proportional_gain` | -2 | stock x 0.75 / 0.5 / 0.25 = -1.5 / -1 / -0.5 | P:96, 105-110, J:49348 |
| `steering_pid_settings.integral_gain` | -1 | x 0.75 / 0.5 / 0.25 = -0.75 / -0.5 / -0.25 | P:105-110, J:49357 |
| `steering_pid_settings.derivative_gain` | -0.5 | x 0.75 / 0.5 / 0.25 = -0.375 / -0.25 / -0.125 | P:105-110, J:49366 |
| `steering_pid_settings.output_smoothing_half_life` | 0.3 | stock / 0.75 / 0.5 / 0.25 = 0.4 / 0.6 / 1.2 | P:111-114, J:49375 |
| `traction_control.grip_atc_strength` | curve, points 0.84 / 0.92 / 1 ... 0 | every point x 0.5 (Half) or x 0 (Off) | P:99, 128-132, J:49582 |
| `damage_settings.aero_speed_reduction_factor` | 0.12 | x 0.5 (Pushing) = 0.06; x 0.25 (Flat out) = 0.03 | P:117-123, J:49456 |
| `damage_settings.aero_radius_modifier` | 0.04 | 0.02 / 0.01 | same, J:49465 |
| `damage_settings.aero_brake_distance_increase_factor` | 0.1 | 0.05 / 0.025 | same, J:49474 |
| `damage_settings.burst_speed_reduction_factor` | 0.325 | 0.1625 / 0.0813 | same, J:49483 |
| `damage_settings.burst_radius_modifier` | 0.3 | 0.15 / 0.075 | same, J:49492 |
| `damage_settings.burst_brake_distance_increase_factor` | 0.25 | 0.125 / 0.0625 | same, J:49501 |
| `speed_limit_settings.puncture_speed_limit` | 40 | x 1.5 (Pushing) = 60; x 2 (Flat out) = 80 | P:117, 124-127, J:49510 |

The example values are the Red Bull 2025 row in `racecraft.json`. Each car's ops are computed from that car's own stock value, so other rows can differ. "Stock" or "Careful" means no op for the scaled keys.

### Per driver (`entrants.drivers.driver[...]`)

| Key (`ai_driver_config.`...) | Stock | Addon | Provenance |
|---|---|---|---|
| `alongside.min_presence_within_buffer` | curve, flat 0.33 | Variety Off: flat curve at the `alongside` value. Variety on: flat curve at clamp(base + a x 0.12 x s, 0.05, 0.98), s = 0.5 / 1.0 / 1.5 for Small / Medium / Big (spread of +-0.06 / 0.12 / 0.18). Always written. | P:57-59, 75-83, J:7441 |
| `overtake.close_range_car_lengths_to_start_overtake` | 1.5 | Variety on only: max(0.2, stock x (1 + a x 0.3 x s)), +-15 / 30 / 45 %. Not on `default_driver`. | P:60, 84-90, J:7759 |
| `overtake.braking_zone_abort_overtake_time` | 0.6667 | Variety on only: max(0.2, stock x (1 - a x 0.4 x s)), +-20 / 40 / 60 %. Not on `default_driver`. | P:61, 84-90, J:7786 |

`a` is a fixed number from -1 to 1 per driver row, made from an FNV-1a hash of the row label (triangular spread; `style()`, P:64-66). It is 0 for `default_driver`. Example, `max_verstappen` (a is about +0.59, worked back from the values), with `alongside` = 0.7: make room at 0.7355 / 0.7709 / 0.8064, start overtake at 1.633 / 1.7659 / 1.8989 car lengths, abort time 0.5879 / 0.5091 / 0.4303 s (Small / Medium / Big; from `racecraft.json`).

Earlier survey claims checked: stock gap 0.35 and stock alongside 0.33 match the manifest, the catalog and our dump.

## Protected keys

None. No op in `racecraft.json` writes a `cede_position.*`, `yellow_flag_*` or `flying_lap_yield_*` field (all 17,131 ops checked by field name).

## Stacks and conflicts

- `registry.json`: conflicts with `kizi.ai-tweaks` (Contact Physics) **below 0.5.0**, because the old AI Racing Tweaks "also sets the racecraft, car control and driver variation values". From 0.5.0 they work together (README, catalog).
- Lap 1 Realistic AI says it stacks with this addon (Lap 1 catalog). Both change `overtake.close_range_car_lengths_to_start_overtake` and `overtake.braking_zone_abort_overtake_time`. This addon writes the database row; Lap 1 sets a live layer on lap 1 only. The pace multiplication Lap 1 mentions no longer applies, because Pace was removed here.
- Overlap with any addon that edits these per-car or per-driver rows (for example a Verve per-driver profile): not stated by the author. Load order decides which `set` wins.

## What the authors admit

From the catalog (written for the Pace-era version, still shown for 0.1.9):

- "Experimental. We tested that the settings load and run. How much each one changes the racing is not measured."
- "Drivers differ" is a first version. It changes database values known only by their names, and "The effect on track is not checked." A driver added by a mod gets the plain values.
- "The gap to other cars is the same for every car": the game keeps it per team car.
- "A closer, harder AI means more contact."
- The one test race used gap Extreme, make room Much later, drivers differ Small, pace spread Medium; "we did not measure the effect."

## Not determined

- Which of these keys the game actually reads in a race, and in which direction, is not shown by the author. The names are the only evidence.
- How `vehicle_buffer` and the `alongside` curve are read across their x axes. The addon writes flat curves, so the x mapping does not matter for its values.
