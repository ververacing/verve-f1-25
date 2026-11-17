# D4: racecraft rating, flat 0.05 vs 0.99, in GP (spectator route, Austria): NULL (supervisor: accepted 2026-11-17)

Pre-registered in [docs/verve_d4_prereg.md](../../docs/verve_d4_prereg.md) (#175), scored with `tools/d4_check.py`
(#177). Seed **2026111704**, 2 launches × 4 races, 5 laps, launcher 1.9.63, game build 26566308.

**Lever:** the per-driver racecraft rating's `evolution` curve set FLAT at 0.99 (HIGH) for one teammate and 0.05 (LOW)
for the other, in both `default` and `2026` StatisticsDataSets (B-0001's exact curve strings). Alonso stock. No other
writes (36 ops). Model expectation (racecraft → reaction_speed, the identity curve): −0.103 s.

| Launch | Valid races | HIGH (9 cars) | LOW (9 cars) | HIGH − LOW | Rule |
|---|---|---|---|---|---|
| 1 (04:19-04:55) | 4 / 4 | +0.476 s | +0.463 s | **+0.013 s** | \|diff\| < 0.02 |
| 2 (04:56-05:31) | 4 / 4 | +0.473 s | +0.456 s | **+0.017 s** | \|diff\| < 0.02 |

**D4 primary: NULL** (\|HIGH − LOW\| < 0.02 s in both launches).

- **Secondaries, not scored, mean of the launches:** passes made +0.06/race, passes suffered +0.11/race, lap-1 gain
  −0.08 places (HIGH − LOW). No sign either.
- **Row imbalance (diagnostic):** the stock reaction_speed rows of HIGH vs LOW drivers differ +0.011 / −0.024, which
  would be worth at most ±0.003 s even if rows acted. Negligible.
- **Build check, both launches:** 36/36 curve ops at the right keys. That's key-only, as approved: `db get` reads stock
  for data add-ons, so the values can't be read back. 0 dropped, gamedb 92 = 56 + 36.
- **Safety:** tyler.json was restored in both launches, the saves were unchanged and the weather LOCKED, the session
  check ok, with no skip-relaunch and no display fallback.

## Reading (F-50)

With V-1 (F-48) and D1 (F-49): in GP, the start reaction follows the per-driver `ai_driver_config` race_start bounds,
while neither the reaction_speed trait override nor the racecraft rating moved it. Whether ratings act on anything else
(pace, other behaviour) is untested.

**Working hypothesis, not a finding:** in GP the reaction draw is driven by the race_start bounds, not by the effective
reaction_speed trait.
