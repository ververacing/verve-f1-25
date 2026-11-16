"""Validity and scoring for B-0015 (#100 v4): per-driver blocking.max_blocking_distance, 45 vs 5, within-driver crossover.

Usage:
    python -I tools/b0015_check.py --validity runs/<batch>/race_<n>   # one race's validity, no scoring
    python -I tools/b0015_check.py runs/<batch>                       # score, after the last race only (#100)
    python -I tools/b0015_check.py --selftest

Odd races are order a (verve.b0015a: G1 = 45, G2 = 5), even races order b (verve.b0015b: swapped). Reads udp/cars.csv,
sessions.csv, events.csv, raw/loader.log, addons.json and race_feel/race_feel.csv (tools/b0015_run.ps1).
Rules (#100 v4, fixed before any data): primary train_s_behind_net per driver-race; model y ~ condition (45 = 1) +
grid + driver fixed effects; SE from a bootstrap over races within each order (2000, seed 1).
  PASS: coefficient > 0, its 2-SE interval excludes 0, the unadjusted within-driver mean difference is also > 0, and
  costly contacts of the modified drivers aren't up by >= 2 SE in the 45 arm.
  FAIL-NULL: the 2-SE interval lies within +-40 s. INCONCLUSIVE otherwise (significant negative = "opposite to the
  prediction"). Arm proof: 4 keys at 45 in order a and 5 in order b, and 4 the reverse (as #71).
Exit 0 PASS, 1 FAIL-NULL, 2 INCONCLUSIVE, 3 not enough valid races (or one race INVALID with --validity).
"""
from __future__ import annotations

import csv
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import b0014_check as k  # noqa: E402  (shared: roster, groups, OLS, within-driver diff, bootstrap)

EXPECT_OVERWRITTEN = 60
HIGH, LOW = 45.0, 5.0
NULL_BAND = 40.0
PRIMARY = "train_s_behind_net"
SECONDARY = ("held_suffered_net_2plus", "train_s_behind", "costly_contacts", "held_passes_net_2plus", "net",
             "lap1_pos_change", "collisions", "penalties", "dnf")
OVERWROTE = re.compile(r"gamedb: overwrote (0x[0-9a-f]+) .*float\): \S+ -> (\S+)\s*$")


def order_of(run: Path) -> str:
    return "a" if int(run.name.split("_")[1]) % 2 == 1 else "b"


def num(v: str) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def load_race(run: Path) -> tuple[list[dict], list[str]]:
    order = order_of(run)
    invalid: list[str] = []
    try:
        sessions = [s for s in k.read_csv(run / "udp" / "sessions.csv") if s["session_type"] == "race"]
        if len(sessions) != 1:
            return [], [f"{len(sessions)} race sessions in UDP"]
        uid = sessions[0]["session_uid"]
        cars = [c for c in k.read_csv(run / "udp" / "cars.csv") if c["session_uid"] == uid]
        events = [e for e in k.read_csv(run / "udp" / "events.csv") if e["session_uid"] == uid]
        feel = {int(r["car"]): r for r in k.read_csv(run / "race_feel" / "race_feel.csv")}
        log = (run / "raw" / "loader.log").read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError as e:
        return [], [f"missing data: {e}"]
    db = next((m for m in map(k.GAMEDB.search, log) if m), None)
    if not db or int(db[1]) != EXPECT_OVERWRITTEN:
        invalid.append(f"gamedb {db[1] if db else 'none'} overwritten, expected {EXPECT_OVERWRITTEN}")
    want = "verve.b0015a" if order == "a" else "verve.b0015b"
    try:
        addons = set(json.loads((run / "addons.json").read_text(encoding="utf-8")))
    except (OSError, ValueError):
        addons = set()
    if addons != {want}:
        invalid.append(f"addons {sorted(addons) or 'unknown'}, expected {want}")
    if sessions[0].get("ai_difficulty", "") != "100":
        invalid.append(f"AI difficulty reads {sessions[0].get('ai_difficulty') or 'nothing'}, expected 100")
    player = int(sessions[0]["player_car"])
    if player != k.PLAYER_CAR:
        invalid.append(f"player is car {player}, not {k.PLAYER_CAR}")
    if not any(e["code"] == "CHQF" for e in events):
        invalid.append("no chequered flag")
    if (run / "pause_cut.txt").exists():
        invalid.append("PAUSE cut")
    # weather (#100, ruling of 2026-11-15): rain in the race session = invalid; tools/weather_check.py writes weather.txt
    wx = run / "weather.txt"
    if not wx.exists():
        invalid.append("no weather.txt (run tools/weather_check.py on raw/udp.bin)")
    elif not wx.read_text(encoding="utf-8").startswith("weather: DRY"):
        invalid.append("weather: " + wx.read_text(encoding="utf-8").splitlines()[0].split(":", 1)[1].strip())
    high = k.G1 if order == "a" else k.G2
    rows = []
    for c in cars:
        car, name = int(c["car"]), c["name"].upper()
        if name not in k.ROSTER:
            continue
        f = feel.get(car)
        if f is None:
            invalid.append(f"race_feel has no row for car {car} ({name})")
            continue
        rows.append({"race": run.name, "order": order, "driver": name, "high": 1 if name in high else 0,
                     "grid": int(c["first_position"]), "net": int(c["first_position"]) - int(c["last_position"]),
                     **{key: num(f.get(key)) for key in (PRIMARY, *SECONDARY) if key != "net"}})
    if len(rows) != 8:
        invalid.append(f"{len(rows)} roster drivers found, expected 8")
    return rows, invalid


