# Working process

The rules for the local agent, the cloud supervisor and Tyler. Until 2026-11-03 these only lived in the supervisor's messages. The technical side (sandbox, hash guard, hygiene) is in [harness.md](harness.md).

## PAUSE

From Tyler or the supervisor. Do these in order:

1. Abort the current run. Losing it is fine.
2. Quit F1 25 and every swofty, test and UDP process.
3. If no such process remains, clear a stale `%LOCALAPPDATA%\swofty-game.lock.d`.
4. Run `tools/post_run_check.ps1` (no drift, 0 open journals, no version.dll; if not clean it does one storage sidestep
   and one `swofty restore`). Exit 2 = URGENT: tell the supervisor and Tyler at once, Tyler must not launch the game.
5. Check Tyler's `remote\` and Steam's records against the last-known-good snapshot. **Report** any difference and don't touch it.
6. Report the Steam Cloud state. If it's off and the check passed, tell Tyler it's safe to turn on.
7. Delete leftover `test-*` profiles where they're unlocked. Tyler's own profiles, addons, saves and settings stay untouched.
8. Commit and push, naming explicit paths only.
9. Message the supervisor `PAUSED` plus 2-3 lines: doctor, saves, Steam Cloud, active profile.

Then start nothing until RESUME.

**While paused, and whenever F1 25 or the Swofty Launcher is running and the agent didn't start it** (standing rule,
supervisor, 2026-11-14, after a check ran against Tyler's live session at 20:55; nothing was changed):
- Run NO swofty CLI commands at all, read-only ones like `doctor` included.
- No reads or writes under `%LOCALAPPDATA%\Swofty` or the game folder, and no scripts that touch them.
  `storage_sidestep.ps1`, `cleanup_test_profiles.ps1`, `guard_snapshot.ps1` and `post_run_check.ps1` refuse or skip
  on their own when the game or the launcher is running.
- Only repo, docs and analysis work on files already copied out.
- The first Swofty-touching command after RESUME is `tools/preflight.ps1`.

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

**Window override log.** One-off changes to the windows, each with Tyler's words and the time. Every run in an
override window also gets a `window_override.txt` in its folder.

| Date | Window | Wrap-up | From | Tyler's words |
|---|---|---|---|---|
| 2026-11-14 | about 17:27 to 20:30 PT | 20:15 | Tyler, relayed by the supervisor about 17:27 PT | "Also you are good to start running tests from now till 8:30pm, exception for tonight" |
| 2026-11-14 | about 18:12 PT to 06:00 PT (15 Nov), continuous | 05:45 | Tyler, relayed by the supervisor about 18:12 PT | "You can start things now, no need to wait till midnight. Just plan to go through the night. I'll likely pause you around 8:30 but we can work around that and I'll give you a heads up" |

The supervisor's scheduled tasks post into the local session: "Verve testing window opens" (09:03 PT), "Verve night testing window opens" (00:00 PT), "Verve testing window wrap-up" (05:45 and 16:45 PT) and "Verve hourly heartbeat (window-aware)" (:37 every hour).

## Messages to the supervisor

- Stopped with work still possible: `IDLE: <why> | next candidates: <issues>`
- Blocked on Tyler: `WAITING ON TYLER: <what>`
- Every report includes a commit sha or a PR number.

## Merging

- Docs and results-text PRs may merge after the supervisor's review, or without it if docs-only and trivial.
- Generator, addon, test-file and tools changes wait for the supervisor's review.
- "DO NOT MERGE" from the supervisor holds until it's resolved.
- Never chain commit + merge in one command. Merge only after the pre-commit hook and the tests have passed, as a separate step (2026-11-14: a refused commit went unnoticed and #81 merged without its fix).
- Tyler's word overrides all of these.

## Profiles (2026-11-14)

- **`tyler` is Tyler's** racing profile, with his community addons and his own launcher save. Never select, build,
  edit or clean it. The same goes for any profile Tyler makes himself.
- **`verve-test` is the agent's only profile.** Profile names allow letters, digits, `-` and `_` only, so it can't be
  "Verve Test". Arms switch addons and settings inside it (or with `--addon` on the run), with no copies. Every run
  logs the exact profile file (`profile.json`) and its hash (`settings_hash.txt`) in its folder.
- `swofty test` makes a throwaway `test-*` profile per run. Every run script deletes it when the run ends
  (`tools/cleanup_test_profiles.ps1`), and pre-flight fails if any is left over.
- **`swofty addons install` writes the new id into every profile,** Tyler's included (as a disabled entry). Install only
  when a batch needs it, and say so in the batch's PR.
- **Never press Play on `verve-test` in the launcher** until it has its own save: with launcher saves on and an empty
  store, the launcher copies the Steam save in at the first Play.

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

## Pause log

| Date (PT) | Event | From |
|---|---|---|
| 2026-11-14 20:42 | PAUSE ("Pause now"). B-0014 race 5 aborted before its session, marked invalid ("pause") on #71. | Tyler, in the agent's chat |
| 2026-11-14 22:17 | RESUME ("you are good to resume"). Pre-flight OK after one `swofty restore` for the benign cache-file line; fresh LKG `20261114-221808-lkg-20261114-resume` (Steam remote unchanged since 17:21; Tyler's launcher save changed by his play). | Tyler, in the agent's chat (also relayed by the supervisor) |

## Housekeeping log

| Date (PT) | What | Who decided | Done |
|---|---|---|---|
| 2026-11-14 19:11 | Deleted 31 `career-vault\launcher-test-*` folders (test profiles of 31 Oct to 4 Nov; Swofty's backups of the Steam-save copies imported into them): 208 files, 16.9 MB. Other vault folders unchanged (`launcher-tyler` 11 files, the Steam vault folder 10 files). | Tyler ("Yeah you can delete those"), via the supervisor | between B-0014 races 1 and 2, no swofty or F1 25 process running |
| 2026-11-14 from 18:54 | Each test profile's imported copy of the Steam save is deleted after the run only if every file is sha256-identical to Tyler's current Steam file (`tools/cleanup_test_profiles.ps1`, logged per run in `cleanup.txt`). | Supervisor, ruling A | automatic |
