# Direct start: setting difficulty, safety car and formation lap (research, 2026-11-14)

The supervisor's item 3. Desk research only, from files already copied out of Swofty: the 2026-11-14 pilot and
check-4b `loader.log`s (Swofty 1.9.51, build 25251167), plus `docs/community/source_insights.md`. **Nothing is built
or run.** The goal is a direct start (9.7 min per race) that's usable for behaviour batches: AI difficulty 100, no
early safety car, and a known formation-lap setting.

## What the direct start does today

From the pilot's `[direct]` log lines:
- It builds a new Grand Prix weekend itself: setup mode `f1`, entrant list `f1_2025`, the track, the weekend
  structure (practice 0, qualifying 0, race 7), the player's seat, and `race laps 18 -> 5`.
- It never goes through the hub's settings screen (`settings_container`), where the menu route sets difficulty 100.
  So difficulty, safety car and formation lap come from whatever the options store and the rule-settings profiles
  hold when the session loads. The pilot read difficulty 19 (the fixture profile's value) and had a full safety
  car 3.1 s after lights out.
- `swofty test session --help`: "`weather=` and `ai_difficulty=` are not applied yet."

## What Swofty 1.9.51 already binds (from `[core] bind ...` lines; names only)

| Area | Bound functions and globals |
|---|---|
| Options store (the route Starting Grid uses) | `g_Game_OptionsStore`, `Game_OptionsStore_FindOption`, `Game_OptionsSystem_ResolveOptionValue`, `Game_FakeOption_SetValue`, `Game_FakeOption_GetMaxIndex` |
| Options into the session | `Sess_CopyOptionsToState`, `Game_ChampionshipGameMode_BuildSessionSettings`, `Game_SessionSettings_Reset`, `Game_SessionSettings_SetSessionId` |
| Session rules | `Sess_Load_RuleSettingsProfiles`, `Sess_Rules_ReadFormationLapMiniGame`, `Sess_Rules_ReadCollisionSettings`, `Sess_Rules_ReadCornerCuttingSettings`, `Sess_Rules_ReadSafetyCarPacePenalties`, ... |
| Safety car | `Sess_SafetyCar_ReadDeploymentFrequency`, `Sess_Set_SafetyCarDeploymentType`, `Sess_Build_SafetyCarLogicGraph`, `Sess_SafetyCarLogic_Subscribe`, `k_Live_SafetyCarLogicSystemKey` |
| Formation lap | `Sess_FormationLapLogic_*` (Construct, IsActiveType0, IsActiveOtherType, Reset, Update, ...), `Sess_FormationLapType_Update`, `Sess_Registry_GetFormationLapLogic` |

So the readers for the safety-car frequency and deployment type, the formation-lap logic and the options-to-session
copy are all resolved on this build (`verified=yes`).

## Design (not built): a small native `verve.harness` addon

1. **Set options by name, as Starting Grid does** (`menu_option.hpp:16-96` in constructor-mods/starting-grid):
   `g_Game_OptionsStore` -> `FindOption(<name>)` -> vtable get (2) / set (3), "as if the player picked it". Do it
   after the profile loads and before `Game_ChampionshipGameMode_BuildSessionSettings` / `Sess_CopyOptionsToState`
   copy the options into the session. Swofty's `[direct] session start: setting up the target` is the right moment.
2. **Options to set:** AI difficulty = 100; safety car = off (or the lowest frequency, if "off" changes other rules);
   formation lap = as the batch registers it. Read each value back (log it, and from UDP: Session packet difficulty
   byte, safety-car status byte at body+124, formation via `race.start` / LGOT timing) and fail the run if it differs.
3. **Only in test profiles,** gated on the `swofty test` environment, never in Tyler's profile.

## What's still unknown (needs the game DB, read-only, with the game closed)

- **The option names themselves** (the `options_system` tables): AI difficulty, safety car, formation lap, and their
  value ranges. Next step after RESUME, with the game closed: read-only `swofty db` queries on the options tables,
  saved to `docs/stock/options_system_*.txt`.
- **Why the direct start had a safety car** when the menu route never did (0 SCAR events in 5 menu races). Not a
  parked player car: it moved with the field (3 m/s at +0.75 s). Candidates: a different safety-car frequency or
  deployment type in the options the direct start inherits, or a rules profile only the menu flow sets.
  `Sess_SafetyCar_ReadDeploymentFrequency` and `Sess_Set_SafetyCarDeploymentType` are where to log the values.
- Whether setting an option before `BuildSessionSettings` is enough, or whether the session reads a cached copy.
