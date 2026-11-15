# Speed checks 4a + 4c: direct start on Swofty 1.9.51, quit at the results (2026-11-14 18:18 PT)

Profile `verve-test` (Skip Cutscenes remove, Offline Quiet), fixture `tyler-profile-20261031`, Austria, 5 laps,
plan `gp_direct_quick.plan`, storage sidestep live, no Defender exclusion. `invalid/attempt1`: 18:12, never launched
(the sidestep call failed on an empty -Addon; fixed in #81).

- **Storage swap passed.** The sidestep moved the 3 empty tyler folders; sandbox confirmed 29 s after launch.
- **Grid fixed (vs 1.8.4).** At +1 s, all 20 cars in grid order over 147 m (about 7.5 m per slot), 80-92 km/h at +3 s.
- **Finished.** 19 classified; FinalClassification arrived. Launch 18:18:34, lights out 18:22:21, results 18:28:12,
  quit 18:28:17: **9.7 min**.
- **But:** a full safety car (SCAR type 1) deployed 3.1 s after lights out, before any collision, back in at 189.5 s,
  so about half the race was under the SC. The AI-driven player car (vehicle 12) was disqualified on lap 5 (PENA
  type 6, infringement 19; from memory of the spec, ignoring tyre regulations). AI difficulty read 19: `test session`
  doesn't apply `ai_difficulty=`.
- gamedb 52 overwritten (Skip Cutscenes and Offline Quiet add none). Saves unchanged. Post-run: one restore for
  Swofty's own cache file, then CLEAN.
- The process trace (summary only; the full trace stays local) shows simplified-helper.exe starting at launch +3 s
  and still running 45 s in.

Verdict: the direct start reaches a real race now, but isn't fit for behaviour batches yet (the early SC, and the
difficulty can't be set). B-0014 stays on the menu route.
