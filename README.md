# Verve Racing for F1 25

Verve's human-like driver personalities, ported to F1 25 as [Swofty Launcher](https://f1.swofty.net) addons.
Offline, modded play only. Not affiliated with Codemasters, EA, Formula 1 or any driver or team.

| Path | What |
|---|---|
| `HANDOFF.md` | Engineering handoff: data model, roadmap, open questions Q-01..Q-16, issue backlog |
| `findings.json` | Machine-readable findings F-01..F-27 with evidence and confidence |
| `RESEARCH_LOG.md` | Dated trail; append to it |
| `docs/` | Key catalogues (`ai_driver_config`, `ai_vehicle_config`); `docs/stock/` holds stock-value dumps |
| `verve_to_swofty.py` | Generator: Verve profiles (pinned `drivers.lua` + `data/crosswalk_f1.csv`) -> Swofty data addon |
| `verve-f1-addon/` | The generated v0.2 addon, built from Verve's real profiles |
| `tools/` | Catalogue builder and other scripts |
| `runs/` | Test runs: `runs/<date>-<variant>/` with `loader.log`, ops hash, telemetry CSV |

Work is tracked in GitHub issues. Test requests and reviews come in as issues and comments.

---

# Scalar mapping and addon generator (v0.2)

> Handing this off? Start with `HANDOFF.md` (engineering handoff, roadmap, open questions,
> issue backlog), then `findings.json` (machine-readable facts with evidence),
> `docs/ai_driver_config_keys.md` (the 84 per-driver keys, rated), `docs/ai_vehicle_config_keys.csv`
> (218 per-car keys) and `RESEARCH_LOG.md` (dated trail). This file is the v0.2 mapping only.

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
| `mistakes` | awareness | Bad race starts: the bad-start draw is U[0.06 - 0.02km, 0.42 - 0.14km] where m = mistakes, so higher = fewer bad starts (F-37, F-39) |
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

## The mapping (v0.2: #5, #6)

Verve scalars in (Pace, Aggression, Risk, Consistency, each 0 to 1), F1 25 fields out. Weights, `K` and the center
live at the top of `verve_to_swofty.py`.

**Source.** Verve's own profiles, read from `ververacing/verve` `lib/drivers.lua` at a pinned commit
(`VERVE_COMMIT`, checked by git blob hash) and joined to F1 25 rows through `data/crosswalk_f1.csv` (real names, F1
only; the rest of Verve's roster stays off this repo). `tools/fetch_verve.ps1` fetches the pinned file into the
gitignored `.cache/`. Grid drivers with no Verve profile are listed in the crosswalk with key `-` and left stock
(today: Jack Doohan).

**Anchor.** Every characteristic starts from the driver's own stock row value (`docs/stock/driver_characteristics_grid.csv`)
and Verve moves it: value = stock + K x (signal - center), clamped to 0 to 1, with K = 0.5 and center = that
signal's mean over the grid being written. The row is what the AI reads (rows win in benchmark, F-36), so every
driver keeps the F1 25 baseline and Verve moves it from there. Verve's 0.5 is the average of its whole F1 bucket,
classic and IndyCar drivers included, and the modern grid sits well above it, so centering at 0.5 would lift nearly
everyone (26 of 138 values clamped at 1; `--center 0.5`).

### Driver characteristics (the core of it)

| F1 25 field | Signal | Why |
|---|---|---|
| `driver_characteristics.aggression` | Aggression | Overtake willingness; no risk input |
| `driver_characteristics.control` | 0.70 Consistency + 0.30 (1 - Risk) | Throttle and brake confidence, exit errors |
| `driver_characteristics.mistakes` | 0.60 (1 - Risk) + 0.40 Consistency | A **skill**, higher = fewer mistakes (F-37): a higher row value gives smaller bad-start draws. Risk = mistake proneness |
| `driver_characteristics.reaction_speed` | 0.60 Aggression + 0.40 Pace | Launch reaction (F-36); Verve has no reaction axis |
| `driver_characteristics.speed_in` | Pace | Braking distance; no risk input |
| `driver_characteristics.speed_out` | 0.80 Pace + 0.20 Consistency | Corner curvature and exit |

The PR table and `verve-f1-addon/table.csv` give each driver's stock and Verve values plus the F-39 start-model
predictions (mean reaction 0.35 - 0.21 k rs, mean bad-start draw 0.24 - 0.08 k m, k = 0.52).

### Pace rating (so simulated sessions and the career UI agree)

Simulated and skipped sessions use baked lap times plus the **ratings**, not the physics, so the `pace` rating
follows Verve Pace. Verve Pace sets the order and the grid's stock season-0 pace ratings
(`docs/stock/pace_curves_grid.csv`) are handed out in that order, ties sharing the mean, so the grid keeps its stock
spread. Each driver's stock `evolution` curve is then shifted by (target - its season-0 value), keeping its shape
and so its season progression (#21), in both the `default` and `2026` datasets. A linear map would squash the field:
Verve puts two drivers at 0.96 to 1.00 and most at 0.62 to 0.71.

### Strategy

Left stock. Verve has no strategy axis, and risk is not a strategy input (#6).
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

## Mistakes direction (settled)

`mistakes` is a skill (higher = fewer mistakes): the stock rows already read that way (Alonso 0.90 > Verstappen
0.75 > Bearman 0.65), and in benchmark a higher row value gives a smaller bad-start draw (F-37; B-0004, replicated
as a dose-response in B-0009). The v0.1 `--mistakes-is-skill` flag is gone: v0.2 always writes the skill.
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

- `verve_to_swofty.py`: the generator. `powershell -File tools/fetch_verve.ps1`, then
  `python3 verve_to_swofty.py --print-table`.
- `data/crosswalk_f1.csv`: Verve key -> real name, F1 25 row label, statistics-holder label, grid.
- `docs/stock/driver_characteristics_grid.csv`, `docs/stock/pace_curves_grid.csv`: the stock anchors.
- `verve-f1-addon/`: the generated addon (`swofty.json` + `db/verve.json`) and `table.csv`. Zip the folder and drag
  it onto the launcher's Addons page.