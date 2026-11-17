"""S-1 screen of six per-driver ai_driver_config keys: the seeded balanced draw and the per-launch test add-on
(docs/verve_s1_prereg.md, APPROVED 2026-11-17).

Usage:
    python -I tools/s1_make.py --seed <int> --launch <L> --out <dir> [--levels <json>] [--step F:LEVEL:k ...]
    python -I tools/s1_make.py --smoke --seed 2026111707 --launch 1 --out <dir> [--levels <json>] [--step ...]
    python -I tools/s1_make.py --paths            # the 114 paths (docs/stock/s1_paths.txt), with its header
    python -I tools/s1_make.py --selftest

Writes <out>/verve.s1-L<LL>/{swofty.json, db/s1.json} (id verve.s1-l<LL>), plus <out>/assignment.csv (driver, team,
the six factors: 1 = HIGH, 0 = LOW), <out>/expected_ops.csv (path, field, value) and <out>/levels.json (every level's
steps and value, the dropped factors, the smoke flag, the --levels source). Use one --out folder per launch.

Factors (prereg section 1; one key each, no bundles; HIGH = the "more" end; values are written as these strings):
    YIELD       alongside.yield_overtake_rate                   stock 1        HIGH 0.5          LOW 2
    EXIT_ERR    exit_fallibility.throttle_error_qualifying_race stock curve    HIGH the diagonal LOW flat 0.48
    OVERLAP     overtake.overlap_percentage                     stock curve    HIGH flat 0.05    LOW flat 0.9
    BLK_SPEED   blocking.blocking_speed_differential            stock 0.6      HIGH 0.15         LOW 2.4
    BLK_THREAT  blocking.blocking_threat_time_modifier          stock 0.175    HIGH 0.7          LOW 0.04375
    COMMIT      overtake.braking_zone_abort_overtake_time       stock 0.6667   HIGH 0.1          LOW 1.0667
Every one of the 19 AI drivers gets HIGH or LOW for every factor: 6 x 19 = 114 ops per launch, none equal to stock.

Assignment (prereg section 2): per factor and launch, draw(seed, launch), seed string "verve-s1|{seed}|{launch}": in
each of the 9 two-AI teams of tools/v1_make.py's TEAMS a seeded coin puts one teammate HIGH and the other LOW; Alonso
alternates HIGH / LOW by launch with a seeded phase per factor ("verve-s1-solo-phase|{seed}"). Factors are drawn
independently, so each has 9 or 10 cars HIGH. draw is pure: tools/s1_check.py's permutation test calls it with other
seeds. S-1's seed is 2026111706; the extremes smoke's is 2026111707, launch 1.

--smoke (prereg section 4): the extremes validity smoke. It is draw(2026111707, 1) exactly: for each factor the seeded
half carries HIGH and the other half LOW, so every car runs every factor at one of its two extremes. --smoke refuses
any other seed or launch, and marks the manifest and levels.json as the smoke.

--levels <json> / --step F:LEVEL:k (prereg section 4, after a failed smoke): the stepped levels, as
{"<factor>": {"HIGH": k, "LOW": k}} with k = 0 (the extreme), 1 (halfway to stock), 2 (a quarter of the way) or
"stock" (3 = stock). Only the named levels change; --step applies after --levels. A level at stock gets no op; a factor
with both levels at stock is DROPPED (no ops, recorded). tools/s1_check.py --smoke writes the next file to pass here.
The step: scalars in log space, x = stock x (x_ext / stock)^(0.5^k), written to 3 significant figures (the prereg's
table); curves pointwise in y on the union of the stock and extreme x points, y = stock + 0.5^k x (y_ext - stock),
written exactly (6 decimals). At a repeated x (the curves' doubled end points) the points pair up in order.

Hard rule: no op ever touches cede_position.*, yellow_flag_* or flying_lap_yield_* (v1_make's FORBIDDEN; the selftest
asserts it on every op and on every file written).
"""
from __future__ import annotations

import csv
import functools
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
STOCK = REPO / "docs" / "stock"
PATHS_FILE = STOCK / "s1_paths.txt"
KEY_CACHE = STOCK / "v1_key_cache_26566308.csv"

ROSTER, TEAMS, TEAM_OF, SOLO = vm.ROSTER, vm.TEAMS, vm.TEAM_OF, vm.SOLO
FORBIDDEN = vm.FORBIDDEN
AIC = vm.AIC
SEED_FMT = "verve-s1|{seed}|{launch}"        # distinct from V-1's, D1's, D4's and C-1's
PHASE_FMT = "verve-s1-solo-phase|{seed}"
S1_SEED = 2026111706
SMOKE_SEED = 2026111707
SMOKE_LAUNCH = 1
N_OPS = 114

EXIT_STOCK = ("@v2@minx:0,maxx:1,miny:-1,maxy:1,0:0.4,0:0,0.05:0.28,0.15:0.415,0.62:0.48,0.92:0.55,0.97:0.685,"
              "1:1,1:0.77")
EXIT_HEADER = "@v2@minx:0,maxx:1,miny:-1,maxy:1"


def exit_flat(y: float) -> str:
    """A flat curve on exit_fallibility's own axes (x 0..1, y -1..1), v1_make.flat_curve's point format."""
    return f"{EXIT_HEADER},0:{y},0:{y},1:{y},1:{y}"


