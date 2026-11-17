# D4 pre-registration: is the racecraft rating the GP reaction lever?

Status: **APPROVED (supervisor, 2026-11-17)**, with one ruling: the levels are **flat `evolution` curves at 0.05
(LOW) and 0.99 (HIGH)**, the same value at every season x = 0..10 (see "Levels" below; model expectation −0.103 s; the
PASS bar stands). The build check is key-only for the curve ops, as accepted (check 4). The seed 2026111704, the
imbalance check, the product note and the tooling list are approved as drafted. **D4 runs ONLY after a D1 PASS.**
Nothing is run yet. Written from repo files only (no game, launcher or `swofty` call); paths are repo-relative.
Evidence base: [verve_drivers_plan.md](verve_drivers_plan.md) ("After V-1", D4 outline),
[verve_d1_d2_prereg.md](verve_d1_d2_prereg.md) (D1), [verve_v1_prereg.md](verve_v1_prereg.md).

**Gate.** D4 runs only if **D1 PASSES**. If D1 fails, D4 waits until the measurement chain is fixed (D1's FAIL row).
D2 is stopped (D2.0: no sandboxed benchmark path, #174), so D4 is GP-only and doesn't depend on it.

## Purpose
A GP-only contrast for lead (b) of the desk research ([racecraft_research_2026-11-17.md](community/racecraft_research_2026-11-17.md)
§5, "Ratings-derived overrides"): GP may fill each car's trait override from the per-driver ratings through
`driver_statistics.driver_characteristic_overrides`. That would explain V-1's DEAD row result (F-48). If it holds, the
ratings, not the rows, are the GP personality lever.

## What the stock dump shows (checks 1-4)

**(1) Which statistic feeds which trait.** `docs/stock/driver_characteristic_overrides.txt` holds 6 rows (lines 4-5).
- `racecraft_reaction_speed`: `driver_statistic racecraft` → `driver_characteristic reaction_speed` (lines 11-15).
  Its distribution (line 13) is `@v2@minx:0,maxx:1,miny:0,maxy:1,0:0,0:0,0.25:0.25,0.75:0.75,1:1,1:1,1:1`, the
  **identity** on 0..1. Racecraft 0..1 maps to reaction_speed 0..1, so the spec's span assumption holds.
- **Racecraft also feeds aggression:** `racecraft_aggression` (lines 6-10), the same identity curve (line 8). No other
  row reads racecraft: awareness → control and mistakes (lines 16-25), pace → speed_in and speed_out (lines 26-35).
- So D4's lever moves reaction_speed **and** aggression together, if lead (b) is real. The primary (reaction) reads
  only reaction_speed (F-39: the reaction draw depends on reaction_speed alone; B-0010 found no cross terms). The pass
  secondaries carry the aggression channel too, and that's why they're not scored.
- The same table on 26566308: identical to 25251167 (`docs/stock/README_26566308.md`:44-45, :93).

**(2) The rating's range and how it's stored.** A rating is a **curve, not a single value**.
- Field `evolution` on each `Statistic`, e.g. Alonso's racecraft, `default` set:
  `@v2@minx:0,maxx:10,miny:0,maxy:100,0:0.9,0:0.9,0.5:0.88,1:0.7,1:0.7` (`docs/stock/stats_fernando_alonso.txt`:26-29).
  x is seasons 0..10 (F-26) and y is the rating, both stored normalised: y = rating/100 (`HANDOFF.md`:83).
- **Scale:** min 0, max 100 by the curve's own header (`miny:0,maxy:100`), so stored y 0.0 to 1.0. The repo has no
  separate clamp for ratings.
- **"Season x=0" is the first point(s) at x=0, and it can be ambiguous.** Some curves carry two points at x=0 with
  different y. Alonso's `2026` set is `0:0.9,0:0.87,...` (`stats_fernando_alonso.txt`:58) and Bearman's is
  `0:0.84,0:0.88,...` (`stats_oliver_bearman.txt`:58). Verstappen's has a single x=0 point
  (`0:0.96,0.2:0.9,...`, `stats_max_verstappen.txt`:28). Which point, and which x, GP evaluates is unknown.
- **Stock racecraft at x=0 (first point, `default`, build 25251167), 12 of the 19 AI drivers:** Verstappen 0.96
  (`stats_max_verstappen.txt`:28), Alonso 0.90 (`stats_fernando_alonso.txt`:28), Bearman 0.84
  (`stats_oliver_bearman.txt`:28), and the `stock_curve` column of `harness/addons/verve.b0006/arms.csv` and
  `verve.b0008/arms.csv` (the "stock racecraft curve", `runs/2026-10-30-B-0008/summary.md`:6): Piastri 0.92,
  Russell 0.92, Norris 0.89, Gasly 0.88, Ocon 0.86, Hulkenberg 0.86, Tsunoda 0.78, Bortoleto 0.76, Hadjar 0.66.
  Known range: 0.66-0.96.
- **Not in the repo:** Leclerc, Hamilton, Antonelli, Albon, Sainz, Colapinto and Lawson. On 26566308 only the three
  `stats_*.txt` were re-checked (identical, `README_26566308.md`:92); the full ratings dump was stopped (:103-105). The
  D4 key-cache prefill (tooling, below) records all 19 stock curves on 26566308 as a side effect.

**(3) The op paths.** One op per driver per dataset, as B-0001 wrote them (`harness/addons/verve.b0001/db/b0001.json`:27-38):
- select `driver_statistics.driver_statistics.DriverStatisticsHolder[driver=<row label>].StatisticsDataSet[_metadata_=default].Statistic[_metadata_=racecraft]`, field `evolution`;
- the same with `StatisticsDataSet[_metadata_=2026]`.
- `[driver=...]` matches the holder's `driver` field, which equals the row label (F-32 correction;
  `docs/stock/statistics_datasets.csv`:1). Albon's holder is `alexander_albon` but `driver alex_albon` (line 18).
- All 19 AI drivers' holders have exactly `default|2026` (`statistics_datasets.csv`, lines 4, 6-11, 13-20, 23, 31, 33,
  38: `has_2026 True`). Those are every StatisticsDataSet a GP on these rows could read.

