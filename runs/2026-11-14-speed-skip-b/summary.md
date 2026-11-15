# Speed check 4b: Skip Cutscenes (remove) in a menu Grand Prix (2026-11-14 18:33 PT)

The B-0014 Amendment 4 plan as a stock rehearsal (`gp_menu_skip_check.plan`), profile `verve-test`, fixture
`tyler-profile-20261031`. `invalid/attempt1`: 18:30, never launched (empty -Addon in the storage-check call; fixed in #82).

- loader.log: `grid rundown: removing`, `grid: removing` (the grid cutscene ran to its end, then the pre-race menu),
  `winner sequence: removing`, `doughnuts celebration: removing`. Intro video and track intro cameras removed.
  Nothing got stuck. The podium wasn't reached: A on the results screen doesn't move on.
- Difficulty 100 read back, player car 19, FinalClassification x10. gamedb 52 overwritten.
- Launch 18:33:09, Start Event 18:37:27, grid 18:40:05, lights out 18:40:18 (7.1 min), results 18:47:31, quit 18:48:19:
  **15.2 min** per race (B-0014's runner budgets 17).
- The sidestep found nothing to move (the tyler folders weren't re-created after the pilot); the swap passed.
  Saves unchanged; post-run CLEAN after the cache-file restore.
