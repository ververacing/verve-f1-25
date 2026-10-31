# Career fixtures

A fixture is a set of F1 25 save files that `swofty test` copies into the save sandbox before a run
(`"env": { "kind": "career", "fixture": "<name>", ... }`). The fixtures are built from Tyler's own profile, so
they hold his data: they live only in the local fixture store (`%LOCALAPPDATA%\Swofty\test-fixtures`) and are
never committed or uploaded. This folder holds what is needed to rebuild them.

## stroll-career-20261031

Driver Career at Team HQ, ready for the first race weekend. Used by `harness/tests/sandbox_check.test.json`
and the weekend/race routes that follow.

| | |
|---|---|
| Base | `tyler-profile-20261031` (Tyler's profile after the clean boot of 2026-10-31, no careers) |
| Mode | Driver Career, 2025 season |
| Wizard | Skip to F1, Full Season, Recommended settings (short sessions, unlimited rewinds, manual starts, reduced damage), Official Teams Only, Official Drivers Only |
| Player | Official driver Lance Stroll (#18), Aston Martin, teammate Fernando Alonso. Jack Doohan, the supervisor's first choice, is not in the 2025 driver list |
| Contract | The default offer, signed unchanged: target rating 78 (Stroll's current RTG), length Season 1, no team change. This keeps the grid stock |
| State | Team HQ overview, 19 February, time not advanced; saved with `save now` at `driver_hq_panel` |
| Built by | `tools/sandbox_shell.ps1`, run `2026-10-31-sandbox-28` (`shell-20261031-221431-1`), plan `career_stroll_create.plan`, then live `save now` |

The player car is driven by the AI in tests and is excluded from every arm and every field statistic.

Rebuild:

```bash
powershell -File tools/sandbox_shell.ps1 -Fixture tyler-profile-20261031 -Plan harness/fixtures/career_stroll_create.plan -Out runs/<id>
```

The plan ends on Team HQ. To keep the career, add `save now` as the plan's last step. Then capture it with
`swofty test fixture capture <name> --run <shell run> --career driver_career`. Steam Cloud must be off for
save-writing runs (docs/harness.md, "Save sandbox").

`frames/` holds the screens the plan was mapped from (downscaled, no gamertag).
