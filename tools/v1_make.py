"""V-1 factorial screen: the seeded balanced assignment and the per-launch test add-on (docs/verve_v1_prereg.md, v3).

Usage:
    python -I tools/v1_make.py --seed <int> --launch <L> --out <dir> [--amp 3]
    python -I tools/v1_make.py --selftest

Writes <out>/verve.v1-L<LL>/{swofty.json, db/v1.json}, plus <out>/assignment.csv (driver, team, 8 factors) and
<out>/expected_ops.csv (path, field, value). Use one --out folder per launch: the two CSVs keep fixed names.

Roster: the 19 AI drivers of the F1 2025 grid (docs/stock/entrant_list_f1_2025.txt), without lance_stroll (the
player car). Alonso is the only AI driver without an AI teammate.

Eight factors, each 0/1 per driver per launch:
- the six row traits: entrants.drivers.driver[_metadata_=<label>].driver_characteristics.<trait> = 0.0 or 1.0
- DEFEND and ATTACK: bundles of per-driver ai_driver_config keys (PROPOSAL below; the supervisor approves before race 1)

Balance per factor per launch: in each of the 9 two-AI teams one coin flip picks the teammate at 1 (teammates always
split); Alonso alternates 1/0 by launch (seeded phase per factor), so each factor has 9 or 10 drivers at 1, alternating
by launch. Factors are drawn independently. draw(seed, launch) is pure: v1_check.py's permutation test calls it with
other seeds.

Every launch also writes the same amplified parameter maps (one package, not per driver): for each LIVE map,
high_difficulty_low_characteristic_mapping = hh + amp x (hl - hh), never past low_difficulty_low_characteristic_mapping.

Hard rule: no op ever touches cede_position.*, yellow_flag_* or flying_lap_yield_* (the selftest asserts it).
"""
from __future__ import annotations

import csv
import json
import random
import re
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
STOCK = REPO / "docs" / "stock"
MAPS_FILE = STOCK / "driver_parameter_maps_f1_2025.txt"

# ======================================================================================================================
# PROPOSAL (for the supervisor's approval before race 1). DEFEND / ATTACK bundles: keys with a proven tick-time
# reader only (Swofty's AI guide, docs/community/swofty_19_ai_learnings.md §1), and only where a source gives the
# direction. Values are strings, written as-is. "1" = defends / attacks harder.
# ======================================================================================================================
AIC = "ai_driver_config."


def flat_curve(y: float) -> str:
    """A flat @v2 curve on overlap_percentage's own axes (0-1 x 0-1), point format as the stock curve and verve.b0001."""
    return f"@v2@minx:0,maxx:1,miny:0,maxy:1,0:{y},0:{y},1:{y},1:{y}"


OVERLAP_STOCK = "@v2@minx:0,maxx:1,miny:0,maxy:1,0:0.56667,0:0.56667,0.25:0.56,0.5:0.5,0.75:0.35,1:0.1,1:0.05"

