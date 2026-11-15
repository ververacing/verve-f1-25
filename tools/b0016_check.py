"""Validity and scoring for B-0016 (#101): stock (A, odd races) vs swofty.lap1-ai (B, even races), lap-1 race feel.

Usage:
    python -I tools/b0016_check.py --validity runs/<batch>/race_<n>   # one race's validity, no scoring
    python -I tools/b0016_check.py runs/<batch>                       # score, after the last race only (#101)
    python -I tools/b0016_check.py --selftest

Reads each race's udp/sessions.csv and events.csv, raw/loader.log, addons.json and race_feel/race_feel_summary.json
(written by tools/b0016_run.ps1 from tools/race_feel.py). The rules are #101's v3, fixed before any data:
  verdict on P3 (lap1_held_changes per race): effect = mean(B) - mean(A), SE from a bootstrap over races within each
  arm (2000, seed 1). PASS: effect > 0, its 2-SE interval excludes 0, and lap1_costly_contacts are not up by >= 2 SE.
  FAIL-NULL: the 2-SE interval lies within +-4. INCONCLUSIVE otherwise (a significant decrease is "opposite to the
  README's claim"). P1 (lap1_loss_median_s) and P2 (lap1_spread_s) are reported with 2-SE intervals, outside the verdict.
Exit 0 PASS, 1 FAIL-NULL, 2 INCONCLUSIVE, 3 not enough valid races (or one race INVALID with --validity).
"""
from __future__ import annotations

import csv
import json
import random
import re
import statistics
import sys
from pathlib import Path

PLAYER_CAR = 19
EXPECT_OVERWRITTEN = 52
EXPECT_DIFFICULTY = "100"
ADDON = "swofty.lap1-ai"
BOOTSTRAPS, BOOT_SEED = 2000, 1
NULL_BAND = 4.0
GAMEDB = re.compile(r"gamedb: (\d+) overwritten")
LAP1AI = re.compile(r"lap1[-_]ai", re.I)
PRIMARY = "lap1_held_changes"
CO_PRIMARIES = ("lap1_loss_median_s", "lap1_spread_s")
GUARD = "lap1_costly_contacts"
SECONDARY = ("lap1_collisions", "held_passes_net_2plus", "train_time_share", "longest_train_median",
             "early_brakes_total", "front_wing_increments", "median_green_lap_s")


def read_csv(path: Path) -> list[dict]:
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def arm_of(run: Path) -> str:
    return "A" if int(run.name.split("_")[1]) % 2 == 1 else "B"