# factor -> key, stock, HIGH, LOW, kind, cite (prereg section 1)
LEVELS = {
    "YIELD": {"key": AIC + "alongside.yield_overtake_rate", "stock": "1", "HIGH": "0.5", "LOW": "2", "kind": "scalar",
              "cite": "lap1-ai R:68 (0.5, holds the line); 2 = V-1's mirror; tick-read"},
    "EXIT_ERR": {"key": AIC + "exit_fallibility.throttle_error_qualifying_race", "stock": EXIT_STOCK,
                 "HIGH": f"{EXIT_HEADER},0:0,0:0,1:1,1:1", "LOW": exit_flat(0.48), "kind": "curve",
                 "cite": "the curve's own axes; HIGH the diagonal (more errors), LOW flat at the stock median 0.48; "
                         "decoded (F-05)"},
    "OVERLAP": {"key": AIC + "overtake.overlap_percentage", "stock": vm.OVERLAP_STOCK, "HIGH": vm.flat_curve(0.05),
                "LOW": vm.flat_curve(0.9), "kind": "curve",
                "cite": "lap1-ai R:56 (flat 0.05, commits early); B-0017 draft (flat 0.9); tick-read, decoded (F-07)"},
    "BLK_SPEED": {"key": AIC + "blocking.blocking_speed_differential", "stock": "0.6", "HIGH": "0.15", "LOW": "2.4",
                  "kind": "scalar", "cite": "x0.25 / x4 of stock (no shipped value); tick-read, sign unknown"},
    "BLK_THREAT": {"key": AIC + "blocking.blocking_threat_time_modifier", "stock": "0.175", "HIGH": "0.7",
                   "LOW": "0.04375", "kind": "scalar", "cite": "x4 / x0.25 of stock; tick-read, sign unknown"},
    "COMMIT": {"key": AIC + "overtake.braking_zone_abort_overtake_time", "stock": "0.6667", "HIGH": "0.1",
               "LOW": "1.0667", "kind": "scalar", "cite": "lap1-ai R:46 (0.1); kizi Big's passive end (x1.6)"},
}
FACTORS = list(LEVELS)
SIDES = ("HIGH", "LOW")
MAX_STEPS = 2       # 1 -> 0.5 -> 0.25 of the distance; past that, stock
STOCK_STEP = 3      # "stock"


# --------------------------------------------------------------------------------------
# the draw (pure)
# --------------------------------------------------------------------------------------

def draw(seed: int, launch: int) -> dict[str, dict[str, int]]:
    """{driver: {factor: 1 (HIGH) / 0 (LOW)}} for one launch. Pure and deterministic in (seed, launch); str seeds are
    stable across runs and machines (random.seed version 2 hashes them with sha512, not hash())."""
    rng = random.Random(SEED_FMT.format(seed=seed, launch=launch))
    phase_rng = random.Random(PHASE_FMT.format(seed=seed))      # per seed only, so the solo driver alternates
    phase = {f: phase_rng.randrange(2) for f in FACTORS}
    out = {d: {} for d in ROSTER}
    for f in FACTORS:
        for _, ds in TEAMS:
            if len(ds) == 2:
                hi = rng.randrange(2)
                out[ds[hi]][f], out[ds[1 - hi]][f] = 1, 0
            else:
                out[ds[0]][f] = (launch + phase[f]) % 2
    return out


# --------------------------------------------------------------------------------------
# curves and steps
# --------------------------------------------------------------------------------------

def parse_curve(s: str) -> tuple[str, list[tuple[float, float]]]:
    """'@v2@minx:..,maxx:..,miny:..,maxy:..,x:y,...' -> (the header string, [(x, y), ...]); x must not descend."""
    if not s.startswith("@v2@"):
        raise ValueError(f"not a @v2@ curve: {s[:20]!r}")
    items = s[4:].split(",")
    head = items[:4]
    if [h.split(":")[0] for h in head] != ["minx", "maxx", "miny", "maxy"]:
        raise ValueError(f"bad curve header: {s!r}")
    pts = []
    for it in items[4:]:
        x, y = it.split(":")
        pts.append((float(x), float(y)))
    if len(pts) < 2 or any(b[0] < a[0] for a, b in zip(pts, pts[1:])):
        raise ValueError(f"bad curve points: {s!r}")
    return "@v2@" + ",".join(head), pts


def curve_value(pts: list[tuple[float, float]], x: float, k: int = 0) -> float:
    """The curve's y at x: the k-th stored point there (in order; the last one if it has fewer), else linear between
    the neighbouring points, held flat outside them."""
    at = [y for xx, y in pts if xx == x]
    if at:
        return at[min(k, len(at) - 1)]
    if x < pts[0][0]:
        return pts[0][1]
    if x > pts[-1][0]:
        return pts[-1][1]
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        if x0 < x < x1:
            return y0 + (y1 - y0) * (x - x0) / (x1 - x0)
    raise AssertionError("unreachable")


def step_curve(stock: str, ext: str, frac: float) -> str:
    """stock + frac x (ext - stock), pointwise in y on the union of both curves' x points (repeated x: in order)."""
    hs, ps = parse_curve(stock)
    he, pe = parse_curve(ext)
    if hs != he:
        raise ValueError(f"the curves' axes differ: {hs} vs {he}")
    xs = sorted({x for x, _ in ps} | {x for x, _ in pe})
    out = []
    for x in xs:
        m = max(sum(1 for xx, _ in ps if xx == x), sum(1 for xx, _ in pe if xx == x), 1)
        for k in range(m):
            ys, ye = curve_value(ps, x, k), curve_value(pe, x, k)
            out.append(f"{vm.fmt(x)}:{vm.fmt(ys + frac * (ye - ys))}")
    return hs + "," + ",".join(out)


def sig3(x: float) -> str:
    return f"{x:.3g}"


def level_value(f: str, side: str, k: int) -> str:
    """The value written for factor f at side HIGH/LOW after k steps (0 = the extreme, 3 = stock)."""
    lv = LEVELS[f]
    if k == 0:
        return lv[side]
    if k >= STOCK_STEP:
        return lv["stock"]
    frac = 0.5 ** k
    if lv["kind"] == "curve":
        return step_curve(lv["stock"], lv[side], frac)
    st = float(lv["stock"])
    return sig3(st * (float(lv[side]) / st) ** frac)


def no_steps() -> dict[str, dict[str, int]]:
    return {f: {s: 0 for s in SIDES} for f in FACTORS}


