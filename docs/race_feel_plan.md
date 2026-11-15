# Verve Race Feel package: plan

Goal (Tyler, 2026-11-14): (1) AI cars race properly on lap 1, (2) no conga lines, (3) no sudden, unexplained AI braking that wrecks front wings.
Deliverable: field-wide improvements with an Off / Mild / Full setting, either a separate addon `verve.racefeel` or a tested stack of community addons (see community_first_plan.md D3). It works on its own or under the Verve driver-personality addon.
Method: measure stock first, change one lever group at a time, pre-register every batch (hypothesis, metric, pass rule, repeats, bootstrap over races), sandbox plus hash guard, testing windows only.

## What we already know
- Per-driver AI settings ARE read in a real Grand Prix (B-0012b, 5/5).
- Every stock driver shares the same 84 ai_driver_config values: the conga-line root-cause candidate.
- Stock values (dumped 2026-10-30):
  - lap 1: blocking.fraction_of_follow_speed_at_race_start 0.875, blocking.max_blocking_distance_at_race_start 18
  - trains: overtake.attacker_close_enough_car_lengths 3, close_range_car_lengths_to_start_overtake 1.5 (continue 2.0), oppertunist_overtake_time 0.25 s, oppertunist_overtake_track_speed_difference 12, regular_overtake_initiate_time_adjustment 0.75, braking_zone_abort_overtake_time 0.67 s
  - following: package parameter maps follow_speed_factor (low aggression follows 5% slower even at max difficulty) and alongside_space_factor (15% more room)
  - per car: buffer_space.vehicle_buffer, downforce_loss.* (AI-only dirty air), drafting.*
- Benchmark mode is a procession: never use it for this.
- OVTK events count every position change, and ~60% are undone within 10 s (rehearsal: 104 raw, 37 held). Use held passes.

## Metrics (tools/race_feel.py, per car per race, from UDP + LAPTIMES)
1. Lap 1:
   - lap-1 time minus the race's median green-flag lap (the "lap-1 loss", per car and the field median)
   - positions changed on lap 1 (sum over cars of |grid pos - pos at end of lap 1|, and held changes)
   - field spread at the end of lap 1 (leader to last, in seconds)
   - lap-1 collisions (COLL events with lap == 1)
2. Trains:
   - "train time": the share of AI car-time on laps 2+ spent within 1.0 s of the car ahead WITHOUT making a held pass on that car within the next 2 laps. Sample at the UDP rate and weight by time, not samples.
   - held passes per race on laps 2+: a position gain on car X that isn't reversed within 10 s
   - longest train: the max number of consecutive cars each within 1.0 s of the car ahead, sampled once per lap at the line; report per-race median and max
3. Sudden braking:
   - "phantom brake": an AI car with brake > 0.3 starting more than 50 m (lap distance) before where that same car starts braking for that corner on its own clean laps (median of laps with no car within 2.0 s ahead), while a car is within 1.0 s behind it. Corners are found from the car's own clean-lap brake onsets (cluster within 30 m). Count per car per race. Validate the detector on 2 races by eye with telemetry plots before trusting it.
   - rear-end contacts: COLL events where the follower (behind by lap distance at the time) hits the leader
   - front-wing damage increments per car per race (CarDamage, front left/right wing: done)
4. No-harm guards (every batch): total collisions, wing damage, DNFs, penalties, field pace (median green lap). A lever that fixes its target but raises a guard by >= 2 SE is rejected or toned down.

Output: runs/<id>/race_feel.csv (one row per car per race) plus summary.json (field-level per race). Also a --selftest with synthetic data covering each metric: a pass reversed at 9 s vs 11 s, a train of 4, a phantom brake at 60 m vs a normal one at 20 m, a rear-end vs a side-swipe.

## Phases
- P0: B-0014 (#71): does per-driver aggression produce held passes. First data point for trains.
- P1: tooling plus stock baseline. race_feel.py, then 10 stock races at difficulty 100 on two tracks: Hungary (check its game label) and Austria. This shows how bad each problem is in numbers, and which track shows it best.
- P2 (now community first): screens of stock vs swofty.lap1-ai vs kizi.ai-driver-behaviour (Tyler setting, then the addon defaults) vs kizi.f1-25-more-aggresive-ai-2 vs Contact Physics (gentle). 6+6 per batch, alternating, on the train-prone track. Our own lever groups only for what's left:
  - S1 lap 1: fraction_of_follow_speed_at_race_start 0.875 -> 1.0, max_blocking_distance_at_race_start 18 -> 10 (note: lap1-ai moves this to 45), plus a field-wide tightening of the race-start bounds
  - S2 trains: opportunist 0.25 s -> 0.10 s, 12 -> 6 km/h; attacker_close_enough 3 -> 4; start window 1.5 -> 2.0
  - S3 following and sudden braking: follow_speed_factor high-difficulty corners 1.05 -> 1.0; alongside_space_factor 1.15 -> 1.05; blocking distance/threat keys in small steps both ways
  - S4 dirty air: the downforce_loss scalars in small steps, with a field-pace guard
  - Never: cede_position.*, yellow_flag_*, flying_lap_yield_*
- P3: combine and validate. The winning setup (addons or our levers), 10+10 races across both tracks vs stock, all metrics pre-registered.
- P4: Tyler playtest (his call): 3 races with and 3 without on the G29, scored with the same metrics from his telemetry.

## Risks
- Several keys have undecoded signs (Q-09): screen with clear opposite steps, and accept "no effect".
- More aggression can mean more contact, hence the guards.
- Some sudden braking may be baked into per-track AI data (the .aispline). The community spline pack is the test of that.
