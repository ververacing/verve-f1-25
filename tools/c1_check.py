"""C-1 start calibration: start-only validity and the analysis (docs/verve_c1_prereg.md). Offline: reads a finished
batch only.

Usage:
    python -I tools/c1_check.py runs/<batch> [--seed <S>] [--allow-partial]
    python -I tools/c1_check.py runs/<batch> --smoke             # the stock smoke test (1 launch, 4 starts, no add-on)
    python -I tools/c1_check.py --selftest [--real runs/2026-11-17-D1/launch_1]

Batch layout (tools/v1_run.ps1 -Make c1, one call per launch): <batch>/launch_<n>/gen/assignment.csv (driver, team,
arm stock / 0.20 / 0.35 / 0.65; tools/c1_make.py) and gen/expected_ops.csv, raw/udp.bin (every start of the launch, one
race-session uid each), raw/loader.log, weather.txt, check_applied.txt / gamedb_expected.txt, session_check.txt
(the plan's race-1 `@sessioncheck`), udp_starts.txt (`@startwait`), transcript.txt (the saves guard), arm.txt
("C1 seed <S> launch <n>, ...") and invalid.txt if the session check failed. The smoke test (v1_run -StockSmoke) has
no gen/ and arm.txt "SMOKE ...". Writes <batch>/c1_check/{summary.json, per_start.csv, per_car_launch.csv}.

START-ONLY VALIDITY per start uid (a start-only variant of tools/aionly_check.py; the starts are the capture's race
sessions with a lights-out event, LGOT, in capture order; the window is LGOT to LGOT + CUTOFF_S 20 s, wall time of
arrival). A start counts only if:
  (a) the launch's race-1 session check holds: session_check.txt reads `session ok` for race 1's uid (an `unverified`
      check is redone offline on race 1's Session packet at lights out: difficulty 100, track 17, weather 0), and
      there is no invalid.txt;
  (b) the player car (header playerCarIndex, car 19) has no COLL (as vehicle or other) and no PENA (as vehicle) in
      the window (the Event packets);
  (c) all 19 AI cars move: a LapData totalDistance gain >= MOVE_M (0.3 m) over the last pre-LGOT frame by the cutoff;
  (d) weather.txt reads LOCKED;
  (e) the uid is new in the launch (a uid listed more than once in udp_starts.txt is not);
  (f) the capture covers the window with no gap > GAP_S (5 s) between the uid's packets (LGOT to the first packet,
      packet to packet, the last packet to the cutoff).
Also per launch, as approved (every start of the launch dropped otherwise): the build check (check_applied.txt: all
of the launch's ops applied, 56 or 52, 0 problems; the loader's gamedb count = gamedb_expected.txt), and the saves
guard (the shell's `saves unchanged`, or a deferred check `checked late: unchanged`). The 19 participants must map to
the roster. The finish, plausible-finish and lap checks don't apply: every start prints "finish checks: not
applicable (start-only)".

MEASURES (v1_check.start_measures, by import: the reference implementation): reaction_s (LGOT arrival to the car's
first LapData totalDistance gain >= MOVE_M, 1/60 s), launch_m (distance in the 2.0 s after its own first movement),
speed_1s_kph (CarTelemetry speed 1 s after LGOT), gain_t1 (grid - LapData position when lap-1 lapDistance first
reaches T1_M 345 m, all inside the cutoff). Per launch: each car's mean over the launch's valid starts, then the mean
over the arm's cars.

ANALYSIS (the prereg, approved; only these are scored):
- The calibration line: per launch an OLS fit of the three level means of reaction_s on the pinned value
  (0.20 / 0.35 / 0.65): slope b_L, intercept a_L. Pooled = the mean over the 2 launches, SE = |b1 - b2| / 2.
- Low end: RESOLVED if 0.20 reads >= RESOLVED_S (0.075 s) below 0.35 in both launches; else FLOOR, and the slope is
  refit on 0.35 / 0.65 (that refit is then the line).
- Offset criterion on the line's slope: CONSTANT if within 1 +/- 0.1 in both launches and pooled; GROWS if > 1.1 in
  both and pooled; SHRINKS if < 0.9 in both and pooled; otherwise MIXED.
- Shape: LINEAR if the 0.35 mean is within +/- 0.02 s of the chord from 0.20 to 0.65 in both launches; else CURVED
  (the two segment slopes reported).
- Reproduction (not scored, reported FIRST): the 0.65 level within one frame (0.017 s) of D1's 0.936 s (0.9363), in
  both launches. If not, the start-only route has changed the chain, and no calibration claim stands before review.
- For V-2 (reported, not scored): the offset per level (mean - value), launch_m per level ("pure delay" if the three
  level means are within 0.5 m in both launches), the stock distribution (car-start values, the per-start fastest
  stock car), and the median per-start fastest stock reaction and the stock median, each inverted through the
  pooled line to a game-time value. Secondaries (speed_1s_kph, gain_t1): per level, not scored.
NOT SCORED: fewer than the 2 launches (without --allow-partial: refused, exit 3; no interim looks), or a launch with
no level mean for one of the three levels.

--smoke (before C-1, not scored): launch_1 only, stock (no add-on, arm.txt "SMOKE"), race 1 + 3 restarts. SMOKE PASS
needs all of: (1) a new uid each start (4 starts, 4 distinct uids, udp_starts.txt lists exactly them, exit 0);
(2) the same grid in every start (LapData gridPosition per driver, the last pre-LGOT frame); (3) the player re-parked
each start (car 19's LapData driverStatus 0, in the garage, in every frame of the window, and no totalDistance gain
>= MOVE_M; the loader's "GARAGE: car 19 sent" lines are reported); (4) 4/4 start-only PASS; (5) a clean end with no
finish needed (transcript `result: plan done`, the quit sent, the saves guard, cleanup.txt and post_run_check.txt,
no @udpfinish). Exit 0 SMOKE PASS, 1 SMOKE FAIL.
Exit 0 done (any C-1 verdict), 2 usage, 3 refused (partial without --allow-partial, assignment problems, not a C-1 or
smoke launch).
"""
from __future__ import annotations

import csv
import io
import json
import random
import re
import statistics
import struct
import sys
import tempfile
from collections import Counter
from contextlib import redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import c1_make as cm  # noqa: E402
import udp_parse as u  # noqa: E402
import v1_check as vc  # noqa: E402

N_LAUNCHES = 2
STARTS_PER_LAUNCH = 20       # race 1 + 19 restarts (fixed before launch 1)
SMOKE_STARTS = 4             # race 1 + 3 restarts
CUTOFF_S = 20.0              # the window: LGOT to LGOT + 20 s (fixed; D1's slowest T1 crossing 9.11-9.34 s)
GAP_S = 5.0                  # (f): aionly_check's live-window rule, ending at the cutoff
RACE_TYPES = (15, 16, 17)
WANT_SESSION = (100, 17, 0)  # (a): AI difficulty, track id (Austria), weather (clear), as @sessioncheck 100 17 0
GAMEDB_BASE = 56             # verve-test's baseline overwrite count (v1_run's check_applied -Baseline 56)
LEVEL_X = [cm.LEVELS[k] for k in (1, 2, 3)]
SLOPE_ONE, SLOPE_TOL = 1.0, 0.1
LINEAR_BAND_S = 0.02         # V-1's reaction band
RESOLVED_S = 0.075           # half the 0.15 s step from 0.20 to 0.35
PURE_DELAY_M = 0.5           # V-1's launch_m band
D1_065_S = 0.9363            # D1: all 18 pinned car-launches at 0.65
FRAME_S = 0.017              # one frame, as the prereg rounds it
PRIMARY = "reaction_s"
SECONDARY = {"launch_m": "m", "speed_1s_kph": "km/h", "gain_t1": "places"}
MEASURES = [PRIMARY] + list(SECONDARY)
NA_LINE = "finish checks: not applicable (start-only)"
PARTIAL = "NOT SCORED (partial)"
ROSTER = cm.ROSTER
ARM_LABEL = cm.ARMS
GARAGE_LINE = re.compile(r"GARAGE: car (\d+) sent to the garage")


# ==================================================================================================== one pass per capture

