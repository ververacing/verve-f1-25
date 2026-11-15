# What Swofty 1.9 and the community already tell us (supervisor desk review, 2026-11-14)

Sources:
- Swofty repo, ebcea51 (1.8.4) to FETCH_HEAD (past 1.9.50): docs/std/systems/ai.md, docs/reference/std/live.md, re/db/subsystems/ai.md, re/db/structs/Ai*.h, commit d181576.
- The addon catalog (134 addons). 21 community addons publish source.

## 1. Which AI keys the game actually re-reads (from Swofty's AI guide, "Racecraft per car, live")
- **Re-read every tick (live-tunable, proven consumers):**
  - the blocking keys: fraction_of_follow_speed(_at_race_start) 0.975 / 0.875, max_blocking_distance(_at_race_start) 18 / 18, blocking_speed_differential 0.6, blocking_threat_time_modifier 0.175, and others
  - overtake.overlap_percentage
  - the two alongside yield floats: speed_difference_for_limited_zone_yielding 3, yield_overtake_rate 1
- **"Off" (no AI-vs-AI reader found):**
  - overtake.oppertunist_overtake_track_speed_difference (12), read behind a packed thunk
  - the divebomb_defense.* rows, read only by the human-divebomb behaviour
  - alongside.min_presence_within_buffer, space_seeking.remember_crowed, blocking.start_blocking_intersection_time, blocking.merge_back_to_racing_line
- **No consumer found yet, so whether the game caches them is unproven:** the other overtake and space_seeking keys.
- The `_at_race_start` pair is read until the race-start state machine's last state, then the plain pair takes over. That's the lap-1 lever.
- "Every stock driver has the same" values (default_driver).
- **Plan impact:**
  - Drop S2's opportunist speed-difference step.
  - Prefer the tick-read keys for S1 and S3.
  - For keys with no proven consumer, a null result is "unproven reader", not "no effect".

## 2. Per-car live layers (cars::live)
- A native addon can set any of 59 racecraft fields per car, live, for as long as it holds a Layer. No database edit is involved, and erasing the Layer restores the game's value.
- Swofty's own example is lap-1 only blocking distance 40, released at that car's first lap event. That's very likely how swofty.lap1-ai works.
- Readiness: each field needs its own KB verify row. Only the 4 blocking rows have one; the other 55 return `unavailable` until verified.
- Not exposed live: cede_position.*, exit_fallibility.*, race_start.*.
- **Verve impact:** per-driver and situational racecraft at runtime (lap 1, being caught, defending), as an alternative to driver rows. It's a candidate v0.3 design.

## 3. ai.controller.update: every AI car's throttle, brake and steering, every frame
- Before, replace and after handlers see each AI car's inputs every frame. It needs in-game check T145.
- **Harness:** a tiny read-only native probe could log AI brake inputs per car. That's ground truth for the phantom-brake detector.
- **Race Feel S3 option:** a bounded "no phantom brake" filter that softens a hard brake on a straight with nothing ahead within X m. It must never touch real braking points or yellow flags.

## 4. Swofty's open questions our harness can answer (re/db/subsystems/ai.md)
- Where the difficulty slider (0-110) applies. That's their highest-value open item.
- Whether runtime-retuned ai_vehicle_config keys take effect. It's parsed once at Sess_Load_VehicleAiConfig.
- Our F-36, F-38 and F-41 are the kind of evidence they ask for. Offering it upstream is Tyler's call; nothing gets posted.

## 5. Community sources still to read, highest value first
1. kizi.ai-driver-behaviour: how "drivers differ" is built per driver
2. kizi.ai-tweaks (Contact Physics): AI reaction after a hit
3. msyeett.driver-form: weekend form via the game's AI pace
4. nick.grid-start-2026: an AI start fumble model, to compare with F-38 / F-39
5. kizi.canned: DNF and failure tables

Swofty's AI guide already shows AI Racing Tweaks' code: buffer_space.vehicle_buffer flat curve (spacing), throttle_cut, give_up, steering PID scaled 75/50/25%, TC off.

## 6. Harness facts learned tonight
- 1.9.x `test shell` and `test session` copy --profile, or the ACTIVE profile when none is given. Addon storage follows the active profile's name.
- Swofty bug: addon_storage.rs finish() still uses remove_tree(aside), not #959's lock-tolerant clear_tree (1.8.33). The storage sidestep works around it.
