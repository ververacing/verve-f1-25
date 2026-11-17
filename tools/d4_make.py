"""D4 racecraft rating LOW vs HIGH in GP: the seeded teammate draw and the per-launch test add-on (docs/verve_d4_prereg.md).

Usage:
    python -I tools/d4_make.py --seed <int> --launch <L> --out <dir>
    python -I tools/d4_make.py --paths            # the 38 racecraft paths (docs/stock/d4_paths.txt), one per line
    python -I tools/d4_make.py --selftest

Writes <out>/verve.d4-L<LL>/{swofty.json, db/d4.json}, plus <out>/assignment.csv (driver, team, level high/low/stock)
and <out>/expected_ops.csv (path, field, value). Use one --out folder per launch: the two CSVs keep fixed names.

Lever (the supervisor's ruling, 2026-11-17): the racecraft rating's `evolution` curve, in BOTH StatisticsDataSets
(`default` and `2026`), set to a FLAT curve: HIGH 0.99 or LOW 0.05 at every season x = 0..10. The strings are
B-0001's exact ones (harness/addons/verve.b0001/db/b0001.json:31 and :55): the stock header
`@v2@minx:0,maxx:10,miny:0,maxy:100`, then the points `0:y,0:y,1:y,1:y`. The points are stored normalised, as in every
stock curve: x 0 -> 1 spans seasons 0 -> 10 (minx..maxx) and y = rating/100. No other writes: no rows, no other
ratings, no driver_characteristic_overrides, no maps, no ai_driver_config.

Select: driver_statistics.driver_statistics.DriverStatisticsHolder[driver=<row>].StatisticsDataSet[_metadata_=<ds>]
.Statistic[_metadata_=racecraft], field evolution. <row> is the holder's `driver` field, which is the driver row's label
(v1_make's ROSTER label; F-32; docs/stock/statistics_datasets.csv: Albon's holder is alexander_albon, its driver
alex_albon).

Assignment: in each of the 9 two-AI teams of tools/v1_make.py's TEAMS, one seeded coin flip makes one teammate HIGH and
the other LOW. Alonso (v1_make's SOLO, no AI teammate) gets no ops (stock). So 9 HIGH, 9 LOW, 1 stock, 36 ops per launch
(18 drivers x 2 datasets), a new draw per launch. draw(seed, launch) is pure; its seed string ("verve-d4|...") is
distinct from V-1's and D1's.

Hard rule: no op ever touches cede_position.*, yellow_flag_* or flying_lap_yield_* (v1_make's FORBIDDEN; asserted).
"""
from __future__ import annotations

import csv
import io
import json
import random
import re
import sys
import tempfile
from contextlib import redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import v1_make as vm  # noqa: E402

REPO = Path(__file__).resolve().parent.parent
PATHS_FILE = REPO / "docs" / "stock" / "d4_paths.txt"
STOCK = REPO / "docs" / "stock"
B0001_DB = REPO / "harness" / "addons" / "verve.b0001" / "db" / "b0001.json"

ROSTER, TEAMS, TEAM_OF, SOLO = vm.ROSTER, vm.TEAMS, vm.TEAM_OF, vm.SOLO
FORBIDDEN = vm.FORBIDDEN
STAT_SELECT = ("driver_statistics.driver_statistics.DriverStatisticsHolder[driver={driver}]"
               ".StatisticsDataSet[_metadata_={ds}].Statistic[_metadata_=racecraft]")
DATASETS = ["default", "2026"]
FIELD = "evolution"
SEED_FMT = "verve-d4|{seed}|{launch}"    # distinct from V-1's "verve-v1|..." and D1's "verve-d1|..."
LEVELS = {"high": "0.99", "low": "0.05"}   # the supervisor's ruling (2026-11-17); B-0001/B-0006's levels
HEADER = "@v2@minx:0,maxx:10,miny:0,maxy:100"   # the stock racecraft axes (docs/stock/stats_*.txt)
SEASONS = range(0, 11)                     # x = 0..10


