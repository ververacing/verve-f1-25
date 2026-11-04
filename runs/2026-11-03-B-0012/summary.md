# B-0012: race_start tags in a direct-start Grand Prix (#57)

**Result: PASS, 5 of 5 starts, none invalid.** Per-driver `race_start` is read in the direct-start state. Q-02 stays open for a normal Grand Prix, because no race has run properly on this route yet (#64).

Austria, `f1_2025`, Stroll as the player (`team=forceindia driver=stroll`). Addon `harness/addons/verve.b0012`: all four `race_start` reaction bounds at 0.65 on 9 drivers from 9 teams, B-0005's set minus Alonso. Profile: swofty.core, teamsimplified.mods and this addon. Fixture `tyler-profile-20261031`. Run in the save sandbox, 2026-11-03. The criterion and setup were recorded on #57 before any data.

## Results

Scored by `tools/b0012_check.py` on the first 20 reaction lines after lights out.

| Start | First block | Cars at 0.650 | Untagged at 0.650 | gamedb | Player vehicle | Leclerc vehicle | Result |
|---|---|---|---|---|---|---|---|
| 1 | 20 of 20 vehicles | 9 | 0 | 88 / 322 | 7 | 10 | PASS |
| 2 | 20 of 20 | 9 | 0 | 88 / 322 | 17 | 1 | PASS |
| 3 | 20 of 20 | 9 | 0 | 88 / 322 | 2 | 15 | PASS |
| 4 | 20 of 20 | 9 | 0 | 88 / 322 | 14 | 1 | PASS |
| 5 | 20 of 20 | 9 | 0 | 88 / 322 | 6 | 11 | PASS |

**All logged re-rolls, reported as the supervisor asked, not scored:** 300 lines in total. Tagged cars have 133 lines, and **none is off 0.650**. No untagged line is at 0.650. The log's rate limit cuts these off, so they're a large sample, not every roll.

Tyler's saves and Steam's records were unchanged on all 5 starts, and matched the last-known-good snapshot afterwards.

## What this shows

- **`ai_driver_config.race_start` is read per driver in this state**, and sets the reaction directly (all bounds equal, so there's no random draw).
- **The join is a real test.** Vehicle numbers shuffle every start here (Leclerc was 10, 1, 15, 1, 11), unlike benchmark's fixed order. The tagged cars moved with their drivers each time. A log with no join couldn't have shown this.
- **The game-database count matched its prediction exactly:** 88 = 52 + 36, so all 36 ops applied and nothing else wrote records.
- **Leclerc obeys his tag here.** In B-0005 he was the benchmark's player car and ignored it. So his row isn't special: what mattered there was being the player car.

## What it doesn't show

- **A normal Grand Prix.** No grid forms and no car launches in this state (#64), and the draws re-roll every 30-50 ms, unlike benchmark's single draw. This is the game's start code reading the driver's row, in a broken race. Q-02 needs a race that runs.
- **Anything about behaviour.** There are no launches to measure, so this says nothing about how a 0.650 reaction plays out on track.

## Side notes

- **The player car isn't consistently fast here.** Untagged Stroll drew 0.100, 0.159, 0.225, 0.061 and 0.147, unlike benchmark's player at about 0.05 every time. PR #68's note that the player's path looked the same was over-reading one sample. Stroll wasn't tagged, so this batch can't say whether the player car would obey a tag here.
- **Launch to green:** about 3 min 43 s. Starts ran about 4 min 40 s apart, so about 13 an hour.
