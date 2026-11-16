# V-1 pre-registration (DRAFT v2): are the driver levers alive? A factorial screen

Status: DRAFT for the supervisor's review (2026-11-16). Nothing runs until it's approved. Scope: Verve Drivers
(docs/process.md). Evidence base: [verve_drivers_plan.md](verve_drivers_plan.md). No lever has a proven on-track
effect on any build. The race-start draws are proven, but only on 25251167. This version builds in Tyler's ask to
speed tests up ("if we just need to see how each driver starts off the line, let's do a bunch of quick 1-lap races").

## Question
On build 26566308, on the spectator garage route, does each of the six per-driver characteristics
(`driver_characteristics.{reaction_speed, mistakes, aggression, control, speed_in, speed_out}` on the 2025 rows)
change behaviour when pushed to its extremes (0 vs 1)? "Alive or not" only: realistic values are V-2.

## Where the time goes today (B-0018 race 3, 16 Nov)
Launch 10:13:34 → intro done 10:14:55 (81 s) → main menu 10:15:59 → settings hub 10:17:09 → difficulty, grid and
weather steps, Start Event, the grid rundown (`@sleep 125`), garage monitor → racing from 10:21:52 to 10:28:56 (7.1 min)
→ quit, guard and race_feel → next launch 10:29:23. **8.7 min of 15.8 is overhead.** Skipped-intro retries add 5-8 min
to about a third of launches today.

## Phase 0: restart discovery (1 launch, about 30 min, after B-0018)
On the spectator route (B-0018's setup), finish a race, then try pause → **Restart Race**, three times. Record:
1. **Does Restart work** while spectating with the car parked? (Frames + transcript.)
2. **Is the car re-parked?** Loader: a new `race.start` and "your car is parked (again) in 2 s".
3. **Do the start draws re-roll?** RaceStarts log: per-driver reaction times differ per restart. Does the shared
   per-session k (F-39) change or stay?
4. **Is the grid the same** across restarts? A fixed grid would be a bonus.
5. **UDP:** the same session uid or a new one per restart? Our parsers must split restarts into races (a new uid, or
   SSTA/LGOT events plus the LapData lap reset).
6. **Restart cost:** wall time from the restart press to lights out (does the grid rundown, about 108 s, replay?).

**If restart works:** N races per launch, and the launch overhead is paid once. **If not:** one race per launch, and
1-lap starts use the **One Lap Race** add-on (standing add-on OK, sha checked, verve-test only).

## Design: a factorial screen of all six traits at once
- **Assignment per launch:** each of the 19 AI drivers gets 0 or 1 on each of the six traits, independently. It's
  balanced per trait (9 or 10 drivers at 1), with teammates split where possible, seeded and recorded
  (`assignment.csv`). Each launch gets a new assignment. One generated test add-on per launch writes the 114 values
  (absolute, `game_builds [">=26566308"]`; expected gamedb count fixed from the build).
- **Within a launch:** several restart-races under the same assignment (Phase 0 decides how many).
- **Analysis:** per trait, the main effect (1 − 0) on its own measure, from a model with all six trait indicators plus
  driver fixed effects (drivers change levels across launches). Bootstrap over launches, with races nested inside.
  Interactions are not scored.

### Pre-registered measure per trait
| Trait | Session | Primary measure | Predicted | Minimum effect (null band) |
|---|---|---|---|---|
| reaction_speed | starts | start reaction (s), RaceStarts log | 1 faster | ±0.02 s |
| mistakes | starts + races | bad starts (race_start_performance < 50) and off-tracks + spins per race | 1 fewer | ±0.05 bad starts per start; ±0.1 per race |
| control | races | off-tracks + spins per race | 1 fewer | ±0.1 per race |
| aggression | races | held passes made, net, laps 2+; time following within 1 s | 1 more | ±0.25 per race |
| speed_in | races | corner-entry pace: median minimum speed in the braking zones of the corner table, clean laps | 1 faster | ±2 km/h |
| speed_out | races | corner-exit pace: median speed 150 m after the apex, clean laps | 1 faster | ±2 km/h |

Secondaries for every trait: positions gained to T1 and at the end of lap 1, lap-time SD, contacts.
**Decision per trait:** ALIVE (2-SE interval excludes 0, in the predicted direction), ALIVE-REVERSED, DEAD (2-SE
inside the null band) or INCONCLUSIVE. **Validity per race:** `aionly_check` (finish from LapData, ≥ 18 AI finished,
live window, LOCKED, gamedb), with the test add-on's values applied (readback before the batch, gamedb every race).

### Sessions
- **Starts (lap 1 only):** a restart once the last AI car has crossed the line for lap 1 (or One Lap Race). Measures:
  the RaceStarts log, positions at T1 (LapData lap distance), positions at the end of lap 1. **Target: 10-25 starts per
  launch**, depending on the restart cost.
- **Races:** **3 laps** if B-0018's data shows the passing and following measures are mostly settled by lap 3 (the
  numbers go to the supervisor after race 10); otherwise 5. The live check stays as now.

