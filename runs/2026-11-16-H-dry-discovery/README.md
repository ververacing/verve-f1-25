# H-dry discovery (#118 step 1): the smoke run on build 26566308

16 Nov 2026, 07:45-07:53 PT. One stock session with no race, on `harness/sessions/gp_menu_weather_discovery.plan`
(`tools/b0016_run.ps1 -StockOnly`, early-start override to 17:00). Frames went to the agent's scratchpad, not the
repo.

**Setup:** launcher 1.9.58 (file version before launch, and the game's main menu: "Swofty Launcher 1.9.58"), core
0.2.13, F1 25 build 26566308 (Steam 1.0.145.2472). verve-test with dromodf.skip-cutscenes off, offline-quiet and
simplified on.

## The harness on the new build (smoke)

- **Session:** the plan ran to the end ("plan done"). Saves unchanged (34 entries), guard exit 0, post-run check
  CLEAN, cleanup done. The intro played, with splash after 84 s.
- **Save sandbox:** verified for this F1_25.exe by `bindings.steam-26566308.json`. offline_quiet.dll and
  simplified.dll both loaded at the window stage.
- **Test-agent bindings:** route, pad and ai_drives_player are ok. car, title, resume and advance say "the KB
  build's layout … not this build". The menu plans use none of these, but the race plans use ai_drives_player
  (ok).
- **No race,** so `race_feel` exit 1 and `weather: NONE` are expected.

## Found

- **Weather:** on the Grand Prix settings hub, the **Weather and Time of Day** tile is up then right from
  Difficulty. Its first row, **Quick Weather**, starts at **Dynamic** ("…or choose dynamic which will randomise it").
  **One press right is "Clear (Dry)"**, which holds for the whole weekend. The other rows are Customise Weather,
  Session Start Time (Realistic), Customise Session Start Time and Forecast Accuracy (Perfect).
- **Back to Start Event:** B from the weather screen leaves the cursor on the Weather tile, and two presses left is
  Start Event (seen on screen).
- **Track list:** it includes reversed layouts. From Austria (ten right of Australia, as in the plans):
  - +3: Great Britain (R), Silverstone
  - +4: Belgium
  - +5: **Hungary, Hungaroring**

  So Hungary is **fifteen right from Australia**, not thirteen. The proof race checks UDP track id 9.

Plans written from this: `gp_menu_full_press_dry.plan` and `gp_menu_full_press_dry_hungary.plan` (press route,
since skip-cutscenes is off on 1.0.145).
