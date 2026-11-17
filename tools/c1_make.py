"""C-1 start calibration: the seeded rotation and the per-launch test add-on (docs/verve_c1_prereg.md).

Usage:
    python -I tools/c1_make.py --seed <int> --launch <L> --out <dir>
    python -I tools/c1_make.py --paths            # the 76 race_start paths (= docs/stock/d1_paths.txt), one per line
    python -I tools/c1_make.py --selftest

Writes <out>/verve.c1-L<LL>/{swofty.json, db/c1.json}, plus <out>/assignment.csv (driver, team, arm) and
<out>/expected_ops.csv (path, field, value). Use one --out folder per launch: the two CSVs keep fixed names.

Lever (D1's): for a PINNED driver, all four ai_driver_config.race_start reaction bounds = the arm's level
(min_reaction_time_lower_bound, min_reaction_time_upper_bound, max_reaction_time_lower_bound,
max_reaction_time_upper_bound). No other writes: no traits, no maps, no bundles.

Arms: 0 = stock (no op), 1 = 0.20, 2 = 0.35, 3 = 0.65 (ARMS / LEVELS).
Rotation (prereg, approved; seed fixed before launch 1, proposed 2026111705): one seeded draw for the whole BATCH
(rotation(seed), seed string "verve-c1|<seed>", distinct from D1's and V-1's) shuffles the 9 two-AI teams of
tools/v1_make.py's TEAMS to an index t = 0..8 and flips a coin per team naming its teammates X and Y. In launch L,
X gets arm (t + L) mod 4 and Y gets arm (t + L + 2) mod 4, so teammates are never in the same arm and every car moves
up one arm per launch. Alonso (v1_make's SOLO, no AI teammate) is always stock. Launch 1: stock 5 / 0.20 5 / 0.35 4 /
0.65 5 (14 pinned, 56 ops); launch 2: 6 / 4 / 5 / 4 (13 pinned, 52 ops), for every seed.

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
import d1_make as dm  # noqa: E402   the four race_start keys and their 76 paths (one source of truth)
import v1_make as vm  # noqa: E402

REPO = Path(__file__).resolve().parent.parent
KEY_CACHE = REPO / "docs" / "stock" / "v1_key_cache_26566308.csv"

ROSTER, TEAMS, TEAM_OF, SOLO = vm.ROSTER, vm.TEAMS, vm.TEAM_OF, vm.SOLO
DRIVER_SELECT = vm.DRIVER_SELECT
FORBIDDEN = vm.FORBIDDEN
RACE_START, KEYS, FIELDS = dm.RACE_START, dm.KEYS, dm.FIELDS
SEED_FMT = "verve-c1|{seed}"     # one draw per batch; distinct from D1's "verve-d1|..." and V-1's "verve-v1|..."
PROPOSED_SEED = 2026111705
ARMS = ["stock", "0.20", "0.35", "0.65"]          # arm index -> label (= the op value for a pinned arm)
LEVELS = {1: 0.20, 2: 0.35, 3: 0.65}               # pinned arm index -> the race_start value
TWO_AI = [t for t, ds in TEAMS if len(ds) == 2]


# --------------------------------------------------------------------------------------
# the rotation (pure)
# --------------------------------------------------------------------------------------

def rotation(seed: int) -> dict[str, tuple[int, str, str]]:
    """{team: (t, X, Y)} for the 9 two-AI teams, fixed for the batch. Pure and deterministic in seed (a str seed is
    stable across runs and machines: random.seed version 2 hashes it with sha512, not hash())."""
    rng = random.Random(SEED_FMT.format(seed=seed))
    order = TWO_AI[:]
    rng.shuffle(order)
    out = {}
    for t, ds in TEAMS:
        if len(ds) == 2:
            p = rng.randrange(2)
            out[t] = (order.index(t), ds[p], ds[1 - p])
    return out


def draw(seed: int, launch: int) -> dict[str, int]:
    """{driver: arm index 0-3} for one launch: X (t + L) mod 4, Y (t + L + 2) mod 4, Alonso 0 (stock)."""
    out = {d: 0 for d in SOLO}
    for _, (t, x, y) in rotation(seed).items():
        out[x], out[y] = (t + launch) % 4, (t + launch + 2) % 4
    return {d: out[d] for d in ROSTER}


def counts(arm: dict[str, int]) -> list[int]:
    return [sum(1 for a in arm.values() if a == k) for k in range(4)]


# --------------------------------------------------------------------------------------
# ops and the add-on
# --------------------------------------------------------------------------------------

def build_ops(arm: dict[str, int]) -> list[dict]:
    return [vm.op(DRIVER_SELECT.format(d), f, ARMS[arm[d]]) for d in ROSTER if arm[d] for f in FIELDS]


def all_paths() -> list[str]:
    """Every path a C-1 launch can write: D1's 76 (19 AI drivers x 4 keys); the key cache already holds them."""
    return dm.all_paths()


