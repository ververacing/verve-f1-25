"""S-1 screen of six per-driver ai_driver_config keys: the analysis, the stock baseline's bands and the extremes smoke
(docs/verve_s1_prereg.md, APPROVED 2026-11-17, with the supervisor's final rulings). Offline: reads finished batches.

Usage:
    python -I tools/s1_check.py runs/<batch> [--seed <S>] [--allow-partial] [--gamedb <N>] [--perms 10000]
    python -I tools/s1_check.py runs/<baseline batch> --baseline     # the stock baseline -> PROPOSED bands
    python -I tools/s1_check.py runs/<smoke batch> --smoke           # the extremes validity smoke
    python -I tools/s1_check.py runs/<batch> --stalls                # validity only, during a batch: stalls per race
    python -I tools/s1_check.py --selftest

Batch layout (tools/v1_run.ps1 -Make s1): <batch>/launch_<n>/gen/{assignment.csv, levels.json} (tools/s1_make.py),
raw/udp.bin (all the launch's restart-races, one race-session uid each), weather.txt, raw/loader.log,
check_applied.txt, gamedb_expected.txt, session_check.txt, transcript.txt (the saves guard), profile_hashes.txt
(tyler.json) and arm.txt ("S1 seed <S> launch <n>, ..."). The stock baseline (v1_run -StockSmoke on the V-1 4-race
plan) has no gen/ and arm.txt "SMOKE stock (no add-on) ...".

DEFAULT (the screen; prereg sections 2 and 5): 16 launches x 4 races, the launch is the block. v1_check's engine, by
import: its per-race measures (process_launch), the driver-fixed-effects launch tables (launch_tables), the centred
(HIGH - LOW) statistic (Stat), the FE slope (fe_slope) and the permutation seeds (perm_seeds); the redraws use
s1_make.draw(seed_k, launch) for every launch, 10,000 of them, two-sided p. One primary per factor:
    YIELD contacts (+), EXIT_ERR exit_all_kph (-), OVERLAP passes_made (+), BLK_SPEED held_behind_s (two-sided),
    BLK_THREAT held_behind_s (two-sided), COMMIT passes_made (+).
Labels: p from the centred statistic, the band comparison on the FE slope. ALIVE (p < 0.05, the predicted direction,
FE slope outside the band), ALIVE-SMALL (p < 0.05, FE slope inside the band), ALIVE-REVERSED (p < 0.05, the opposite
direction, outside the band), DEAD (FE slope +/- 2 SE(FE) inside the band), else INCONCLUSIVE. The two-sided factors
take ALIVE with either sign (the sign is reported) and have no ALIVE-REVERSED. No multiple-testing correction (a
screen). The bands come from the COMMITTED bands file docs/stock/s1_bands.json (the bands amendment): REFUSED if it is
missing or malformed. Secondaries (estimate, SE, p; never a decision) as the prereg's table, plus gain_t1, gain_lap1,
laptime_sd_s and penalties (PENA per car, any code) for every factor.
Validity per race: aionly_check per uid and the build check (v1_check), plus per launch: invalid.txt (the session
check), check_applied's op count and tyler.json (CHANGED / NOT RESTORED). A tripped saves guard (SAVES CHANGED in
transcript.txt) is a NOTE, not an invalidation (the supervisor's ruling on #182, as V-1's launch 7 stood): it is a
safety stop in the runner (v1_run exits 5 and the batch halts), printed per launch and recorded in summary.json, and
the launch's races stay in the analysis (and in --baseline). The smoke's rule 4 still names the saves guard.
STALLS (reported, not invalidating): an AI car with < 1 m of LapData totalDistance gain in any 30 s window while not
in the pit lane (pitStatus 0), from lights out to its own or the leader's finish, whichever is earlier; an AI car whose
final LapData resultStatus isn't 3 (finished) also counts. More than one stalled race in a launch prints STOP (the
batch stops for the supervisor). Beside every primary, a SENSITIVITY line (not scored): the same statistic,
permutation test and label without the races that had a stalled car. The decision stays the primary's.
No interim looks: exit 3 unless the batch has 16 complete launches; --allow-partial prints NOT SCORED on every line.

--baseline (prereg section 3): 2 stock launches x 4 races, no add-on; >= 6 of the 8 races valid, else REFUSED (rerun
the short launch once). Over the valid races and the 19 AI cars (NA excluded): M_p (passes_made), M_h (held_behind_s),
M_c (contacts), the exit_all_kph mean, and C_race (the mean per race of all COLL events, race_feel's
guards.collisions). Bands, 3 significant figures: contacts max(0.15, 0.25 M_c); exit_all_kph 2.0 (always the floor,
the supervisor's ruling); passes_made 0.25 M_p (no floor); held_behind_s max(25, 0.25 M_h). Writes the PROPOSED file
<batch>/s1_bands_proposed.json (the bands file's format) and prints it. It never writes docs/.

--smoke (prereg section 4; validity only, never effects): launch_1 of the smoke batch (s1_make --smoke, seed
2026111707, 2 races). PASS needs, in both races: 1. aionly_check PASS; 2. no stalled or unfinished AI car; 3. the
race's COLL events <= 3 x C_race (from the bands file); 4. the session check, weather LOCKED, the build check and the
saves / tyler.json guards. A rule-4 failure is a harness failure: rerun the smoke once with the same seed, no stepping.
On a FAIL of 1-3 it names the levels to step (the supervisor's rulings): a stall or an unfinished car implicates every
factor at the level that car held; excess contacts implicate each factor's predicted CONTACT-RAISING extreme, named
by value: YIELD 0.5, OVERLAP flat 0.05, COMMIT 0.1, BOTH blocking extremes (BLK_SPEED 0.15 and 2.4, BLK_THREAT 0.7
and 0.04375), and never EXIT_ERR. Each step halves the distance to stock (s1_make's steps; at most 2, then stock; both
levels at stock drops the factor). Writes <batch>/s1_smoke/{summary.json, levels_next.json} (s1_make --levels).

Exit 0 done (scored, PASS, or --allow-partial), 1 SMOKE FAIL (--smoke) or STOP (--stalls), 2 usage, 3 refused.
"""
from __future__ import annotations

import csv
import io
import json
import math
import random
import re
import shutil
import statistics
import sys
import tempfile
import time
from collections import defaultdict
from contextlib import redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import c1_check as cc  # noqa: E402
import race_feel as rf  # noqa: E402
import s1_make as sm  # noqa: E402
import udp_parse as u  # noqa: E402
import v1_check as vc  # noqa: E402

REPO = Path(__file__).resolve().parent.parent
BANDS_FILE = REPO / "docs" / "stock" / "s1_bands.json"   # the committed bands (the bands amendment PR)
N_LAUNCHES = 16
RACES_PER_LAUNCH = 4
BASELINE_LAUNCHES = 2
BASELINE_MIN_VALID = 6       # of 8
SMOKE_RACES = 2
N_PERMS = 10_000
ALPHA = 0.05
TRACK = vc.TRACK_AUSTRIA
FACTORS = sm.FACTORS
SIDES = sm.SIDES
ROSTER = sm.ROSTER
PARTIAL = "NOT SCORED (partial)"

STALL_WINDOW_S = 30.0
STALL_MIN_M = 1.0
CONTACT_MULT = 3.0

EXTRA = {"costly_contacts": ("/race", False, "race_feel costly_contacts (contacts with a wing hit, a spin or places lost)"),
         "front_wing_added": ("/race", False, "race_feel front_wing_added (front-wing damage added, CarDamage)"),
         "penalties": ("/race", False, "PENA events for the car, any code (descriptive only, prereg section 6)")}
MEASURES = {**vc.MEASURES, **EXTRA}
# factor -> (primary, predicted sign of HIGH - LOW; 0 = two-sided)
PRIMARY = {"YIELD": ("contacts", +1), "EXIT_ERR": ("exit_all_kph", -1), "OVERLAP": ("passes_made", +1),
           "BLK_SPEED": ("held_behind_s", 0), "BLK_THREAT": ("held_behind_s", 0), "COMMIT": ("passes_made", +1)}
HYPOTHESIS = {"BLK_SPEED": "+", "BLK_THREAT": "+"}
SECONDARY = {"YIELD": ["passes_suffered", "held_behind_s", "costly_contacts", "front_wing_added"],
             "EXIT_ERR": ["laptime_sd_s", "offtracks_spins", "offtracks", "spins", "entry_all_kph", "contacts"],
             "OVERLAP": ["contacts", "costly_contacts", "gain_lap1", "passes_suffered"],
             "BLK_SPEED": ["passes_suffered", "contacts", "passes_made"],
             "BLK_THREAT": ["passes_suffered", "contacts", "passes_made"],
             "COMMIT": ["contacts", "costly_contacts", "gain_lap1"]}
COMMON_SECONDARY = ["gain_t1", "gain_lap1", "laptime_sd_s", "penalties"]
BAND_MEASURES = ("contacts", "exit_all_kph", "passes_made", "held_behind_s")
FLOORS = {"contacts": 0.15, "exit_all_kph": 2.0, "held_behind_s": 25.0}      # passes_made: no floor ruled
BAND_SHARE = 0.25
# the predicted contact-raising extreme per factor, BY VALUE (prereg section 4's table; the supervisor's ruling). The
# side (HIGH/LOW) is looked up in s1_make.LEVELS, so a relabelling there can't move the stepped value.
CONTACT_RAISING = {"YIELD": ("0.5",), "OVERLAP": (sm.LEVELS["OVERLAP"]["HIGH"],), "COMMIT": ("0.1",),
                   "BLK_SPEED": ("0.15", "2.4"), "BLK_THREAT": ("0.7", "0.04375"), "EXIT_ERR": ()}


def contact_sides(f: str) -> list[str]:
    return [s for s in SIDES if sm.LEVELS[f][s] in CONTACT_RAISING[f]]


def secondaries(f: str) -> list[str]:
    return list(dict.fromkeys(m for m in SECONDARY[f] + COMMON_SECONDARY if m != PRIMARY[f][0]))


def fnum(x, nd=4):
    return "NA" if x is None else (f"{x:.{nd}f}" if isinstance(x, float) else str(x))


def sig3(x: float) -> float:
    return float(f"{x:.3g}")


# ==================================================================================================== stalls

def lgot_time(s: dict) -> float | None:
    return next((st for st, _, code, _ in s["events"] if code == "LGOT"), None)


def coll_total(s: dict) -> int:
    """All COLL events of the race session (race_feel's guards.collisions)."""
    return sum(1 for _, _, code, f in s["events"] if code == "COLL" and "vehicle" in f)