**(4) Can the build check verify them? Only by key, not by value.** `evolution` is a curve (tag 9), and the
loader.log line for a changed curve shows only `record at <address>` (`tools/check_applied.ps1`:10-11, :94). The check
confirms each op hit the right key (an overwrite line for its hash), and a flat curve never equals stock, so a
missing line is a MISSING problem (:96-97). **It can't confirm the value written.** The value rests on the generator
(`expected_ops.csv`, its selftest) and B-0001/B-0006's format, which loaded (64 overwritten,
`runs/2026-10-30-B-0001/summary.md`:11). A value readback would need D3-style access, which isn't approved. The key
cache (`docs/stock/v1_key_cache_26566308.csv`) holds 0 `driver_statistics` paths today, so it needs a prefill.
**Key-only is accepted** (supervisor, 2026-11-17).

**Value readback with `swofty db get`: skipped (db get reads stock for data add-ons).** The supervisor asked for one
`db get` on verve-test with the D4 add-on enabled, on one HIGH and one LOW holder, if cheap. It can't show a data
add-on's ops:
- The repo: `tools/check_applied.ps1`:8 ("`swofty db get --addon` only applies DB Editor addons, not data addons"),
  which is why #53 (commit 5fc16c2) replaced the `db get --addon` build check (`tools/check_build.ps1`) with the
  loader.log check. `HANDOFF.md`:176: `db get <path>` without `--addon` prints stock.
