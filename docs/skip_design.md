# verve.skip design (#65)

Static research from Swofty's `re/db`, its SDK headers and `bindings.json` (launcher 1.8.4), plus today's logs in `runs/2026-11-03-*`. **Nothing here has hooked anything yet.** Evidence levels are Swofty's: L1 inferred from strings or patterns, L2 decompiled and read, L3 seen in a real session.

## The constraint that shapes everything

**An addon can only hook exported bindings, and a plugin that names an unexported one is dropped whole.** `swofty/addons/core/bindings.json` is the list. Checked against 1.8.4:

| Target | Level | Exported to addons? |
|---|---|---|
| `Ne_InputMapper_IsActionPressed` 0x1441162f0 | L2 | **Yes** |
| `Ne_InputMapper_IsActionReleased` | L2 | **Yes** |
| `Ne_Input_IsActionDownAnyDevice` 0x144116870 | L2 | **Yes** |
| `Ne_Input_InternActionName` 0x143a860a0 | L2 | **Yes** |
| `Sess_PlayCutScene_OnStateEnter` 0x142d78f80 | L2 | **Yes** |
| `Sess_PreRaceGridState_OnEnter` 0x142d81270 | L2 | **Yes** |
| `Sess_RetirementSequence_Update`, `_ShouldEnd`, `_PlayTerminalDamage` | L2 | **Yes** |
| `Sess_IntroVideo_CanFinish` 0x142d6d3b0 | L2 | **Yes** |
| `Game_Handle_GarageCrewEvent_Thunk` 0x14038cc80 | L2 | **Yes**, but a jump into `.data1` |
| `Game_Input_IsMenuAcceptPressed` 0x1436af750 | L1 | No |
| `Game_CutsceneManager_PlayInternal` 0x140227db0, `StopInternal` 0x140228870 | L1 | No |
| `Game_CutsceneScript_RequestShutdown` 0x140237150, `SetStateShutdown`, `TestAndClrRequestStop` | L1 | No |
| `Game_CutSceneParams_SetIgnoreEndEvent` 0x14022d340 | L1 | No, and no signature either |
| `Game_GarageCrew_StateTransition` 0x14043e5a0, every `GarageCrewInstanceLogic_State*` | L1 | No |

So the brief's plan of wrapping `PlayInternal` and `StateTransition` **can't be built as written**. All the unexported rows except `SetIgnoreEndEvent` do have signatures in upstream's `re/db/signatures.json`, so there are three ways forward:

1. **Ask upstream to export them (recommended first).** It's the clean route, and it needs them raised to L2. The same request can go with the bug report.
2. **Find them with `api->scan`.** The API can return an address from a signature, which is enough to **call** a function such as `requestShutdown`. Nothing in the docs or `swofty_api.h` offers a mixin on a raw address, so this doesn't give us a hook. Upstream's advice is also "hook bindings, not fixed addresses".
3. **Use only what's exported.** See the fallbacks below. This covers less, but it can ship without upstream.

The exported bindings are declared `address<...>` with no signature, so `SWOFTY_WRAP`'s compile-time check may not apply. They may need the lower-level `SWOFTY_MIXIN_WRAP` with a signature we state ourselves. Not tried yet.

## (a) Detecting the press and swallowing it

**What the game does:** `IsMenuAcceptPressed` asks whether any local controller reports the interned action `Menu Accept`, through `Ne_Input_IsActionDownAnyDevice` (database note, L1). It has 15 callers, including the cutscene state and the TalkingPoints skip button. `Ne_InputMapper_IsActionPressed` returns a pressed-edge flag by action hash.

**Design:**

- Intern `Menu Accept` once with `Ne_Input_InternActionName`, so the handle can be compared by value.
- Wrap `IsActionPressed` and `IsActionDownAnyDevice`, both exported. Only the action we care about is touched. Everything else goes straight to `orig`.
- While a skippable scene is up and `skip_input` is `game_action`, a true result from `orig` counts as a press.
- On a press, ask for the skip and enter **swallowing**: both wraps return false for that action until `orig` has read false for a release **and** at least 300 ms has passed.

