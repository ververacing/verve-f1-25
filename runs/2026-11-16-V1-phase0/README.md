# V-1 Phase 0: Restart Session discovery (2026-11-16)

One launch on game build 26566308 (F1 25 1.0.145.2472) using the spectator garage-start route (F-46) at Hungary, with
the plan `harness/sessions/phase0_restart_discovery.plan`. It tests whether several races can run inside one launch
with Restart Session.

## Results

- **The path:** `pad start` opens the pause menu. Restart Session is on top, and pressing A opens a confirm dialog
  that defaults to Cancel. `pad up` then `pad a` confirms. After about 8 s the screen is `garage_monitor_container`
  (the pre-race garage), which skips the 125 s rundown. `pad a 700` starts the race.
- **Each restart is a new race:**
  - It gets a new UDP session uid, with its own SSTA and LGOT.
  - The player car is re-parked on each race.start.
  - The grid stays the same within a launch.
- **Restart to lights out takes about 20-35 s.** A 5-lap Austria race comes to about 6.5 min, against 15.8 min per
  launched race on the old route.
- **UDP start measures** (4 starts × 19 AI = 76 car-starts; LapData at 60 Hz):
  - **reaction** = the LGOT wall time to the car's first totalDistance gain of 0.3 m or more. Results: 0.351-0.570 s,
    median 0.468. The per-car SD across restarts has a median of 0.044 s. There's a constant offset, so this is a
    relative measure only.
  - **launch** = the distance in the 2 s after the car's own first movement: 16-23 m.
- **The game log is unavailable.** The RaceStarts game log isn't available on 26566308 (no `log_channels.tsv` for
  this build), so start measures come from UDP.
- **Crash report at quit.** The quit ends with the systemic exit -1 crash report (F-47). Saves are unchanged.

The raw capture (`race_1/raw/udp.bin`) stays local (it's in .gitignore).
