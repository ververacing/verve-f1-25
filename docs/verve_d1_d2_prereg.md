# D1 and D2 pre-registration: do the per-driver rows reach the AI on 26566308?

Status: **DRAFT for the supervisor's approval** (2026-11-17). Nothing runs until it's approved.

**Why.** V-1 (#160, #169; F-48) found reaction_speed DEAD in GP on 26566308 (FE slope −0.006 s). B-0006 and B-0008 found
about −0.11 s per unit for the same row write in benchmark on 25251167. V-1 can't tell (H1) "the overrides reach the AI
but don't matter in GP on this build" from (H2) "they never reach the per-car AI record on this route or build". D1
checks the measurement chain and the per-driver `ai_driver_config` path in GP. D2 checks the row path in benchmark,
the mode where it once worked. D3, a readback of the effective per-car values, is written up separately before
anything is built for it.

Both run on launcher **1.9.63**, after its stock route check (`runs/2026-11-17-routecheck-1.9.63`) passes. They use
profile verve-test only, and the reaction measure is V-1's UDP definition: the LGOT arrival to the first LapData
totalDistance gain ≥ 0.3 m (`MOVE_M`), 60 Hz, relative only.

## D1: positive control in GP (spectator route, Austria)

- **Lever:** B-0012b's. All four `ai_driver_config.race_start` reaction bounds are pinned to **0.65 s**:
  `min_reaction_time_lower_bound`, `min_reaction_time_upper_bound`, `max_reaction_time_lower_bound` and
  `max_reaction_time_upper_bound`. In GP on 25251167 (B-0012b, 5/5) each pinned car drew exactly 0.650. No other
  writes: no traits, no maps, no bundles.
- **Assignment:** in each of the 9 two-AI teams, a seeded coin flip pins one teammate and leaves the other stock.
  Alonso (no AI teammate) stays stock. That gives 9 pinned and 10 stock cars per launch, with a new draw per launch.
  The seed is fixed when this is approved, and the assignment is recorded (`assignment.csv`).
- **Size:** 2 launches × 4 races, 5 laps (V-1's plan `v1_austria_4races.plan`, with the race-1 session check). That's
  about 70 min.
- **Validity:** as V-1: aionly_check per race uid, the session check, the per-launch build check (check_applied: all
  36 ops applied), weather LOCKED and the saves guard.
- **Primary (per launch):** the mean UDP reaction of the pinned cars minus that of the stock cars, over the launch's
  valid races (a car's mean over its races, then the mean over cars).
- **PASS:** the difference is **≥ 0.12 s in both launches** (the supervisor's threshold). That's conservative: pinning
  to 0.65 s against a stock draw of about 0.28-0.42 s should give about +0.25-0.35 s.
- **FAIL:** < 0.12 s in either launch (two readings in the outcome table below).
- **Secondaries, not scored** (B-0012b's exploratory signal): speed at 1 s after lights out, and positions gained to T1
  (`T1_M` 345 m), for the pinned cars against the stock cars.
- **Tooling to build (for review, before D1 runs):** `tools/d1_make.py` (the seeded teammate draw plus the add-on
  `verve.d1-l<LL>`, 36 ops), and a `-Make` switch on `tools/v1_run.ps1` to use it instead of v1_make (same install,
  enable, remove, hash, build and session checks). The check_applied key cache gets the 76 race_start paths, from
  read-only `db get --profile verve-test` calls with nothing running.

## D2: benchmark replication of B-0008 on 26566308

- **D2.0, a feasibility probe first** (1 start, stock, no add-on, not scored). B-0008's tests waited on the
  `RaceStarts: Reaction Time…` log line, which is gone on 26566308 (Swofty ships no `log_channels.tsv` for this build). The probe runs
  B-0008's env (`swofty test`, `kind: benchmark`, Austria, 3 laps, 20 cars, clear, fresh) with the UDP capture on.
  It records:
  - whether the benchmark boots and ends on 26566308;
  - which log or session-trace line marks the start and the end;
  - whether UDP LapData and an LGOT event arrive;
  - the vehicle → driver map.
  If any of these fails, D2 stops there and is reported. No other mode is tried without approval.
- **Lever, as B-0008 but at the extremes and split by teammates:** `driver_characteristics.reaction_speed` = 0 for one
  teammate per team and 1 for the other (seeded coin per team). No other writes. B-0008 left Ferrari (vehicles 8 and
  19) out of the arms and the stock field; D2 does the same. Ferrari stays stock and isn't scored.
- **Size:** 6 starts (B-0008's count): assignment A for starts 1-3, and assignment B (every coin flipped) for starts
  4-6, so each driver runs at both levels.
- **Primary:** the within-team difference (the driver at 1 minus the teammate at 0) in UDP reaction, the mean over
  teams per start, then the mean over the 6 starts. SE from a bootstrap over starts.
- **REPLICATES:** the estimate ≤ −0.05 s and its 2-SE interval excludes 0 (B-0008 predicts about −0.12 s).
  **NULL:** the 2-SE interval is inside ±0.02 s (V-1's reaction band). Otherwise INCONCLUSIVE.

## How the outcomes read (pre-registered)

| D1 | D2 | Reading |
|---|---|---|
| PASS | REPLICATES | The rows reach the AI in benchmark, and the chain works in GP: the trait path is **mode-dependent** (H2 for GP). Next: D3, to see where GP loses the override. |
| PASS | NULL | `ai_driver_config` reaches the AI in GP, but the trait row is dead in both modes on 26566308: a build change (H1-like for this build). Next: D3, plus the per-seat racecraft levers (desk research). |
| FAIL | any | Two readings: (a) the measurement chain is broken (the UDP reaction measure or the route), or (b) per-driver `ai_driver_config` rows aren't read in GP on this build. **First step after a FAIL:** a stock-vs-stock check of the UDP reaction measure (no add-on; the two random halves of the field must read about 0 apart), plus the build check's applied-op readback (all 36 ops applied at the right keys). Until it's understood, the V-1 nulls are moot. |
| PASS | probe fails | D1 alone stands; the benchmark route is unavailable on 26566308. D3 decides. |

No interim looks. Each run is reported when it's done, and nothing is called a result before the supervisor's review.
