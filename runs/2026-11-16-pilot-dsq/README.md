# Pilot (not counted): the H-dry proof race that ended in a player DSQ

**Pilot, not counted.** This was run as the H-dry proof race and would have been B-0018 race 1 (#120, #118 step 2).
It's discarded, and B-0018's race count starts at 0 (supervisor, 2026-11-16). The folder was renamed from
`runs/2026-11-16-B-0018/`.

16 Nov 2026, 08:01-08:15 PT. `gp_menu_full_press_dry_hungary.plan`, stock, `-LockedWeather`, launcher 1.9.58,
build 26566308. Realistic grid, with the player starting P13.

## What happened
- **`ai_drives_player` was unavailable:** "the player's car: the car field offsets are the KB build's and this is not
  that build". Nobody drove car 19. It was penalised (type 6) at 20.0 s, retired (RTMT reason 6, black flag) at
  30.0 s, and SEND came at 31.0 s.
- **The rest of the race was simulated.** The UDP stream stops at session time 31.0 s and resumes 90 wall-seconds later
  at 450.5 s, with the results. So 419 s of race went by in 90 s, with no telemetry. `laps.csv` is empty: every car
  jumps from lap 1 to lap 5.
- **FinalClassification:** all 19 AI cars finished (status 3, 5 laps, best laps 78.5-80.1 s); the player has status 4
  and 0 laps. There was no SCAR in the 0-31 s window.
- **Weather:** weather 0 in all 76 race Session packets, and rain% a flat 3 in all 228 forecast samples. LOCKED under
  #118 as amended (rain% constant ≤ 3). `weather.txt` here was written before the amendment and says NOT LOCKED.
- **Held on 1.0.145:** the hud expect before the rundown press, the garage monitor, track id 9 at fifteen rights, and
  the save guard (saves unchanged).

`race_1/raw/udp.bin` (gitignored, kept on the test PC) is the known-FAIL fixture for `tools/b0131_check.py`'s
live-race check.