def find_stalls(s: dict, cars: list[int]) -> list[dict]:
    """Stalled AI cars (prereg section 4, rule 2): < STALL_MIN_M of totalDistance gain over any STALL_WINDOW_S window
    with pitStatus 0 throughout, from lights out to the car's own finish or the leader's, whichever is earlier; and
    cars whose last LapData resultStatus isn't 3. [{"car", "kind": "stall" | "not finished", ...}]"""
    frames = s["lap_frames"]
    lg = lgot_time(s)
    if lg is None or not frames:
        return []
    n = s["n_active"] or s.get("cars", u.CARS)
    fin = rf.finish_times(frames, n)
    leader = min(fin.values()) if fin else frames[-1][0]
    out = []
    for c in cars:
        end = min(fin.get(c, math.inf), leader)
        pts = [(t, cs[c][u.L_TOTDIST], cs[c][u.L_PIT]) for t, cs in frames if lg <= t <= end]
        nxt_pit, k = [0] * (len(pts) + 1), len(pts)
        nxt_pit[k] = k
        for i in range(len(pts) - 1, -1, -1):
            nxt_pit[i] = i if pts[i][2] else nxt_pit[i + 1]
        j = 0
        for i in range(len(pts)):
            j = max(j, i)
            while j < len(pts) and pts[j][0] - pts[i][0] < STALL_WINDOW_S:
                j += 1
            if j >= len(pts):
                break
            if nxt_pit[i] > j and pts[j][1] - pts[i][1] < STALL_MIN_M:
                out.append({"car": c, "kind": "stall", "t_after_lights_out_s": round(pts[i][0] - lg, 1),
                            "gain_m": round(pts[j][1] - pts[i][1], 3)})
                break
        st = frames[-1][1][c][u.L_RSTATUS]
        if st != rf.FINISHED:
            out.append({"car": c, "kind": "not finished", "result_status": st})
    return out


def stall_text(st: list[dict]) -> str:
    return ", ".join(f"{x.get('driver', 'car %d' % x['car'])} ({x['kind']}"
                     + (f" at {x['t_after_lights_out_s']} s" if x["kind"] == "stall" else
                        f", resultStatus {x['result_status']}") + ")" for x in st)


def race_hook(race: dict, s: dict, cmap: dict[int, str], rows_rf: list[dict] | None) -> None:
    """v1_check.process_launch's hook: the race's COLL total and stalls (every race), and the extra race_feel measures
    (valid races)."""
    n = s["n_active"] or s.get("cars", u.CARS)
    player = s.get("player")
    race["coll_total"] = coll_total(s)
    race["stalls"] = [{**x, "driver": cmap.get(x["car"], f"car {x['car']}")}
                      for x in find_stalls(s, [c for c in range(n) if c != player])]
    if rows_rf:
        by = {r["car"]: r for r in rows_rf}
        for v in race["drivers"].values():
            r = by.get(v.get("car"), {})
            for m in EXTRA:
                x = r.get(m)
                v[m] = x if isinstance(x, (int, float)) and not isinstance(x, bool) else None


def stall_summary(launch_data: dict[int, dict]) -> tuple[list[str], list[int]]:
    """(lines, launches that stop the batch: more than one stalled race)."""
    lines, stop = [], []
    for n, L in sorted(launch_data.items()):
        bad = [r for r in L["races"] if r.get("stalls")]
        for r in bad:
            lines.append(f"  stalled: launch {n} race {r['race']} (uid {r['uid']}, {r['verdict']}): {stall_text(r['stalls'])}")
        if len(bad) > 1:
            stop.append(n)
    if not lines:
        lines.append("  stalls: none (no AI car stalled or unfinished in any race)")
    for n in stop:
        lines.append(f"STOP: launch {n} had {sum(1 for r in launch_data[n]['races'] if r.get('stalls'))} races with a "
                     f"stalled car (more than 1): the batch stops for the supervisor")
    return lines, stop


# ==================================================================================================== bands

def load_bands(path: Path | None = None) -> tuple[dict | None, str]:
    """(the bands file, '') or (None, why). The committed file: the four bands, the floors held, C_race."""
    path = path or BANDS_FILE
    if not path.exists():
        return None, f"no bands file {path} (the bands amendment commits it before S-1 launch 1)"
    try:
        js = json.loads(path.read_text(encoding="utf-8-sig"))
        b, st = js["bands"], js["stats"]
        vals = {m: float(b[m]) for m in BAND_MEASURES}
        c_race = float(st["C_race"])
    except (ValueError, KeyError, TypeError) as e:
        return None, f"bands file {path} is malformed ({e!r})"
    bad = [m for m, v in vals.items() if not v > 0 or v < FLOORS.get(m, 0)]
    if bad or vals["exit_all_kph"] != FLOORS["exit_all_kph"] or not c_race > 0:
        return None, f"bands file {path} breaks the rule (floors, exit 2.0, C_race > 0): {bad or vals}"
    return {"bands": vals, "C_race": c_race, "stats": st, "path": str(path)}, ""


def baseline_stats(launch_data: dict[int, dict]) -> dict:
    races = [r for L in launch_data.values() for r in L["races"]]
    valid = [r for r in races if r["valid"]]

    def mean_of(m):
        x = [v[m] for r in valid for v in r["drivers"].values() if v.get(m) is not None]
        return (statistics.fmean(x) if x else None), len(x)
    out = {"races_total": len(races), "races_valid": len(valid)}
    for key, m in (("M_p", "passes_made"), ("M_h", "held_behind_s"), ("M_c", "contacts"), ("exit_mean", "exit_all_kph")):
        out[key], out[f"n_{m}"] = mean_of(m)
    colls = [r["coll_total"] for r in valid if r.get("coll_total") is not None]
    out["C_race"] = statistics.fmean(colls) if colls else None
    return out


def bands_from(st: dict) -> dict:
    """The prereg's rule (section 3) with the supervisor's: exit always its floor. 3 significant figures."""
    return {"contacts": sig3(max(FLOORS["contacts"], BAND_SHARE * st["M_c"])),
            "exit_all_kph": FLOORS["exit_all_kph"],
            "passes_made": sig3(BAND_SHARE * st["M_p"]),
            "held_behind_s": sig3(max(FLOORS["held_behind_s"], BAND_SHARE * st["M_h"]))}


# ==================================================================================================== launch guards

def build_problems(ld: Path, n_ops: int) -> list[str]:
    """The per-launch build check (c1_check's, with check_applied's own accounting): check_applied.txt with this
    launch's op count, every op applied or dropped as equal to stock (S-1 writes none equal to stock), 0 problems, no
    DIFFERS, and the loader's gamedb count = gamedb_expected.txt."""
    t = cc.text_of(ld / "check_applied.txt")
    if not t:
        return ["build: no check_applied.txt (the build check never ran)"]
    probs = []
    if not re.search(r"(?<!\d)0 problem\(s\)", t) or "DIFFERS" in t:
        probs.append("build: check_applied.txt found problems")
    m = re.search(r"ops (\d+): (\d+) applied.*?(\d+) dropped as equal to stock", t)
    if not m or int(m[1]) != n_ops or int(m[2]) + int(m[3]) != n_ops:
        probs.append(f"build: check_applied.txt reads {m[0][:60] if m else 'no ops line'!r}, expected {n_ops} ops "
                     f"accounted for")
    want = _int_in(ld / "gamedb_expected.txt")
    db = re.search(r"gamedb: (\d+) overwritten", cc.text_of(ld / "raw" / "loader.log"))
    if want is None or not db or int(db[1]) != want:
        probs.append(f"build: loader.log gamedb {db[1] if db else 'none'} overwritten, gamedb_expected.txt {want}")
    return probs


def launch_guard_problems(ld: Path, n_ops: int) -> list[str]:
    """Per-launch validity beyond v1_check's (prereg section 2): the session check's mark, the build check's op count,
    tyler.json. The saves guard is NOT here: it is a note (saves_note), not a validity rule."""
    probs = []
    inv = ld / "invalid.txt"
    if inv.exists():
        probs.append(f"INVALID: the launch is marked invalid.txt ({(cc.text_of(inv).strip().splitlines() or ['?'])[0]})")
    probs += [f"INVALID: {p}" for p in build_problems(ld, n_ops)]
    ph = cc.text_of(ld / "profile_hashes.txt")
    if re.search(r"tyler\.json: (NOT RESTORED|CHANGED)", ph):
        probs.append("INVALID: tyler.json changed (profile_hashes.txt)")
    return probs


def saves_note(n: int, ld: Path) -> str | None:
    """The supervisor's ruling on #182: a tripped saves guard is a safety stop, not a validity rule."""
    if "SAVES CHANGED" in cc.text_of(ld / "transcript.txt"):
        return (f"NOTE: saves guard tripped (SAVES CHANGED) in launch {n}: a safety stop, not a validity rule; reviewed "
                f"by the supervisor (its races stay in the analysis)")
    return None


def tyler_ok(ld: Path) -> bool:
    return bool(re.search(r"tyler\.json: (restored|unchanged)", cc.text_of(ld / "profile_hashes.txt")))


def n_ops_of(ld: Path) -> int:
    p = ld / "gen" / "expected_ops.csv"
    if not p.exists():
        return 0
    with p.open(encoding="utf-8", newline="") as fh:
        return sum(1 for _ in csv.DictReader(fh))


def mark_launch(L: dict, probs: list[str]) -> None:
    for r in L["races"]:
        if probs:
            r["valid"], r["verdict"], r["reasons"] = False, "INVALID", r["reasons"] + probs


# ==================================================================================================== the analysis

def ones(assign: dict, factors: list[str]) -> dict[str, tuple]:
    return {f: tuple(i for i, d in enumerate(ROSTER) if assign[d][f]) for f in factors}


def decide(p, est, fe, se_fe, band, sign) -> str:
    if p is None or fe is None or se_fe is None or est is None:
        return "NO DATA"
    if p < ALPHA:
        if abs(fe) <= band:
            return "ALIVE-SMALL"
        if sign == 0:
            return "ALIVE"
        return "ALIVE" if (est > 0) == (sign > 0) else "ALIVE-REVERSED"
    if fe - 2 * se_fe >= -band and fe + 2 * se_fe <= band:
        return "DEAD"
    return "INCONCLUSIVE"


