# B-0018: the stock baseline on the spectator garage route (Hungary, dry), 10 races (#120)

16 Nov 2026, 09:34-13:19 PT. The Verve Drivers stock baseline (scope narrowed 2026-11-16).
- **Setup:** verve-test stock plus kizi.spectator-hud 0.1.11 (garage start) and msyeett.starting-grid 0.1.4 (Custom grid,
  player last), on launcher 1.9.59 and build 26566308.
- **Race:** Hungary, difficulty 100, 5 laps, Quick Weather Clear (Dry).
- **Plans:** race 1 ran on `gp_menu_full_press_dry_hungary_grid.plan` (fixed end); races 2-10 on `…_grid_ai.plan`
  (`@udpfinish`).
- **Checks:** `tools/aionly_check.py` validity (#138). race_feel at `481d0b9` (#140 per-car finish window), re-run on every
  race's kept capture at the batch end (`race_N/race_feel_version.txt`).

## Validity
**10 of 10 valid, aionly PASS each:**
- 19 AI cars finished by LapData every race, with the live window at ratio 1.000 and a max gap of about 0.03 s.
- Weather LOCKED (#118 ≤ 5 rule) every race, gamedb 56, saves unchanged, guard clean.
- SCAR 0 in every race. No player COLL or PENA; the car was parked about 4 s before lights out.

**Invalid attempts, all skipped intros** (the shell relaunched, then the runner retried after 300 s; none started a
race): race_4_1, race_5_1, race_5_2, race_5_3, race_6_1, race_7_1, race_8_1, race_9_1 and race_10_1, in `invalid/`.
Every retry 300 s after a skip played its intro; that's the basis for the relaunch cool-down, #144.

## Per race (race_feel summary; descriptive, no hypothesis)
| Race | Net held passes, laps 2+ | Train share | Longest train | Lap-1 loss median (s) | Lap-1 spread (s) | Phantom brakes |
|---|---|---|---|---|---|---|
| 1 | 2 | 0.883 | 18 | 7.53 | 7.73 | 0 |
| 2 | 2 | 0.832 | 19 | 7.47 | 6.94 | 0 |
| 3 | 0 | 0.775 | 19 | 7.34 | 7.32 | 0 |
| 4 | 4 | 0.791 | 19 | 7.26 | 6.55 | 0 |
| 5 | 1 | 0.789 | 19 | 7.15 | 6.92 | 1 |
| 6 | 0 | 0.871 | 19 | 7.40 | 6.76 | 1 |
| 7 | 2 | 0.834 | 19 | 6.81 | 7.00 | 0 |
| 8 | 2 | 0.789 | 19 | 7.26 | 6.95 | 0 |
| 9 | 5 | 0.746 | 18 | 8.03 | 8.17 | 1 |
| 10 | 6 | 0.818 | 19 | 7.27 | 6.37 | 0 |

- **Net held passes by lap (all 10 races):** lap 1: 91, lap 2: 7, lap 3: 6, lap 4: 9, lap 5: 2. So 13 of the 24 on
  laps 2+ (54%) come on laps 2-3.
- **The grid** (UDP, every race) is in each `race_N/aionly.txt`. The 19 AI cars' order varies per session; the player is
  always 20th.
- Full numbers: `batch_end.json`, `race_N/race_feel/`.

`tools/b0018_check.py`'s validity predates the spectator route (gamedb 52, a FinalClassification), so validity here is
`aionly_check`'s, as #120's amendment set.
