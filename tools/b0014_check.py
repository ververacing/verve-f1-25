"""Score B-0014 (#71): row aggression vs overtaking, within-driver crossover.

Usage:
    python -I tools/b0014_check.py runs/<batch> [--expect-overwritten N] [--expect-difficulty N]
    python -I tools/b0014_check.py --validity runs/<batch>/race_<n>     # one race's validity, no scoring
    python -I tools/b0014_check.py --selftest

Each run folder is runs/<batch>/race_<n>. Odd races are order a (G1 high, G2 low), even races order b.
A race is invalid if addons.json doesn't name its order's addon, and a batch can't be scored unless exactly 8 database
keys flip between the two orders: that's what proves each race really ran the arm its number says.
Reads udp/cars.csv, events.csv, laps.csv, sessions.csv and raw/loader.log. Exit 0 PASS, 1 FAIL-NULL, 2 INCONCLUSIVE, 3 not
enough valid races. All the rules are on #71: model, bootstrap and validity were fixed before any data.

No third-party packages: python here is the bare WindowsApps one, so the least squares is written out below.
"""
from __future__ import annotations

import csv
import json
import random
import re
import statistics
import sys
from pathlib import Path

G1 = {"SAINZ", "BORTOLETO", "HADJAR", "BEARMAN"}
G2 = {"ALBON", "RUSSELL", "HULKENBERG", "GASLY"}
ROSTER = sorted(G1 | G2)
STOCK_2025 = {"ALBON", "ALONSO", "ANTONELLI", "BEARMAN", "BORTOLETO", "COLAPINTO", "GASLY", "HADJAR", "HAMILTON",
              "HULKENBERG", "LAWSON", "LECLERC", "NORRIS", "OCON", "PIASTRI", "RUSSELL", "SAINZ", "STROLL", "TSUNODA",
              "VERSTAPPEN"}
PLAYER_CAR = 19
BOOTSTRAPS, BOOT_SEED = 2000, 1
NULL_BAND = 0.3
HOLD_S = 10  # a pass counts as held if the same pair doesn't swap back within this many seconds
ARM_OVERWRITTEN = 60  # 52 + 8: the arm checks only apply at this count, not on stock test data
GAMEDB = re.compile(r"gamedb: (\d+) overwritten")
OVERWROTE = re.compile(r"gamedb: overwrote (0x[0-9a-f]+) .*tag 1 float\): \S+ -> (\S+)\s*$")
LAPNAME = re.compile(r"v\((\d+), ([^)]+)\)")


def read_csv(path: Path) -> list[dict]:
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def fields(text: str) -> dict:
    return dict(p.split("=", 1) for p in text.split(";") if "=" in p)