PROPOSAL = {
    "DEFEND": [
        {"key": AIC + "blocking.max_blocking_distance", "stock": "18", "level0": "5", "level1": "45",
         "cite": "B-0015 (#100) arms 45 vs 5, harness/addons/verve.b0015a/b; tick-read (swofty_19_ai_learnings.md §1); "
                 "45 = swofty.lap1-ai R:41. F-44: alone, INCONCLUSIVE / practical null on 25251167"},
        {"key": AIC + "blocking.max_blocking_distance_at_race_start", "stock": "18", "level0": "5", "level1": "45",
         "cite": "read until the race-start state machine ends, then the plain key takes over (swofty_19 §1); "
                 "45 = swofty.lap1-ai R:42; never written by us (verve_drivers_plan 4.2)"},
        {"key": AIC + "blocking.fraction_of_follow_speed", "stock": "0.975", "level0": "1.0", "level1": "0.7",
         "cite": "tick-read (swofty_19 §1); 0.7 = swofty.lap1-ai R:43, its 'treats slower-closing cars as threats' "
                 "(docs/community/swofty.lap1-ai.md); 1.0 = only cars at full follow speed count (sign from lap1-ai)"},
        {"key": AIC + "blocking.fraction_of_follow_speed_at_race_start", "stock": "0.875", "level0": "1.0",
         "level1": "0.6",
         "cite": "tick-read until the race-start state machine ends (swofty_19 §1); 0.6 = swofty.lap1-ai R:44"},
    ],
    "ATTACK": [
        {"key": AIC + "overtake.overlap_percentage", "stock": OVERLAP_STOCK,
         "level0": flat_curve(0.9), "level1": flat_curve(0.05),
         "cite": "B-0017 draft (#121): flat 0.05 ('commits early') vs flat 0.9 ('needs to be nearly alongside'); "
                 "decoded consumer 0x140650150 (F-07); tick-read (swofty_19 §1); 0.05 = swofty.lap1-ai R:56"},
        {"key": AIC + "alongside.yield_overtake_rate", "stock": "1", "level0": "2", "level1": "0.5",
         "cite": "tick-read (swofty_19 §1); 0.5 = swofty.lap1-ai R:68 ('yields half as much when alongside'); "
                 "catalogue B, aggression up -> value down (docs/ai_driver_config_keys.md); 2 = the mirror ratio"},
    ],
}
# Left out on purpose (the supervisor can add them):
# - blocking.blocking_speed_differential, blocking.blocking_threat_time_modifier: tick-read, but the sign is the
#   catalogue's name-only hypothesis (rating B, "trace sign"); the B-0015 v2 ruling: keys with uncertain signs can
#   cancel each other out.
# - alongside.speed_difference_for_limited_zone_yielding: tick-read, but acts only in limited-overtake zones (track
#   markup) and the sign is unclear.
# - every other overtake.* / space_seeking.* key: no proven reader (a null would be "unproven reader").
# - start_blocking_intersection_time, merge_back_to_racing_line, oppertunist_overtake_track_speed_difference,
#   divebomb_defense.*, alongside.min_presence_within_buffer: Swofty says "off" (no AI-vs-AI reader).
# - cede_position.* (incl. flying_lap_yield_*, yellow_flag_*): never (HARD RULE).
# ======================================================================================================================

TRAITS = ["reaction_speed", "mistakes", "aggression", "control", "speed_in", "speed_out"]
BUNDLES = ["DEFEND", "ATTACK"]
FACTORS = TRAITS + BUNDLES

PLAYER = "lance_stroll"
# entrant_list_f1_2025 order (docs/stock/entrant_list_f1_2025.txt); team -> AI drivers. Checked by the selftest.
TEAMS = [
    ("mclaren", ("oscar_piastri", "lando_norris")),
    ("ferrari", ("charles_leclerc", "lewis_hamilton")),
    ("redbull", ("max_verstappen", "yuki_tsunoda")),
    ("mercedes", ("george_russell", "andrea-kimi_antonelli")),
    ("forceindia", ("fernando_alonso",)),           # Aston Martin; the other car is the player (lance_stroll)
    ("renault", ("pierre_gasly", "franco_colapinto")),
    ("haas", ("esteban_ocon", "oliver_bearman")),
    ("tororosso", ("liam_lawson", "isack_hadjar")),
    ("williams", ("alex_albon", "carlos_sainz-jr")),
    ("sauber", ("nico_hulkenberg", "gabriel_bortoleto")),
]
ROSTER = [d for _, ds in TEAMS for d in ds]
TEAM_OF = {d: t for t, ds in TEAMS for d in ds}
SOLO = [ds[0] for _, ds in TEAMS if len(ds) == 1]        # ["fernando_alonso"]

