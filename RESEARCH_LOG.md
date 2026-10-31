# Research log

Dated trail of what was looked at, where, and what came out. Newest at the bottom. Keep appending.

## 2026-10-30 — session 1 (Claude, for Tyler / TC Verve)

### Goal
Decide whether a Verve-style driver-personality layer is possible on F1 25 via Swofty Launcher, and map the known AI complaints to levers.

### Sources consulted
- Swofty docs: f1.swofty.net (home, `/reference/game/`, `/reference/addons/native-plugins.html`, `/std/systems/ai.html`, `/std/systems/drivers.html`, `/reference/ops/database.html`, `/reference/addons/manifest.html`, `/reference/std/logging.html`, `/reference/std/telemetry.html`, `/reference/cli.html`).
- Swofty repo clone at commit `0a071a43397c34378281b247cc10f4ffdfc90101`: `re/db/subsystems/{ai,car,session,game}.md`, `re/db/functions.tsv` (4,138 rows), `re/db/globals.tsv`, `re/db/db_keys.tsv`, `tools/gamedb/catalog/{tables.tsv,keys.tsv.gz,exe_names.tsv}`, `tools/gamedb/meanings.tsv`, `packages/core/src/activation/{row_keys.txt.gz,dbx.rs}`, `packages/sdk/include/swofty/systems/ai.hpp`, `addons/classicseasons/*/db/*.json`, `addons/*` listing, `native/src/gamelog/log_channels.tsv`, `docs/reference/gamedb/{schema,catalogue}.md`, `docs/design/std-2/coverage.md`.
- OverTake.gg listings (search snippets only; the addon pages block fetches): Swofty Launcher 1.5.0 (19,809 downloads of 1.5.0 as of ~Oct 29), Collision & AI Tweaks 0.3.0, More Aggressive AI Track Pack 1.3.2, SC Ending 1.0.2, Supercars, Paul Ricard, Classic Career Mod.
- EA forums for the complaint list (AI straight-line speed, wet pace, 110 too slow, overprogrammed, overtakes under yellow, ghosting), EA community-raised-issues thread.

### What was established (see findings.json F-01..F-19)
1. Per-driver characteristics exist, are 0..1, derived from ratings via curves, and can be overridden per driver row (F-01, F-02).
2. 84 per-driver `ai_driver_config` keys exist and are stock-identical (F-04). Catalogued with A/B/C ratings.
3. Corner-exit error (F-05), race-start reaction (F-06), overtake overlap (F-07) and ERS push logic (F-08) are decoded and give measurable levers.
4. The difficulty slider is per-track data (F-09); above 100 the AI loses mass. Hypothesis for the straight-line complaint.
5. `set` ops resolve by hash (F-11), so no `fields` block is needed for the per-driver keys.
6. The 1.6 AI registry API is design-only (F-13); use database ops.
7. Game log channels give free verification (F-14).
8. Cutscene skip and garage push-in skip are both native-plugin work, with the hook names listed (F-16).

### What was built
- `verve_to_swofty.py` generator, `verve_grid_2025.csv` sample, `verve-f1-addon/` (232 ops, 23 drivers), statically validated against the key catalogue, driver labels and stock ranges.
- `tools/build_catalogue.py` → `docs/ai_driver_config_keys.{csv,md}` (84 keys).
- `docs/ai_vehicle_config_keys.csv` (218 of the 221 per-car keys from the RE vocabulary; see corrections below).
- `HANDOFF.md`, `findings.json`, this log.

### Corrections made during the session
- First draft of the catalogue said a `set` needs the `fields` block; `dbx.rs` shows it resolves by hash. Corrected.
- The per-car `ai_vehicle_config` vocabulary in `ai.md` is headed "221 keys" and its 30 group counts sum to 221, but the `drafting` group (header 20) enumerates only 17 leaves, so the CSV carries 218. The three missing drafting leaves are unknown; `swofty db get` on one vehicle's `ai_vehicle_config.drafting` will list them.