### Size (proposed; fixed before race 1)
- Starts: **6 launches × 15 starts** = 90 starts. Each driver gets about 45 at each level of every trait.
- Races: **10 launches × 5 races** = 50 races. Each driver gets about 25 at each level of every trait.
- Old design (one trait at a time): 48 races total, 8 per trait. The factorial gives each trait the full 50 races.

## Hours
| Design | Assumptions | Hours |
|---|---|---|
| Old draft: one trait at a time | 48 races × 15.8 min + skip retries (about 1/3 × 6 min) | **about 14 h** |
| Factorial, restart works | launch 8.7 min once; a start ≈ restart + rundown (≤ 2 min, if it replays) + lap 1 (1.5 min) ≈ 3.5 min; a 3-lap race ≈ 2 + 4.4 ≈ 6.5 min. Starts: 6 × (8.7 + 15 × 3.5) ≈ 6.1 h; races: 10 × (8.7 + 5 × 6.5) ≈ 6.9 h | **about 13 h for 6 traits with about 6× the data per trait** (starts alone: 6 h) |
| Factorial, no restart | one race per launch at about 13 min (3 laps); starts via One Lap Race at about 11 min per launch (1 start each) | races: 50 × 13 min ≈ 11 h; starts: 30 launches ≈ 5.5 h. Cut to 30 races and 20 starts: **about 10 h** |

## Overhead cuts (no changes to the guards or the pause path)
| Cut | Saves per launch | Note |
|---|---|---|
| **A captured fixture with the GP settings already set** (difficulty 100, Quick Weather Clear (Dry), Starting Grid Custom with the player last; `swofty test fixture capture`) | about 1.5-2 min (the difficulty hold, the weather and grid-editor steps) | Starting Grid keeps its order "with your Grand Prix save", so **the AI grid may become fixed** too, a bonus. It needs one capture run and a fixture review (the sandbox only). |
| `@udpfinish` (in use since race 2) | 0-2 min vs the fixed wait | done |
| A 300 s cool-down before a relaunch (#144) | 5-8 min per skip streak (fewer wasted launches) | in review |
| Restart Race (Phase 0) | 8.7 min per extra race | the big one |
| Hungary stays (fifteen rights, about 10 s); a closer track saves seconds only | < 0.2 min | not worth a new track baseline |
| The rundown `@sleep 125` | none | needed while skip-cutscenes crashes 1.0.145 |

## Not in V-1
Realistic values, strength, stacking with community add-ons, other tracks, the parameter maps and the 84
ai_driver_config keys (V-2 or later). No interim analysis before the last launch of each session type.

## Tooling to build before race 1 (for review)
- `tools/v1_make.py`: the seeded balanced factorial assignment per launch, and the generated test add-on.
- The restart-race support in the plan and shell: a `@restart` step, and splitting races in the UDP parser by uid or
  by event.
- `tools/v1_check.py`: validity via `aionly_check` per race segment, the measures above (incl. the corner-entry/exit
  pace from the corner table in `race_feel`), and the decision per trait.
