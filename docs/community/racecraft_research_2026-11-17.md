# Racecraft aggression, per-car AI traits and build gates (desk research, 2026-11-17)

Source: Swofty's public repo `Swofty-Developments/SwoftyLauncher`, shallow clone at `c01366b` (2026-11-17, past 1.9.61). Citations are `path:line` in that repo. Read only: nothing was built, run or launched, and no closed DLL was opened. "Unproven" means the source doesn't settle the point.

Builds: the "KB" build is Steam 25251167 (`d873a1c8`, PE timestamp 1789118616; `docs/reference/addons/first-addon.md:148`, `native/src/core/live/live_rows.hpp:177`). The current Steam build is 26566308 (1.0.145.2472, PE timestamp 1794312636; `re/research/live-steam-26566308.md:5-7`).

## 1. `ai::VehicleConfig.racecraft.{overtake_aggression, defend_aggression}`

- **Status: design only.** No database key, struct slot or code exists for these two fields.
  - The guide's own banner says that in 1.6.0 the header has only `ai.controller.update`. It says the registries, `vehicle_configs` among them, "ship later" and that those sections describe the design (`docs/std/systems/ai.md:12-14`).
  - The shipped SDK header has only `ControllerUpdate` (`packages/sdk/include/swofty/systems/ai.hpp:8-25`).
  - `overtake_aggression` and `defend_aggression` appear only in docs and in one registry-merge test fixture (`packages/sdk/std/tests/cases/029-tagged-field.json:43`).
  - The game database has no `racecraft` group. The 220 `ai_vehicle_config.*` keys run from `native/src/core/apply/content/row_keys.inc:811` to `:1031`. Its `overtake` group holds 4 unrelated keys (`:952-955`), and its `blocking` group holds 5 (`:827-831`).
  - `AiHandlingConfig.h` and `AiDriverConfig.h` have no aggression slot.
- **Where it would live.** Per vehicle, which is the team car. The design comment maps it to `entrants.vehicles.vehicle_N.ai_vehicle_config` (`ai.md:43`). The game builds that config once per `entrants.vehicles` row at startup, keyed by the vehicle stat id (`re/db/functions.tsv:3889`, `:3887`), so teammates on the same vehicle row share it. That they share it at runtime is inferred, not traced.
- **Tick reader:** none, because no data path exists.
- **Range and stock value:** not documented. The only numbers are example values (0.85, 0.8, 0.9) in the docs (`docs/std/layers.md:151-152`).
- **The real aggression is per driver:** `entrants.drivers.driver_N.driver_characteristics.aggression` (`row_keys.inc:575-587`).
  - Range 0 to 1, step 0.01 (`packages/core/src/dbedit/modules.json:223-231`). Stock drivers sit between 0.2 and 1 (`docs/using/driver-manager.md:30`).
  - Proven reader 1: `overtake.overlap_percentage` is evaluated "at x = aggression" in the overtake helper (`re/db/structs/AiDriverConfig.h:64`; `re/db/subsystems/ai.md:166`). The independent verify row agrees on the slot offset only, with "asm check not done" (`re/db/verify.tsv:8653`).
  - Reader 2, inferred: aggression is the characteristic of the `alongside_space_factor` and `follow_speed_factor` parameter maps (`docs/reference/gamedb/schema.md:1668`, `:1688`). Those are map indices 1 and 5 (`ai.md:184`). That fits profile `+0xc4` (vehicle-buffer scale, read per tick at `0x14060e641`) and `+0xd4` (follow buffer) (`ai.md:221`; `verify.tsv:10648`). The mapping from map index to offset is an inference, and the writer of `+0xc0..+0xe8` is "not found" (`ai.md:166`).

## 2. Does `cars::live` or Live State expose per-car aggression or AI traits?