### Not done / open
- Nothing run against a game install. All in-game questions are listed as Q-01..Q-12 in HANDOFF.md.
- Stock values of the six characteristics and the 84 keys not dumped (needs `swofty db get` on a machine with the game).
- The RE note references `work/aiperso/findings_aiperso.md` for the driver-personality decode; that file is not in the public repo. Neither are the `re/decomp/*.c` decompilations that `functions.tsv` cites as evidence (the `re/` tree in the public repo holds the tables, ghidra scripts, tests and traces only). Worth asking on the Swofty Discord (https://discord.swofty.net) for both and for the `ai-re` lane owner.

### Verification of this handoff
- All 43 `0x…` addresses cited in `HANDOFF.md`, `findings.json` and the catalogue exist in `re/db/functions.tsv`, `re/db/globals.tsv` or the subsystem notes.
- All cited Swofty repo paths exist except the `re/decomp/*.c` files (see above).
- `findings.json` parses; `docs/ai_driver_config_keys.csv` has exactly the 84 keys of the Classic Seasons fields list; `verve-f1-addon/db/verve.json` revalidated (232 ops).

### Numbers worth remembering
- 197 driver rows, 129 fields each; 43 track rows; 43 vehicle-package rows; 46 packages with difficulty tables; 84 form curves; 30 AI vehicle slots per session (AI table size); 218/221 per-car AI keys in 30 groups; 84 per-driver AI keys in 9 groups; 11 parameter maps.
- Stock ERS gates: 0.7 / 0.6 / 0.47 / 0.25 (0.15, 0.30) / 1.0 (defend).
- Stock reaction bounds: min [0.28, 0.42] s, max [0.04, 0.24] s.
- Parameter-map corners at high difficulty: braking 1.15-1.25x for low speed_in; curvature 0.92x for low speed_out; follow speed 1.05x and alongside space 1.15x for low aggression; exit error 0.75x for high control.

## 2026-10-30 — session 1, part 2 (settings surfaces, My Team difficulty)

### Sources consulted
- `docs/reference/addons/manifest.md` (options, career_setup, hub_tab, hud, screens), `docs/reference/addons/in-game-ui.md` (career setup page, Team HQ tab), `docs/reference/addons/settings.md`, `docs/reference/ops/database.md` (`{{id}}`, `when`), `docs/make/career.md` (data-only career tile), `addons/progressive/swofty.json` and `native/src/rnd_model_logic.hpp` (per-career R&D model via `Career_Rebuild_SeasonStandings` wrap).
- `tools/gamedb/catalog/keys.tsv.gz` for `bank.*`, `career.my_team_*`, `resource_points.*`, `attributes.Attributes_N.*`, `difficulty.settings_N`, regulation schedules, `UpgradeDepartmentEntry_N`, `upgrade_N.cost`; `re/db/subsystems/career.md` (pipeline, tweakables, department entries, resource rates).
- EA forums: "Can we talk about MyTeam now?" (12291949), "R&D is broken" (12248339). Reddit searches through this session's search tool returned no usable r/F1Game threads; the EA threads carry the same complaints.

### Established
- F-20..F-24 in findings.json. HANDOFF §10 (settings surfaces) and §11 (My Team presets, levers, three shipping options). Q-13..Q-16 and issues 17-20 added.

### Decisions recommended
- Ship the My Team preset as a profile-level `db` choice option first (option A). Investigate the wizard step (option C) only after the numbers are validated, because it needs native code and an undocumented attachment to the My Team tile.
- Treat the AI-vs-player ceiling (`target_mass_adjustment_at_max_upgrade`) and AI RP pacing as fairness fixes applied to every preset, not as "difficulty".

## 2026-10-30 — session 1, part 3 (My Team applicability, gaps, harness)

- Confirmed from the RE notes that the per-car AI driver record is built from the driver row at session setup with no mode-specific path (F-25). Found a real v0.1 flaw: the flat pace curve and static overrides remove per-season driver development in careers (F-26, issue 21).
- Designed the autonomous test loop around `swofty run --apply --direct`, a harness plugin (routes + `sessions::set_control` + exit on `session.end`), and the official UDP telemetry (F-27, HANDOFF §13, issue 24). The EA forum UDP spec post (12187347) links the PDFs; packet details were not fetched here, so the Overtake/Collision event claim comes from the F1 23/F1 24 specs and must be checked against the F1 25 PDF.
- Added §12 gaps checklist and §14 other-improvement candidates; issues 21–24.

## 2026-10-30 — session 2 (local dev session on the game PC): stock dump

- Machine: Steam F1 25 build 25251167, exe sha256 matches the RE build; Swofty 1.6.11 (`swofty doctor`: no drift).
  Read-only `swofty db get` only; the game was not launched.
- Dumped driver rows, rating holders, the six override curves, all 84 `ai_driver_config` keys for four rows, the
  2026 dataset census, one `ai_vehicle_config`, the f1_2025 parameter maps and Austria's difficulty table into
  `docs/stock/` (README there summarises). New tools: `tools/dump_stock.ps1`, `tools/dump_ai_driver_config.ps1`.
- Answered: Q-01 (stock rows carry curated characteristics, not -1; F-28), Q-03 static half (`mistakes` is a
  skill; F-29), Q-11 (24 drivers have a `2026` dataset; F-30).
- Corrected: F-02 (stock does set the fields), F-06 (race-start bound labels were swapped), catalogue types (15
  "float" keys are curves; F-31). Found label mismatches that would break the v0.1 build (Antonelli row, Albon
  stats; F-32). Pinned `compat.game_builds` to `25251167`.
- Side note: the Microsoft Store-style Python on this PC cannot see files under `AppData\Roaming` (MSIX
  redirection), so scripts that touch the repo must run with the repo outside that folder.
