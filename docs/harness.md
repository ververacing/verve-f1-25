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

**Capturing with a test (#4).** `tools/run_with_udp.ps1 -Test <file> -Out runs/<id>` runs the capture next to
`swofty test run` and parses the result with `tools/udp_parse.py` into `runs/<id>/udp/`:
- `sessions.csv`: session type, track, packet counts per id, and any packet whose size doesn't match the F1 25 spec;
- `cars.csv`: participant, grid, final position, laps, best lap, pit stops, overtakes, collisions, penalties, plus
  speed, lap distance and position 1, 3 and 6 s after lights out (the behavioural side of F-38's bad-start draw);
- `laps.csv` and `events.csv`.

Python here (the WindowsApps alias) can't read files under `%APPDATA%` or the rest of `%LOCALAPPDATA%`, only under
`%TEMP%`, so the scripts and the raw recording live in `%TEMP%\verve-udp\<run>\`. `harness/tests/udp_tt.test.json` is the first in-game check: a Time Trial reached
by pad (Swofty's documented sequence) with the AI driving.

**Benchmark runs send no UDP.** During B-0003's 5 starts the capture received 0 packets, with the setting on and kept
by the game. **The offline, modded launch does send UDP:** the first `udp_tt` run (2026-10-31,
`runs/2026-10-31-udp-tt/`) got 21 Event packets (`BUTN`, format 2026) in the menus. So it is benchmark mode that sends
nothing. That run never reached a session: its pad presses on F1 World's Play cards (`solo_container`) came within a
second of the screen opening and did nothing.

**Route tests use the player's own saves.** Only the `career` environment runs in the save sandbox (from a fixture);
a `route` env rejects a `fixture` key. So a Time Trial or Grand Prix reached by `route` + `pad` can write to Tyler's
saves (records, F1 World progress, mid-session saves). Benchmark runs haven't written any. Don't run route tests that
reach a session without Tyler's OK.

`tools/udp_join.py` joins one start's RaceStarts draws to its UDP cars on vehicle id = car index, and checks that both
sides' team ids agree (exit 1 on any mismatch).

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

## Saves

### Route tests: guarded (Tyler's OK, 2026-10-31)

Time Trial and Grand Prix tests by route + pad run on Tyler's own saves (`loader.log`: "no save sandbox ... the game
uses the player's own saves"). Tyler approved them on 2026-10-31 on these terms: back up before each one, compare
after, restore the originals if anything changed. `tools/run_with_udp.ps1` does this with `tools/saves_guard.ps1`:

- Before: copy of `remote\` to `%LOCALAPPDATA%\verve-f1-25\save-backups\<time>-<run>\` (outside the Steam tree,
  never overwritten), copy verified by hash.
- After: `<run>/saves_changes.csv` lists each changed, added or removed file with size and SHA-256 before and after,
  and whether it was restored. Changed or added files are moved to `<backup>\written_by_test\`, the originals copied
  back with their modified time set to now, and the hashes checked again.
- A restore that doesn't come out clean exits 4: stop all route tests and tell Tyler.
- **Master backup:** `save-backups\20261031-070733-master\`, taken before any route test with Tyler's approval;
  identical to the post-B-0010 hashes. Never deleted.
- **Steam Cloud** syncs `remote\` when the game exits, so a test's write can reach the cloud before the restore. The
  fresh modified time makes the restored files the newer local copy. If a later launch shows a cloud-conflict
  dialog, stop and tell Tyler rather than clicking through it.
- **Steam Cloud toggle (Tyler confirmed, 2026-10-31):** "Keep game saves in the Steam Cloud" for F1 25 may be
  switched off for route testing, which closes that hole. The rules:
  - Toggle it only with F1 25 closed.
  - Switch it off before the first guarded route run of a session.
  - Before switching it back on, `saves_guard.ps1 -Action Check` must pass against the master backup or the last
    verified restore, so a bad local save is never what gets synced.
  - Switch it back on whenever route testing stops, and on PAUSE before reporting PAUSED (say so in that message).
  - Log every toggle below with time, on/off and why.
  It's a Steam UI setting (Library > F1 25 > Properties > General), and Steam rewrites its config files while it runs,
  so it needs desktop control or Tyler's hand. Until it's off, runs use the fresh-mtime fallback above.

  Toggle log:
  - 2026-10-31 07:16: not toggled. No desktop control in this session, so I asked Tyler. Cloud was on, and udp-tt-2
    ran with the fallback (saves unchanged).
  - 2026-10-31 ~07:45: **OFF**, set by Tyler by hand for route testing. Game closed; saves matched the master backup
    beforehand. Verified in `userdata\928649988\7\remote\sharedconfig.vdf`: `"3059520" { "cloudenabled" "0" }`.
    Check that key to confirm the state before switching it back on.

### Incident 2026-10-31: "save data corrupted" after a guarded restore (route tests STOPPED)

**Timeline.**
- 07:27-07:30, udp-tt-3: the Time Trial rewrote `savegame@profile#NXDSMWW.BWW` (521128 -> 519688 bytes) and its
  416-byte header. The guard restored Tyler's byte-identical originals at 07:30:52.
- 07:38, udp-tt-4 boot: F1 25 showed a "save data corrupted" dialog and wrote `corrupt_saves#<steamid>.zip` to
  `remote\`. Tyler saw it on screen.
- About 07:41: the test and the game were killed before any pad press could answer the dialog. Then `swofty restore`
  (no drift), lock and test profile cleared. No game launch of any kind since.

**Evidence** (snapshot `save-backups\20261031-074350-post-dialog\`, incl. `remotecache.vdf`; master untouched):
- All 10 save files on disk are hash-identical to the master backup. The only addition is the zip.
- The zip's `savegame@profile#NXDSMWW.BWW` is **519688 bytes, identical to the first 519688 bytes of the restored
  521128-byte original**. Its header equals the original header. So the game read the restored file **truncated to the
  size of its own last write**. `info.xml` lists 3 error codes (CBCB7BC4, 6522DF69, CF228F62).
- 519688 is the size Steam recorded at the game's exit after tt-3. The game reads saves through Steam (the files live
  in Steam's `remote\` folder), and Steam still had that size when tt-4 launched, because the restore happened behind
  its back after it had recorded the write. After the 07:41 exit Steam rescanned: `remotecache.vdf` (07:42) now
  records 521128 bytes and the sha1 of the disk file.
- Nothing outside `remote\` changed between 07:20 and 07:45 except `hardware_settings_config.xml` / `_info.xml`
  (rewritten at every launch; the config differs from the pre-UDP backup only in `<udp enabled>`). `3059520\local\`
  is untouched since 2026-10-03.
- Header diff (master vs the tt-3 write): bytes 0-63 are identical, bytes 64-415 all differ. That looks like a
  digest or encrypted block over the data, not a plain timestamp, so a truncated read fails the check.

**Cause:** restoring save files out of band while Steam's record of them is stale. The fresh-mtime step is not the
cause: Steam's current record matches the disk files' mtimes. The guard checked file contents but not Steam's view
of them.

**Resolved 08:05.** Tyler restarted Steam (08:03) and booted F1 25 from Steam with no Swofty and no test.
- It loaded cleanly: no dialog, his profile and progress as expected (Tyler, in chat).
- The game wrote a fresh profile save (519704 bytes, 08:04:55), and no second corrupt zip appeared.
- `remotecache.vdf` (08:05:06) matches every file in `remote\`: size, sha1, and localtime = mtime.
- Snapshot of this state: `save-backups\20261031-080525-post-fix-boot`.
- `corrupt_saves#<steamid>.zip` is left in `remote\`; deleting it is Tyler's call.
- Never answer the corrupt-save dialog: it may reset the profile.

**Ruling (supervisor, 2026-10-31): route tests stay off Tyler's real saves.** They come back only with a real save
sandbox, so that `run.json` names sandboxed saves: a career fixture in Swofty's sandbox, or a route / `grand_prix`
sandbox if Swofty adds one (Tyler can ask the Swofty Discord). `tools/saves_guard.ps1` stays as a check, but its
Restore is only safe inside the emergency procedure below.

**Emergency restore procedure** (only if a save in `remote\` has to be put back):
1. F1 25 closed. Fully exit Steam (tray > Exit) and confirm no `steam.exe` is running.
2. `saves_guard.ps1 -Action Restore -Backup <backup>`.
3. Start Steam. Before any launch, check `remotecache.vdf` against the disk for every file in `remote\`: size,
   sha1, and localtime = mtime. Log the table.
4. One plain boot from Steam (no Swofty, no test, no pad input), with Tyler watching. If a corrupt-save dialog
   appears, close the game without answering it.

## Time Trial by route (works since 2026-10-31)

`harness/tests/udp_tt.test.json` reaches an AI-driven Time Trial session at Melbourne. The pad sequence, with a frame
of each screen, is in `runs/2026-10-31-udp-tt-3/summary.md` and `docs/time_trial_route/`. Points that cost runs:

- `play` opens either `solo_container` or `f1_world_activity_container` (F1 World's offline cards), depending on the
  run, so wait on a log regex that takes either.
- There's no pause step: `wait` takes only event, log or screen, and `sample` fails outside a session. Hold `ls` (does
  nothing on these menus) as the pause; a hold of N ms takes about 2N ms of wall time.
- `capture` doesn't work yet; `tools/window_frames.ps1` saves the game window every few seconds (PrintWindow) to
  see what the menus show.
- A Time Trial rewrites `savegame@profile` even without a completed lap, so the save guard restores it every run.

### Benchmark leaves them alone

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
