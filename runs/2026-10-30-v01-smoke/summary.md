# 2026-10-30 v0.1 smoke build (issue #2)

The sample addon (`verve-f1-addon/`, 23 drivers, 232 ops, illustrative numbers only) with the label fixes from this
PR. Smoke only, no tuning.

## Build (`swofty build --profile verve-smoke`)

Exit 0. `profile verve-smoke: swofty.core -> teamsimplified.mods -> verve.driver-profiles`,
`Verve Driver Profiles: 232 database values`, **0 "no such key", 0 "no row matches"**.
(`teamsimplified.mods` is "always on" and can't be disabled per profile; its Grid Editor made 0 changes.)

The first build failed on `DriverStatisticsHolder[driver=alexander_albon]: no row matches`: the holder's
`_metadata_` is `alexander_albon`, but its `driver` field, which the selector matches, is `alex_albon`. So F-32 was
half wrong. Antonelli's row label really was `andrea-kimi_antonelli`, but Albon's stats selector was right as it was.
The same goes for the other misspelt holders (`micheal_schumacher` → driver `michael_schumacher`, `aryton_senna` →
`ayrton_senna`, `nilola_tsolov` → `nikola_tsolov`, `john_benneet` → `john_bennett`).

## In game (`harness/tests/v01_smoke.test.json`, benchmark Austria 3 laps)

**PASS** (4 min 53 s, no crash, 20 RaceStarts lines). The edits apply at database load:
`gamedb: ... applying 602 edit(s)` → `280 overwritten, 322 created, 0 retyped, 0 skipped`. The 322 created are
Swofty core's add-row copies (39 + 283 keys); 0 skipped means every Verve `set` found its key. `racestarts.log` holds
the RaceStarts lines and the gamedb summary. The game folder was rolled back afterwards (`drift: swofty is not part of
the game`).

**Not verified:** the addon appearing in the in-game ADDON SETTINGS menu. The log shows `ADDON SETTINGS mixin: active`,
but the harness can't capture frames yet, and this addon has no options to show.

## Harness notes

- Reinstalling an addon over an existing install (`swofty addons install` on the same id) fails on this PC with "files
  are still in use", and leaves the installed copy half-deleted. A fresh install works: delete
  `%LOCALAPPDATA%\Swofty\addons\verve.driver-profiles` (and any `.installing-*` folder) first.
- The test runner again couldn't delete its throwaway profile (`cache/overlay/test-…` locked), even with the Launcher
  window closed, so the lock is something else (Defender or the search indexer).
