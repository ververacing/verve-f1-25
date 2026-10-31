# udp_tt: first in-game UDP check outside benchmark (#4)

`tools/run_with_udp.ps1 -Test harness/tests/udp_tt.test.json`, 2026-10-31 02:33. Route `f1_world > play`, then
Swofty's documented Time Trial pad sequence, with the capture on 127.0.0.1:20777.

## Result: test FAIL, but UDP flows

- **The game sends UDP in a modded, offline launch.** 21 packets, format 2026, game version 25.1.26, all Event
  packets with code `BUTN` (button status), one per virtual-pad press and the presses around them. No size mismatches.
  So B-0003's 0 packets were benchmark mode, not the offline launch or the launcher (`udp/sessions.csv`,
  `udp/events.csv`).
- **No session started.** `wait session.start` timed out after 150 s. The route reached `solo_container` (F1 World's
  Play cards) at 02:35:00.86. The pad presses that should pick Time Trial, the season, the team and the track opened no
  further screen (`loader.log`: no `[test] screen` lines after `solo_container` until the quit at 02:37:32). The
  presses came within a second of the screen opening, so the likeliest cause is pressing before the cards were ready;
  the fix is a `wait` on `screen solo_container` plus a pause before the first press.
- **No session, so no Session, Participants, LapData or CarTelemetry packets:** the parser's per-car outputs are empty.

## Save safety (blocks further route tests)

`loader.log`: "no save sandbox (run.json names no saves), so the game uses the player's own saves". Only the `career`
environment takes a fixture (`swofty test plan` rejects `fixture` on a `route` env: unknown key), so **every Time
Trial or Grand Prix test by route runs on Tyler's own saves**. This run wrote none: the newest file in the save folder
is from 2026-10-30 22:37, before the run (Steam's `remotecache.vdf` and the hardware settings are rewritten on every
exit, benchmark included; settings still differ from the pre-UDP backup only in `<udp>`). A Time Trial lap or a Grand
Prix could write records, F1 World progress or a mid-session save, so the next route test waits for Tyler's decision.

## Files

`udp/sessions.csv`, `udp/events.csv`, `udp/cars.csv`, `udp/laps.csv` (empty: no session). The raw capture is in
`%TEMP%\verve-udp\20261031-023344\`; `raw/` isn't committed.
