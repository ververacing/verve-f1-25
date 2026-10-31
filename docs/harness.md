# Test harness: `swofty test`

How Verve runs unattended races on PC1, what Swofty's built-in harness covers, and the gaps left for issue #24
(re-scoped). Swofty 1.6.11, F1 25 build 25251167. Sources: `docs/std/testing.md`,
`docs/design/std-2/test-suite.md` and `docs/reference/std/telemetry.md` in the Swofty repo, plus the smoke runs in
`runs/2026-10-30-smoke/` (issue #3).

## Running a test

```powershell
$env:SWOFTY_GAME_LOG_CHANNELS = "default,RaceStarts:info,AI_VARIATION:info,CANNED_EVENTS:info"
& "$env:LOCALAPPDATA\Programs\SwoftyLauncher\bin\swofty.exe" test run harness\tests\smoke.test.json --out runs\<date>-<id>\raw\report --wait 0
```

`swofty test run` takes the machine's game lock, builds a throwaway launcher profile with only the addons the test
names, stages the environment, launches F1 25 modded and offline, runs the steps, checks the asserts, writes
`report.json`, `junit.xml`, `summary.txt` and per-batch `loader.log` / `launcher.log` / `perf.log`, closes the game
and puts the game folder back. Exit code 0 = all passed, 1 = a test failed, 2 = the game could not start or the
run hit an error, 3 = the game was busy past `--wait`. Tests that share an environment share one game start.
Verve's test files live in `harness/tests/`.

## The `benchmark` environment (what Verve races use)

The game's own `-benchmark <xml>` mode: about 25 s from launch to an all-AI race, no menus. Keys: `track`, `laps`,
`cars`, `weather` (`clear`, `wet`, `rain`), `grid_pos`, `box`, `camera`, `driver`. The AI drives every car,
including the player's.

What the smoke run showed (Austria, 3 laps, 20 cars, clear):

- Session loads as `StateLoadSession (benchmark)` with the **f1_2025 entrant list, 20 cars, setup mode f1**.
- It is a **standing start with no formation lap**: 8.5 s after the session loads, `RaceStarts` logs a
  `Reaction Time` and a `Race Start performance` line for every car (vehicle ids 0-19). Reaction times ranged
  0.109-0.332 s, which fits the F-06 formula's range.
- 3 laps took ~4 min 20 s; `StateSession Exiting (benchmark)` marks the end, then the game exits with code 0.
  Launch to exit: ~5 min. So roughly **10 starts per hour** with 3-lap races, or more if a test quits right after
  the start lines.
- **Swofty's `race.start` event does not fire in benchmark** (it is hooked on the championship formation-lap
  component). Wait on log lines instead: `RaceStarts: Reaction Time for driver with vehicle id` for the start and
  `session trace StateSession Exiting \(benchmark\)` for the end.
- The grid looks fixed: the entrant trace lists the same team order on every load (`teams 2,3,8,4,3,2,9,0,1,4,7,6,8,9,6,7,5,5,0,1`).
- Difficulty, formation lap and start mode are not benchmark keys; whatever the benchmark uses is fixed.

## The questions from #3

| Question | Answer |
|---|---|
| Route to a Grand Prix with fixed track / weather / difficulty / grid? | **Partly.** `grand_prix` is planned, not runnable. `benchmark` gives a fixed track, weather, car count and (apparently) grid, but no difficulty or start-mode control. |
| Hand the player car to the AI? | **Yes.** Automatic in `benchmark`; `ai_drives_player` elsewhere. |
| Quit on session end? | **Yes.** The benchmark exits by itself after the race (code 0); the CLI also closes the game when the test ends or times out. |
| Roll back? | **Yes.** After each run `swofty doctor` reports `drift: swofty is not part of the game`. |
| Capture loader.log? | **Yes.** Per batch, with the game's own log channels when `SWOFTY_GAME_LOG_CHANNELS` is set. |
| Capture UDP? | **No.** Nothing in the harness records UDP; Swofty's shared-memory telemetry feed exists but its car and participant fields are "not populated yet". That is #4. |
| Driver Career race (B-0002)? | **Not directly.** The `career` environment reaches Team HQ from a fixture; `weekend_hub` / `session` and `advance` don't work yet. |

