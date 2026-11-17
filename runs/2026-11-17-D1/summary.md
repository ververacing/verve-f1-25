# D1: positive control in GP (spectator route, Austria): PASS (supervisor: accepted 2026-11-17)

Pre-registered in [docs/verve_d1_d2_prereg.md](../../docs/verve_d1_d2_prereg.md) (#170), scored with
`tools/d1_check.py` (#172). Seed **2026111701**, 2 launches × 4 races, 5 laps, launcher 1.9.63, game build 26566308.

**Lever:** all four `ai_driver_config.race_start` reaction bounds pinned to **0.65 s** on one teammate per two-AI team
(a seeded coin; Alonso stock), so 9 pinned and 10 stock cars per launch. No other writes (36 ops).

## Result

| Launch | Valid races | Pinned UDP reaction (9 cars) | Stock (10 cars) | Pinned − stock | Bar |
|---|---|---|---|---|---|
| 1 (01:34-02:10) | 4 / 4 | +0.936 s | +0.469 s | **+0.467 s** | ≥ 0.12: pass |
| 2 (attempt 3, 03:44-04:19) | 4 / 4 | +0.936 s | +0.483 s | **+0.453 s** | ≥ 0.12: pass |

**D1 primary: PASS** (≥ 0.12 s in both launches).

- **Sanity check:** the pinned cars read an identical **0.936 s** in both launches. With all four bounds collapsed to
  0.65, the game's reaction draw is deterministic, so its UDP mean shouldn't move between launches, and it didn't. The
  stock cars, which still draw at random, move a little (0.469 vs 0.483).
- **Secondaries, not scored:** pinned − stock speed at 1 s was −8.18 / −7.60 km/h, and gain to T1 −1.85 / −1.64 places.
  That's B-0012b's exploratory signal, reproduced in GP on 26566308.
- **Build check, both launches:** 36/36 ops applied and all value-checked, 0 dropped, 0 problems; gamedb 92 = 56 + 36.
- **Safety:** tyler.json was restored (hash as before the install) in both launches. The saves were unchanged, the
  weather LOCKED, the session check ok, with no skip-relaunch and no display fallback.
- **Launch 2, attempts 1-2** (02:10, 02:15) are in `invalid\` and not analysed. Both stopped in the menus: `home` timed
  out because the game raised `ServerStatus_AccessDeniedWithCustomMessage` again and again, during an **EA-side F1 25
  server outage** (EA's server-status page read "Server Outage" at 02:25 PT). The 03:23 stock route check
  (`runs/2026-11-17-routecheck-0330`) was clean, and attempt 3 ran.

## Reading (per the prereg)

The measurement chain works, and per-driver `ai_driver_config` rows reach the AI in GP on 26566308. So V-1's
reaction_speed null (F-48) isn't a broken chain or route; it's specific to the `driver_characteristics` path (**F-49**).

## Hypothesis: REFUTED by C-1 (2026-11-17)

The effect (+0.46 s) was larger than the +0.25-0.35 s expected. The hypothesis was that the offset grows with
reaction (a later reaction also giving a slower first motion to the 0.3 m threshold).

**C-1 refuted it** (`runs/2026-11-17-C1`, F-51): the UDP reaction is game time + a CONSTANT 0.285 s (slope 0.998). The
bigger D1 effect came from the stock draws being shorter than assumed. Their game-time median is about 0.18 s, not
0.28-0.42 s, so a 0.65 pin is about 0.47 s later than a typical stock draw.
