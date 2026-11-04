# verve.skip design (#65)

Static research from Swofty's `re/db`, its SDK headers and `bindings.json` (launcher 1.8.4), plus today's logs in `runs/2026-11-03-*`. **Nothing here has hooked anything yet.** Evidence levels are Swofty's: L1 inferred from strings or patterns, L2 decompiled and read, L3 seen in a real session.

## The constraint that shapes everything

**An addon can only hook bindings exported in `swofty/addons/core/bindings.json`, and a plugin naming an unexported one is dropped whole.** Checked against 1.8.4, 2,660 ids:

**Not exported, so can't be hooked** (all L1): `Game_CutsceneManager_PlayInternal` and `StopInternal`, `Game_CutsceneScript_RequestShutdown`, `SetStateShutdown` and `TestAndClrRequestStop`, `Game_GarageCrew_StateTransition`, every `GarageCrewInstanceLogic_State*`, `Game_Input_IsMenuAcceptPressed`.

So the brief's plan of wrapping `PlayInternal` and `StateTransition` can't be built as written. A request to export them is drafted in [upstream/swofty_skip_bindings.md](upstream/swofty_skip_bindings.md). `api->scan` can find those addresses for **calling**, but nothing offers a mixin on a raw address.

**Exported, and potentially enough** (all L2):

| Binding | Address | What it offers |
|---|---|---|
| `Ne_InputMapper_IsActionPressed`, `IsActionReleased`, `Ne_Input_IsActionDownAnyDevice`, `InternActionName` | 0x1441162f0, -, 0x144116870, 0x143a860a0 | Read and swallow a game action |
| `Game_DataDrivenCutSceneScript_FireEvent` | 0x1402527b0 | An event named `STOP` calls the script's own stop. **The most promising way to end a scene.** Also sees the script pointer |
| `Game_DataDrivenCutSceneScript_SetStateStop` | 0x140251f80 | Direct stop: state 8, and notifies its components |
| `Game_CutSceneScript_SetStateFinished`, `Game_CutSceneScript_Initialise`, `_RunCommand` | 0x140238af0, -, 0x14023c600 | Script lifecycle: a place to learn script pointers without `PlayInternal`. Note says the name is at script+0x550 |
| `Sess_PreRace_Update`, `Sess_PreRace_PlayGridPlayerShotCutscene`, `Sess_PreRace_OnStateExit` | 0x142d831e0, 0x142d83e30, 0x142d843e0 | The grid state, and the call that plays `grid_plyshot` |
| `Sess_PlayCutScene_OnStateEnter` | 0x142d78f80 | The session's own cutscene state |
| `Sess_RetirementSequence_ShouldEnd`, `_OnEnter`, `_PlayTerminalDamage` | 0x142d8b080, 0x142d89960, - | A clean decision point for terminal damage |
| `Sess_IntroVideo_CanFinish` | 0x142d6d3b0 | True when its skip flag +0xdc6 is set |
| `Game_RewardSequence_PlayCutscene`, `Game_Pod2019FirstScript_Shutdown` | 0x142c74860, - | Reward and podium paths |
| `Game_Handle_GarageCrewEvent_Thunk` | 0x14038cc80 | **Every crew request passes here, `_Inst` events included.** A stub jumping into `.data1`: the stub can be used, the body can't be patched |
| `Game_GarageCrewInstance_PlaySequence`, `PlayOverlaySequence` | 0x140382500, 0x1403848a0 | The crew's animation sequences, by name |
| `Game_InGameMenuVM_OnReturnToGarage` | 0x141d592c0 | Return handler; references `flying_to_track_instant` |
| `Game_Garage_FadeOutForExit`, `FadeInAfterReturn`, `OnFadedOutInRace` | 0x142a3a560, 0x142a3ac00, 0x142a3cbe0 | Garage fades |

These are declared `address<...>` with no signature, so they may need `SWOFTY_MIXIN_WRAP` with a signature we state ourselves. Not tried yet.

## What's possible, per scene

"Exported only" means possible without any upstream change. **None of this is tested.** The "game's own skip" column matters most: `IsMenuAcceptPressed` has callers in `PlayCutScene`, `IntroVideo_CanFinish`, `RetirementSequence` and TalkingPoints, so some scenes may already skip on an accept press.