def scan_starts(path: Path, cutoff: float = CUTOFF_S) -> dict[int, dict]:
    """One pass over a launch's capture: per session uid, its type and track, the LGOT arrival (wall), the Session
    values (difficulty, track, weather) at or after LGOT and the latest, the participants, the last LapData frame
    before LGOT (raw), and in the window LGOT..LGOT + cutoff: each car's largest totalDistance gain over that frame,
    the player's driverStatus values, each car's lap-1 position at lapDistance T1_M, the COLL/PENA events (seconds
    after LGOT, udp_parse's fields) and the largest gap between the uid's packets (wall)."""
    out: dict[int, dict] = {}
    for wall, p in u.records(path):
        if len(p) < u.HEADER.size:
            continue
        fmt, _, _, _, _, pid, uid, _, _, _, player, player2 = u.HEADER.unpack_from(p, 0)
        d = out.get(uid)
        if d is None:
            d = out[uid] = {"uid": uid, "first_wall": wall, "type": None, "track": None, "player": player,
                            "lgot_wall": None, "sess_at_lgot": None, "sess_latest": None, "parts": None,
                            "n_active": None, "n_cars": None, "pre_body": None, "pre": None, "gain": {},
                            "player_dstatus": Counter(), "t1": {}, "last_in": None, "max_gap": 0.0, "gap_at": None,
                            "events": [], "n_lap_in": 0}
        lay = u.LAYOUTS.get(fmt)
        if lay is None:
            continue
        n = d["n_cars"] = lay["cars"]
        body = p[u.HEADER.size:]
        lg = d["lgot_wall"]
        inwin = lg is not None and wall <= lg + cutoff
        if inwin:
            prev = d["last_in"]
            if wall - prev > d["max_gap"]:
                d["max_gap"], d["gap_at"] = wall - prev, prev - lg
            d["last_in"] = max(prev, wall)
        if pid == 1 and len(body) > u.S_TRACK:
            d["type"], d["track"] = body[u.S_TYPE], struct.unpack_from("<b", body, u.S_TRACK)[0]
            if len(body) > u.S_AI_DIFFICULTY and body[u.S_AI_DIFFICULTY]:
                vals = (body[u.S_AI_DIFFICULTY], d["track"], body[u.S_WEATHER])
                d["sess_latest"] = vals
                if lg is not None and d["sess_at_lgot"] is None:
                    d["sess_at_lgot"] = vals
        elif pid == 3 and len(body) >= 4:
            code = body[:4]
            if code == b"LGOT" and lg is None:
                d["lgot_wall"] = d["last_in"] = wall
                if d["pre_body"] is not None:
                    d["pre"] = [u.LAP.unpack_from(d["pre_body"], c * u.LAP.size) for c in range(n)]
            elif code in (b"COLL", b"PENA") and inwin:
                name = code.decode("ascii")
                d["events"].append((round(wall - lg, 3), name, u.event_fields(name, body[4:])))
        elif pid == 4 and d["parts"] is None and len(body) == 1 + n * lay["part_size"]:
            d["n_active"] = body[0]
            parts = []
            for c in range(n):
                ai, drv, _, _, _, _, _, name = lay["part"].unpack_from(body, 1 + c * lay["part_size"])
                human = u.is_human(c, ai, drv, player, player2, lay["unknown_driver"])
                parts.append({"ai": ai, "name": "player" if human else name.split(b"\0", 1)[0].decode("utf-8", "replace")})
            d["parts"] = parts
        elif pid == 2 and len(body) == n * u.LAP.size + 2:
            if lg is None:
                d["pre_body"] = body          # unpacked only at LGOT (most sessions never reach one)
            elif inwin:
                d["n_lap_in"] += 1
                cars = [u.LAP.unpack_from(body, c * u.LAP.size) for c in range(n)]
                if d["pre"] is None:
                    d["pre"] = cars
                for c in range(n):
                    g = cars[c][u.L_TOTDIST] - d["pre"][c][u.L_TOTDIST]
                    if g > d["gain"].get(c, float("-inf")):
                        d["gain"][c] = g
                    if c not in d["t1"] and cars[c][u.L_LAPNUM] == 1 and cars[c][u.L_LAPDIST] >= vc.T1_M:
                        d["t1"][c] = cars[c][u.L_POS]
                if d["player"] < n:
                    d["player_dstatus"][cars[d["player"]][u.L_DSTATUS]] += 1
    for d in out.values():
        d.pop("pre_body", None)
    return out


def start_uids(scan: dict[int, dict]) -> list[int]:
    """Race sessions with a lights-out event, in capture order."""
    return [d["uid"] for d in sorted(scan.values(), key=lambda x: x["first_wall"])
            if d["type"] in RACE_TYPES and d["lgot_wall"] is not None]


# ==================================================================================================== the launch's files

def text_of(p: Path) -> str:
    return p.read_text(encoding="utf-8-sig", errors="replace") if p.exists() else ""


def read_starts_file(ld: Path) -> list[dict] | None:
    """udp_starts.txt (sandbox_shell's @startwait): [{"start", "exit", "uid"}], or None if there is none."""
    p = ld / "udp_starts.txt"
    if not p.exists():
        return None
    rows = []
    for ln in text_of(p).splitlines():
        m = re.match(r"\s*start (\d+) \S+ exit (-?\d+) uid (\d+|-)", ln)
        if m:
            rows.append({"start": int(m[1]), "exit": int(m[2]), "uid": m[3]})
    return rows


def build_problems(ld: Path, n_ops: int) -> list[str]:
    """The per-launch build check: check_applied.txt with every op applied and 0 problems, and the loader's gamedb
    overwrite count = gamedb_expected.txt (else the baseline + the ops)."""
    ca = ld / "check_applied.txt"
    if not ca.exists():
        return ["build: no check_applied.txt (the build check never ran)"]
    t = text_of(ca)
    probs = []
    if not re.search(r"(?<!\d)0 problem\(s\)", t) or "DIFFERS" in t:
        probs.append("build: check_applied.txt found problems")
    m = re.search(r"ops (\d+): (\d+) applied", t)
    if not m or int(m[1]) != n_ops or int(m[2]) != n_ops:
        probs.append(f"build: check_applied.txt reads {m[0] if m else 'no ops line'!r}, expected all {n_ops} ops applied")
    try:
        want = int(text_of(ld / "gamedb_expected.txt").strip())
    except ValueError:
        want = GAMEDB_BASE + n_ops
    db = re.search(r"gamedb: (\d+) overwritten", text_of(ld / "raw" / "loader.log"))
    if not db or int(db[1]) != want:
        probs.append(f"build: loader.log gamedb {db[1] if db else 'none'} overwritten, expected {want}")
    return probs


def saves_guard(ld: Path) -> tuple[bool, str]:
    tr = text_of(ld / "transcript.txt")
    if "SAVES CHANGED" in tr:
        return False, "saves: SAVES CHANGED (transcript.txt)"
    if "saves unchanged (" in tr:
        return True, "saves unchanged"
    late = text_of(ld / "saves_diff_deferred.txt").strip().splitlines()
    if late and late[0].startswith("checked late") and "unchanged" in late[0]:
        return True, "saves checked late: unchanged"
    if late:
        return False, f"saves: the check is deferred ({late[0][:60]})"
    return False, "saves: no saves check on record (no `saves unchanged` in transcript.txt)"


def session_problems(ld: Path, scan: dict[int, dict], race1: int | None) -> tuple[list[str], str]:
    """(a): the launch's race-1 session check, and invalid.txt. Returns (problems, note)."""
    probs = []
    inv = ld / "invalid.txt"
    if inv.exists():
        probs.append(f"(a) the launch is marked invalid.txt ({(text_of(inv).strip().splitlines() or ['(empty)'])[0]})")
    sc = ld / "session_check.txt"
    line = (text_of(sc).strip().splitlines() or [""])[0].strip()
    note = line
    if not sc.exists():
        probs.append("(a) no session_check.txt (the plan never reached @sessioncheck)")
    elif line.startswith("session ok"):
        m = re.search(r"uid (\d+)", line)
        if race1 is not None and (not m or int(m[1]) != race1):
            probs.append(f"(a) the session check read uid {m[1] if m else '?'}, not race 1's uid {race1}")
    elif line.startswith("unverified"):
        d = scan.get(race1) if race1 is not None else None
        vals = (d["sess_at_lgot"] or d["sess_latest"]) if d else None
        if vals is None:
            probs.append(f"(a) the session check was unverified ({line}) and race 1 has no Session packet to redo it")
        elif tuple(vals) != WANT_SESSION:
            probs.append(f"(a) the session check was unverified; offline race 1 reads difficulty {vals[0]} track "
                         f"{vals[1]} weather {vals[2]}, expected {WANT_SESSION}")
        else:
            note = f"{line} -> redone offline on race 1's Session packet: difficulty {vals[0]} track {vals[1]} weather {vals[2]}"
    else:
        probs.append(f"(a) the race-1 session check does not hold: {line or '(empty)'}")
    return probs, note


def weather_problems(ld: Path) -> list[str]:
    wx = ld / "weather.txt"
    t = text_of(wx)
    if not t.startswith("weather: LOCKED"):
        return ["(d) weather: " + ((t.splitlines() or ["(empty)"])[0] if wx.exists() else "no weather.txt")]
    return []


# ==================================================================================================== one launch

