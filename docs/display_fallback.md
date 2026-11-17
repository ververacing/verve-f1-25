# Display fallback: the game boots at the desktop's 1024x768 (supervisor desk check, 2026-11-17)

**What it is.** At the end of a test launch, Tyler's `hardware_settings_config.xml` differs from his reference only in
`graphics_card/resolution` (1920x1080 -> 1024x768). `tools/hw_display_restore.ps1` (#168) keeps an evidence copy, puts
the two values back and verifies, before SAFE TO PLAY. Validity isn't affected: AI behaviour and saves are unchanged.

## Finding (from saved files only: each launch's `raw/loader.log` and `display_fallback.txt`)

- **The resolution is set at START, not at exit.** The loader log's first `CreateSwapChainForHwnd (WxH)` line is already
  1024x768 in every fallback launch. The game then writes that resolution to the settings at exit. The restore fixes
  Tyler's file, but the next boot falls back again.
- **Every fallback launch actually ran at 1024x768.** Perf lines still show 60 fps.
- **The quit path is not the cause.** Every launch, 1920x1080 or not, ends the same way: `quit`, then F-47's crash-on-quit
  (TerminateProcess 0xffffffff, a crash report). V-1 launch 5 ended that way and the next launch still booted at
  1920x1080. The launcher was unchanged across the switch (1.9.59).
- **Display query 1** (read-only, supervisor-approved, 2026-11-17 08:11 PT, nothing running): the Windows desktop on the
  GPU's physical output was itself at 1024x768, and that monitor read "off line". A virtual display adapter from a
  remote-desktop tool was also present, at its own resolution. So the game simply boots at the desktop's resolution.
- **Display query 2** (2026-11-17 09:13 PT, nothing running) read the same: the desktop on the physical output was still
  at 1024x768 and the monitor still off line. It doesn't separate the guess from other causes, because the monitor never
  came back online between the queries.
- **Best guess, still UNVERIFIED:** when the physical monitor goes off line (off or asleep), Windows
  drops that output to 1024x768, and the game follows the desktop. It began between 19:52 and 20:29 PT on 2026-11-16.

**Rulings (supervisor, 2026-11-17).** It's harmless: tests at 1024x768 are fine. There's no fix to the fallback, the
restore stays, and display and power settings are never changed. #186 adds a start-of-run and preflight restore
(`-FallbackOnly`: the exact 1024x768 fallback only) for a run that crashed or was killed before its own restore. For #166,
perf comparisons must use launches booted at the same swapchain size.

## Per launch

Boot = the first `CreateSwapChainForHwnd` size in `raw/loader.log`. Fallback = a resolution-only change at the end,
restored (`display_fallback.txt`, or by hand for V-1 launch 7).

| Batch | Launch | Boot | Fallback at end |
|---|---|---|---|
| 2026-11-16-V1-readback | 1 | 1920x1080 | no |
| 2026-11-17-V1 | 1-5 | 1920x1080 | no |
| 2026-11-17-V1 | invalid launch_6_1 (19:52) | 1920x1080 | no |
| 2026-11-17-V1 | 7 (20:29) | 1024x768 | yes, the SAVES CHANGED stop, restored by hand |
| 2026-11-17-V1 | 6 (rerun), 8-12 | 1024x768 | yes, auto-restored |
| 2026-11-17-D1 | 1, 2 | 1024x768 | yes, auto-restored |
| 2026-11-17-D4 | 1, 2 | 1024x768 | yes, auto-restored |
| 2026-11-17-C1-smoke | 1 | 1024x768 | yes, auto-restored |
| 2026-11-17-C1 | 1, 2 | 1024x768 | yes, auto-restored |
| 2026-11-17-S1-baseline | 1, 2 | 1024x768 | yes, auto-restored |

Earlier sporadic 1024x768 boots, in invalid race attempts: B-0016 race_3_2 (2026-11-15 09:36), B-0016 race_12_1 (12:16),
and B-0015 race_2_1 (21:54).

Records correction: the D1 and D4 summaries said "no display fallback". Both launches of each had one, auto-restored.