def parse_k(v) -> int:
    if v == "stock" or v == STOCK_STEP:
        return STOCK_STEP
    if isinstance(v, bool) or not isinstance(v, int) or not 0 <= v <= MAX_STEPS:
        raise ValueError(f"a step must be 0, 1, 2 or \"stock\", not {v!r}")
    return v


def merge_steps(steps: dict, override: dict) -> dict:
    """steps updated by {"<factor>": {"HIGH": k, "LOW": k}} (only the named levels change)."""
    out = {f: dict(v) for f, v in steps.items()}
    if not isinstance(override, dict):
        raise ValueError("the levels must be a JSON object {factor: {HIGH|LOW: k}}")
    for f, sides in override.items():
        if f not in LEVELS:
            raise ValueError(f"unknown factor {f!r} (one of {', '.join(FACTORS)})")
        if not isinstance(sides, dict) or not sides:
            raise ValueError(f"{f}: expected {{\"HIGH\": k, \"LOW\": k}}")
        for s, v in sides.items():
            if s not in SIDES:
                raise ValueError(f"{f}: unknown level {s!r} (HIGH or LOW)")
            out[f][s] = parse_k(v)
    return out


def parse_step_arg(a: str) -> dict:
    m = re.fullmatch(r"([A-Z_]+):(HIGH|LOW):(\d|stock)", a)
    if not m:
        raise ValueError(f"--step {a!r}: expected FACTOR:HIGH|LOW:k (k 0, 1, 2 or stock)")
    return {m[1]: {m[2]: parse_k("stock" if m[3] == "stock" else int(m[3]))}}


def dropped(steps: dict) -> list[str]:
    return [f for f in FACTORS if all(steps[f][s] >= STOCK_STEP for s in SIDES)]


def levels_record(seed: int, launch: int, steps: dict, smoke: bool, source: str | None) -> dict:
    return {"seed": seed, "launch": launch, "smoke": smoke, "levels_source": source,
            "stepped": {f: {s: steps[f][s] for s in SIDES if steps[f][s]} for f in FACTORS
                        if any(steps[f][s] for s in SIDES)},
            "dropped": dropped(steps),
            "factors": {f: {"key": LEVELS[f]["key"], "stock": LEVELS[f]["stock"],
                            **{s: {"steps": steps[f][s], "value": level_value(f, s, steps[f][s]),
                                   "at_stock": steps[f][s] >= STOCK_STEP} for s in SIDES}} for f in FACTORS}}


# --------------------------------------------------------------------------------------
# ops and the add-on
# --------------------------------------------------------------------------------------

def build_ops(assign: dict[str, dict[str, int]], steps: dict | None = None) -> list[dict]:
    steps = steps or no_steps()
    ops = []
    for d in ROSTER:
        sel = vm.DRIVER_SELECT.format(d)
        for f in FACTORS:
            side = "HIGH" if assign[d][f] else "LOW"
            val = level_value(f, side, steps[f][side])
            if val != LEVELS[f]["stock"]:
                ops.append(vm.op(sel, LEVELS[f]["key"], val))
    return ops


def all_paths() -> list[str]:
    return [f"{vm.DRIVER_SELECT.format(d)}.{LEVELS[f]['key']}" for d in ROSTER for f in FACTORS]


PATHS_HEADER = [
    "# S-1 (docs/verve_s1_prereg.md): every path an S-1 launch can write, 19 AI drivers x 6 ai_driver_config keys.",
    "# For tools/check_applied.ps1 -PrefillOnly (fills docs/stock/v1_key_cache_26566308.csv). Regenerate: "
    "python -I tools/s1_make.py --paths",
]


def addon_id(launch: int) -> str:
    return f"verve.s1-l{launch:02d}"


def folder_name(launch: int) -> str:
    return f"verve.s1-L{launch:02d}"


def manifest(seed: int, launch: int, n_ops: int, steps: dict, smoke: bool) -> dict:
    st = levels_record(seed, launch, steps, smoke, None)
    stepped = "; ".join(f"{f} " + ", ".join(f"{s} {'stock' if k >= STOCK_STEP else f'step {k}'}" for s, k in v.items())
                        for f, v in st["stepped"].items())
    what = "the extremes validity smoke" if smoke else "the screen"
    return {
        "schema_version": 1, "id": addon_id(launch),
        "name": f"Verve test S-1 launch {launch:02d} ({'extremes smoke' if smoke else 'six-key screen'})",
        "version": "0.0.1", "author": "TC Verve",
        "description": f"Test-only addon for S-1 (docs/verve_s1_prereg.md), {what}, seed {seed}, launch {launch}: six "
                       f"per-driver ai_driver_config keys (yield, exit error, overlap, the two blocking keys, the "
                       f"braking-zone abort time) at HIGH or LOW per driver (assignment.csv). "
                       f"{'Stepped levels: ' + stepped + '. ' if stepped else 'No stepped levels. '}"
                       f"{'Dropped: ' + ', '.join(st['dropped']) + '. ' if st['dropped'] else ''}{n_ops} ops. Not for play.",
        "license": "MIT", "category": "ai", "kind": ["database"],
        # absolute values; 26566308 = F1 25 1.0.145 (docs/harness.md)
        "compat": {"game": "f1_25", "game_builds": [">=26566308"], "launcher": ">=1.9.34"},
        "requires": [{"id": "swofty.core", "version": ">=0.2.13"}], "saves": {"affects": False},
        "operations": {"database": ["db/s1.json"]},
    }


@functools.lru_cache(maxsize=None)
def allowed_values(f: str) -> frozenset[str]:
    return frozenset(level_value(f, s, k) for s in SIDES for k in range(MAX_STEPS + 1))


