# Log-channel probe: what a benchmark race logs about laps, positions and contacts (#4)

One stock benchmark start: Austria, 3 laps, 20 cars, clear, no Verve addon, `harness/tests/smoke.test.json`, PASS
(4 m 53 s). 2026-10-31 08:15, after Tyler OK'd benchmark races again. Channels:
`default,RaceStarts:info,...,LAPTIMES*:info,LEADERBOARD*:info,OVERTAKES:info,SESSION-RESULT:info,RaceResults:info,
RESULTS*:info,PENALTY_LOG:info,VEHICLE_COLLISION*:info,TIMINGBOARDS:info,POST_RACE:info,DRIVERMOVES*:info,PITSTOPS:info`.
Caps raised: `SWOFTY_GAME_LOG_RATE=100000`, `_REPEAT=100000`, `_MAX=1000000`. `loader.log` was 55.7 MB; the raw file
isn't committed.

## Lines per channel

| Channel | Lines | What it gives |
|---|---|---|
| `RESULTS/V` | 215,623 | `Position - P, Vehicle Id - V, Status - S, Lap - L, Progress x, Time - t`, a full 20-car block many times a second. Stopped at 08:17:39 (end of lap 1): the 100,000-per-format repeat cap. |
| `RaceResults` | 8,830 | ruleset setup and the end-of-race sort (`N. vehicle`) |
| `LEADERBOARDS` | 4,925 | leaderboard definitions loaded at boot (no race data) |
| `VEHICLE_COLLISION_WORLD` (+`_DETAIL`) | 2,064 each | `Car to world <ptr> <ptr>, time t`: car-to-wall contacts, by object pointer, not vehicle id |
| `LAPTIMES` | 785 | `onVehicleNewSector() - v(16, Pierre GASLY), s(0)` and `Added sector S, on lap L, to vehicle V, ... session time T, Sector Time x` |
| `SESSION-RESULT` | 360 | per-vehicle encoded result: progress, status, time, fastest lap |
| `TIMINGBOARDS` | 160 | trackside board animations (no data) |
| `LAPTIMES/V` | 60 | `Reporting NEW LAP TIME (n) for vehicle Ix V (time +x s)`: 20 cars x 3 laps |
| `PITSTOPS` | 20 | pit crew to team assignment |
| `OVERTAKES`, `PENALTY_LOG`, `LEADERBOARD`, `POST_RACE`, `DRIVERMOVES` | 0 | nothing logged in this race |

## Findings

1. **Vehicle id to driver, from the log itself.** `LAPTIMES` names all 20 cars: 0 Tsunoda, 1 Albon, 2 Piastri,
   3 Stroll, 4 Sainz, 5 Verstappen, 6 Bortoleto, 7 Antonelli, 8 Hamilton, 9 Alonso, 10 Ocon, 11 Lawson, 12 Norris,
   13 Hulkenberg, 14 Hadjar, 15 Bearman, 16 Gasly, 17 Colapinto, 18 Russell, 19 Leclerc. That closes gap 1
   (vehicle id to driver) for benchmark, with no UDP. It replaces the team-order inference and B-0005's tags.
2. **Per-car lap and sector times.** 60 lap times and 180 sector records, each by named car. Lap 1: 81.18 to 92.78 s.
   Lap 2: 79.09 to 82.22 s. Lap 3: 77.74 to 79.91 s. Vehicle 0 was fastest on every lap.
3. **The race was a procession.** The line-crossing order (from sector-2 session times) was the starting order on
   every lap: `0-8, 19, 9-18`. `RESULTS/V` positions never changed, and sorting by its Progress field gives the same
   order. `OVERTAKES` logged nothing. So no overtakes happened in this 3-lap benchmark, and positions can't measure
   behaviour here as it stands. The final `RESULTS/V` block and `RaceResults`' sorted list show lap 0 and time 0 in
   the starting order, which looks like a post-race reset rather than a classification.
4. **Contacts** are logged only as car-to-world, by object pointer. No car-to-car line appeared, so contact can't be
   attributed to a driver from these channels yet.

## What this means for benchmark behaviour batches

- Lap pace and consistency per named driver: **available now**, from `LAPTIMES` / `LAPTIMES/V`.
- Overtakes and position changes: **none to measure** in a 3-lap stock benchmark. Next steps: longer races (e.g. 10
  laps), or arms that change pace or aggression enough to break the train.
- For `RESULTS/V`, raise `SWOFTY_GAME_LOG_REPEAT` above 100,000 (or drop that channel). The other channels are far
  below the cap.