```text
idle --press during a skippable scene--> swallowing --released and 300 ms passed--> idle
```

- **While swallowing, the game must see no press at all**, so `Start Race` and `Go to Track` can't fire from the same one.
- **Hold a safety limit:** if `orig` never reads released (a stuck button or a lost device), leave swallowing after about 5 s and log it, so the player's button can't stay dead.

**Three unknowns that could break this:**

1. **Does the G29 raise `Menu Accept`?** `INPUT` logs from today show no per-press lines, so the trace needs a log line in the wrap. It needs Tyler at the wheel.
2. **Do the wraps get called while a scene plays?** Detection only works if something polls the action each frame. If nothing does, poll it ourselves from `on_frame`, which needs the manager pointer `[0x14604c2c8]+0x140+0x1c0` (an L1 field path).
3. **Do menu prompts read the same path?** `Start Race` and `Go to Track` may come through UI view-model input rather than these two functions. **If they do, these wraps won't swallow the press**, and the double-fire hazard stays open. This is the biggest risk in the design.

**Fallback inputs** don't change the state machine: DirectInput with a learned button, or `key_pressed(vk)` from the overlay. They'd only need the swallow if they share a button with the game's binding, and the same 3rd unknown applies then.

## (b) The active cutscene's name and script pointer

**What the logs show.** The manager logs every step, with the script pointer and name. A real race grid from `direct-race-2`, with no input:

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

And as a session starts, `requestShutdown` then `setStateShutdown` on `f1_world_loadout` about 9 ms later. So `requestShutdown` followed by `setStateShutdown` **is a real path in the game**, which supports asking for a shutdown rather than jumping states. L3 for the sequence, not for calling it ourselves.

**Lessons from that sequence:**

- **"Grid" is several scripts in a row, about 10 s each**, and more than one is active at once. A skip has to deal with a chain, or the next one just starts.
- **The game itself uses `stopInternal`** at the end of the rundown, then `testAndClrRequestStop`. That may be a better way in than `requestShutdown`. The trace should compare them.
- **Preloaded isn't playing.** `f1_26_cloth_car` and others are preloaded and get shut down without ever playing.
- **Don't touch `f1_world_loadout`.** It's the front-end scene the session's own start shuts down.

**How to get the name and pointer, by route:**

- **With upstream's exports:** wrap `playInternal` and `stopInternal`. The log format gives `this`-style script pointer and name.
- **Without them:** no wrap can see this. `Sess_PlayCutScene_OnStateEnter` builds `CutSceneParams` for the session's own cutscene state, so it gives a state-level signal ("a session cutscene is starting") but not a list of grid scripts. Mapping the per-scene toggles (podium, grid, garage...) onto that signal is unproven.

The scene names need a table: `grid_*`, `r_grid*` and `grid_plyshot` are seen. Podium, results, `terminal_damage` and `intro_flag` names aren't seen yet, as no race has reached them.

**Also available:** `Sess_IntroVideo_CanFinish` (exported) returns true when its skip flag `+0xdc6` is set, so the session intro video may have a simple, safe skip. And `Game.SkipRewardSequence` is an existing console variable for reward sequences.

## (c) Garage-crew transitions

**What's known:** `StateWaitPushIntoGarage` -> `StateZoomIntoMonitor` -> `StateCarIsReadyForTrack` -> `StateSendCarToTrack_P3`, driven by `StateTransition` (`setNextState` logs), with requests through `Game_Handle_GarageCrewEvent_Thunk`. All L1 except the thunk. The car's own pit status goes garage 0/9 -> WantsToLeave 10 -> 11/12 -> LeavingGarage 13 -> LeavingPitLane 14 -> OnTrack 1 (session notes).

**What today's logs add:** nothing on the sequence itself. The Time Trial sat in the garage for 3 minutes with no input and logged only `onSessionLoaded`, `spawnGarageCrew` and one `GarageCrewInstance::hide`, with no `setNextState`. So **the states only move on a garage exit or return**, and no exit has been traced yet.