def analyse(launch_data: dict[int, dict], assigns: dict[int, dict], seed: int, bands: dict, perms: int = N_PERMS,
            factors: list[str] | None = None, with_secondary: bool = True, draw=None) -> dict:
    """The per-factor tests, with v1_check's engine. assigns[L] = s1_make.draw(seed, L). Pure in its inputs."""
    draw = draw or sm.draw
    factors = list(factors or FACTORS)
    launches = sorted(launch_data)
    tables = vc.launch_tables(launch_data, MEASURES)
    prim = [(f, PRIMARY[f][0]) for f in factors]
    pairs = prim + ([(f, m) for f in factors for m in secondaries(f)] if with_secondary else [])
    stats = {m: vc.Stat(tables[m], launches) for m in {m for _, m in pairs}}
    real = {n: ones(assigns[n], factors) for n in launches}
    obs = {p: stats[p[1]]({n: real[n][p[0]] for n in launches}) for p in pairs}
    live = [p for p in pairs if obs[p] is not None]
    null = {p: [] for p in live}
    null_fe = {p: [] for p in prim}
    t0 = time.perf_counter()
    for sk in vc.perm_seeds(seed, perms):
        drawn = {n: draw(sk, n) for n in launches}
        idx = {n: ones(drawn[n], factors) for n in launches}
        for f, m in live:
            v = stats[m]({n: idx[n][f] for n in launches})
            if v is not None:
                null[(f, m)].append(v)
        for f, m in prim:
            v = vc.fe_slope(tables[m], drawn, f)
            if v is not None:
                null_fe[(f, m)].append(v)
    perm_s = time.perf_counter() - t0

    def test(f, m):
        t = obs[(f, m)]
        raw = [v.get(m) for L in launch_data.values() for r in L["races"] if r["valid"] for v in r["drivers"].values()
               if v.get(m) is not None]
        res = {"measure": m, "unit": MEASURES[m][0], "estimate": t, "n_values": len(raw),
               "races_valid": sum(1 for L in launch_data.values() for r in L["races"] if r["valid"]),
               "constant": len(set(raw)) <= 1 if raw else None}
        nl = null.get((f, m), [])
        if t is None or not nl:
            return {**res, "se": None, "p": None, "null_n": len(nl)}
        hits = sum(1 for x in nl if abs(x) >= abs(t) - 1e-12)
        return {**res, "se": statistics.pstdev(nl), "p": (1 + hits) / (1 + len(nl)), "null_n": len(nl)}

    out = {}
    for f in factors:
        m, sign = PRIMARY[f]
        r = test(f, m)
        nf = null_fe[(f, m)]
        fe = vc.fe_slope(tables[m], assigns, f)
        se_fe = statistics.pstdev(nf) if len(nf) > 1 else None
        band = bands[m]
        r.update(predicted="+/-" if sign == 0 else ("+" if sign > 0 else "-"), two_sided=sign == 0,
                 hypothesis=HYPOTHESIS.get(f), null_band=band, fe_slope=fe, se_fe=se_fe,
                 decision=decide(r["p"], r["estimate"], fe, se_fe, band, sign))
        if r["decision"] == "ALIVE" and sign == 0:
            r["sign"] = "+" if r["estimate"] > 0 else "-"
        if with_secondary:
            r["secondary"] = {sm2: test(f, sm2) for sm2 in secondaries(f)}
        out[f] = r
    return {"factors": out, "perms": perms, "perm_runtime_s": round(perm_s, 2), "launches": launches, "tables": tables}


def without_stalled(launch_data: dict[int, dict]) -> tuple[dict, int]:
    """The batch with every race that had a stalled car set aside (valid False), and how many valid races that was."""
    out, k = {}, 0
    for n, L in launch_data.items():
        races = []
        for r in L["races"]:
            if r["valid"] and r.get("stalls"):
                k += 1
                r = {**r, "valid": False}
            races.append(r)
        out[n] = {**L, "races": races}
    return out, k


def report(res: dict, sens: dict, n_sens: int, dropped_f: list[str], head: list[str], partial: bool) -> list[str]:
    lines = list(head)
    lines.append(f"{'factor':<12}{'primary':<15}{'pred':>5}{'estimate':>10}{'SE':>9}{'p':>8}{'FE slope':>10}"
                 f"{'SE(FE)':>9}  {'band (FE slope)':<22}decision")
    for f in FACTORS:
        if f in dropped_f:
            lines.append(f"{f:<12}{PRIMARY[f][0]:<15}  DROPPED (both levels at stock after the smoke's stepping; "
                         f"recorded in levels.json)")
            continue
        r = res["factors"][f]
        dec = PARTIAL if partial else r["decision"] + (f" ({r['sign']})" if r.get("sign") else "")
        pred = r["predicted"]
        band = f"+/-{fnum(r['null_band'], 3)} {r['unit']}"
        flag = " [measure constant]" if r["constant"] else ""
        lines.append(f"{f:<12}{r['measure']:<15}{pred:>5}{fnum(r['estimate']):>10}{fnum(r['se']):>9}"
                     f"{fnum(r['p'], 4):>8}{fnum(r['fe_slope']):>10}{fnum(r['se_fe']):>9}  {band:<22}{dec}{flag}")
        s = sens["factors"][f]
        sdec = s["decision"] + (f" ({s['sign']})" if s.get("sign") else "")
        lines.append(f"  SENSITIVITY (not scored; without the {n_sens} race(s) with a stalled car, "
                     f"{s['races_valid']} races): estimate {fnum(s['estimate'])} SE {fnum(s['se'])} p {fnum(s['p'], 4)} "
                     f"FE {fnum(s['fe_slope'])} SE(FE) {fnum(s['se_fe'])} -> {sdec}")
    lines.append("two-sided (BLK_SPEED, BLK_THREAT; hypothesis +): ALIVE takes either sign, reported in brackets; no "
                 "ALIVE-REVERSED. No multiple-testing correction (a screen); any ALIVE is CONFIRMED in a focused "
                 "follow-up before a Verve Drivers release.")
    lines.append("secondaries (no decision): estimate / SE / p")
    for f in FACTORS:
        if f in dropped_f:
            continue
        lines.append(f"  {f:<12}" + "; ".join(f"{m} {fnum(x['estimate'], 3)}/{fnum(x['se'], 3)}/{fnum(x['p'], 3)}"
                                             for m, x in res["factors"][f]["secondary"].items()))
    return [f"{PARTIAL} | {ln}" for ln in lines] if partial else lines


def write_outputs(out: Path, launch_data: dict, assigns: dict, js: dict) -> None:
    out.mkdir(parents=True, exist_ok=True)
    mcols = list(MEASURES)
    with (out / "per_race.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["launch", "race", "session_uid", "valid", "verdict", "reasons", "coll_total", "stalls", "driver",
                    "team", "car", "grid", "side_odd"] + FACTORS + mcols)
        for n, L in sorted(launch_data.items()):
            for r in L["races"]:
                head = [n, r["race"], r["uid"], int(r["valid"]), r["verdict"], " | ".join(r["reasons"]),
                        r.get("coll_total"), stall_text(r.get("stalls") or [])]
                if not r["drivers"]:
                    w.writerow(head + [""] * (5 + len(FACTORS) + len(mcols)))
                for drv in ROSTER:
                    if drv in r["drivers"]:
                        v = r["drivers"][drv]
                        w.writerow(head + [drv, sm.TEAM_OF[drv], v.get("car"), v.get("grid"), v.get("side")] +
                                   [assigns[n][drv][x] for x in FACTORS] + [fnum(v.get(m), 6) for m in mcols])
    (out / "summary.json").write_text(json.dumps(js, indent=1, default=str) + "\n", encoding="utf-8")


# ==================================================================================================== batch helpers

def arm_seed(ld: Path) -> int | None:
    m = re.match(r"\s*S1 seed (-?\d+) launch", cc.text_of(ld / "arm.txt"))
    return int(m[1]) if m else None


def resolve_seed(arg: str | None, batch: Path, launches: dict[int, Path]) -> tuple[int | None, str]:
    found = {}
    for n, ld in launches.items():
        for src, val in (("arm.txt", arm_seed(ld)), ("seed.txt", _int_in(ld / "seed.txt")),
                         ("levels.json", _levels(ld).get("seed"))):
            if val is not None:
                found[f"launch_{n}/{src}"] = int(val)
    if _int_in(batch / "seed.txt") is not None:
        found["seed.txt"] = _int_in(batch / "seed.txt")
    vals = set(found.values())
    if arg is not None:
        if vals and vals != {int(arg)}:
            return None, f"--seed {arg} disagrees with {found}"
        return int(arg), ""
    if len(vals) == 1:
        return vals.pop(), ""
    return None, (f"the seeds disagree: {found}" if vals else "no --seed and no seed on record (arm.txt, seed.txt)")


def _int_in(p: Path) -> int | None:
    m = re.search(r"-?\d+", cc.text_of(p))
    return int(m[0]) if m else None


def _levels(ld: Path) -> dict:
    p = ld / "gen" / "levels.json"
    try:
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
    except ValueError:
        return {}


def steps_of(lv: dict) -> dict:
    return {f: {s: int(lv["factors"][f][s]["steps"]) for s in SIDES} for f in FACTORS}


# ==================================================================================================== default run

def run(batch: Path, gamedb: int | None, seed_arg: str | None, perms: int, allow_partial: bool,
        quiet: bool = False) -> int:
    say = (lambda *a: None) if quiet else print
    pre = (lambda s: f"{PARTIAL} | {s}") if allow_partial else (lambda s: s)
    launches = vc.find_launches(batch)
    complete = {n: ld for n, ld in launches.items() if not vc.launch_problems(ld)}
    full = set(complete) == set(range(1, N_LAUNCHES + 1)) and len(launches) == N_LAUNCHES
    if not full and not allow_partial:
        print(f"REFUSED: {len(complete)} complete launch(es) of {N_LAUNCHES} in {batch} (found {sorted(launches)}; "
              f"incomplete {[n for n in launches if n not in complete]}). No interim looks: run after launch "
              f"{N_LAUNCHES}, or --allow-partial (NOT SCORED).")
        return 3
    bands, why = load_bands()
    if bands is None:
        print(pre(f"REFUSED: {why}"))
        return 3
    if not complete:
        print(pre(f"no complete launch in {batch}"))
        return 3
    seed, why = resolve_seed(seed_arg, batch, complete)
    if seed is None:
        print(pre(f"REFUSED: {why}"))
        return 3
    levels = {n: _levels(ld) for n, ld in complete.items()}
    if any(not lv for lv in levels.values()):
        print(pre(f"REFUSED: no gen/levels.json in launch(es) {[n for n, lv in levels.items() if not lv]}"))
        return 3
    if any(lv.get("smoke") for lv in levels.values()):
        print(pre("REFUSED: a launch is the extremes smoke (levels.json smoke true); its data never enters S-1"))
        return 3
    st = {n: steps_of(lv) for n, lv in levels.items()}
    if len({json.dumps(v, sort_keys=True) for v in st.values()}) != 1:
        print(pre(f"REFUSED: the launches' levels differ (no level changes once any S-1 race has been seen): {st}"))
        return 3
    steps = next(iter(st.values()))
    dropped_f = sm.dropped(steps)
    active = [f for f in FACTORS if f not in dropped_f]
    assigns = {}
    for n, ld in complete.items():
        a = sm.read_assignment(ld / "gen" / "assignment.csv")
        if a != sm.draw(seed, n):
            print(pre(f"REFUSED: launch_{n}/gen/assignment.csv is not s1_make.draw({seed}, {n}): the permutation test "
                      f"needs the real randomisation"))
            return 3
        assigns[n] = a
    if gamedb is None and vc._VALIDITY_OVERRIDE is None and not all(
            (ld / "gamedb_expected.txt").exists() for ld in complete.values()):
        print(pre("REFUSED: --gamedb <N> is required unless every launch has v1_run's gamedb_expected.txt"))
        return 2
    out = batch / "s1_check"
    t0 = time.perf_counter()
    launch_data = {}
    for n, ld in complete.items():
        L = vc.process_launch(n, ld, gamedb, TRACK, out, log=lambda s: say(pre(s)), hook=race_hook)
        mark_launch(L, launch_guard_problems(ld, n_ops_of(ld)))
        launch_data[n] = L
    parse_s = time.perf_counter() - t0
    res = analyse(launch_data, assigns, seed, bands["bands"], perms, active)
    sdata, n_sens = without_stalled(launch_data)
    sens = analyse(sdata, assigns, seed, bands["bands"], perms, active, with_secondary=False)
    races = [r for L in launch_data.values() for r in L["races"]]
    valid = [r for r in races if r["valid"]]
    dropped = [r for r in races if not r["valid"]]
    stall_lines, stop = stall_summary(launch_data)
    odd = {n: len(L["races"]) for n, L in launch_data.items() if len(L["races"]) != RACES_PER_LAUNCH}
    untyler = [n for n, ld in complete.items() if not tyler_ok(ld)]
    snotes = {n: x for n, ld in complete.items() if (x := saves_note(n, ld))}
    head = [f"S-1 check {batch}: seed {seed}, {len(complete)} launches, {len(valid)}/{len(races)} races valid, "
            f"{perms} permutations with the launch as the block ({res['perm_runtime_s']} s; parsing {parse_s:.0f} s)",
            f"  bands: {bands['path']} " + ", ".join(f"{m} +/-{bands['bands'][m]:g}" for m in BAND_MEASURES)]
    head += [f"  dropped: launch {r['launch']} race {r['race']} (uid {r['uid']}): {r['verdict']}: "
             f"{'; '.join(r['reasons'])}" for r in dropped]
    if odd:
        head.append(f"  launches without {RACES_PER_LAUNCH} races: {odd}")
    head += list(snotes.values())
    if untyler:
        head.append(f"  note: tyler.json has no 'restored' line in profile_hashes.txt for launch(es) {untyler}")
    if steps != sm.no_steps():
        head.append(f"  stepped levels (levels.json): {levels[min(levels)]['stepped']}; dropped factors: "
                    f"{dropped_f or 'none'}")
    head += stall_lines
    lines = report(res, sens, n_sens, dropped_f, head, allow_partial)
    for ln in lines:
        say(ln)
    js = {"batch": str(batch), "seed": seed, "scored": full and not allow_partial, "launches": sorted(complete),
          "races_total": len(races), "races_valid": len(valid), "bands": bands, "perms": perms,
          "perm_runtime_s": res["perm_runtime_s"], "parse_runtime_s": round(parse_s, 1), "levels": levels[min(levels)],
          "dropped_factors": dropped_f, "factors": res["factors"],
          "sensitivity": {"races_set_aside": n_sens, "factors": sens["factors"], "scored": False},
          "stalls": [{"launch": r["launch"], "race": r["race"], "uid": r["uid"], "stalls": r["stalls"]}
                     for r in races if r.get("stalls")], "stop_launches": stop,
          "saves_notes": {str(n): x for n, x in snotes.items()},
          "dropped": [{"launch": r["launch"], "race": r["race"], "uid": r["uid"], "verdict": r["verdict"],
                       "reasons": r["reasons"]} for r in dropped], "report": lines}
    write_outputs(out, launch_data, assigns, js)
    say(pre(f"wrote {out / 'summary.json'}, per_race.csv"))
    return 0