DRIVER_SELECT = "entrants.drivers.driver[_metadata_={}]"
# The package row as the task and docs/stock name it. Not yet used as an op select by any batch (drivers and stats
# use [_metadata_=...]): check the readback before race 1.
PACKAGE_SELECT = "entrants.vehicles.vehicle_packages.vehicle_package_10"
MAP_FIELD = "ai_vehicle_package_config.driver_parameter_maps.{}.high_difficulty_low_characteristic_mapping"
DEAD_MAPS = {"alongside_awareness", "brake_off_time", "slide_confidence", "wet_weather_ability"}
CORNERS = ("high_difficulty_high_characteristic_mapping", "high_difficulty_low_characteristic_mapping",
           "low_difficulty_high_characteristic_mapping", "low_difficulty_low_characteristic_mapping")

FORBIDDEN = re.compile(r"cede_position\.|yellow_flag_|flying_lap_yield_")
LABEL_RE = r"[a-z0-9_\-]+"


# --------------------------------------------------------------------------------------
# the draw (pure)
# --------------------------------------------------------------------------------------

def draw(seed: int, launch: int) -> dict[str, dict[str, int]]:
    """{driver: {factor: 0/1}} for one launch. Pure and deterministic in (seed, launch); str seeds are stable across
    runs and machines (random.seed version 2 hashes them with sha512, not hash())."""
    rng = random.Random(f"verve-v1|{seed}|{launch}")
    phase_rng = random.Random(f"verve-v1-solo-phase|{seed}")      # per seed only, so the solo driver alternates
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
# amplified parameter maps
# --------------------------------------------------------------------------------------

def fmt(x: float) -> str:
    s = f"{round(x, 6):.6f}".rstrip("0").rstrip(".")
    return "0" if s in ("-0", "") else s


# Supervisor's ruling on #148: ONE exception to the cap. "Rare vs frequent mistakes" is a headline trait for Tyler, and
# the cap makes throttle_exit_fallibility a no-op (hh 0.75, hl = ll = 1), so its hl corner goes to hh + amp x (hl - hh)
# UNCAPPED (1.5 at amp 3), past ll. The per-car exit_fallibility caps still bound the error. If the validity stop (F)
# trips, the first step down is this map back to 1.0 (--no-uncapped), then amp 2 overall.
UNCAPPED_MAPS = {"throttle_exit_fallibility"}


def amplify(hh: float, hl: float, ll: float, amp: float) -> float:
    """hh + amp x (hl - hh), capped at ll in the direction of the low-difficulty value (never past it)."""
    v = hh + amp * (hl - hh)
    if hl >= hh:
        return min(v, ll) if ll >= hh else v
    return max(v, ll) if ll <= hh else v


def read_maps(path: Path = MAPS_FILE) -> dict[str, dict[str, str]]:
    maps, cur = {}, None
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        if not line.startswith(" "):
            cur = maps.setdefault(line.strip(), {})
        else:
            k, v = line.split(None, 1)
            cur[k] = v.strip()
    return maps


def map_plan(amp: float, maps: dict | None = None, uncapped: bool = True) -> list[dict]:
    """One row per map: stock corners, status, amplified hl (None when untouched)."""
    rows = []
    for name, m in sorted((maps or read_maps()).items()):
        hh, hl, lh, ll = (float(m[c]) for c in CORNERS)
        row = {"map": name, "characteristic": m["characteristic"], "hh": hh, "hl": hl, "ll": ll, "new": None}
        if name in DEAD_MAPS:
            row["status"] = "dead (untouched)"
        elif hh == hl == lh == ll:
            row["status"] = "flat (untouched)"
        elif uncapped and name in UNCAPPED_MAPS:
            row["status"], row["new"] = "amplified, uncapped (ruling on #148)", float(fmt(hh + amp * (hl - hh)))
        else:
            new = float(fmt(amplify(hh, hl, ll, amp)))
            if new == hl:
                row["status"] = "capped at stock (no op)"
            else:
                row["status"], row["new"] = ("capped at ll" if new == ll else "amplified"), new
        rows.append(row)
    return rows


