# Speed check 4a, direct start on Swofty 1.9.51: no race ran (2026-11-14)

Extra window, authorised by Tyler (`window_override.txt`). Profile `verve-test`, fixture `tyler-profile-20261031`,
`grand_prix f1_2025 austria team=forceindia driver=stroll session=race laps=5`, plan `gp_direct_quick.plan`.

| Attempt | Launched (PT) | Launcher GUI | Result | Saves |
|---|---|---|---|---|
| 1 (`invalid/`) | 17:29 | open | wrapper exit 1 before the game started | unchanged (26 entries) |
| 2 (`invalid/attempt2/`) | 17:31 | open | the same | unchanged (26) |
| 3 (top level) | 17:39 | closed (Tyler's OK) | the same | unchanged (28, now with Tyler's addon data) |

All three stopped in Swofty's addon-storage swap: `addon storage: <id>: recovery failed ... addon-profiles\<id>\.saved-old
... os error 32 -- still locked after 5 retries`, then `the wrapper exited (exit code: 1) before the game started`.
No loader.log and no session. Cause, workaround and recovery: `docs/upstream/swofty_addon_storage_lock.md`. Fix in the
harness: `tools/storage_sidestep.ps1` and `tools/post_run_check.ps1` (#77). The pilot follows at 00:00.

The test session's own messages ("the game exited before the test agent said hello", "the core never reported the
save sandbox (no sandbox.json)") come after the wrapper's failure. Don't read them as the cause.
