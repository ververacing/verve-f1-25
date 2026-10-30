# Verve Racing for F1 25

Verve's human-like driver personalities, ported to F1 25 as [Swofty Launcher](https://f1.swofty.net) addons.
Offline, modded play only. Not affiliated with Codemasters, EA, Formula 1 or any driver or team.

| Path | What |
|---|---|
| `HANDOFF.md` | Engineering handoff: data model, roadmap, open questions Q-01..Q-16, issue backlog |
| `findings.json` | Machine-readable findings F-01..F-27 with evidence and confidence |
| `RESEARCH_LOG.md` | Dated trail; append to it |
| `docs/` | Key catalogues (`ai_driver_config`, `ai_vehicle_config`); `docs/stock/` holds stock-value dumps |
| `verve_to_swofty.py` | Generator: Verve scalars CSV -> Swofty data addon |
| `verve-f1-addon/` | The generated v0.1 addon (built from the illustrative sample CSV) |
| `tools/` | Catalogue builder and other scripts |
| `runs/` | Test runs: `runs/<date>-<variant>/` with `loader.log`, ops hash, telemetry CSV |

Work is tracked in GitHub issues. Test requests and reviews come in as issues and comments.

---

# Scalar mapping and addon generator (v0.1)

> Handing this off? Start with `HANDOFF.md` (engineering handoff, roadmap, open questions,
> issue backlog), then `findings.json` (machine-readable facts with evidence),
> `docs/ai_driver_config_keys.md` (the 84 per-driver keys, rated), `docs/ai_vehicle_config_keys.csv`
> (218 per-car keys) and `RESEARCH_LOG.md` (dated trail). This file is the v0.1 mapping only.

Turns Verve driver profiles (Pace, Aggression, Risk, Consistency, each 0 to 1) into a
Swofty Launcher data addon for F1 25. No native code, no DLL, no signature scanning:
every change is a `set` op on the game database, applied by the launcher at build time.

Everything below comes from the Swofty Launcher repo (`re/db/subsystems/ai.md`,
`tools/gamedb/catalog/keys.tsv.gz`, `docs/reference/ops/database.md`) and the
`docs/std/systems` pages, build `d873a1c8` (Steam), launcher 1.5.x / 1.6.x.

## How F1 25 models a driver's personality

F1 25 has six per-driver **characteristics**, all 0 to 1:

| Characteristic | Stock source (rating, 0 to 100) | What the engine does with it |
|---|---|---|
| `aggression` | racecraft | Evaluates `overtake.overlap_percentage` at x = aggression when within half a lap of the car ahead; drives `follow_speed_factor` and `alongside_space_factor` maps |
| `reaction_speed` | racecraft | Race-start reaction time, drawn from U[0.28 - 0.24kr, 0.42 - 0.18kr] where r = reaction_speed |
| `control` | awareness | Drives seven parameter maps: `throttle_confidence`, `throttle_exit_fallibility` (0.75x at high control), `throttle_on_time`, `brake_off_time`, `slide_confidence`, `alongside_awareness`, `wet_weather_ability` (stock 1 everywhere, dead) |
| `mistakes` | awareness | Bad race starts; direction unverified, see below |
| `speed_in` | pace | `braking_distance_factor` map (1.15x to 1.25x longer braking at low speed_in, even at high difficulty) |
| `speed_out` | pace | `corner_curvature_factor` map (0.92x at low speed_out at high difficulty) |

The rating-to-characteristic step is a `distribution` curve on the six rows of
`driver_statistics.driver_statistics.driver_characteristic_overrides`. The driver row
(`entrants.drivers.driver[_metadata_=<label>]`) carries its own
`driver_characteristics.<name>` fields which, when non-negative, **override** the derived
value. That is the hook: Verve writes the override directly and skips the curves.

Stock F1 25 overrides nothing (all 197 drivers sit on the derived values), and every
driver shares an identical `ai_driver_config`, which is why the AI feels
"overprogrammed, same decision every time".

The parameter maps are bilinear in (difficulty, characteristic), so a driver's
characteristics still separate the field at difficulty 110. They don't change the
car's ceiling: the baked per-track AI tables cap pace, so a weak driver in a fast car
loses time through braking distance, exit speed and throttle confidence, not through a
slower car.

## The mapping

Verve scalars in, F1 25 fields out. All inputs and all characteristics are 0 to 1.
Weights live at the top of `verve_to_swofty.py` and are meant to be tuned after the first
test grid.

### Driver characteristics (the core of it)

| F1 25 field | Formula | Why |
|---|---|---|
| `driver_characteristics.aggression` | 0.70 Aggression + 0.30 Risk | Overtake willingness; risk-takers also go for gaps |
| `driver_characteristics.control` | Consistency | Throttle and brake confidence, exit errors, wet ability |
| `driver_characteristics.mistakes` | 1 - (0.60 Consistency + 0.40 (1 - Risk)), i.e. error proneness | See "mistakes direction" |
| `driver_characteristics.reaction_speed` | 0.60 Aggression + 0.40 Pace | Launch reaction; Verve has no reaction axis |
| `driver_characteristics.speed_in` | 0.80 Pace + 0.20 Risk | Braking distance; late brakers |
| `driver_characteristics.speed_out` | 0.80 Pace + 0.20 Consistency | Corner curvature and exit |

