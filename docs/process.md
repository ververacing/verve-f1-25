# Working process

The rules for the local agent, the cloud supervisor and Tyler. Until 2026-11-03 these only lived in the supervisor's messages. The technical side (sandbox, hash guard, hygiene) is in [harness.md](harness.md).

## PAUSE

From Tyler or the supervisor. Do these in order:

1. Abort the current run. Losing it is fine.
2. Quit F1 25 and every swofty, test and UDP process.
3. If no such process remains, clear a stale `%LOCALAPPDATA%\swofty-game.lock.d`.
4. Run `swofty restore`. `swofty doctor` must then show no drift.
5. Check Tyler's `remote\` and Steam's records against the last-known-good snapshot. **Report** any difference and don't touch it.
6. Report the Steam Cloud state. If it's off and the check passed, tell Tyler it's safe to turn on.
7. Delete leftover `test-*` profiles where they're unlocked. Tyler's own profiles, addons, saves and settings stay untouched.
8. Commit and push, naming explicit paths only.
9. Message the supervisor `PAUSED` plus 2-3 lines: doctor, saves, Steam Cloud, active profile.

Then start nothing until RESUME.

## RESUME

1. Pre-flight: `tools/preflight.ps1` (build pin, drift, cleanup, hardware-settings diff).
2. Take a fresh last-known-good snapshot of `remote\` and Steam's records.
3. Go on with the queue.

## Testing windows

Game testing runs every day in two windows, Pacific time: **09:00-17:00** and **00:00-06:00**.

- **Wrap-up at 16:45 and 05:45:** no new launches. Finish the current run only if it ends by :58, otherwise abort it as "window end". Finish the full PAUSE routine by the top of the hour, then message the supervisor `WINDOW CLOSED` plus 2 lines.
- **Outside the windows:** non-game work only (analysis, verve.skip with Zig, docs, PRs). Never launch F1 25, and keep the CPU load light.
- **If F1 25 or another game is running that the agent didn't start, Tyler is playing:** don't launch, even inside a window.
- **Tyler's PAUSE inside a window** holds until RESUME or the next window opening.
- **Planning:** the day window suits shorter batches and tooling checks. The night window suits long unattended batches (20-30 start replications, multi-race behavioural batches). Size every batch to finish 15 minutes before its wrap-up.

**Scheduled messages only reach the agent between turns, so these rules can't depend on one arriving on time:**

- Check the Pacific clock before every launch and between runs. Never start a run that can't finish 15 minutes before the next wrap-up (16:45 or 05:45).
- No single blocking command may run past a wrap-up. Split long batches into per-race calls, so control comes back between races.
- If a window turns out to have closed unnoticed, do the PAUSE routine at once.

The supervisor's scheduled tasks post into the local session: "Verve testing window opens" (09:03 PT), "Verve night testing window opens" (00:00 PT), "Verve testing window wrap-up" (05:45 and 16:45 PT) and "Verve hourly heartbeat (window-aware)" (:37 every hour).

## Messages to the supervisor

- Stopped with work still possible: `IDLE: <why> | next candidates: <issues>`
- Blocked on Tyler: `WAITING ON TYLER: <what>`
- Every report includes a commit sha or a PR number.

## Merging

- Docs and results-text PRs may merge after the supervisor's review, or without it if docs-only and trivial.
- Generator, addon, test-file and tools changes wait for the supervisor's review.
- "DO NOT MERGE" from the supervisor holds until it's resolved.
- Tyler's word overrides all of these.

## Guardrails

- Offline only.
- The sandbox and the hash guard apply to every route, Grand Prix and career run.
- Never touch `cede_position.*`, `yellow_flag_*` or `flying_lap_yield_*` keys.
- Nothing gets published.
- No images outside `harness/fixtures/frames` and `docs/`.
- No account ids or user paths in commits. The pre-commit hook (`tools/pre_commit_check.ps1`) and `tools/scrub_logs.ps1` catch these. **A fresh clone doesn't have the hook**: run `powershell -File tools/pre_commit_check.ps1 -Install` once.
- Steam Cloud stays off for save-writing sandbox runs until 3 clean write runs on a new Swofty version, since the sandbox implementation may have changed. Tyler can switch it on after that.

## Toolchain

Native addons build with Zig, matching Swofty's template (`zig c++ -target x86_64-windows-gnu`). It's a portable download with no UAC. MSVC is a backup only. A UAC prompt can't be clicked over Parsec, so anything needing one waits until Tyler is at the PC.
