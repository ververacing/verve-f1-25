# Phantom-brake detector: by-eye validation (2026-11-15)

The plan requires 2 races validated by eye before the detector is trusted. Races: stock check 4b
(`runs/2026-11-14-speed-skip-b`, menu route, difficulty 100) and B-0014 race 1 (run after the batch completed and was
scored, so there was no interim look). Tool: `tools/phantom_plots.py` (seed 1). It plots 5 flagged and 5 normal onsets
per race: speed and brake against lap distance, with the onset and the corner reference marked. Plots and CSVs are in
this folder.

## Round 1: the detector as merged in #88. FAILED

- **All 10 flagged onsets were false positives.** The AI *pulses* the brake inside a braking zone (0 to 1 many
  times), and every rise above 0.3 counted as a new onset: about 3,350 onsets per race, roughly 35 per car-lap at a
  track with about 7 braking zones. The field reference (the median of all clean onsets) therefore landed mid-zone,
  and a car braking at the real braking point looked 50-90 m early.
- **One flag was a wrap-around bug:** an onset 30 m *after* the corner was wrapped to "4,293 m early".
- The 10 normal onsets looked right.

## Fixes (this PR)

- **Onset = one per braking zone:** the first rise above 0.3 after the brake has been released (below 0.05) for at
  least 1.0 s. Onsets fell to about 500 per race (about 5 per car-lap).
- **Signed lap-distance difference** wrapped into +-half a lap, so an onset just after a corner is never "a lap early".
- New selftests for both. Selftest all passing.

## Round 2: after the fixes

| Race | Onsets scored (share) | Flagged | Flagged with a car within 1.0 s AHEAD | Flagged with clear road ahead |
|---|---|---|---|---|
| stock 4b | 500 (0.986) | 32 | 31 | 1 |
| B-0014 race 1 | 552 (0.989) | 35 | 34 | 1 |

- **Normal onsets:** 10/10 correct. Onset at the braking point, reference within about 10 m.
- **Flagged onsets:** the braking is genuinely early. Cars start braking 50-90 m before the field's clean-pass
  reference, mostly at the heavy stop at about 1,200-1,280 m and at turn 1 (about 290-350 m).
  - But 65 of 67 have a car within 1.0 s ahead, so they're in a train, and the earlier braking is explained by the
    car in front.
  - Several are lap-1 taps in the pack (Leclerc at turn 1 in 4b; Alonso at the heavy stop in race 1).

## Verdict

**The detector is now mechanically right, but its definition measures "early braking in traffic", not "sudden,
unexplained braking".** By the plan's goal 3 (braking that wrecks front wings), the train case is still relevant: the
car behind is the one at risk. But it isn't "unexplained".

**Proposal for a ruling:** split it into two metrics.
- `early_brake_in_traffic`: as now (> 50 m early, car within 1.0 s behind), restricted to a car within 1.0 s ahead.
  It's a train or follow metric, and the likely wing-damage risk.
- `phantom_brake`: the same, but with clear road ahead (no car within 1.0 s ahead, or 2.0 s to be stricter). It's
  the "unexplained" case, and rare in stock: 1 per race in both races.

Until the ruling, don't use phantom counts in any screen.
