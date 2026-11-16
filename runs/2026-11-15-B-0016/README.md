# B-0016: stock vs swofty.lap1-ai (Lap 1 Realistic AI 1.0.0), lap-1 race feel (#101)

Menu Grand Prix (`harness/sessions/gp_menu_full_skip.plan`), Austria, 5 laps, 2025 season, Stroll (car 19) driven
by the AI, difficulty 100, profile verve-test. Odd races = A (stock), even = B (+swofty.lap1-ai). Run 2026-11-15
08:00-21:30 PT (extended window), tools/b0016_run.ps1; validity and score by tools/b0016_check.py.
N = 20 (10 + 10), set at 11:58 PT by the supervisor on time available only, before any metric was looked at (#101).

## Validity
20 of 20 valid. Reruns in their slots, kept in `invalid/` and not scored:
- race_3_1: the intro skipped 3 of 3 attempts and the UDP capture was lost (the unscoped stop fixed in #108).
- race_3_2: the menu route missed the solo screen (`@expect solo_container`).
- race_12_1, race_15_1: PAUSE (Tyler, 12:19 and 14:29 PT).
Every B race has 82-85 lap1-ai lines in loader.log, every A race none. gamedb 52 in every race. Every post-run check
CLEAN, saves unchanged. Race 2's saves check ran late (deferred; "CHANGED, Tyler played in between", only his own
session's files).

## Result (registered rules, #101 v3): INCONCLUSIVE
`score.txt` has the full output.
- P3, lap-1 held changes (net) per race, B - A: **+1.30**, bootstrap SE 1.73, 2-SE interval [-2.16, +4.76].
  It includes 0, so it's not a PASS; and it reaches past +4, so it's not FAIL-NULL either.
- Guard, lap-1 costly contacts: +0.30 (SE 0.25): not a cost.
- Co-primaries (outside the verdict): lap-1 loss median -0.82 s (2-SE [-1.80, +0.15]); lap-1 spread -0.36 s
  (2-SE [-1.80, +1.09]).

## Weather (found after scoring; not in the registered rules)
Grand Prix weather was random. From the session packets (weather byte): races 7 and 9 (A) ran in storm (5) and
race 11 (A) in light rain (3). Every B race and the other 7 A races were dry (clear, light cloud or overcast). So all
3 wet races fell in the stock arm. That shows in the secondaries: median green lap B - A -2.98 s, and
early_brakes_total, where the wet races are at 5-13 against 19-39.

**Sensitivity, not scored: dry races only (A 7, B 10).** P3 B - A **+0.06** (SE 1.97). P1 -0.39 s (SE 0.47). P2
-0.31 s (SE 0.72). Costly contacts +0.21 (SE 0.28). early_brakes -1.0 (SE 2.5). Median green lap +0.12 s (SE 0.16).
On dry races, lap1-ai shows no sign of more lap-1 held changes. The registered +1.30 comes mostly from the 3 wet A
races (P3 14, 19, 15).

## Harness notes
- After every race, the test shell waited the full 120 s after `quit` for stdin EOF and was then stopped (by recorded
  PID). Fixed by #111, which merges before B-0015.
- 08:31:59: the race-2 runner killed Tyler's game by name. See `docs/incidents/2026-11-15-killed-tyler-game.md`.
