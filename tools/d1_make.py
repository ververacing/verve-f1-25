"""D1 positive control in GP: the seeded teammate draw and the per-launch test add-on (docs/verve_d1_d2_prereg.md).

Usage:
    python -I tools/d1_make.py --seed <int> --launch <L> --out <dir>
    python -I tools/d1_make.py --paths            # the 76 race_start paths (docs/stock/d1_paths.txt), one per line
    python -I tools/d1_make.py --selftest

Writes <out>/verve.d1-L<LL>/{swofty.json, db/d1.json}, plus <out>/assignment.csv (driver, team, pinned 0/1) and
<out>/expected_ops.csv (path, field, value). Use one --out folder per launch: the two CSVs keep fixed names.

Lever (B-0012b's): for each PINNED driver, all four ai_driver_config.race_start reaction bounds = "0.65"
(min_reaction_time_lower_bound, min_reaction_time_upper_bound, max_reaction_time_lower_bound,
max_reaction_time_upper_bound). No other writes: no traits, no maps, no bundles.

Assignment: in each of the 9 two-AI teams of tools/v1_make.py's TEAMS, one seeded coin flip pins one teammate; the
other stays stock. Alonso (v1_make's SOLO, no AI teammate) is always stock. So 9 pinned, 10 stock, 36 ops per launch,
a new draw per launch. draw(seed, launch) is pure; its seed string ("verve-d1|...") is distinct from V-1's.

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
PATHS_FILE = REPO / "docs" / "stock" / "d1_paths.txt"

ROSTER, TEAMS, TEAM_OF, SOLO = vm.ROSTER, vm.TEAMS, vm.TEAM_OF, vm.SOLO
DRIVER_SELECT = vm.DRIVER_SELECT
FORBIDDEN = vm.FORBIDDEN
RACE_START = vm.AIC + "race_start."
KEYS = ["min_reaction_time_lower_bound", "min_reaction_time_upper_bound",
        "max_reaction_time_lower_bound", "max_reaction_time_upper_bound"]
FIELDS = [RACE_START + k for k in KEYS]
SEED_FMT = "verve-d1|{seed}|{launch}"    # distinct from V-1's "verve-v1|{seed}|{launch}"
VALUE = "0.65"          # B-0012b: each pinned car drew exactly 0.650 in GP on 25251167


# --------------------------------------------------------------------------------------
# the draw (pure)
# --------------------------------------------------------------------------------------

def draw(seed: int, launch: int) -> dict[str, int]:
    """{driver: 1 pinned / 0 stock} for one launch. Pure and deterministic in (seed, launch); a str seed is stable
    across runs and machines (random.seed version 2 hashes it with sha512, not hash())."""
    rng = random.Random(SEED_FMT.format(seed=seed, launch=launch))
    out = {}
    for _, ds in TEAMS:
        if len(ds) == 2:
            p = rng.randrange(2)
            out[ds[p]], out[ds[1 - p]] = 1, 0
        else:
            out[ds[0]] = 0
    return {d: out[d] for d in ROSTER}


# --------------------------------------------------------------------------------------
# ops and the add-on
# --------------------------------------------------------------------------------------

def build_ops(pin: dict[str, int]) -> list[dict]:
    return [vm.op(DRIVER_SELECT.format(d), f, VALUE) for d in ROSTER if pin[d] for f in FIELDS]


def all_paths() -> list[str]:
    """Every path a D1 launch can write (19 AI drivers x 4 keys): the check_applied key cache needs all of them."""
    return [f"{DRIVER_SELECT.format(d)}.{f}" for d in ROSTER for f in FIELDS]


def addon_id(launch: int) -> str:
    return f"verve.d1-l{launch:02d}"


def folder_name(launch: int) -> str:
    return f"verve.d1-L{launch:02d}"


def manifest(seed: int, launch: int, n_ops: int) -> dict:
    return {
        "schema_version": 1, "id": addon_id(launch),
        "name": f"Verve test D1 launch {launch:02d} (race_start positive control)",
        "version": "0.0.1", "author": "TC Verve",
        "description": f"Test-only addon for D1 (docs/verve_d1_d2_prereg.md), seed {seed}, launch {launch}: all four "
                       f"ai_driver_config.race_start reaction bounds = {VALUE} on one seeded teammate per two-AI team "
                       f"(9 pinned drivers, assignment.csv); the other teammates and Alonso stay stock. {n_ops} ops. "
                       f"Not for play.",
        "license": "MIT", "category": "ai", "kind": ["database"],
        # absolute values; 26566308 = F1 25 1.0.145 (docs/harness.md)
        "compat": {"game": "f1_25", "game_builds": [">=26566308"], "launcher": ">=1.9.34"},
        "requires": [{"id": "swofty.core", "version": ">=0.2.13"}], "saves": {"affects": False},
        "operations": {"database": ["db/d1.json"]},
    }


def op_problems(o: dict) -> list[str]:
    """Why an op is malformed, forbidden or outside D1's lever (empty = fine)."""
    if set(o) != {"op", "select", "field", "value"} or o.get("op") != "set":
        return [f"bad op shape: {o}"]
    p = []
    sel, field, val = o["select"], o["field"], o["value"]
    if FORBIDDEN.search(sel) or FORBIDDEN.search(field):
        p.append(f"FORBIDDEN key: {sel} {field}")
    m = re.fullmatch(r"entrants\.drivers\.driver\[_metadata_=(" + vm.LABEL_RE + r")\]", sel)
    if not m:
        p.append(f"unexpected select: {sel}")
    elif m[1] not in ROSTER or m[1] in SOLO:
        p.append(f"driver not pinnable (off the AI roster, or the solo driver): {m[1]}")
    if field not in FIELDS:
        p.append(f"not one of the four race_start reaction bounds: {field}")
    if val != VALUE:
        p.append(f"value {val!r}, not {VALUE!r}")
    return p