### Pace rating (so simulated sessions and the career UI agree)

Simulated and skipped sessions use baked lap times plus the **ratings**, not the
physics, so the `pace` rating must track Verve Pace or a skipped FP3 will contradict
the race.

`driver_statistics.driver_statistics.DriverStatisticsHolder[driver=<label>].StatisticsDataSet[_metadata_=default].Statistic[_metadata_=pace]`
field `evolution` = `@v2@minx:0,maxx:10,miny:0,maxy:100,0:y,0:y,1:y,1:y` with
y = (floor + Pace x (ceiling - floor)) / 100. Default band 70 to 99.

Only the `default` dataset is written. Some drivers also have a `2026` dataset; a
`set` that selects a missing row fails the build, so add those per driver by hand or
extend the script once you know which drivers carry it.

### Strategy (optional, on by default)

Per-driver strategy tendencies live on the same driver row. Stock ranges from the
key catalogue:

| F1 25 field | Stock range | Formula |
|---|---|---|
| `driver_strategy.fastest_strategy_base_selection_chance` | 0.15 to 0.85 | 0.15 + 0.70 Risk |
| `driver_strategy.safety_car_pit_wear_min` | 0.10 to 0.35 | 0.35 - 0.25 Risk |
| `driver_strategy.safety_car_pit_wear_max` | 0.20 to 0.50 | 0.50 - 0.30 Risk |

Fuel load and weather-change timing are left stock; their semantics are not decoded.

### Not mapped (yet)

- `ai_driver_config.*` (84 per-driver keys: overtake 19, blocking 16, space_seeking 13,
  race_start 9, cede_position, divebomb_defense, exit_fallibility, offset_variation,
  alongside). Identical for all 197 stock drivers. A plain `set` on them works (keys
  resolve by hash); 11 are decoded, 32 are name-obvious, 41 should stay stock until
  traced. Full catalogue with ratings: `docs/ai_driver_config_keys.md`. This is v0.2.
- `ai.driver_variation.in_race` (84 global form curves: `consistent_*`,
  `inconsistent_*`, `mid_race_mistake`, `bad_race_day_*`...). This is F1 25's own
  Consistency axis but the selection is global per session type, not per driver.
  Weighting it per driver needs a native hook.
- `driver_characteristics.preferred_tracks` (list of track labels). Passthrough column
  in the CSV if you want to use Verve's style descriptor for it.

## Mistakes direction (verify first)

The characteristic is named `mistakes` and the RE notes say "bad start from mistakes",
which reads as proneness (higher = more mistakes). But it is derived from the
awareness rating through a curve the catalogue truncates, so it could equally be
"mistake resistance". The script defaults to proneness. Verify with one race: give
one driver `mistakes` = 0.95 and another 0.05, both with identical other values, and
watch who botches starts and corner exits. If it is backwards, rerun with
`--mistakes-is-skill`.

## Verification plan (one evening)

1. Install Swofty Launcher 1.5.13+, make a profile "Verve test", drag the addon zip onto
   Addons, enable, Play. Check `swofty/loader.log` for the build applying
   `yourname.verve-f1` with no "no such key" line.
2. Mistakes direction, as above.
3. Override takes effect at all: set one driver's `aggression` to 0.0 and another's to
   1.0, run a 25% race from the back with both; the 1.0 driver should attack, the 0.0
   driver should sit in the train.
4. Pace rating is visible in the driver stats UI (Career > Drivers), so the `evolution`
   write is easy to confirm without racing.
5. Whether a changed config applies mid-session or only at session load is unverified
   in the Swofty docs. Always restart the session after rebuilding.

## Files

- `verve_to_swofty.py`: the generator. `python3 verve_to_swofty.py profiles.csv --out verve-f1-addon`
- `verve_grid_2025.csv`: sample input, the 2025 grid plus reserves, **illustrative
  scalars only** (not Verve data). Replace the numbers with your real profiles.
- `verve-f1-addon/`: the generated addon (`swofty.json` + `db/verve.json`). Zip the
  folder and drag it onto the launcher's Addons page.

## CSV columns

```
label,display,pace,aggression,risk,consistency[,preferred_tracks]
max_verstappen,Max Verstappen,0.98,0.90,0.70,0.90,
```

`label` is the driver row's `_metadata_` (e.g. `carlos_sainz-jr`, `kimi_antonelli`,
`oliver_bearman`). The 2025 grid labels are in the sample CSV; others are in the
Swofty key schema (`docs/reference/gamedb/schema.md`) or the DB Editor's Drivers page.
`preferred_tracks` is a comma-free list separated by `|` (e.g. `monaco|singapore`).