| Scene | Seen so far | Game's own skip? | Exported only? | Route to test first |
|---|---|---|---|---|
| **Grid rundown** (`grid_scs_*`, `r_grid*`) | Yes, about 45 s of 10 s shots | Unknown. Press `a` during it | **Maybe** | `FireEvent("STOP")` on the active scripts, if they're data-driven. They chain, so each one needs it |
| **`grid_plyshot`** | Yes | `Start Race` ends it | **Likely** | Wrap `Sess_PreRace_PlayGridPlayerShotCutscene` and don't call `orig`. Risk: the grid UI may wait on it |
| **Session intro video** | Yes, in the flow | Yes, by the `CanFinish` flag | **Likely** | Wrap `CanFinish` |
| **Intro flag** (`intro_flag`, `_alt`) | No | Unknown | **Maybe** | `FireEvent("STOP")`. Initialise is L1 and not exported |
| **Podium** | No, needs a full race with the player on the podium | Unknown | **Maybe** | `Game_Pod2019FirstScript_Shutdown`, or `Game.SkipRewardSequence` |
| **Results** | Screen only: `session_results_container` | `Advance` is a menu, not a scene | **Yes**, but it may need nothing | It's a menu press. Check what, if anything, plays first |
| **Terminal damage** | No | Note says `RetirementSequence` reads accept | **Likely** | Wrap `ShouldEnd` to return true |
| **Track extras** (marshals, helicopter...) | No | No: ambient, not blocking | **No** | Initialise functions are L1. Low value: they block nothing, so leave them out of v1 |
| **Garage: to track** | Yes, Time Trial: instant | Yes, the `_Inst` request exists | **Maybe** | Rewrite the request at the thunk |
| **Garage push-in** | **No: not seen yet** | Same | **Maybe** | Same |

## The game's own skip (3 of 3, 2026-11-03)

**In a menu race, one `pad a` during the grid rundown ends it.** The press at 18:30:02.4 stopped `r_grid3_06` at 18:30:02.423, then `grid_plyshot` and the grid followed by 18:30:04, about 40 s early. It **did not fire Start Race**: `race.start` came only from a separate press at 18:30:17 (`runs/2026-11-03-menu-trace`). The same in both rehearsals, at difficulty 100.

So the first version of the grid skip may need **no hook at all**, only a synthetic accept, and possibly not even that for a player willing to press. B-0014 repeats it during every race's rundown, before lights out. These were all the virtual pad: a real wheel press hasn't been tried.

Also: `BroadcastGridRundownViewModel - Skipping Rundown screen` logs twice, about 18 s before the press and with no input, so the game has its own notion of skipping the rundown screen. What sets it isn't known.

## Scenes seen so far

| Stage | Scenes, in order | Notes |
|---|---|---|
| Practice garage entry | `pq_garage7_02` | Then `garage_cockpit` |
| Race grid | `grid_scs_2018_np`, then `r_grid3_*` shots about 10 s each, in varying order, then `grid_plyshot` | Rundown takes about 45 s |
| After the flag | `celebrate_pitlane01`, `pod_crew_cele_garage01` or `02`, `celebrate_parcferme01`, then `pod_2019_1st` (44 s) | Seen with the player first and with the player tenth, so it plays for whoever won. Flag to results takes about 100 s. Then `session_results_container`, where FinalClassification arrives |

## (a) Detecting the press and swallowing it

- Intern `Menu Accept` once with `Ne_Input_InternActionName`, so the handle can be compared by value.
- Wrap `IsActionPressed` and `IsActionDownAnyDevice`. Only that action is touched. Everything else goes straight to `orig`.
- While a skippable scene is up and `skip_input` is `game_action`, a true result from `orig` counts as a press.
- On a press, ask for the skip and enter **swallowing**: both wraps return false for that action until `orig` has read false for a release **and** at least 300 ms has passed.

```text
idle --press during a skippable scene--> swallowing --released and 300 ms passed--> idle
```

- **Safety limit:** if `orig` never reads released (a stuck button or a lost device), leave swallowing after about 5 s and log it, so the player's button can't stay dead.

**Three unknowns that could break this:**

1. **Does the G29 raise `Menu Accept`?** `INPUT` logs show no per-press lines, so this needs a line from a wrap, and Tyler at the wheel.
2. **Do the wraps get called while a scene plays?** If nothing polls the action, poll it from `on_frame`, which needs the manager pointer `[0x14604c2c8]+0x140+0x1c0` (an L1 field path).
3. **Do menu prompts read the same path?** `Start Race` and `Go to Track` may come through UI view-model input. **If they do, these wraps won't swallow the press**, and the double-fire hazard stays open. This is the biggest risk here.