No.
- **`cars::live`:** its only AI fields are the 59 `ai.<group>.<key>` driver-config slots (blocking, alongside, divebomb_defense, offset_variation, overtake, space_seeking) plus `ai.grip_scale` (`docs/std/systems/car-physics.md:190-192`; `ai.md:292-358`). `cede_position.*`, `exit_fallibility.*` and `race_start.*` are explicitly not fields (`ai.md:391`). No `driver_characteristics` or profile field exists.
- **Live State:** `SwoftyLiveCar` carries only flags (player / AI driving / watched / racer), physics, ERS, lap, position, pit, tyre, penalty and DRS data (`docs/reference/std/live.md:95-129`). Its 21 groups contain no AI group (`native/src/core/live/live_rows.hpp:96-122`).

## 3. Per-car live fields on 26566308 vs the KB build

- **Build checks.**
  - `same_build()` is true only for the KB stamp 1789118616 (`native/src/core/stage.cpp:204-209`).
  - `verified_build()` is true for the KB, EA 1789128892 and Steam 1794312636 (26566308) (`stage.cpp:211-218`).
- **`cars::live`, including the 59 `ai.*` racecraft layers: KB only, off on 26566308.**
  - Live car operations log "off" unless `same_build()` (`native/src/core/hooks/car_live.cpp:508-516`).
  - The car events are not armed (`car_live.cpp:635-638`).
  - The levers and the racecraft mixin return early on `!same_build()` (`car_live.cpp:691`, `:703-711`).
  - The docs agree: "on any other build ... `cars::live::available()` is false" (`car-physics.md:196`), and `cars::live` is "on the KB build only" (`docs/std/systems/cars.md:500`).
- **Live car signals (shaders, `fields_of(same_build, verified_build)`).**
  - On 26566308: `table` and `drs` only (`native/src/core/live_car_logic.hpp:22-28`; `native/src/core/live_car.cpp:46`). `table` covers the vehicle table, CarLive, engine, gearbox, chassis, body, steering, suspension and wing-open fraction (`live_car_logic.hpp:3-7`).
  - KB only: per-wheel surface, wheel wetness, spin and slip, chassis orientation, angular velocity and track wetness (`live_car_logic.hpp:7-8`, `:26`; `live_car.cpp:61-63`).
- **Test-agent `car[...]` read/set: KB only.**
  - The table covers chassis mass, fuel, engine, gear, brake bias, ERS energy and mode, fuel mode and drag (`native/src/core/testagent/agent.cpp:371-386`).
  - `car_unbound()` refuses on any build but the KB (`agent.cpp:393-396`). Save, tile and HQ commands are gated the same way (`agent.cpp:40-42`, `:1265`, `:1352`).
- **Live State: all 21 groups on 26566308.** These are car systems, ERS, world, aero/DRS, progress, classification, timing, pit, pit lane, penalties, tyres, flags, controllers, spectator, spectator gap, mode, badges, track, track name, bus events and driver names (`live_rows.hpp:186-193`; `docs/releases/1.9.61.md:13`). ERS mode moves to `+0x1a6c` there.
  - Runtime validation of the broader API (T154) is still pending (`live-steam-26566308.md:11-13`).
  - None of these fields is an AI trait.

## 4. The per-car AI driver record (0x1a0-byte profile)

- **Layout.** Raw `driver_characteristics` sit at `+0xf0..+0x104`, overrides at `+0x108..+0x11c` (negative means none), and effective values at `+0xa8..+0xbc`: aggression, control, mistakes, reaction speed, speed in, speed out (`ai.md:166`).
- **When it is built: session enter, not race start.**
  - `Ai_Build_DriverProfiles` has one caller, `Sess_Build_AiSystem` (`re/db/functions.tsv:735`; verify agree `verify.tsv:10573`). That function runs on session enter from `Game_GameModule_OnSessionEnter` (`functions.tsv:686`).
  - Per car, the builder looks up the entrant's driver label in `entrants.drivers` and reads 6 floats from that row. It falls back to 1.0 x6 / -1.0 x6 when the row is missing (`functions.tsv:735`).
  - The normalisers are recomputed later by `Ai_DriverVariationInRaceSystem_Setup` (`functions.tsv:736`).
