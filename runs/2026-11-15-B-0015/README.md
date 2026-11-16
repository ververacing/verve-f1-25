# B-0015: per-driver blocking.max_blocking_distance 45 vs 5, within-driver crossover (#100, v4)

Menu Grand Prix (`harness/sessions/gp_menu_full_skip.plan`), Austria, 5 laps, 2025 season, Stroll (car 19) driven
by the AI, difficulty 100, profile verve-test. G1 = Sainz, Bortoleto, Hadjar, Bearman; G2 = Albon, Russell,
Hulkenberg, Gasly. Odd races = order a (verve.b0015a: G1 45, G2 5), even = order b (verve.b0015b: swapped). The
`_at_race_start` key stays stock (18). Run 2026-11-15 21:40 to 2026-11-16 04:31 PT, tools/b0015_run.ps1; validity
and score by tools/b0015_check.py. N = 20 (the registered maximum), with no interim look at any metric.

## Validity
20 of 20 valid. Arm proof: 4 keys at 45 in order a and 5 in order b, 4 the reverse. gamedb 60 in every race. Every
race dry: weather.txt, the rule added on #100 before race 1. Every post-run check CLEAN, saves unchanged.
Reruns in their slots, kept in `invalid/` and not scored:
- race_2_1: PAUSE (Tyler, 21:55 PT).
- race_5_1, race_14_1, race_15_1, race_19_1: "weather" (rain in the race session; 4 of 24 attempts).

Harness: #111's stdin fix held in every race (the shell ends on its own about 12 s after quit; no stop needed). From
race 2, #115 recorded the game at launch from sandbox.json and recorded the shell's exit.

## Result (registered rules, #100 v4): INCONCLUSIVE
`score.txt` has the full output.
- Primary, train_s_behind_net per driver-race, condition coefficient (45 - 5): **-18.7 s**, bootstrap SE 17.0,
  2-SE [-52.8, +15.3]; within-driver mean -21.2 s.
  The prediction was positive (more train time behind a driver who defends from far). The estimate is negative but not
  significant, so it isn't a PASS. The interval reaches past -40 s, so it isn't FAIL-NULL either.
- Cost check: costly contacts +0.013 (SE 0.027), no cost.
- Secondaries (2-SE intervals, report only):
  - held_suffered_net_2plus -0.05 [-0.25, +0.15]. That lies inside v3's +-0.3 band, but v3 isn't the scored rule.
  - train_s_behind -15.5 [-45.7, +14.7]
  - held_passes_net_2plus -0.13 [-0.34, +0.09]
  - net position -0.03 [-0.52, +0.47]
  - lap-1 position change +0.05 [-0.17, +0.27] (about 0, as expected: lap 1 untouched)
  - collisions -0.11 [-0.42, +0.20]
  - penalties 0; DNFs 0
- Sensitivity at 5 s / 20 s hold windows: not computed (not scored).

Reading: at Austria, a per-driver max_blocking_distance of 45 vs 5 shows no detectable change in how often those
drivers are passed or how long cars queue behind them. The point estimates lean the opposite way to the prediction
(slightly less train time at 45).
