"""D4 racecraft rating LOW vs HIGH in GP: the analysis (docs/verve_d4_prereg.md). Offline: reads a finished batch only.

Usage:
    python -I tools/d4_check.py runs/<batch> [--allow-partial] [--seed <S>] [--gamedb <N>] [--track 17]
    python -I tools/d4_check.py --selftest

Batch layout (tools/v1_run.ps1 -Make d4): <batch>/launch_<n>/gen/assignment.csv (driver, team, level high/low/stock;
tools/d4_make.py) and gen/expected_ops.csv, raw/udp.bin (all the launch's races, one race-session uid each),
weather.txt, raw/loader.log, check_applied.txt / gamedb_expected.txt, arm.txt ("D4 seed <S> launch <n>, ..."), and
invalid.txt if the session check failed. Writes <batch>/d4_check/{summary.json, per_car_launch.csv} and a short report
on stdout.

Validity, as tools/v1_check.py (by import, not a copy) and tools/d1_check.py: per race uid, aionly_check (INVALID or
FAIL = dropped), and the launch's build check (check_applied.txt with problems = every race of the launch dropped; the
36 curve ops are key-checked only, as approved). Also dropped: every race of a launch with invalid.txt (the session
check). The assignment must pass d4_make's structural checks, match the launch's expected_ops.csv, and (when the seed is
known: --seed, or arm.txt) equal d4_make.draw(seed, launch).

Primary (per launch): reaction_s (v1_check.start_measures: the LGOT arrival to the car's first LapData totalDistance
gain >= MOVE_M 0.3 m; relative, 1/60 s), each car's mean over the launch's valid races first, then the mean over the
HIGH cars minus the mean over the LOW cars (Alonso, stock, isn't scored). Model expectation -0.103 s.
  PASS: <= PASS_S (-0.05 s) in BOTH launches 1 and 2.
  NULL: |diff| < NULL_S (0.02 s) in BOTH launches.
  Otherwise INCONCLUSIVE.
  NOT SCORED: fewer than the 2 launches (without --allow-partial: refused, exit 3; no interim looks), or a launch with
  no valid race or no measured HIGH / LOW car.
Secondaries, not scored: passes_made and passes_suffered (race_feel held passes net, laps 2+, V-1's definition) and
gain_lap1 (grid - position at the end of lap 1), HIGH minus LOW, the same way.
Diagnostic, not scored (the prereg's row imbalance): the rows stay stock, so per launch the mean stock row
reaction_speed of the HIGH drivers minus the LOW drivers (docs/stock/bundle_26566308.csv), and that times the old row
slope ROW_SLOPE (-0.109 s/unit, B-0006): the difference "rows win" would predict.
Exit 0 done (any verdict), 2 usage, 3 refused (partial without --allow-partial, assignment problems, no gamedb).
"""
from __future__ import annotations

import csv
import io
import json
import random
import re
import statistics
import sys
import tempfile
from contextlib import redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import d4_make as dm  # noqa: E402
import v1_check as vc  # noqa: E402

N_LAUNCHES = 2
PASS_S = -0.05          # the prereg's PASS bar (supervisor, 2026-11-17)
NULL_S = 0.02           # the prereg's NULL band
ROW_SLOPE = -0.109      # s per unit of row reaction_speed: B-0006 (runs/2026-10-30-B-0006/summary.md:17-18)
PRIMARY = "reaction_s"
SECONDARY = {"passes_made": "/race", "passes_suffered": "/race", "gain_lap1": "places"}
PARTIAL = "NOT SCORED (partial)"
ROSTER = dm.ROSTER
STOCK_ROWS = dm.STOCK / "bundle_26566308.csv"
STOCK_ROWS_OLD = dm.STOCK / "driver_characteristics_grid.csv"


# ==================================================================================================== the statistic

def car_means(launch: dict, measure: str) -> dict[str, tuple[float, int]]:
    """{driver: (mean over the launch's valid races, races)} for one measure."""
    vals: dict[str, list[float]] = {}
    for r in launch["races"]:
        if not r["valid"]:
            continue
        for drv, v in r["drivers"].items():
            if v.get(measure) is not None:
                vals.setdefault(drv, []).append(v[measure])
    return {d: (statistics.fmean(x), len(x)) for d, x in vals.items()}