def load_race(run: Path, order: str, expect_overwritten: int, expect_difficulty: int) -> tuple[list[dict], list[str]]:
    """The race's driver rows, and why it's invalid (empty if valid)."""
    invalid = []
    try:
        sessions = [s for s in read_csv(run / "udp" / "sessions.csv") if s["session_type"] == "race"]
        if len(sessions) != 1:
            return [], [f"{len(sessions)} race sessions in UDP"]
        uid = sessions[0]["session_uid"]
        cars = [c for c in read_csv(run / "udp" / "cars.csv") if c["session_uid"] == uid]
        events = [e for e in read_csv(run / "udp" / "events.csv") if e["session_uid"] == uid]
        laps = [l for l in read_csv(run / "udp" / "laps.csv") if l["session_uid"] == uid]
        log = (run / "raw" / "loader.log").read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError as e:
        return [], [f"missing data: {e}"]

    db = next((m for m in map(GAMEDB.search, log) if m), None)
    if not db or int(db[1]) != expect_overwritten:
        invalid.append(f"gamedb {db[1] if db else 'none'} overwritten, expected {expect_overwritten}")
    if expect_overwritten == ARM_OVERWRITTEN:  # both arms have the same count, so the count can't tell them apart
        want = "verve.b0014a" if order == "a" else "verve.b0014b"
        try:
            addons = set(json.loads((run / "addons.json").read_text(encoding="utf-8")))
        except (OSError, ValueError):
            addons = set()
        if addons != {want}:
            invalid.append(f"addons {sorted(addons) or 'unknown'}, expected {want}")
    difficulty = sessions[0].get("ai_difficulty", "")
    if difficulty != str(expect_difficulty):
        invalid.append(f"AI difficulty reads {difficulty or 'nothing'}, expected {expect_difficulty}")
    player = int(sessions[0]["player_car"])
    if player != PLAYER_CAR:
        invalid.append(f"player is car {player}, not {PLAYER_CAR}")
    names = {int(c["car"]): c["name"].upper() for c in cars}
    others = {n for v, n in names.items() if v != player}
    if others != STOCK_2025 - {"STROLL"}:
        invalid.append(f"not the stock roster: missing {sorted(STOCK_2025 - {'STROLL'} - others)}, extra {sorted(others - STOCK_2025)}")
    logged = {int(m[1]): m[2] for m in map(LAPNAME.search, log) if m}
    if player in logged and "STROLL" not in logged[player].upper():
        invalid.append(f"LAPTIMES names car {player} as {logged[player]}")
    if not any(e["code"] == "CHQF" for e in events):
        invalid.append("no chequered flag")
    ovtk = [fields(e["fields"]) | {"t": float(e["session_time"])} for e in events if e["code"] == "OVTK"]
    moved = any(c["first_position"] != c["last_position"] for c in cars)
    if not ovtk and moved:
        invalid.append("no OVTK events, though positions changed")

    ovtk.sort(key=lambda o: o["t"])
    for i, o in enumerate(ovtk):
        o["back"] = next((n["t"] - o["t"] for n in ovtk[i + 1:] if n["vehicle"] == o["other"] and n["other"] == o["vehicle"]),
                         float("inf"))  # seconds until the same pair swaps back
    print(f"  {run.name}: OVTK raw {len(ovtk)}, held at {HOLD_S} s {sum(1 for o in ovtk if o['back'] > HOLD_S)}")
    lap1 = {int(l["car"]): int(l["lap_time_ms"]) / 1000 for l in laps if l["lap"] == "1"}
    coll, pen = {}, {}
    for e in events:
        f = fields(e["fields"])
        if e["code"] == "COLL":
            for k in ("vehicle", "other"):
                coll[int(f[k])] = coll.get(int(f[k]), 0) + 1
        elif e["code"] == "PENA":
            pen[int(f["vehicle"])] = pen.get(int(f["vehicle"]), 0) + 1

    rows = []
    high = G1 if order == "a" else G2
    for c in cars:
        car, name = int(c["car"]), c["name"].upper()
        if name not in ROSTER:
            continue
        cut = lap1.get(car, float("inf"))
        made = [o for o in ovtk if int(o["vehicle"]) == car]
        lost = [o for o in ovtk if int(o["other"]) == car]
        rows.append({
            "race": run.name, "order": order, "driver": name, "high": 1 if name in high else 0,
            "grid": int(c["first_position"]), "made_2_5": sum(1 for o in made if o["t"] >= cut),
            "held_2_5": sum(1 for o in made if o["t"] >= cut and o["back"] > HOLD_S),
            "held_5s": sum(1 for o in made if o["t"] >= cut and o["back"] > 5),
            "held_20s": sum(1 for o in made if o["t"] >= cut and o["back"] > 20),
            "flips": sum(1 for o in made if o["back"] <= HOLD_S),
            "made_1": sum(1 for o in made if o["t"] < cut), "suffered_2_5": sum(1 for o in lost if o["t"] >= cut),
            "net": int(c["first_position"]) - int(c["last_position"]), "coll": coll.get(car, 0), "pen": pen.get(car, 0),
            "dnf": 0 if c["result_status"] in ("3", "NA") else 1,
        })
    return rows, invalid


def applied_values(run: Path) -> dict[str, float]:
    """What the run's log says each database key was overwritten with, for float keys."""
    out = {}
    for line in (run / "raw" / "loader.log").read_text(encoding="utf-8", errors="replace").splitlines():
        m = OVERWROTE.search(line)
        if m:
            out[m[1]] = float(m[2])
    return out


def flipping_keys(runs: list[tuple[Path, str]]) -> tuple[int, int]:
    """Keys at 1.0 in every order-a race and 0.05 in every order-b race, and the reverse: 4 of each if the arms are right."""
    values = [(applied_values(run), order) for run, order in runs]
    keys = set.intersection(*(set(v) for v, _ in values)) if values else set()

    def count(a: float, b: float) -> int:
        return sum(1 for k in keys if all(abs(v[k] - (a if o == "a" else b)) < 1e-6 for v, o in values))
    return count(1.0, 0.05), count(0.05, 1.0)


