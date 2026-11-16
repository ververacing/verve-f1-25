# Verve Drivers: per-season build (design note, draft)

From `verve_to_swofty.py` v0.2 (one grid, pace curves written) to a per-season data add-on: **Verve Drivers**, real-driver
personalities by season, written as per-driver character values only. It works on its own or next to community add-ons.

Sources: repo `verve_to_swofty.py`, `README.md`, `HANDOFF.md` §9 and #22, `docs/stock/README.md`, `data/crosswalk_f1.csv`,
`verve-f1-addon/`, `findings.json` (F-20, F-25, F-26, F-30, F-36, F-37, F-39), `docs/community/*.md`. Swofty public repo
at `main` 0ded78c (2026-11-16), paths cited inline.

---

## 1. Scope and constraints

- **Owns only** `entrants.drivers.driver[_metadata_=<row_label>].driver_characteristics.{aggression, control, mistakes,
  reaction_speed, speed_in, speed_out}`, and only on rows listed in the season CSV.
- **Writes no** per-car keys (`ai_vehicle_config`, packages, tracks), no global keys (`driver_characteristic_overrides`
  curves, `ai.driver_variation`), no `ai_driver_config.*`, no `driver_strategy.*`, no `preferred_tracks`.
- **Writes no pace ratings.** The v0.2 `StatisticsDataSet[...].Statistic[pace].evolution` ops are dropped. Database ops
  can't be limited to some game modes (a `when` only reads option values and addon presence, see §4), so dropping them is
  the only way to keep them out of careers. Ratings come back later through a native read-time path
  (`driver.ratings.read`, applied as a floor `max(value, floor)` per career data group, `docs/community/source_insights.md` §D).
  Until then, simulated sessions follow the stock ratings. The live AI still gets Verve pace through `speed_in` and
  `speed_out`.
- The basis: in benchmark the row value is what the AI reads (F-36 reaction_speed, F-37 mistakes). `mistakes` is a
  skill: higher means fewer mistakes (F-37, F-29; the Swofty DB Editor labels it "Mistake avoidance",
  `packages/core/src/dbedit/modules.json`). Both results were measured on build 25251167, in benchmark only, and haven't
  been re-checked on 26566308.

## 2. Input: per-season CSV

One file, `data/verve_seasons.csv`, keyed on **(season, row_label)**. Labels reuse the crosswalk columns: `row_label` is
the crosswalk's `f1_25_label` and `stats_label` is its `stats_label`. The two differ for Albon (`alex_albon` vs holder
`alexander_albon`, F-32).

| Column | Type / units | Notes |
|---|---|---|
| `season` | `2025` \| `2026` | Key. One row per driver per season grid |
| `row_label` | driver-row `_metadata_` | Key. The only selector the build writes |
| `stats_label` | statistics-holder label | Carried for the later ratings path. **Not written** |
| `verve_key` | Verve id, or `-` | `-` = no Verve profile, so no ops for that row (today: Doohan) |
| `real_name` | text | Display only (table.csv) |
| `verve_pace`, `verve_aggression`, `verve_risk`, `verve_consistency` | 0..1, unitless; 0.5 = mean of Verve's F1 bucket | Traits. From pinned `drivers.lua` (VERVE_COMMIT/VERVE_BLOB), or a season snapshot |
| `target_aggression` ... `target_speed_out` (6) | 0..1 | Optional explicit Verve value at strength 100. Blank = derive with the v0.2 mapping |
| `pace_floor` | 0..100 rating points, optional | For the later native ratings floor. **Not written** by this build |
| `source` | text | Provenance, e.g. `drivers.lua@80d1798`, or a 2026 snapshot id |

- Stock anchor: `docs/stock/26566308/driver_characteristics_grid.csv`. It's a single set for both seasons, because a
  season doesn't get its own driver row (§5).
- Derived target (v0.2, unchanged): `target = clamp(stock + K*(signal - center))` with K = 0.5, the `MAPPING` weights, and
  `center` = the signal's mean over **that season's** written rows (so a grid-average driver keeps their stock value).
- Today's grids, from the crosswalk: 2025 has 20 profiled rows plus Doohan stock. 2026 has 22 profiled rows (Perez,
  Bottas and Lindblad join, Tsunoda and Doohan drop).

## 3. Options