**Fallback inputs** don't change the state machine: DirectInput with a learned button, or `key_pressed(vk)`.

## (b) The active cutscene's name and script pointer

A real race grid from `direct-race-2`, with no input:

```text
15:50:14.006 playInternal [..68C6C0] [grid_scs_2018_np]
15:50:20.020 playInternal [..68CF40] [r_grid3_01]
15:50:29.841 playInternal [..68D7B0] [r_grid3_06]
15:50:39.659 playInternal [..68E020] [r_grid3_03]
15:50:49.468 stopInternal for all four, then playInternal [..68E890] [r_grid3_04]
15:50:59.640 stopInternal [..68E890] [r_grid3_04]
15:50:59.656 testAndClrRequestStop returned true ..68E890 r_grid3_04
15:51:01.478 playInternal [..665B80] [grid_plyshot]
15:51:11.134 setStateShutdown (all of them), about when Start Race was pressed
```

And as a session starts, `requestShutdown` then `setStateShutdown` on `f1_world_loadout` about 9 ms later. So asking for a shutdown **is a real path in the game**.

- **"Grid" is several scripts in a row, about 10 s each**, some active at once. A skip has to deal with the chain, or the next one just starts.
- **Preloaded isn't playing.** `f1_26_cloth_car` and others are preloaded and shut down without playing.
- **Never touch `f1_world_loadout`.** It's the front-end scene the session's own start shuts down.

**Getting the name and pointer without `PlayInternal`:** wrap `Game_CutSceneScript_Initialise` or a lifecycle function to collect script pointers, and read the name at script+0x550 (one database note: confirm in the trace). Then map names to the per-scene toggles, and treat anything unknown as "don't skip".

## (c) The garage: today's trace (Time Trial)

```text
Go to Track, then Flying Lap:
17:31:03.011 GARAGE: onPitStateChanged m_nextPitState 1
17:31:03.013 GARAGECREW: GAME EVENT [0] ERequest_SendCarToTrack_Inst
17:31:03.016 GARAGECREW: StateTransition setNextState StateSendCarToTrack_P3
17:31:03.049 GARAGECREW: m_transitionComplete, ANIM EVENT [0] SC, GarageCrewInstance::hide

Pause, Return to Garage:
17:31:58.077 GARAGE: returnVehicleToGarage (virtualiseData 1, sessionSkipped 0)
17:31:58.093 GARAGE: onPitStateChanged m_nextPitState 9, changeToGarageCamera
17:31:58.098 GARAGECREW: GAME EVENT [0] ERequest_ReturnToGarage_Inst
17:31:58.112 GARAGECREW: StateTransition setNextState StateCarIsReadyForTrack
17:31:58.113 GARAGECREWINSTANCE: unhide
```

**The same exit in a practice session, choosing `Drive Out`** (`runs/2026-11-03-pushin-trace`):

```text
18:47:39.318 GARAGECREW: GAME EVENT [19] ERequest_SendCarToTrack
18:47:39.327 GARAGE: onPitStateChanged m_nextPitState 10
18:47:39.333 GARAGECREW: StateTransition setNextState StateSendCarToTrack_P1
18:47:43.459 GARAGECREW: setNextState StateSendCarToTrack_P2 (other crews, vehicles 2 and 17, step the same way)
18:47:43.487 GARAGECREW: GAME EVENT ERequest_SendCarToTrack_LaneClear
18:47:43.493 GARAGECREW: setNextState StateSendCarToTrack_P3
```

**What this shows:**

- **The game has instant requests of its own:** `ERequest_SendCarToTrack_Inst` and `ERequest_ReturnToGarage_Inst`, each done in under 40 ms. The animated exit takes about 4 s to reach P3, and the lane-clear step shows the crew really does wait for the lane.
- **The player already has the instant choice:** the garage offers `Flying Lap` next to `Drive Out`, and the pause menu's `Return to Garage` was `_Inst` in both a Time Trial and a practice session. **So a push-in only happens when driving into the box.**
- **The push-in, from an AI car coming back in the same session:**

