# Skip Cutscenes

| | |
|---|---|
| Id | `dromodf.skip-cutscenes` |
| Version | 1.9.4 (catalog latest, installed `swofty.json`, `#define VERSION` in `skip_cutscenes.c` line 69). Earlier in the catalog: 1.9.3. |
| Author | Dromodf |
| Licence | MIT (installed `swofty.json`; SPDX header, `skip_cutscenes.c` line 1). The catalog has no licence field. |
| Source | Shipped with the addon: `src/skip_cutscenes.c`, `src/swofty_api.h`, `build.sh`. No public repo linked (catalog `homepage` and `repository` are null). |
| Game build | F1 25 Steam build `d873a1c8d2044cef` / 25251167 (`skip_cutscenes.c` line 16; README "Experimental"). The manifest has no `game_builds`. Five states use fixed vtable offsets of this build and are skipped on any other build (README; source lines 1300-1373). |
| Launcher | `>=1.7.15` (manifest and catalog). README: read with Swofty Launcher 1.8.10. |
| Requires | `swofty.core >=0.1.0` (manifest and catalog) |
| Kind | native (one DLL, `native/skip_cutscenes.dll`, built from the shipped source by `build.sh`). Manifest `experimental_features: ["overlay"]` for the skip prompt. |

Sources read: catalog entry (2026-11-14; its `description` is empty, only the summary); installed `%LOCALAPPDATA%\Swofty\addons\dromodf.skip-cutscenes\` `swofty.json`, `README.md`, `build.sh`, `src/skip_cutscenes.c` (read in part: header, option, state hooks, mixin table, load). `swofty_api.h` was not read in full.

## What it changes

It ends cutscenes early, or never plays them. It does not change any AI, physics or race data.

- **Skip with the accept button:** while a cutscene state runs, pressing the game's "Menu Accept" button skips it. A Skip prompt shows in the bottom-right corner. A button already held when the cutscene starts does not count.
- **Remove automatically:** each cutscene state is left on its first frame. Where the game has a "do not play" flag it is set before the state starts, so the cutscene is not loaded.

Covered (README table): track intro cameras, intro video, session videos, in-session cutscenes (garage and similar), the grid scene, the grid rundown, the finish-line celebration, post-race and podium scenes, doughnuts, retirement, and the career hub scenes (contract intro and signing, Driver HQ intro, silly season, end of season, secret meeting outro, season grid reveal, contract offers, car reveal / My Team intro).

Not touched (README): the formation lap, press interviews, anything you play yourself, Braking Point, F1 World.

1.9.4 change: the grid skip runs the grid cutscene to its end and leaves the pre-race strategy menu alone. 1.9.3 set the dev `Game.SkipPreRace` flag, which closed the strategy menu with a strategy already picked (README "Changes"; source lines 1240-1263).

## Settings

| Option id | Label | Values | Default | Applies |
|---|---|---|---|---|
| `mode` | Cutscenes | `skip` (Skip with the accept button), `remove` (Remove automatically) | `skip` | live; read fresh each time a cutscene starts (source lines 87-103) |

## Native hooks and states

Provenance: **S:n** = `src/skip_cutscenes.c` line n. "Accept" = holds Menu Accept down for the duration of that state's update only (`Ne_Input_IsActionDownAnyDevice` wrap, S:170-210, S:1514).

| Binding / state | Skip mode | Remove mode | Provenance |
|---|---|---|---|
| `Ne_Input_IsActionDownAnyDevice` (wrapped) | answers 1 for Menu Accept only while a handled state updates | same | S:165-210, 1514 |
| `Sess_SessionStateIntroCameras_OnEnter` + its update (vtable via enter) | sets skip flag +0xdd1 on press | sets +0xdd1 on enter | S:1150-1167, 1475, 1515 |
| `Sess_IntroVideo_OnStateEnter` (update via vtable) | Accept | Accept at once | S:1169-1177, 1477 |
| `vt_Sess_Video` slot 9 | Accept | Accept at once | S:1179-1187, 1516 |
| `Sess_PlayCutScene_OnStateEnter`, `vt_Sess_PlayCutScene` slots 9, 10 | sets skippable +0xea0 once playing, Accept; restored on exit | sets no-cutscene +0xe8b before enter; restored on exit | S:1189-1235, 1517-1519 |
| `Sess_PreRace_Update` (grid scene) | runs the grid script to its end (vt+0x208) | same, at once | S:1240-1263, 1520 |
| `Sess_GridRundown_Update` | routes link `next` | routes `next` at once, unless a restart is pending (+0xcc9 bit 1) | S:1266-1276, 1521 |
| `Sess_WinnerSequence_Update` | sets timer +0xdb0 to -1 (the game's 40 s timeout path) once +0xe76 is set | same, at once | S:1279-1288, 1522 |
| `Sess_RetirementSequence_Update` | Accept | Accept at once | S:1291-1298, 1523 |
| `vt_Sess_DriverCareerContractNegotiationsIntro`, `...Outro`, `vt_Sess_DriverHQIntro`, `vt_Sess_EndOfSeasonCutscene`, `vt_Sess_SillySeasonCutscene`, `vt_Sess_SecretMeetingOutro` (slot 9) | skippable flag + Accept | done flag | S:1395-1411, 1524-1529 |
| `vt_Sess_CutsceneLocation` slot 9 (season grid reveal) | sets done +0xdc0 right after a grid-reveal skip | same | S:1130-1146, 1530 |
| Post-race cutscene (podium), session cutscene, zoom to monitor, mid-session save, doughnuts: vtables at fixed RVAs 0x57e5340, 0x57e4e60, 0x57e43d0, 0x57e51a0, 0x57de790, used only if they match this build | sets the done dword (or routes `next`) | same, at once | S:1300-1373 |
| CutsceneManager scripts (frame tick) | posts the game's `listen_for_user_interruption_message` skip; stops the script directly only if still playing 2.5 s later | same, at once | README "How it works"; S:281-460 |

Other bindings resolved at load: `Ne_Input_InternActionName`, `Ne_Post_BusMessage`, `g_Game_MessageBus`, `g_Career_FlowLinkContinue`, `Ne_InputMapper_FindBindingByHash`, `g_Game_Manager` (S:1472-1505).

No game-database keys, no `ai_*` config keys, no `.aispline` files.

## Protected keys

None. It touches no `cede_position.*`, `yellow_flag_*` or `flying_lap_yield_*` key.

## Stacks and conflicts

Not stated. No `registry.json` in the installed copy. Any other addon that wraps the same session-state updates (for example a grid-rundown or podium skipper) could clash; none is named.

## What the authors admit

- README "Experimental": read from F1_25.exe build d873a1c8d2044cef, "not yet tested in game".
- During the F1 logo transition that opens a career hub cutscene, the prompt and button do nothing.
- A cutscene that holds on its last frame is left to the game.

## Notes for our use

- In Remove mode the grid rundown is passed at once (S:1266-1276), and the grid scene is run to its end. The pre-race menu after it still opens (1.9.4 change).
- Each handled cutscene logs `[skip-cutscenes] <name>: skipped (button pressed)` or `<name>: removing` in `<F1 25>/swofty/loader.log` (README).

## Not determined

- Source comments are partly out of date. The header (lines 5-13, 28) still describes "any button" and the `Game.SkipPreRace` grid path. The 1.9.4 code and README use the accept button and run the grid script to its end.
- Whether the shipped DLL was built from this exact source. No hash or build record ties them together.