# ==================================================================================================== --baseline

def is_stock_launch(ld: Path) -> bool:
    return cc.text_of(ld / "arm.txt").lstrip().startswith("SMOKE stock") and not (ld / "gen").exists()


def run_baseline(batch: Path, gamedb: int | None, quiet: bool = False) -> int:
    say = (lambda *a: None) if quiet else print
    launches = {n: ld for n, ld in vc.find_launches(batch).items() if (ld / "raw" / "udp.bin").exists()}
    if sorted(launches) != list(range(1, BASELINE_LAUNCHES + 1)):
        print(f"REFUSED: the stock baseline is {BASELINE_LAUNCHES} launches with a capture (launch_1, launch_2); "
              f"found {sorted(launches)} in {batch}")
        return 3
    notstock = [n for n, ld in launches.items() if not is_stock_launch(ld)]
    if notstock:
        print(f"REFUSED: launch(es) {notstock} aren't stock (arm.txt 'SMOKE stock (no add-on)', no gen/): the baseline "
              f"runs with no add-on (v1_run -StockSmoke)")
        return 3
    if gamedb is None and vc._VALIDITY_OVERRIDE is None and not all(
            (ld / "gamedb_expected.txt").exists() for ld in launches.values()):
        print("REFUSED: --gamedb <N> is required unless every launch has v1_run's gamedb_expected.txt")
        return 2
    out = batch / "s1_baseline"
    launch_data = {}
    for n, ld in launches.items():
        L = vc.process_launch(n, ld, gamedb, TRACK, out, log=say, hook=race_hook)
        mark_launch(L, launch_guard_problems(ld, 0))
        launch_data[n] = L
    snotes = {n: x for n, ld in launches.items() if (x := saves_note(n, ld))}
    for x in snotes.values():
        say(x)
    st = baseline_stats(launch_data)
    stall_lines, stop = stall_summary(launch_data)
    for ln in stall_lines:
        say(ln)
    say(f"stock baseline {batch}: {st['races_valid']}/{st['races_total']} races valid")
    if st["races_valid"] < BASELINE_MIN_VALID or None in (st["M_p"], st["M_h"], st["M_c"], st["C_race"]):
        print(f"REFUSED: {st['races_valid']} of {st['races_total']} races valid (at least {BASELINE_MIN_VALID} of 8 "
              f"needed): rerun the short launch once (prereg section 3). No bands proposed.")
        return 3
    bands = bands_from(st)
    js = {"what": "S-1 null bands (docs/verve_s1_prereg.md section 3), PROPOSED from the stock baseline; the bands "
                  "amendment PR commits this as docs/stock/s1_bands.json",
          "proposed": True, "batch": str(batch),
          "rule": "contacts max(0.15, 0.25 M_c); exit_all_kph 2.0 (always the floor); passes_made 0.25 M_p; "
                  "held_behind_s max(25, 0.25 M_h); 3 significant figures; over the valid races and the 19 AI cars",
          "bands": bands,
          "stats": {"M_p": sig3(st["M_p"]), "M_h": sig3(st["M_h"]), "M_c": sig3(st["M_c"]),
                    "exit_mean": sig3(st["exit_mean"]) if st["exit_mean"] is not None else None,
                    "C_race": sig3(st["C_race"]), "races_valid": st["races_valid"], "races_total": st["races_total"],
                    "n_driver_races": {m: st[f"n_{m}"] for m in ("passes_made", "held_behind_s", "contacts",
                                                                 "exit_all_kph")}},
          "exit_rule_info": {"0.25 x |mean|": sig3(BAND_SHARE * abs(st["exit_mean"])) if st["exit_mean"] is not None
                             else None, "applied": FLOORS["exit_all_kph"]},
          "races": [{"launch": r["launch"], "race": r["race"], "uid": r["uid"], "valid": r["valid"],
                     "verdict": r["verdict"], "coll_total": r.get("coll_total"), "stalls": r.get("stalls")}
                    for L in launch_data.values() for r in L["races"]],
          "stop_launches": stop, "saves_notes": {str(n): x for n, x in snotes.items()}}
    dest = batch / "s1_bands_proposed.json"
    dest.write_text(json.dumps(js, indent=1) + "\n", encoding="utf-8")
    say(f"  M_p {fnum(st['M_p'], 4)} (n {st['n_passes_made']}), M_h {fnum(st['M_h'], 2)} s (n {st['n_held_behind_s']}), "
        f"M_c {fnum(st['M_c'], 4)} (n {st['n_contacts']}), exit_all_kph mean {fnum(st['exit_mean'], 3)}, "
        f"C_race {fnum(st['C_race'], 3)} COLL/race")
    for m in BAND_MEASURES:
        say(f"  band {m:<15} +/-{bands[m]:g}")
    if js["exit_rule_info"]["0.25 x |mean|"] and js["exit_rule_info"]["0.25 x |mean|"] > FLOORS["exit_all_kph"]:
        say(f"  note: 0.25 x |exit mean| = {js['exit_rule_info']['0.25 x |mean|']:g} km/h is above the floor; the "
            f"ruling keeps exit at 2.0")
    say(f"PROPOSED bands written to {dest} (not docs/: the bands amendment PR commits them)")
    return 0


# ==================================================================================================== --smoke

def smoke_harness_problems(ld: Path, n_races: int, n_ops: int) -> list[str]:
    """Rule 4: the session check, weather, the build check, the saves / tyler.json guards (and the race count)."""
    probs = []
    sc = (cc.text_of(ld / "session_check.txt").strip().splitlines() or [""])[0]
    if not (sc.startswith("session ok") or sc.startswith("unverified")):
        probs.append(f"session check: {sc or 'no session_check.txt'}")
    if (ld / "invalid.txt").exists():
        probs.append("the launch is marked invalid.txt")
    probs += cc.weather_problems(ld)
    probs += build_problems(ld, n_ops)
    ok_saves, note = cc.saves_guard(ld)
    if not ok_saves:
        probs.append(note)
    if not tyler_ok(ld):
        probs.append("tyler.json: no 'restored' / 'unchanged' line in profile_hashes.txt")
    if n_races != SMOKE_RACES:
        probs.append(f"the capture has {n_races} race session(s) with lights out, not {SMOKE_RACES}")
    return probs


def smoke_verdict(races: list[dict], harness: list[str], assign: dict, steps: dict, c_race: float) -> dict:
    """races: [{"race", "verdict", "reasons", "stalls", "coll_total"}]. The PASS rules, the implicated levels, the
    next steps (prereg section 4 and the supervisor's rulings)."""
    active = [f for f in FACTORS if f not in sm.dropped(steps)]
    crit, implicated, unattributed = [], defaultdict(list), []
    limit = CONTACT_MULT * c_race
    for r in races:
        ok1 = r["verdict"] == "PASS"
        ok2 = not r["stalls"]
        ok3 = r["coll_total"] is not None and r["coll_total"] <= limit
        crit.append({"race": r["race"], "uid": r.get("uid"), "1 finishes (aionly PASS)": ok1,
                     "2 no stalled or unfinished AI": ok2, f"3 COLL <= 3 x C_race ({limit:g})": ok3,
                     "coll_total": r["coll_total"], "stalls": r["stalls"], "aionly": r["verdict"],
                     "reasons": r.get("reasons", [])})
        for x in r["stalls"]:
            d = x.get("driver")
            if d in assign:
                for f in active:
                    side = "HIGH" if assign[d][f] else "LOW"
                    implicated[(f, side)].append(f"race {r['race']}: {d} {x['kind']}")
            else:
                unattributed.append(f"race {r['race']}: {x.get('driver')} {x['kind']} (not on the roster)")
        if not ok1 and not r["stalls"]:
            unattributed.append(f"race {r['race']}: aionly {r['verdict']} with no stalled or unfinished car "
                                f"({'; '.join(r.get('reasons', []))[:200]})")
        if not ok3:
            for f in active:
                for side in contact_sides(f):
                    implicated[(f, side)].append(f"race {r['race']}: {r['coll_total']} COLL > {limit:g}")
    rules_ok = all(c["1 finishes (aionly PASS)"] and c["2 no stalled or unfinished AI"] and
                   c[f"3 COLL <= 3 x C_race ({limit:g})"] for c in crit)
    passed = not harness and rules_ok and bool(races)
    nxt = {f: dict(v) for f, v in steps.items()}
    advice = []
    if harness:
        advice.append("HARNESS FAILURE (rule 4), not a factor failure: rerun the smoke once with the same seed and "
                      "levels; failing twice is a stop. No level is stepped.")
    elif not passed:
        for (f, side), why in sorted(implicated.items(), key=lambda kv: (FACTORS.index(kv[0][0]), kv[0][1])):
            k = steps[f][side]
            if k >= sm.STOCK_STEP:
                advice.append(f"{f} {side}: already at stock; nothing to step ({'; '.join(why)})")
                continue
            nxt[f][side] = k + 1
            new = sm.level_value(f, side, k + 1)
            short = new if sm.LEVELS[f]["kind"] == "scalar" or k + 1 >= sm.STOCK_STEP else f"curve step {k + 1}"
            advice.append(f"{f} {side} ({sm.level_value(f, side, k)[:40]}): step {k} -> "
                          f"{'stock' if k + 1 >= sm.STOCK_STEP else k + 1} = {short} ({'; '.join(why)})")
        newly = [f for f in sm.dropped(nxt) if f not in sm.dropped(steps)]
        for f in newly:
            advice.append(f"{f}: both levels at stock -> DROPPED from S-1 (record the drop in the levels amendment)")
        for x in unattributed:
            advice.append(f"not attributable to a level: {x}; tell the supervisor")
        if nxt == steps and not unattributed:
            advice.append("nothing left to step: tell the supervisor")
    return {"verdict": "SMOKE PASS" if passed else "SMOKE FAIL", "harness": harness, "criteria": crit,
            "implicated": {f"{f} {s}": w for (f, s), w in implicated.items()}, "advice": advice,
            "next_steps": nxt, "changed": nxt != steps, "dropped_next": sm.dropped(nxt)}