def process_launch(n: int, ld: Path, n_ops: int, cutoff: float = CUTOFF_S, log=print) -> dict:
    """Every start of one launch: the start-only validity and, for every start, the measures per roster driver."""
    cap = ld / "raw" / "udp.bin"
    scan = scan_starts(cap, cutoff)
    vscan = vc.scan_capture(cap)
    uids = start_uids(scan)
    launch_probs = build_problems(ld, n_ops)
    ok_saves, saves_note = saves_guard(ld)
    if not ok_saves:
        launch_probs.append(saves_note)
    a_probs, a_note = session_problems(ld, scan, uids[0] if uids else None)
    launch_probs += a_probs + weather_problems(ld)
    listed = read_starts_file(ld)
    listed_n = Counter(r["uid"] for r in listed or [])
    starts = []
    for k, uid in enumerate(uids, 1):
        d = scan[uid]
        player = d["player"]
        n_cars = d["n_active"] or d["n_cars"] or 20
        cmap, map_probs = vc.map_drivers(d["parts"], n_cars, player)
        reasons = list(launch_probs) + [f"participants: {x}" for x in map_probs]
        if listed_n.get(str(uid), 0) > 1:
            reasons.append(f"(e) uid {uid} listed {listed_n[str(uid)]} times in udp_starts.txt: not a new start")
        pv = [t for t, code, f in d["events"] if code == "COLL" and player in (f.get("vehicle"), f.get("other"))]
        pp = [t for t, code, f in d["events"] if code == "PENA" and f.get("vehicle") == player]
        if pv:
            reasons.append(f"(b) COLL with the player car at +{', +'.join(f'{t:.1f}' for t in pv)} s")
        if pp:
            reasons.append(f"(b) PENA for the player car at +{', +'.join(f'{t:.1f}' for t in pp)} s")
        still = [cmap[c] for c in sorted(cmap) if d["gain"].get(c, float("-inf")) < vc.MOVE_M]
        if len(cmap) != 19 or still:
            reasons.append(f"(c) {19 - len(still) if len(cmap) == 19 else len(cmap) - len(still)} of 19 AI cars moved "
                           f">= {vc.MOVE_M} m by the cutoff" + (f" (not: {', '.join(still)})" if still else ""))
        end_gap = d["lgot_wall"] + cutoff - d["last_in"]
        gap, at = (end_gap, d["last_in"] - d["lgot_wall"]) if end_gap > d["max_gap"] else (d["max_gap"], d["gap_at"])
        if gap > GAP_S:
            reasons.append(f"(f) capture gap {gap:.1f} s after LGOT + {at:.1f} s (window LGOT to + {cutoff:g} s)")
        st = vc.start_measures(vscan[uid], sorted(cmap)) if uid in vscan else {}
        drivers = {}
        for c, drv in cmap.items():
            v = dict(st.get(c, {}))
            g = v.get("grid")
            t1 = d["t1"].get(c)
            v["gain_t1"] = g - t1 if g and t1 else None
            v["car"] = c
            drivers[drv] = v
        pre = d["pre"] or []
        grid = tuple(sorted((pre[c][u.L_GRID], drv) for c, drv in cmap.items() if c < len(pre)))
        pl_gain = d["gain"].get(player)
        start = {"launch": n, "start": k, "uid": str(uid), "valid": not reasons, "verdict": "INVALID" if reasons else "PASS",
                 "reasons": reasons, "drivers": drivers, "grid": grid, "player": player,
                 "player_dstatus": dict(d["player_dstatus"]), "player_gain_m": None if pl_gain is None else round(pl_gain, 3),
                 "max_gap_s": round(gap, 2), "player_events": {"COLL": pv, "PENA": pp},
                 "listed": listed_n.get(str(uid), 0) if listed is not None else None,
                 "session_info": d["sess_at_lgot"] or d["sess_latest"]}
        log(f"  launch {n} start {k} uid {uid}: {start['verdict']}" + (f" ({'; '.join(reasons)})" if reasons else ""))
        log(f"    {NA_LINE}")
        starts.append(start)
    return {"launch": n, "starts": starts, "launch_problems": launch_probs, "session_note": a_note,
            "saves_note": saves_note, "listed": listed, "uids": [str(x) for x in uids]}


# ==================================================================================================== the analysis

def car_means(launch: dict, measure: str) -> dict[str, tuple[float, int]]:
    """{driver: (mean over the launch's valid starts, starts)}."""
    vals: dict[str, list[float]] = {}
    for s in launch["starts"]:
        if not s["valid"]:
            continue
        for drv, v in s["drivers"].items():
            if v.get(measure) is not None:
                vals.setdefault(drv, []).append(v[measure])
    return {d: (statistics.fmean(x), len(x)) for d, x in vals.items()}


def level_means(launch: dict, arm: dict[str, int], measure: str) -> dict[int, dict]:
    """{arm index: {"mean", "n_cars"}}: a car's mean over its valid starts first, then the mean over the arm's cars."""
    cm_ = car_means(launch, measure)
    out = {}
    for k in range(4):
        xs = [cm_[d][0] for d in ROSTER if arm[d] == k and d in cm_]
        out[k] = {"mean": statistics.fmean(xs) if xs else None, "n_cars": len(xs)}
    return out


def ols(xs: list[float], ys: list[float]) -> tuple[float, float]:
    """(intercept, slope)."""
    mx, my = statistics.fmean(xs), statistics.fmean(ys)
    b = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sum((x - mx) ** 2 for x in xs)
    return my - b * mx, b


def offset_class(slopes: list[float]) -> str:
    if all(abs(b - SLOPE_ONE) <= SLOPE_TOL + 1e-12 for b in slopes):
        return "CONSTANT"
    if all(b > SLOPE_ONE + SLOPE_TOL for b in slopes):
        return "GROWS"
    if all(b < SLOPE_ONE - SLOPE_TOL for b in slopes):
        return "SHRINKS"
    return "MIXED"


def launch_fit(lv: dict[int, dict]) -> dict | None:
    """The per-launch line and shape numbers from the reaction level means (None if a level has no mean)."""
    ys = [lv[k]["mean"] for k in (1, 2, 3)]
    if any(y is None for y in ys):
        return None
    y20, y35, y65 = ys
    a, b = ols(LEVEL_X, ys)
    chord = y20 + (y65 - y20) * (0.35 - 0.20) / (0.65 - 0.20)
    bf = (y65 - y35) / (0.65 - 0.35)
    return {"a": a, "b": b, "low_end_s": y35 - y20, "resolved": y35 - y20 >= RESOLVED_S - 1e-12,
            "chord_dev_s": y35 - chord, "linear": abs(y35 - chord) <= LINEAR_BAND_S + 1e-12,
            "segment_slopes": [(y35 - y20) / 0.15, bf], "floor_fit": {"a": y35 - bf * 0.35, "b": bf},
            "repro_dev_s": y65 - D1_065_S, "reproduced": abs(y65 - D1_065_S) <= FRAME_S + 1e-12,
            "offsets_s": {ARM_LABEL[k]: lv[k]["mean"] - cm.LEVELS[k] for k in (1, 2, 3)}}


def stock_values(launch_data: dict[int, dict], arms: dict[int, dict[str, int]]) -> tuple[list[float], list[float]]:
    """(every stock car-start reaction, the per-start fastest stock reaction), over the valid starts of all launches."""
    allv, fastest = [], []
    for n, L in launch_data.items():
        for s in L["starts"]:
            if not s["valid"]:
                continue
            xs = [v[PRIMARY] for drv, v in s["drivers"].items() if arms[n][drv] == 0 and v.get(PRIMARY) is not None]
            allv += xs
            if xs:
                fastest.append(min(xs))
    return allv, fastest


def analyse(launch_data: dict[int, dict], arms: dict[int, dict[str, int]], partial: bool = False) -> dict:
    """The C-1 analysis from per-launch start tables (launch_data[n] = {"starts": [{"valid", "drivers": {driver:
    {measure: value}}}]}, as process_launch returns them); arms[n] = {driver: arm index}."""
    per = {}
    for n, L in sorted(launch_data.items()):
        lv = {m: level_means(L, arms[n], m) for m in MEASURES}
        per[n] = {"starts_valid": sum(s["valid"] for s in L["starts"]), "starts_total": len(L["starts"]),
                  "levels": {m: {ARM_LABEL[k]: v for k, v in lv[m].items()} for m in MEASURES},
                  "fit": launch_fit(lv[PRIMARY])}
        lm = [lv["launch_m"][k]["mean"] for k in (1, 2, 3)]
        per[n]["launch_m_range_m"] = (max(lm) - min(lm)) if all(x is not None for x in lm) else None
    need = list(range(1, N_LAUNCHES + 1))
    have = [n for n in need if n in per]
    unread = [n for n in have if per[n]["fit"] is None]
    res = {"per_launch": per, "ignored_launches": sorted(set(per) - set(need))}
    if partial or len(have) < N_LAUNCHES:
        res["verdict"] = PARTIAL if partial else "NOT SCORED"
        res["why"] = f"{len(have)} of {N_LAUNCHES} launches"
    elif unread:
        res["verdict"], res["why"] = "NOT SCORED", f"launch(es) {unread}: a level (0.20 / 0.35 / 0.65) has no valid car"
    fits = {n: per[n]["fit"] for n in have if per[n]["fit"] is not None}
    if len(fits) == N_LAUNCHES:
        f1, f2 = fits[1], fits[2]
        resolved = f1["resolved"] and f2["resolved"]
        line = {n: ({"a": f["a"], "b": f["b"]} if resolved else f["floor_fit"]) for n, f in fits.items()}
        b1, b2 = line[1]["b"], line[2]["b"]
        pooled = {"a": (line[1]["a"] + line[2]["a"]) / 2, "b": (b1 + b2) / 2, "se_b": abs(b1 - b2) / 2,
                  "source": "OLS on 0.20 / 0.35 / 0.65" if resolved else "FLOOR: refit on 0.35 / 0.65"}
        res.update({
            "low_end": "RESOLVED" if resolved else "FLOOR",
            "line": {str(n): v for n, v in line.items()}, "pooled": pooled,
            "offset": offset_class([b1, b2, pooled["b"]]),
            "shape": "LINEAR" if f1["linear"] and f2["linear"] else "CURVED",
            "reproduction": "REPRODUCED" if f1["reproduced"] and f2["reproduced"] else "NOT REPRODUCED"})
        rngs = [per[n]["launch_m_range_m"] for n in need]
        res["launch_m"] = ("pure delay" if all(r is not None and r <= PURE_DELAY_M + 1e-12 for r in rngs)
                           else "not pure delay: the per-level launch_m is V-2's second input")
        if "verdict" not in res:
            res["verdict"], res["why"] = res["offset"], f"slopes {b1:.3f} / {b2:.3f}, pooled {pooled['b']:.3f}"
    allv, fastest = stock_values({n: launch_data[n] for n in have}, arms)
    stock = {"car_starts": len(allv), "starts": len(fastest)}
    if allv:
        stock.update({"min": min(allv), "median": statistics.median(allv), "mean": statistics.fmean(allv),
                      "max": max(allv), "fastest_median": statistics.median(fastest) if fastest else None})
        p = res.get("pooled")
        if p and p["b"]:
            stock["median_game_s"] = (stock["median"] - p["a"]) / p["b"]
            if stock["fastest_median"] is not None:
                stock["fastest_median_game_s"] = (stock["fastest_median"] - p["a"]) / p["b"]
    res["stock"] = stock
    return res