# --------------------------------------------------------------------------------------
# the curve
# --------------------------------------------------------------------------------------

def flat_curve(y: str) -> str:
    """B-0001's flat racecraft curve: the stock header, then 0:y,0:y,1:y,1:y (x stored normalised, 0..1 = minx..maxx)."""
    return f"{HEADER},0:{y},0:{y},1:{y},1:{y}"


CURVE = {lvl: flat_curve(v) for lvl, v in LEVELS.items()}


def parse_curve(s: str) -> tuple[dict[str, float], list[tuple[float, float]]]:
    """'@v2@minx:0,maxx:10,miny:0,maxy:100,0:0.9,...' -> ({minx, maxx, miny, maxy}, [(x, y), ...]) with x as stored."""
    if not s.startswith("@v2@"):
        raise ValueError(f"not a @v2@ curve: {s[:20]!r}")
    head, pts = {}, []
    for item in s[4:].split(","):
        k, v = item.split(":")
        if k in ("minx", "maxx", "miny", "maxy"):
            if pts:
                raise ValueError(f"header key {k} after a point")
            head[k] = float(v)
        else:
            pts.append((float(k), float(v)))
    if set(head) != {"minx", "maxx", "miny", "maxy"} or not pts:
        raise ValueError(f"incomplete curve: {s!r}")
    if any(b[0] < a[0] for a, b in zip(pts, pts[1:])):
        raise ValueError(f"x not ascending: {s!r}")
    return head, pts


def curve_at(s: str, season: float) -> float:
    """The stored y (rating/100) at a season on the header's x axis: piecewise linear over the normalised points,
    held flat outside them. At a repeated x the last point there wins (only matters for a non-flat curve)."""
    head, pts = parse_curve(s)
    x = (season - head["minx"]) / (head["maxx"] - head["minx"])
    if x <= pts[0][0]:
        return pts[0][1]
    if x >= pts[-1][0]:
        return pts[-1][1]
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        if x0 <= x <= x1 and x1 > x0:
            return y0 + (y1 - y0) * (x - x0) / (x1 - x0)
    raise AssertionError("unreachable")


# --------------------------------------------------------------------------------------
# the draw (pure)
# --------------------------------------------------------------------------------------

def draw(seed: int, launch: int) -> dict[str, str]:
    """{driver: 'high' / 'low' / 'stock'} for one launch. Pure and deterministic in (seed, launch); a str seed is stable
    across runs and machines (random.seed version 2 hashes it with sha512, not hash())."""
    rng = random.Random(SEED_FMT.format(seed=seed, launch=launch))
    out = {}
    for _, ds in TEAMS:
        if len(ds) == 2:
            h = rng.randrange(2)
            out[ds[h]], out[ds[1 - h]] = "high", "low"
        else:
            out[ds[0]] = "stock"
    return {d: out[d] for d in ROSTER}


# --------------------------------------------------------------------------------------
# ops and the add-on
# --------------------------------------------------------------------------------------

def select_of(driver: str, ds: str) -> str:
    return STAT_SELECT.format(driver=driver, ds=ds)


def build_ops(level: dict[str, str]) -> list[dict]:
    return [vm.op(select_of(d, ds), FIELD, CURVE[level[d]]) for d in ROSTER if level[d] != "stock" for ds in DATASETS]


def all_paths() -> list[str]:
    """Every path a D4 launch can write (19 AI drivers x 2 datasets; Alonso's 2 for the stock record only): the
    check_applied key cache needs all of them."""
    return [f"{select_of(d, ds)}.{FIELD}" for d in ROSTER for ds in DATASETS]


def addon_id(launch: int) -> str:
    return f"verve.d4-l{launch:02d}"


def folder_name(launch: int) -> str:
    return f"verve.d4-L{launch:02d}"