- Swofty's public source (SwoftyLauncher, commit c01366b, read-only shallow clone, deleted after):
  `docs/reference/cli.md`:207 and :217 ("`swofty db get` without `--addon` shows stock values");
  `apps/cli/src/db.rs`:405-409 (`db get` takes its edits only from `--addon` through `open()`, else none) and :222-226
  (`open()` refuses any id that isn't a DB Editor addon: "no DB Editor addon named {id}");
  `packages/core/src/dbedit/package.rs`:20, 24, 97-99 (a DB Editor addon has the `dbedit.` id prefix and a
  `dbedit.json` marker; `verve.d4-l<LL>` has neither); `packages/core/src/dbedit/catalog.rs`:593-596 (the values come
  from the stock database file).
- So enabling the add-on in verve-test changes nothing that `db get` reads (the profile isn't consulted), and
  `db get --addon verve.d4-l<LL>` fails. A readback would print the stock curve, which proves nothing. The value rests
  on the generator and its selftest (the flat curve parses back to the level at every x), as accepted.

## Levels (the supervisor's ruling, 2026-11-17)
"The rating's minimum / maximum" is defined as a **flat** `evolution` curve, the same value at every season x = 0..10,
in both datasets: **LOW 0.05, HIGH 0.99** (not 0 and 1: no special treatment of 0 or the scale ends, and it matches
B-0001/B-0006). The exact strings are B-0001's (`harness/addons/verve.b0001/db/b0001.json`:31 and :55):
- LOW: `@v2@minx:0,maxx:10,miny:0,maxy:100,0:0.05,0:0.05,1:0.05,1:0.05`;
- HIGH: `@v2@minx:0,maxx:10,miny:0,maxy:100,0:0.99,0:0.99,1:0.99,1:0.99`.

The header keeps the stock axes (x seasons 0..10, y 0..100). The points are stored normalised: x 0 → 1 spans seasons
0 → 10 and y = rating/100, as every stock curve does (they all end at x = 1, e.g. `stats_fernando_alonso.txt`:28). A
flat curve gives the same value at every season x and at both x=0 points, so the open questions in (2) don't matter.

## Design
- **Lever:** per launch, in each of the 9 two-AI teams (v1_make's TEAMS), a seeded coin sets one teammate's racecraft
  to HIGH and the other's to LOW, in both `default` and `2026`. Alonso (no AI teammate) stays stock and isn't scored.
  That gives 9 HIGH and 9 LOW cars, **36 ops** (18 drivers × 2 datasets), and a new draw per launch. **No other
  writes:** no rows, no other ratings, no `driver_characteristic_overrides`, no maps, no `ai_driver_config`.
- **Seed:** **2026111704** (approved), fixed and recorded before D4's first launch; the seed string is
  `verve-d4|{seed}|{launch}`, distinct from D1's. `assignment.csv` is written per launch.
- **Size:** 2 launches × 4 races, 5 laps, Austria, on V-1's plan `harness/sessions/v1_austria_4races.plan` with the
  race-1 session check (`@sessioncheck`, line 195). That's about 70 min. The launcher is D1's (1.9.63); if it changes,
  the stock route check is rerun first.
- **Validity:** the same as V-1/D1: aionly_check per race uid, the session check, the per-launch build check
  (check_applied: all 36 ops applied, key-checked), gamedb = the route baseline (56) + 36, weather LOCKED, the saves
  guard, profile verve-test only, and the tyler.json hash unchanged.

## Measures and decision
- **Primary (per launch):** UDP reaction (V-1/D1: LGOT arrival to the first LapData totalDistance gain ≥ 0.3 m,
  60 Hz, relative only). Each car's mean over the launch's valid races first, then the mean over HIGH cars minus the
  mean over LOW cars.
- **Model expectation:** **−0.103 s**. The mean reaction is 0.35 − 0.21·k·rs with k ≈ 0.52 (F-36 implications;
  F-39's U[0.28 − 0.24k·rs, 0.42 − 0.18k·rs]), so the ruled 0.05 → 0.99 span (0.94, through the identity
  `racecraft_reaction_speed`) gives −0.21 × 0.52 × 0.94 = −0.103 s. k was fitted on 25251167 (benchmark) and isn't
  re-checked on 26566308.
- **Decision:**
  - **PASS:** the difference is ≤ −0.05 s in **both** launches.
  - **NULL:** |difference| < 0.02 s in **both** launches.
  - Otherwise **INCONCLUSIVE**.
- **Operating characteristics** (context only, not a rule): V-1's per-launch between-car SD of reaction means is
  about 0.032 s (`runs/2026-11-17-V1/v1_check/per_driver_launch.csv`, 12 launches), so a 9-vs-9 difference has an SE
  of about 0.015 s. At −0.103 s PASS is near-certain. At 0, a false PASS has a chance under 1 in a million, and NULL comes
  out about 2 times in 3.
- **Row imbalance (diagnostic, not scored):** the rows stay stock, so a draw can unbalance the stock row
  reaction_speed between HIGH and LOW. The worst case over all draws is 0.12
  (`docs/stock/driver_characteristics_grid.csv`). Under "rows win" that's at most ±0.013 s, and V-1 found the row DEAD
  in GP. d4_check prints it per launch.
- **Secondaries, not scored:** passes made and passes suffered (net held, laps 2+, V-1's definition), and lap-1 gain
  (`gain_lap1`), HIGH minus LOW, the same way. They also carry racecraft's aggression channel (check 1).

## Prior evidence
- **B-0006** (benchmark, 25251167): the STATS (racecraft rating) slope on reaction was **+0.068 s/unit (SE 0.029)**,
  against the row's **−0.109** (`runs/2026-10-30-B-0006/summary.md`:17-18, `slopes.csv`). It read as confounded by
  the STATS drivers' untouched rows, with +0.039 predicted under "rows win" (:56-60). **B-0001:** the STATS pair gap
  was −0.039 s, reversed (`runs/2026-10-30-B-0001/summary.md`:28; F-35). So in benchmark the rating didn't act like the
  trait (F-36: "not proven absent").
- **V-1** (F-48): the `driver_characteristics` trait rows were DEAD in GP on 26566308. reaction_speed's FE slope was
  −0.0061 s (SE 0.0038), against about −0.11 in benchmark. Lead (b) is one candidate explanation.

## How the outcomes read
| D4 | Reading |
|---|---|
| PASS | In GP, racecraft drives the start reaction through `racecraft_reaction_speed`: lead (b) holds for this pair. The ratings are the GP lever. Next: the awareness and pace pairs (the D4 outline's factorial) and the product decision below. |
| NULL | The racecraft rating doesn't reach reaction in GP either. Lead (b) is unsupported for this pair, and leads (a) and (c) remain. |
| INCONCLUSIVE | Reported as is; the supervisor rules on a follow-up. |

## Product note (for the build design)
Ratings are what the career and ratings screens show (`HANDOFF.md`:83; F-26). `verve_build_design.md` §1 (lines
18-23) drops all rating writes because database ops can't be limited to game modes, so they would reach careers. §6
(lines 154-155) relies on Verve not writing ratings to avoid colliding with Silly Season, F2 Revamp and Progressive,
which write statistic curves. A D4 PASS reopens both points. D4 itself runs only in verve-test, and its add-on is
removed after each launch.

## Tooling (approved as listed; built on the branch `d4-tooling`)
- **`tools/d4_make.py`**, modelled on d1_make.py: a pure `draw(seed, launch)` (the teammate coin, Alonso stock), the
  add-on `verve.d4-l<LL>` (36 curve ops, LOW 0.05 / HIGH 0.99 flat, as ruled), `assignment.csv`, `expected_ops.csv`,
  `--paths` and `--selftest`.
- **`tools/v1_run.ps1 -Make d4`**: the same install, enable, remove, hash, build and session checks; ValidateSet adds
  `d4`.
- **Key cache:** `docs/stock/d4_paths.txt` (the 38 racecraft paths of the 19 AI drivers; Alonso's 2 for the stock
  record only), filled by `check_applied.ps1 -PrefillOnly` with read-only `db get --profile verve-test` calls, with
  nothing running (after D1). This also records the 26566308 stock curves (check 2).
- **`tools/d4_check.py`**, modelled on d1_check.py: the same validity by import; primary HIGH − LOW; the PASS / NULL /
  INCONCLUSIVE rule above; the secondaries; the row-imbalance diagnostic; NOT SCORED for a partial batch.

No interim looks. Nothing is called a result before the supervisor's review.
