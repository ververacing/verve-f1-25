# C-1: start calibration, start-only route, GP Austria: offset CONSTANT (supervisor: accepted 2026-11-17)

Pre-registered in [docs/verve_c1_prereg.md](../../docs/verve_c1_prereg.md) (#179, scoring details in #180), scored
with `tools/c1_check.py`. Seed **2026111705**, 2 launches × 20 start-only starts (race 1 plus 19 restarts, each ended at
lights out + 20 s), launcher 1.9.63, game build 26566308. The stock smoke test (`runs/2026-11-17-C1-smoke`, 4 starts)
PASSED first.

**Lever:** all four `ai_driver_config.race_start` reaction bounds pinned per car to 0.20, 0.35 or 0.65 s, or left stock,
rotated by launch (teammates never in the same arm; Alonso stock). 56 / 52 ops.

## Result

| Level | UDP reaction, launch 1 | launch 2 |
|---|---|---|
| stock | 0.468 s | 0.453 s |
| 0.20 | 0.486 s | 0.485 s |
| 0.35 | 0.632 s | 0.635 s |
| 0.65 | 0.936 s | 0.933 s |

- **Line:** slope 1.0018 / 0.9951, pooled **0.9985** (SE 0.0034), intercept **0.2851 s**. The offsets per level are
  0.283-0.286 s. **Offset: CONSTANT** (1 ± 0.1 in both launches and pooled).
- **Shape: LINEAR**, with the 0.35 level −0.003 / +0.000 s off the chord. **Low end: RESOLVED** (0.35 − 0.20 =
  0.147 / 0.149 s).
- **Reproduction** (not scored): the 0.65 level read 0.9358 / 0.9330 s against D1's 0.9363 s, within one frame.
- **Validity:** 40/40 starts valid (the start-only check, with "finish checks: not applicable (start-only)" on each).
  The session check was live in both launches. Build checks 56/56 and 52/52 value-checked, gamedb 112 / 108. tyler.json
  was restored, the saves unchanged, the weather LOCKED.

## Not scored (for V-2)

- **Stock:** 220 car-starts. UDP reaction min 0.334, median 0.468, max 0.585 s. The per-start fastest stock car's median
  is 0.385 s. Through the line, that's a game-time **median of about 0.18 s**, the fastest per start about **0.10 s**,
  and the slowest about **0.30 s**.
- **launch_m is NOT pure delay:** the level means span 0.53-0.61 m, with no clean order. So launch distance is a separate
  input.
- **Speed at 1 s** falls with the pinned delay (about 19 → 16 → 11 km/h at 0.20 → 0.35 → 0.65). Gain to T1 at 0.65 was
  −1.84 / −0.63 places.

## Reading (F-51)

UDP start reaction = game-time race_start reaction + 0.285 s (slope 0.998 ± 0.003, linear and resolved over
0.20-0.65 s; below 0.20 s untested). Stock draws have a game-time median of about 0.18 s, so a 0.20 pin is slower than
the stock median. The "offset grows" hypothesis from D1 is **refuted**: D1's larger effect came from the stock draws
being shorter than assumed.