def op_problems(o: dict) -> list[str]:
    """Why an op is malformed, forbidden or outside S-1's six keys and their registered levels (empty = fine)."""
    if set(o) != {"op", "select", "field", "value"} or o.get("op") != "set":
        return [f"bad op shape: {o}"]
    p = []
    sel, field, val = o["select"], o["field"], o["value"]
    if FORBIDDEN.search(sel) or FORBIDDEN.search(field) or FORBIDDEN.search(str(val)):
        p.append(f"FORBIDDEN key: {sel} {field}")
    m = re.fullmatch(r"entrants\.drivers\.driver\[_metadata_=(" + vm.LABEL_RE + r")\]", sel)
    if not m:
        p.append(f"unexpected select: {sel}")
    elif m[1] not in ROSTER:
        p.append(f"driver not on the AI roster: {m[1]}")
    f = next((x for x in FACTORS if LEVELS[x]["key"] == field), None)
    if f is None:
        p.append(f"field {field!r} is not one of S-1's six keys")
    elif val not in allowed_values(f):
        p.append(f"{f}: value {val!r} is not a registered level or step")
    elif val == LEVELS[f]["stock"]:
        p.append(f"{f}: an op equal to stock")
    if not vm.is_value(str(val)):
        p.append(f"bad value: {val!r}")
    return p


def check_ops(ops: list[dict]) -> None:
    probs = [x for o in ops for x in op_problems(o)]
    if probs:
        sys.exit("refusing to write: " + "; ".join(probs[:5]))


