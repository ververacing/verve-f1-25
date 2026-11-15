# Lap 1 Realistic AI

| | |
|---|---|
| Id | `swofty.lap1-ai` |
| Version | 1.0.0 (catalog and installed copy agree) |
| Author | Swofty |
| Licence | MIT (installed `swofty.json`). The catalog has no licence field. |
| Source | Not public. Catalog `homepage` and `repository` are null. The installed `README.md` quotes the lever table from the source (`kLevers[]`). The DLL itself is a closed binary. |
| Game build | `compat.game_builds: [">=25251167"]` (manifest). Catalog: game `f1_25`. |
| Launcher | `>=1.8.6` (manifest and catalog) |
| Requires | `swofty.core >=0.2.13` (manifest and catalog) |
| Kind | native (one DLL: `native/lap1_ai.dll`) |
| Settings | None |

Sources read: catalog entry (api.f1.swofty.net/v1/addons, 2026-11-14), installed `%LOCALAPPDATA%\Swofty\addons\swofty.lap1-ai\swofty.json` and `README.md`. Stock values: `docs/stock/ai_driver_config.csv` (Swofty 1.6.11 dump, build 25251167).

## What it changes

On lap 1 of a race or sprint only, every AI car:

- plans braking and corner speed from 10 % more grip (dry races only);
- defends from further back and treats slower-closing cars as threats;
- starts overtakes from further back, keeps them going longer, and does not drop them when the car ahead brakes early;
- pulls out of a queue sooner and with less clear track;
- holds its place in traffic instead of conceding after 5 s;
- may stay off the racing line into a corner, and yields half as much when alongside.

Each car goes back to the game's values when it starts lap 2. A red-flag restart is a new lap 1 (catalog, README).

How lap 1 is tracked (README lines 22-25): `race.start` arms every AI car. A `session.lap` for a car 40 s or more after lights out ends that car's lap 1. `session.end`, `session.unload` or 20 minutes after lights out end it for all cars.

Mechanism: each lever is a layer on a live car field (`ai.*`), one per AI car, released at the end of lap 1. It does not write the game database. `ai.grip_scale` is a `scale` layer; the others replace the value (README line 36). On a core without the live `ai.blocking/overtake/space_seeking/offset_variation/alongside` fields it logs each refused field and runs without it (README line 18).

## Keys it touches

Value provenance: **R:n** = installed `README.md`, line n (the `kLevers[]` block, lines 39-70). Stock = `docs/stock/ai_driver_config.csv` (identical on all four rows dumped) unless noted. The live field `ai.X.Y` is the runtime copy of `ai_driver_config.X.Y`; that mapping is by name only.