# ==================================================================================================== the smoke test

def smoke_criteria(L: dict, ld: Path) -> list[tuple[str, bool, str]]:
    starts = L["starts"]
    uids = [s["uid"] for s in starts]
    listed = L["listed"] or []
    ok0 = [r["uid"] for r in listed if r["exit"] == 0]
    out = [("1. a new uid each start", len(starts) == SMOKE_STARTS and len(set(uids)) == len(uids)
            and ok0 == uids and len(listed) == SMOKE_STARTS,
            f"{len(starts)} starts, {len(set(uids))} distinct uids; udp_starts.txt: "
            f"{len(listed)} line(s), {len(ok0)} exit 0" + ("" if ok0 == uids else " (not the capture's uids)"))]
    grids = {s["grid"] for s in starts}
    out.append(("2. the same grid in every start (LapData gridPosition)", len(grids) == 1 and bool(starts)
                and all(len(g) == 19 for g in grids), f"{len(grids)} distinct grid(s)"))
    parked = [s["start"] for s in starts if set(s["player_dstatus"]) == {0} and s["player_gain_m"] is not None
              and s["player_gain_m"] < vc.MOVE_M]
    gl = GARAGE_LINE.findall(text_of(ld / "raw" / "loader.log"))
    pl = {str(s["player"]) for s in starts}
    out.append(("3. the player re-parked each start (driverStatus 0, not moving)",
                bool(starts) and len(parked) == len(starts),
                f"parked in {len(parked)}/{len(starts)} starts; loader 'GARAGE: car {'/'.join(sorted(pl))} sent' lines: "
                f"{sum(1 for c in gl if c in pl)} (reported)"))
    npass = sum(s["valid"] for s in starts)
    out.append(("4. start-only check: all starts PASS", npass == SMOKE_STARTS == len(starts),
                f"{npass}/{len(starts)} PASS"))
    tr = text_of(ld / "transcript.txt")
    ok_saves, note = saves_guard(ld)
    end = {"plan done": "result: plan done" in tr, "quit sent": bool(re.search(r"> quit\b", tr)), "saves guard": ok_saves,
           "cleanup.txt": (ld / "cleanup.txt").exists(), "post_run_check.txt": (ld / "post_run_check.txt").exists(),
           "no @udpfinish": not list(ld.glob("udpfinish_race*.txt"))}
    out.append(("5. a clean end with no finish needed", all(end.values()),
                ", ".join(f"{k} {'yes' if v else 'NO'}" for k, v in end.items())))
    return out


# ==================================================================================================== the batch

def seed_of(ld: Path, arg: str | None) -> tuple[int | None, str]:
    """The seed from --seed or arm.txt ("C1 seed <S> launch <n>, ..."); a problem if they disagree or arm isn't C1."""
    arm = ld / "arm.txt"
    s = None
    if arm.exists():
        t = text_of(arm)
        m = re.match(r"\s*C1 seed (-?\d+) launch (\d+)", t)
        if not m:
            return None, f"arm.txt is not a C1 launch: {t.strip()[:60]!r}"
        s = int(m[1])
    if arg is not None:
        if s is not None and s != int(arg):
            return None, f"--seed {arg} disagrees with arm.txt seed {s}"
        s = int(arg)
    return s, ""


def assignment_of(n: int, ld: Path, seed_arg: str | None) -> tuple[dict[str, int] | None, list[str], int]:
    """(arm per driver, problems, the expected op count)."""
    try:
        arm = cm.read_assignment(ld / "gen" / "assignment.csv")
    except (KeyError, ValueError) as e:
        return None, [f"gen/assignment.csv unreadable as a C-1 assignment ({e!r})"], 0
    probs = cm.assignment_problems(arm)
    if probs:
        return None, probs, 0
    exp = ld / "gen" / "expected_ops.csv"
    if not exp.exists():
        return None, ["no gen/expected_ops.csv"], 0
    with exp.open(encoding="utf-8", newline="") as f:
        got = sorted((r["path"], r["field"], r["value"]) for r in csv.DictReader(f))
    if got != sorted((o["select"], o["field"], o["value"]) for o in cm.build_ops(arm)):
        return None, ["gen/expected_ops.csv does not match the assignment's arms"], 0
    seed, why = seed_of(ld, seed_arg)
    if why:
        return None, [why], 0
    if seed is not None and arm != cm.draw(seed, n):
        return None, [f"gen/assignment.csv is not c1_make.draw({seed}, {n})"], 0
    return arm, [], len(got)


def fnum(x, nd=3, unit=""):
    return "n/a" if x is None else f"{x:+.{nd}f}{unit}"


def report(res: dict, head: list[str]) -> list[str]:
    lines = list(head)
    if "reproduction" in res:
        per = res["per_launch"]
        devs = ", ".join(f"launch {n} {per[n]['levels'][PRIMARY]['0.65']['mean']:.4f} s ({fnum(per[n]['fit']['repro_dev_s'], 4)})"
                         for n in sorted(per) if per[n]["fit"])
        lines.append(f"REPRODUCTION (not scored, first): 0.65 vs D1's {D1_065_S} s within {FRAME_S} s: "
                     f"{res['reproduction']} ({devs})")
        if res["reproduction"] != "REPRODUCED":
            lines.append("  the start-only route has changed the chain: reported before any calibration claim")
    for n, v in sorted(res["per_launch"].items()):
        lines.append(f"  launch {n}: {v['starts_valid']}/{v['starts_total']} starts valid")
        for m in MEASURES:
            unit = "s" if m == PRIMARY else SECONDARY[m]
            cells = ", ".join(f"{lab} {'n/a' if c['mean'] is None else format(c['mean'], '.3f')} ({c['n_cars']})"
                              for lab, c in v["levels"][m].items())
            lines.append(f"    {m} ({unit}) per level (cars): {cells}" + ("" if m == PRIMARY else "  [not scored]"))
        f = v["fit"]
        if f:
            lines.append(f"    line: reaction = {f['a']:.4f} + {f['b']:.4f} x value; offsets "
                         + ", ".join(f"{k} {fnum(x, 4)}" for k, x in f["offsets_s"].items()))
            lines.append(f"    low end: 0.35 - 0.20 = {f['low_end_s']:.4f} s ({'>=' if f['resolved'] else '<'} {RESOLVED_S}); "
                         f"0.35 vs the chord {fnum(f['chord_dev_s'], 4)} s ({'within' if f['linear'] else 'outside'} "
                         f"+/-{LINEAR_BAND_S}); segment slopes {f['segment_slopes'][0]:.3f} / {f['segment_slopes'][1]:.3f}")
        if v["launch_m_range_m"] is not None:
            lines.append(f"    launch_m: the three level means span {v['launch_m_range_m']:.2f} m")
    if "pooled" in res:
        p = res["pooled"]
        lines.append(f"  low end: {res['low_end']}; line: {p['source']}; slopes launch 1 {res['line']['1']['b']:.4f}, "
                     f"launch 2 {res['line']['2']['b']:.4f}, pooled {p['b']:.4f} (SE {p['se_b']:.4f}), intercept "
                     f"{p['a']:.4f}")
        lines.append(f"  offset criterion (1 +/- {SLOPE_TOL} in both launches and pooled): {res['offset']}")
        lines.append(f"  shape: {res['shape']}" + ("" if res["shape"] == "LINEAR" else
                                                    " (segment slopes per launch above)"))
        lines.append(f"  launch_m (not scored): {res['launch_m']}")
    st = res["stock"]
    if st.get("car_starts"):
        lines.append(f"  stock (not scored): {st['car_starts']} car-starts, reaction min {st['min']:.4f} / median "
                     f"{st['median']:.4f} / mean {st['mean']:.4f} / max {st['max']:.4f} s; per-start fastest stock car "
                     f"median {st['fastest_median']:.4f} s over {st['starts']} starts")
        if "median_game_s" in st:
            lines.append(f"  for V-2 (not scored): game time through the pooled line: stock median "
                         f"{st['median_game_s']:.4f} s, per-start fastest stock median "
                         f"{st.get('fastest_median_game_s', float('nan')):.4f} s")
    if res["ignored_launches"]:
        lines.append(f"  ignored: launch(es) {res['ignored_launches']} (the prereg has launches 1-{N_LAUNCHES})")
    lines.append(f"C-1 offset: {res['verdict']} ({res['why']})")
    return lines


