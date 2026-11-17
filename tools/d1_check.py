"""D1 positive control in GP: the analysis (docs/verve_d1_d2_prereg.md). Offline: reads a finished batch only.

Usage:
    python -I tools/d1_check.py runs/<batch> [--allow-partial] [--seed <S>] [--gamedb <N>] [--track 17]
    python -I tools/d1_check.py --selftest

Batch layout (tools/v1_run.ps1 -Make d1): <batch>/launch_<n>/gen/assignment.csv (driver, team, pinned; tools/d1_make.py)
and gen/expected_ops.csv, raw/udp.bin (all the launch's races, one race-session uid each), weather.txt, raw/loader.log,
check_applied.txt / gamedb_expected.txt, arm.txt ("D1 seed <S> launch <n>, ..."), and invalid.txt if the session
check failed. Writes <batch>/d1_check/{summary.json, per_car_launch.csv} and a short report on stdout.

Validity, as tools/v1_check.py (by import, not a copy): per race uid, aionly_check (INVALID or FAIL = dropped), and
the launch's build check (check_applied.txt with problems = every race of the launch dropped). Also dropped: every race
of a launch with invalid.txt (the session check). The assignment must pass d1_make's structural checks, match the
launch's expected_ops.csv, and (when the seed is known: --seed, or arm.txt) equal d1_make.draw(seed, launch).

Primary (per launch): reaction_s (v1_check.start_measures: the LGOT arrival to the car's first LapData totalDistance
gain >= MOVE_M 0.3 m; relative, 1/60 s), each car's mean over the launch's valid races first, then the mean over the
pinned cars minus the mean over the stock cars. PASS: >= THRESHOLD_S (0.12 s) in BOTH launches 1 and 2. FAIL: below
it in either. NOT SCORED: fewer than the 2 launches (without --allow-partial: refused, exit 3; no interim looks), or a
launch with no valid race or no measured pinned / stock car.
Secondaries, not scored (B-0012b's exploratory signal): speed_1s_kph (CarTelemetry speed 1 s after LGOT) and gain_t1
(grid - position at lapDistance T1_M 345 m), pinned minus stock, the same way.
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
import d1_make as dm  # noqa: E402
import v1_check as vc  # noqa: E402

N_LAUNCHES = 2
THRESHOLD_S = 0.12      # the supervisor's threshold (prereg D1)
PRIMARY = "reaction_s"
SECONDARY = {"speed_1s_kph": "km/h", "gain_t1": "places"}
PARTIAL = "NOT SCORED (partial)"
ROSTER = dm.ROSTER


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


def launch_diff(launch: dict, pin: dict[str, int], measure: str) -> dict:
    """Pinned minus stock for one launch: a car's mean over its races first, then the mean over cars."""
    cm = car_means(launch, measure)
    p = [cm[d][0] for d in ROSTER if pin[d] and d in cm]
    s = [cm[d][0] for d in ROSTER if not pin[d] and d in cm]
    out = {"measure": measure, "races_valid": sum(r["valid"] for r in launch["races"]),
           "races_total": len(launch["races"]), "n_pinned": len(p), "n_stock": len(s),
           "pinned_mean": statistics.fmean(p) if p else None, "stock_mean": statistics.fmean(s) if s else None}
    out["diff"] = out["pinned_mean"] - out["stock_mean"] if p and s else None
    return out


