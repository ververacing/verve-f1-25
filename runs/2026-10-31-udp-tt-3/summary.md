# udp_tt runs 2-4: Time Trial by route reaches a session, AI-driven, under the save guard (#4)

Four guarded route runs, 2026-10-31 07:16 to 07:30, each through `tools/run_with_udp.ps1`, which wraps the run in
`tools/saves_guard.ps1`.

| Run | What it tried | Result | Saves |
|---|---|---|---|
| `udp-tt-2` (07:16) | wait `screen solo_container`, then the documented pad sequence | FAIL: `play` opened `f1_world_activity_container`, so the wait timed out | unchanged |
| `udp-tt-probe` (07:21) | `sample` as a pause | FAIL: `sample` needs a session ("no cars in the session") | unchanged |
| `udp-tt-probe2` (07:23) | `ls` holds as pauses + `tools/window_frames.ps1` | pass; reached `track_select` | unchanged |
| **`udp-tt-3`** (07:27) | full sequence below | **pass (2 m 6 s): Time Trial session, AI drove** | **profile save changed, restored** |

Steam Cloud for F1 25 was on for `udp-tt-2` and off from `udp-tt-probe` on (Tyler, about 07:20; `docs/harness.md`
toggle log).

## The route (`harness/tests/udp_tt.test.json`, frames in `docs/time_trial_route/`)

1. Route `f1_world > play`, then wait for `[test] screen (solo_container|f1_world_activity_container)`. This run got the
   activity container: F1 World's offline cards, Grand Prix / Time Trial / Retry Connection (frame 1). The 02:33 run got
   `solo_container`. Which one opens differs between runs, so the wait takes either.
2. Hold `ls` 6 s, then `right` (Time Trial, frame 2), then `a`.
3. Season select, F1 2026 first (frame 3): `a`. Team select, McLaren first (frame 4): `a`.
4. Wait `screen track_select` (Australia first, frame 5), hold `ls` 6 s, `a` = Start Session. `session.start` fired
   13 s later.
5. Garage (frame 6): hold `ls` 8 s, `a`, hold `ls` 4 s, `a` (Flying Lap). Then `ai_drives_player`: the car ran at
   306 km/h in 8th gear on lap 1 (frame 7).

`ls` (left-stick click) does nothing on these screens, so holding it is the only pause there is: `wait` takes only
event, log or screen, and `sample` fails outside a session. A hold of N ms takes about 2N ms of wall time.
`capture` doesn't work yet (Swofty docs), so `tools/window_frames.ps1` grabs the game window with PrintWindow every
few seconds.

**Gap:** the gear `sample` (for_s 240) stopped after 29 samples / 30 s and the test passed. So no full lap: the
lap-time and LapData steps still need a longer drive. Cause not yet known.

## Saves (guard working as designed)

`saves_changes.csv`: `savegame@profile#NXDSMWW.BWW` 521128 -> 519688 bytes and `savegame@profile#QKRHMYXE` (416, hash
changed). A Time Trial writes the profile save even without a completed lap. Both were moved to
`save-backups\20261031-072721-2026-10-31-udp-tt-3\written_by_test\`, Tyler's originals copied back (mtime now) and re-hashed: "saves
match the backup again". No other save file changed. The other three runs wrote nothing.

## UDP (`udp/`)

- 9,512 packets, 9,465 of them in one `time_trial` session (track 0 = Melbourne, 1 active car, player car 0).
  Motion, CarTelemetry, CarStatus, MotionEx, TyreSets and packet 16 at about 1,075 each; TimeTrial and LapPositions
  55 each.
- **LapData didn't parse:** all 1,370 LapData packets have a 1370-byte body, against the parser's F1 25 layout
  (22 x 57 + 2 = 1256). The game reports format 2026 (25.1.26), so the 2026 LapData record is larger. So `laps.csv` is
  empty and the per-car speeds are NA. The parser needs the 2026 layout (#4).
