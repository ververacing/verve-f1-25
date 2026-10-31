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

## Side effect seen

The first `swofty test run` on this PC created profile `test-<run>` and could not delete it afterwards: "is the
only profile". Before the run, `swofty profile list` showed `default (active)`, but no profile file existed, so
`default` seems to have been an implicit placeholder. The test profile is now the active one and lists the same two
addons (swofty.core, teamsimplified.mods). Later runs should delete their own profile since another one now exists.