def score(launch_data: dict[int, dict], pins: dict[int, dict[str, int]], partial: bool = False) -> dict:
    """The D1 verdict from per-launch measure tables (launch_data[n] = {"races": [{"valid", "drivers": {driver:
    {measure: value}}}]}, as v1_check.process_launch returns them)."""
    per = {n: {"primary": launch_diff(L, pins[n], PRIMARY),
               "secondary": {m: launch_diff(L, pins[n], m) for m in SECONDARY}} for n, L in launch_data.items()}
    need = list(range(1, N_LAUNCHES + 1))
    have = [n for n in need if n in per]
    unread = [n for n in have if per[n]["primary"]["diff"] is None]
    diffs = {n: per[n]["primary"]["diff"] for n in have}
    if partial or len(have) < N_LAUNCHES:
        verdict = PARTIAL if partial else "NOT SCORED"
        why = f"{len(have)} of {N_LAUNCHES} launches"
    elif unread:
        verdict, why = "NOT SCORED", f"launch(es) {unread}: no valid race, or no measured pinned or stock car"
    elif all(diffs[n] >= THRESHOLD_S for n in need):
        verdict, why = "PASS", f"pinned - stock >= {THRESHOLD_S} s in both launches"
    else:
        verdict = "FAIL"
        why = f"pinned - stock < {THRESHOLD_S} s in launch(es) {[n for n in need if diffs[n] < THRESHOLD_S]}"
    sec = {}
    for m in SECONDARY:
        xs = [per[n]["secondary"][m]["diff"] for n in have if per[n]["secondary"][m]["diff"] is not None]
        sec[m] = statistics.fmean(xs) if xs else None
    return {"verdict": verdict, "why": why, "threshold_s": THRESHOLD_S, "per_launch": per,
            "ignored_launches": sorted(set(per) - set(need)), "secondary_mean_over_launches": sec}


# ==================================================================================================== the batch

def seed_of(ld: Path, arg: str | None) -> tuple[int | None, str]:
    """The seed from --seed or arm.txt ("D1 seed <S> launch <n>, ..."); problems if they disagree or arm isn't D1."""
    arm = ld / "arm.txt"
    s = None
    if arm.exists():
        t = arm.read_text(encoding="utf-8-sig", errors="replace")
        m = re.match(r"\s*D1 seed (-?\d+) launch (\d+)", t)
        if not m:
            return None, f"arm.txt is not a D1 launch: {t.strip()[:60]!r}"
        s = int(m[1])
    if arg is not None:
        if s is not None and s != int(arg):
            return None, f"--seed {arg} disagrees with arm.txt seed {s}"
        s = int(arg)
    return s, ""


def assignment_of(n: int, ld: Path, seed_arg: str | None) -> tuple[dict[str, int] | None, list[str]]:
    try:
        pin = dm.read_assignment(ld / "gen" / "assignment.csv")
    except (KeyError, ValueError) as e:
        return None, [f"gen/assignment.csv unreadable as a D1 assignment ({e!r})"]
    probs = dm.assignment_problems(pin)
    if probs:
        return None, probs
    exp = ld / "gen" / "expected_ops.csv"
    if exp.exists():
        with exp.open(encoding="utf-8", newline="") as f:
            got = sorted((r["path"], r["field"], r["value"]) for r in csv.DictReader(f))
        if got != sorted((o["select"], o["field"], o["value"]) for o in dm.build_ops(pin)):
            return None, ["gen/expected_ops.csv does not match the assignment's pinned drivers"]
    else:
        return None, ["no gen/expected_ops.csv"]
    seed, why = seed_of(ld, seed_arg)
    if why:
        return None, [why]
    if seed is not None and pin != dm.draw(seed, n):
        return None, [f"gen/assignment.csv is not d1_make.draw({seed}, {n})"]
    return pin, []


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
        lines.append(f"  launch {n}: {p['races_valid']}/{p['races_total']} races valid; reaction pinned "
                     f"{fnum(p['pinned_mean'])} s ({p['n_pinned']} cars) - stock {fnum(p['stock_mean'])} s "
                     f"({p['n_stock']} cars) = {fnum(p['diff'], unit=' s')}"
                     + ("" if p["diff"] is None else f" ({'>=' if p['diff'] >= THRESHOLD_S else '<'} {THRESHOLD_S})"))
        for m, unit in SECONDARY.items():
            s = v["secondary"][m]
            lines.append(f"    secondary {m}: pinned - stock {fnum(s['diff'], 2, ' ' + unit)} "
                         f"({s['n_pinned']}/{s['n_stock']} cars; not scored)")
    if res["ignored_launches"]:
        lines.append(f"  ignored: launch(es) {res['ignored_launches']} (the prereg has launches 1-{N_LAUNCHES})")
    sec = ", ".join(f"{m} {fnum(x, 2, ' ' + SECONDARY[m])}" for m, x in res["secondary_mean_over_launches"].items())
    lines.append(f"  secondaries, mean over launches (not scored): {sec}")
    lines.append(f"D1 primary: {res['verdict']} ({res['why']})")
    return lines