**Candidates, all unproven until traced:**

| Candidate | Why it might be safe | Risk |
|---|---|---|
| `StateWaitPushIntoGarage` -> `StateZoomIntoMonitor` on return | It's the state after the push-in, so the game gets there anyway | The car may not be physically in the box yet, which could leave it stuck |
| `StateCarIsReadyForTrack` -> `StateSendCarToTrack_P3` on exit | Purely the crew's send-off | It may wait for the pit lane to clear. Skipping that could release the car into traffic |
| Never: `StateSendCarToTrack_P3` onward | | The car's own status 10 -> 13 -> 14 is live physics, not a cutscene |

**Route:** `StateTransition` isn't exported, so this also needs upstream's export. `Game_Handle_GarageCrewEvent_Thunk` is exported but jumps into `.data1`, which upstream's rules say to treat as a black box: it can be called, not patched. Calling it to request a state may be the only route without an export, and that's unproven.

**Honest read:** the garage push-in is the riskiest part and has the least support. Build the cutscene skip first.

## (d) Watchdog

A skip is only allowed if the game demonstrably moves on. Per scene type, per session:

```text
armed --skip requested--> waiting(expected next state, deadline 5 s)
waiting --expected state seen--> armed
waiting --deadline passed--> tripped: log it, one-line notice, no more auto-skips of this type this session
```

- **Expected next state:** for cutscenes, `stopInternal` or `setStateShutdown` on that script, or the next scene or screen. For the garage, the next crew state from the trace, plus the car's pit status.
- **Runs on `on_frame`** from `swofty/events.hpp`. If the frame tick isn't available, don't skip at all: the core logs a missing tick, and no watchdog means no skips.
- **Button mode:** a tripped watchdog stops auto-skip for that type, and a press still works, because it's the player's own choice. Whether a press should be allowed after a garage trip is a judgement call, and I'd say no for the garage.
- **Reset:** on `session.start`. Never carried across sessions.
- **Fail safe:** a trip only stops further skips. It never tries to repair the state: a repair is another blind jump.
- **It can't undo a stuck car.** A stuck state after a garage skip needs a test before shipping, not a watchdog. The 20 exits and returns in #65's acceptance are what cover this.

## Checklist for the trace

Run with `CUTSCENE_MANAGER`, `CUTSCENE_SCRIPT_VERBOSE`, `GARAGECREW`, `GARAGE`, `GARAGECREWINSTANCE`, `INPUT` at info. Time Trial: `time_trial f1_2025 austria team=forceindia`, in the sandbox.

**Can run unattended:**

- [ ] `Go to Track` once: the full `setNextState` sequence and timings on exit, with the car's pit status from UDP.
- [ ] Return to the garage (a `start`, `down`, `down`, `a` sequence is documented upstream; check it first): the full sequence on return. **Is there a push-in in a Time Trial at all?** If not, fall back to the career fixture's weekend route to the P1 garage.
- [ ] The cutscenes that play on exit and return, by name.
- [ ] A test build with log-only wraps on `IsActionPressed` and `IsActionDownAnyDevice`: are they called during a scene, and how often? Which action hashes? Does a `pad a` on `Go to Track` go through them? **That answers whether a press can be swallowed.** A log-only wrap changes nothing, so this is a safe first native step, but it does need SWOFTY_MIXIN_WRAP to work on an `address<>` binding.

**Needs Tyler at the wheel:**

- [ ] Does the G29's Cross button raise `Menu Accept`? Press it in the garage with the log-only build running, and watch for the wrap's line.
- [ ] Which button is bound to it in his profile?

**Later, once a race runs (blocked by #64):**

- [ ] Podium, results, `terminal_damage` and `intro_flag` scene names.

## Decisions needed

1. **Ask Swofty to export the cutscene manager, script and garage-crew functions?** Recommended; everything except input hangs on it. It's Tyler's call, along with the bug report.
2. **Ship cutscenes before the garage?** Recommended, given the risk above. It means #65's acceptance splits in two.