def check_ops(ops: list[dict]) -> None:
    probs = [x for o in ops for x in op_problems(o)]
    if probs:
        sys.exit("refusing to write: " + "; ".join(probs[:5]))


def write_launch(seed: int, launch: int, out: Path) -> list[dict]:
    pin = draw(seed, launch)
    ops = build_ops(pin)
    check_ops(ops)
    folder = out / folder_name(launch)
    (folder / "db").mkdir(parents=True, exist_ok=True)
    (folder / "db" / "d1.json").write_text(json.dumps({"schema_version": 1, "ops": ops}, indent=2) + "\n", "utf-8")
    (folder / "swofty.json").write_text(json.dumps(manifest(seed, launch, len(ops)), indent=2) + "\n", "utf-8")
    with (out / "assignment.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["driver", "team", "pinned"])
        for d in ROSTER:
            w.writerow([d, TEAM_OF[d], pin[d]])
    with (out / "expected_ops.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["path", "field", "value"])
        w.writerows([o["select"], o["field"], o["value"]] for o in ops)
    return ops


def read_assignment(path: Path) -> dict[str, int]:
    with path.open(encoding="utf-8", newline="") as f:
        return {r["driver"]: int(r["pinned"]) for r in csv.DictReader(f)}


def assignment_problems(pin: dict[str, int]) -> list[str]:
    """Structural checks on an assignment (as read back from assignment.csv)."""
    p = []
    if set(pin) != set(ROSTER):
        p.append(f"drivers {sorted(set(pin) ^ set(ROSTER))} differ from the roster")
        return p
    if set(pin.values()) - {0, 1}:
        p.append("pinned is not 0/1")
    for t, ds in TEAMS:
        if len(ds) == 2 and pin[ds[0]] + pin[ds[1]] != 1:
            p.append(f"{t}: not exactly one teammate pinned")
    if any(pin[d] for d in SOLO):
        p.append(f"solo driver pinned: {[d for d in SOLO if pin[d]]}")
    return p


# --------------------------------------------------------------------------------------
# selftest
# --------------------------------------------------------------------------------------

def selftest() -> int:
    results, ok = [], True

    def chk(name: str, cond: bool, detail: str = "") -> None:
        nonlocal ok
        ok &= bool(cond)
        results.append(f"{'ok' if cond else 'FAIL'} {name}" + (f": {detail}" if detail else ""))

    seeds, launches = [1, 7, 20261117, 123456789], range(1, 21)
    draws = {(s, L): draw(s, L) for s in seeds for L in launches}
    chk("roster and teams come from v1_make (19 AI drivers, 9 two-AI teams, Alonso solo)",
        ROSTER is vm.ROSTER and TEAMS is vm.TEAMS and len(ROSTER) == 19 and SOLO == ["fernando_alonso"]
        and sum(len(ds) == 2 for _, ds in TEAMS) == 9)
    chk("determinism (same seed + launch -> same draw)", all(draw(s, L) == draws[(s, L)] for s, L in draws))
    chk("draw covers the 19 drivers with 0/1",
        all(list(a) == ROSTER and set(a.values()) <= {0, 1} for a in draws.values()))
    chk("exactly one pinned per two-AI team",
        all(a[ds[0]] + a[ds[1]] == 1 for a in draws.values() for _, ds in TEAMS if len(ds) == 2))
    chk("Alonso never pinned", all(a["fernando_alonso"] == 0 for a in draws.values()))
    chk("9 pinned, 10 stock in every draw", all(sum(a.values()) == 9 for a in draws.values()))
    # 2^9 = 512 possible draws, so a repeat between two of 20 launches is possible (about 1 in 3 seeds has one);
    # check that the launches draw afresh, not that they never collide
    distinct = {s: len({json.dumps(draws[(s, L)], sort_keys=True) for L in launches}) for s in seeds}
    chk("different launches give different draws (>= 18 distinct of 20 launches per seed)",
        all(v >= 18 for v in distinct.values()), str(distinct))
    chk("different seeds give different draws (launch 1)", len({json.dumps(draws[(s, 1)]) for s in seeds}) == len(seeds))
    chk("launch 1 and launch 2 differ for every seed", all(draws[(s, 1)] != draws[(s, 2)] for s in seeds))
    n = sum(draw(s, 1)["oscar_piastri"] for s in range(2000))
    chk("coin flips are fair (Piastri pinned in 2000 seeds)", 900 < n < 1100, str(n))
    chk("the seed string is D1's own (verve-d1|seed|launch, not V-1's verve-v1|...)",
        SEED_FMT.format(seed=1, launch=2) == "verve-d1|1|2")

    all_ops = {k: build_ops(a) for k, a in draws.items()}
    chk("36 ops per launch (9 pinned x 4 keys)", all(len(o) == 36 for o in all_ops.values()))
    chk("the ops are exactly the 4 race_start bounds = '0.65' on each pinned driver, and nothing else", all(
        sorted((o["select"], o["field"], o["value"]) for o in ops) ==
        sorted((DRIVER_SELECT.format(d), RACE_START + k, "0.65") for d in ROSTER if draws[key][d] for k in KEYS)
        for key, ops in all_ops.items()))
    chk("the four keys are as specified", FIELDS == [
        "ai_driver_config.race_start.min_reaction_time_lower_bound",
        "ai_driver_config.race_start.min_reaction_time_upper_bound",
        "ai_driver_config.race_start.max_reaction_time_lower_bound",
        "ai_driver_config.race_start.max_reaction_time_upper_bound"] and VALUE == "0.65")
    aic = vm.stock_aic_keys()
    chk("the keys exist in docs/stock/ai_driver_config.csv and 0.65 differs from every stock value (no op dropped)",
        all(f in aic and float(aic[f]) != float(VALUE) for f in FIELDS), str({f[len(RACE_START):]: aic.get(f)
                                                                              for f in FIELDS}))
    chk("every op passes op_problems", not [p for ops in all_ops.values() for o in ops for p in op_problems(o)])
    chk("no forbidden key (cede_position.*, yellow_flag_*, flying_lap_yield_*) in any op",
        not any(FORBIDDEN.search(o["select"] + " " + o["field"]) for ops in all_ops.values() for o in ops))
    chk("no duplicate (select, field) in a launch",
        all(len({(o["select"], o["field"]) for o in ops}) == len(ops) for ops in all_ops.values()))
    sel = DRIVER_SELECT.format("max_verstappen")
    chk("the guard catches a forbidden key, another key, another value, Alonso and the player", all(op_problems(x) for x in [
        vm.op(sel, vm.AIC + "cede_position.yellow_flag_ramp_up_time", "0.65"),
        vm.op(sel, vm.AIC + "cede_position.flying_lap_yield_to_human_track_speed_diff", "0.65"),
        vm.op(sel, vm.AIC + "race_start.max_bad_start_lower_bound", "0.65"),
        vm.op(sel, FIELDS[0], "0.6"),
        vm.op(DRIVER_SELECT.format("fernando_alonso"), FIELDS[0], "0.65"),
        vm.op(DRIVER_SELECT.format(vm.PLAYER), FIELDS[0], "0.65")]))
    chk("assignment_problems: a valid draw is clean, a broken one is caught",
        not assignment_problems(draws[(1, 1)]) and assignment_problems({**draws[(1, 1)], "fernando_alonso": 1})
        and assignment_problems({**draws[(1, 1)], "oscar_piastri": 1, "lando_norris": 1}))
    paths = all_paths()
    chk("76 paths (19 drivers x 4 keys), unique, no forbidden key",
        len(paths) == 76 == len(set(paths)) and not any(FORBIDDEN.search(p) for p in paths))
    have = [ln.strip() for ln in PATHS_FILE.read_text(encoding="utf-8").splitlines()
            if ln.strip() and not ln.startswith("#")] if PATHS_FILE.exists() else []
    chk("docs/stock/d1_paths.txt = all_paths()", have == paths, f"{len(have)} lines")
    chk("every op path is in all_paths()", all(f"{o['select']}.{o['field']}" in set(paths)
                                               for ops in all_ops.values() for o in ops))

    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp)
        w_ops = write_launch(5, 3, out)
        man = json.loads((out / "verve.d1-L03" / "swofty.json").read_text(encoding="utf-8"))
        db = json.loads((out / "verve.d1-L03" / "db" / "d1.json").read_text(encoding="utf-8"))
        with (out / "expected_ops.csv").open(encoding="utf-8") as f:
            exp = list(csv.DictReader(f))
        with (out / "assignment.csv").open(encoding="utf-8") as f:
            asg = list(csv.DictReader(f))
        chk("files written: verve.d1-L03/{swofty.json, db/d1.json}, assignment.csv, expected_ops.csv",
            all((out / p).is_file() for p in ("verve.d1-L03/swofty.json", "verve.d1-L03/db/d1.json",
                                              "assignment.csv", "expected_ops.csv")))
        chk("manifest id (lowercase, as v1_make's addon_id) / version / compat / requires / kind / saves",
            man["id"] == "verve.d1-l03" == addon_id(3) == vm.addon_id(3).replace("v1", "d1")
            and man["version"] == "0.0.1"
            and man["compat"] == {"game": "f1_25", "game_builds": [">=26566308"], "launcher": ">=1.9.34"}
            and man["requires"] == [{"id": "swofty.core", "version": ">=0.2.13"}] and man["kind"] == ["database"]
            and man["saves"] == {"affects": False} and man["operations"] == {"database": ["db/d1.json"]}
            and "36 ops" in man["description"] and "D1" in man["description"])
        chk("db/d1.json = expected_ops.csv", db == {"schema_version": 1, "ops": w_ops} and len(w_ops) == 36 and
            [(e["path"], e["field"], e["value"]) for e in exp] == [(o["select"], o["field"], o["value"]) for o in w_ops])
        chk("assignment.csv = draw (driver, team, pinned)", [r["driver"] for r in asg] == ROSTER and all(
            int(r["pinned"]) == draw(5, 3)[r["driver"]] and r["team"] == TEAM_OF[r["driver"]] for r in asg)
            and list(asg[0]) == ["driver", "team", "pinned"] and read_assignment(out / "assignment.csv") == draw(5, 3))
        text = "".join(p.read_text(encoding="utf-8") for p in out.rglob("*") if p.is_file())
        chk("FORBIDDEN never matches anything written", not FORBIDDEN.search(text))
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = main(["--seed", "5", "--launch", "4", "--out", str(out / "cli")])
        chk("the CLI writes the add-on and prints its id", rc == 0 and (out / "cli" / "verve.d1-L04" / "swofty.json")
            .is_file() and "verve.d1-l04" in buf.getvalue())
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
    pin = draw(seed, launch)
    print(f"D1 seed {seed} launch {launch} -> {out / folder_name(launch)} (id {addon_id(launch)})")
    print(f"  {'driver':<24}{'team':<12}{'pinned':>7}")
    for d in ROSTER:
        print(f"  {d:<24}{TEAM_OF[d]:<12}{pin[d]:>7}")
    print(f"  pinned {sum(pin.values())}, stock {len(ROSTER) - sum(pin.values())}")
    print(f"expected ops: {len(ops)} = {sum(pin.values())} pinned drivers x {len(FIELDS)} race_start bounds = {VALUE}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