def addon_id(launch: int) -> str:
    return f"verve.c1-l{launch:02d}"


def folder_name(launch: int) -> str:
    return f"verve.c1-L{launch:02d}"


def manifest(seed: int, launch: int, arm: dict[str, int], n_ops: int) -> dict:
    c = counts(arm)
    return {
        "schema_version": 1, "id": addon_id(launch),
        "name": f"Verve test C1 launch {launch:02d} (race_start calibration)",
        "version": "0.0.1", "author": "TC Verve",
        "description": f"Test-only addon for C-1 (docs/verve_c1_prereg.md), seed {seed}, launch {launch}: all four "
                       f"ai_driver_config.race_start reaction bounds = one level per pinned driver (0.20 on {c[1]}, "
                       f"0.35 on {c[2]}, 0.65 on {c[3]} drivers; the seeded rotation, assignment.csv); {c[0]} drivers "
                       f"incl. Alonso stay stock. {n_ops} ops. Not for play.",
        "license": "MIT", "category": "ai", "kind": ["database"],
        # absolute values; 26566308 = F1 25 1.0.145 (docs/harness.md)
        "compat": {"game": "f1_25", "game_builds": [">=26566308"], "launcher": ">=1.9.34"},
        "requires": [{"id": "swofty.core", "version": ">=0.2.13"}], "saves": {"affects": False},
        "operations": {"database": ["db/c1.json"]},
    }


def op_problems(o: dict) -> list[str]:
    """Why an op is malformed, forbidden or outside C-1's lever (empty = fine)."""
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
    if val not in ARMS[1:]:
        p.append(f"value {val!r}, not a level {ARMS[1:]}")
    return p


def ops_problems(ops: list[dict]) -> list[str]:
    """Per-op problems, plus a driver whose four bounds aren't all one level (a pinned car = one value, all 4)."""
    probs = [x for o in ops for x in op_problems(o)]
    by: dict[str, dict[str, str]] = {}
    for o in ops:
        by.setdefault(o["select"], {})[o["field"]] = o["value"]
    for sel, f in by.items():
        if sorted(f) != sorted(FIELDS) or len(set(f.values())) != 1:
            probs.append(f"{sel}: not all four race_start bounds at one level ({f})")
    if len({(o["select"], o["field"]) for o in ops}) != len(ops):
        probs.append("duplicate (select, field)")
    return probs


def check_ops(ops: list[dict]) -> None:
    probs = ops_problems(ops)
    if probs:
        sys.exit("refusing to write: " + "; ".join(probs[:5]))


