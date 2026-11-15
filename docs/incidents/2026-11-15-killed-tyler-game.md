# Incident 2026-11-15: our race runner killed Tyler's game

**Summary.** After B-0016 race 2 (#101) quit, `tools/sandbox_shell.ps1` waited 120 s for the test shell to exit,
and then force-stopped every process named `swofty` or `F1_25`. Tyler had opened the Swofty Launcher and started
his own game in that gap. His game and its Swofty session were killed at 08:31:59 PT. The local agent caused it; the
supervisor and Tyler were told as soon as it was diagnosed.

## Timeline (PT)

| Time | What |
|---|---|
| 08:16:13 | B-0016 race 2 starts (`tools/b0016_run.ps1`, profile verve-test, +swofty.lap1-ai). |
| 08:28 | Tyler: "Pause after the current race". Race 2 is left to finish. |
| 08:29:56 | Race 2's plan sends `quit`; the game quits. The test shell starts its own cleanup and restore. |
| 08:30:24 | Tyler opens the Swofty Launcher (1.9.54). |
| 08:30:33 / 08:30:48 | Tyler presses Play: session `20261115-163048`, game starts. |
| 08:31:53 | In his game, Tyler opens the mod menu. |
| ~08:31:56 | Our 120 s wait after `quit` runs out: `Get-Process swofty, F1_25 \| Stop-Process -Force` (sandbox_shell.ps1 line 266 before the fix). |
| 08:31:59 | Tyler's game: "[offline] game exited with code 4294967295" (-1, the code `Stop-Process -Force` leaves). His session folder gets no game_end or exit code; its log lands in `sessions\orphaned-logs`. The game folder is left modded (journal `18e844ef557cb610-30780` open, ui_package .erp files changed, version.dll present). |
| ~08:32 | Our post-run check runs `swofty doctor`: NOT CLEAN (12 drift lines). The storage sidestep refuses (a swofty process is up), so "URGENT ... restore not tried". No restore, nothing moved. Our runner then defers the saves check and exits 11, which **hid** the URGENT. |
| 08:32:15 | Tyler presses Play again: session `20261115-163234`. His launcher rolls the folder back and the game starts. |
| 08:33:16-08:33:33 | The agent merges #106 through `tools/merge_pr.ps1` (repo selftests only; no Swofty or game command). |
| after 08:34 | Tyler: "Make sure neither of you are touching anything. Swofty just closed the game on its own without me." Hands off. |
| 09:06:05 | Tyler's second session ends normally: "F1 25 exited with code 0", "the game folder is back to vanilla", "rolled the profile's game files back". |
| 09:07 | RESUME. The read-only diagnosis follows. |

## Cause

1. **Stopping by name.** `sandbox_shell.ps1` (4 places), `sandbox_run.ps1` (3) stopped processes with
   `Get-Process swofty, F1_25 | Stop-Process -Force`. That matches Tyler's game and his launcher's swofty sessions
   as well as ours.
2. **No check for a process that isn't ours after the race.** The runner went on with its post-race steps (kill on
   timeout, doctor, sidestep) after Tyler's launcher had appeared.
3. **A deferral hid an URGENT.** `post_run_check` returned 2 (URGENT), but the deferred-saves path exited 11, so the
   runner said DEFERRED, not URGENT.

The test shell didn't exit within 120 s, most likely because Tyler's session had started on the same game folder
while the shell was still restoring it.

## Impact

- Tyler's session of 08:30:48 was terminated at 08:31:59, about a minute in (he was in the mod menu; no race lost).
- The game folder stayed modded until his next Play (08:32:15) restored it.
- No save change found: his launcher logged "the profile save is unchanged since snapshot ..." at the start of the
  second session, and the Steam remote listing is the same at its start and end. The deferred saves check for race 2
  runs at the next pre-flight.
- B-0016 race 2's own data is intact (UDP, race_feel). Its loader.log and validity are still to be done.

## Fixes (PR after this incident; reviewed by the supervisor before merge)

- (a) `post_run_check.ps1`: while F1 25 **or the launcher** is up, SKIPPED (exit 4) before any swofty command,
  `doctor` included. Selftest cases for both.
- (b) `sandbox_shell.ps1`: once a game or Swofty process that isn't ours appears (during the post-quit wait or at the
  end), no post-race Swofty steps at all: no kill, no loader.log read, no doctor, no cleanup, no saves check.
  Everything is deferred to the next pre-flight. The runners don't read under Swofty while anything is up.
- (c) `tools/safe_to_play.ps1`: after every PAUSE and window close, "SAFE TO PLAY" only once our processes are gone
  and the post-run check, cleanup and deferred check have finished; otherwise "WAIT: cleanup running".
- (d), (f) PID ownership everywhere (`tools/ours.ps1`): every process we start (test shell, test session, UDP
  capture, process trace) is recorded with its start time in `<run>\ours.csv`. The game, which starts through Steam,
  is adopted ONLY by the PID its test agent reports; there is no fallback (a game whose PID wasn't reported stays
  foreign, is never stopped, and waits for pre-flight). Every stop targets only those PIDs and their child trees,
  with the start time checked (a reused PID doesn't count). The descent never enters or passes steam*,
  swofty-launcher*, explorer or F1_25*, and Steam, the launcher and explorer are never ours even if recorded, so a
  Steam our shell started can't make Tyler's later games "ours". Nothing stops while anything foreign runs. No
  script stops a process by name.
- (e) An URGENT post-run result is never hidden by a deferral: the runner exits 7.
- (g) docs/process.md: PAUSE step 2 reworded, plus the standing override for scheduled-task wording.
- (h) `tools/test_ours.ps1`: starts foreign dummies named F1_25.exe and swofty-launcher.exe and checks that
  Ours-Stop, post_run_check, storage_sidestep, cleanup_test_profiles, sandbox_shell and safe_to_play all leave them
  running. merge_pr runs it.
- Also: our session log is the FIRST session folder created after our launch, not the newest (race 2 picked Tyler's).