def manifest(seed: int, launch: int, n_ops: int) -> dict:
    return {
        "schema_version": 1, "id": addon_id(launch),
        "name": f"Verve test D4 launch {launch:02d} (racecraft rating LOW vs HIGH)",
        "version": "0.0.1", "author": "TC Verve",
        "description": f"Test-only addon for D4 (docs/verve_d4_prereg.md), seed {seed}, launch {launch}: the racecraft "
                       f"rating's evolution curve, default and 2026, flat at {LEVELS['high']} (HIGH) on one seeded "
                       f"teammate per two-AI team and flat at {LEVELS['low']} (LOW) on the other (assignment.csv); "
                       f"Alonso stays stock. {n_ops} ops. Not for play.",
        "license": "MIT", "category": "ai", "kind": ["database"],
        # absolute values; 26566308 = F1 25 1.0.145 (docs/harness.md)
        "compat": {"game": "f1_25", "game_builds": [">=26566308"], "launcher": ">=1.9.34"},
        "requires": [{"id": "swofty.core", "version": ">=0.2.13"}], "saves": {"affects": False},
        "operations": {"database": ["db/d4.json"]},
    }


SELECT_RE = re.compile(r"driver_statistics\.driver_statistics\.DriverStatisticsHolder\[driver=(" + vm.LABEL_RE +
                       r")\]\.StatisticsDataSet\[_metadata_=(" + vm.LABEL_RE + r")\]\.Statistic\[_metadata_=racecraft\]")


def op_problems(o: dict) -> list[str]:
    """Why an op is malformed, forbidden or outside D4's lever (empty = fine)."""
    if set(o) != {"op", "select", "field", "value"} or o.get("op") != "set":
        return [f"bad op shape: {o}"]
    p = []
    sel, field, val = o["select"], o["field"], o["value"]
    if FORBIDDEN.search(sel) or FORBIDDEN.search(field):
        p.append(f"FORBIDDEN key: {sel} {field}")
    m = SELECT_RE.fullmatch(sel)
    if not m:
        p.append(f"unexpected select: {sel}")
    else:
        if m[1] not in ROSTER or m[1] in SOLO:
            p.append(f"driver not drawable (off the AI roster, or the solo driver): {m[1]}")
        if m[2] not in DATASETS:
            p.append(f"dataset {m[2]!r} not one of {DATASETS}")
    if field != FIELD:
        p.append(f"field {field!r}, not {FIELD!r}")
    if val not in CURVE.values():
        p.append(f"value {val!r} is not the HIGH or LOW flat curve")
    return p


def check_ops(ops: list[dict]) -> None:
    probs = [x for o in ops for x in op_problems(o)]
    if probs:
        sys.exit("refusing to write: " + "; ".join(probs[:5]))