def levels_json(steps: dict) -> dict:
    """s1_make --levels format: every level that isn't at 0 steps."""
    return {f: {s: ("stock" if k >= sm.STOCK_STEP else k) for s, k in v.items() if k} for f, v in steps.items()
            if any(v.values())}


def run_smoke(batch: Path, quiet: bool = False) -> int:
    say = (lambda *a: None) if quiet else print
    ld = batch / "launch_1"
    cap = ld / "raw" / "udp.bin"
    lv = _levels(ld)
    if not lv.get("smoke") or lv.get("seed") != sm.SMOKE_SEED or lv.get("launch") != sm.SMOKE_LAUNCH:
        print(f"REFUSED: {ld / 'gen' / 'levels.json'} isn't the extremes smoke (s1_make --smoke, seed "
              f"{sm.SMOKE_SEED}, launch 1): {({k: lv.get(k) for k in ('smoke', 'seed', 'launch')})}")
        return 3
    bands, why = load_bands()
    if bands is None:
        print(f"REFUSED: {why} (the smoke's contact rule needs C_race)")
        return 3
    if not cap.exists():
        print(f"REFUSED: no {cap}")
        return 3
    assign = sm.read_assignment(ld / "gen" / "assignment.csv")
    if assign != sm.draw(sm.SMOKE_SEED, 1):
        print(f"REFUSED: launch_1/gen/assignment.csv is not s1_make.draw({sm.SMOKE_SEED}, 1)")
        return 3
    steps = steps_of(lv)
    gamedb, build_probs = vc.launch_gamedb(ld, None)
    sessions = u.parse(cap, [])
    uids = [uid for uid, s in sessions.items() if s.get("type") == 15 and lgot_time(s) is not None]
    out = batch / "s1_smoke"
    races = []
    for k, uid in enumerate(uids, 1):
        s = sessions[uid]
        n = s["n_active"] or s.get("cars", u.CARS)
        player = s.get("player")
        cmap, mprobs = vc.map_drivers(s["participants"], n, player)
        verdict, reasons = vc.validity(ld, uid, {uid: s}, gamedb, TRACK, out / f"race_{k}")
        if mprobs:
            verdict, reasons = "INVALID", reasons + [f"INVALID: {p}" for p in mprobs]
        stalls = [{**x, "driver": cmap.get(x["car"], f"car {x['car']}")}
                  for x in find_stalls(s, [c for c in range(n) if c != player])]
        races.append({"race": k, "uid": str(uid), "verdict": verdict, "reasons": reasons, "stalls": stalls,
                      "coll_total": coll_total(s)})
    harness = smoke_harness_problems(ld, len(races), n_ops_of(ld)) + build_probs
    v = smoke_verdict(races, harness, assign, steps, bands["C_race"])
    out.mkdir(parents=True, exist_ok=True)
    lines = [f"S-1 extremes smoke {batch}: seed {sm.SMOKE_SEED} launch 1, {len(races)} race(s); levels "
             f"{lv.get('stepped') or 'the extremes (no steps)'}; C_race {bands['C_race']:g} ({bands['path']})"]
    lines += [f"  rule 4 (harness): {'OK' if not harness else 'FAIL: ' + '; '.join(harness)}"]
    for c in v["criteria"]:
        lines.append(f"  race {c['race']} (uid {c['uid']}): " + ", ".join(
            f"{k} {'ok' if c[k] else 'FAIL'}" for k in c if k[:1].isdigit())
            + f"; COLL {c['coll_total']}" + (f"; stalls: {stall_text(c['stalls'])}" if c["stalls"] else "")
            + (f"; aionly: {'; '.join(c['reasons'])}" if c["aionly"] != "PASS" else ""))
    lines.append(v["verdict"])
    lines += [f"  {a}" for a in v["advice"]]
    if v["changed"]:
        nj = out / "levels_next.json"
        nj.write_text(json.dumps(levels_json(v["next_steps"]), indent=1) + "\n", encoding="utf-8")
        lines.append(f"  next levels: {nj} = {json.dumps(levels_json(v['next_steps']))}")
        lines.append(f"  re-smoke (same seed): powershell -File tools/v1_run.ps1 -Make s1 -Smoke -Launch 1 -Batch "
                     f"{batch} -Seed {sm.SMOKE_SEED} -Levels {nj}")
        lines.append("  any level change goes into a second amendment PR before S-1 launch 1")
    for ln in lines:
        say(ln)
    (out / "summary.json").write_text(json.dumps({"batch": str(batch), "mode": "smoke", **v, "races": races,
                                                  "levels": lv, "report": lines}, indent=1, default=str) + "\n",
                                      encoding="utf-8")
    return 0 if v["verdict"] == "SMOKE PASS" else 1


# ==================================================================================================== --stalls

def run_stalls(batch: Path, quiet: bool = False) -> int:
    """Validity only (allowed during the batch): the stalled cars per race and the STOP rule; no measures."""
    say = (lambda *a: None) if quiet else print
    launch_data = {}
    for n, ld in vc.find_launches(batch).items():
        cap = ld / "raw" / "udp.bin"
        if not cap.exists():
            continue
        sessions = u.parse(cap, [])
        races = []
        for k, (uid, s) in enumerate(((uid, s) for uid, s in sessions.items() if s.get("type") == 15
                                      and lgot_time(s) is not None), 1):
            n_cars = s["n_active"] or s.get("cars", u.CARS)
            cmap, _ = vc.map_drivers(s["participants"], n_cars, s.get("player"))
            stalls = [{**x, "driver": cmap.get(x["car"], f"car {x['car']}")}
                      for x in find_stalls(s, [c for c in range(n_cars) if c != s.get("player")])]
            races.append({"race": k, "uid": str(uid), "verdict": "-", "stalls": stalls})
        launch_data[n] = {"races": races}
        say(f"  launch {n}: {len(races)} race(s), {sum(1 for r in races if r['stalls'])} with a stalled car")
    lines, stop = stall_summary(launch_data)
    for ln in lines:
        say(ln)
    return 1 if stop else 0


# ==================================================================================================== selftest

SCALE = {"reaction_s": (0.47, 0.03, 0.015, 0.04), "launch_m": (19.0, 1.0, 0.4, 1.2),
         "speed_1s_kph": (35.0, 3.0, 1.0, 3.0), "gain_t1": (0.0, 0.5, 0.3, 0.8), "gain_lap1": (0.0, 0.7, 0.4, 1.2),
         "passes_made": (1.0, 0.3, 0.2, 0.7), "passes_suffered": (1.0, 0.3, 0.2, 0.7),
         "held_behind_s": (140.0, 40.0, 20.0, 60.0), "offtracks": (0.0, 0.02, 0.01, 0.03),
         "spins": (0.0, 0.01, 0.01, 0.02), "entry_kph": (0.0, 1.5, 0.3, 0.6), "exit_kph": (0.0, 1.5, 0.3, 0.6),
         "entry_all_kph": (0.0, 1.5, 0.4, 0.8), "exit_all_kph": (0.0, 1.5, 0.4, 0.8),
         "laptime_sd_s": (0.6, 0.05, 0.03, 0.08), "contacts": (0.6, 0.15, 0.05, 0.5),
         "costly_contacts": (0.2, 0.05, 0.03, 0.3), "front_wing_added": (3.0, 1.0, 0.5, 3.0),
         "penalties": (0.05, 0.02, 0.01, 0.1)}


def synth_launch_data(seed: int, plant: dict[str, tuple[str, float]], rng_seed: int = 3, n_launch: int = N_LAUNCHES,
                      races: int = RACES_PER_LAUNCH, scale: float = 1.0) -> tuple[dict, dict]:
    """Synthetic per-race measure tables below the parsing layer (as v1_check's): driver effects, launch noise shared
    by a launch's races, race noise; plant = {factor: (measure, HIGH - LOW effect)}."""
    rng = random.Random(rng_seed)
    alpha = {(m, d): rng.gauss(0, sc[1]) for m, sc in SCALE.items() for d in ROSTER}
    data, assigns = {}, {}
    for n in range(1, n_launch + 1):
        a = sm.draw(seed, n)
        assigns[n] = a
        order = ROSTER[:]
        rng.shuffle(order)
        side = {d: (i + 1) % 2 for i, d in enumerate(order)}
        lnoise = {(m, d): rng.gauss(0, sc[2] * scale) for m, sc in SCALE.items() for d in ROSTER}
        rs = []
        for k in range(races):
            drivers = {}
            for d in ROSTER:
                v = {"side": side[d]}
                for m, (mu, _, _, sd) in SCALE.items():
                    v[m] = mu + alpha[(m, d)] + lnoise[(m, d)] + rng.gauss(0, sd * scale)
                for f, (m, eff) in plant.items():
                    v[m] += eff * a[d][f]
                v["offtracks_spins"] = v["offtracks"] + v["spins"]
                drivers[d] = v
            rs.append({"launch": n, "race": k + 1, "valid": True, "drivers": drivers, "uid": f"{n}{k}",
                       "verdict": "PASS", "reasons": [], "stalls": [], "coll_total": 6})
        data[n] = {"launch": n, "races": rs, "grids": []}
    return data, assigns


TEST_BANDS = {"contacts": 0.15, "exit_all_kph": 2.0, "passes_made": 0.245, "held_behind_s": 35.7}


def lap_tuple(td: float, pit: int = 0, status: int = 2, lap: int = 1) -> tuple:
    x = [0] * 33
    x[u.L_TOTDIST], x[u.L_LAPDIST], x[u.L_PIT], x[u.L_RSTATUS], x[u.L_LAPNUM] = float(td), float(td), pit, status, lap
    return tuple(x)