def solve(a: list[list[float]], b: list[float]) -> list[float]:
    """Gaussian elimination with partial pivoting."""
    n = len(a)
    m = [row[:] + [b[i]] for i, row in enumerate(a)]
    for i in range(n):
        p = max(range(i, n), key=lambda r: abs(m[r][i]))
        if abs(m[p][i]) < 1e-12:
            raise ValueError("singular")
        m[i], m[p] = m[p], m[i]
        for r in range(n):
            if r != i:
                k = m[r][i] / m[i][i]
                m[r] = [x - k * y for x, y in zip(m[r], m[i])]
    return [m[i][n] / m[i][i] for i in range(n)]


def condition_coef(rows: list[dict], y: str = "held_2_5") -> float:
    """OLS of y on condition + grid + driver fixed effects; returns the condition coefficient."""
    drivers = sorted({r["driver"] for r in rows})
    x = [[r["high"], r["grid"]] + [1.0 if r["driver"] == d else 0.0 for d in drivers] for r in rows]
    t = [float(r[y]) for r in rows]
    k = len(x[0])
    xtx = [[sum(row[i] * row[j] for row in x) for j in range(k)] for i in range(k)]
    xty = [sum(row[i] * v for row, v in zip(x, t)) for i in range(k)]
    return solve(xtx, xty)[0]


def within_diff(rows: list[dict], y: str) -> float:
    """Mean across drivers of each driver's high-minus-low mean."""
    diffs = []
    for d in {r["driver"] for r in rows}:
        hi = [r[y] for r in rows if r["driver"] == d and r["high"]]
        lo = [r[y] for r in rows if r["driver"] == d and not r["high"]]
        if hi and lo:
            diffs.append(statistics.mean(hi) - statistics.mean(lo))
    return statistics.mean(diffs) if diffs else float("nan")


def bootstrap_se(rows: list[dict], stat) -> float:
    """Resample whole races within each order."""
    rng = random.Random(BOOT_SEED)
    by_order: dict[str, list[list[dict]]] = {}
    for race in sorted({r["race"] for r in rows}):
        group = [r for r in rows if r["race"] == race]
        by_order.setdefault(group[0]["order"], []).append(group)
    values = []
    for _ in range(BOOTSTRAPS):
        sample = []
        for races in by_order.values():
            for _ in races:
                sample += rng.choice(races)
        try:
            v = stat(sample)
        except ValueError:  # a resample that can't identify the model
            continue
        if v == v:
            values.append(v)
    return statistics.pstdev(values) if len(values) > 1 else float("nan")


def decide(rows: list[dict]) -> tuple[str, dict]:
    coef = condition_coef(rows)
    se = bootstrap_se(rows, condition_coef)
    raw = within_diff(rows, "held_2_5")
    net = within_diff(rows, "net")
    coll, coll_se = within_diff(rows, "coll"), bootstrap_se(rows, lambda s: within_diff(s, "coll"))
    out = {"coef": coef, "se": se, "raw": raw, "net": net, "coll": coll, "coll_se": coll_se,
           "ovtk_2_5": within_diff(rows, "made_2_5"), "flips": within_diff(rows, "flips"),
           "coef_5s": condition_coef(rows, "held_5s"), "coef_20s": condition_coef(rows, "held_20s"),
           "made_1": within_diff(rows, "made_1"), "suffered_2_5": within_diff(rows, "suffered_2_5"),
           "pen": within_diff(rows, "pen"), "dnf": within_diff(rows, "dnf")}
    if coef > 0 and coef >= 2 * se and raw > 0 and net > 0:
        return "PASS", out
    if coef - 2 * se >= -NULL_BAND and coef + 2 * se <= NULL_BAND:
        return "FAIL-NULL", out
    return "INCONCLUSIVE", out


def selftest() -> int:
    """Synthetic races with a known effect: the model must recover it, and a zero effect must not pass."""
    def fake(effect: float, seed: int) -> list[dict]:
        rng = random.Random(seed)
        rows = []
        for race in range(12):
            order = "a" if race % 2 == 0 else "b"
            high = G1 if order == "a" else G2
            slots = rng.sample(range(1, 21), 8)
            for d, g in zip(ROSTER, slots):
                h = 1 if d in high else 0
                made = 4 + 0.2 * g + effect * h + rng.gauss(0, 1.5)
                rows.append({"race": f"race_{race + 1}", "order": order, "driver": d, "high": h, "grid": g,
                             "made_2_5": made + 3, "held_2_5": made, "held_5s": made, "held_20s": made, "flips": 3,
                             "made_1": 0, "suffered_2_5": 0, "net": effect * h + rng.gauss(0, 1),
                             "coll": 0, "pen": 0, "dnf": 0})
        return rows
    verdict, o = decide(fake(2.0, 11))
    print(f"effect 2.0: {verdict}, coef {o['coef']:.2f} +- {o['se']:.2f}")
    v0, o0 = decide(fake(0.0, 12))
    print(f"effect 0.0: {v0}, coef {o0['coef']:.2f} +- {o0['se']:.2f}")
    ok = verdict == "PASS" and abs(o["coef"] - 2.0) < 2 * o["se"] + 0.2 and v0 != "PASS"
    print("selftest", "ok" if ok else "FAILED")
    return 0 if ok else 1