def write_outputs(out: Path, launch_data: dict, arms: dict, js: dict) -> None:
    out.mkdir(parents=True, exist_ok=True)
    with (out / "per_start.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["launch", "start", "uid", "verdict", "reasons", "finish_checks", "max_gap_s", "player_dstatus",
                    "player_gain_m", "fastest_stock_reaction_s"])
        for n, L in sorted(launch_data.items()):
            for s in L["starts"]:
                xs = [v[PRIMARY] for d, v in s["drivers"].items() if arms[n].get(d) == 0 and v.get(PRIMARY) is not None]
                w.writerow([n, s["start"], s["uid"], s["verdict"], "; ".join(s["reasons"]), "not applicable (start-only)",
                            s["max_gap_s"], json.dumps(s["player_dstatus"]), s["player_gain_m"],
                            round(min(xs), 4) if xs else ""])
    with (out / "per_car_launch.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["launch", "driver", "team", "arm"] + [x for m in MEASURES for x in (m, f"{m}_starts")])
        for n, L in sorted(launch_data.items()):
            cms = {m: car_means(L, m) for m in MEASURES}
            for d in ROSTER:
                row = [n, d, cm.TEAM_OF[d], ARM_LABEL[arms[n][d]]]
                for m in MEASURES:
                    mu, k = cms[m].get(d, (None, 0))
                    row += ["" if mu is None else round(mu, 4), k]
                w.writerow(row)
    (out / "summary.json").write_text(json.dumps(js, indent=1, default=str) + "\n", encoding="utf-8")


def strip_starts(launch_data: dict) -> list[dict]:
    return [{k: s[k] for k in ("launch", "start", "uid", "verdict", "reasons", "max_gap_s", "player_dstatus",
                               "player_gain_m", "player_events", "listed")}
            for L in launch_data.values() for s in L["starts"]]


def run_smoke(batch: Path, quiet: bool = False) -> int:
    say = (lambda *a: None) if quiet else print
    ld = batch / "launch_1"
    if not (ld / "raw" / "udp.bin").exists():
        print(f"REFUSED: no {ld / 'raw' / 'udp.bin'}")
        return 3
    arm_t = text_of(ld / "arm.txt")
    if not arm_t.startswith("SMOKE"):
        print(f"REFUSED: launch_1/arm.txt is not a smoke launch ({arm_t.strip()[:60]!r})")
        return 3
    if (ld / "gen").exists():
        print("REFUSED: launch_1 has a gen/ folder: the smoke test runs with no add-on")
        return 3
    L = process_launch(1, ld, 0, log=say)
    crit = smoke_criteria(L, ld)
    ok = all(c[1] for c in crit)
    for name, good, detail in crit:
        say(f"  {'ok  ' if good else 'FAIL'} {name}: {detail}")
    arms = {1: {d: 0 for d in ROSTER}}
    allv, fastest = stock_values({1: L}, arms)
    if allv:
        say(f"  stock reaction (info): {len(allv)} car-starts, median {statistics.median(allv):.4f} s; per-start fastest "
            f"median {statistics.median(fastest):.4f} s")
    say(f"SMOKE {'PASS' if ok else 'FAIL'}")
    js = {"batch": str(batch), "mode": "smoke", "verdict": "SMOKE PASS" if ok else "SMOKE FAIL",
          "criteria": [{"name": n, "ok": g, "detail": d} for n, g, d in crit], "starts": strip_starts({1: L}),
          "launch_problems": L["launch_problems"], "session_check": L["session_note"],
          "constants": {"CUTOFF_S": CUTOFF_S, "GAP_S": GAP_S, "MOVE_M": vc.MOVE_M, "SMOKE_STARTS": SMOKE_STARTS}}
    write_outputs(batch / "c1_check", {1: L}, arms, js)
    return 0 if ok else 1


def run(batch: Path, seed_arg: str | None, allow_partial: bool, quiet: bool = False) -> int:
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
    arms, n_ops = {}, {}
    for n, ld in complete.items():
        a, probs, k = assignment_of(n, ld, seed_arg)
        if probs:
            print(pre(f"REFUSED: launch_{n}: {'; '.join(probs)}"))
            return 3
        arms[n], n_ops[n] = a, k
    launch_data = {}
    for n, ld in complete.items():
        L = process_launch(n, ld, n_ops[n], log=lambda s: say(pre(s)))
        if len(L["starts"]) != STARTS_PER_LAUNCH:
            say(pre(f"  launch {n}: {len(L['starts'])} starts in the capture, the prereg fixes {STARTS_PER_LAUNCH}"))
        launch_data[n] = L
    res = analyse(launch_data, arms, partial=allow_partial and not full)
    starts = [s for L in launch_data.values() for s in L["starts"]]
    meta = {"batch": str(batch), "mode": "c1", "launches": sorted(complete), "starts_total": len(starts),
            "starts_valid": sum(s["valid"] for s in starts),
            "arms": {n: {ARM_LABEL[k]: [d for d in ROSTER if a[d] == k] for k in range(4)} for n, a in arms.items()},
            "starts": strip_starts(launch_data),
            "session_check": {n: L["session_note"] for n, L in launch_data.items()},
            "constants": {"CUTOFF_S": CUTOFF_S, "GAP_S": GAP_S, "MOVE_M": vc.MOVE_M, "LAUNCH_S": vc.LAUNCH_S,
                          "SPEED_AT_S": vc.SPEED_AT_S, "T1_M": vc.T1_M, "SLOPE_TOL": SLOPE_TOL,
                          "LINEAR_BAND_S": LINEAR_BAND_S, "RESOLVED_S": RESOLVED_S, "PURE_DELAY_M": PURE_DELAY_M,
                          "D1_065_S": D1_065_S, "FRAME_S": FRAME_S, "N_LAUNCHES": N_LAUNCHES,
                          "STARTS_PER_LAUNCH": STARTS_PER_LAUNCH}}
    write_outputs(batch / "c1_check", launch_data, arms, {**meta, **res})
    head = [f"C-1 check {batch}: {len(complete)} launch(es), {meta['starts_valid']}/{len(starts)} starts valid"]
    for ln in report(res, head):
        say(pre(ln))
    say(pre(f"wrote {batch / 'c1_check' / 'summary.json'}, per_start.csv, per_car_launch.csv"))
    return 0


# ==================================================================================================== selftest

REC = struct.Struct("<dH")


def _pkt(wall: float, pid: int, uid: int, st: float, body: bytes) -> tuple[float, bytes]:
    h = u.HEADER.pack(2026, 25, 1, 27, 1, pid, uid, st, 0, 0, 19, 255)
    return wall, h + body


def _dist(t: float, a: float, vmax: float = 80.0) -> float:
    if t < 0:
        return 0.0
    if a * t <= vmax:
        return 0.5 * a * t * t
    t1 = vmax / a
    return 0.5 * a * t1 * t1 + vmax * (t - t1)


def write_synth_starts(path: Path, starts: list[dict], uid0: int, cutoff: float = CUTOFF_S) -> list[int]:
    """A capture of len(starts) starts in udp_parse's layouts: each start is v1_check.write_synth_capture's race (the
    session, participants, SSTA/LGOT, LapData at 60 Hz and CarTelemetry around the start, to LGOT + 6.5 s), shifted
    600 s per start, then LapData at 10 Hz to the window's end (end_s, default cutoff + 1.5 s). Per start:
    {"order": the grid (19 drivers), "react": {driver: s}, "accel": {driver: m/s2}, and optional "gap": (t0, t1) with
    no extension packets, "coll" / "pena" / "ai_coll": an Event at LGOT + 3 s, "player_moves": the player on track,
    "end_s"}. Returns the uids."""
    lay = u.LAYOUTS[2026]
    ncar = lay["cars"]
    recs, uids = [], []
    with tempfile.TemporaryDirectory() as tmp:
        for k, spec in enumerate(starts):
            uid = uid0 + k
            uids.append(uid)
            t = Path(tmp) / f"s{k}.bin"
            order, react, accel = spec["order"], spec["react"], spec["accel"]
            vc.write_synth_capture(t, order, {d: [react[d]] for d in ROSTER}, accel, uid)
            shift = 600.0 * k
            mine = [(w + shift, p) for w, p in u.records(t)]
            lg = vc.W0 + shift + 1.0
            end = spec.get("end_s") or cutoff + 1.5
            gap = spec.get("gap")
            i = 0
            while True:
                ts = 6.6 + 0.1 * i
                i += 1
                if ts > end:
                    break
                if gap and gap[0] <= ts < gap[1]:
                    continue
                body = b""
                for c in range(ncar):
                    td, ds = -8.0 * c, 0
                    if c < 19:
                        tt = ts - react[order[c]]
                        td += (0.35 + _dist(tt, accel[order[c]])) if tt >= -1e-9 else 0.0
                        ds = 4
                    elif c == 19 and spec.get("player_moves"):
                        td, ds = td + 5.0 * ts, 4
                    lap = [0] * 33
                    lap[u.L_LAPDIST], lap[u.L_TOTDIST] = float(td), float(td)
                    lap[u.L_POS], lap[u.L_LAPNUM], lap[u.L_GRID], lap[u.L_DSTATUS] = c + 1, 1, c + 1, ds
                    lap[u.L_RSTATUS] = 2
                    body += u.LAP.pack(*lap)
                mine.append(_pkt(lg + ts, 2, uid, ts, body + b"\0\0"))
            if spec.get("coll"):
                mine.append(_pkt(lg + 3.0, 3, uid, 3.0, b"COLL" + bytes([18, 19]) + bytes(10)))
            if spec.get("ai_coll"):
                mine.append(_pkt(lg + 3.0, 3, uid, 3.0, b"COLL" + bytes([6, 8]) + bytes(10)))
            if spec.get("pena"):
                mine.append(_pkt(lg + 4.0, 3, uid, 4.0, b"PENA" + bytes([5, 1, 19, 255, 0, 1, 0]) + bytes(5)))
            if spec.get("ai_pena"):
                mine.append(_pkt(lg + 4.0, 3, uid, 4.0, b"PENA" + bytes([5, 1, 7, 255, 0, 1, 0]) + bytes(5)))
            mine.sort(key=lambda r: r[0])
            recs += [REC.pack(w, len(p)) + p for w, p in mine]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"".join(recs))
    return uids