def synth_session(cars: dict[int, callable], t_end: float = 300.0, dt: float = 0.5, n: int = 20,
                  finish_at: dict[int, float] | None = None, lgot: float = 10.0, colls: int = 0) -> dict:
    """A parsed-session stand-in: cars[c](t) -> (totalDistance, pitStatus); finish_at[c] = the time it reads 3."""
    frames = []
    t = 0.0
    while t <= t_end + 1e-9:
        row = []
        for c in range(n):
            f = cars.get(c)
            td, pit = f(t) if f else (0.0, 0)
            st = 3 if finish_at and c in finish_at and t >= finish_at[c] else 2
            row.append(lap_tuple(td, pit, st))
        frames.append((t, row))
        t += dt
    ev = [(lgot, 0.0, "LGOT", {})] + [(lgot + 5 + i, 0.0, "COLL", {"vehicle": 1, "other": 2}) for i in range(colls)]
    return {"lap_frames": frames, "events": ev, "n_active": n, "cars": n, "player": 19}


def selftest() -> int:
    global BANDS_FILE
    results, ok = [], True

    def chk(name: str, cond: bool, detail: str = "") -> None:
        nonlocal ok
        ok &= bool(cond)
        results.append(f"{'ok  ' if cond else 'FAIL'} {name}" + (f": {detail}" if detail else ""))

    seed = sm.S1_SEED
    # ---- the design table
    chk("primaries: YIELD contacts +, EXIT_ERR exit_all_kph -, OVERLAP and COMMIT passes_made +, both blocking keys "
        "held_behind_s two-sided", PRIMARY == {"YIELD": ("contacts", 1), "EXIT_ERR": ("exit_all_kph", -1),
                                              "OVERLAP": ("passes_made", 1), "BLK_SPEED": ("held_behind_s", 0),
                                              "BLK_THREAT": ("held_behind_s", 0), "COMMIT": ("passes_made", 1)})
    chk("every primary and secondary is a measure (v1_check's MEASURES + costly_contacts, front_wing_added, penalties)",
        all(PRIMARY[f][0] in MEASURES and all(m in MEASURES for m in secondaries(f)) for f in FACTORS)
        and all(m in vc.MEASURES for m in MEASURES if m not in EXTRA) and "penalties" in secondaries("YIELD"))
    cs = {f: contact_sides(f) for f in FACTORS}
    chk("contact-raising extremes, by value: YIELD the 0.5 level (the low yield rate), OVERLAP flat 0.05, COMMIT 0.1, "
        "BLK_SPEED and BLK_THREAT both extremes, EXIT_ERR excluded",
        [sm.LEVELS["YIELD"][s] for s in cs["YIELD"]] == ["0.5"]
        and [sm.LEVELS["OVERLAP"][s] for s in cs["OVERLAP"]] == [sm.vm.flat_curve(0.05)]
        and [sm.LEVELS["COMMIT"][s] for s in cs["COMMIT"]] == ["0.1"]
        and cs["BLK_SPEED"] == ["HIGH", "LOW"] and cs["BLK_THREAT"] == ["HIGH", "LOW"] and cs["EXIT_ERR"] == [],
        str(cs))

    # ---- planted effects, one per factor (ALIVE)
    plant = {"YIELD": ("contacts", 0.4), "EXIT_ERR": ("exit_all_kph", -3.0), "OVERLAP": ("passes_made", 0.6),
             "BLK_SPEED": ("held_behind_s", -60.0), "BLK_THREAT": ("held_behind_s", 60.0),
             "COMMIT": ("passes_made", 0.6)}
    data, assigns = synth_launch_data(seed, plant)
    t0 = time.perf_counter()
    res = analyse(data, assigns, seed, TEST_BANDS, N_PERMS)
    full_s = time.perf_counter() - t0
    fx = res["factors"]
    chk("planted effects: every factor ALIVE (BLK_SPEED's negative effect ALIVE with sign -, BLK_THREAT's +)",
        all(fx[f]["decision"] == "ALIVE" for f in FACTORS) and fx["BLK_SPEED"].get("sign") == "-"
        and fx["BLK_THREAT"].get("sign") == "+",
        "; ".join(f"{f} {fnum(fx[f]['fe_slope'], 3)} p {fnum(fx[f]['p'], 4)} {fx[f]['decision']}" for f in FACTORS))
    chk(f"10,000 permutations on 16 launches x 4 races, {sum(1 + len(secondaries(f)) for f in FACTORS)} tests",
        all(fx[f]["null_n"] == N_PERMS for f in FACTORS), f"permutations {res['perm_runtime_s']} s, total {full_s:.1f} s")
    nd, na = synth_launch_data(seed, {}, rng_seed=11)
    nres = analyse(nd, na, seed, TEST_BANDS, 2000)["factors"]
    chk("null: no factor ALIVE; EXIT_ERR (a tight measure, band 2 km/h) DEAD",
        not any(nres[f]["decision"].startswith("ALIVE") for f in FACTORS) and nres["EXIT_ERR"]["decision"] == "DEAD",
        str({f: nres[f]["decision"] for f in FACTORS}))
    rv, ra = synth_launch_data(seed, {"YIELD": ("contacts", -0.4), "BLK_THREAT": ("held_behind_s", -60.0)})
    rres = analyse(rv, ra, seed, TEST_BANDS, 1000)["factors"]
    chk("the wrong direction: YIELD ALIVE-REVERSED; a two-sided factor is ALIVE with either sign (never REVERSED)",
        rres["YIELD"]["decision"] == "ALIVE-REVERSED" and rres["BLK_THREAT"]["decision"] == "ALIVE"
        and rres["BLK_THREAT"]["sign"] == "-", f"{rres['YIELD']['decision']} {rres['BLK_THREAT']['decision']}")
    sd_, sa_ = synth_launch_data(seed, {"YIELD": ("contacts", 0.09)}, scale=0.5)
    sres = analyse(sd_, sa_, seed, TEST_BANDS, 1000)["factors"]["YIELD"]
    chk("a significant effect inside the band (YIELD +0.09, band 0.15) is ALIVE-SMALL",
        sres["decision"] == "ALIVE-SMALL", f"p {fnum(sres['p'], 4)} FE {fnum(sres['fe_slope'])}")
    fp = 0
    for k in range(8):
        d8, a8 = synth_launch_data(seed + k, {}, rng_seed=200 + k)
        r8 = analyse(d8, a8, seed + k, TEST_BANDS, 300, with_secondary=False)["factors"]
        fp += sum(r8[f]["p"] < ALPHA for f in FACTORS)
    chk("type I error: 8 null batches x 6 factors, p < 0.05 in about 5% (allowed <= 8 of 48)", fp <= 8, f"{fp}/48")
    calls = []

    def counting(s, n):
        calls.append((s, n))
        return sm.draw(s, n)
    analyse(data, assigns, seed, TEST_BANDS, 50, with_secondary=False, draw=counting)
    chk("each redraw replaces every launch's assignment with s1_make.draw(seed_k, launch), fresh seeds",
        len(calls) == 50 * N_LAUNCHES and len({s for s, _ in calls}) == 50 and seed not in {s for s, _ in calls})
    chk("the decision rule: ALIVE / ALIVE-SMALL / ALIVE-REVERSED / DEAD / INCONCLUSIVE, two-sided has no REVERSED",
        decide(0.01, 0.5, 0.5, 0.1, 0.15, 1) == "ALIVE" and decide(0.01, 0.1, 0.1, 0.03, 0.15, 1) == "ALIVE-SMALL"
        and decide(0.01, -0.5, -0.5, 0.1, 0.15, 1) == "ALIVE-REVERSED" and decide(0.01, -0.5, -0.5, 0.1, 0.15, 0) ==
        "ALIVE" and decide(0.5, 0.01, 0.01, 0.05, 0.15, 1) == "DEAD" and decide(0.5, 0.1, 0.1, 0.05, 0.15, 1) ==
        "INCONCLUSIVE" and decide(None, 0, 0, 0, 0.15, 1) == "NO DATA")

    # ---- stall detection
    def moving(v=50.0):
        return lambda t: (v * t, 0)
    cars = {c: moving() for c in range(19)}
    cars[3] = lambda t: (50 * min(t, 100) if t < 140 else 50 * 100 + 50 * (t - 140), 0)      # stopped 100-140 s
    cars[4] = lambda t: (50 * min(t, 100) if t < 140 else 50 * 100 + 50 * (t - 140), 1 if 100 <= t < 140 else 0)
    cars[5] = lambda t: (50 * min(t, 100) if t < 120 else 50 * 100 + 50 * (t - 120), 0)      # stopped 20 s only
    cars[6] = lambda t: (50 * min(t, 200), 0)                                                # stops at 200 s ...
    cars[7] = lambda t: (50 * min(t, 260), 0)                                                # ... after the leader
    cars[8] = lambda t: (50 * min(t, 100) + 0.02 * max(0, t - 100), 0)                       # crawling: 0.6 m / 30 s
    sess = synth_session(cars, t_end=300, finish_at={c: 250.0 for c in range(19) if c not in (6, 8)})
    st = {(x["car"], x["kind"]) for x in find_stalls(sess, list(range(19)))}
    chk("stalls: a car stopped 40 s on track is a stall; in the pit lane it isn't; 20 s isn't; a crawl under 1 m "
        "in 30 s is; stopping after the leader's finish isn't; an unfinished car (resultStatus not 3) counts",
        st == {(3, "stall"), (6, "stall"), (6, "not finished"), (8, "stall"), (8, "not finished")}, str(sorted(st)))
    chk("the race's COLL total counts every COLL event", coll_total(synth_session({}, t_end=20, colls=7)) == 7)

    # ---- sensitivity and the stop rule
    sdata, sas = synth_launch_data(seed, {"YIELD": ("contacts", 0.4)})
    sdata[2]["races"][0]["stalls"] = [{"car": 1, "kind": "stall", "t_after_lights_out_s": 50.0, "driver": "lando_norris"}]
    sdata[5]["races"][1]["stalls"] = [{"car": 2, "kind": "not finished", "result_status": 7, "driver": "max_verstappen"}]
    sdata[5]["races"][3]["stalls"] = [{"car": 2, "kind": "stall", "t_after_lights_out_s": 9.0, "driver": "max_verstappen"}]
    ws, nset = without_stalled(sdata)
    sres2 = analyse(sdata, sas, seed, TEST_BANDS, 300)
    sens2 = analyse(ws, sas, seed, TEST_BANDS, 300, with_secondary=False)
    lines = report(sres2, sens2, nset, [], ["head"], False)
    stl, stop = stall_summary(sdata)
    sens_lines = [ln for ln in lines if ln.strip().startswith("SENSITIVITY")]
    chk("sensitivity: the races with a stalled car are set aside (3 of 64), the same test reruns, a SENSITIVITY line "
        "sits beside each of the 6 primaries; the primary keeps all valid races",
        nset == 3 and len(sens_lines) == 6 and sens2["factors"]["YIELD"]["races_valid"] == 61
        and sres2["factors"]["YIELD"]["races_valid"] == 64 and sens2["factors"]["YIELD"]["decision"] == "ALIVE"
        and all(sdata[n]["races"][k]["valid"] for n, k in ((2, 0), (5, 1))) and "not scored" in sens_lines[0],
        sens_lines[0].strip()[:120])
    chk("stalls are reported, not invalidating; more than 1 stalled race in a launch prints STOP (launch 5)",
        stop == [5] and any(ln.startswith("STOP: launch 5") for ln in stl) and len([x for x in stl if "stalled:" in x]) == 3)

    # ---- the bands: refusal, the baseline computation, the floors
    with tempfile.TemporaryDirectory() as tmp:
        tmpd = Path(tmp)
        saved = BANDS_FILE
        BANDS_FILE = tmpd / "missing.json"
        b0, why0 = load_bands()
        bf = tmpd / "b.json"
        bad_files = [{"bands": {"contacts": 0.15, "exit_all_kph": 2.0, "passes_made": 0.245}, "stats": {"C_race": 5}},
                     {"bands": {**TEST_BANDS, "contacts": 0.1}, "stats": {"C_race": 5}},
                     {"bands": {**TEST_BANDS, "exit_all_kph": 3.0}, "stats": {"C_race": 5}},
                     {"bands": {**TEST_BANDS, "held_behind_s": 20}, "stats": {"C_race": 5}},
                     {"bands": TEST_BANDS, "stats": {}}]
        nbad = 0
        for js in bad_files:
            bf.write_text(json.dumps(js), encoding="utf-8")
            nbad += load_bands(bf)[0] is None
        bf.write_text(json.dumps({"bands": TEST_BANDS, "stats": {"C_race": 5.5}}), encoding="utf-8")
        good = load_bands(bf)[0]
        chk("the bands file: missing -> refused; a missing band, a broken floor, exit not 2.0 or no C_race -> refused",
            b0 is None and "no bands file" in why0 and nbad == 5 and good and good["C_race"] == 5.5)
        buf = io.StringIO()
        with redirect_stdout(buf):
            rcb = run(tmpd, None, None, 100, True)
        chk("the analysis REFUSES without the committed bands file (exit 3)",
            rcb == 3 and "REFUSED" in buf.getvalue() and "bands" in buf.getvalue(), buf.getvalue().strip()[:100])
        st1 = {"M_c": 0.4, "M_p": 0.98, "M_h": 60.0, "exit_mean": 9.0}
        st2 = {"M_c": 1.0, "M_p": 2.0, "M_h": 142.7, "exit_mean": 0.1}
        chk("band rule: contacts 0.25 x 0.4 -> the 0.15 floor, held 0.25 x 60 -> the 25 floor, exit 2.0 even at a mean "
            "of 9, passes 0.25 x 0.98 = 0.245 (no floor); and 0.25 / 0.5 / 35.7 above the floors",
            bands_from(st1) == {"contacts": 0.15, "exit_all_kph": 2.0, "passes_made": 0.245, "held_behind_s": 25.0}
            and bands_from(st2) == {"contacts": 0.25, "exit_all_kph": 2.0, "passes_made": 0.5, "held_behind_s": 35.7},
            f"{bands_from(st1)} {bands_from(st2)}")
        bdata = {n: {"races": [{"valid": k < 2 + n, "coll_total": 4 + k, "drivers": {
            d: {"passes_made": 1.0 + (i % 2), "held_behind_s": 100.0 + i, "contacts": 0.5 if i % 2 else None,
                "exit_all_kph": 0.0} for i, d in enumerate(ROSTER)}} for k in range(4)]} for n in (1, 2)}
        bs = baseline_stats(bdata)
        chk("baseline statistics: over the valid races and AI cars, NA excluded; C_race = the mean COLL per valid race",
            bs["races_valid"] == 7 and bs["races_total"] == 8 and bs["n_contacts"] == 9 * 7
            and abs(bs["M_c"] - 0.5) < 1e-12 and abs(bs["M_p"] - (10 * 1 + 9 * 2) / 19) < 1e-12
            and abs(bs["M_h"] - 109.0) < 1e-12 and abs(bs["C_race"] - (4 + 5 + 6 + 4 + 5 + 6 + 7) / 7) < 1e-12, str(bs))
        v1pr = next((p for p in (REPO / "runs" / "2026-11-17-V1" / "v1_check" / "per_race.csv",
                                 REPO.parents[2] / "runs" / "2026-11-17-V1" / "v1_check" / "per_race.csv")
                     if p.exists()), None)
        if v1pr:
            rows = list(csv.DictReader(v1pr.open(encoding="utf-8")))
            vdata = defaultdict(lambda: {"races": []})
            byr = defaultdict(dict)
            for r0 in rows:
                if r0["valid"] == "1" and r0["driver"]:
                    byr[(r0["launch"], r0["race"])][r0["driver"]] = {
                        m: (None if r0[m] in ("NA", "") else float(r0[m]))
                        for m in ("passes_made", "held_behind_s", "contacts", "exit_all_kph")}
            for (ln_, rc_), drv in byr.items():
                vdata[int(ln_)]["races"].append({"valid": True, "coll_total": 1, "drivers": drv})
            vs = baseline_stats(vdata)
            chk("realistic: V-1's 48 races (runs/2026-11-17-V1/v1_check/per_race.csv, read-only) give M_c 0.583, M_p "
                "0.976, M_h 142.7 and bands 0.15 / 2.0 / 0.244 / 35.7 (the prereg's 0.245 is 0.25 x the rounded 0.98)",
                (sig3(vs["M_c"]), sig3(vs["M_p"]), sig3(vs["M_h"])) == (0.583, 0.976, 143.0)
                and bands_from(vs) == {"contacts": 0.15, "exit_all_kph": 2.0, "passes_made": 0.244, "held_behind_s": 35.7},
                f"M_c {vs['M_c']:.4f} M_p {vs['M_p']:.4f} M_h {vs['M_h']:.2f} -> {bands_from(vs)}")
        else:
            results.append("skip V-1 per_race.csv not found (realistic band check)")

        # ---- the smoke: PASS, FAIL and the stepping advice
        sa = sm.draw(sm.SMOKE_SEED, 1)
        s0 = sm.no_steps()

        def race(k, verdict="PASS", stalls=(), coll=5):
            return {"race": k, "uid": str(k), "verdict": verdict, "reasons": [] if verdict == "PASS" else ["FAIL: x"],
                    "stalls": list(stalls), "coll_total": coll}
        v_ok = smoke_verdict([race(1), race(2, coll=16)], [], sa, s0, 5.5)
        chk("smoke PASS: both races finish, no stall, COLL 16 <= 3 x 5.5, harness OK",
            v_ok["verdict"] == "SMOKE PASS" and not v_ok["changed"] and not v_ok["advice"])
        v_c = smoke_verdict([race(1), race(2, coll=17)], [], sa, s0, 5.5)
        want_c = {"YIELD HIGH", "OVERLAP HIGH", "COMMIT HIGH", "BLK_SPEED HIGH", "BLK_SPEED LOW", "BLK_THREAT HIGH",
                  "BLK_THREAT LOW"}
        nx = v_c["next_steps"]
        chk("smoke FAIL on contacts (17 > 16.5): steps the contact-raising extremes only: YIELD 0.5 -> 0.707, OVERLAP "
            "flat 0.05 -> step 1, COMMIT 0.1 -> 0.258, BOTH blocking extremes (0.15 -> 0.3, 2.4 -> 1.2; 0.7 -> 0.35, "
            "0.04375 -> 0.0875); EXIT_ERR and the other sides untouched",
            v_c["verdict"] == "SMOKE FAIL" and set(v_c["implicated"]) == want_c
            and sm.level_value("YIELD", "HIGH", nx["YIELD"]["HIGH"]) == "0.707" and nx["YIELD"]["LOW"] == 0
            and nx["EXIT_ERR"] == {"HIGH": 0, "LOW": 0} and nx["OVERLAP"] == {"HIGH": 1, "LOW": 0}
            and sm.level_value("COMMIT", "HIGH", nx["COMMIT"]["HIGH"]) == "0.258" and nx["COMMIT"]["LOW"] == 0
            and [sm.level_value("BLK_SPEED", s, nx["BLK_SPEED"][s]) for s in SIDES] == ["0.3", "1.2"]
            and [sm.level_value("BLK_THREAT", s, nx["BLK_THREAT"][s]) for s in SIDES] == ["0.35", "0.0875"],
            str(sorted(v_c["implicated"])))
        stall_d = "max_verstappen"
        v_s = smoke_verdict([race(1, "INVALID", [{"car": 3, "kind": "not finished", "result_status": 7,
                                                  "driver": stall_d}]), race(2)], [], sa, s0, 5.5)
        want_s = {f"{f} {'HIGH' if sa[stall_d][f] else 'LOW'}" for f in FACTORS}
        chk("smoke FAIL on a stalled / unfinished car: every factor (EXIT_ERR included) at the level that car held",
            v_s["verdict"] == "SMOKE FAIL" and set(v_s["implicated"]) == want_s
            and all(v_s["next_steps"][f]["HIGH" if sa[stall_d][f] else "LOW"] == 1 for f in FACTORS), str(sorted(want_s)))
        v_h = smoke_verdict([race(1), race(2, coll=40)], ["weather: NOT LOCKED"], sa, s0, 5.5)
        chk("a harness failure (rule 4) is a FAIL with a rerun, and steps nothing (even with excess contacts)",
            v_h["verdict"] == "SMOKE FAIL" and not v_h["changed"] and "HARNESS FAILURE" in v_h["advice"][0])
        s2 = sm.merge_steps(s0, {"BLK_SPEED": {"HIGH": 2, "LOW": 2}, "YIELD": {"HIGH": 1}})
        v_p = smoke_verdict([race(1, coll=30), race(2)], [], sa, s2, 5.5)
        chk("stepping goes on from the current levels: YIELD 0.707 -> 0.841; BLK_SPEED at 0.25 on both sides -> stock, "
            "so BLK_SPEED is DROPPED",
            sm.level_value("YIELD", "HIGH", v_p["next_steps"]["YIELD"]["HIGH"]) == "0.841"
            and v_p["dropped_next"] == ["BLK_SPEED"] and any("DROPPED" in a for a in v_p["advice"]))
        v_u = smoke_verdict([race(1, "FAIL"), race(2)], [], sa, s0, 5.5)
        chk("an aionly FAIL with no stalled car steps nothing and goes to the supervisor",
            v_u["verdict"] == "SMOKE FAIL" and not v_u["changed"] and any("not attributable" in a for a in v_u["advice"]))
        lj = levels_json(v_p["next_steps"])
        chk("levels_next.json is s1_make --levels' format and s1_make reads it back",
            sm.merge_steps(sm.no_steps(), json.loads(json.dumps(lj))) == v_p["next_steps"]
            and lj["BLK_SPEED"] == {"HIGH": "stock", "LOW": "stock"}, json.dumps(lj))

        # ---- the smoke end to end on a synthetic launch (the capture's 6 s after lights out: no car finishes)
        bfile = tmpd / "bands.json"
        bfile.write_text(json.dumps({"bands": TEST_BANDS, "stats": {"C_race": 5.5}}), encoding="utf-8")
        BANDS_FILE = bfile
        smk = tmpd / "smoke"
        ld = smk / "launch_1"
        with redirect_stdout(io.StringIO()):
            sm.main(["--smoke", "--out", str(ld / "gen")])
        write_synth_launch(ld, 1, sm.SMOKE_SEED, races=2, arm="S1 seed 2026111707 launch 1 (smoke)")
        saved_v = vc._VALIDITY_OVERRIDE
        vc._VALIDITY_OVERRIDE = lambda ld_, uid: ("PASS", [])   # noqa: E731
        buf = io.StringIO()
        with redirect_stdout(buf):
            rcs = run_smoke(smk)
        sj = json.loads((smk / "s1_smoke" / "summary.json").read_text(encoding="utf-8"))
        chk("smoke end to end: 2 races, harness OK, every AI car unfinished in the 6 s capture -> SMOKE FAIL, every "
            "factor stepped at both levels, levels_next.json and the re-smoke command written",
            rcs == 1 and not sj["harness"] and len(sj["criteria"]) == 2 and (smk / "s1_smoke" / "levels_next.json").exists()
            and all(sj["next_steps"][f] == {"HIGH": 1, "LOW": 1} for f in FACTORS) and "-Smoke" in buf.getvalue(),
            buf.getvalue().splitlines()[-4][:100] if buf.getvalue() else "")
        (ld / "weather.txt").write_text("weather: NOT LOCKED (weather 1)\n", encoding="utf-8")
        with redirect_stdout(io.StringIO()):
            rch = run_smoke(smk)
        sjh = json.loads((smk / "s1_smoke" / "summary.json").read_text(encoding="utf-8"))
        chk("smoke end to end: weather NOT LOCKED -> harness failure, nothing stepped",
            rch == 1 and sjh["harness"] and not sjh["changed"])
        vc._VALIDITY_OVERRIDE = saved_v

        # ---- the analysis end to end on synthetic captures (validity stubbed, the files as v1_run writes them)
        batch = tmpd / "batch"
        for n in range(1, N_LAUNCHES + 1):
            with redirect_stdout(io.StringIO()):
                sm.write_launch(seed, n, batch / f"launch_{n}" / "gen")
            write_synth_launch(batch / f"launch_{n}", n, seed, races=RACES_PER_LAUNCH)
        vc._VALIDITY_OVERRIDE = lambda ld_, uid: ("PASS", [])   # noqa: E731
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = run(batch, None, None, 200, False)
        js = json.loads((batch / "s1_check" / "summary.json").read_text(encoding="utf-8"))
        prc = list(csv.DictReader((batch / "s1_check" / "per_race.csv").open(encoding="utf-8")))
        txt = buf.getvalue()
        chk("end to end: 16 launches scored, 64/64 races, per_race.csv 64 x 19, a decision and a SENSITIVITY line per "
            "factor; the 6 s captures leave every car unfinished, so every race is stalled and STOP prints",
            rc == 0 and js["scored"] and js["races_valid"] == 64 and len(prc) == 64 * 19
            and all(js["factors"][f]["decision"] for f in FACTORS) and txt.count("SENSITIVITY") == 6
            and "STOP: launch 1" in txt and js["sensitivity"]["races_set_aside"] == 64, f"rc {rc}")
        tr5 = batch / "launch_5" / "transcript.txt"
        keep5 = tr5.read_text(encoding="utf-8")
        tr5.write_text(keep5.replace("saves unchanged (179 entries)", "SAVES CHANGED: stop the batch"), encoding="utf-8")
        buf = io.StringIO()
        with redirect_stdout(buf):
            rcn = run(batch, None, None, 100, False)
        jsn = json.loads((batch / "s1_check" / "summary.json").read_text(encoding="utf-8"))
        note = ("NOTE: saves guard tripped (SAVES CHANGED) in launch 5: a safety stop, not a validity rule; reviewed by "
                "the supervisor")
        chk("a SAVES CHANGED launch is KEPT (64/64 races valid, launch 5's 4 included) with the NOTE printed and in "
            "summary.json (the supervisor's ruling on #182)",
            rcn == 0 and jsn["races_valid"] == 64 and note in buf.getvalue() and note in jsn["saves_notes"]["5"]
            and not launch_guard_problems(batch / "launch_5", n_ops_of(batch / "launch_5"))
            and sum(1 for r0 in csv.DictReader((batch / "s1_check" / "per_race.csv").open(encoding="utf-8"))
                    if r0["launch"] == "5" and r0["valid"] == "1") == 4 * 19,
            next((ln for ln in buf.getvalue().splitlines() if ln.startswith("NOTE")), "no NOTE line")[:90])
        tr5.write_text(keep5, encoding="utf-8")
        part = tmpd / "partial"
        for n in (1, 2):
            shutil.copytree(batch / f"launch_{n}", part / f"launch_{n}")
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc3 = run(part, None, None, 100, False)
        chk("a partial batch (2 of 16) is refused, exit 3", rc3 == 3 and "REFUSED" in buf.getvalue())
        buf = io.StringIO()
        with redirect_stdout(buf):
            rcp = run(part, None, None, 100, True)
        pl = [ln for ln in buf.getvalue().splitlines() if ln.strip()]
        chk("--allow-partial runs and prints NOT SCORED on every line", rcp == 0 and pl and all(PARTIAL in ln for ln in pl),
            f"{len(pl)} lines")
        lv3 = batch / "launch_3" / "gen" / "levels.json"
        keep = lv3.read_text(encoding="utf-8")
        with redirect_stdout(io.StringIO()):
            sm.main(["--seed", str(seed), "--launch", "3", "--out", str(batch / "launch_3" / "gen"), "--step",
                     "YIELD:HIGH:1"])
        buf = io.StringIO()
        with redirect_stdout(buf):
            rcl = run(batch, None, None, 100, False)
        chk("launches with different levels are refused (no level changes once a race has been seen)",
            rcl == 3 and "levels differ" in buf.getvalue())
        with redirect_stdout(io.StringIO()):
            sm.main(["--seed", str(seed), "--launch", "3", "--out", str(batch / "launch_3" / "gen")])
        chk("(launch 3 restored)", lv3.read_text(encoding="utf-8") == keep)
        (batch / "launch_3" / "gen" / "assignment.csv").write_text(
            (batch / "launch_4" / "gen" / "assignment.csv").read_text(encoding="utf-8"), encoding="utf-8")
        buf = io.StringIO()
        with redirect_stdout(buf):
            rcm = run(batch, None, None, 100, False)
        chk("an assignment.csv that isn't s1_make.draw(seed, launch) is refused", rcm == 3 and "is not" in buf.getvalue())
        vc._VALIDITY_OVERRIDE = saved_v
        BANDS_FILE = saved

    # ---- real data (read-only, optional): stall detection on V-1 launch 1's 4 races
    cap = next((p for p in (REPO / "runs" / "2026-11-17-V1" / "launch_1" / "raw" / "udp.bin",
                            REPO.parents[2] / "runs" / "2026-11-17-V1" / "launch_1" / "raw" / "udp.bin")
                if p.exists()), None)
    if cap:
        t1 = time.perf_counter()
        ss = u.parse(cap, [])
        rr = [s for s in ss.values() if s.get("type") == 15 and lgot_time(s) is not None]
        found = []
        for s in rr:
            n = s["n_active"] or s.get("cars", u.CARS)
            found.append(find_stalls(s, [c for c in range(n) if c != s.get("player")]))
        chk("real: V-1 launch 1 (runs/2026-11-17-V1, read-only): 4 races, every AI car finished (as udp_races.txt: 19 "
            "finished), COLL 4 / 10 / 4 / 3", len(rr) == 4 and all(x["kind"] != "not finished" for f_ in found for x in f_)
            and [coll_total(s) for s in rr] == [4, 10, 4, 3],
            f"stalls per race {[len(f_) for f_ in found]} ({time.perf_counter() - t1:.0f} s)")
    else:
        results.append("skip V-1 launch 1 capture not on this PC (real-data stall check)")
    print("\n".join(results))
    print("selftest", "ok" if ok else "FAILED")
    return 0 if ok else 1


