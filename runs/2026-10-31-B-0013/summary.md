# B-0013: is benchmark a procession? (#60)

Benchmark, Austria, clear, 20 cars, 2026-10-31.
- Channels: `LAPTIMES*`, `RESULTS*`, `OVERTAKES`, `RaceResults`, `SESSION-RESULT`, `VEHICLE_COLLISION*`,
  `PENALTY_LOG`.
- Caps: rate 1M/s, repeat 10M, max 10M.
- Analysis: `tools/race_order.py` (sector-line crossing order and gaps from `LAPTIMES`, lap times from `LAPTIMES/V`,
  `RESULTS/V` sampled once per second). The raw logs (204 MB and 120 MB) aren't committed.

## Verdict (criterion fixed on #60 before either run)

**Benchmark is a procession mode.** There was no position change within 5 laps of the strong-arm probe:
- none in `RESULTS/V` (425 one-per-second samples);
- `OVERTAKES` logged 0 lines;
- none at any of the 15 sector lines.

The stock 10-lap run had none in 8 laps either. So behavioural tests need a Grand Prix, which means a save sandbox.

## a: stock, 10 laps requested (`B-0013a`)

- **The game ends benchmark 11 minutes after the start** (08:24:55 to 08:35:55, `StateSession Exiting (benchmark)`),
  part-way into lap 9. So 8 laps were timed, and the test's 200-lap-line assert failed on that (160).
- **Order:** the grid order (`0-8, 19, 9-18`, team order) at all 24 sector lines, with 0 changes. `RESULTS/V`:
  663 samples, 0 changes.
- **Gaps:** the field spreads from 13.6 s (lap 0) to 22.6 s (lap 7), but 10-15 of the 19 car-to-car gaps at the
  line stay under 1.0 s every lap. Median gap 0.67 s, max 5.1 s.
- **Faster cars stuck behind slower ones:** car 10 (Ocon) has the 4th-best lap (78.63 s) and runs 12th all race.
  Car 18 (Russell) has the 9th-best and runs last. Best laps of the whole field (laps 2-8) span only 78.13-79.61 s.
- **Pace is slow:** about 78-81 s laps, slower than the slowest point of the stock difficulty table (74.7 s at
  index 0; 65.5 s at 100). Benchmark either runs its own pace, or the train sets it.

## c: strong-arm probe, 5 laps (`B-0013c`, addon `verve.b0013`)

- **Isolation:** 62 overwritten = 52 + all 10 ops. Vehicles 17 / 18 (Colapinto, Russell): row aggression, speed_in,
  speed_out and control = 1.0. Vehicle 9 (Alonso): speed_in and speed_out = 0.02.
- **Order:** grid order at every sector line. The only gap is car 15's lap-3 crossing, which is missing from the log
  (also the reason for 99 of the 100 lap lines the assert wanted).
- **No effect on pace:**

| Car | Stock laps 2-5 mean | Probe laps 2-5 mean |
|---|---|---|
| 9 Alonso (speed_in/out 0.02) | 79.83 s | 80.13 s |
| 17 Colapinto (maxed) | 80.59 s | 80.77 s |
| 18 Russell (maxed) | 80.52 s | 80.77 s |
| field neighbours (8, 10, 16, 19) | 79.6-80.9 s | about +0.3 s, the same shift |

  The maxed cars ran 0.3-0.8 s behind the car ahead every lap and never passed. Alonso at near-zero corner speed held
  his place and his pace.

## Verification (Tyler asked whether overtakes are measured correctly)

- **`RESULTS/V` is excluded.** It is not live: its Lap field stays 0 all race and its blocks are labelled
  `ePreLoaded`. Its "0 changes" are not evidence. An empty `OVERTAKES` channel isn't evidence either.
- **The `LAPTIMES` crossing order, checked independently on B-0013a:**
  - The wall-clock arrival order of the "Added sector" lines equals the session-time order at 24 of 24 lines.
  - Each Sector Time equals the difference between consecutive session times: 0 mismatches in 478.
  - Every vehicle id keeps one driver name across all its lines. So even if the ids were position slots, a pass
    would have changed a name, and none did.
- **Ground truth from the screen** (`visual/`). A 3-lap stock benchmark (08:48, PASS) with `tools/window_frames.ps1`
  every 3 s. The broadcast camera follows vehicle 19 (Leclerc, the player car, as B-0003 suspected). Its timing tower
  on laps 1, 2 and 3 shows Antonelli P8, Hamilton P9, Leclerc P10, Alonso P11, Ocon P12, with sub-second gaps. That
  is the log's order (vehicles 7, 8, 19, 9, 10 at 8th-12th; `visual/crossings_visual_run.csv`), unchanged every lap.
  The log also shows 0 order changes for this race.

## Implications

1. Per-driver lap times in benchmark measure the train, not driver pace. The pace / consistency batch (b) isn't
   meaningful here.
2. These row characteristics (aggression, speed_in, speed_out, control) show no visible effect on lap pace or order in
   benchmark, even at extremes. Benchmark may ignore them for driving (it does read `race_start` and the start
   rows: F-39, B-0005), or the train masks them. Benchmark alone can't tell which.
3. Behavioural measurement needs a real race session. With Tyler's saves ruled out, that means a save sandbox: the
   career-fixture route (Swofty's `career` env and `test shell --fixture`). That moves to the top of the list.
4. What benchmark still offers: race starts (F-39 work), the vehicle-to-driver map, and checks that a build applies.