def main() -> int:
    args = sys.argv[1:]
    if "--selftest" in args:
        return selftest()
    expect, difficulty = 60, 100
    if "--expect-overwritten" in args:
        i = args.index("--expect-overwritten")
        expect = int(args[i + 1])
        del args[i:i + 2]
    if "--expect-difficulty" in args:
        i = args.index("--expect-difficulty")
        difficulty = int(args[i + 1])
        del args[i:i + 2]
    validity = "--validity" in args
    args = [a for a in args if a != "--validity"]
    unknown = [a for a in args if a.startswith("--")]
    if unknown or len(args) != 1:
        print(f"unknown or extra arguments: {unknown or args}\n{__doc__}")
        return 2
    if validity:
        # one race, for the morning report: no scoring, so no interim look at the result (#71)
        run = Path(args[0])
        order = "a" if int(run.name.split("_")[1]) % 2 == 1 else "b"
        _, invalid = load_race(run, order, expect, difficulty)
        for why in invalid:
            print(f"  INVALID: {why}")
        print("  RESULT: INVALID, discard and rerun" if invalid else "  RESULT: VALID")
        return 3 if invalid else 0
    runs = sorted((p for p in Path(args[0]).glob("race_*") if p.is_dir()), key=lambda p: int(p.name.split("_")[1]))
    rows = []
    valid = []
    for run in runs:
        order = "a" if int(run.name.split("_")[1]) % 2 == 1 else "b"
        r, invalid = load_race(run, order, expect, difficulty)
        print(f"{run.name} (order {order}): {'VALID' if not invalid else 'INVALID: ' + '; '.join(invalid)}")
        if not invalid:
            rows += r
            valid.append(run)
    print(f"\n{len(valid)} valid of {len(runs)} races")
    if len({r['order'] for r in rows}) < 2 or len(valid) < 4:
        print("not enough valid races in both orders to score")
        return 3
    if expect == ARM_OVERWRITTEN:
        pair = flipping_keys([(run, "a" if int(run.name.split("_")[1]) % 2 == 1 else "b") for run in valid])
        print(f"Arm check: {pair[0]} keys at 1.0 in order a and 0.05 in order b; {pair[1]} the reverse (expect 4 and 4)")
        if pair != (4, 4):
            print("ARM CHECK FAILED: the logs don't show these races ran the arms their numbers say. Not scoring")
            return 3
    try:
        verdict, o = decide(rows)
    except ValueError:
        print("the model can't be fitted: grid slot doesn't vary within drivers. Check that these are different races")
        return 3
    print(f"\nPrimary, held passes on laps 2-5, per race: condition coefficient {o['coef']:+.3f}, bootstrap SE {o['se']:.3f}")
    print(f"Within-driver high minus low: held passes {o['raw']:+.3f}; net position change {o['net']:+.3f}")
    print(f"Sensitivity (not scored): coefficient at 5 s {o['coef_5s']:+.3f}, at 20 s {o['coef_20s']:+.3f}")
    print(f"Secondary: raw OVTK laps 2-5 {o['ovtk_2_5']:+.3f}; flip-flops {o['flips']:+.3f}; made lap 1 {o['made_1']:+.3f}; suffered laps 2-5 {o['suffered_2_5']:+.3f}; collisions {o['coll']:+.3f} (SE {o['coll_se']:.3f}); penalties {o['pen']:+.3f}; DNFs {o['dnf']:+.3f}")
    if o["coll"] >= 2 * o["coll_se"] and o["coll"] > 0:
        print("FLAG: high aggression raises collisions by >= 2 SE: a cost, even on a PASS")
    if o["coef_5s"] * o["coef"] <= 0 or o["coef_20s"] * o["coef"] <= 0:
        print("NOTE: the coefficient's sign doesn't hold at both 5 s and 20 s, so treat the verdict with care")
    print(f"\nRESULT: {verdict}")
    return {"PASS": 0, "FAIL-NULL": 1, "INCONCLUSIVE": 2}[verdict]


if __name__ == "__main__":
    sys.exit(main())
