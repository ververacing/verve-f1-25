# What the 21 open-source community addons teach Verve (supervisor review, 2026-11-14)

Method: 21 public repos, shallow-cloned and read only (nothing built or run). Four parallel code reviews, then this synthesis. Every point below comes from reading code and has NOT been checked in game. Offsets and RVAs are for Steam build 25251167.

## A. Harness: faster, more repeatable test races
1. **Likely cause of the safety car 3 s after lights out on the direct start.**
   - Two independent sources say safety cars come from "deployment points" (terminal-damage: probe/01_game_signatures.inc:53-57).
   - The stopped-cars accumulator adds points for any car standing still. In an unattended start the player car can sit on the grid: Race Broadcast only lets the AI take the car once it is already above 20 m/s (race_broadcast.c:1751).
   - Fix to test: hand the player car to the AI at `race.start`, without waiting for speed (`sessions::set_control(me, ai)`, re-taking it if the game takes it back). Or park it in the garage 2 s after race.start (Game_Pitlane_SetVehicleStatus(sys, car, 9), spectator mode 1506-1564).
   - First check, read-only: in the pilot capture, was the player car below 3 m/s after lights out?
2. **Set game options by name, which may fix "direct start ignores difficulty".**
   - Starting Grid sets the `starting_grid` option through g_Game_OptionsStore: FindOption, then vtable get (2) and set (3), "as if the player picked it" (menu_option.hpp:16-96).
   - The same route probably works for AI difficulty, the safety-car setting and the formation lap, once their option names are found in the options_system tables.
   - That would need a small native harness addon (verve.harness). Then the direct start (9.7 min per race instead of 16) becomes usable for real batches.
3. **Grids.** Starting Grid's Random is seeded from the clock and isn't repeatable. Reversed or Custom are deterministic. The grid table sits at system+0x988 and is rewritten before the cars are placed.
4. **Hidden randomness in other addons.** These reseed from the clock: canned DNFs re-shuffle from GetTickCount, Terminal Damage seeds from tick^PID, Driver Form keeps a weekend roll for 24 h. The game's own DNF dice give the same cars on every restart. Keep all of these out of test profiles unless they're the arm being tested.
5. **Running in the background.** Losing window focus pauses the game. Spectator mode filters WM_ACTIVATEAPP/KILLFOCUS to stop that (457-557). Useful if Tyler uses the PC, for example over Parsec, while a test runs.
6. **Signals.**
   - UDP Session packet body+124 is the safety-car status: 0 none, 1 SC, 2 VSC, 3 formation.
   - SCAR event: a = type, b = phase.
   - race.start also fires at the end of the formation lap, and LGOT also fires when the formation lap starts.
   - The lights state byte gives an exact lights-out time.
   - Swofty's session label stays on the weekend's first session, so read the game's own session type (15-17 = race).
   - The results-screen activate hook is a dependable "race over" signal.
7. **Save hazard.** The stock Grand Prix "Start new" deletes the save on card 0 (grand-prix-saves new_grand_prix.hpp:17-23). Our plans must never use it outside the sandbox.

## B. Measuring race feel (improves tools/race_feel.py)
- **Pit-cycle passes.** An OVTK within 20 s of either car's pit stop is a pit cycle, not an overtake (Race Broadcast 951-958). Exclude these from held passes.
- **Contact outcome.** Judge it 2 s after COLL: wing damage +8 or more, a spin (speed under 8 m/s), or 2+ places lost (898-934). This attributes front-wing hits to car pairs.
- **The broadcasters' thresholds, for calibration:**
  - battle: gap 0.7 s starts it, kept to 1.2 s; it goes stale with no 0.1 s gain in 25 s
  - spin: a speed drop over 18 m/s within 0.25 s, with brake under 0.35, at over 25 m/s
  - stopped: under 3 m/s for 1.5 s
  - side by side: car centres under 2.6 m apart
- **Pair attribution from contact records.** The collision handler's contact record holds impulse, the other car and the normal (terminal-damage). Front-wing damage at wing+0x48/+0x4C (left/right) could feed a native probe.
- **Ground truth for the phantom-brake detector.** The AI's input record [ctrl+8] has throttle +0x0c, steer +0x14 and brake +0x18. That's also what Swofty's ai.controller.update exposes.