def launch_diff(launch: dict, level: dict[str, str], measure: str) -> dict:
    """HIGH minus LOW for one launch: a car's mean over its races first, then the mean over cars."""
    cm = car_means(launch, measure)
    h = [cm[d][0] for d in ROSTER if level[d] == "high" and d in cm]
    lo = [cm[d][0] for d in ROSTER if level[d] == "low" and d in cm]
    out = {"measure": measure, "races_valid": sum(r["valid"] for r in launch["races"]),
           "races_total": len(launch["races"]), "n_high": len(h), "n_low": len(lo),
           "high_mean": statistics.fmean(h) if h else None, "low_mean": statistics.fmean(lo) if lo else None}
    out["diff"] = out["high_mean"] - out["low_mean"] if h and lo else None
    return out


def stock_rows(path: Path = STOCK_ROWS, label: str = "row_label") -> dict[str, float]:
    """{row label: stock row reaction_speed} from a docs/stock CSV (# lines skipped)."""
    with path.open(encoding="utf-8-sig") as f:
        return {r[label]: float(r["reaction_speed"]) for r in csv.DictReader(ln for ln in f if not ln.startswith("#"))}


def imbalance(level: dict[str, str], rows: dict[str, float]) -> dict:
    """The stock-row imbalance of one draw: mean row reaction_speed HIGH - LOW, and that times ROW_SLOPE."""
    h = [rows[d] for d in ROSTER if level[d] == "high"]
    lo = [rows[d] for d in ROSTER if level[d] == "low"]
    d = statistics.fmean(h) - statistics.fmean(lo)
    return {"high_row_rs": statistics.fmean(h), "low_row_rs": statistics.fmean(lo), "diff_row_rs": d,
            "rows_win_s": d * ROW_SLOPE}


def verdict_of(diffs: dict[int, float]) -> tuple[str, str]:
    need = range(1, N_LAUNCHES + 1)
    if all(diffs[n] <= PASS_S for n in need):
        return "PASS", f"HIGH - LOW <= {PASS_S} s in both launches"
    if all(abs(diffs[n]) < NULL_S for n in need):
        return "NULL", f"|HIGH - LOW| < {NULL_S} s in both launches"
    return "INCONCLUSIVE", (f"neither PASS (<= {PASS_S} s in both) nor NULL (|diff| < {NULL_S} s in both): "
                            + ", ".join(f"launch {n} {diffs[n]:+.3f} s" for n in need))


def score(launch_data: dict[int, dict], levels: dict[int, dict[str, str]], partial: bool = False,
          rows: dict[str, float] | None = None) -> dict:
    """The D4 verdict from per-launch measure tables (launch_data[n] = {"races": [{"valid", "drivers": {driver:
    {measure: value}}}]}, as v1_check.process_launch returns them)."""
    rows = stock_rows() if rows is None else rows
    per = {n: {"primary": launch_diff(L, levels[n], PRIMARY),
               "secondary": {m: launch_diff(L, levels[n], m) for m in SECONDARY},
               "imbalance": imbalance(levels[n], rows)} for n, L in launch_data.items()}
    need = list(range(1, N_LAUNCHES + 1))
    have = [n for n in need if n in per]
    unread = [n for n in have if per[n]["primary"]["diff"] is None]
    diffs = {n: per[n]["primary"]["diff"] for n in have}
    if partial or len(have) < N_LAUNCHES:
        verdict = PARTIAL if partial else "NOT SCORED"
        why = f"{len(have)} of {N_LAUNCHES} launches"
    elif unread:
        verdict, why = "NOT SCORED", f"launch(es) {unread}: no valid race, or no measured HIGH or LOW car"
    else:
        verdict, why = verdict_of(diffs)
    sec = {}
    for m in SECONDARY:
        xs = [per[n]["secondary"][m]["diff"] for n in have if per[n]["secondary"][m]["diff"] is not None]
        sec[m] = statistics.fmean(xs) if xs else None
    return {"verdict": verdict, "why": why, "pass_s": PASS_S, "null_s": NULL_S, "per_launch": per,
            "ignored_launches": sorted(set(per) - set(need)), "secondary_mean_over_launches": sec}