def synth_reactions(arm: dict[str, int], slope: float, rng: random.Random, at065: float = 0.936,
                    floor: float | None = None) -> dict[str, float]:
    """Per driver, one start's reaction (whole frames): a pinned car reads at065 + slope x (value - 0.65) (at least
    floor, if given), exactly as D1's pinned cars (no spread); a stock car 22-32 frames plus +/-2 frames."""
    out = {}
    for d in ROSTER:
        if arm[d]:
            y = at065 + slope * (cm.LEVELS[arm[d]] - 0.65)
            if floor is not None:
                y = max(y, floor)
            out[d] = round(y * 60) / 60
        else:
            out[d] = (rng.choice(range(22, 33)) + rng.choice((-2, -1, 0, 1, 2))) / 60
    return out


def write_synth_launch(ld: Path, n: int, specs: list[dict], seed: int | None = None, smoke: bool = False,
                       uid0: int | None = None) -> list[int]:
    """A launch folder as v1_run -Make c1 (or -StockSmoke) leaves it, with a synthetic capture."""
    ld.mkdir(parents=True, exist_ok=True)
    if smoke:
        n_ops = 0
        (ld / "arm.txt").write_text("SMOKE stock (no add-on) launch 1, harness\\sessions\\c1_smoke_4starts.plan\n",
                                    encoding="utf-8")
    else:
        n_ops = len(cm.write_launch(seed, n, ld / "gen"))
        (ld / "arm.txt").write_text(f"C1 seed {seed} launch {n}, add-on {cm.addon_id(n)}, "
                                    f"harness\\sessions\\c1_austria_20starts.plan\n", encoding="utf-8")
    uids = write_synth_starts(ld / "raw" / "udp.bin", specs, uid0 if uid0 is not None else 1000 * n)
    (ld / "raw" / "loader.log").write_text(
        f"[assets] gamedb: {GAMEDB_BASE + n_ops} overwritten, 322 created\n"
        "2026-11-17 01:42:46.741 [1] [spectator] off GARAGE: car 19 sent to the garage (start in the garage), call returned 0\n",
        encoding="utf-8")
    (ld / "weather.txt").write_text("weather: LOCKED\n", encoding="utf-8")
    (ld / "check_applied.txt").write_text(
        f"ops {n_ops}: {n_ops} applied ({n_ops} value-checked, 0 curves ...), 0 dropped as equal to stock (), 0 problem(s)\n"
        f"loader total {GAMEDB_BASE + n_ops} overwritten; expected {GAMEDB_BASE} + {n_ops} = {GAMEDB_BASE + n_ops}\n",
        encoding="utf-8")
    (ld / "gamedb_expected.txt").write_text(f"{GAMEDB_BASE + n_ops}\n", encoding="ascii")
    (ld / "session_check.txt").write_text(f"session ok uid {uids[0]}: difficulty 100 track 17 weather 0\n"
                                          "source: the first Session packet at or after lights out (LGOT)\nexit 0\n",
                                          encoding="utf-8")
    (ld / "udp_starts.txt").write_text("".join(f"start {k} 2026-11-18T10:{k:02d}:00 exit 0 uid {x} | udp start wait: "
                                               f"... | started uid {x}\n" for k, x in enumerate(uids, 1)),
                                       encoding="utf-8")
    (ld / "transcript.txt").write_text("attempt 1 started\nintro played (splash after 60 s)\n"
                                       "10:30:00 > quit  =>  {\"seq\":99,\"ok\":true}\nresult: plan done\n"
                                       "saves unchanged (179 entries)\n", encoding="utf-8")
    for f in ("cleanup.txt", "post_run_check.txt"):
        (ld / f).write_text("ok\n", encoding="utf-8")
    return uids