def applied_values(run: Path) -> dict[str, float]:
    out = {}
    for line in (run / "raw" / "loader.log").read_text(encoding="utf-8", errors="replace").splitlines():
        m = OVERWROTE.search(line)
        if m:
            out[m[1]] = float(m[2])
    return out


def flipping_keys(runs: list[Path]) -> tuple[int, int]:
    values = [(applied_values(r), order_of(r)) for r in runs]
    keys = set.intersection(*(set(v) for v, _ in values)) if values else set()

    def count(a: float, b: float) -> int:
        return sum(1 for key in keys if all(abs(v[key] - (a if o == "a" else b)) < 1e-6 for v, o in values))
    return count(HIGH, LOW), count(LOW, HIGH)


def decide(rows: list[dict]) -> tuple[str, dict]:
    coef = k.condition_coef(rows, PRIMARY)
    se = k.bootstrap_se(rows, lambda s: k.condition_coef(s, PRIMARY))
    raw = k.within_diff(rows, PRIMARY)
    cc = k.within_diff(rows, "costly_contacts")
    cc_se = k.bootstrap_se(rows, lambda s: k.within_diff(s, "costly_contacts"))
    cost = cc > 0 and cc >= 2 * cc_se
    lo, hi = coef - 2 * se, coef + 2 * se
    out = {"coef": coef, "se": se, "lo": lo, "hi": hi, "raw": raw, "cc": cc, "cc_se": cc_se, "cost": cost}
    if coef > 0 and lo > 0 and raw > 0 and not cost:
        return "PASS", out
    if lo >= -NULL_BAND and hi <= NULL_BAND:
        return "FAIL-NULL", out
    return "INCONCLUSIVE", out


def selftest() -> int:
    import random

    def fake(effect: float, seed: int) -> list[dict]:
        rng = random.Random(seed)
        rows = []
        for race in range(12):
            order = "a" if race % 2 == 0 else "b"
            high = k.G1 if order == "a" else k.G2
            for d, g in zip(k.ROSTER, rng.sample(range(1, 21), 8)):
                h = 1 if d in high else 0
                rows.append({"race": f"race_{race + 1}", "order": order, "driver": d, "high": h, "grid": g,
                             PRIMARY: 186 + 3 * g + effect * h + rng.gauss(0, 98), "costly_contacts": 0})
        return rows
    v1, o1 = decide(fake(150.0, 1))
    v0, o0 = decide(fake(0.0, 2))
    print(f"effect +150 s: {v1} ({o1['coef']:+.1f} +- {o1['se']:.1f}); effect 0: {v0} ({o0['coef']:+.1f} +- {o0['se']:.1f})")
    ok = v1 == "PASS" and v0 != "PASS"
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
    if validity:
        run = Path(args[0])
        _, invalid = load_race(run)
        vals = sorted(set(applied_values(run).values())) if (run / "raw" / "loader.log").exists() else []
        print(f"  {run.name} (order {order_of(run)}): float values overwritten {vals}")
        for why in invalid:
            print(f"  INVALID: {why}")
        print("  RESULT: INVALID, discard and rerun" if invalid else "  RESULT: VALID")
        return 3 if invalid else 0
    runs = sorted((p for p in Path(args[0]).glob("race_*") if p.is_dir()), key=lambda p: int(p.name.split("_")[1]))
    rows, valid = [], []
    for run in runs:
        r, invalid = load_race(run)
        print(f"{run.name} (order {order_of(run)}): {'VALID' if not invalid else 'INVALID: ' + '; '.join(invalid)}")
        if not invalid:
            rows += r
            valid.append(run)
    print(f"\n{len(valid)} valid of {len(runs)} races")
    if len({r['order'] for r in rows}) < 2 or len(valid) < 4:
        print("not enough valid races in both orders to score")
        return 3
    pair = flipping_keys(valid)
    print(f"Arm check: {pair[0]} keys at 45 in order a and 5 in order b; {pair[1]} the reverse (expect 4 and 4)")
    if pair != (4, 4):
        print("ARM CHECK FAILED: not scoring")
        return 3
    try:
        verdict, o = decide(rows)
    except ValueError:
        print("the model can't be fitted")
        return 3
    print(f"\nPrimary {PRIMARY} per driver-race: coefficient (45 - 5) {o['coef']:+.1f} s, bootstrap SE {o['se']:.1f}, "
          f"2-SE [{o['lo']:+.1f}, {o['hi']:+.1f}] (null band +-{NULL_BAND:g} s); within-driver mean {o['raw']:+.1f} s")
    print(f"Cost check, costly contacts (45 - 5): {o['cc']:+.3f} (SE {o['cc_se']:.3f}){'  COST: blocks PASS' if o['cost'] else ''}")
    for key in SECONDARY:
        e = k.within_diff(rows, key)
        s = k.bootstrap_se(rows, lambda x, key=key: k.within_diff(x, key))
        print(f"Secondary {key}: within-driver 45 - 5 {e:+.3f}, 2-SE [{e - 2 * s:+.3f}, {e + 2 * s:+.3f}]")
    print("Sensitivity (5 s / 20 s hold windows, not scored): run race_feel with HOLD_S changed; not computed here")
    if verdict == "INCONCLUSIVE" and o["hi"] < 0:
        print("NOTE: a significant negative effect: opposite to the prediction")
    print(f"\nRESULT: {verdict}")
    return {"PASS": 0, "FAIL-NULL": 1, "INCONCLUSIVE": 2}[verdict]


if __name__ == "__main__":
    sys.exit(main())
