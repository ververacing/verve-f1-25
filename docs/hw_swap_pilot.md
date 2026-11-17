# Pilot: the low-graphics test preset (`-LowGraphics`, tools/hw_swap.ps1)

**Status: planned, not run.** It runs once V-1 is scored and #166 is merged. Until the pilot passes, no batch uses
`-LowGraphics`. If the pilot fails, the switch stays off.

## The launch

One stock Austria launch: two races, no add-on, not scored. It uses the Austria discovery plan, after the usual
pre-flight.

    powershell -File tools/preflight.ps1
    powershell -File tools/b0016_run.ps1 -Race 1 -Batch runs/<date>-HW-pilot -StockOnly -LockedWeather -LowGraphics `
        -Plan harness\sessions\austria_discovery_2races.plan

Before the launch, record the live file's SHA-256 and confirm pre-flight says `settings: values identical to the
reference`. Record the hash only, never the file. Keep `%LOCALAPPDATA%\verve-f1-25\state\hw_swap.log` and the race
folder's `hw_swap.txt`.

## Checks

**(a) The game keeps the preset, and UDP still arrives.**
- The game does NOT reset the file to defaults (`applyOOTB`). Read the file's values once the race has started. This
  is read-only, through `Compare-HwValues` against the preset copy named in `state\hw_swap.json`. Expect no difference,
  or only the game's own normalisation of an `unverified` key; record each one.
- `motion/udp` stays enabled, on 127.0.0.1:20777, with format 2026 (and Tyler's sendRate).
- UDP packets arrive from lights out in both races (`udp_races.txt`, `udp\sessions.csv`).
- **If UDP is missing, the pilot fails and the swap stays off.**

**(b) Tyler's file comes back after the game exits.**
- `hw_swap.txt` shows `restored (swap-back)` after the game's exit.
- The live file's SHA-256 equals the hash recorded before the launch.
- Pre-flight's values compare says `identical to the reference`.
- The guard's saves check is clean (`saves_diff.txt` is empty).

**(c) A forced interrupt.** Run `tools/pause.ps1` during race 2. Then check:
- the verdict is SAFE TO PLAY only after the restore (`state\hw_swap.log`: the restore line is timed before
  `pause_result.txt`);
- the live hash is Tyler's;
- the race is marked `pause_cut.txt`;
- the runner's own swap-back afterwards is a no-op (`back: no swap active`).

RESUME with `pause.ps1 -Clear` afterwards.

**(d) Timings and load, if they're cheap to read.** Compare these with the Austria discovery launch
(`runs/2026-11-16-V1-austria-disc`):
- boot to splash, splash to the main menu, and menu to lights out (transcript times);
- each race's wall time;
- GPU and CPU load, only if a counter is cheap to read without installing anything (for example
  `Get-Counter '\GPU Engine(*)\Utilization Percentage'` and `'\Processor(_Total)\% Processor Time'`, sampled during
  race 1). Otherwise leave them out.

**The 10 `unverified` keys.** Record the real value form of each, read-only, from the preset the game re-serialised
(the edit log in `hw_swap.txt` shows the starting forms):
- `graphics_card/resolution@displayMode`
- `antialiasing@dlss`, `antialiasing@fsr3`, `antialiasing@xess`
- `aa_quality@value`
- `frame_gen@mode`, `multi_frame_gen@value`
- `lighting@quality`
- `postprocess@motionBlurV2`
- `crowd@distanceScale`

Mark each row `ok` in `tools/hw_test_preset_keys.csv` once its form and test value are confirmed, or fix it (in its
own PR).

## Pass

The pilot passes when (a), (b) and (c) all pass. The window must also really open at 1280x720 with no monitor mode
switch, and the game must reach lights out in both races as it does at full graphics. (d) and the key forms are
recorded for the supervisor; they don't decide the pass.
