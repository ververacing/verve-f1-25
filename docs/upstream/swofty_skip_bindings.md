# Draft request to Swofty: bindings for a skip addon

**Draft only. Nothing has been posted.** It's Tyler's call whether to post it on Discord or GitHub, or to have it opened from Tyler's account.

---

**Title: Export the cutscene manager, cutscene script and garage-crew state bindings for an opt-in skip addon**

Hi! I'm building `verve.skip`, an opt-in addon that skips cutscenes and the garage push-in, either on a button press or automatically. By default it does nothing until the player turns it on, and it would stop itself for the session if the game doesn't move on within a few seconds.

The functions below are in your KB with signatures, but they aren't in `bindings.json` (launcher 1.8.4, build 25251167), so an addon naming one is dropped. Could they be exported? I'd rather ask the game to end a scene through its own calls than poke at memory.

## Most useful

| Binding | Address | KB level | Why |
|---|---|---|---|
| `Game_CutsceneManager_PlayInternal` | 0x140227db0 | L1 | Know which scene is starting, by name, to honour per-scene settings |
| `Game_CutsceneManager_StopInternal` | 0x140228870 | L1 | Know it ended, for the watchdog |
| `Game_CutsceneScript_RequestShutdown` | 0x140237150 | L1 | The clean way to end a scene |
| `Game_GarageCrew_StateTransition` | 0x14043e5a0 | L1 | See crew state changes, for the watchdog on a garage skip |

## Nice to have

| Binding | Address | KB level | Why |
|---|---|---|---|
| `Game_CutsceneScript_SetStateShutdown` | 0x140235f10 | L1 | See the shutdown happen |
| `Game_CutsceneScript_TestAndClrRequestStop` | 0x1402371f0 | L1 | The game's own stop check at the end of a scene |
| `Game_GarageCrewInstanceLogic_StateWaitPushIntoGarage` | 0x140386720 | L1 | Trace and detect the push-in |
| `Game_GarageCrewInstanceLogic_StateZoomIntoMonitor` | 0x140385b80 | L1 | Same |
| `Game_GarageCrewInstanceLogic_StateCarIsReadyForTrack` | 0x140385760 | L1 | Same |
| `Game_GarageCrewInstanceLogic_StateSendCarToTrack_P3` | 0x140386320 | L1 | Same |
| `Game_Input_IsMenuAcceptPressed` | 0x1436af750 | L1 | Device-independent detection of a skip press |

## Evidence I can offer

The log messages behind these are real on build 25251167, from sessions on my PC. I can share logs if that helps raise them from L1:

```text
CUTSCENE_MANAGER: >>>>>>>> CutsceneManager::playInternal [...] [grid_scs_2018_np]
CUTSCENE_MANAGER: >>>>>>>> CutsceneManager::stopInternal [...] [r_grid3_04]
CUTSCENE_SCRIPT_VERBOSE: requestShutdown ... f1_world_loadout
CUTSCENE_SCRIPT_VERBOSE: setStateShutdown ... f1_world_loadout
CUTSCENE_SCRIPT_VERBOSE: testAndClrRequestStop returned true ... r_grid3_04
GARAGECREW: GAME EVENT [0] ERequest_SendCarToTrack_Inst
GARAGECREW: StateTransition setNextState StateSendCarToTrack_P3
GARAGECREW: GAME EVENT [0] ERequest_ReturnToGarage_Inst
GARAGECREW: StateTransition setNextState StateCarIsReadyForTrack
```

## Two questions

1. **Is there a better way?** If `Game_DataDrivenCutSceneScript_FireEvent` with `STOP` is the right way to end a scene, I'll use that and need much less of the above. Are the grid scenes data-driven?
2. **Would a small cutscene event in the standard library suit you better?** Something like `cutscene.start` and `cutscene.end` with the name and a way to ask for a stop. That would cover this addon without exporting the internals.

Thanks for Swofty. The direct start and the test harness have saved a lot of time.
