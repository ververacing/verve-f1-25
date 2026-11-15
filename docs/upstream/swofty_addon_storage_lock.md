# Draft: addon storage swap fails with os error 32 on Windows (Swofty 1.9.51)

**Not posted.** A draft for Tyler to post on the Swofty Discord or GitHub if he wants. Nothing private in it.

> **`swofty test session` / `apply` / `restore` abort with "addon-profiles\<id>\.saved-old ... os error 32" when the
> profile isn't the active one (1.9.51, Windows 10)**
>
> **Setup.** Windows 10 Pro 19045, Steam F1 25 build 25251167, Swofty 1.9.51 (core 0.2.13). Active profile `A`
> (launcher saves on). A second profile `B` enables teamsimplified.mods, dromodf.skip-cutscenes 1.9.4 and
> twilight.offline-quiet 1.0.1. `addon-profiles\<id>\A` exists and is empty for those three, and `.current` reads `A`.
> Windows Defender real-time protection is on, with no exclusions we know of.
>
> **Repro (no game needed).** `swofty --profile B apply`. It exits 1 with
> `addon-profiles\dromodf.skip-cutscenes\.saved-old: The process cannot access the file because it is being used by
> another process. (os error 32) -- still locked after 5 retries`. The same happens at the start of
> `swofty --profile B test session ...` and `test shell --profile B ...`: the wrapper logs `addon storage: <id>:
> recovery failed, skipping its profile copies: ...\.saved-old ... os error 32`, then `rollback failed`, then
> `the wrapper exited (exit code: 1) before the game started`. 3 of 3 attempts, with and without the launcher GUI
> open. Profile A's own Play also logged it at session end (non-fatal there).
>
> **Worse: `swofty restore` then can't recover.** After the failed `apply`, doctor shows `journal <id> is open`, nine
> ui_package .erp files differ and version.dll is present. `swofty restore` fails on the same error every time (4
> tries, with the empty `.saved-old` folders removed before each). So the game folder stays modded, and a plain Steam
> launch would run it.
>
> **Where it seems to come from** (reading the source past 1.9.50): `restore` -> `Installer::roll_back` -> `rollback()`
> -> for each addon id in the journal, `addon_storage::save_current(data, id)?`. That calls `save_as`, which stages
> `.saving`, then `finish()`: if the target `addon-profiles\<id>\<label>` exists, it's renamed to `.saved-old`,
> `.saving` is renamed into place, and `remove_tree(.saved-old)` fails with os error 32 after `with_retry`'s 5 tries
> (about 2 s). The `?` then aborts the whole rollback before any game file is put back. The stuck-state recovery at
> session start uses the same `finish()`.
>
> **What we checked.** With no Swofty process running, every `.saved-old` and `addon-profiles\<id>\A` folder opens
> exclusively and deletes at once. A plain PowerShell create, rename to `.saved-old` and immediate delete of a fresh
> folder succeeds 5/5 inside `addon-profiles` and 5/5 in `%TEMP%`. So nothing outside Swofty holds these folders at
> rest. The failure only happens when `remove_tree` runs right after Swofty's own rename, either from Swofty's own
> handle or from a scanner reacting to the rename within the retry window.
>
> **Workaround that worked.** With no Swofty or F1 25 process running, move the EMPTY `addon-profiles\<id>\<label>`
> folders for the journal's addons out of the way. Then `finish()` has no target to rename, so there's no aside to
> remove. `swofty restore` then succeeded first time: "the game folder matches the baseline", no drift, journal closed,
> and Swofty re-created the empty folders itself.
>
> **Suggestions.**
> - Don't let a failed cleanup of the aside abort `rollback()`: putting the game files back matters more than tidying
>   storage. Log the leftover `.saved-old` and remove it on the next start.
> - Skip the swap when both the target and `.saving` are empty.
> - Retry `remove_tree` for longer, or rename the aside to a unique name, so a slow handle doesn't block the next run.
>
> Logs available.

## Our side (2026-11-14)

- Runs: `runs/2026-11-14-speed-direct-1/` (3 attempts at 17:29, 17:31 and 17:39 PT, saves unchanged each time).
- The `apply` probe at about 17:45 PT left the game folder modded. It was recovered at 17:49 PT with the workaround
  above, on the supervisor's ruling. The empty folders went to `Documents\verve-f1-25-recovery\20261114-174915\`,
  logged in `moves.log` there. Afterwards: no drift, 0 journals, saves equal to the 17:21 last-known-good snapshot.
- Rule from now on: never run `swofty apply` as a probe. A failed apply leaves an open journal that `restore` can't
  roll back while this bug stands.
