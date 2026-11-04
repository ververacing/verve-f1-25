# Direct start on Swofty 1.8.4, 2026-11-03 (#64)

First runs after the update, on F1 25 build 25251167. Steam Cloud off. Every launch ran in the save sandbox or left saves alone: Tyler's 11 files and Steam's records matched before and after every run, and the last-known-good snapshot still matches.

**Result: the direct start reaches the race grid and Start Race works, but the race itself doesn't run. No car gets off the grid in any attempt. #57 stays blocked on this route.** The Time Trial direct start works and gives #65 its garage test bed.

## Runs

| Run | Asked for | Reached | What happened |
|---|---|---|---|
| `smoke-184` | Benchmark, Austria, 3 laps, stock | Full race | Pass: 20/20 start lines, gamedb 52 / 322 |
| `sandbox-184-a` | Career fixture | Nothing launched | Transient lock on `addon-profiles\...\.saved-old` |
| `sandbox-184-b`, `-c` | Career fixture | Title | Sandbox confirmed, then stalled: skipped intro |
| `direct-practice` | `team=aston`, practice1 | Race grid | Wrong seat (Colapinto): `aston` matches no label |
| `direct-practice-2` | `team=forceindia`, practice1 | Race grid | Right seat. Asked for practice, got the race |
| `direct-practice-1-name` | `session=practice_1` | Race grid | Same |
| `direct-race-1` | Race, 5 laps | Grid | First try stalled at the title (skipped intro). The retry stopped on my wrong grid signal |
| `direct-race-2` | Race, 5 laps | Lights out | `ai_drives_player` refused. All 20 DSQ at 20 s |
| `direct-race-3` | Race, 5 laps | Lights out | AI on the player's car. All DSQ again |
| `direct-race-nolaps` | Race, no `laps=` | Lights out | Same start. Red flag at 3 s, Safety Car at 13 s. Run ended 45 s after lights out, before any DSQ |
| `direct-race-melbourne` | Race, Melbourne | Lights out | Same start. Safety Car at 3 s, red flag at 5.5 s |
| `direct-tt` | Time Trial | **Garage** | Works: `garage_cockpit` 74 s after launch, `Look Around / Session Info / Go to Track` |

## What the race does

From UDP (`udp/`) and `raw/loader.log`, Austria with `laps=5` (`direct-race-2`):

- Lights out, then `SCAR` 3 s later. At 20 s, all 20 cars get `penalty_type=6, infringement=18` and `RTMT reason=6`. `SEND` at 31 s. The results screen shows DSQ for all.
- The cars are **not on a grid**. They're strung out over 1.7-2 km of track, with no two within 2 m. In the no-laps run they sat about 3.7 km round a 4.3 km lap (Melbourne: 4.5-4.8 km of 5.3 km).
- They drift at a steady 2-8 m/s while telemetry reads about 0 km/h. `grid` reads 0 or 4 for every car.
- `RaceStarts` still logs reaction times, and more than once: 64 lines in `direct-race-2` against 20 in benchmark.
- A vehicle 20 appears in the log (`vehicleId (20) out of range`, velocity failsafes). It's probably the safety car. Benchmark logs it twice.

From memory of the UDP spec, penalty 6 is "disqualified" and infringement 18 is "parked for too long". Not checked against the spec this session.

**Ruled out, one change at a time:** the AI takeover, `laps=`, the track. **Not tried:** another fixture, another box.

**Lead, not proof.** `current session 0 of:` logs an empty session list on all of these runs, so `choose_session` in `native/src/core/direct_start.cpp` returns at `if (!n) return`. That explains why the requested practice session is ignored. The file's comment says a race "builds the grid from" earlier sessions' results, which would fit the empty grid. Upstream's documented runs show a filled list on Classic Seasons boxes, and describe reaching the grid, not racing from it.

## What did work

- Launch to green about 3 min 42 s, with no title, menus or screenshots. Launch to the grid about 3 min 30 s.
- Team, driver and laps all apply: `the player drives for forceindia as lance_stroll`, `race laps 18 -> 5`.
- `pad a` fires Start Race, and `ai_drives_player` works about 1 s after it.
- **UDP works in a Grand Prix, unlike benchmark:** Session, Participants, LapData, Motion, telemetry, FinalClassification. That's the data #57's join needs.
- The guard: sandbox line validated, fail-closed path proven on a real stale lock, saves unchanged throughout.

## verve.skip (#65)

- Cutscene names from the grid: `grid_scs_2018_n...`, `r_grid3_01`, `_03`, `_04`, `_06`, `grid_plyshot`.
- The Time Trial garage is the trace bed. Whether it has a push-in isn't known yet.
- Whether the G29 raises `Menu Accept` still needs Tyler at the wheel.

## Update, later the same day

- **A fixture that holds a Grand Prix (`gp-austria-20261104`) doesn't fix it** (`runs/2026-11-03-direct-race-gpfixture`). The session list fills and grid slots are real, but half the field reads 264 km/h 3 s after lights out and the session ends at 18 s.
- **The normal menu route races to the flag in the sandbox** (`runs/2026-11-03-gp-fixture`), and it's now the route for racing tests. See `docs/harness.md`.
- #57 passed on this direct-start state (`runs/2026-11-03-B-0012`), and #70 passed on the menu route (`runs/2026-11-03-B-0012b`).

## Draft bug report for Tyler to post (nothing private in it)

> **`swofty test session grand_prix f1_2025`: the race starts with no grid, and every car is disqualified (1.8.4)**
>
> F1 25 build 25251167, Windows, launcher 1.8.4, profile with swofty.core and teamsimplified.mods only, fixture made from a copy of a profile save with no careers.
>
> `swofty --profile <p> test session grand_prix f1_2025 austria team=forceindia driver=stroll session=race laps=5 --fixture <f>`
>
> The start itself is great: cover screen, right seat, `race laps 18 -> 5`, and the grid with `Start Race` in about 3.5 minutes. But after Start Race, the cars aren't on the grid. UDP Motion shows all 20 strung out over 1-2 km, near the end of the lap, drifting at 2-8 m/s while telemetry reads about 0 km/h. The Safety Car or a red flag comes within seconds. With `laps=5`, all 20 cars are disqualified at 20 s (`penalty_type=6, infringement=18`), and the results screen shows DSQ for all. Same at Melbourne, without `laps=`, and with `ai_drives_player` on.
>
> Also, `session=practice1` and `session=practice_1` both land on the race grid, although the cover says "Opening the garage". `[direct] Grand Prix (built): ... current session 0 of: ` logs an empty session list, so `choose_session` looks like it returns at `if (!n)`. Your docs show a filled list on Classic Seasons boxes.
>
> **From a fixture that already holds a Grand Prix,** the list fills (`current session 0 of: race`), laps apply (`race laps 71 -> 5`) and cars get real grid slots. But it's still broken: 3 s after lights out about half the field reads 264 km/h while the rest read 0, 12 cars are penalised and retired, and the session ends at 18 s.
>
> **The same race through the menus works perfectly,** in the same save sandbox: a real grid, a full 5 laps to the flag, UDP complete. The differences I can see in the session trace: menus use `f1_custom_team` of setup mode `f1`, and direct start uses `f1_2025` of `swofty_f1`.
>
> `time_trial f1_2025 austria team=forceindia` works perfectly. Logs and UDP captures are available.
>
> Two smaller ones: a label that matches nothing (`team=aston`) carries on in the first seat, where failing the start might be safer. And when the intro video is skipped (`video_1` to `legal` under 1 s), the title never takes the virtual pad, so the direct start stalls on `PRESS ANY BUTTON`.