```text
18:52:44.267 GARAGECREW: GAME EVENT [17] ERequest_PrepareToPushIntoGarage
18:52:44.273 GARAGECREW: setNextState StateWaitPushIntoGarage        (complete at 18:52:52.866)
18:52:57.224 GARAGECREW: GAME EVENT [17] ERequest_PushIntoGarage
18:52:57.229 GARAGECREW: setNextState StateWaitPushIntoGaragePart2   (complete at 18:53:35.246)
```

  So it's two requests, about 51 s in all, and `StateWaitPushIntoGaragePart2` isn't in the KB. `StateZoomIntoMonitor` didn't appear for AI cars, so it may only apply to the player. **A player's own drive-in hasn't been traced.**

This lowers the stakes: a player can already avoid most of this with `Flying Lap` and `Return to Garage`, and the only slow case left is driving into the box.

**The candidate, replacing "skip to a state":** when a non-instant request reaches `Game_Handle_GarageCrewEvent_Thunk` (exported), rewrite it to its `_Inst` twin. **Don't rewrite past the lane-clear step:** that's the check that stops a car being released into traffic. The game then uses its own instant path, so no state is jumped, and the stuck-car risk should be far lower. **Unproven:** we don't know the requests' enum values, which a log-only trace at the thunk can show, or whether the rest of the game expects the animation to finish.

**Still never do:** anything from `StateSendCarToTrack_P3` onward by hand. The car's pit status 10 -> 13 -> 14 is live physics.

**Honest read:** still the part with least support, because the push-in itself hasn't been seen. Build the cutscene skip first.

## (d) Watchdog

A skip is only allowed if the game demonstrably moves on. Per scene type, per session:

```text
armed --skip requested--> waiting(expected next state, deadline 5 s)
waiting --expected state seen--> armed
waiting --deadline passed--> tripped: log it, one-line notice, no more auto-skips of this type this session
```

- **Expected next state:** for cutscenes, the script's stop or finish, or the next scene or screen. For the garage, the next crew state from the trace, plus the car's pit status.
- **Runs on `on_frame`.** If the frame tick isn't available, don't skip at all: no watchdog means no skips.
- **Button mode:** a tripped watchdog stops auto-skip for that type, and a press still works, except for the garage.
- **Reset** on `session.start`. Never carried across sessions.
- **A trip only stops further skips.** It never tries to repair the state, because a repair is another blind jump.
- **It can't undo a stuck car.** That's what the 20 exits and returns in #65's acceptance are for.

## Checklist for the next traces

Channels: `CUTSCENE_MANAGER`, `CUTSCENE_SCRIPT_VERBOSE`, `GARAGECREW`, `GARAGE`, `GARAGECREWINSTANCE`, `INPUT`, all at info.

**Done:** ✓ Time Trial exit and return. ✓ Practice `Drive Out` and `Return to Garage`. ✓ Grid cutscene chain. ✓ One rundown skip by `pad a`. ✓ Scene chain after a win.

**Can run unattended, no addon:**

- [ ] **The game's own skip, repeated:** about 20 more times, during B-0014's races.
- [ ] **Do other scenes skip on accept?** `pad a` during the post-race chain and the podium. Do it on a run where nothing's being scored.
- [ ] **Post-race scenes when the player doesn't win,** now that difficulty 100 makes that likely.

**Needs Tyler driving:**

- [ ] **The player's own drive-in:** does it use the same two requests as the AI cars' push-in, plus `StateZoomIntoMonitor`?

**Needs a log-only test build first (safe: it changes nothing):**

- [ ] Wraps on `IsActionPressed` and `IsActionDownAnyDevice`: are they called during a scene? With which action hashes? Does a `pad a` on `Go to Track` pass through them? **That answers whether a press can be swallowed.**
- [ ] Are the grid scripts data-driven? Does `FireEvent` see them? Is the name really at script+0x550?
- [ ] What do requests look like at `Game_Handle_GarageCrewEvent_Thunk`? The enum values for the `_Inst` pairs.

**Needs Tyler at the wheel:**

- [ ] Does the G29's Cross button raise `Menu Accept`? Which button is bound to it in Tyler's profile?

## Decisions needed

1. **Ask Swofty to export the manager, script and garage-crew functions?** It's less critical than it first looked, since the exported functions may be enough, but the request is drafted. It's Tyler's call, along with the bug report.
2. **Ship cutscenes before the garage?** Recommended. It means #65's acceptance splits in two.