## C. AI behaviour: what's known to work, not work or hurt
1. **AI Driver Behaviour's "drivers differ" may be mostly inert.**
   - Its per-driver spread sets alongside.min_presence_within_buffer, which Swofty lists as "no reader found".
   - It also sets close_range_car_lengths_to_start_overtake and braking_zone_abort_overtake_time, which have no proven consumer.
   - Seed: a triangular value from an FNV hash of the driver label, fixed per driver.
   - The buffer (spacing) is per car, not per driver.
   - Measure it before trusting it.
2. **Its default "slides" package is a plausible cause of AI off-line moments and front-wing hits.** It sets steering PID ×0.25 and steering smoothing to 1.2 s. Our "Tyler setting" (75%) is gentler; stock may be gentler still.
3. **Driver Form's "moments" are deliberate sudden slowdowns.**
   - It sets difficulty to ×0.35 for 3-8 s at random, at up to 0.5 per minute for an out-of-form car (patches.hpp:39-46).
   - In-form drivers get up to 2× blocking distance, which encourages trains.
   - Keep it out of anything aimed at Tyler's three goals.
4. **Don't use grip as a pace lever.**
   - Grip above 1 made the AI plan corner speeds the car couldn't hold, and it hit the barriers (AI Driver Behaviour's removed Pace option; README:20). Lap 1 AI uses +10% grip on lap 1, so expect lap-1 contact.
   - Better pace levers: the AI profile's base lap time (profile+0x148, as Driver Form uses), the difficulty override, or the DB pace curves Verve already uses.
5. **Start model (spool-up's measurements).** AI reaction about 0.2 s; 0-50 km/h in 2.0-2.3 s; AI launch about 0.8× the traction limit. Launch quality (an engine.power_scale layer) is a lever separate from reaction time. Verve's start personality can use both: reaction plus launch.
6. **Contact Physics freezes AI steering for up to 1 s after a hit**, by swapping each AI controller's vtable. That's a plausible cause of chain crashes, and it may clash with Swofty's ai.controller.update. It's another reason to keep it out of Tyler's career.

## D. Verve design lessons (careers and compatibility)
- **Ratings in careers.** The game develops its drivers itself. Silly Season's overwriting of every driver drifted ratings 20-30 points over a few seasons, so it stopped.
  - The save-safe way is the `driver.ratings.read` event: change each value as it's read, per career data group, without persisting.
  - Raise as a floor (max(value, floor)), not a plus.
  - Load order matters, because Progressive uses the same event.
- **Don't key personality only on the driver label.** Silly Season renames reserve drivers live into new talents, and they'd inherit the old reserve's Verve character. Key on label plus identity, and expose a `services` interface so other addons can query or override.
- **Known career groups.** Gate on f1_career_2026 / 2025 / sw_progressive / f2_26 (F2 Revamp builds from 2026 copies). Leave others stock.
- **Clashes to handle:**
  - AI Driver Behaviour's per-driver rows on the alongside/overtake keys against Verve's rows (last writer wins)
  - Driver Form's in-memory overrides of difficulty and characteristics on top of Verve's DB values
  - Silly Season and F2 Revamp writing statistic curves for their drivers
  - Terminal Damage cancelling the game's canned DNFs
- **CPU patterns:**
  - Change live layers off the frame thread, only when the value moved ≥0.05. Changing them on the frame thread runs the core's apply pass for every car and field, and hitches.
  - `cars::live::Car(c).control()` costs about 2.5 ms per call, so read it at a low rate, round-robin.
  - Avoid ReadProcessMemory per frame.
  - Time your own cost with a QueryPerformanceCounter scope profiler, as mean and max per window.
  - Read the DB once on a worker thread; a per-driver walk caused a 12-14 s stall.
- **Safe mode (RE-Optimization).** Write a launch-state file atomically, confirm at 90 s or a clean exit, and after a crash run stock for N launches.