def write_synth_launch(ld: Path, n: int, seed: int, races: int, arm: str | None = None) -> None:
    """A launch folder as v1_run leaves it: the capture (v1_check.write_synth_capture: 6 s after lights out), and the
    validity files (weather, the build check, the session check, the saves guard, tyler.json, arm.txt)."""
    rng = random.Random(n)
    order = ROSTER[:]
    rng.shuffle(order)
    react = {d: [rng.choice(range(22, 32)) / 60 for _ in range(races)] for d in ROSTER}
    accel = {d: rng.uniform(9.0, 11.0) for d in ROSTER}
    vc.write_synth_capture(ld / "raw" / "udp.bin", order, react, accel, uid0=1000 * n)
    n_ops = n_ops_of(ld)
    (ld / "raw" / "loader.log").write_text(f"[assets] gamedb: {56 + n_ops} overwritten\n", encoding="utf-8")
    (ld / "check_applied.txt").write_text(f"ops {n_ops}: {n_ops} applied, 0 dropped as equal to stock (), 0 problem(s)\n"
                                          f"loader total {56 + n_ops} overwritten; expected 56 + {n_ops} = {56 + n_ops}\n",
                                          encoding="utf-8")
    (ld / "gamedb_expected.txt").write_text(f"{56 + n_ops}\n", encoding="ascii")
    (ld / "weather.txt").write_text("weather: LOCKED\n", encoding="utf-8")
    (ld / "session_check.txt").write_text(f"session ok uid {1000 * n}: difficulty 100 track 17 weather 0\n",
                                          encoding="utf-8")
    (ld / "transcript.txt").write_text("result: plan done\nsaves unchanged (179 entries)\n", encoding="utf-8")
    (ld / "profile_hashes.txt").write_text("tyler.json: restored (hash as before the install)\n", encoding="utf-8")
    (ld / "arm.txt").write_text((arm or f"S1 seed {seed} launch {n}, add-on {sm.addon_id(n)}, plan") + "\n",
                                encoding="utf-8")


# ==================================================================================================== CLI

def main(argv: list[str]) -> int:
    args = list(argv)
    if "--selftest" in args:
        return selftest()
    flags = {f: f in args for f in ("--allow-partial", "--baseline", "--smoke", "--stalls")}
    args = [a for a in args if a not in flags]
    opts = {"--seed": None, "--gamedb": None, "--perms": str(N_PERMS)}
    for k in list(opts):
        if k in args:
            i = args.index(k)
            if i + 1 >= len(args):
                print(__doc__)
                return 2
            opts[k] = args[i + 1]
            del args[i:i + 2]
    if len(args) != 1 or sum(flags[f] for f in ("--baseline", "--smoke", "--stalls")) > 1:
        print(__doc__)
        return 2
    batch = Path(args[0])
    gamedb = int(opts["--gamedb"]) if opts["--gamedb"] else None
    if flags["--baseline"]:
        return run_baseline(batch, gamedb)
    if flags["--smoke"]:
        return run_smoke(batch)
    if flags["--stalls"]:
        return run_stalls(batch)
    return run(batch, gamedb, opts["--seed"], int(opts["--perms"]), flags["--allow-partial"])


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
