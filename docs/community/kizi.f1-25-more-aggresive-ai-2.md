# F1 25 + 26 Aggressive AI (Alternate)

| | |
|---|---|
| Id | `kizi.f1-25-more-aggresive-ai-2` (catalog spelling, "aggresive") |
| Version | 2.0.1 (catalog latest; the downloaded package's `swofty.json` and `READ_ME_FIRST.txt` agree). Earlier: 1.0.1. **Not installed on this PC.** |
| Author | Kizi |
| Licence | Not stated (no licence field in the catalog or the package manifest, no licence file in the package) |
| Source | None linked. Catalog `homepage` and `repository` are null. `READ_ME_FIRST.txt`: "A Track Pack exported from F1 Track Editor". |
| Game build | Not stated. Manifest `compat.game` is `f1_25`; no `game_builds`. |
| Launcher | `>=1.5.3` (manifest and catalog) |
| Requires | Nothing (catalog `requires: []`, no `requires` in the manifest) |
| Kind | `erp` (data only, `native: false`) |
| Settings | None |

Sources read: catalog entry (2026-11-14); the 2.0.1 package downloaded from the catalog URL into the scratch area (1,706,708 bytes, sha256 `a7e90338...caca2`, matches the catalog). Read as text: `swofty.json`, `ops/tracks.json`, `README.md`, `READ_ME_FIRST.txt`. The track files were listed, not decoded. Nothing was run.

## What it changes

It replaces the AI racing line and the track markup on 28 layouts. The catalog says AI drivers commit to overtakes and defend more, with "less extreme lines than the main version". It contains "no game files and no code".

`ops/tracks.json` has 84 `replace-resource` ops, 3 per track, all inside `2025_asset_groups/environment_package/tracks/<track>/wep/<track>_common.erp`:

| Resource replaced | Fragment | Source file in the package |
|---|---|---|
| `eaid://environment_package/tracks/<track>/ai/<track>_ai_track.aispline` | 0 | `tracks/<track>/<track>_ai_track.aispline` (about 265-458 KB) |
| same `.aispline` resource | 1 | `tracks/<track>/<track>_ai_track.tsmd` (120 bytes each) |
| `eaid://environment_package/tracks/<track>/track_space_data/<track>_common.trackmarkup` | 0 | `tracks/<track>/<track>_common.trackmarkup` (about 60-156 KB) |

Tracks (28): abu_dhabi, austria, austria_reverse, bahrain, baku, brazil, catalunya, hungaroring, imola, jeddah, las_vegas, losail, madrid, melbourne, mexico, miami, monaco, montreal, monza, shanghai, silverstone, silverstone_reverse, singapore, spa_francorchamps, suzuka, texas, zandvoort, zandvoort_reverse (`READ_ME_FIRST.txt`, `ops/tracks.json`).

2.0.1 changelog: "Some adjustments to the street circuit track" (catalog).

## Keys it touches

| Target | Stock | Addon | Provenance |
|---|---|---|---|
| `.aispline` per track (28) | the game's spline | replaced whole | `ops/tracks.json` |
| `.aispline` fragment 1 (`.tsmd`) per track (28) | the game's | replaced whole | `ops/tracks.json` |
| `.trackmarkup` per track (28) | the game's markup | replaced whole | `ops/tracks.json` |

No game-database keys, no `ai_*` config keys, no native hooks.

Per-point values are not determinable from text. The `.aispline` and `.trackmarkup` files are binary XML (`BXML` header); the `.tsmd` files start with `TSMD`. Readable element names in the Austria markup include `MarkupElement`, `Sector1_CarBehind` and values such as `Limited`, `Partial`, `Full` and `Disable`, but which zones changed against stock was not compared. The catalog says the lines are "gentler" than the main pack. It does not say which spline or markup values changed.

## Protected keys

None of `cede_position.*`, `yellow_flag_*` or `flying_lap_yield_*` (it has no database ops). Whether the track markup changes yellow-flag or yield behaviour through track zones is not stated and was not checked.

## Stacks and conflicts

- "Do not enable together with the original More Aggressive AI track pack; both edit the same tracks" (catalog, README). The original pack is not in the public catalog today.
- Any other addon that replaces the same `.aispline` or `.trackmarkup` resources would clash. None is named.
- Interaction with the database AI addons (Lap 1 Realistic AI, AI Driver Behaviour): not stated.

## What the authors admit

- The catalog hedges: "HOPEFULLY THIS IS BETTER LOL", and it only hopes the field stays aggressive without constant crashes.
- No measurements are given.
- READ_ME_FIRST: if something looks wrong, verify the game files or run `swofty restore`.

## Not determined

- Licence.
- What changed in each spline and markup file against stock.
- Whether the track files were made for build 25251167 or another build.