def print_maps(rows: list[dict], amp: float) -> None:
    print(f"amplified parameter maps (amp {fmt(amp)}; {PACKAGE_SELECT}):")
    print(f"  {'map':<28}{'characteristic':<16}{'hh':>8}{'hl':>8}{'ll':>9}{'new hl':>9}  status")
    for r in rows:
        new = fmt(r["new"]) if r["new"] is not None else "-"
        print(f"  {r['map']:<28}{r['characteristic']:<16}{fmt(r['hh']):>8}{fmt(r['hl']):>8}{fmt(r['ll']):>9}"
              f"{new:>9}  {r['status']}")


# --------------------------------------------------------------------------------------
# ops and the add-on
# --------------------------------------------------------------------------------------

def op(select: str, field: str, value: str) -> dict:
    return {"op": "set", "select": select, "field": field, "value": value}


def build_ops(assign: dict[str, dict[str, int]], amp: float, maps: dict | None = None, uncapped: bool = True) -> list[dict]:
    ops = []
    for d in ROSTER:
        sel = DRIVER_SELECT.format(d)
        for t in TRAITS:
            ops.append(op(sel, f"driver_characteristics.{t}", "1.0" if assign[d][t] else "0.0"))
        for b in BUNDLES:
            for k in PROPOSAL[b]:
                ops.append(op(sel, k["key"], k["level1"] if assign[d][b] else k["level0"]))
    for r in map_plan(amp, maps, uncapped):
        if r["new"] is not None:
            ops.append(op(PACKAGE_SELECT, MAP_FIELD.format(r["map"]), fmt(r["new"])))
    return ops


def addon_id(launch: int) -> str:
    return f"verve.v1-l{launch:02d}"


def manifest(seed: int, launch: int, n_ops: int, amp: float) -> dict:
    return {
        "schema_version": 1, "id": addon_id(launch), "name": f"Verve test V-1 launch {launch:02d} (factorial screen)",
        "version": "0.0.1", "author": "TC Verve",
        "description": f"Test-only addon for V-1 (docs/verve_v1_prereg.md), seed {seed}, launch {launch}: six row "
                       f"traits and the DEFEND/ATTACK ai_driver_config bundles at 0/1 per driver (assignment.csv), "
                       f"plus the parameter maps amplified {fmt(amp)}x. {n_ops} ops. Not for play.",
        "license": "MIT", "category": "ai", "kind": ["database"],
        # absolute values; 26566308 = F1 25 1.0.145 (docs/harness.md)
        "compat": {"game": "f1_25", "game_builds": [">=26566308"], "launcher": ">=1.9.34"},
        "requires": [{"id": "swofty.core", "version": ">=0.2.13"}], "saves": {"affects": False},
        "operations": {"database": ["db/v1.json"]},
    }


def stock_traits() -> dict[str, dict[str, float]]:
    with (STOCK / "driver_characteristics_grid.csv").open(encoding="utf-8") as f:
        rows = [ln for ln in f if not ln.startswith("#")]
    return {r["label"]: {t: float(r[t]) for t in TRAITS} for r in csv.DictReader(rows)}


