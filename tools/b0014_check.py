"""Score B-0014 (#71): row aggression vs overtaking, within-driver crossover.

Usage:
    python -I tools/b0014_check.py runs/<batch> [--order-of race_N=a|b ...] [--expect-overwritten N] [--expect-difficulty N]
    python -I tools/b0014_check.py --selftest

Each run folder is runs/<batch>/race_<n>. Odd races are order a (G1 high, G2 low), even races order b, unless given.
Reads udp/cars.csv, events.csv, laps.csv, sessions.csv and raw/loader.log. Exit 0 PASS, 1 FAIL-NULL, 2 INCONCLUSIVE, 3 not
enough valid races. All the rules are on #71: model, bootstrap and validity were fixed before any data.

No third-party packages: python here is the bare WindowsApps one, so the least squares is written out below.
"""
from __future__ import annotations

import csv
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
GAMEDB = re.compile(r"gamedb: (\d+) overwritten")
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
            "made_1": sum(1 for o in made if o["t"] < cut), "suffered_2_5": sum(1 for o in lost if o["t"] >= cut),
            "net": int(c["first_position"]) - int(c["last_position"]), "coll": coll.get(car, 0), "pen": pen.get(car, 0),
            "dnf": 0 if c["result_status"] in ("3", "NA") else 1,
        })
    return rows, invalid


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


def condition_coef(rows: list[dict], y: str = "made_2_5") -> float:
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
    raw = within_diff(rows, "made_2_5")
    net = within_diff(rows, "net")
    coll, coll_se = within_diff(rows, "coll"), bootstrap_se(rows, lambda s: within_diff(s, "coll"))
    out = {"coef": coef, "se": se, "raw": raw, "net": net, "coll": coll, "coll_se": coll_se,
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
                             "made_2_5": made, "made_1": 0, "suffered_2_5": 0, "net": effect * h + rng.gauss(0, 1),
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
    if not args:
        print(__doc__)
        return 2
    runs = sorted((p for p in Path(args[0]).glob("race_*") if p.is_dir()), key=lambda p: int(p.name.split("_")[1]))
    rows = []
    valid = []
    for run in runs:
        order = "a" if int(run.name.split("_")[1]) % 2 == 1 else "b"
        r, invalid = load_race(run, order, expect, difficulty)
        print(f"{run.name} (order {order}): {'VALID' if not invalid else 'INVALID: ' + '; '.join(invalid)}")
        if not invalid:
            rows += r
            valid.append(run.name)
    print(f"\n{len(valid)} valid of {len(runs)} races")
    if len({r['order'] for r in rows}) < 2 or len(valid) < 4:
        print("not enough valid races in both orders to score")
        return 3
    verdict, o = decide(rows)
    print(f"\nPrimary, OVTK made on laps 2-5, per race: condition coefficient {o['coef']:+.3f}, bootstrap SE {o['se']:.3f}")
    print(f"Within-driver high minus low: made laps 2-5 {o['raw']:+.3f}; net position change {o['net']:+.3f}")
    print(f"Secondary: made lap 1 {o['made_1']:+.3f}; suffered laps 2-5 {o['suffered_2_5']:+.3f}; collisions {o['coll']:+.3f} (SE {o['coll_se']:.3f}); penalties {o['pen']:+.3f}; DNFs {o['dnf']:+.3f}")
    if o["coll"] >= 2 * o["coll_se"] and o["coll"] > 0:
        print("FLAG: high aggression raises collisions by >= 2 SE: a cost, even on a PASS")
    print(f"\nRESULT: {verdict}")
    return {"PASS": 0, "FAIL-NULL": 1, "INCONCLUSIVE": 2}[verdict]


if __name__ == "__main__":
    sys.exit(main())
