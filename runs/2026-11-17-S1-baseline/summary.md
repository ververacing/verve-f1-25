# S-1 stock baseline, GP Austria (spectator route): 8/8 races valid, bands proposed

Pre-registered in [docs/verve_s1_prereg.md](../../docs/verve_s1_prereg.md) §3 (#181), scored with
`python -I tools/s1_check.py runs/2026-11-17-S1-baseline --baseline` (#182). 2 launches × 4 races, 5 laps, stock, with no
add-on (`v1_run -StockSmoke`, `v1_austria_4races.plan`, `-LaunchMinutes 80`). Launcher 1.9.63, game build 26566308.

| Launch | Time (PT) | Valid races | Build check | Display fallback |
|---|---|---|---|---|
| 1 | 06:46-07:20 | 4 / 4 | 0 ops, gamedb 56 = 56 + 0 | yes, resolution only, auto-restored |
| 2 | 07:29-08:04 | 4 / 4 | 0 ops, gamedb 56 = 56 + 0 | yes, resolution only, auto-restored |

- **Validity:** aionly_check per uid passed for all 8 races. 19/19 AI cars finished every race, with no stalls and 0 SCAR.
- **Safety:** tyler.json hash as before the run (no add-on), saves unchanged (179), guard 0, session check ok
  (difficulty 100, track 17, weather 0), weather LOCKED, in both launches.
- **Display fallback:** at each launch's end, the live settings differed from the reference only in resolution
  (1920x1080 -> 1024x768). `hw_display_restore` kept an evidence copy and restored the setting before SAFE TO PLAY
  (#168). Validity isn't affected. Cause: a desk check is pending (supervisor, 2026-11-17).
- **Records:** save-file names in `cleanup.txt` are written as save#1 / save#2.

## Statistics and the proposed bands (`s1_bands_proposed.json`, committed as `docs/stock/s1_bands.json`)

| Statistic | Value | V-1-based expectation |
|---|---|---|
| M_p | 0.651 | 0.98 |
| M_h | 173 s | 142.7 s |
| M_c | 0.645 | 0.583 |
| exit_all_kph mean | 0.165 | about 0 |
| C_race | 6.12 COLL/race (per race 8, 4, 4, 7, 7, 6, 6, 7) | |

| Band | contacts | exit_all_kph | passes_made | held_behind_s |
|---|---|---|---|---|
| Half-width | 0.161 | 2.0 km/h | 0.163 | 43.2 s |