def write_launch(seed: int, launch: int, out: Path, steps: dict | None = None, smoke: bool = False,
                 source: str | None = None) -> list[dict]:
    steps = steps or no_steps()
    assign = draw(seed, launch)
    ops = build_ops(assign, steps)
    check_ops(ops)
    folder = out / folder_name(launch)
    (folder / "db").mkdir(parents=True, exist_ok=True)
    (folder / "db" / "s1.json").write_text(json.dumps({"schema_version": 1, "ops": ops}, indent=2) + "\n", "utf-8")
    (folder / "swofty.json").write_text(json.dumps(manifest(seed, launch, len(ops), steps, smoke), indent=2) + "\n",
                                        "utf-8")
    with (out / "assignment.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["driver", "team"] + FACTORS)
        for d in ROSTER:
            w.writerow([d, TEAM_OF[d]] + [assign[d][x] for x in FACTORS])
    with (out / "expected_ops.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["path", "field", "value"])
        w.writerows([o["select"], o["field"], o["value"]] for o in ops)
    (out / "levels.json").write_text(json.dumps(levels_record(seed, launch, steps, smoke, source), indent=1) + "\n",
                                     "utf-8")
    return ops


def read_assignment(path: Path) -> dict[str, dict[str, int]]:
    with path.open(encoding="utf-8", newline="") as fh:
        return {r["driver"]: {x: int(r[x]) for x in FACTORS} for r in csv.DictReader(fh)}


# --------------------------------------------------------------------------------------
# selftest
# --------------------------------------------------------------------------------------

def selftest() -> int:
    results, ok = [], True

    def chk(name: str, cond: bool, detail: str = "") -> None:
        nonlocal ok
        ok &= bool(cond)
        results.append(f"{'ok' if cond else 'FAIL'} {name}" + (f": {detail}" if detail else ""))

    # ---- the exact keys, values and curve strings (prereg section 1)
    want = {
        "YIELD": ("ai_driver_config.alongside.yield_overtake_rate", "1", "0.5", "2"),
        "EXIT_ERR": ("ai_driver_config.exit_fallibility.throttle_error_qualifying_race",
                     "@v2@minx:0,maxx:1,miny:-1,maxy:1,0:0.4,0:0,0.05:0.28,0.15:0.415,0.62:0.48,0.92:0.55,0.97:0.685,"
                     "1:1,1:0.77",
                     "@v2@minx:0,maxx:1,miny:-1,maxy:1,0:0,0:0,1:1,1:1",
                     "@v2@minx:0,maxx:1,miny:-1,maxy:1,0:0.48,0:0.48,1:0.48,1:0.48"),
        "OVERLAP": ("ai_driver_config.overtake.overlap_percentage",
                    "@v2@minx:0,maxx:1,miny:0,maxy:1,0:0.56667,0:0.56667,0.25:0.56,0.5:0.5,0.75:0.35,1:0.1,1:0.05",
                    "@v2@minx:0,maxx:1,miny:0,maxy:1,0:0.05,0:0.05,1:0.05,1:0.05",
                    "@v2@minx:0,maxx:1,miny:0,maxy:1,0:0.9,0:0.9,1:0.9,1:0.9"),
        "BLK_SPEED": ("ai_driver_config.blocking.blocking_speed_differential", "0.6", "0.15", "2.4"),
        "BLK_THREAT": ("ai_driver_config.blocking.blocking_threat_time_modifier", "0.175", "0.7", "0.04375"),
        "COMMIT": ("ai_driver_config.overtake.braking_zone_abort_overtake_time", "0.6667", "0.1", "1.0667"),
    }
    chk("the six factors, in the prereg's order", FACTORS == list(want), str(FACTORS))
    chk("each factor's key, stock, HIGH and LOW are the prereg's exact strings",
        all((LEVELS[f]["key"], LEVELS[f]["stock"], LEVELS[f]["HIGH"], LEVELS[f]["LOW"]) == want[f] for f in want),
        str([f for f in want if (LEVELS[f]["key"], LEVELS[f]["stock"], LEVELS[f]["HIGH"], LEVELS[f]["LOW"]) != want[f]]))
    aic = vm.stock_aic_keys()
    chk("every key is in docs/stock/ai_driver_config.csv with that stock value",
        all(aic.get(LEVELS[f]["key"]) == LEVELS[f]["stock"] for f in FACTORS))
    chk("HIGH, LOW and stock differ for every factor",
        all(len({LEVELS[f]["stock"], LEVELS[f]["HIGH"], LEVELS[f]["LOW"]}) == 3 for f in FACTORS))
    chk("OVERLAP's levels are v1_make.flat_curve's (V-1's ATTACK strings) and its stock is V-1's",
        LEVELS["OVERLAP"]["HIGH"] == vm.flat_curve(0.05) and LEVELS["OVERLAP"]["LOW"] == vm.flat_curve(0.9)
        and LEVELS["OVERLAP"]["stock"] == vm.OVERLAP_STOCK)
    curves_ok = True
    for f in ("EXIT_ERR", "OVERLAP"):
        hs, _ = parse_curve(LEVELS[f]["stock"])
        for s in SIDES:
            h, pts = parse_curve(LEVELS[f][s])
            curves_ok &= h == hs and vm.is_value(LEVELS[f][s]) and pts[0][0] == 0 and pts[-1][0] == 1 and len(pts) == 4
    _, diag = parse_curve(LEVELS["EXIT_ERR"]["HIGH"])
    chk("curves: on the stock axes, v1_make's point format (0:y,0:y,1:y,1:y), x spans 0..1; EXIT_ERR HIGH is the "
        "diagonal (0 at x 0, 1 at x 1, 0.5 at x 0.5)", curves_ok and curve_value(diag, 0) == 0
        and curve_value(diag, 1) == 1 and abs(curve_value(diag, 0.5) - 0.5) < 1e-12)
    chk("the scalar levels are numbers, the curves are @v2@ strings",
        all(vm.is_value(LEVELS[f][s]) for f in FACTORS for s in SIDES + ("stock",)))
    chk("one key per factor, six distinct keys (no bundles)", len({LEVELS[f]["key"] for f in FACTORS}) == 6)
    chk("no factor key matches FORBIDDEN", not any(FORBIDDEN.search(LEVELS[f]["key"]) for f in FACTORS))

    # ---- the draw
    seeds, launches = [1, 7, S1_SEED, SMOKE_SEED, 123456789], range(1, 21)
    draws = {(s, L): draw(s, L) for s in seeds for L in launches}
    chk("roster and teams are v1_make's (19 AI drivers, 9 two-AI teams, Alonso solo)",
        ROSTER is vm.ROSTER and TEAMS is vm.TEAMS and len(ROSTER) == 19 and SOLO == ["fernando_alonso"])
    chk("determinism (same seed + launch -> same draw)", all(draw(s, L) == draws[(s, L)] for s, L in draws))
    chk("draw covers 19 drivers x 6 factors with 0/1", all(set(a) == set(ROSTER) and all(
        set(a[d]) == set(FACTORS) and set(a[d].values()) <= {0, 1} for d in a) for a in draws.values()))
    counts = {k: {f: sum(a[d][f] for d in ROSTER) for f in FACTORS} for k, a in draws.items()}
    chk("balance: every factor has 9 or 10 cars HIGH", all(c in (9, 10) for v in counts.values() for c in v.values()))
    chk("teammates split for every two-AI team and factor", all(
        sum(a[d][f] for d in ds) == 1 for a in draws.values() for _, ds in TEAMS if len(ds) == 2 for f in FACTORS))
    chk("Alonso alternates HIGH / LOW by launch, per factor", all(
        draws[(s, L)]["fernando_alonso"][f] != draws[(s, L + 1)]["fernando_alonso"][f]
        for s in seeds for L in range(1, 20) for f in FACTORS))
    chk("a seeded phase per factor (Alonso's launch-1 level is not the same for all six factors, some seed)",
        any(len({draws[(s, 1)]["fernando_alonso"][f] for f in FACTORS}) == 2 for s in seeds))
    keys = [json.dumps(a, sort_keys=True) for a in draws.values()]
    chk("different launches and seeds give different draws", len(set(keys)) == len(keys), f"{len(keys)} draws")
    a1 = draws[(S1_SEED, 1)]
    chk("factors are drawn independently (they differ within a launch)",
        len({tuple(a1[d][f] for d in ROSTER) for f in FACTORS}) > 1)
    n = sum(draw(s, 1)["oscar_piastri"]["YIELD"] for s in range(2000))
    chk("coin flips are fair (Piastri YIELD HIGH in 2000 seeds)", 900 < n < 1100, str(n))
    chk("the seed string is S-1's own", SEED_FMT.format(seed=1, launch=2) == "verve-s1|1|2" and draw(1, 1) != vm_draw6(1, 1))

    # ---- ops
    all_ops = {k: build_ops(a) for k, a in draws.items()}
    chk(f"{N_OPS} ops per launch (6 keys x 19 AI drivers), every one HIGH or LOW",
        all(len(o) == N_OPS == 6 * 19 for o in all_ops.values()) and all(
            o["value"] in (LEVELS[f]["HIGH"], LEVELS[f]["LOW"]) for ops in all_ops.values() for o in ops
            for f in FACTORS if o["field"] == LEVELS[f]["key"]))
    chk("the ops carry the draw (1 -> HIGH, 0 -> LOW) for every driver and factor", all(
        next(o["value"] for o in all_ops[k] if o["select"] == vm.DRIVER_SELECT.format(d) and o["field"] ==
             LEVELS[f]["key"]) == LEVELS[f]["HIGH" if a[d][f] else "LOW"]
        for k, a in list(draws.items())[:10] for d in ROSTER for f in FACTORS))
    chk("every op passes op_problems", not [p for ops in all_ops.values() for o in ops for p in op_problems(o)])
    chk("FORBIDDEN (cede_position.*, yellow_flag_*, flying_lap_yield_*) never matches an op", not any(
        FORBIDDEN.search(o["select"] + " " + o["field"] + " " + o["value"]) for ops in all_ops.values() for o in ops))
    chk("no duplicate (select, field) in a launch",
        all(len({(o["select"], o["field"]) for o in ops}) == len(ops) for ops in all_ops.values()))
    s0 = vm.DRIVER_SELECT.format("max_verstappen")
    chk("the guard catches a forbidden key, the player, another key, an unregistered value and a stock value",
        all(op_problems(x) for x in [
            vm.op(s0, AIC + "cede_position.yellow_flag_ramp_up_time", "1"),
            vm.op(s0, AIC + "cede_position.flying_lap_yield_to_human_track_speed_diff", "1"),
            vm.op(vm.DRIVER_SELECT.format(vm.PLAYER), LEVELS["YIELD"]["key"], "0.5"),
            vm.op(s0, AIC + "blocking.max_blocking_distance", "45"),
            vm.op(s0, LEVELS["YIELD"]["key"], "0.3"),
            vm.op(s0, LEVELS["YIELD"]["key"], "1"),
            vm.op(s0, "driver_characteristics.aggression", "1.0")]))
    paths = all_paths()
    have = [ln.strip() for ln in PATHS_FILE.read_text(encoding="utf-8").splitlines()
            if ln.strip() and not ln.startswith("#")] if PATHS_FILE.exists() else []
    chk("114 paths (19 drivers x 6 keys), unique, no forbidden key; docs/stock/s1_paths.txt = all_paths()",
        len(paths) == 114 == len(set(paths)) and not any(FORBIDDEN.search(p) for p in paths) and have == paths,
        f"{len(have)} lines in the file")
    cached = set()
    if KEY_CACHE.exists():
        with KEY_CACHE.open(encoding="utf-8-sig", newline="") as fh:
            cached = {r["path"] for r in csv.DictReader(fh)}
    inc = [p for p in paths if p in cached]
    chk("the key cache already holds overlap_percentage and yield_overtake_rate for all 19 (>= 38 of 114)",
        all(p in cached for p in paths if p.endswith(("overlap_percentage", "yield_overtake_rate"))) and len(inc) >= 38,
        f"{len(inc)} cached, {len(paths) - len(inc)} to prefill")
    chk("every op path is in all_paths()", all(f"{o['select']}.{o['field']}" in set(paths)
                                               for ops in all_ops.values() for o in ops))

    # ---- the steps (prereg section 4's table)
    table = {("YIELD", "HIGH"): ("0.707", "0.841"), ("YIELD", "LOW"): ("1.41", "1.19"),
             ("BLK_SPEED", "HIGH"): ("0.3", "0.424"), ("BLK_SPEED", "LOW"): ("1.2", "0.849"),
             ("BLK_THREAT", "HIGH"): ("0.35", "0.247"), ("BLK_THREAT", "LOW"): ("0.0875", "0.124"),
             ("COMMIT", "HIGH"): ("0.258", "0.415"), ("COMMIT", "LOW"): ("0.843", "0.75")}
    got = {k: (level_value(*k, 1), level_value(*k, 2)) for k in table}
    chk("scalar steps 1 and 2 are the prereg's table (log space, 3 significant figures; 1.414 / 1.189 -> 1.41 / 1.19)",
        got == table, str({k: v for k, v in got.items() if v != table[k]}))
    chk("step 3 (stock) is the stock value, step 0 the extreme",
        all(level_value(f, s, 3) == LEVELS[f]["stock"] and level_value(f, s, 0) == LEVELS[f][s]
            for f in FACTORS for s in SIDES))
    curve_ok = []
    for f in ("EXIT_ERR", "OVERLAP"):
        _, ps = parse_curve(LEVELS[f]["stock"])
        for s in SIDES:
            _, pe = parse_curve(LEVELS[f][s])
            for k in (1, 2):
                h, pn = parse_curve(level_value(f, s, k))
                xs = sorted({x for x, _ in ps} | {x for x, _ in pe})
                fine = h == parse_curve(LEVELS[f]["stock"])[0] and sorted({x for x, _ in pn}) == xs
                for x in xs + [0.1, 0.33, 0.8]:
                    for j in (0, 1):
                        want_y = curve_value(ps, x, j) + 0.5 ** k * (curve_value(pe, x, j) - curve_value(ps, x, j))
                        fine &= abs(curve_value(pn, x, j) - want_y) < 2e-6
                curve_ok.append((f, s, k, fine))
    chk("curve steps: the union of the x points, y = stock + 0.5^k (y_ext - stock) at every point, the stock axes",
        all(x[3] for x in curve_ok), str([x[:3] for x in curve_ok if not x[3]]))
    ov1 = parse_curve(level_value("OVERLAP", "HIGH", 1))[1]
    ex2 = parse_curve(level_value("EXIT_ERR", "LOW", 2))[1]
    chk("worked examples: OVERLAP HIGH step 1 at x 0.5 = 0.5 + 0.5 x (0.05 - 0.5) = 0.275; EXIT_ERR LOW step 2 at x 0 "
        "= (0.4 + 0.25 x 0.08, 0 + 0.25 x 0.48) = (0.42, 0.12), at x 0.62 = 0.48",
        curve_value(ov1, 0.5) == 0.275 and [y for x, y in ex2 if x == 0] == [0.42, 0.12]
        and curve_value(ex2, 0.62) == 0.48, f"{level_value('EXIT_ERR', 'LOW', 2)}")
    chk("every step value passes is_value and differs from stock and from the extreme",
        all(vm.is_value(level_value(f, s, k)) and level_value(f, s, k) not in (LEVELS[f]["stock"], LEVELS[f][s])
            for f in FACTORS for s in SIDES for k in (1, 2)))

    # ---- --levels / --step overriding
    st = merge_steps(no_steps(), {"YIELD": {"HIGH": 1}, "BLK_SPEED": {"HIGH": 2, "LOW": "stock"},
                                  "COMMIT": {"HIGH": "stock", "LOW": 3}})
    st = merge_steps(st, parse_step_arg("OVERLAP:LOW:1"))
    a = draws[(S1_SEED, 1)]
    ops = build_ops(a, st)
    by = {(o["select"], o["field"]): o["value"] for o in ops}
    hi = [d for d in ROSTER if a[d]["YIELD"]]
    lo_bs = [d for d in ROSTER if not a[d]["BLK_SPEED"]]
    chk("--levels changes only the named levels: YIELD HIGH -> 0.707, YIELD LOW stays 2, OVERLAP LOW step 1",
        all(by[(vm.DRIVER_SELECT.format(d), LEVELS["YIELD"]["key"])] == ("0.707" if d in hi else "2") for d in ROSTER)
        and all(by[(vm.DRIVER_SELECT.format(d), LEVELS["OVERLAP"]["key"])] == (
            LEVELS["OVERLAP"]["HIGH"] if a[d]["OVERLAP"] else level_value("OVERLAP", "LOW", 1)) for d in ROSTER))
    chk("a level at stock gets no op (BLK_SPEED LOW), a factor with both at stock is dropped (COMMIT: no ops)",
        all((vm.DRIVER_SELECT.format(d), LEVELS["BLK_SPEED"]["key"]) not in by for d in lo_bs)
        and not any(o["field"] == LEVELS["COMMIT"]["key"] for o in ops) and dropped(st) == ["COMMIT"]
        and len(ops) == N_OPS - 19 - len(lo_bs), f"{len(ops)} ops")
    chk("every stepped op passes op_problems", not [p for o in ops for p in op_problems(o)])
    bad = 0
    for o in ({"NOPE": {"HIGH": 1}}, {"YIELD": {"MID": 1}}, {"YIELD": {"HIGH": 4}}, {"YIELD": {"HIGH": -1}},
              {"YIELD": {"HIGH": 1.5}}, {"YIELD": {"HIGH": True}}, {"YIELD": {}}, ["YIELD"]):
        try:
            merge_steps(no_steps(), o)
        except ValueError:
            bad += 1
    for s in ("YIELD:HIGH", "YIELD:HIGH:9", "yield:HIGH:1"):
        try:
            parse_step_arg(s)
        except ValueError:
            bad += 1
    chk("bad --levels / --step are refused (unknown factor or level, k outside 0-2/stock, bad syntax)", bad == 11)

    # ---- the files, smoke mode, the CLI
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp)
        w_ops = write_launch(5, 3, out / "a")
        man = json.loads((out / "a" / "verve.s1-L03" / "swofty.json").read_text(encoding="utf-8"))
        db = json.loads((out / "a" / "verve.s1-L03" / "db" / "s1.json").read_text(encoding="utf-8"))
        with (out / "a" / "expected_ops.csv").open(encoding="utf-8") as fh:
            exp = list(csv.DictReader(fh))
        lv = json.loads((out / "a" / "levels.json").read_text(encoding="utf-8"))
        chk("manifest id verve.s1-l03 / version / compat / requires / kind / saves / operations",
            man["id"] == "verve.s1-l03" == addon_id(3) and man["version"] == "0.0.1"
            and man["compat"] == {"game": "f1_25", "game_builds": [">=26566308"], "launcher": ">=1.9.34"}
            and man["requires"] == [{"id": "swofty.core", "version": ">=0.2.13"}] and man["kind"] == ["database"]
            and man["saves"] == {"affects": False} and man["operations"] == {"database": ["db/s1.json"]}
            and "114 ops" in man["description"] and "No stepped levels" in man["description"])
        chk("db/s1.json = expected_ops.csv, 114 ops", db == {"schema_version": 1, "ops": w_ops} and len(w_ops) == 114
            and [(e["path"], e["field"], e["value"]) for e in exp] == [(o["select"], o["field"], o["value"]) for o in w_ops])
        chk("assignment.csv = draw (1 = HIGH)", read_assignment(out / "a" / "assignment.csv") == draw(5, 3))
        chk("levels.json: no steps, nothing dropped, not the smoke", lv["stepped"] == {} and lv["dropped"] == []
            and lv["smoke"] is False and lv["factors"]["YIELD"]["HIGH"]["value"] == "0.5")
        write_launch(5, 3, out / "b", st, source="levels_next.json")
        lvb = json.loads((out / "b" / "levels.json").read_text(encoding="utf-8"))
        manb = json.loads((out / "b" / "verve.s1-L03" / "swofty.json").read_text(encoding="utf-8"))
        chk("stepping is recorded: levels.json (steps, values, dropped, source) and the manifest description",
            lvb["stepped"] == {"YIELD": {"HIGH": 1}, "OVERLAP": {"LOW": 1}, "BLK_SPEED": {"HIGH": 2, "LOW": 3},
                               "COMMIT": {"HIGH": 3, "LOW": 3}}
            and lvb["dropped"] == ["COMMIT"] and lvb["levels_source"] == "levels_next.json"
            and lvb["factors"]["YIELD"]["HIGH"]["value"] == "0.707" and lvb["factors"]["BLK_SPEED"]["LOW"]["at_stock"]
            and "YIELD HIGH step 1" in manb["description"] and "Dropped: COMMIT" in manb["description"])
        lj = out / "lv.json"
        lj.write_text(json.dumps({"YIELD": {"HIGH": 1}, "BLK_THREAT": {"HIGH": 1, "LOW": 1}}), encoding="utf-8")
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = main(["--seed", "5", "--launch", "4", "--out", str(out / "cli"), "--levels", str(lj),
                       "--step", "EXIT_ERR:HIGH:1"])
        lvc = json.loads((out / "cli" / "levels.json").read_text(encoding="utf-8"))
        chk("the CLI: --levels <json> and --step override, recorded, id printed",
            rc == 0 and lvc["stepped"] == {"YIELD": {"HIGH": 1}, "EXIT_ERR": {"HIGH": 1}, "BLK_THREAT": {"HIGH": 1, "LOW": 1}}
            and "verve.s1-l04" in buf.getvalue() and "stepped" in buf.getvalue())
        buf = io.StringIO()
        with redirect_stdout(buf):
            rcs = main(["--smoke", "--seed", str(SMOKE_SEED), "--launch", "1", "--out", str(out / "smoke")])
            rcx = main(["--smoke", "--seed", str(S1_SEED), "--launch", "1", "--out", str(out / "x1")])
            rcy = main(["--smoke", "--seed", str(SMOKE_SEED), "--launch", "2", "--out", str(out / "x2")])
        sa = read_assignment(out / "smoke" / "assignment.csv")
        sl = json.loads((out / "smoke" / "levels.json").read_text(encoding="utf-8"))
        sm = json.loads((out / "smoke" / "verve.s1-L01" / "swofty.json").read_text(encoding="utf-8"))
        with (out / "smoke" / "expected_ops.csv").open(encoding="utf-8") as fh:
            sops = list(csv.DictReader(fh))
        chk("smoke mode: the HIGH half is draw(2026111707, 1), the rest LOW; 9 or 10 HIGH per factor; every car at an "
            "extreme of every factor (114 ops); marked as the smoke",
            rcs == 0 and sa == draw(SMOKE_SEED, 1) and all(sum(sa[d][f] for d in ROSTER) in (9, 10) for f in FACTORS)
            and len(sops) == 114 and all(e["value"] == LEVELS[f]["HIGH" if sa[e["path"].split("=")[1].rstrip("]")][f]
                                                                  else "LOW"]
                                         for e in sops for f in FACTORS if e["field"] == LEVELS[f]["key"])
            and sl["smoke"] is True and sl["seed"] == SMOKE_SEED and "extremes" in sm["name"])
        chk("smoke mode refuses another seed or launch", rcx == 3 and rcy == 3 and not (out / "x1").exists()
            and not (out / "x2").exists())
        text = "".join(p.read_text(encoding="utf-8") for p in out.rglob("*") if p.is_file())
        chk("FORBIDDEN never matches anything written", not FORBIDDEN.search(text))
        buf = io.StringIO()
        with redirect_stdout(buf):
            rcp = main(["--paths"])
        chk("--paths prints the header and the 114 paths (the file's content)",
            rcp == 0 and buf.getvalue().splitlines() == PATHS_HEADER + paths
            and (not PATHS_FILE.exists() or PATHS_FILE.read_text(encoding="utf-8") == buf.getvalue()))
    print("\n".join(results))
    print("selftest", "ok" if ok else "FAILED")
    return 0 if ok else 1


def vm_draw6(seed: int, launch: int) -> dict:
    """What V-1's seed string would draw for the six factors (the selftest checks S-1's differs)."""
    rng = random.Random(f"verve-v1|{seed}|{launch}")
    out = {d: {} for d in ROSTER}
    for f in FACTORS:
        for _, ds in TEAMS:
            if len(ds) == 2:
                hi = rng.randrange(2)
                out[ds[hi]][f], out[ds[1 - hi]][f] = 1, 0
            else:
                out[ds[0]][f] = launch % 2
    return out


# --------------------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------------------

def main(argv: list[str]) -> int:
    args = list(argv)
    if "--selftest" in args:
        return selftest()
    if "--paths" in args:
        print("\n".join(PATHS_HEADER + all_paths()))
        return 0
    smoke = "--smoke" in args
    args = [a for a in args if a != "--smoke"]
    step_args = []
    while "--step" in args:
        i = args.index("--step")
        if i + 1 >= len(args):
            print(__doc__)
            return 3
        step_args.append(args[i + 1])
        del args[i:i + 2]
    opts = {"--seed": None, "--launch": None, "--out": None, "--levels": None}
    for k in list(opts):
        if k in args:
            i = args.index(k)
            if i + 1 >= len(args):
                print(__doc__)
                return 3
            opts[k] = args[i + 1]
            del args[i:i + 2]
    if smoke:
        opts["--seed"] = opts["--seed"] or str(SMOKE_SEED)
        opts["--launch"] = opts["--launch"] or str(SMOKE_LAUNCH)
    if args or None in (opts["--seed"], opts["--launch"], opts["--out"]):
        print(__doc__)
        return 3
    seed, launch, out = int(opts["--seed"]), int(opts["--launch"]), Path(opts["--out"])
    if launch < 1:
        print("--launch must be >= 1")
        return 3
    if smoke and (seed, launch) != (SMOKE_SEED, SMOKE_LAUNCH):
        print(f"--smoke is draw({SMOKE_SEED}, {SMOKE_LAUNCH}) only (prereg section 4), not seed {seed} launch {launch}")
        return 3
    steps = no_steps()
    try:
        if opts["--levels"]:
            steps = merge_steps(steps, json.loads(Path(opts["--levels"]).read_text(encoding="utf-8-sig")))
        for s in step_args:
            steps = merge_steps(steps, parse_step_arg(s))
    except (ValueError, OSError) as e:
        print(f"refusing the levels: {e}")
        return 3
    ops = write_launch(seed, launch, out, steps, smoke, opts["--levels"])
    assign = draw(seed, launch)
    rec = levels_record(seed, launch, steps, smoke, opts["--levels"])
    print(f"S-1 {'extremes smoke, ' if smoke else ''}seed {seed} launch {launch} -> {out / folder_name(launch)} "
          f"(id {addon_id(launch)})")
    print(f"  {'driver':<24}{'team':<12}" + "".join(f"{f:>11}" for f in FACTORS))
    for d in ROSTER:
        print(f"  {d:<24}{TEAM_OF[d]:<12}" + "".join(f"{'HIGH' if assign[d][f] else 'LOW':>11}" for f in FACTORS))
    print(f"  {'HIGH':<36}" + "".join(f"{sum(assign[d][f] for d in ROSTER):>11}" for f in FACTORS))
    print()
    for f in FACTORS:
        lv = rec["factors"][f]
        short = [("stock" if lv[s]["at_stock"] else (lv[s]["value"] if LEVELS[f]["kind"] == "scalar" else
                  f"curve step {lv[s]['steps']}" if lv[s]["steps"] else ("diagonal" if f == "EXIT_ERR" and s == "HIGH"
                                                                         else "flat " + lv[s]["value"].split(":")[-1])))
                 for s in SIDES]
        print(f"  {f:<11}{LEVELS[f]['key'][len(AIC):]:<50}HIGH {short[0]:<14}LOW {short[1]:<14}"
              + ("DROPPED" if f in rec["dropped"] else ""))
    print(f"  stepped: {rec['stepped'] or 'none'}; dropped: {rec['dropped'] or 'none'}")
    print(f"expected ops: {len(ops)} (6 keys x 19 AI drivers = {N_OPS}, less any level at stock)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
