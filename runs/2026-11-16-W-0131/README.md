# #131 workaround race: AI-only, the player parked last (Starting Grid Custom). FAIL

16 Nov 2026, 08:47-09:02 PT. `gp_menu_full_press_dry_hungary_grid.plan` (#133): Hungary, difficulty 100, 5 laps, Quick
Weather Clear (Dry), Starting Grid Custom with the player moved to P20. Stock otherwise, plus msyeett.starting-grid
0.1.4 in verve-test. Launcher 1.9.59 (`race_1/launcher.txt`), build 26566308. Saves unchanged, guard 0.

**`tools/b0131_check.py` (#135): INVALID, and FAIL on the live-race check**:
- **ai_drives_player on 1.9.59:** still "unavailable: the player's car: the car field offsets are the KB build's and
  this is not that build" (08:56:09 and 08:56:11).
- **The player** started P20 (UDP grid), was penalised (type 6) at 20.0 s and retired (RTMT) at 30.0 s.
- **Simulated from 31.0 s:** one 88 s telemetry gap, and a session/wall ratio of 3.58 from lights out to the
  classification. laps.csv is incomplete for all 19 AI cars, so lap-1 disturbance can't be measured. Same as the pilot
  (F-45).
- **SCAR:** 0 (in the 0-31 s window, the only live part).
- **Weather:** NOT LOCKED under #118 as amended. The weather byte was 0 in all 79 race Session packets and the
  forecast weather was 0 in all 237 samples, but rain% was 3 (158) and 4 (79), not one constant. So the "floor" under
  Clear (Dry) isn't always a flat 3; that's for the supervisor's ruling.
- **gamedb 56:** as expected.
- **Grid order (UDP):** Bortoleto, Russell, Tsunoda, Hamilton, Lawson, Verstappen, Leclerc, Hadjar, Norris, Antonelli,
  Gasly, Piastri, Colapinto, Albon, Ocon, Alonso, Bearman, Hülkenberg, Sainz, with the player 20th. That **doesn't
  match** the Grid Editor list seen in discovery (#133), so the editor's base order is reshuffled per session. Only
  "player last" holds.

The verdict for race-feel baselines is **FAIL**: a player DSQ means a simulated race. The FinalClassification is
still usable as a source only (not scored): all 19 AI cars were classified as finished.
