# Grid Editor discovery (#131): the player car last, on build 26566308

16 Nov 2026, 08:33-08:41 PT. One stock session with no race, on `gp_menu_weather_discovery.plan` (Austria) with
**msyeett.starting-grid 0.1.4** enabled in verve-test (catalog download, sha256 matched; see #132). Launcher 1.9.59
(`race_1/launcher.txt`). Frames went to the agent's scratchpad, not the repo.

**Session:** the plan ran to the end. Saves unchanged (34), guard 0, post-run CLEAN. `starting_grid.dll` loaded at the
window stage. gamedb: **56 overwritten** (52 stock + 4 from Starting Grid's database part), 322 created.

## Found
1. **Weekend Structure:** on the settings hub, down from Difficulty is the Weekend Structure tile. Its rows are
   Weekend Structure (Standard), Practice Format (Off), **Qualifying Format (Off)**, Session Length (Very Short),
   **Starting Grid (Realistic)** and **Grid Editor**. So the add-on's setting applies (it needs Qualifying Off).
2. **Grid Editor:** five down from the top row, then A. The player, Lance Stroll, is P1 with the cursor on him.
   **X ("Move Player Down") moves him down one**, and every other car keeps its relative order. After 19 presses he's
   P20 of 20 and the "Move Player Down" prompt disappears.
3. **The AI order (P1-P19)** that results is the game's list with each car moved up one:

   Sainz, Tsunoda, Russell, Lawson, Bearman, Verstappen, Hamilton, Hadjar, Ocon, Alonso, Colapinto, Piastri,
   Bortoleto, Albon, Hülkenberg, Leclerc, Norris, Antonelli, Gasly. Stroll is P20.

   That isn't performance order. Whether the "Realistic" starting list is the same every session isn't known yet. The
   #131 race's UDP grid order will show it.
4. **Back to the hub:** B gives a **Confirm Changes** dialog (A confirms), then the Weekend Structure screen shows
   **Starting Grid: Custom Grid**. B again is the hub with the cursor on Weekend Structure, and up is Difficulty
   (seen on screen).

Plan from this: `harness/sessions/gp_menu_full_press_dry_hungary_grid.plan`. It's the Hungary dry plan, with these
steps between Difficulty 100 and the weather lock.
