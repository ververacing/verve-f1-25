# Verve F1 25: community-first plan (2026-11-14)

> **Scope narrowed (2026-11-16).** Tyler: "let's drop anything that isn't specifically tied to Verve Drivers". Verve is
> now ONE product: **Verve Drivers**, real-driver personalities by season, working alone or alongside the community
> add-ons. The community screens as product tests, verve.racefeel and the Race Feel S-steps, B-0016b (#119), B-0017
> (#121), B-0019 (#122) and the options-by-name difficulty research are **parked** (label "parked: scope narrowed
> 2026-11-16"; nothing is deleted). #94/#95 (difficulty, alien) are parked for after v1. This plan stays as the record
> of the survey; the current plan is [verve_drivers_plan.md](verve_drivers_plan.md), and the scope rules are in
> [process.md](process.md#scope-verve-drivers-from-2026-11-16).

Source: the Swofty public catalog (api.f1.swofty.net/v1/addons, 134 addons, pulled 2026-11-14), the Swofty release notes 1.8.5 to 1.9.50, and two downloaded addons (sha256 matched the catalog).

## What the survey found

1. **The direct-start bug is probably already fixed.** Swofty 1.8.11: "`swofty test session` starts a Grand Prix ... with the track's ground in place: cars no longer fall through the track at the start." Our symptom on 1.8.4 (cars strung out, DSQs) fits cars falling through the track and being reset. The PC is on 1.8.4; the current version is 1.9.50, and most new addons need 1.8.36 or later.
2. **Skip Cutscenes (dromodf.skip-cutscenes 1.9.4, MIT, source included) already is verve.skip.** It has both of Tyler's modes ("Skip with the accept button" and "Remove automatically"). It covers track intro cameras, intro video, in-session cutscenes (garage and similar), the grid scene, the grid rundown, the finish-line celebration, podium and results, retirement, and the career hub scenes. It targets our exact game build (d873a1c8...). It hooks the states we found unexported: Sess_GridRundown_Update, Sess_PreRace_Update, Sess_WinnerSequence_Update, plus vtable slots it checks against this build.
3. **Lap 1 Realistic AI (swofty.lap1-ai 1.0.0, by Swofty) changes the same lap-1 keys our Race Feel S1/S2 planned.** Lap 1 only: braking planned from 10% more grip; overtakes start from 4 car lengths instead of 1.5; the window is about 4x longer; a car leaves a queue after 0.3 s instead of 2 s; cars stay side by side into corners; defence from 45 m instead of 18 m. It says it stacks with Contact Physics and AI Driver Behaviour.
4. **AI Driver Behaviour (kizi, source on GitHub) covers the following gap, room-making, slides and pace spread.** Gap to other cars (stock 0.35), when they make room (stock 0.33 alongside), per-driver spread, steering correction, traction control, lift-off and spin angle, and damaged-car pace.
5. **More Aggressive AI Alternate (kizi, data only) replaces the AI racing line (.aispline) on 28 layouts.** That's the per-track braking data our plan flagged as "a much bigger job" (Race Feel risk 3).
6. **The authors haven't measured any of it.** AI Driver Behaviour: "How much each one changes the racing is not measured." Lap 1 AI and the spline pack give no numbers either. Our harness and metrics are the missing piece.
7. **Tools that speed up our own tests:** Offline Quiet (skips the EA sign-in popups at every boot), Starting Grid (offline GP grid: Realistic, Reversed, Random or a fixed custom order), One Lap Race (a 1-lap race length), Grand Prix Saves, and AI Drive or Race Broadcast (AI drives the player car).

## Decisions

- **D1. Update Swofty to 1.9.50 before any more testing.** Back up the saves first. Tyler clicks Update in the launcher, or says the agent may.
- **D2. Shelve verve.skip.** Tyler uses Skip Cutscenes. Our skeleton stays in the repo, closed. We reopen it only if Tyler finds a scene it misses.
- **D3. Re-scope Race Feel.** Measure what the community built first, then build only what's missing:
  - P1 screens: stock vs Lap 1 AI vs AI Driver Behaviour (recommended settings) vs the Alternate spline pack.
  - Same metrics as the plan: lap-1 loss and spread, train time, held passes, phantom brakes, rear-end contacts and wing damage, plus the no-harm guards.
  - verve.racefeel then holds only the gaps, or becomes a recommended stack with tested settings.
- **D4. Verve's own job stays per-driver personality** from the AC Verve profiles. It must stack with the community AI addons: load order, a conflicts and touches list, and a check that each driver's own values survive.
- **D5. Two profiles, kept apart** (details below). The agent never selects Tyler's racing profile.
- **D6. Practice-programme work is dropped.** No resource-point, R&D or practice-programme changes.
- **D7. B-0014 stays as pre-registered** (random grid). Skip Cutscenes in Remove mode replaces the manual rundown press in both arms; amendment A3 on #71 before race 1. Fixed-grid designs (Starting Grid, Custom) are for the new screens.

## Faster test races (in order)

1. On 1.9.50, retest the direct start: `swofty test session grand_prix ...` with the fixture, 2 races. Pass: every car starts from its grid slot, no DSQ, the race finishes, and UDP final classification arrives. If it passes, lights-out comes in about 1-2 minutes instead of 6.5.
2. Skip Cutscenes in Remove mode in the testing profile: no grid scene, rundown, celebration or podium. Confirm in loader.log that each state is "removing" in a Grand Prix.
3. Quit as soon as the final classification packet arrives. Never wait for the podium.
4. Offline Quiet: no EA popups at boot, so the plans get shorter and stall less.
5. Repeats inside one launch with Restart Race, where an arm needs no relaunch. First confirm that a restart re-rolls the start draws (the RaceStarts log).

Target: about 6-8 min per 5-lap race instead of 16, so about 2x the races per window.

## Profiles

**"Tyler Racing"** (Tyler's own, for playing):
- Use launcher saves ON. Saves page: Import from Steam, which copies the current Steam career in and keeps the old profile save as a version.
- From then on, play that career only from Swofty with this profile. The plain Steam copy stays as it was and won't follow, and launcher saves don't go to Steam Cloud. Export to Steam exists if Tyler ever wants to go back.
- Add-ons that can be switched on or off any time (session-only native): Skip Cutscenes (accept-button mode), Offline Quiet, FFB Overhaul (early release; anti-clipping and kerb spike guard also apply to the G29), Lap 1 Realistic AI, Driver Form, Smarter AI Strategies, Team Orders.
- Add-ons that become part of the career (pick before continuing it, because Play warns later if they're turned off): Silly Season, Paddock Drama or Dynamic Events, season packs, More Driver Models, Team Names, Career Length (new careers only), R&D Tyres department.
- Tyler's choice entirely. The agent doesn't touch this profile.

**"Verve Test"** (the agent's):
- Launcher saves ON with its own save. Never imported from Tyler's career.
- The fixture sandbox and hash guard stay on for every run. The guard now also covers the Tyler Racing profile save.
- Baseline add-ons: Skip Cutscenes (Remove), Offline Quiet. Starting Grid is used only for fixed-grid screens. The community AI addons are on only in their own arms.
- Arms that need different addon sets use copies of this profile ("Verve Test A/B"), set up by the agent.
