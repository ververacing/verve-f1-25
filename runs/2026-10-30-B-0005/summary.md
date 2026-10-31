# B-0005: vehicle id → driver map via race_start tags, benchmark Austria (#37)

Addon `harness/addons/verve.b0005` (40 ops): all four `ai_driver_config.race_start` reaction bounds set to 0.65 on one
driver per team (random, seed 5005, `tags.csv`), Ferrari included. `harness/tests/b0005.test.json`: 2 fresh starts,
benchmark Austria, 3 laps, 20 cars, clear. 2026-10-30, both PASS.

## Isolation

Both starts: **92 overwritten** (52 + 40), 322 created, 0 skipped.

## Result: hypothesis **A** for 9 of 10 teams. `ai_driver_config.race_start` is read **per driver**

| Start | Cars at ≥ 0.40 s |
|---|---|
| 1 | vehicles 2, 4, 5, 6, 9, 10, 11, 16, 18, **each at exactly 0.650000** |
| 2 | the same nine vehicles, each at exactly 0.650000 |

- One car per team for 9 teams, the same vehicles in both starts, and the value is exactly the tag (all bounds
  equal → no random draw). The untagged teammates stayed stock (0.198–0.345 s). So the four race_start bounds are
  read from the driver row, per driver, and they set the reaction directly. That's the first direct test of a v0.2
  A-rated key, and part of Q-08 (these keys are per driver, not per car).
- **Ferrari is the exception.** Charles Leclerc was tagged, but neither Ferrari car showed 0.65: vehicle 8 0.335 / 0.319
  (stock-like), **vehicle 19 0.054 / 0.050** (its usual fast start). So the tagged Leclerc car is the one that
  ignored its race_start bounds, and that can only be **vehicle 19 = Leclerc**, with vehicle 8 = Hamilton. Vehicle 19
  takes a different start path that ignores `ai_driver_config.race_start`, consistent with it being the **player
  car** (AI-driven in benchmark). Inferred, not directly observed.
- Pass criterion from #37: "A: exactly 10 cars in 0.60–0.70 s". We got 9 + the Ferrari exception, so strictly
  **"C: anything else, report as is"**; the nine-team pattern plus the vehicle-19 explanation is the reading.

## The map

`docs/stock/vehicle_map_benchmark_austria.csv` (vehicle, team_id, team, driver, evidence): 9 cars identified
directly, 9 teammates by elimination, the two Ferraris by the inference above. Team ids match the session trace's
team list for all 20 vehicles, which confirms "vehicle id *i* = trace entry *i*" (harness finding 3). Holds for
benchmark Austria with the f1_2025 entrant list only.

## Consequences

- Later batches can use **per-driver arms** (B-0006, #39, is the first).
- v0.2a's race_start bounds (#10) work per driver, and a bound that equals the others pins the reaction exactly.
- Vehicle 19 / Leclerc stays out of every arm and field statistic: it ignores at least the race_start config.