def write_outputs(out: Path, launch_data: dict, pins: dict, res: dict, meta: dict) -> None:
    out.mkdir(parents=True, exist_ok=True)
    with (out / "per_car_launch.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        ms = [PRIMARY] + list(SECONDARY)
        w.writerow(["launch", "driver", "team", "pinned"] + [x for m in ms for x in (m, f"{m}_races")])
        for n, L in sorted(launch_data.items()):
            cms = {m: car_means(L, m) for m in ms}
            for d in ROSTER:
                row = [n, d, dm.TEAM_OF[d], pins[n][d]]
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
    pins = {}
    for n, ld in complete.items():
        pin, probs = assignment_of(n, ld, seed_arg)
        if probs:
            print(pre(f"REFUSED: launch_{n}: {'; '.join(probs)}"))
            return 3
        pins[n] = pin
    if gamedb is None and vc._VALIDITY_OVERRIDE is None and not all(
            (ld / "gamedb_expected.txt").exists() for ld in complete.values()):
        print(pre("REFUSED: --gamedb <expected overwritten count> is required unless every launch has v1_run's "
                  "gamedb_expected.txt"))
        return 3
    out = batch / "d1_check"
    launch_data = {}
    for n, ld in complete.items():
        L = vc.process_launch(n, ld, gamedb, track, out, log=lambda s: None)
        mark_invalid_launch(ld, L)
        for r in L["races"]:
            say(pre(f"  launch {n} race {r['race']} uid {r['uid']}: {r['verdict']}"
                    + (f" ({'; '.join(r['reasons'])})" if r["reasons"] else "")))
        launch_data[n] = L
    res = score(launch_data, pins, partial=allow_partial and not full)
    races = [r for L in launch_data.values() for r in L["races"]]
    meta = {"batch": str(batch), "launches": sorted(complete), "races_total": len(races),
            "races_valid": sum(r["valid"] for r in races), "track": track, "gamedb": gamedb,
            "pinned": {n: [d for d in ROSTER if p[d]] for n, p in pins.items()},
            "dropped": [{"launch": r["launch"], "race": r["race"], "uid": r["uid"], "verdict": r["verdict"],
                         "reasons": r["reasons"]} for r in races if not r["valid"]],
            "constants": {"MOVE_M": vc.MOVE_M, "SPEED_AT_S": vc.SPEED_AT_S, "T1_M": vc.T1_M,
                          "THRESHOLD_S": THRESHOLD_S, "N_LAUNCHES": N_LAUNCHES}}
    write_outputs(out, launch_data, pins, res, meta)
    head = [f"D1 check {batch}: {len(complete)} launch(es), {meta['races_valid']}/{len(races)} races valid"]
    for ln in report(res, head):
        say(pre(ln))
    say(pre(f"wrote {out / 'summary.json'}, per_car_launch.csv"))
    return 0


# ==================================================================================================== selftest

def synth_tables(pins: dict[int, dict[str, int]], plant: float, rng_seed: int = 5, races: int = 4) -> dict:
    """Measure tables injected below the parsing layer: a driver effect, race noise, plant = pinned reaction offset."""
    rng = random.Random(rng_seed)
    base = {d: rng.uniform(0.38, 0.52) for d in ROSTER}
    data = {}
    for n, pin in pins.items():
        rs = []
        for k in range(races):
            drivers = {}
            for d in ROSTER:
                rt = base[d] + rng.gauss(0, 0.03) + plant * pin[d]
                drivers[d] = {"reaction_s": rt, "speed_1s_kph": 40 - 30 * rt + rng.gauss(0, 1),
                              "gain_t1": rng.choice((-1, 0, 0, 1))}
            rs.append({"launch": n, "race": k + 1, "uid": f"{n}{k}", "valid": True, "verdict": "PASS",
                       "reasons": [], "drivers": drivers})
        data[n] = {"launch": n, "races": rs, "grids": []}
    return data


def write_synth_batch(batch: Path, seed: int, launches: list[int], plant_s: float, rng_seed: int = 3) -> None:
    """On-disk D1 batch: launch_<n>/gen (d1_make.write_launch), arm.txt, raw/udp.bin with 4 races in udp_parse's
    layouts (v1_check.write_synth_capture), pinned cars reacting plant_s later."""
    rng = random.Random(rng_seed)
    base_rt = {d: rng.choice(range(22, 32)) for d in ROSTER}        # frames (1/60 s)
    accel = {d: rng.uniform(9.0, 11.0) for d in ROSTER}
    for n in launches:
        ld = batch / f"launch_{n}"
        dm.write_launch(seed, n, ld / "gen")
        (ld / "arm.txt").write_text(f"D1 seed {seed} launch {n}, add-on {dm.addon_id(n)}, plan\n", encoding="utf-8")
        pin = dm.draw(seed, n)
        order = ROSTER[:]
        rng.shuffle(order)
        react = {d: [(base_rt[d] + round(plant_s * 60) * pin[d] + rng.choice((-2, -1, 0, 1, 2))) / 60
                     for _ in range(vc.RACES_PER_LAUNCH)] for d in ROSTER}
        vc.write_synth_capture(ld / "raw" / "udp.bin", order, react, accel, uid0=1000 * n)


def selftest() -> int:
    results, ok = [], True

    def chk(name: str, cond: bool, detail: str = "") -> None:
        nonlocal ok
        ok &= bool(cond)
        results.append(f"{'ok  ' if cond else 'FAIL'} {name}" + (f": {detail}" if detail else ""))

    seed = 20261117
    pins = {n: dm.draw(seed, n) for n in (1, 2)}
    # ---- 1. measure tables injected below the parsing layer
    for plant, want in ((0.30, "PASS"), (0.05, "FAIL"), (0.0, "FAIL")):
        r = score(synth_tables(pins, plant), pins)
        d = [fnum(r["per_launch"][n]["primary"]["diff"]) for n in (1, 2)]
        chk(f"tables: planted +{plant:.2f} s on the pinned cars -> {want}", r["verdict"] == want, f"diffs {d}")
    r = score(synth_tables(pins, 0.30), pins)
    chk("tables: secondaries are computed and not scored (speed at 1 s lower for pinned cars)",
        r["secondary_mean_over_launches"]["speed_1s_kph"] < 0 and r["verdict"] == "PASS")
    one = {1: pins[1]}
    chk("tables: one launch -> NOT SCORED", score(synth_tables(one, 0.30), one)["verdict"] == "NOT SCORED")
    chk("tables: one launch with --allow-partial -> NOT SCORED (partial)",
        score(synth_tables(one, 0.30), one, partial=True)["verdict"] == PARTIAL)
    t = synth_tables(pins, 0.30)
    for d in ROSTER:
        if pins[1][d]:
            for rr in t[1]["races"]:
                rr["drivers"][d]["reaction_s"] -= 0.25       # launch 1 only: +0.05 left
    chk("tables: PASS needs BOTH launches (one at +0.05 -> FAIL)", score(t, pins)["verdict"] == "FAIL",
        score(t, pins)["why"])
    t = synth_tables(pins, 0.30)
    for rr in t[2]["races"]:
        rr["valid"] = False
    chk("tables: a launch with no valid race -> NOT SCORED", score(t, pins)["verdict"] == "NOT SCORED")
    # a car's mean over its races first: 4 copies of one car's race don't outweigh the others
    t = synth_tables(pins, 0.30, races=1)
    t4 = {n: {**L, "races": L["races"] * 4} for n, L in t.items()}
    chk("tables: the car is the unit (4 copies of a race give the same difference)", all(
        abs(score(t, pins)["per_launch"][n]["primary"]["diff"] - score(t4, pins)["per_launch"][n]["primary"]["diff"])
        < 1e-12 for n in (1, 2)))
    hand = {1: {"launch": 1, "races": [
        {"valid": True, "drivers": {"oscar_piastri": {"reaction_s": 1.0}, "lando_norris": {"reaction_s": 0.2}}},
        {"valid": True, "drivers": {"oscar_piastri": {"reaction_s": 0.8}}},
        {"valid": False, "drivers": {"lando_norris": {"reaction_s": 9.0}}}]}}
    hp = {1: {d: int(d == "oscar_piastri") for d in ROSTER}}
    hd = launch_diff(hand[1], hp[1], PRIMARY)
    chk("tables: by hand, pinned car mean 0.9 - stock 0.2 = 0.7 (the invalid race ignored)",
        abs(hd["diff"] - 0.7) < 1e-12 and hd["n_pinned"] == 1 and hd["n_stock"] == 1, str(hd["diff"]))

    # ---- 2. synthetic UDP through the whole tool (v1_check's parsing and start_measures), validity stubbed
    saved = vc._VALIDITY_OVERRIDE
    vc._VALIDITY_OVERRIDE = lambda ld, uid: ("PASS", [])   # noqa: E731
    try:
        with tempfile.TemporaryDirectory() as tmp:
            for plant, want in ((0.30, "PASS"), (0.05, "FAIL")):
                batch = Path(tmp) / f"b{int(plant * 100)}"
                write_synth_batch(batch, seed, [1, 2], plant)
                buf = io.StringIO()
                with redirect_stdout(buf):
                    rc = run(batch, None, None, vc.TRACK_AUSTRIA, False)
                js = json.loads((batch / "d1_check" / "summary.json").read_text(encoding="utf-8"))
                d = [fnum(js["per_launch"][str(n)]["primary"]["diff"]) for n in (1, 2)]
                chk(f"end to end: planted +{plant:.2f} s ({round(plant * 60)} frames) -> {want}, 8/8 races valid",
                    rc == 0 and js["verdict"] == want and js["races_valid"] == 8
                    and f"D1 primary: {want}" in buf.getvalue(), f"rc {rc}, diffs {d}")
                if want == "PASS":
                    rows = list(csv.DictReader((batch / "d1_check" / "per_car_launch.csv").open(encoding="utf-8")))
                    chk("end to end: per_car_launch.csv has 2 x 19 cars, 4 races each, 9 pinned per launch",
                        len(rows) == 38 and all(r["reaction_s_races"] == "4" for r in rows)
                        and all(sum(int(r["pinned"]) for r in rows if r["launch"] == str(n)) == 9 for n in (1, 2)))
                    chk("end to end: speed at 1 s is lower for the pinned cars (secondary)",
                        js["secondary_mean_over_launches"]["speed_1s_kph"] < 0,
                        fnum(js["secondary_mean_over_launches"]["speed_1s_kph"], 2))
                    pb = batch
            # one launch only: refused without --allow-partial, NOT SCORED (partial) with it
            part = Path(tmp) / "partial"
            write_synth_batch(part, seed, [1], 0.30)
            buf = io.StringIO()
            with redirect_stdout(buf):
                rc3 = run(part, None, None, vc.TRACK_AUSTRIA, False)
            chk("end to end: one launch -> NOT SCORED, refused (exit 3)", rc3 == 3 and
                buf.getvalue().startswith("NOT SCORED"))
            buf = io.StringIO()
            with redirect_stdout(buf):
                rcp = run(part, None, None, vc.TRACK_AUSTRIA, True)
            lines = [ln for ln in buf.getvalue().splitlines() if ln.strip()]
            pj = json.loads((part / "d1_check" / "summary.json").read_text(encoding="utf-8"))
            chk("end to end: one launch with --allow-partial -> NOT SCORED (partial) on every line",
                rcp == 0 and pj["verdict"] == PARTIAL and lines and all(PARTIAL in ln for ln in lines))
            # the session check's invalid.txt drops the launch
            (pb / "launch_2" / "invalid.txt").write_text("invalid: difficulty 99 (session check)\n", encoding="utf-8")
            with redirect_stdout(io.StringIO()):
                run(pb, None, None, vc.TRACK_AUSTRIA, False)
            js = json.loads((pb / "d1_check" / "summary.json").read_text(encoding="utf-8"))
            chk("end to end: invalid.txt drops the launch's races -> NOT SCORED", js["verdict"] == "NOT SCORED"
                and js["races_valid"] == 4, js["why"])
            (pb / "launch_2" / "invalid.txt").unlink()
            # assignment guards
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
            (pb / "launch_1" / "gen" / "assignment.csv").write_text(a1, encoding="utf-8")
            (pb / "launch_1" / "arm.txt").write_text("V-1 seed 1 launch 1, add-on verve.v1-l01\n", encoding="utf-8")
            buf = io.StringIO()
            with redirect_stdout(buf):
                rcv = run(pb, None, None, vc.TRACK_AUSTRIA, False)
            chk("a V-1 arm.txt is refused", rcv == 3 and "not a D1 launch" in buf.getvalue())
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