- **Do DB overrides reach it in a GP?** Partly settled.
  - Data edits apply while the game boots (`docs/reference/data/database.md:163`), so a `driver_characteristics` edit is in the database before any session reads it.
  - Unproven: who writes the `+0x108` overrides and the effective `+0xa8..+0xbc` values. The notes leave it open: "whoever writes those profile fields after the build is the next place to look" (`ai.md:221`).
- **Read paths on 26566308.**

| Path | Documented? | Risk on 26566308 |
|---|---|---|
| `cars::live` field | No profile field exists | Off anyway (KB only, section 3) |
| Live State | No AI group | Not applicable |
| Test-agent command | Only `car[...]` physics fields | KB only (`agent.cpp:393-396`) |
| Native probe via `AiSystem.records_begin +0xa8` -> `AiCarRecord` (stride 0x508) `+0x20 driver_profile` -> `+0xa8..+0xbc` | The first two hops are exported L2 with agree rows (`native/include/swofty/game/ai.hpp:177-195`, `:257-261`; `verify.tsv:8610`, `:10648`). The 0x1a0 profile has no struct header, so `+0xa8..+0xbc` exist only as inbox notes (`ai.md:166`) | High. The hook site and `Ai_Build_DriverProfiles` resolve on 26566308 only as captured pattern hints (`re/db/builds/steam-26566308.json:599-601`, `:10325-10327`; `re/PROTOCOL.md:183`), but no layout is proven for that build. Swofty's own consumer of this chain is gated to the KB (`car_live.cpp:691`). |

## 5. Why per-driver overrides could work in benchmark/Time-Trial-like modes but not in a GP

Swofty's source has no direct statement on this. The source points to these candidates, all unproven:
- **In-race driver variation outranks the DB value.**
  - The effective trait is taken first from the in-race variation record's value/flag pairs, then from the override at `+0x108` (when it is >= 0), then from the raw `+0xf0` (`functions.tsv:736`, verified `verify.tsv:10590`).
  - Variation is enabled per game mode: Time Trial off; Practice, Qualifying and Race on (`ai.md:204`). The L2 row marks this as DB-side and not re-checked (`functions.tsv:1238`).
  - That precedence is proven for the normaliser only. That the effective `+0xa8..` follows it too is unproven.
- **Ratings-derived overrides.**
  - `driver_statistics.driver_characteristic_overrides` has rows labelled `racecraft_aggression`, `racecraft_reaction_speed`, `awareness_control` and `awareness_mistakes` (`tools/gamedb/catalog/tables.tsv:259`; `docs/reference/gamedb/catalogue.md:287`). This looks like a map from the racecraft and awareness ratings onto the traits.
  - If championship and career sessions fill `+0x108` from it, a GP would ignore a raw `driver_characteristics` edit. The writer is not documented.
- **Per-mode driver overrides.** Each `game_modes` entry parses `benchmark`, `timetrial` and `driver_%s_override` fields (`re/db/subsystems/game.md:138`). Their meaning is unproven.
- **Ruled out by the source:** the record being built before data ops apply. The ops apply at boot (`database.md:163`), and the profile is built at each session enter (`functions.tsv:735`, `:686`).

## Implications for Verve

- Drop any plan that relies on `racecraft.overtake_aggression` or `defend_aggression`. They have no data path and no reader, only a design note. The per-driver `driver_characteristics.aggression` (0 to 1) is the real lever, and it feeds `overtake.overlap_percentage` and, by inference, the space and follow buffers.
- On 26566308, `cars::live` is off entirely: no racecraft layers and no per-car field reads. Live State works, but it has no AI-trait data. Racecraft work through `cars::live` needs the KB build 25251167 or a future Swofty build proof.
- A GP-vs-benchmark difference in trait overrides is most plausibly the variation record or the ratings-derived overrides taking precedence. The next test is to compare the same edit in a GP with in-race variation on and off, and with the driver's racecraft/awareness ratings changed. A desk read can't settle it.
- A read-only native probe of profile `+0xa8..+0xbc` on 26566308 relies on KB-only layouts and undocumented profile offsets. Treat any result from it as unverified, and ask the supervisor before building one.