# ==================================================================================================== the batch

def seed_of(ld: Path, arg: str | None) -> tuple[int | None, str]:
    """The seed from --seed or arm.txt ("D4 seed <S> launch <n>, ..."); problems if they disagree or arm isn't D4."""
    arm = ld / "arm.txt"
    s = None
    if arm.exists():
        t = arm.read_text(encoding="utf-8-sig", errors="replace")
        m = re.match(r"\s*D4 seed (-?\d+) launch (\d+)", t)
        if not m:
            return None, f"arm.txt is not a D4 launch: {t.strip()[:60]!r}"
        s = int(m[1])
    if arg is not None:
        if s is not None and s != int(arg):
            return None, f"--seed {arg} disagrees with arm.txt seed {s}"
        s = int(arg)
    return s, ""


def assignment_of(n: int, ld: Path, seed_arg: str | None) -> tuple[dict[str, str] | None, list[str]]:
    try:
        level = dm.read_assignment(ld / "gen" / "assignment.csv")
    except (KeyError, ValueError) as e:
        return None, [f"gen/assignment.csv unreadable as a D4 assignment ({e!r})"]
    probs = dm.assignment_problems(level)
    if probs:
        return None, probs
    exp = ld / "gen" / "expected_ops.csv"
    if exp.exists():
        with exp.open(encoding="utf-8", newline="") as f:
            got = sorted((r["path"], r["field"], r["value"]) for r in csv.DictReader(f))
        if got != sorted((o["select"], o["field"], o["value"]) for o in dm.build_ops(level)):
            return None, ["gen/expected_ops.csv does not match the assignment's HIGH / LOW drivers"]
    else:
        return None, ["no gen/expected_ops.csv"]
    seed, why = seed_of(ld, seed_arg)
    if why:
        return None, [why]
    if seed is not None and level != dm.draw(seed, n):
        return None, [f"gen/assignment.csv is not d4_make.draw({seed}, {n})"]
    return level, []


def mark_invalid_launch(ld: Path, launch: dict) -> None:
    inv = ld / "invalid.txt"
    if inv.exists():
        why = (inv.read_text(encoding="utf-8-sig", errors="replace").strip().splitlines() or ["(empty)"])[0]
        for r in launch["races"]:
            r["valid"], r["verdict"] = False, "INVALID"
            r["reasons"] = r["reasons"] + [f"INVALID: launch marked invalid.txt ({why})"]


def fnum(x, nd=3, unit=""):
    return "n/a" if x is None else f"{x:+.{nd}f}{unit}"


def report(res: dict, head: list[str]) -> list[str]:
    lines = list(head)
    for n, v in sorted(res["per_launch"].items()):
        p = v["primary"]
        mark = ""
        if p["diff"] is not None:
            mark = f" ({'<=' if p['diff'] <= PASS_S else '>'} {PASS_S}; |diff| {'<' if abs(p['diff']) < NULL_S else '>='} {NULL_S})"
        lines.append(f"  launch {n}: {p['races_valid']}/{p['races_total']} races valid; reaction HIGH "
                     f"{fnum(p['high_mean'])} s ({p['n_high']} cars) - LOW {fnum(p['low_mean'])} s "
                     f"({p['n_low']} cars) = {fnum(p['diff'], unit=' s')}{mark}")
        for m, unit in SECONDARY.items():
            s = v["secondary"][m]
            lines.append(f"    secondary {m}: HIGH - LOW {fnum(s['diff'], 2, ' ' + unit)} "
                         f"({s['n_high']}/{s['n_low']} cars; not scored)")
        im = v["imbalance"]
        lines.append(f"    row imbalance (diagnostic): stock row reaction_speed HIGH {im['high_row_rs']:.3f} - LOW "
                     f"{im['low_row_rs']:.3f} = {im['diff_row_rs']:+.3f}; x {ROW_SLOPE} s/unit = "
                     f"{im['rows_win_s']:+.4f} s if rows won (not scored)")
    if res["ignored_launches"]:
        lines.append(f"  ignored: launch(es) {res['ignored_launches']} (the prereg has launches 1-{N_LAUNCHES})")
    sec = ", ".join(f"{m} {fnum(x, 2, ' ' + SECONDARY[m])}" for m, x in res["secondary_mean_over_launches"].items())
    lines.append(f"  secondaries, mean over launches (not scored): {sec}")
    lines.append(f"D4 primary: {res['verdict']} ({res['why']})")
    return lines