def load_race(run: Path) -> tuple[dict, list[str]]:
    """The race's summary values, and why it's invalid (empty if valid)."""
    arm = arm_of(run)
    invalid: list[str] = []
    try:
        sessions = [s for s in read_csv(run / "udp" / "sessions.csv") if s["session_type"] == "race"]
        events = read_csv(run / "udp" / "events.csv")
        log = (run / "raw" / "loader.log").read_text(encoding="utf-8", errors="replace").splitlines()
        summary = json.loads((run / "race_feel" / "race_feel_summary.json").read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        return {}, [f"missing data: {e}"]
    if len(sessions) != 1:
        return {}, [f"{len(sessions)} race sessions in UDP"]
    uid = sessions[0]["session_uid"]
    events = [e for e in events if e["session_uid"] == uid]

    db = next((m for m in map(GAMEDB.search, log) if m), None)
    if not db or int(db[1]) != EXPECT_OVERWRITTEN:
        invalid.append(f"gamedb {db[1] if db else 'none'} overwritten, expected {EXPECT_OVERWRITTEN}")
    try:
        addons = set(json.loads((run / "addons.json").read_text(encoding="utf-8")))
    except (OSError, ValueError):
        addons = None
    want = {ADDON} if arm == "B" else set()
    if addons != want:
        invalid.append(f"addons {sorted(addons) if addons is not None else 'unknown'}, expected {sorted(want)}")
    l1 = [line for line in log if LAP1AI.search(line)]
    if arm == "B" and not l1:
        invalid.append("B race, but loader.log has no lap1-ai lines")
    if arm == "A" and l1:
        invalid.append(f"A race, but loader.log has {len(l1)} lap1-ai line(s)")
    difficulty = sessions[0].get("ai_difficulty", "")
    if difficulty != EXPECT_DIFFICULTY:
        invalid.append(f"AI difficulty reads {difficulty or 'nothing'}, expected {EXPECT_DIFFICULTY}")
    player = int(sessions[0]["player_car"])
    if player != PLAYER_CAR:
        invalid.append(f"player is car {player}, not {PLAYER_CAR}")
    if not any(e["code"] == "CHQF" for e in events):
        invalid.append("no chequered flag")
    if (run / "pause_cut.txt").exists():
        invalid.append("PAUSE cut")
    vals = {k: summary.get(k) for k in (PRIMARY, GUARD, *CO_PRIMARIES, *SECONDARY)}
    vals["dnfs"] = (summary.get("guards") or {}).get("dnfs")
    vals["lap1ai_lines"] = len(l1)
    for k in (PRIMARY, GUARD, *CO_PRIMARIES):
        if vals[k] is None:
            invalid.append(f"race_feel has no {k}")
    return vals | {"race": run.name, "arm": arm}, invalid


def diff(races: list[dict], key: str) -> float:
    a = [r[key] for r in races if r["arm"] == "A" and r.get(key) is not None]
    b = [r[key] for r in races if r["arm"] == "B" and r.get(key) is not None]
    if not a or not b:
        return float("nan")
    return statistics.mean(b) - statistics.mean(a)


def bootstrap_se(races: list[dict], key: str) -> float:
    rng = random.Random(BOOT_SEED)
    a = [r for r in races if r["arm"] == "A"]
    b = [r for r in races if r["arm"] == "B"]
    values = []
    for _ in range(BOOTSTRAPS):
        v = diff([rng.choice(a) for _ in a] + [rng.choice(b) for _ in b], key)
        if v == v:
            values.append(v)
    return statistics.pstdev(values) if len(values) > 1 else float("nan")


def decide(races: list[dict]) -> tuple[str, dict]:
    eff, se = diff(races, PRIMARY), bootstrap_se(races, PRIMARY)
    g, gse = diff(races, GUARD), bootstrap_se(races, GUARD)
    cost = g > 0 and g >= 2 * gse
    lo, hi = eff - 2 * se, eff + 2 * se
    out = {"effect": eff, "se": se, "lo": lo, "hi": hi, "guard": g, "guard_se": gse, "cost": cost}
    if eff > 0 and lo > 0 and not cost:
        return "PASS", out
    if lo >= -NULL_BAND and hi <= NULL_BAND:
        return "FAIL-NULL", out
    return "INCONCLUSIVE", out


def selftest() -> int:
    def fake(effect: float, seed: int, guard_up: float = 0.0) -> list[dict]:
        rng = random.Random(seed)
        return [{"race": f"race_{i + 1}", "arm": "A" if i % 2 == 0 else "B",
                 PRIMARY: 18.9 + (effect if i % 2 else 0) + rng.gauss(0, 2.76),
                 GUARD: max(0, round(rng.gauss(0.24 + (guard_up if i % 2 else 0), 0.5)))} for i in range(12)]
    v1, o1 = decide(fake(8.0, 1))
    v0, o0 = decide(fake(0.0, 2))
    vc, oc = decide(fake(8.0, 3, guard_up=4.0))
    vn, on = decide(fake(-8.0, 4))
    print(f"effect +8: {v1} ({o1['effect']:+.2f} +- {o1['se']:.2f}); effect 0: {v0} ({o0['effect']:+.2f} +- {o0['se']:.2f}); "
          f"+8 with a costly-contact rise: {vc} (cost {oc['cost']}); effect -8: {vn}")
    ok = v1 == "PASS" and v0 != "PASS" and vc != "PASS" and oc["cost"] and vn == "INCONCLUSIVE"
    print("selftest", "ok" if ok else "FAILED")
    return 0 if ok else 1


def main() -> int:
    args = sys.argv[1:]
    if "--selftest" in args:
        return selftest()
    validity = "--validity" in args
    args = [a for a in args if a != "--validity"]
    if len(args) != 1 or args[0].startswith("--"):
        print(__doc__)
        return 3
    if validity:   # one race: validity only, no metrics printed (no interim analysis, #101)
        run = Path(args[0])
        vals, invalid = load_race(run)
        print(f"  {run.name} (arm {arm_of(run)}): lap1-ai lines in loader.log {vals.get('lap1ai_lines', '?')}")
        for why in invalid:
            print(f"  INVALID: {why}")
        print("  RESULT: INVALID, discard and rerun" if invalid else "  RESULT: VALID")
        return 3 if invalid else 0
    runs = sorted((p for p in Path(args[0]).glob("race_*") if p.is_dir()), key=lambda p: int(p.name.split("_")[1]))
    races = []
    for run in runs:
        vals, invalid = load_race(run)
        print(f"{run.name} (arm {arm_of(run)}): {'VALID' if not invalid else 'INVALID: ' + '; '.join(invalid)}")
        if not invalid:
            races.append(vals)
    na, nb = sum(r["arm"] == "A" for r in races), sum(r["arm"] == "B" for r in races)
    print(f"\n{len(races)} valid of {len(runs)} races (A {na}, B {nb})")
    if na < 2 or nb < 2:
        print("not enough valid races in both arms to score")
        return 3
    verdict, o = decide(races)
    print(f"\nPrimary P3, lap-1 held changes (net) per race: B - A {o['effect']:+.2f}, bootstrap SE {o['se']:.2f}, "
          f"2-SE interval [{o['lo']:+.2f}, {o['hi']:+.2f}] (null band +-{NULL_BAND:g})")
    print(f"Guard, lap-1 costly contacts: B - A {o['guard']:+.2f} (SE {o['guard_se']:.2f}){'  COST: up by >= 2 SE, blocks PASS' if o['cost'] else ''}")
    for k in CO_PRIMARIES:
        e, s = diff(races, k), bootstrap_se(races, k)
        print(f"Co-primary {k}: B - A {e:+.3f}, SE {s:.3f}, 2-SE [{e - 2 * s:+.3f}, {e + 2 * s:+.3f}]")
    for k in (*SECONDARY, "dnfs"):
        e = diff(races, k)
        print(f"Secondary {k}: B - A {e:+.4f}" + (f" (SE {bootstrap_se(races, k):.4f})" if e == e else ""))
    print("\nPer race (arm, P3, guard, P1, P2):")
    for r in races:
        print(f"  {r['race']}: {r['arm']} {r[PRIMARY]} {r[GUARD]} {r['lap1_loss_median_s']} {r['lap1_spread_s']}")
    if verdict == "INCONCLUSIVE" and o["hi"] < 0:
        print("NOTE: a significant decrease: opposite to the README's claim")
    print(f"\nRESULT: {verdict}")
    return {"PASS": 0, "FAIL-NULL": 1, "INCONCLUSIVE": 2}[verdict]


if __name__ == "__main__":
    sys.exit(main())