def write_launch(seed: int, launch: int, out: Path) -> list[dict]:
    level = draw(seed, launch)
    ops = build_ops(level)
    check_ops(ops)
    folder = out / folder_name(launch)
    (folder / "db").mkdir(parents=True, exist_ok=True)
    (folder / "db" / "d4.json").write_text(json.dumps({"schema_version": 1, "ops": ops}, indent=2) + "\n", "utf-8")
    (folder / "swofty.json").write_text(json.dumps(manifest(seed, launch, len(ops)), indent=2) + "\n", "utf-8")
    with (out / "assignment.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["driver", "team", "level"])
        for d in ROSTER:
            w.writerow([d, TEAM_OF[d], level[d]])
    with (out / "expected_ops.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["path", "field", "value"])
        w.writerows([o["select"], o["field"], o["value"]] for o in ops)
    return ops


def read_assignment(path: Path) -> dict[str, str]:
    with path.open(encoding="utf-8", newline="") as f:
        return {r["driver"]: r["level"] for r in csv.DictReader(f)}


def assignment_problems(level: dict[str, str]) -> list[str]:
    """Structural checks on an assignment (as read back from assignment.csv)."""
    p = []
    if set(level) != set(ROSTER):
        p.append(f"drivers {sorted(set(level) ^ set(ROSTER))} differ from the roster")
        return p
    if set(level.values()) - {"high", "low", "stock"}:
        p.append("level is not high/low/stock")
    for t, ds in TEAMS:
        if len(ds) == 2 and sorted((level[ds[0]], level[ds[1]])) != ["high", "low"]:
            p.append(f"{t}: not exactly one HIGH and one LOW teammate")
    if any(level[d] != "stock" for d in SOLO):
        p.append(f"solo driver not stock: {[d for d in SOLO if level[d] != 'stock']}")
    return p


def stock_holders() -> dict[str, str]:
    """{holder driver field: datasets} from docs/stock/statistics_datasets.csv (build 25251167)."""
    with (STOCK / "statistics_datasets.csv").open(encoding="utf-8") as f:
        return {r["driver"]: r["datasets"] for r in csv.DictReader(ln for ln in f if not ln.startswith("#"))}


# --------------------------------------------------------------------------------------
# selftest
# --------------------------------------------------------------------------------------

def selftest() -> int:
    results, ok = [], True

    def chk(name: str, cond: bool, detail: str = "") -> None:
        nonlocal ok
        ok &= bool(cond)
        results.append(f"{'ok' if cond else 'FAIL'} {name}" + (f": {detail}" if detail else ""))

    # ---- the curve
    b1 = {o["value"] for o in json.loads(B0001_DB.read_text(encoding="utf-8"))["ops"] if o["field"] == "evolution"}
    chk("the HIGH and LOW curves are B-0001's exact strings (harness/addons/verve.b0001/db/b0001.json)",
        CURVE["high"] in b1 and CURVE["low"] in b1, f"{CURVE['high']} | {CURVE['low']}")
    chk("the levels are the ruling's 0.99 / 0.05", LEVELS == {"high": "0.99", "low": "0.05"})
    flat = {lvl: [curve_at(CURVE[lvl], s) for s in SEASONS] for lvl in CURVE}
    fine = {lvl: [curve_at(CURVE[lvl], s / 10) for s in range(0, 101)] for lvl in CURVE}
    chk("each curve parses back to y = its level at every season x = 0..10 (and every 0.1 between)",
        all(v == float(LEVELS[lvl]) for lvl in CURVE for v in flat[lvl] + fine[lvl]),
        str({lvl: sorted(set(flat[lvl])) for lvl in CURVE}))
    hd, pts = parse_curve(CURVE["high"])
    chk("the header is the stock racecraft axes (x 0..10 seasons, y 0..100) and the points span x 0 -> 1 (normalised)",
        hd == {"minx": 0, "maxx": 10, "miny": 0, "maxy": 100} and pts[0][0] == 0 and pts[-1][0] == 1
        and all(y == 0.99 for _, y in pts) and len(pts) == 4)
    alo = "@v2@minx:0,maxx:10,miny:0,maxy:100,0:0.9,0:0.9,0.5:0.88,1:0.7,1:0.7"
    stock_txt = (STOCK / "stats_fernando_alonso.txt").read_text(encoding="utf-8")
    chk("the parser reads a stock curve (Alonso racecraft default: 0.9 at x=0, 0.88 at season 5, 0.7 at 10)",
        alo in stock_txt and curve_at(alo, 0) == 0.9 and abs(curve_at(alo, 5) - 0.88) < 1e-12
        and curve_at(alo, 10) == 0.7 and abs(curve_at(alo, 2.5) - 0.89) < 1e-12)
    stock_rc = re.findall(r"\(racecraft\)\s+_metadata_\s+racecraft\s+evolution\s+(\S+)",
                          "".join((STOCK / f"stats_{d}.txt").read_text(encoding="utf-8")
                                  for d in ("fernando_alonso", "max_verstappen", "oliver_bearman")))
    chk("neither flat curve equals a stock racecraft curve in the repo (so no op is dropped as equal to stock)",
        len(stock_rc) == 6 and not set(stock_rc) & set(CURVE.values()), f"{len(stock_rc)} stock curves")
    bad = 0
    for s in ("0:0.5,1:0.5", "@v2@minx:0,maxx:10,0:1", "@v2@minx:0,maxx:10,miny:0,maxy:100,1:0.5,0:0.5"):
        try:
            parse_curve(s)
        except ValueError:
            bad += 1
    chk("parse_curve refuses a missing prefix, an incomplete header and descending x", bad == 3)

    # ---- the draw
    seeds, launches = [1, 7, 2026111704, 123456789], range(1, 21)
    draws = {(s, L): draw(s, L) for s in seeds for L in launches}
    chk("roster and teams come from v1_make (19 AI drivers, 9 two-AI teams, Alonso solo)",
        ROSTER is vm.ROSTER and TEAMS is vm.TEAMS and len(ROSTER) == 19 and SOLO == ["fernando_alonso"]
        and sum(len(ds) == 2 for _, ds in TEAMS) == 9)
    chk("determinism (same seed + launch -> same draw)", all(draw(s, L) == draws[(s, L)] for s, L in draws))
    chk("draw covers the 19 drivers with high/low/stock",
        all(list(a) == ROSTER and set(a.values()) <= {"high", "low", "stock"} for a in draws.values()))
    chk("exactly one HIGH and one LOW per two-AI team", all(
        sorted((a[ds[0]], a[ds[1]])) == ["high", "low"] for a in draws.values() for _, ds in TEAMS if len(ds) == 2))
    chk("Alonso always stock (no ops)", all(a["fernando_alonso"] == "stock" for a in draws.values()))
    chk("9 HIGH, 9 LOW, 1 stock in every draw", all(
        sum(v == "high" for v in a.values()) == 9 and sum(v == "low" for v in a.values()) == 9 for a in draws.values()))
    distinct = {s: len({json.dumps(draws[(s, L)], sort_keys=True) for L in launches}) for s in seeds}
    chk("different launches give different draws (>= 18 distinct of 20 launches per seed; 512 draws exist)",
        all(v >= 18 for v in distinct.values()), str(distinct))
    chk("launch 1 and launch 2 differ for every seed, the D4 seed included",
        all(draws[(s, 1)] != draws[(s, 2)] for s in seeds))
    chk("different seeds give different draws (launch 1)", len({json.dumps(draws[(s, 1)]) for s in seeds}) == len(seeds))
    n = sum(draw(s, 1)["oscar_piastri"] == "high" for s in range(2000))
    chk("coin flips are fair (Piastri HIGH in 2000 seeds)", 900 < n < 1100, str(n))
    chk("the seed string is D4's own (verve-d4|seed|launch, not V-1's or D1's)",
        SEED_FMT.format(seed=1, launch=2) == "verve-d4|1|2")

    # ---- ops and paths
    all_ops = {k: build_ops(a) for k, a in draws.items()}
    chk("36 ops per launch (18 drivers x 2 datasets)", all(len(o) == 36 for o in all_ops.values()))
    chk("the ops are exactly default + 2026 racecraft evolution = the level's flat curve on each drawn driver", all(
        sorted((o["select"], o["field"], o["value"]) for o in ops) ==
        sorted((select_of(d, ds), "evolution", CURVE[draws[key][d]]) for d in ROSTER if d != "fernando_alonso"
               for ds in ("default", "2026"))
        for key, ops in all_ops.items()))
    chk("the exact select and field (B-0001's, harness/addons/verve.b0001/db/b0001.json)",
        select_of("nico_hulkenberg", "default") == "driver_statistics.driver_statistics.DriverStatisticsHolder"
        "[driver=nico_hulkenberg].StatisticsDataSet[_metadata_=default].Statistic[_metadata_=racecraft]"
        and FIELD == "evolution" and select_of("nico_hulkenberg", "default") in
        {o["select"] for o in json.loads(B0001_DB.read_text(encoding="utf-8"))["ops"]})
    hold = stock_holders()
    chk("every roster driver is a holder's `driver` field with exactly default|2026 (statistics_datasets.csv)",
        all(hold.get(d) == "default|2026" for d in ROSTER), str([d for d in ROSTER if hold.get(d) != "default|2026"]))
    chk("Albon is selected by his driver field alex_albon (the holder's _metadata_ is alexander_albon)",
        "alex_albon" in hold and "alexander_albon" not in hold and "[driver=alex_albon]" in select_of("alex_albon", "2026"))
    chk("Alonso never gets an op", not any("fernando_alonso" in o["select"] for ops in all_ops.values() for o in ops))
    chk("every op passes op_problems", not [p for ops in all_ops.values() for o in ops for p in op_problems(o)])
    chk("no forbidden key (cede_position.*, yellow_flag_*, flying_lap_yield_*) in any op",
        not any(FORBIDDEN.search(o["select"] + " " + o["field"] + " " + o["value"])
                for ops in all_ops.values() for o in ops))
    chk("no duplicate (select, field) in a launch",
        all(len({(o["select"], o["field"]) for o in ops}) == len(ops) for ops in all_ops.values()))
    s0 = select_of("max_verstappen", "default")
    chk("the guard catches another field, another stat, another dataset, another value, Alonso, the player, a "
        "forbidden key", all(op_problems(x) for x in [
            vm.op(s0, "info", CURVE["high"]),
            vm.op(s0.replace("racecraft", "awareness"), FIELD, CURVE["high"]),
            vm.op(select_of("max_verstappen", "f2_2026"), FIELD, CURVE["high"]),
            vm.op(s0, FIELD, flat_curve("1")),
            vm.op(s0, FIELD, "0.99"),
            vm.op(select_of("fernando_alonso", "default"), FIELD, CURVE["low"]),
            vm.op(select_of(vm.PLAYER, "default"), FIELD, CURVE["low"]),
            vm.op(vm.DRIVER_SELECT.format("max_verstappen"), vm.AIC + "cede_position.yellow_flag_ramp_up_time",
                  CURVE["low"])]))
    chk("assignment_problems: a valid draw is clean, a broken one is caught",
        not assignment_problems(draws[(1, 1)]) and assignment_problems({**draws[(1, 1)], "fernando_alonso": "high"})
        and assignment_problems({**draws[(1, 1)], "oscar_piastri": "high", "lando_norris": "high"})
        and assignment_problems({**draws[(1, 1)], "oscar_piastri": "pinned"}))
    paths = all_paths()
    chk("38 paths (19 drivers x 2 datasets), unique, no forbidden key",
        len(paths) == 38 == len(set(paths)) and not any(FORBIDDEN.search(p) for p in paths))
    have = [ln.strip() for ln in PATHS_FILE.read_text(encoding="utf-8").splitlines()
            if ln.strip() and not ln.startswith("#")] if PATHS_FILE.exists() else []
    chk("docs/stock/d4_paths.txt = all_paths()", have == paths, f"{len(have)} lines")
    chk("every op path is in all_paths()", all(f"{o['select']}.{o['field']}" in set(paths)
                                               for ops in all_ops.values() for o in ops))

    # ---- the files
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp)
        w_ops = write_launch(5, 3, out)
        man = json.loads((out / "verve.d4-L03" / "swofty.json").read_text(encoding="utf-8"))
        db = json.loads((out / "verve.d4-L03" / "db" / "d4.json").read_text(encoding="utf-8"))
        with (out / "expected_ops.csv").open(encoding="utf-8") as f:
            exp = list(csv.DictReader(f))
        with (out / "assignment.csv").open(encoding="utf-8") as f:
            asg = list(csv.DictReader(f))
        chk("files written: verve.d4-L03/{swofty.json, db/d4.json}, assignment.csv, expected_ops.csv",
            all((out / p).is_file() for p in ("verve.d4-L03/swofty.json", "verve.d4-L03/db/d4.json",
                                              "assignment.csv", "expected_ops.csv")))
        chk("manifest id (lowercase, as v1_make's addon_id) / version / compat / requires / kind / saves",
            man["id"] == "verve.d4-l03" == addon_id(3) == vm.addon_id(3).replace("v1", "d4")
            and man["version"] == "0.0.1"
            and man["compat"] == {"game": "f1_25", "game_builds": [">=26566308"], "launcher": ">=1.9.34"}
            and man["requires"] == [{"id": "swofty.core", "version": ">=0.2.13"}] and man["kind"] == ["database"]
            and man["saves"] == {"affects": False} and man["operations"] == {"database": ["db/d4.json"]}
            and "36 ops" in man["description"] and "D4" in man["description"])
        chk("db/d4.json = expected_ops.csv", db == {"schema_version": 1, "ops": w_ops} and len(w_ops) == 36 and
            [(e["path"], e["field"], e["value"]) for e in exp] == [(o["select"], o["field"], o["value"]) for o in w_ops])
        chk("assignment.csv = draw (driver, team, level)", [r["driver"] for r in asg] == ROSTER and all(
            r["level"] == draw(5, 3)[r["driver"]] and r["team"] == TEAM_OF[r["driver"]] for r in asg)
            and list(asg[0]) == ["driver", "team", "level"] and read_assignment(out / "assignment.csv") == draw(5, 3))
        chk("the written values parse back to the assigned level at every season", all(
            all(curve_at(e["value"], s) == float(LEVELS[draw(5, 3)[SELECT_RE.fullmatch(e["path"])[1]]])
                for s in SEASONS) for e in exp))
        text = "".join(p.read_text(encoding="utf-8") for p in out.rglob("*") if p.is_file())
        chk("FORBIDDEN never matches anything written", not FORBIDDEN.search(text))
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = main(["--seed", "5", "--launch", "4", "--out", str(out / "cli")])
        chk("the CLI writes the add-on and prints its id", rc == 0 and (out / "cli" / "verve.d4-L04" / "swofty.json")
            .is_file() and "verve.d4-l04" in buf.getvalue())
    print("\n".join(results))
    print("selftest", "ok" if ok else "FAILED")
    return 0 if ok else 1


# --------------------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------------------

def main(argv: list[str]) -> int:
    args = list(argv)
    if "--selftest" in args:
        return selftest()
    if "--paths" in args:
        print("\n".join(all_paths()))
        return 0
    opts = {"--seed": None, "--launch": None, "--out": None}
    for k in list(opts):
        if k in args:
            i = args.index(k)
            if i + 1 >= len(args):
                print(__doc__)
                return 3
            opts[k] = args[i + 1]
            del args[i:i + 2]
    if args or None in opts.values():
        print(__doc__)
        return 3
    seed, launch, out = int(opts["--seed"]), int(opts["--launch"]), Path(opts["--out"])
    if launch < 1:
        sys.exit("--launch must be >= 1")
    ops = write_launch(seed, launch, out)
    level = draw(seed, launch)
    print(f"D4 seed {seed} launch {launch} -> {out / folder_name(launch)} (id {addon_id(launch)})")
    print(f"  {'driver':<24}{'team':<12}{'level':>7}")
    for d in ROSTER:
        print(f"  {d:<24}{TEAM_OF[d]:<12}{level[d]:>7}")
    print(f"  HIGH {sum(v == 'high' for v in level.values())}, LOW {sum(v == 'low' for v in level.values())}, "
          f"stock {sum(v == 'stock' for v in level.values())}")
    print(f"expected ops: {len(ops)} = 18 drivers x {len(DATASETS)} datasets, racecraft evolution flat at "
          f"{LEVELS['high']} (HIGH) / {LEVELS['low']} (LOW)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