def write_outputs(out: Path, launch_data: dict, levels: dict, res: dict, meta: dict) -> None:
    out.mkdir(parents=True, exist_ok=True)
    with (out / "per_car_launch.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        ms = [PRIMARY] + list(SECONDARY)
        w.writerow(["launch", "driver", "team", "level"] + [x for m in ms for x in (m, f"{m}_races")])
        for n, L in sorted(launch_data.items()):
            cms = {m: car_means(L, m) for m in ms}
            for d in ROSTER:
                row = [n, d, dm.TEAM_OF[d], levels[n][d]]
                for m in ms:
                    mu, k = cms[m].get(d, (None, 0))
                    row += ["" if mu is None else round(mu, 4), k]
                w.writerow(row)
    js = {**meta, **res}
    (out / "summary.json").write_text(json.dumps(js, indent=1, default=str) + "\n", encoding="utf-8")


def run(batch: Path, gamedb: int | None, seed_arg: str | None, track: str, allow_partial: bool,
        quiet: bool = False) -> int:
    say = (lambda *a: None) if quiet else print
    pre = (lambda s: f"{PARTIAL} | {s}") if allow_partial else (lambda s: s)
    launches = vc.find_launches(batch)
    complete = {n: ld for n, ld in launches.items() if not vc.launch_problems(ld)}
    need = set(range(1, N_LAUNCHES + 1))
    full = need <= set(complete)
    if not full and not allow_partial:
        print(f"NOT SCORED: REFUSED: {len(need & set(complete))} complete launch(es) of {N_LAUNCHES} in {batch} "
              f"(found {sorted(launches)}; incomplete {[n for n in launches if n not in complete]}). No interim looks: "
              f"run after launch {N_LAUNCHES}, or --allow-partial ({PARTIAL}).")
        return 3
    if not complete:
        print(pre(f"no complete launch in {batch}"))
        return 3
    levels = {}
    for n, ld in complete.items():
        level, probs = assignment_of(n, ld, seed_arg)
        if probs:
            print(pre(f"REFUSED: launch_{n}: {'; '.join(probs)}"))
            return 3
        levels[n] = level
    if gamedb is None and vc._VALIDITY_OVERRIDE is None and not all(
            (ld / "gamedb_expected.txt").exists() for ld in complete.values()):
        print(pre("REFUSED: --gamedb <expected overwritten count> is required unless every launch has v1_run's "
                  "gamedb_expected.txt"))
        return 3
    out = batch / "d4_check"
    launch_data = {}
    for n, ld in complete.items():
        L = vc.process_launch(n, ld, gamedb, track, out, log=lambda s: None)
        mark_invalid_launch(ld, L)
        for r in L["races"]:
            say(pre(f"  launch {n} race {r['race']} uid {r['uid']}: {r['verdict']}"
                    + (f" ({'; '.join(r['reasons'])})" if r["reasons"] else "")))
        launch_data[n] = L
    res = score(launch_data, levels, partial=allow_partial and not full)
    races = [r for L in launch_data.values() for r in L["races"]]
    meta = {"batch": str(batch), "launches": sorted(complete), "races_total": len(races),
            "races_valid": sum(r["valid"] for r in races), "track": track, "gamedb": gamedb,
            "high": {n: [d for d in ROSTER if lv[d] == "high"] for n, lv in levels.items()},
            "low": {n: [d for d in ROSTER if lv[d] == "low"] for n, lv in levels.items()},
            "dropped": [{"launch": r["launch"], "race": r["race"], "uid": r["uid"], "verdict": r["verdict"],
                         "reasons": r["reasons"]} for r in races if not r["valid"]],
            "constants": {"MOVE_M": vc.MOVE_M, "PASS_S": PASS_S, "NULL_S": NULL_S, "ROW_SLOPE": ROW_SLOPE,
                          "N_LAUNCHES": N_LAUNCHES, "LEVELS": dm.LEVELS}}
    write_outputs(out, launch_data, levels, res, meta)
    head = [f"D4 check {batch}: {len(complete)} launch(es), {meta['races_valid']}/{len(races)} races valid"]
    for ln in report(res, head):
        say(pre(ln))
    say(pre(f"wrote {out / 'summary.json'}, per_car_launch.csv"))
    return 0


# ==================================================================================================== selftest

def synth_tables(levels: dict[int, dict[str, str]], plant: dict[int, float] | float, rng_seed: int = 5,
                 races: int = 4) -> dict:
    """Measure tables injected below the parsing layer. A team effect (teammates share it, so the coin can't move it),
    small race noise, and plant[n] = the HIGH cars' reaction offset in launch n (a float: the same in every launch)."""
    rng = random.Random(rng_seed)
    team_base = {t: rng.uniform(0.38, 0.52) for t, _ in dm.TEAMS}
    data = {}
    for n, level in levels.items():
        pl = plant[n] if isinstance(plant, dict) else plant
        rs = []
        for k in range(races):
            drivers = {}
            for d in ROSTER:
                rt = team_base[dm.TEAM_OF[d]] + rng.gauss(0, 0.004) + pl * (level[d] == "high")
                drivers[d] = {"reaction_s": rt, "passes_made": rng.choice((0, 0, 1, 2)) + (level[d] == "high"),
                              "passes_suffered": rng.choice((0, 0, 1, 2)), "gain_lap1": rng.choice((-1, 0, 0, 1))}
            rs.append({"launch": n, "race": k + 1, "uid": f"{n}{k}", "valid": True, "verdict": "PASS",
                       "reasons": [], "drivers": drivers})
        data[n] = {"launch": n, "races": rs, "grids": []}
    return data


def write_synth_batch(batch: Path, seed: int, launches: list[int], plant_s: float, rng_seed: int = 3) -> None:
    """On-disk D4 batch: launch_<n>/gen (d4_make.write_launch), arm.txt, raw/udp.bin with 4 races in udp_parse's
    layouts (v1_check.write_synth_capture). Teammates share a base reaction (so the draw can't move it), the HIGH cars
    react round(plant_s * 60) frames from it, and every car +-1 frame of noise per race."""
    rng = random.Random(rng_seed)
    team_rt = {t: rng.choice(range(22, 32)) for t, _ in dm.TEAMS}        # frames (1/60 s)
    accel = {d: rng.uniform(9.0, 11.0) for d in ROSTER}
    for n in launches:
        ld = batch / f"launch_{n}"
        dm.write_launch(seed, n, ld / "gen")
        (ld / "arm.txt").write_text(f"D4 seed {seed} launch {n}, add-on {dm.addon_id(n)}, plan\n", encoding="utf-8")
        level = dm.draw(seed, n)
        order = ROSTER[:]
        rng.shuffle(order)
        react = {d: [(team_rt[dm.TEAM_OF[d]] + round(plant_s * 60) * (level[d] == "high") + rng.choice((-1, 0, 1)))
                     / 60 for _ in range(vc.RACES_PER_LAUNCH)] for d in ROSTER}
        vc.write_synth_capture(ld / "raw" / "udp.bin", order, react, accel, uid0=1000 * n)


def selftest() -> int:
    results, ok = [], True

    def chk(name: str, cond: bool, detail: str = "") -> None:
        nonlocal ok
        ok &= bool(cond)
        results.append(f"{'ok  ' if cond else 'FAIL'} {name}" + (f": {detail}" if detail else ""))

    seed = 2026111704
    levels = {n: dm.draw(seed, n) for n in (1, 2)}
    # ---- 1. measure tables injected below the parsing layer
    for plant, want in ((-0.10, "PASS"), (0.0, "NULL"), (-0.03, "INCONCLUSIVE"), (+0.10, "INCONCLUSIVE")):
        r = score(synth_tables(levels, plant), levels)
        d = [fnum(r["per_launch"][n]["primary"]["diff"]) for n in (1, 2)]
        chk(f"tables: planted {plant:+.2f} s on the HIGH cars -> {want}", r["verdict"] == want, f"diffs {d}")
    one = {1: levels[1]}
    chk("tables: one launch -> NOT SCORED", score(synth_tables(one, -0.10), one)["verdict"] == "NOT SCORED")
    chk("tables: one launch with --allow-partial -> NOT SCORED (partial)",
        score(synth_tables(one, -0.10), one, partial=True)["verdict"] == PARTIAL)
    r = score(synth_tables(levels, {1: -0.10, 2: -0.03}), levels)
    chk("tables: PASS needs BOTH launches (-0.10 and -0.03 -> INCONCLUSIVE)", r["verdict"] == "INCONCLUSIVE", r["why"])
    r = score(synth_tables(levels, {1: 0.0, 2: -0.03}), levels)
    chk("tables: NULL needs BOTH launches (0 and -0.03 -> INCONCLUSIVE)", r["verdict"] == "INCONCLUSIVE", r["why"])
    r = score(synth_tables(levels, {1: -0.10, 2: 0.0}), levels)
    chk("tables: one PASS-like and one NULL-like launch -> INCONCLUSIVE", r["verdict"] == "INCONCLUSIVE", r["why"])
    chk("verdict_of at the edges: -0.05 both PASS, -0.0499 not; +/-0.0199 NULL, 0.02 not",
        verdict_of({1: -0.05, 2: -0.05})[0] == "PASS" and verdict_of({1: -0.0499, 2: -0.06})[0] == "INCONCLUSIVE"
        and verdict_of({1: 0.0199, 2: -0.0199})[0] == "NULL" and verdict_of({1: 0.02, 2: 0.0})[0] == "INCONCLUSIVE")
    t = synth_tables(levels, -0.10)
    for rr in t[2]["races"]:
        rr["valid"] = False
    chk("tables: a launch with no valid race -> NOT SCORED", score(t, levels)["verdict"] == "NOT SCORED")
    r = score(synth_tables(levels, -0.10), levels)
    chk("tables: secondaries are computed HIGH - LOW and not scored (passes_made planted +1 on HIGH)",
        r["verdict"] == "PASS" and 0.5 < r["secondary_mean_over_launches"]["passes_made"] < 1.5
        and all(r["secondary_mean_over_launches"][m] is not None for m in SECONDARY),
        str({m: fnum(x, 2) for m, x in r["secondary_mean_over_launches"].items()}))
    t = synth_tables(levels, -0.10, races=1)
    t4 = {n: {**L, "races": L["races"] * 4} for n, L in t.items()}
    chk("tables: the car is the unit (4 copies of a race give the same difference)", all(
        abs(score(t, levels)["per_launch"][n]["primary"]["diff"] - score(t4, levels)["per_launch"][n]["primary"]["diff"])
        < 1e-12 for n in (1, 2)))
    hl = {d: "stock" for d in ROSTER}
    hl.update({"oscar_piastri": "high", "lando_norris": "low"})
    hand = {"launch": 1, "races": [
        {"valid": True, "drivers": {"oscar_piastri": {"reaction_s": 0.3}, "lando_norris": {"reaction_s": 0.5},
                                    "fernando_alonso": {"reaction_s": 9.0}}},
        {"valid": True, "drivers": {"oscar_piastri": {"reaction_s": 0.4}}},
        {"valid": False, "drivers": {"lando_norris": {"reaction_s": 9.0}}}]}
    hd = launch_diff(hand, hl, PRIMARY)
    chk("tables: by hand, HIGH car mean 0.35 - LOW 0.5 = -0.15 (the invalid race and the stock car ignored)",
        abs(hd["diff"] + 0.15) < 1e-12 and hd["n_high"] == 1 and hd["n_low"] == 1, str(hd["diff"]))

    # ---- 2. the row imbalance
    rows = stock_rows()
    chk("stock rows: bundle_26566308.csv has all 19 roster rows and equals driver_characteristics_grid.csv on them",
        set(ROSTER) <= set(rows) and all(rows[d] == stock_rows(STOCK_ROWS_OLD, "label")[d] for d in ROSTER))
    worst = sum(abs(rows[a] - rows[b]) for _, ds in dm.TEAMS if len(ds) == 2 for a, b in [ds]) / 9
    chk("the worst case over all draws is 0.12 (the prereg's), at most +/-0.013 s if rows won",
        abs(worst - 0.12) < 1e-9 and abs(worst * ROW_SLOPE) < 0.0131, f"{worst:.3f} -> {worst * ROW_SLOPE:+.4f} s")
    im = imbalance(levels[1], rows)
    want = (statistics.fmean(rows[d] for d in ROSTER if levels[1][d] == "high")
            - statistics.fmean(rows[d] for d in ROSTER if levels[1][d] == "low"))
    chk("imbalance = mean row rs HIGH - LOW, times -0.109", abs(im["diff_row_rs"] - want) < 1e-12
        and abs(im["rows_win_s"] - want * -0.109) < 1e-12 and abs(im["diff_row_rs"]) <= worst + 1e-12,
        f"launch 1: {im['diff_row_rs']:+.3f} -> {im['rows_win_s']:+.4f} s")
    flipped = {d: {"high": "low", "low": "high"}.get(v, v) for d, v in levels[1].items()}
    chk("flipping every coin flips the imbalance's sign", abs(imbalance(flipped, rows)["diff_row_rs"] + im["diff_row_rs"])
        < 1e-12)
    rep = "\n".join(report(score(synth_tables(levels, -0.10), levels), ["head"]))
    chk("the report prints the imbalance per launch and the verdict",
        rep.count("row imbalance (diagnostic)") == 2 and "D4 primary: PASS" in rep)

    # ---- 3. synthetic UDP through the whole tool (v1_check's parsing and start_measures), validity stubbed
    saved = vc._VALIDITY_OVERRIDE
    vc._VALIDITY_OVERRIDE = lambda ld, uid: ("PASS", [])   # noqa: E731
    try:
        with tempfile.TemporaryDirectory() as tmp:
            pb = None
            for plant, want in ((-0.10, "PASS"), (0.0, "NULL"), (-0.03, "INCONCLUSIVE")):
                batch = Path(tmp) / f"b{int(round(-plant * 100))}"
                write_synth_batch(batch, seed, [1, 2], plant)
                buf = io.StringIO()
                with redirect_stdout(buf):
                    rc = run(batch, None, None, vc.TRACK_AUSTRIA, False)
                js = json.loads((batch / "d4_check" / "summary.json").read_text(encoding="utf-8"))
                d = [fnum(js["per_launch"][str(n)]["primary"]["diff"]) for n in (1, 2)]
                chk(f"end to end: planted {plant:+.2f} s ({round(plant * 60)} frames) on HIGH -> {want}, 8/8 races "
                    f"valid", rc == 0 and js["verdict"] == want and js["races_valid"] == 8
                    and f"D4 primary: {want}" in buf.getvalue(), f"rc {rc}, diffs {d}")
                if want == "PASS":
                    rows_csv = list(csv.DictReader((batch / "d4_check" / "per_car_launch.csv").open(encoding="utf-8")))
                    chk("end to end: per_car_launch.csv has 2 x 19 cars, 4 races each, 9 HIGH / 9 LOW / 1 stock",
                        len(rows_csv) == 38 and all(r["reaction_s_races"] == "4" for r in rows_csv)
                        and all([r["level"] for r in rows_csv if r["launch"] == str(n)].count(lv) == k
                                for n in (1, 2) for lv, k in (("high", 9), ("low", 9), ("stock", 1))))
                    chk("end to end: the report has the secondaries and the row imbalance",
                        buf.getvalue().count("secondary passes_made") == 2
                        and buf.getvalue().count("row imbalance (diagnostic)") == 2
                        and "imbalance" in js["per_launch"]["1"])
                    pb = batch
            part = Path(tmp) / "partial"
            write_synth_batch(part, seed, [1], -0.10)
            buf = io.StringIO()
            with redirect_stdout(buf):
                rc3 = run(part, None, None, vc.TRACK_AUSTRIA, False)
            chk("end to end: one launch -> NOT SCORED, refused (exit 3)", rc3 == 3 and
                buf.getvalue().startswith("NOT SCORED"))
            buf = io.StringIO()
            with redirect_stdout(buf):
                rcp = run(part, None, None, vc.TRACK_AUSTRIA, True)
            lines = [ln for ln in buf.getvalue().splitlines() if ln.strip()]
            pj = json.loads((part / "d4_check" / "summary.json").read_text(encoding="utf-8"))
            chk("end to end: one launch with --allow-partial -> NOT SCORED (partial) on every line",
                rcp == 0 and pj["verdict"] == PARTIAL and lines and all(PARTIAL in ln for ln in lines))
            (pb / "launch_2" / "invalid.txt").write_text("invalid: difficulty 99 (session check)\n", encoding="utf-8")
            with redirect_stdout(io.StringIO()):
                run(pb, None, None, vc.TRACK_AUSTRIA, False)
            js = json.loads((pb / "d4_check" / "summary.json").read_text(encoding="utf-8"))
            chk("end to end: invalid.txt drops the launch's races -> NOT SCORED", js["verdict"] == "NOT SCORED"
                and js["races_valid"] == 4, js["why"])
            (pb / "launch_2" / "invalid.txt").unlink()
            buf = io.StringIO()
            with redirect_stdout(buf):
                rcs = run(pb, None, str(seed + 1), vc.TRACK_AUSTRIA, False)
            chk("an assignment that isn't draw(--seed, launch) is refused", rcs == 3 and "disagrees" in buf.getvalue())
            a1 = (pb / "launch_1" / "gen" / "assignment.csv").read_text(encoding="utf-8")
            (pb / "launch_1" / "gen" / "assignment.csv").write_text(
                (pb / "launch_2" / "gen" / "assignment.csv").read_text(encoding="utf-8"), encoding="utf-8")
            buf = io.StringIO()
            with redirect_stdout(buf):
                rcm = run(pb, None, None, vc.TRACK_AUSTRIA, False)
            chk("an assignment.csv that doesn't match the launch's expected_ops.csv is refused",
                rcm == 3 and "expected_ops.csv does not match" in buf.getvalue(), buf.getvalue().strip()[:120])
            (pb / "launch_1" / "gen" / "assignment.csv").write_text(
                "driver,team,pinned\n" + "".join(f"{d},{dm.TEAM_OF[d]},0\n" for d in ROSTER), encoding="utf-8")
            buf = io.StringIO()
            with redirect_stdout(buf):
                rcd = run(pb, None, None, vc.TRACK_AUSTRIA, False)
            chk("a D1 assignment.csv (pinned, no level) is refused", rcd == 3 and "unreadable as a D4" in buf.getvalue())
            (pb / "launch_1" / "gen" / "assignment.csv").write_text(a1, encoding="utf-8")
            (pb / "launch_1" / "arm.txt").write_text("D1 seed 1 launch 1, add-on verve.d1-l01\n", encoding="utf-8")
            buf = io.StringIO()
            with redirect_stdout(buf):
                rcv = run(pb, None, None, vc.TRACK_AUSTRIA, False)
            chk("a D1 arm.txt is refused", rcv == 3 and "not a D4 launch" in buf.getvalue())
    finally:
        vc._VALIDITY_OVERRIDE = saved
    print("\n".join(results))
    print("selftest", "ok" if ok else "FAILED")
    return 0 if ok else 1


# ==================================================================================================== CLI

def main(argv: list[str]) -> int:
    args = list(argv)
    if "--selftest" in args:
        return selftest()
    allow = "--allow-partial" in args
    args = [a for a in args if a != "--allow-partial"]
    opts = {"--seed": None, "--gamedb": None, "--track": vc.TRACK_AUSTRIA}
    for k in list(opts):
        if k in args:
            i = args.index(k)
            if i + 1 >= len(args):
                print(__doc__)
                return 2
            opts[k] = args[i + 1]
            del args[i:i + 2]
    if len(args) != 1:
        print(__doc__)
        return 2
    return run(Path(args[0]), int(opts["--gamedb"]) if opts["--gamedb"] else None, opts["--seed"], opts["--track"],
               allow)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