def write_launch(seed: int, launch: int, out: Path, amp: float, uncapped: bool = True) -> list[dict]:
    assign = draw(seed, launch)
    ops = build_ops(assign, amp, uncapped=uncapped)
    check_ops(ops)
    folder = out / f"verve.v1-L{launch:02d}"
    (folder / "db").mkdir(parents=True, exist_ok=True)
    (folder / "db" / "v1.json").write_text(json.dumps({"schema_version": 1, "ops": ops}, indent=2) + "\n", "utf-8")
    (folder / "swofty.json").write_text(json.dumps(manifest(seed, launch, len(ops), amp), indent=2) + "\n", "utf-8")
    with (out / "assignment.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["driver", "team"] + FACTORS)
        for d in ROSTER:
            w.writerow([d, TEAM_OF[d]] + [assign[d][x] for x in FACTORS])
    with (out / "expected_ops.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["path", "field", "value"])
        w.writerows([o["select"], o["field"], o["value"]] for o in ops)
    return ops


# --------------------------------------------------------------------------------------
# checks
# --------------------------------------------------------------------------------------

def stock_aic_keys() -> dict[str, str]:
    with (STOCK / "ai_driver_config.csv").open(encoding="utf-8") as f:
        return {r["key"]: r["default_driver"] for r in csv.DictReader(f)}


def is_value(v: str) -> bool:
    if v.startswith("@v2@"):
        return re.fullmatch(r"@v2@minx:[-\d.]+,maxx:[-\d.]+,miny:[-\d.]+,maxy:[-\d.]+(,[-\d.]+:[-\d.]+){2,}", v) is not None
    try:
        float(v)
        return True
    except ValueError:
        return False


def op_problems(o: dict, live_maps: set[str] | None = None, aic: set[str] | None = None) -> list[str]:
    """Why an op is malformed or forbidden (empty = fine)."""
    p = []
    if set(o) != {"op", "select", "field", "value"} or o.get("op") != "set":
        return [f"bad op shape: {o}"]
    sel, field, val = o["select"], o["field"], o["value"]
    if FORBIDDEN.search(sel) or FORBIDDEN.search(field):
        p.append(f"FORBIDDEN key: {sel} {field}")
    m = re.fullmatch(r"entrants\.drivers\.driver\[_metadata_=(" + LABEL_RE + r")\]", sel)
    if m:
        if m[1] not in ROSTER:
            p.append(f"driver not on the AI roster: {m[1]}")
        t = re.fullmatch(r"driver_characteristics\.(\w+)", field)
        if t:
            if t[1] not in TRAITS or val not in ("0.0", "1.0"):
                p.append(f"bad trait op: {field}={val}")
        elif field.startswith(AIC):
            if aic is not None and field not in aic:
                p.append(f"unknown ai_driver_config key: {field}")
        else:
            p.append(f"unexpected driver field: {field}")
    elif sel == PACKAGE_SELECT:
        mm = re.fullmatch(MAP_FIELD.replace(".", r"\.").replace("{}", r"(\w+)"), field)
        if not mm or mm[1] in DEAD_MAPS or (live_maps is not None and mm[1] not in live_maps):
            p.append(f"bad map field: {field}")
    else:
        p.append(f"unexpected select: {sel}")
    if not is_value(val):
        p.append(f"bad value: {val!r}")
    return p


def check_ops(ops: list[dict]) -> None:
    probs = [x for o in ops for x in op_problems(o)]
    if probs:
        sys.exit("refusing to write: " + "; ".join(probs[:5]))


def selftest() -> int:
    results, ok = [], True

    def chk(name: str, cond: bool, detail: str = "") -> None:
        nonlocal ok
        ok &= bool(cond)
        results.append(f"{'ok' if cond else 'FAIL'} {name}" + (f": {detail}" if detail else ""))

    # roster against the repo files
    ent = (STOCK / "entrant_list_f1_2025.txt").read_text(encoding="utf-8")
    pairs = re.findall(r"entrant_reference\s+(\S+)\s*\n(?:.*\n)*?\s+team\s+(\S+)", ent)
    from_file = {}
    for d, t in pairs:
        from_file.setdefault(t, []).append(d)
    want = {t: list(ds) for t, ds in TEAMS}
    want["forceindia"] = ["lance_stroll", "fernando_alonso"]
    chk("roster = entrant_list_f1_2025 minus the player", from_file == want and len(pairs) == 20,
        f"{len(pairs)} entrants")
    grid = stock_traits()
    with (REPO / "data" / "crosswalk_f1.csv").open(encoding="utf-8") as f:
        cw = {r["f1_25_label"] for r in csv.DictReader(f) if "2025" in r["grid"].split("|")}
    chk("19 AI drivers, all in driver_characteristics_grid.csv and crosswalk 2025, no player",
        len(ROSTER) == 19 == len(set(ROSTER)) and set(ROSTER) <= set(grid) and set(ROSTER) | {PLAYER} <= cw
        and PLAYER not in ROSTER and SOLO == ["fernando_alonso"])

    # the draw
    seeds, launches = [1, 7, 20261116, 123456789], range(1, 21)
    chk("determinism (same seed + launch -> same draw)", all(draw(s, L) == draw(s, L) for s in seeds for L in launches))
    chk("draw covers 19 drivers x 8 factors with 0/1",
        all(set(a) == set(ROSTER) and all(set(a[d]) == set(FACTORS) and set(a[d].values()) <= {0, 1} for d in a)
            for a in (draw(s, L) for s in seeds for L in launches)))
    counts = {(s, L): {f: sum(draw(s, L)[d][f] for d in ROSTER) for f in FACTORS} for s in seeds for L in launches}
    chk("balance: every factor 9 or 10 ones of 19", all(c in (9, 10) for v in counts.values() for c in v.values()))
    chk("the count alternates 9/10 by launch, per factor",
        all(counts[(s, L)][f] != counts[(s, L + 1)][f] for s in seeds for L in range(1, 20) for f in FACTORS))
    chk("teammates split for every two-AI team and factor",
        all(sum(draw(s, L)[d][f] for d in ds) == 1 for s in seeds for L in launches for _, ds in TEAMS if len(ds) == 2
            for f in FACTORS))
    keys = [json.dumps(draw(s, L), sort_keys=True) for s in seeds for L in launches]
    chk("different launches (and seeds) give different draws", len(set(keys)) == len(keys), f"{len(keys)} draws")
    a = draw(1, 1)
    tf = [[a[d][f] for d in ROSTER] for f in FACTORS]
    chk("factors differ from each other within a launch", len({tuple(x) for x in tf}) > 1)
    # each teammate gets 1 about half the time over many seeds (no fixed side)
    n = sum(draw(s, 1)["oscar_piastri"]["aggression"] for s in range(2000))
    chk("coin flips are fair (Piastri aggression=1 in 2000 seeds)", 900 < n < 1100, str(n))

    # map math
    for name, (hh, hl, ll), want_v in [("follow_speed_factor", (1, 1.05, 1.4), 1.15),
                                       ("braking_distance_factor", (1, 1.15, 2.74), 1.45),
                                       ("corner_curvature_factor", (1, 0.92, 0.5888), 0.76)]:
        got = float(fmt(amplify(hh, hl, ll, 3)))
        chk(f"amplify {name} hh {hh} hl {hl} ll {ll} -> {want_v}", got == want_v, fmt(got))
    chk("cap upward: hh 1 hl 1.15 ll 1.3 -> 1.3", float(fmt(amplify(1, 1.15, 1.3, 3))) == 1.3)
    chk("cap downward: hh 1 hl 0.8 ll 0.5 -> 0.5", float(fmt(amplify(1, 0.8, 0.5, 3))) == 0.5)
    chk("cap at stock: throttle_exit_fallibility hh 0.75 hl 1 ll 1 -> 1",
        float(fmt(amplify(0.75, 1, 1, 3))) == 1.0)
    chk("amp 2: braking hh 1 hl 1.15 ll 2.74 -> 1.3", float(fmt(amplify(1, 1.15, 2.74, 2))) == 1.3)
    rows = {r["map"]: r for r in map_plan(3)}
    chk("dead and flat maps untouched", all(rows[m]["new"] is None for m in DEAD_MAPS) and
        all(r["new"] is None for r in rows.values() if r["hh"] == r["hl"] == r["ll"]))
    chk("stock maps: 7 written, throttle_exit_fallibility uncapped to 1.5 (ruling on #148)",
        sorted(m for m, r in rows.items() if r["new"] is not None) ==
        ["alongside_space_factor", "braking_distance_factor", "corner_curvature_factor", "follow_speed_factor",
         "throttle_confidence", "throttle_exit_fallibility", "throttle_on_time"]
        and rows["throttle_exit_fallibility"]["new"] == 1.5)
    chk("no amplified value past ll, except the named uncapped map", all(
        r["new"] is None or r["map"] in UNCAPPED_MAPS or (min(r["hh"], r["ll"]) <= r["new"] <= max(r["hh"], r["ll"]))
        for r in rows.values()))
    rows_nu = {r["map"]: r for r in map_plan(3, uncapped=False)}
    chk("the fallback (--no-uncapped) puts throttle_exit_fallibility back at stock (no op)",
        rows_nu["throttle_exit_fallibility"]["new"] is None)

    # the proposal against the stock dump
    aic = stock_aic_keys()
    chk("PROPOSAL keys exist with the stock values in docs/stock/ai_driver_config.csv",
        all(k["key"] in aic and aic[k["key"]] == k["stock"] for b in BUNDLES for k in PROPOSAL[b]))
    chk("PROPOSAL levels differ from stock and from each other",
        all(len({k["stock"], k["level0"], k["level1"]}) == 3 for b in BUNDLES for k in PROPOSAL[b]))
    chk("PROPOSAL: no forbidden key", not any(FORBIDDEN.search(k["key"]) for b in BUNDLES for k in PROPOSAL[b]))

    # ops
    live = {m for m, r in rows.items() if r["new"] is not None}
    all_ops = [build_ops(draw(s, L), 3) for s in seeds for L in (1, 2, 3)]
    n_aic = sum(len(PROPOSAL[b]) for b in BUNDLES)
    n_exp = len(ROSTER) * (len(TRAITS) + n_aic) + len(live)
    chk(f"op count = 19 x (6 + {n_aic}) + {len(live)} = {n_exp}", all(len(o) == n_exp for o in all_ops))
    probs = [p for ops in all_ops for o in ops for p in op_problems(o, live, set(aic))]
    chk("every op path well-formed", not probs, "; ".join(probs[:3]))
    chk("no forbidden key (cede_position.*, yellow_flag_*, flying_lap_yield_*) in any op",
        not any(FORBIDDEN.search(o["select"] + " " + o["field"]) for ops in all_ops for o in ops))
    chk("no duplicate (select, field) in a launch",
        all(len({(o["select"], o["field"]) for o in ops}) == len(ops) for ops in all_ops))
    chk("forbidden-key guard catches a planted op", bool(op_problems(op(DRIVER_SELECT.format("max_verstappen"),
        AIC + "cede_position.yellow_flag_ramp_up_time", "1"))) and bool(op_problems(op(DRIVER_SELECT.format(
            "max_verstappen"), AIC + "cede_position.flying_lap_yield_to_human_track_speed_diff", "1"))))
    chk("guard catches the player car and a dead map",
        bool(op_problems(op(DRIVER_SELECT.format(PLAYER), "driver_characteristics.aggression", "1.0")))
        and bool(op_problems(op(PACKAGE_SELECT, MAP_FIELD.format("wet_weather_ability"), "0.5"), live)))
    ops = all_ops[0]
    a = draw(seeds[0], 1)
    chk("ops carry the draw (traits and bundles)", all(
        next(o["value"] for o in ops if o["select"] == DRIVER_SELECT.format(d) and o["field"] == k["key"])
        == (k["level1"] if a[d][b] else k["level0"]) for d in ROSTER for b in BUNDLES for k in PROPOSAL[b]) and all(
        next(o["value"] for o in ops if o["select"] == DRIVER_SELECT.format(d) and o["field"] ==
             f"driver_characteristics.{t}") == ("1.0" if a[d][t] else "0.0") for d in ROSTER for t in TRAITS))

    # a full write into a temp folder
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp)
        w_ops = write_launch(5, 3, out, 3)
        man = json.loads((out / "verve.v1-L03" / "swofty.json").read_text(encoding="utf-8"))
        db = json.loads((out / "verve.v1-L03" / "db" / "v1.json").read_text(encoding="utf-8"))
        with (out / "expected_ops.csv").open(encoding="utf-8") as f:
            exp = list(csv.DictReader(f))
        with (out / "assignment.csv").open(encoding="utf-8") as f:
            asg = list(csv.DictReader(f))
        chk("manifest id/version/compat/requires/kind/saves", man["id"] == "verve.v1-l03" and man["version"] == "0.0.1"
            and man["compat"] == {"game": "f1_25", "game_builds": [">=26566308"], "launcher": ">=1.9.34"}
            and man["requires"] == [{"id": "swofty.core", "version": ">=0.2.13"}] and man["kind"] == ["database"]
            and man["saves"] == {"affects": False} and man["operations"] == {"database": ["db/v1.json"]})
        chk("db/v1.json = expected_ops.csv", db == {"schema_version": 1, "ops": w_ops} and
            [(e["path"], e["field"], e["value"]) for e in exp] == [(o["select"], o["field"], o["value"]) for o in w_ops])
        chk("assignment.csv = draw", [r["driver"] for r in asg] == ROSTER and all(
            int(r[f]) == draw(5, 3)[r["driver"]][f] and r["team"] == TEAM_OF[r["driver"]] for r in asg for f in FACTORS))
    print("\n".join(results))
    print("selftest", "ok" if ok else "FAILED")
    return 0 if ok else 1


# --------------------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------------------

def print_proposal() -> None:
    print("DEFEND / ATTACK bundles (PROPOSAL, awaiting the supervisor):")
    for b in BUNDLES:
        for k in PROPOSAL[b]:
            stock = "stock curve" if k["stock"].startswith("@v2@") else k["stock"]
            lv = [x.split(",")[-1].split(":")[-1] + " flat" if x.startswith("@v2@") else x for x in (k["level0"], k["level1"])]
            print(f"  {b:<7}{k['key'][len(AIC):]:<50} stock {stock:<12} 0: {lv[0]:<10} 1: {lv[1]}")


def main() -> int:
    args = sys.argv[1:]
    if "--selftest" in args:
        return selftest()
    uncapped = "--no-uncapped" not in args   # the validity-stop fallback: throttle_exit_fallibility back to stock
    args = [a for a in args if a != "--no-uncapped"]
    opts = {"--seed": None, "--launch": None, "--out": None, "--amp": "3"}
    for k in list(opts):
        if k in args:
            i = args.index(k)
            opts[k] = args[i + 1]
            del args[i:i + 2]
    if args or None in opts.values():
        print(__doc__)
        return 3
    seed, launch, amp, out = int(opts["--seed"]), int(opts["--launch"]), float(opts["--amp"]), Path(opts["--out"])
    if launch < 1 or amp <= 0:
        sys.exit("--launch must be >= 1 and --amp > 0")
    ops = write_launch(seed, launch, out, amp, uncapped)
    assign = draw(seed, launch)
    print(f"V-1 seed {seed} launch {launch} -> {out / f'verve.v1-L{launch:02d}'} (id {addon_id(launch)})")
    print(f"  {'driver':<24}{'team':<12}" + "".join(f"{f[:7]:>8}" for f in FACTORS))
    for d in ROSTER:
        print(f"  {d:<24}{TEAM_OF[d]:<12}" + "".join(f"{assign[d][f]:>8}" for f in FACTORS))
    print(f"  {'ones':<36}" + "".join(f"{sum(assign[d][f] for d in ROSTER):>8}" for f in FACTORS))
    print()
    print_proposal()
    print()
    print_maps(map_plan(amp, uncapped=uncapped), amp)
    stock = stock_traits()
    same = sum(1 for d in ROSTER for t in TRAITS if float(stock[d][t]) == float(assign[d][t]))
    n_map = sum(1 for o in ops if o["select"] == PACKAGE_SELECT)
    print()
    print(f"expected ops: {len(ops)} = {len(ROSTER)} drivers x ({len(TRAITS)} traits + "
          f"{sum(len(PROPOSAL[b]) for b in BUNDLES)} bundle keys) + {n_map} maps")
    print(f"  of which {same} trait ops equal the stock row value (if gamedb counts only changed values, "
          f"expect {len(ops) - same} from this add-on; check race 1's overwrote lines)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