def selftest(real: Path | None = None) -> int:
    results, ok = [], True

    def chk(name: str, cond: bool, detail: str = "") -> None:
        nonlocal ok
        ok &= bool(cond)
        results.append(f"{'ok  ' if cond else 'FAIL'} {name}" + (f": {detail}" if detail else ""))

    seed = cm.PROPOSED_SEED
    arms = {n: cm.draw(seed, n) for n in (1, 2)}

    # ---- 1. the decision rules, on start tables injected below the parsing layer
    def tables(slope, at065=0.936, floor=None, curve=0.0, starts=3, rng_seed=5, slope2=None, lm=None):
        rng = random.Random(rng_seed)
        data = {}
        for n in (1, 2):
            ss = []
            for k in range(starts):
                r = synth_reactions(arms[n], slope2 if (slope2 is not None and n == 2) else slope, rng, at065, floor)
                drivers = {}
                for d in ROSTER:
                    rt = r[d] + (curve if arms[n][d] == 2 else 0.0)
                    lmv = (lm or {}).get(arms[n][d], 19.0)
                    drivers[d] = {"reaction_s": rt, "launch_m": lmv + rng.gauss(0, 0.05), "speed_1s_kph": 40 - 30 * rt,
                                  "gain_t1": rng.choice((-1, 0, 1))}
                ss.append({"launch": n, "start": k + 1, "uid": f"{n}{k}", "valid": True, "verdict": "PASS",
                           "reasons": [], "drivers": drivers})
            data[n] = {"launch": n, "starts": ss}
        return data
    for slope, want in ((1.0, "CONSTANT"), (1.2, "GROWS"), (0.8, "SHRINKS")):
        r = analyse(tables(slope), arms)
        chk(f"tables: planted slope {slope} -> {want}, LINEAR, RESOLVED, REPRODUCED", r["verdict"] == want
            and r["offset"] == want and r["shape"] == "LINEAR" and r["low_end"] == "RESOLVED"
            and r["reproduction"] == "REPRODUCED", f"pooled {r['pooled']['b']:.3f}")
    r = analyse(tables(1.0, slope2=1.2), arms)
    chk("tables: launch 1 at 1.0, launch 2 at 1.2 -> MIXED (SE = |b1 - b2| / 2 = 0.1)", r["verdict"] == "MIXED"
        and abs(r["pooled"]["se_b"] - 0.1) < 0.02, f"SE {r['pooled']['se_b']:.3f}")
    r = analyse(tables(1.14), arms)
    chk("tables: the prereg's stock-draw prediction (slope 1.14) -> GROWS", r["verdict"] == "GROWS",
        f"pooled {r['pooled']['b']:.3f}")
    r = analyse(tables(1.0, floor=0.60), arms)
    f1 = r["per_launch"][1]["fit"]
    chk("tables: a floor (0.20 reads as 0.35) -> FLOOR, the slope refit on 0.35 / 0.65 (= 1.0 -> CONSTANT)",
        r["low_end"] == "FLOOR" and r["pooled"]["source"].startswith("FLOOR") and abs(r["pooled"]["b"] - 1.0) < 0.06
        and r["verdict"] == "CONSTANT" and f1["b"] < 0.9, f"OLS {f1['b']:.3f}, refit {r['pooled']['b']:.3f}")
    r = analyse(tables(1.0, curve=0.05), arms)
    chk("tables: 0.35 bowed 0.05 s off the chord -> CURVED (segment slopes reported)", r["shape"] == "CURVED"
        and all(abs(r["per_launch"][n]["fit"]["chord_dev_s"] - 0.05) < 0.01 for n in (1, 2)))
    r = analyse(tables(1.0, at065=0.98), arms)
    chk("tables: 0.65 at 0.98 s (> 1 frame off D1's 0.9363) -> NOT REPRODUCED, printed before the line",
        r["reproduction"] == "NOT REPRODUCED" and report(r, [])[0].startswith("REPRODUCTION")
        and "changed the chain" in report(r, [])[1])
    r = analyse(tables(1.0, lm={1: 19.0, 2: 19.2, 3: 19.3}), arms)
    r2 = analyse(tables(1.0, lm={1: 20.5, 2: 19.6, 3: 19.0}), arms)
    chk("tables: launch_m within 0.5 m -> pure delay; spread 1.5 m -> not (V-2's second input)",
        r["launch_m"] == "pure delay" and r2["launch_m"].startswith("not pure delay"))
    r = analyse(tables(1.0), arms)
    st = r["stock"]
    chk("tables: the stock distribution and its inversion through the pooled line",
        st["car_starts"] == 3 * (5 + 6) and st["starts"] == 6 and abs(st["median_game_s"] - (st["median"] - r["pooled"]["a"])
                                                                        / r["pooled"]["b"]) < 1e-12
        and st["fastest_median"] <= st["median"], f"median {st['median']:.3f} -> game {st['median_game_s']:.3f}")
    one = {1: tables(1.0)[1]}
    chk("tables: one launch -> NOT SCORED; with --allow-partial -> NOT SCORED (partial)",
        analyse(one, arms)["verdict"] == "NOT SCORED" and analyse(one, arms, partial=True)["verdict"] == PARTIAL)
    t = tables(1.0)
    for s in t[2]["starts"]:
        for d in ROSTER:
            if arms[2][d] == 1:
                s["drivers"][d]["reaction_s"] = None
    chk("tables: a launch with no measured 0.20 car -> NOT SCORED", analyse(t, arms)["verdict"] == "NOT SCORED")
    t = tables(1.0, starts=1)
    t4 = {n: {**L, "starts": L["starts"] * 4} for n, L in t.items()}
    chk("tables: the car is the unit (4 copies of a start give the same line)", all(
        abs(analyse(t, arms)["per_launch"][n]["fit"]["b"] - analyse(t4, arms)["per_launch"][n]["fit"]["b"]) < 1e-12
        for n in (1, 2)))
    a, b = ols(LEVEL_X, [0.486, 0.636, 0.936])
    chk("ols by hand: 0.486 / 0.636 / 0.936 -> slope 1, intercept 0.286", abs(b - 1) < 1e-9 and abs(a - 0.286) < 1e-9)

    # ---- 2. synthetic captures through the whole tool
    def specs_for(arm, slope, n_starts, rng, order=None, at065=0.936, per=None):
        o = order or ROSTER[:]
        accel = {d: 9.0 + (i % 5) * 0.4 for i, d in enumerate(ROSTER)}
        out = []
        for k in range(n_starts):
            sp = {"order": o, "react": synth_reactions(arm, slope, rng, at065), "accel": accel}
            sp.update((per or {}).get(k, {}))
            out.append(sp)
        return out

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        # validity: one launch, one start per rule
        rng = random.Random(11)
        order = ROSTER[:]
        rng.shuffle(order)
        vb = tmp / "valid"
        sp = specs_for(arms[1], 1.0, 8, rng, order, per={1: {"coll": True}, 2: {"pena": True}, 4: {"gap": (8.0, 14.0)},
                                                        5: {"end_s": 12.0}, 6: {"ai_coll": True, "ai_pena": True}})
        sp[3]["react"] = {**sp[3]["react"], order[4]: 99.0}       # start 4: one AI car never moves
        uids = write_synth_launch(vb / "launch_1", 1, sp, seed)
        # (e): start 8's uid listed twice in udp_starts.txt (the wait returned an old uid)
        with (vb / "launch_1" / "udp_starts.txt").open("a", encoding="utf-8") as f:
            f.write(f"start 9 2026-11-18T10:09:00 exit 0 uid {uids[7]} | started uid {uids[7]}\n")
        buf = io.StringIO()
        with redirect_stdout(buf):
            L = process_launch(1, vb / "launch_1", 56)
        got = {s["start"]: s for s in L["starts"]}
        want = {1: None, 2: "(b) COLL", 3: "(b) PENA", 4: "(c)", 5: "(f)", 6: "(f)", 7: None, 8: "(e)"}
        for k, w in want.items():
            s = got.get(k)
            good = s is not None and (s["valid"] if w is None else (not s["valid"] and any(x.startswith(w) for x in s["reasons"])
                                                                    and len(s["reasons"]) == 1))
            chk(f"validity: start {k} " + ("clean -> PASS" if w is None else f"fails {w} only") +
                (" (an AI-AI COLL and an AI PENA don't count)" if k == 7 else ""), good,
                "" if s is None else f"{s['verdict']} {s['reasons']}")
        out = buf.getvalue()
        chk("every start prints 'finish checks: not applicable (start-only)'",
            out.count(NA_LINE) == len(L["starts"]) == 8, f"{out.count(NA_LINE)} lines")
        chk("validity: the gap rule reports the gap (6.5 s -> 14 s) and the short capture (12 s of 20)",
            got[5]["max_gap_s"] > 5 and got[6]["max_gap_s"] > 5 and got[1]["max_gap_s"] < 1,
            f"{got[5]['max_gap_s']} / {got[6]['max_gap_s']}")
        # launch-level rules, each failing once (every start of the launch dropped)
        lb = tmp / "launch_rules"
        sp = specs_for(arms[1], 1.0, 2, random.Random(3), order)
        write_synth_launch(lb / "launch_1", 1, sp, seed)
        ld = lb / "launch_1"

        def all_invalid(tag):
            with redirect_stdout(io.StringIO()):
                LL = process_launch(1, ld, 56)
            return all(not s["valid"] and any(tag in x for x in s["reasons"]) for s in LL["starts"]) and LL["starts"]

        def clean():
            with redirect_stdout(io.StringIO()):
                LL = process_launch(1, ld, 56)
            return all(s["valid"] for s in LL["starts"]) and LL["starts"]
        chk("launch rules: the clean launch passes", clean())
        keep = (ld / "weather.txt").read_text(encoding="utf-8")
        (ld / "weather.txt").write_text("weather: NOT LOCKED (weather 1)\n", encoding="utf-8")
        chk("(d) weather NOT LOCKED -> every start INVALID", all_invalid("(d) weather"))
        (ld / "weather.txt").write_text(keep, encoding="utf-8")
        keep = (ld / "session_check.txt").read_text(encoding="utf-8")
        (ld / "session_check.txt").write_text("invalid: difficulty 99 (uid 1)\nexit 6\n", encoding="utf-8")
        chk("(a) a failed race-1 session check -> every start INVALID", all_invalid("(a) the race-1 session check"))
        (ld / "session_check.txt").write_text("unverified: no race session within 90 s\nexit 2\n", encoding="utf-8")
        chk("(a) an unverified session check is redone offline (difficulty 100, track 17, weather 0) -> PASS", clean())
        (ld / "session_check.txt").write_text(keep, encoding="utf-8")
        (ld / "invalid.txt").write_text("invalid: difficulty 99 (session check)\n", encoding="utf-8")
        chk("(a) invalid.txt -> every start INVALID", all_invalid("invalid.txt"))
        (ld / "invalid.txt").unlink()
        keep = (ld / "check_applied.txt").read_text(encoding="utf-8")
        (ld / "check_applied.txt").write_text(keep.replace("56 applied", "55 applied").replace("0 problem(s)", "1 problem(s)"),
                                              encoding="utf-8")
        chk("build: check_applied with a problem -> every start INVALID", all_invalid("build:"))
        (ld / "check_applied.txt").write_text(keep, encoding="utf-8")
        (ld / "gamedb_expected.txt").write_text("93\n", encoding="ascii")
        chk("build: the loader's gamedb count != gamedb_expected -> every start INVALID", all_invalid("build: loader.log gamedb"))
        (ld / "gamedb_expected.txt").write_text("112\n", encoding="ascii")
        keep = (ld / "transcript.txt").read_text(encoding="utf-8")
        (ld / "transcript.txt").write_text(keep.replace("saves unchanged (179 entries)", "SAVES CHANGED: stop"), encoding="utf-8")
        chk("saves guard: SAVES CHANGED -> every start INVALID", all_invalid("saves:"))
        (ld / "transcript.txt").write_text(keep.replace("saves unchanged (179 entries)\n", ""), encoding="utf-8")
        (ld / "saves_diff_deferred.txt").write_text("checked late 2026-11-18T12:00:00: unchanged (179 entries)\n--- was:\n",
                                                    encoding="utf-8")
        chk("saves guard: a deferred check, checked late unchanged -> PASS", clean())
        (ld / "saves_diff_deferred.txt").write_text("pending 2026-11-18T12:00:00\n", encoding="utf-8")
        chk("saves guard: a deferred check still pending -> every start INVALID", all_invalid("saves:"))
        (ld / "saves_diff_deferred.txt").unlink()
        (ld / "transcript.txt").write_text(keep, encoding="utf-8")

        # end to end: planted slope 1.0 -> CONSTANT, 1.2 -> GROWS (2 launches x 3 starts)
        for slope, want in ((1.0, "CONSTANT"), (1.2, "GROWS")):
            eb = tmp / f"e2e_{int(slope * 10)}"
            for n in (1, 2):
                write_synth_launch(eb / f"launch_{n}", n, specs_for(arms[n], slope, 3, random.Random(20 + n), order),
                                   seed)
            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = run(eb, None, False)
            js = json.loads((eb / "c1_check" / "summary.json").read_text(encoding="utf-8"))
            chk(f"end to end: planted slope {slope} -> {want}, 6/6 starts valid, REPRODUCED", rc == 0
                and js["verdict"] == want and js["starts_valid"] == 6 and js["reproduction"] == "REPRODUCED"
                and f"C-1 offset: {want}" in buf.getvalue() and buf.getvalue().count(NA_LINE) == 6,
                f"rc {rc}, pooled slope {js.get('pooled', {}).get('b')}")
            if slope == 1.0:
                rows = list(csv.DictReader((eb / "c1_check" / "per_car_launch.csv").open(encoding="utf-8")))
                chk("end to end: per_car_launch.csv has 2 x 19 cars, 3 starts each, the arms of c1_make",
                    len(rows) == 38 and all(r["reaction_s_starts"] == "3" for r in rows)
                    and all(Counter(r["arm"] for r in rows if r["launch"] == str(n)) ==
                            Counter(cm.ARMS[a] for a in arms[n].values()) for n in (1, 2)))
                lv = js["per_launch"]["1"]["levels"]["reaction_s"]
                chk("end to end: the measured levels read the planted values (within a frame)",
                    all(abs(lv[k]["mean"] - (0.936 + (cm.LEVELS[cm.ARMS.index(k)] - 0.65))) < 0.017
                        for k in ("0.20", "0.35", "0.65")), str({k: round(v["mean"], 4) for k, v in lv.items()}))
                good_batch = eb
        part = tmp / "partial"
        write_synth_launch(part / "launch_1", 1, specs_for(arms[1], 1.0, 2, random.Random(4), order), seed)
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc3 = run(part, None, False)
        chk("end to end: one launch -> refused (exit 3, NOT SCORED)", rc3 == 3 and buf.getvalue().startswith("NOT SCORED"))
        buf = io.StringIO()
        with redirect_stdout(buf):
            rcp = run(part, None, True)
        lines = [ln for ln in buf.getvalue().splitlines() if ln.strip()]
        chk("end to end: one launch with --allow-partial -> NOT SCORED (partial) on every line",
            rcp == 0 and lines and all(PARTIAL in ln for ln in lines))
        buf = io.StringIO()
        with redirect_stdout(buf):
            rcs = run(good_batch, str(seed + 1), False)
        chk("an assignment that isn't draw(--seed, launch) is refused", rcs == 3 and "disagrees" in buf.getvalue())
        a1 = (good_batch / "launch_1" / "gen" / "assignment.csv").read_text(encoding="utf-8")
        (good_batch / "launch_1" / "gen" / "assignment.csv").write_text(
            (good_batch / "launch_2" / "gen" / "assignment.csv").read_text(encoding="utf-8"), encoding="utf-8")
        buf = io.StringIO()
        with redirect_stdout(buf):
            rcm = run(good_batch, None, False)
        chk("an assignment.csv that doesn't match expected_ops.csv is refused", rcm == 3 and "does not match" in buf.getvalue())
        (good_batch / "launch_1" / "gen" / "assignment.csv").write_text(a1, encoding="utf-8")
        (good_batch / "launch_1" / "arm.txt").write_text("D1 seed 1 launch 1, add-on verve.d1-l01\n", encoding="utf-8")
        buf = io.StringIO()
        with redirect_stdout(buf):
            rcv = run(good_batch, None, False)
        chk("a D1 arm.txt is refused", rcv == 3 and "not a C1 launch" in buf.getvalue())

        # the smoke test: stock, 4 starts
        stock = {d: 0 for d in ROSTER}

        def smoke_batch(name, per=None):
            sb = tmp / name
            write_synth_launch(sb / "launch_1", 1, specs_for(stock, 1.0, 4, random.Random(8), order, per=per), smoke=True)
            return sb

        def smoke(sb):
            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = run_smoke(sb)
            return rc, buf.getvalue()
        sb = smoke_batch("smoke_ok")
        rc, out = smoke(sb)
        chk("smoke: 4 clean stock starts -> SMOKE PASS (exit 0)", rc == 0 and "SMOKE PASS" in out
            and out.count(NA_LINE) == 4, out.strip().splitlines()[-1])
        rev = order[::-1]
        sbg = tmp / "smoke_grid"
        sp = specs_for(stock, 1.0, 4, random.Random(8), order)
        sp[2]["order"] = rev
        write_synth_launch(sbg / "launch_1", 1, sp, smoke=True)
        rc, out = smoke(sbg)
        chk("smoke: a different grid in start 3 -> SMOKE FAIL (criterion 2)", rc == 1 and "FAIL 2." in out)
        rc, out = smoke(smoke_batch("smoke_moves", {1: {"player_moves": True}}))
        chk("smoke: the player on track in start 2 -> SMOKE FAIL (criterion 3, and (c)-(f) still pass)",
            rc == 1 and "FAIL 3." in out and "ok   4." in out)
        rc, out = smoke(smoke_batch("smoke_coll", {3: {"coll": True}}))
        chk("smoke: a player COLL in start 4 -> SMOKE FAIL (criterion 4: 3/4 PASS)", rc == 1 and "FAIL 4." in out
            and "3/4 PASS" in out)
        sbs = tmp / "smoke_short"
        write_synth_launch(sbs / "launch_1", 1, specs_for(stock, 1.0, 3, random.Random(8), order), smoke=True)
        rc, out = smoke(sbs)
        chk("smoke: only 3 starts -> SMOKE FAIL (criterion 1)", rc == 1 and "FAIL 1." in out)
        sbe = smoke_batch("smoke_end")
        tr = sbe / "launch_1" / "transcript.txt"
        tr.write_text(tr.read_text(encoding="utf-8").replace("result: plan done", "result: startwait: start 4: no lights out"),
                      encoding="utf-8")
        rc, out = smoke(sbe)
        chk("smoke: the plan stopped (not 'plan done') -> SMOKE FAIL (criterion 5)", rc == 1 and "FAIL 5." in out)
        sbu = smoke_batch("smoke_udpfinish")
        (sbu / "launch_1" / "udpfinish_race1.txt").write_text("finished uid 1\n", encoding="utf-8")
        rc, out = smoke(sbu)
        chk("smoke: a finish waited for (@udpfinish) -> SMOKE FAIL (criterion 5)", rc == 1 and "FAIL 5." in out)
        (sb / "launch_1" / "gen").mkdir()
        rc, out = smoke(sb)
        chk("smoke: a launch with an add-on (gen/) is refused", rc == 3 and "no add-on" in out)
        buf = io.StringIO()
        with redirect_stdout(buf):
            rcx = run_smoke(good_batch)
        chk("smoke: a C1 launch is refused as a smoke launch", rcx == 3)

    fixture = "skipped (no --real)"
    if real is not None:
        # a finished D1 launch, read start-only: its 4 races as starts, the D1 pinned cars as the 0.65 arm
        cap = real / "raw" / "udp.bin"
        if cap.exists():
            import d1_make as dm
            pin = dm.read_assignment(real / "gen" / "assignment.csv")
            n_ops = sum(pin.values()) * 4
            buf = io.StringIO()
            with redirect_stdout(buf):
                L = process_launch(1, real, n_ops)
            arm = {d: 3 * pin[d] for d in ROSTER}
            lv = level_means(L, arm, PRIMARY)
            good = (len(L["starts"]) >= 1 and all(s["valid"] for s in L["starts"]) and lv[3]["mean"] is not None
                    and abs(lv[3]["mean"] - D1_065_S) <= FRAME_S and buf.getvalue().count(NA_LINE) == len(L["starts"]))
            ok &= good
            fixture = (f"{'ok' if good else 'WRONG'}: {real}: {sum(s['valid'] for s in L['starts'])}/{len(L['starts'])} "
                       f"starts PASS start-only, pinned (0.65) mean {lv[3]['mean']:.4f} s over {lv[3]['n_cars']} cars "
                       f"(D1 {D1_065_S}), stock {lv[0]['mean']:.4f} s; player driverStatus "
                       f"{[s['player_dstatus'] for s in L['starts']]}, max gaps {[s['max_gap_s'] for s in L['starts']]}"
                       + ("" if good else " | " + " | ".join("; ".join(s["reasons"]) for s in L["starts"])))
        else:
            fixture = f"skipped ({cap} not on this PC)"
    print("\n".join(results))
    print("selftest", "ok" if ok else "FAILED", "| real:", fixture)
    return 0 if ok else 1


# ==================================================================================================== CLI

def main(argv: list[str]) -> int:
    args = list(argv)
    if "--selftest" in args:
        return selftest(Path(args[args.index("--real") + 1]) if "--real" in args else None)
    allow = "--allow-partial" in args
    smoke = "--smoke" in args
    args = [a for a in args if a not in ("--allow-partial", "--smoke")]
    seed = None
    if "--seed" in args:
        i = args.index("--seed")
        if i + 1 >= len(args):
            print(__doc__)
            return 2
        seed = args[i + 1]
        del args[i:i + 2]
    if len(args) != 1:
        print(__doc__)
        return 2
    if smoke:
        return run_smoke(Path(args[0]))
    return run(Path(args[0]), seed, allow)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