def write_launch(seed: int, launch: int, out: Path) -> list[dict]:
    arm = draw(seed, launch)
    ops = build_ops(arm)
    check_ops(ops)
    folder = out / folder_name(launch)
    (folder / "db").mkdir(parents=True, exist_ok=True)
    (folder / "db" / "c1.json").write_text(json.dumps({"schema_version": 1, "ops": ops}, indent=2) + "\n", "utf-8")
    (folder / "swofty.json").write_text(json.dumps(manifest(seed, launch, arm, len(ops)), indent=2) + "\n", "utf-8")
    with (out / "assignment.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["driver", "team", "arm"])
        for d in ROSTER:
            w.writerow([d, TEAM_OF[d], ARMS[arm[d]]])
    with (out / "expected_ops.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["path", "field", "value"])
        w.writerows([o["select"], o["field"], o["value"]] for o in ops)
    return ops


def read_assignment(path: Path) -> dict[str, int]:
    """{driver: arm index} from assignment.csv (arm labels stock / 0.20 / 0.35 / 0.65)."""
    with path.open(encoding="utf-8", newline="") as f:
        return {r["driver"]: ARMS.index(r["arm"]) for r in csv.DictReader(f)}


def assignment_problems(arm: dict[str, int]) -> list[str]:
    """Structural checks on an assignment (as read back from assignment.csv)."""
    p = []
    if set(arm) != set(ROSTER):
        return [f"drivers {sorted(set(arm) ^ set(ROSTER))} differ from the roster"]
    if set(arm.values()) - {0, 1, 2, 3}:
        p.append("an arm is not 0-3")
    for t, ds in TEAMS:
        if len(ds) == 2 and arm[ds[0]] == arm[ds[1]]:
            p.append(f"{t}: teammates in the same arm")
    if any(arm[d] for d in SOLO):
        p.append(f"solo driver pinned: {[d for d in SOLO if arm[d]]}")
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

    seeds, launches = [1, 7, PROPOSED_SEED, 123456789], range(1, 9)
    draws = {(s, L): draw(s, L) for s in seeds for L in launches}
    rots = {s: rotation(s) for s in seeds}
    chk("roster and teams come from v1_make (19 AI drivers, 9 two-AI teams, Alonso solo)",
        ROSTER is vm.ROSTER and TEAMS is vm.TEAMS and len(ROSTER) == 19 and SOLO == ["fernando_alonso"]
        and len(TWO_AI) == 9)
    chk("determinism (same seed -> same rotation, same seed + launch -> same arms)",
        all(rotation(s) == rots[s] for s in seeds) and all(draw(s, L) == draws[(s, L)] for s, L in draws))
    chk("the rotation is fixed for the batch: t is a permutation of 0..8, X/Y are the team's two drivers",
        all(sorted(t for t, _, _ in r.values()) == list(range(9)) and all({x, y} == set(dict(TEAMS)[tm])
                                                                          for tm, (_, x, y) in r.items())
            for r in rots.values()))
    chk("different seeds give different rotations", len({json.dumps(r, sort_keys=True) for r in rots.values()}) == 4)
    chk("the seed string is C-1's own (verve-c1|seed, not D1's verve-d1|... or V-1's verve-v1|...)",
        SEED_FMT.format(seed=1) == "verve-c1|1")
    chk("the rotation rule: X = (t + L) mod 4, Y = (t + L + 2) mod 4, for every seed and launch",
        all(draws[(s, L)][x] == (t + L) % 4 and draws[(s, L)][y] == (t + L + 2) % 4
            for s, L in draws for t, x, y in rots[s].values()))
    chk("every car moves up one arm from launch to launch (Alonso stays stock)",
        all(draws[(s, L + 1)][d] == (draws[(s, L)][d] + 1) % 4 for s in seeds for L in range(1, 8)
            for d in ROSTER if d not in SOLO))
    chk("Alonso always stock", all(a["fernando_alonso"] == 0 for a in draws.values()))
    chk("teammates never in the same arm", all(a[ds[0]] != a[ds[1]] for a in draws.values()
                                               for _, ds in TEAMS if len(ds) == 2))
    c1 = {s: counts(draws[(s, 1)]) for s in seeds}
    c2 = {s: counts(draws[(s, 2)]) for s in seeds}
    chk("launch 1: stock 5 / 0.20 5 / 0.35 4 / 0.65 5 for every seed (the prereg's table)",
        all(c == [5, 5, 4, 5] for c in c1.values()), str(c1[PROPOSED_SEED]))
    chk("launch 2: stock 6 / 0.20 4 / 0.35 5 / 0.65 4 for every seed (the prereg's table)",
        all(c == [6, 4, 5, 4] for c in c2.values()), str(c2[PROPOSED_SEED]))
    chk("car-launches over the 2 launches: stock 11, 0.20 9, 0.35 9, 0.65 9",
        all([a + b for a, b in zip(c1[s], c2[s])] == [11, 9, 9, 9] for s in seeds))
    n = sum(rotation(s)[TWO_AI[0]][1] == dict(TEAMS)[TWO_AI[0]][0] for s in range(2000))
    chk("the X/Y coin is fair (the first team's first driver named X in 2000 seeds)", 900 < n < 1100, str(n))

    all_ops = {k: build_ops(a) for k, a in draws.items()}
    chk("56 ops in launch 1 (14 pinned x 4 keys), 52 in launch 2 (13 x 4)",
        all(len(all_ops[(s, 1)]) == 56 and len(all_ops[(s, 2)]) == 52 for s in seeds))
    chk("the ops are exactly the 4 race_start bounds = the arm's level on each pinned driver, and nothing else", all(
        sorted((o["select"], o["field"], o["value"]) for o in ops) ==
        sorted((DRIVER_SELECT.format(d), RACE_START + k, ARMS[draws[key][d]]) for d in ROSTER if draws[key][d]
               for k in KEYS) for key, ops in all_ops.items()))
    chk("a pinned car has all four bounds at its level (one value, all 4), and ops_problems is clean",
        not any(ops_problems(ops) for ops in all_ops.values()))
    chk("the levels are as specified (0.20 / 0.35 / 0.65) and the keys are D1's four",
        ARMS == ["stock", "0.20", "0.35", "0.65"] and LEVELS == {1: 0.20, 2: 0.35, 3: 0.65} and FIELDS == [
            "ai_driver_config.race_start.min_reaction_time_lower_bound",
            "ai_driver_config.race_start.min_reaction_time_upper_bound",
            "ai_driver_config.race_start.max_reaction_time_lower_bound",
            "ai_driver_config.race_start.max_reaction_time_upper_bound"])
    aic = vm.stock_aic_keys()
    chk("every level differs from every stock bound (docs/stock/ai_driver_config.csv: no op dropped as equal to stock)",
        all(f in aic and float(aic[f]) != LEVELS[k] for f in FIELDS for k in LEVELS),
        str({f[len(RACE_START):]: aic.get(f) for f in FIELDS}))
    chk("no forbidden key (cede_position.*, yellow_flag_*, flying_lap_yield_*) in any op",
        not any(FORBIDDEN.search(o["select"] + " " + o["field"]) for ops in all_ops.values() for o in ops))
    sel = DRIVER_SELECT.format("max_verstappen")
    chk("the guard catches a forbidden key, another key, another value, Alonso and the player", all(op_problems(x) for x in [
        vm.op(sel, vm.AIC + "cede_position.yellow_flag_ramp_up_time", "0.20"),
        vm.op(sel, vm.AIC + "cede_position.flying_lap_yield_to_human_track_speed_diff", "0.35"),
        vm.op(sel, vm.AIC + "race_start.max_bad_start_lower_bound", "0.65"),
        vm.op(sel, FIELDS[0], "0.5"),
        vm.op(DRIVER_SELECT.format("fernando_alonso"), FIELDS[0], "0.20"),
        vm.op(DRIVER_SELECT.format(vm.PLAYER), FIELDS[0], "0.20")]))
    mixed = [vm.op(sel, f, "0.20") for f in FIELDS[:3]] + [vm.op(sel, FIELDS[3], "0.35")]
    chk("ops_problems catches a car with mixed levels or only some of its bounds",
        ops_problems(mixed) and ops_problems(mixed[:3]) and not ops_problems([vm.op(sel, f, "0.20") for f in FIELDS]))
    chk("assignment_problems: a valid draw is clean, a broken one is caught",
        not assignment_problems(draws[(1, 1)]) and assignment_problems({**draws[(1, 1)], "fernando_alonso": 1})
        and assignment_problems({**draws[(1, 1)], "oscar_piastri": 2, "lando_norris": 2}))
    paths = all_paths()
    have = [ln.strip() for ln in dm.PATHS_FILE.read_text(encoding="utf-8").splitlines()
            if ln.strip() and not ln.startswith("#")] if dm.PATHS_FILE.exists() else []
    chk("76 paths, = docs/stock/d1_paths.txt (no new path for the key cache)", len(paths) == 76 == len(set(paths))
        and have == paths)
    cached = set()
    if KEY_CACHE.exists():
        with KEY_CACHE.open(encoding="utf-8-sig", newline="") as f:
            cached = {r["path"] for r in csv.DictReader(f)}
    chk("every op path is in the 26566308 key cache (check_applied runs offline)",
        all(f"{o['select']}.{o['field']}" in cached for ops in all_ops.values() for o in ops), f"{len(cached)} cached")

    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp)
        w_ops = write_launch(PROPOSED_SEED, 2, out)
        man = json.loads((out / "verve.c1-L02" / "swofty.json").read_text(encoding="utf-8"))
        db = json.loads((out / "verve.c1-L02" / "db" / "c1.json").read_text(encoding="utf-8"))
        with (out / "expected_ops.csv").open(encoding="utf-8") as f:
            exp = list(csv.DictReader(f))
        with (out / "assignment.csv").open(encoding="utf-8") as f:
            asg = list(csv.DictReader(f))
        chk("files written: verve.c1-L02/{swofty.json, db/c1.json}, assignment.csv, expected_ops.csv",
            all((out / p).is_file() for p in ("verve.c1-L02/swofty.json", "verve.c1-L02/db/c1.json",
                                              "assignment.csv", "expected_ops.csv")))
        chk("manifest id (lowercase) / version / compat / requires / kind / saves",
            man["id"] == "verve.c1-l02" == addon_id(2) == vm.addon_id(2).replace("v1", "c1")
            and man["version"] == "0.0.1"
            and man["compat"] == {"game": "f1_25", "game_builds": [">=26566308"], "launcher": ">=1.9.34"}
            and man["requires"] == [{"id": "swofty.core", "version": ">=0.2.13"}] and man["kind"] == ["database"]
            and man["saves"] == {"affects": False} and man["operations"] == {"database": ["db/c1.json"]}
            and "52 ops" in man["description"] and "C-1" in man["description"])
        chk("db/c1.json = expected_ops.csv", db == {"schema_version": 1, "ops": w_ops} and len(w_ops) == 52 and
            [(e["path"], e["field"], e["value"]) for e in exp] == [(o["select"], o["field"], o["value"]) for o in w_ops])
        chk("assignment.csv = draw (driver, team, arm)", [r["driver"] for r in asg] == ROSTER and all(
            ARMS.index(r["arm"]) == draw(PROPOSED_SEED, 2)[r["driver"]] and r["team"] == TEAM_OF[r["driver"]]
            for r in asg) and list(asg[0]) == ["driver", "team", "arm"]
            and read_assignment(out / "assignment.csv") == draw(PROPOSED_SEED, 2))
        text = "".join(p.read_text(encoding="utf-8") for p in out.rglob("*") if p.is_file())
        chk("FORBIDDEN never matches anything written", not FORBIDDEN.search(text))
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = main(["--seed", str(PROPOSED_SEED), "--launch", "1", "--out", str(out / "cli")])
        chk("the CLI writes the add-on and prints its id and counts", rc == 0 and (out / "cli" / "verve.c1-L01" /
                                                                                  "swofty.json").is_file()
            and "verve.c1-l01" in buf.getvalue() and "56 ops" in buf.getvalue())
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
    arm = draw(seed, launch)
    rot = rotation(seed)
    t_of = {d: (t, "X" if d == x else "Y") for _, (t, x, y) in rot.items() for d in (x, y)}
    print(f"C1 seed {seed} launch {launch} -> {out / folder_name(launch)} (id {addon_id(launch)})")
    print(f"  {'driver':<24}{'team':<12}{'t':>3}{'X/Y':>5}{'arm':>7}")
    for d in ROSTER:
        t, xy = t_of.get(d, ("-", "-"))
        print(f"  {d:<24}{TEAM_OF[d]:<12}{t:>3}{xy:>5}{ARMS[arm[d]]:>7}")
    c = counts(arm)
    print(f"  stock {c[0]}, 0.20 {c[1]}, 0.35 {c[2]}, 0.65 {c[3]}")
    print(f"expected ops: {len(ops)} ops = {len(ROSTER) - c[0]} pinned drivers x {len(FIELDS)} race_start bounds")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
