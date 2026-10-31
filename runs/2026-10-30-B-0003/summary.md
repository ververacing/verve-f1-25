# B-0003: stock reaction-time baseline, benchmark Austria (#33)

Vanilla, `harness/tests/b0003.test.json`: 5 fresh game starts, benchmark Austria, 3 laps, 20 cars, clear. Start 5
also set `grid_pos: 1`. 18:37–19:03 on 2026-10-30, all 5 PASS, unattended. Raw report in `raw/` (not committed);
`racestarts_<n>.log` holds each start's RaceStarts lines; tables are from `tools/racestarts_summary.ps1`.

## Isolation

Every start: `gamedb: 52 overwritten, 322 created, 0 retyped, 0 skipped`, the vanilla baseline from swofty.core +
the always-on teamsimplified.mods, identical to the vanilla smoke runs. No Verve edits applied
(`isolation.csv`). The settings line says "3 addon(s)" because it counts installed addons, and the sample Verve
addon was still installed (not enabled); see `docs/harness.md`.

## Results

`summary.csv` (100 rows: start, vehicle, team_id, reaction_time, race_start_performance), `per_vehicle.csv`,
`per_start.csv`.

- **Vehicle 19 (team 1, Ferrari) is special.** Per start: 0.055, 0.218, 0.201, 0.054, 0.095 s (and 0.109 / 0.095 in
  the two smoke runs), so it was the fastest car in 5 of 7 stock starts, by ~0.1 s. **No other car ever went
  below 0.171 s.** The other Ferrari (vehicle 8) has median 0.207, the second lowest.
- **`grid_pos: 1` changed nothing visible:** same entrant order (`teams 2,3,8,4,3,2,9,0,1,4,7,6,8,9,6,7,5,5,0,1`) in
  all 5 starts, and vehicle 19 was still the fastest. So whether vehicle 19 is the player car is **not settled**:
  UDP sent nothing (below), and grid_pos had no observable effect. Keep Ferrari and vehicle 19 out of every arm
  and every field statistic.
- **Per-start level** (field without vehicle 19): mean 0.249, 0.254, 0.265, 0.248, 0.254 s; within-start SD
  0.036–0.058 s. The level moves by up to ~0.017 s between starts, so arms are compared with the same start's field.
- **Per-vehicle medians** (5 starts, vehicle 19 excluded): 0.180 (vehicle 4, Williams) to 0.285 (vehicle 18,
  Mercedes). With ~5 samples each, those differences are near the noise (SE of a 5-sample median ≈ 0.025 s).
- **Power for B-0001:** 2 cars × 5 starts = 10 samples per arm, SE of the arm median ≈ 0.018 s, against a predicted
  ~0.2 s gap between the arms of the winning pair. Comfortable.
- **The formula doesn't fit the stock field.** With stock reaction_speed 0.6–1.0, F-06's U[0.28 − 0.24r, 0.42 − 0.18r]
  predicts values down to ~0.04–0.14 s, but the field never went below 0.171 s. Either k < 1 in benchmark, or the
  formula's bounds are off. Read B-0001 by ordering, as planned. Vehicle 19's values do fit U[0.04, 0.24].

## UDP check (supervisor's #4 question)

`tools/udp_capture.py` listened on 127.0.0.1:20777 for the whole batch, with `<udp enabled="true" ...>` set (and kept
by the game when it rewrote the file at 18:58): **0 packets**. Benchmark mode, or the offline launch, sends no UDP
telemetry. So no Participants packet, no playerCarIndex, and B-0001 stays on per-team arms. Checking UDP in a
normal (non-benchmark) session needs a Time Trial or Grand Prix reached by pad steps; that is #4 work.