## Gaps (re-scoped #24)

1. **Vehicle id -> driver.** RaceStarts names cars by vehicle id only, and the session trace gives just each
   car's team. Teammates can't be told apart. Options: the game's UDP Participants packet (needs the in-game UDP
   telemetry setting on; #4), or arms that give both drivers of a team the same value.
2. **Grand Prix sessions** with chosen difficulty and start rules: Swofty's `grand_prix` env when it ships, or
   `route` + `pad` steps.
3. **Career race sessions** (B-0002): a fixture saved inside a race weekend, then `pad` to the race.
4. **UDP logger** (#4).

## Reading benchmark results (review findings on #32)

1. **The player car.** Vehicle 19 was the fastest starter in both smoke runs (0.109 / 0.095 s) while every other
   car moved around. It is probably the player car (AI-driven in benchmark), which may take a different start path.
   Until B-0003 (#33) settles which vehicle is the player, leave the player's car and team out of every arm and
   every field statistic.
2. **Mode caveat.** Benchmark is its own session mode. Anything learned there about row vs rating precedence
   (Q-17) or start behaviour holds *for benchmark*; Grand Prix and career need gaps 2 and 3 before they count.
3. **Vehicle id = trace entry.** Reading RaceStarts by team assumes vehicle id *i* is entry *i* of the session
   trace's `teams …` list. Per-team arms test it, since both cars of a modified team should move together.
4. **Race Start performance** (65-93 in the smoke runs) has no known scale. Log it, but don't use it as a metric
   until #8.
5. **Per-session level.** The whole field's reaction times shift from start to start (F-06's per-session k), so
   compare arms against the stock field of the *same* start, not across starts.

## Game-database edits per run, and experiment isolation (#34 review)

Each start's `loader.log` has one line `[assets] gamedb: N overwritten, M created, 0 retyped, 0 skipped`.

- **Baseline, every run: 52 overwritten, 322 created.** That is swofty.core plus the always-on
  `teamsimplified.mods` (it can't be disabled per profile), with no Verve addon. Resolving each edit's hash with
  `swofty db get 0x<hash>` (v0.1 smoke overlay) shows what they are: core's `swofty_f1` box. 322 add-row records
  (an `entrant_setup_mode` and a `game_setup_mode` copy) plus 52 overwrites of game modes, content sets, setup-mode
  lists, track data, tyre classes, videos, the schedule, and one driver-side list
  (`entrants.drivers.seasonal_infos.seasonal_info_0.game_setup_modes`: `f1` → `f1,swofty_f1`). **None touch
  `driver_characteristics`, `driver_strategy`, `driver_statistics` or any `ai_*` key.**
- **v0.1 sample addon: 280 overwritten = 52 + 228.** Its 232 ops became 228 edits because the build drops ops whose
  value already equals stock: Piastri control 0.9, Hulkenberg control 0.84, Bortoleto reaction_speed 0.7,
  Gasly safety_car_pit_wear_max 0.35. All 229 driver-row and statistics edits (incl. the one seasonal list) are
  accounted for.
- **But an equal write is not always dropped.** B-0010 (#51): 68 overwritten = 52 + all 16 ops, and `loader.log`
  logs Sainz `reaction_speed 0.9 -> 0.9` as an overwrite. Which equal writes the build drops is unknown, so don't
  predict the count from stock values: before trusting a batch, check start 1's `gamedb: overwrote` lines against
  the addon's ops (one per op, plus the baseline), then run the analysis with that count.
- **Isolation rule.** An experiment profile holds only swofty.core (+ the always-on teamsimplified.mods) plus that
  batch's own test addon. The sample `verve.driver-profiles` is uninstalled. `tools/racestarts_summary.ps1
  -ExpectOverwritten <52 + the batch's edit count>` fails the analysis if any start applied a different number of
  edits. Don't trust the settings line's "N addon(s)": it counts installed addons, enabled or not, and the
  offline-play hook (`swofty\mods\core\f1op_hook.dll`, "left idle") is loaded in every modded run.

## UDP telemetry

On since 2026-10-30, with Tyler's approval: `Documents\My Games\F1 25\hardwaresettings\hardware_settings_config.xml`
`<udp enabled="true" broadcast="false" ip="127.0.0.1" port="20777" sendRate="20" format="2026"
yourTelemetry="restricted" onlineNames="off" />`. Only `enabled` changed; the original is saved next to it as
`hardware_settings_config.pre-udp.xml`. Record with `tools/udp_capture.py` (raw packets with wall-clock times) and
read the Participants packet with `tools/udp_participants.py`.

**Benchmark runs send no UDP.** During B-0003's 5 starts the capture received 0 packets, with the setting on and kept
by the game. Either benchmark mode or the offline launch doesn't emit telemetry. A normal session (Time Trial by pad,
`docs/std/testing.md`) is the next place to check (#4).

## PC hygiene after every run

- `swofty doctor` must show `drift: swofty is not part of the game`, so launching from Steam gives the stock game.
- The launcher must open on Tyler's own profile. `swofty test` creates `test-<run>` profiles and can't delete them
  here (`cache\overlay\<name>`: "being used by another process", although a plain Remove-Item of that folder works).
  Run `tools/cleanup_test_profiles.ps1` after every batch: it clears each leftover's cache, then deletes the profile.
  Before the first run on this PC the only profile was an implicit `default` with no file, which the first test
  profile replaced as the active one; there is no CLI command to pick the active profile, so that is done in the
  launcher.
- Reinstalling an addon over an existing install fails here ("files still in use") and half-deletes it.
  `tools/reinstall_addon.ps1 -Folder <addon>` clears the old copy and staging folder first;
  `-Id <id> -Uninstall` removes one (and drops it from every profile file when `swofty addons remove` hits the lock).
- Close the Swofty Launcher window when it isn't needed (Tyler's OK, 2026-10-30).
- **After aborting a run** (PAUSE, killed task), also check `%LOCALAPPDATA%\swofty-game.lock.d`. A killed
  `swofty test` leaves it behind (its `owner` file names the dead run), and the next run then fails at once with "the
  game was not free". There is no CLI command to clear it. If no `F1_25` or `swofty` process is running, delete the
  folder. Seen 2026-10-30 after the B-0004 pause. `tools/cleanup_test_profiles.ps1` now does this (only when no such
  process is running), so the PAUSE checklist and every post-run cleanup cover it.
- **Pre-flight** (after RESUME or after Tyler has played): `tools/preflight.ps1`. It checks that the build is still
  25251167 and that doctor shows no drift. It also runs the cleanup above, and lists any `hardware_settings_config.xml`
  lines that differ from the pre-UDP backup besides `<udp>`.

## Saves (benchmark leaves them alone)

Tyler's F1 25 saves live in `C:\Program Files (x86)\Steam\userdata\928649988\3059520\remote` (10 files, Steam Cloud
synced). Hashed with SHA-256 during B-0010 (2026-10-31 02:43) and again after its 20 starts (04:20): all 10 identical,
newest file still 2026-10-30 22:37 (`runs/2026-10-31-B-0010/summary.md`). So benchmark tests don't read or write
saves. Route tests (Time Trial, Grand Prix by route and pad) do run on these saves and stay on hold until Tyler decides
how to protect them.

## Side effect seen

The first `swofty test run` on this PC created profile `test-<run>` and could not delete it afterwards: "is the
only profile". Before the run, `swofty profile list` showed `default (active)`, but no profile file existed, so
`default` seems to have been an implicit placeholder. The test profile is now the active one and lists the same two
addons (swofty.core, teamsimplified.mods). Later runs should delete their own profile since another one now exists.