| id | type | values (default) | binds | effect |
|---|---|---|---|---|
| `on` | toggle | true | db | false = no ops at all, identical to vanilla driver rows (#22 acceptance) |
| `season` | choice | `2025`, `2026` (proposal: `2026`, Tyler to confirm) | db | which season's rows are written |
| `strength` | choice | `25`, `50`, `75`, `100` (`100`) | db | `v = stock + s*(target - stock)`, s = strength/100 |
| `mistakes` | choice | `off`, `realistic`, `more` (`realistic`) | db | see below |

- Strength is a convex blend, so v stays inside 0..1 with no clamp. At s = 1 it reproduces v0.2 exactly.
- Mistakes:
  - **Off**: no `mistakes` op, so stock stays.
  - **Realistic**: `m = stock + s*(target_m - stock)`, like the other five fields.
  - **More** (proposal): `m_more = clamp(m_realistic - 0.20, 0, 1)`. That's a fixed 0.20 step down the skill scale,
    applied after strength. It keeps the driver order (stock grid minimum is 0.65, so nothing reaches 0) and stays
    within 0..1.
- Size of "More": under the F-39 contrast slope (k = 0.8) it raises the expected bad-start draw by about
  0.08 × 0.8 × 0.20 ≈ 0.013. The grid sd of the predicted draw is 0.007, so the step is clearly visible but not extreme.
  Re-tune once behavioural mistake metrics exist (#4).
- Worked example, Verstappen mistakes (stock 0.75, target 0.7989): at s = 50, Realistic gives about 0.774 and More about
  0.574.

## 4. How the options are implemented (data add-on, no native part)

What Swofty supports for `binds: "db"` (`docs/reference/ops/database.md` "Settings", `docs/reference/addons/settings.md`,
`docs/reference/addons/manifest.md` "options"; code in `packages/core/src/settings.rs` `render_ops` / `substitute`):

- `{{id}}` is **plain text substitution**. `substitute()` pastes in the option's value string, with no arithmetic or
  expressions. So `stock + s*(target-stock)` can't be computed at build time from a placeholder.
- `"when": {"id": value, ...}` keeps an op only when every listed option equals that value (`render_ops` → `holds`:
  `on.value(...) == normalise(want)`). A `when` value that isn't a declared value fails the build. A **top-level `when`
  gates the whole op file** (launcher 1.9.34 or later).
- `binds: "native"` only means the value is read live by an engine DLL (`SWOFTY_SETTING`). It's needed for in-session or
  wizard-step changes, not for gating ops. A `db` change applies after a rebuild and a game restart.
- A precedent ships today: `kizi.ai-driver-behaviour` has 17,131 pre-built `set` ops, each gated by a `db` choice. Its
  DLL only logs a line (`docs/community/kizi.ai-driver-behaviour.md`). Custom Grid Size gates on a number:
  `"when": {"cars": 26}` (settings.md).

**Design: pre-built variants, one op file per (season, strength), gated by a top-level `when`.**

```
db/2025/s25.json ... db/2025/s100.json, db/2026/s25.json ... db/2026/s100.json   (8 files)

{ "schema_version": 1,
  "when": { "on": true, "season": "2025", "strength": "50" },
  "ops": [
    { "op": "set", "select": "entrants.drivers.driver[_metadata_=max_verstappen]",
      "field": "driver_characteristics.aggression", "value": "1" },              // 5 ungated fields per driver
    { "op": "set", "select": "...max_verstappen]", "field": "driver_characteristics.mistakes",
      "value": "0.7745", "when": { "mistakes": "realistic" } },
    { "op": "set", "select": "...max_verstappen]", "field": "driver_characteristics.mistakes",
      "value": "0.5745", "when": { "mistakes": "more" } } ] }
```

- Per file: 7 op entries per driver. 2025 has 140 entries and renders 120 ops (100 with mistakes Off). 2026 has 154
  entries and renders 132 (110). Across all files that's 1,176 entries, and one file survives a build.
- Manifest: `"kind": ["database"]`, `"category": "ai"`, the 4 options above, `operations.database` listing all 8 files,
  `compat.launcher ">=1.9.34"` (because of the top-level `when`; the PC runs 1.9.59), and `compat.game_builds` pinned to
  the dump builds. Use a new id (proposal `verve.drivers`) and keep `verve.driver-profiles` for the research builds.
- If launchers older than 1.9.34 must work, put the `{on, season, strength}` keys on every op instead of the file. It's
  the same result with a bigger file.
- **A native part is not needed for strength or mistakes.** One would be needed only for (a) a continuous slider
  without pre-built steps (a slider is capped at 100 steps; a launcher-plugin build hook can return computed db ops,
  `docs/reference/addons/launcher-api/build-reply.md`, but that's a shipped binary), (b) changes that apply mid-session or
  inside the career wizard, (c) choosing the season automatically from the game mode, or (d) the ratings floor.

## 5. Season handling

- **The driver row is shared across seasons.** `driver_characteristics` sits on `entrants.drivers.driver_N`, and the
  2025 and 2026 grids use the same row labels (crosswalk `grid` = `2025|2026`). Only the statistics holders split, into
  the `default` and `2026` datasets (F-30, Q-11; `2026` is tagged `game_setup_modes f1_26`, `seasons season_2026`). This
  is inferred from the dumps: no season-specific driver rows were found.
- A data build therefore can't hold 2025 and 2026 values at once. The **`season` option picks which season's rows
  apply** for the whole profile, and the player matches it to the season pack they race. A wrong pick still gives sane
  values, just from the other year's Verve snapshot.
- Rows not on the selected season's CSV grid get no ops (stock). So with 2026 selected, Tsunoda and Doohan stay stock.
- No `StatisticsDataSet` ops at all (§1). This also removes v0.2's risk of a `set` on a missing `2026` dataset failing
  the build (HANDOFF Q-11).
- A season snapshot only changes the CSV rows for that season. Stock anchors stay per game build, not per season.

## 6. Compatibility with other add-ons (inferred; the full audit is separate)

- Rule: within one build, a later write to the same field wins, and the build prints `warning: <winner> overrides
  <loser> on N database values` (`docs/reference/data/operations.md` "Order and conflicts"). `swofty conflicts` lists
  the winners.
- Verve Drivers touches only the 6 `driver_characteristics` fields on ≤ 22 stock rows. Overlaps known so far:
  - `kizi.ai-driver-behaviour` writes `ai_driver_config.{alongside, overtake}` on all 197 driver rows. **No overlap** now
    that Verve doesn't own `ai_driver_config`.
  - `swofty.lap1-ai`, `kizi.ai-tweaks`, and the More Aggressive AI spline packs work through live layers, per-car keys
    or track data. No overlap is expected.
  - `msyeett.driver-form` and `alexs.driver-momentum` (native) apply in-memory form and characteristic overrides on top
    of database values (`source_insights.md` §D). They layer over Verve and don't conflict at build. Whether their form
    reads Verve's row as its base is unverified.
  - Silly Season, F2 Revamp and Progressive write statistic curves or add driver rows. Verve doesn't write ratings, so
    the two don't collide. Silly Season renames reserve drivers live, so a renamed row would carry the old label's
    Verve values (key-on-label risk).
  - DB Editor packages and `swofty.career-editor` (live) can edit the same 6 fields. A DB Editor package wins if it loads
    later, and the career editor wins at runtime.
  - `swofty.driver-manager` adds new drivers as new rows, which Verve never selects.
- Manifest stance: no `conflicts` entry, so Verve stacks by default. Don't use `load_after` either. The player's order
  decides, and the build log and the test hook (§7) show who won. A
  `conflicts: [{"id": "*", "touches": "db:entrants.drivers.driver_*.driver_characteristics.*"}]` would warn on every
  overlap. That's worth weighing in the audit, but it may flag DB Editor edits too.

## 7. Test hooks (what the build emits)

- **`table.csv`, long form**, one row per (season, row_label, field): stock, target (s = 100), the value at s =
  25/50/75/100, `mistakes_more` at each strength, `equal_to_stock` per variant, plus the F-39 predictions as in v0.2.
- **`expect/<season>_s<strength>_<mistakes>.csv`**, 24 files: the exact rendered ops for that combination (`select`,
  `field`, `value`, `stock`, `equal_to_stock`). `expect/off.csv` is empty.
- **`expect/summary.csv`**: per combination, the rendered op count, the non-stock count `n`, the sha256 of the sorted
  rendered ops, and **expected `gamedb: N overwritten` = B + n**. B is the profile's baseline with `on = false`, measured
  in the same profile: 52 on the 2026-10 profiles, 56 in the spectator-hud fixture (`tools/aionly_check.py`), so don't
  hard-code it. Count only non-stock ops, because the build drops ops equal to stock
  (`harness/addons/verve.b0011/power/README.txt`).
- **`build_info.json`**: tool version, the CSV's sha256, the stock-anchor file and its sha256, the Verve source per
  season, centers per season, K, the More shift, and the game-build pin.
- **Batch checks**, later, with nothing run now:
  1. Set the combination with `swofty settings set verve.drivers <id> <value>` in the test profile.
  2. Compare loader.log `gamedb: overwrote 0x... OLD -> NEW` lines against the matching `expect/` file. Each op needs a
     matching line, or `equal_to_stock`.
  3. Compare `gamedb: N overwritten` against summary.csv.
  4. Check that the build output has no `overrides Verve Drivers` warning, unless the arm intends one.
  - `tools/check_applied.ps1` reads every `db/*.json` today. It needs an `-Expect <csv>` mode, because only one variant
    file renders.
- **Regression**: 2025, s100, realistic, with the center over the v0.2 driver set must equal v0.2's
  `driver_characteristics` ops line for line. Per-season centers move the values slightly, so pin that in a unit test.

## 8. Open points

- Default `season` (2025 vs 2026), and whether to ship two add-ons instead of a choice.
- Is the row still what the AI reads on 26566308, and in Grand Prix and career, not just benchmark (F-36 and F-37 are
  benchmark-only, on 25251167)?
- Does a career pick up a strength change after a rebuild without starting a new career? F-25 says the AI record is
  built from the row at session setup. Not yet run.
- The More shift of 0.20 is a placeholder until #4 gives behavioural mistake metrics.