| Live field (lap 1 only) | Stock | Addon | Provenance |
|---|---|---|---|
| `ai.grip_scale` (scale layer) | 1.0 (no layer) | x1.10 | R:40 |
| `ai.blocking.max_blocking_distance` | 18 | 45 | R:41 |
| `ai.blocking.max_blocking_distance_at_race_start` | 18 | 45 | R:42 |
| `ai.blocking.fraction_of_follow_speed` | 0.975 | 0.7 | R:43 |
| `ai.blocking.fraction_of_follow_speed_at_race_start` | 0.875 | 0.6 | R:44 |
| `ai.overtake.attacker_close_enough_car_lengths` | 3 | 6 | R:45 |
| `ai.overtake.braking_zone_abort_overtake_time` | 0.6667 | 0.1 | R:46 |
| `ai.overtake.close_range_car_lengths_to_start_overtake` | 1.5 | 4.0 | R:47 |
| `ai.overtake.close_range_car_lengths_to_continue_overtake` | 2 | 4.5 | R:48 |
| `ai.overtake.oppertunist_overtake_time` | 0.25 | 1.5 | R:49 |
| `ai.overtake.regular_overtake_initiate_time_adjustment` | 0.75 | 2.75 | R:50 |
| `ai.overtake.regular_overtake_continue_time_adjustment` | 1.25 | 3.25 | R:51 |
| `ai.overtake.danger_overtake_initiate_time_adjustment` | 0.5 | 2.5 | R:52 |
| `ai.overtake.danger_overtake_continue_time_adjustment` | 0.75 | 2.75 | R:53 |
| `ai.overtake.regular_overtake_pull_out_time` | curve, points 0.325-0.4625, axis maxy 4 (see note) | 2.0 | R:54 |
| `ai.overtake.danger_overtake_pull_out_time` | curve, points flat 0.5, axis maxy 4 (see note) | 1.5 | R:55 |
| `ai.overtake.overlap_percentage` | curve over aggression, 0.567 down to 0.05 | 0.05 | R:56 |
| `ai.space_seeking.concede_overtake_blocked_by_crowed_time` | 5 | 60 | R:57 |
| `ai.offset_variation.offset_limit_at_corner_start` | 0.2 | 1.0 | R:58 |
| `ai.space_seeking.total_queue_needed` | 3 | 1 | R:59 |
| `ai.space_seeking.car_in_front_needed` | 2 | 1 | R:60 |
| `ai.space_seeking.time_to_switch_sides` | 2 | 0.3 | R:61 |
| `ai.space_seeking.track_distance_needed` | 170 | 60 | R:62 |
| `ai.space_seeking.speed_below_follow` | 4 | 8 | R:63 |
| `ai.space_seeking.first_speed_below_follow` | 2 | 5 | R:64 |
| `ai.space_seeking.distance_braking_point` | 75 | 150 | R:65 |
| `ai.space_seeking.can_start_track_radius` | 400 | 800 | R:66 |
| `ai.space_seeking.track_abort_distance` | 50 | 100 | R:67 |
| `ai.alongside.yield_overtake_rate` | 1 | 0.5 | R:68 |
| `ai.alongside.speed_difference_for_limited_zone_yielding` | 3 | 1.5 | R:69 |

30 levers in all. The README's own "game:" values match the stock dump where it gives them (18 m, 97.5 %, 87.5 %, 1.5, 2, 3, 0.667 s, 0.25 s, 3 cars, 2 cars, 2 s, 170 m, 400 m, 5 s, 0.2). The README does not state stock for `speed_below_follow`, `first_speed_below_follow`, `distance_braking_point`, `track_abort_distance` or `speed_difference_for_limited_zone_yielding`; those stock values come from our dump only.

Earlier survey claims checked: "overtakes from 4 car lengths instead of 1.5", "defence from 45 m instead of 18 m" and "leaves a queue after 0.3 s instead of 2 s" all match R:41, R:47, R:61 and the stock dump.

## Protected keys

None. It does not touch any `cede_position.*`, `yellow_flag_*` or `flying_lap_yield_*` key (full lever list, R:40-69).

## Stacks and conflicts

- Catalog: "Contact Physics and AI Driver Behaviour stack with it, and their pace settings multiply with this one."
- README line 36: AI Driver Behaviour's "Pace" settings multiply with `ai.grip_scale`. Note: AI Driver Behaviour removed its Pace options in 0.1.7 (its `ai_driver_behaviour.cpp`, lines 4-6). With the current 0.1.9 nothing multiplies with this grip layer from that addon.
- Overlap with AI Driver Behaviour: both change `overtake.close_range_car_lengths_to_start_overtake` and `overtake.braking_zone_abort_overtake_time`. AI Driver Behaviour writes the database row (with "Drivers differ" on); this addon sets a live layer on lap 1. Which one wins on lap 1 is not stated by either author. Presumably the live layer, but not checked.
- No declared conflicts (no `registry.json` in the installed copy).

## What the authors admit

- "Expect more contact between AI cars on lap 1" (catalog).
- Pace lever: dry races only (catalog, README line 11).
- No measurements of the effect are given.

## Not determined

- The DLL is closed. Behaviour above is from the catalog text and the README's lever table only. The README's source excerpt cannot be checked against the binary.
- Pull-out times. The stock values are `@v2@` curves with `maxy:4`. The README reads them as raw seconds ("game: about 0.4 s"). If the curve points are normalised to the axis (other stock curves, such as `cede_position.max_cede_time_ratio` with `miny:1` and points below 1, suggest they are), stock is about 1.3-1.85 s regular and 2.0 s danger. Then the lap-1 danger value (1.5) would be lower than stock, not higher. Not resolved.
- Whether `ai.*` live fields map one to one onto the `ai_driver_config.*` database keys is assumed from the names.
