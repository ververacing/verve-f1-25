# udp_tt run 5: stopped at boot by a "save data corrupted" dialog (incident)

2026-10-31 07:38. At boot F1 25 found the profile save corrupt and wrote `corrupt_saves#<steamid>.zip`
(`saves_changes.csv`: the only change). The test and the game were killed before any pad step could answer the
dialog. The guard's Restore refused to run while the game was up (exit 4), as designed. No session and no UDP data.

Cause: the game read the restored profile save truncated, to the size Steam had recorded for the game's own write in
udp-tt-3. Resolved at 08:05 by a Steam restart and a clean boot. Timeline, evidence and the ruling are in
`docs/harness.md`, under "Incident 2026-10-31". Route tests stay off Tyler's saves.
