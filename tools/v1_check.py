"""V-1 factorial screen: the analysis (docs/verve_v1_prereg.md, v3 rulings). Offline: reads a finished batch only.

Usage:
    python -I tools/v1_check.py runs/<batch> --gamedb <N> [--seed <S>] [--track 17] [--perms 10000] [--allow-partial]
    python -I tools/v1_check.py --selftest

Batch layout (tools/v1_run.ps1): <batch>/launch_<n>/gen/assignment.csv (driver, team, 8 factors; tools/v1_make.py),
<batch>/launch_<n>/raw/udp.bin (one capture, all the launch's restart-races, one race-session uid each), the
launch's weather.txt and raw/loader.log (validity), and the seed (--seed, or <batch>/launch_<n>/seed.txt). Writes
<batch>/v1_check/{summary.json, per_race.csv, per_driver_launch.csv} and a short report on stdout.

THE LAUNCH IS THE BLOCK. 12 launches x 4 races, 5 laps, Austria. A launch's 4 races share one assignment
(draw(seed, launch)) and one grid: they are correlated replicates, never independent. Per factor: average each
driver's measure over the launch's valid races, centre each driver's launch-means across launches (driver fixed
effects; start measures are first residualised on grid side), statistic = mean over launches of (mean centred value
at 1 - mean at 0). Permutation test: 10,000 redraws, each replacing EVERY launch's assignment with draw(seed_k, launch)
for a fresh seed_k (the real constrained randomisation: teammates split, Alonso alternates), two-sided p; SE = the SD
of the permutation null. Decision (prereg v3): ALIVE (p < 0.05, predicted direction, FE slope outside the null band),
ALIVE-SMALL (p < 0.05, FE slope inside the band: real but not usable), ALIVE-REVERSED (p < 0.05, opposite, outside the
band), DEAD (FE slope +/- 2 SE of its own permutation null inside the band), else INCONCLUSIVE. Control floor fallback:
fewer than 10 off-track + spin events in the whole batch -> control's primary is corner-exit pace (exit_all_kph). No interim looks: exit 3 unless the batch has
12 complete launches; --allow-partial runs anyway and prints NOT SCORED (partial) on every line.

Validity per race: tools/aionly_check.py's check() on that race's uid (INVALID or FAIL = dropped, listed).

Measures (per driver per race; ONE primary per factor, see PRIMARY):
- reaction_s (reaction_speed): the LGOT event's arrival wall time to the car's first LapData frame whose totalDistance
  is >= MOVE_M (0.3 m) over its last pre-LGOT value. Relative (a constant offset), resolution 1/60 s.
- launch_m (mistakes): totalDistance covered in the LAUNCH_S (2.0 s) after the car's OWN first movement.
  Direction: driver_characteristics.mistakes is a SKILL, higher = fewer mistakes (F-29, F-37; verve_build_design.md
  1; verve_drivers_plan.md 1.2), so mistakes 1 -> fewer bad starts -> a LONGER launch (predicted +).
- passes_made (aggression, ATTACK): race_feel held_passes_net_2plus. passes_suffered (DEFEND, predicted fewer at 1):
  race_feel held_suffered_net_2plus.
- offtracks_spins (control, predicted fewer at 1): there is no off-track event in the F1 25 UDP, and LapData's
  currentLapInvalid / cornerCuttingWarnings never move for AI cars (Phase 0: 0 in 510k car-frames). Best available:
  off-track = CarTelemetry surfaceType with >= OFF_WHEELS (2) wheels on an unpaved surface (OFF_SURFACES: rock,
  gravel, mud, sand, grass, water), an episode ends after OFF_MERGE_S (1 s) back on paved surface; spin = Motion
  horizontal velocity >= SPIN_MIN_MS (5 m/s) at a slip angle (velocity vs the car's forward direction) >= SPIN_SLIP_DEG
  (60 deg), episodes merged within SPIN_MERGE_S (3 s). Counted from lights out to the car's own finish, not in the
  pit lane. Phase 0 (Hungary, stock): 0 unpaved wheel samples and a max slip of 25-30 deg, so both are 0 at stock.
- entry_kph / exit_kph (speed_in / speed_out): race_feel's corner table (clean corner passes: laps 2+, no pit lap, no
  car within 2.0 s ahead in the 300 m before the brake onset; corners with >= 4 clean passes). Per clean pass: entry =
  the minimum speed from the brake onset to ZONE_M (250 m) after it (the apex = where that minimum is); exit = the
  speed EXIT_M (150 m) after the apex. Per car per race: the mean over corners of (the car's median - the field's
  median at that corner), km/h (relative to the race, so corner composition cancels).
Secondaries (estimate, SE, p; never a decision): positions gained to T1 (grid - LapData position when lapDistance
first reaches T1_M, PROVISIONAL 300 m) and at the end of lap 1, lap-time SD (laps 2+, no pit lap), contacts (COLL),
speed_1s_kph (CarTelemetry speed at the first frame >= 1 s after LGOT), the ATTACK/DEFEND cross-effects,
offtracks / spins apart, and entry_all_kph / exit_all_kph (the corner pace over every pass, traffic included: the
clean-pass rule leaves few cars in a train-heavy race; Phase 0's stock Hungary race: 4 of 19 cars).
Exit 0 scored (or --allow-partial), 2 usage, 3 refused (partial batch, seed or assignment mismatch).
"""
from __future__ import annotations

import bisect
import csv
import io
import json
import math
import random
import re
import shutil
import statistics
import struct
import sys
import tempfile
import time
import unicodedata
from collections import defaultdict
from contextlib import redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import aionly_check as ac  # noqa: E402
import race_feel as rf  # noqa: E402
import udp_parse as u  # noqa: E402
import v1_make as vm  # noqa: E402

# ---------------------------------------------------------------------------------------------------- design (v3)
N_LAUNCHES = 12
RACES_PER_LAUNCH = 4
TRACK_AUSTRIA = "17"
N_PERMS = 10_000
ALPHA = 0.05
FACTORS = vm.FACTORS
ROSTER = vm.ROSTER

# ---------------------------------------------------------------------------------------------------- start measures
MOVE_M = 0.3            # totalDistance gain over the pre-LGOT value that counts as the car's first movement (fixed)
MOVE_WINDOW_S = 6.0     # LapData frames read after LGOT for the start measures
LAUNCH_S = 2.0          # launch_m: distance covered in this long after the car's own first movement
SPEED_AT_S = 1.0        # speed_1s_kph: CarTelemetry speed this long after LGOT
T1_M = 300.0            # PROVISIONAL: Austria's T1 lap distance for positions gained to T1 (prereg must fix it)

# ---------------------------------------------------------------------------------------------------- race measures
OFF_SURFACES = {3, 4, 5, 6, 7, 8}   # CarTelemetry surfaceType: rock, gravel, mud, sand, grass, water (unpaved)
OFF_WHEELS = 2
OFF_MERGE_S = 1.0
SPIN_SLIP_DEG = 60.0
SPIN_MIN_MS = 5.0
SPIN_MERGE_S = 3.0
MOTION_ENTRY = (54, 60)             # Motion car entry: 54 bytes in packet format 2026, 60 in 2025 (both lead the same)
ZONE_M = 250.0
EXIT_M = 150.0

# ---------------------------------------------------------------------------------------------------- the prereg table
# measure -> (unit, is a start measure (residualised on grid side), description)
MEASURES = {
    "reaction_s": ("s", True, "LGOT arrival to first LapData totalDistance gain >= 0.3 m"),
    "launch_m": ("m", True, "totalDistance in the 2.0 s after the car's own first movement"),
    "speed_1s_kph": ("km/h", True, "CarTelemetry speed 1 s after LGOT"),
    "gain_t1": ("places", True, "grid - position at lapDistance T1_M (provisional 300 m)"),
    "gain_lap1": ("places", True, "grid - position at the end of lap 1"),
    "passes_made": ("/race", False, "race_feel held_passes_net_2plus"),
    "passes_suffered": ("/race", False, "race_feel held_suffered_net_2plus"),
    "offtracks_spins": ("/race", False, "off-tracks (surfaceType) + spins (slip angle)"),
    "offtracks": ("/race", False, ">= 2 wheels unpaved, episodes"),
    "spins": ("/race", False, "slip angle >= 60 deg at >= 5 m/s, episodes"),
    "entry_kph": ("km/h", False, "min speed in the braking zone vs field, clean corner passes"),
    "exit_kph": ("km/h", False, "speed 150 m after the apex vs field, clean corner passes"),
    "entry_all_kph": ("km/h", False, "as entry_kph, every corner pass laps 2+ (traffic included)"),
    "exit_all_kph": ("km/h", False, "as exit_kph, every corner pass laps 2+ (traffic included)"),
    "laptime_sd_s": ("s", False, "SD of lap times, laps 2+, no pit lap"),
    "contacts": ("/race", False, "COLL events (race_feel collisions)"),
}
# factor -> (primary measure, predicted sign of (1 - 0))
PRIMARY = {
    "reaction_speed": ("reaction_s", -1),     # 1 -> faster: a shorter reaction
    "mistakes": ("launch_m", +1),             # mistakes is a skill (F-29, F-37): 1 -> fewer mistakes -> longer launch
    "aggression": ("passes_made", +1),
    "control": ("offtracks_spins", -1),
    "speed_in": ("entry_all_kph", +1),      # prereg v3: all passes primary (clean-pass left 4 of 19 cars in Phase 0)
    "speed_out": ("exit_all_kph", +1),
    "DEFEND": ("passes_suffered", -1),
    "ATTACK": ("passes_made", +1),
}
# primary measure -> (null band half-width, source). "prereg" = the v2 table; "PROVISIONAL" = to fix before race 1.
NULL_BAND = {
    "reaction_s": (0.02, "from the prereg"),
    "launch_m": (0.5, "PROVISIONAL (not in the prereg)"),
    "passes_made": (0.25, "from the prereg"),
    "offtracks_spins": (0.1, "from the prereg"),
    "entry_kph": (2.0, "from the prereg"),
    "exit_kph": (2.0, "from the prereg"),
    "entry_all_kph": (2.0, "from the prereg"),
    "exit_all_kph": (2.0, "from the prereg"),
    "passes_suffered": (0.25, "from the prereg"),
}
COMMON_SECONDARY = ["gain_t1", "gain_lap1", "laptime_sd_s", "contacts"]
EXTRA_SECONDARY = {
    "reaction_speed": ["speed_1s_kph", "launch_m"],
    "mistakes": ["speed_1s_kph", "reaction_s"],
    "aggression": ["passes_suffered"],
    "control": ["offtracks", "spins"],
    "speed_in": ["entry_kph"],          # clean-pass: secondary (it leaves few cars in a train-heavy race, Phase 0: 4 of 19)
    "speed_out": ["exit_kph"],
    "DEFEND": ["passes_made"],          # cross-effect
    "ATTACK": ["passes_suffered"],      # cross-effect
}
PARTIAL = "NOT SCORED (partial)"
# prereg v3 control FLOOR FALLBACK (supervisor, ruling on #155), decided blind to assignment: if the whole batch has fewer
# than FLOOR_EVENTS off-track + spin events in total (all cars, all valid races), control's primary becomes corner-exit
# pace (exit_all_kph, predicted faster at 1); off-tracks + spins stays a secondary.
FLOOR_EVENTS = 10
CONTROL_FALLBACK = ("exit_all_kph", +1)

_VALIDITY_OVERRIDE = None   # selftest: callable(launch_dir, uid) -> (verdict, reasons)


def secondaries(f: str, primary: dict | None = None) -> list[str]:
    prim = (primary or PRIMARY)[f][0]
    extra = EXTRA_SECONDARY.get(f, []) + COMMON_SECONDARY
    if prim != PRIMARY[f][0]:
        extra = [PRIMARY[f][0]] + extra      # the fallback's original primary stays as a secondary
    return list(dict.fromkeys(m for m in extra if m != prim))


def control_events(launch_data: dict[int, dict]) -> float:
    """Total off-track + spin events over all cars and all valid races (the floor rule looks at nothing else)."""
    return sum(v.get("offtracks_spins") or 0 for L in launch_data.values() for r in L["races"] if r["valid"]
               for v in r["drivers"].values())


def primaries(launch_data: dict[int, dict]) -> tuple[dict, dict]:
    ev = control_events(launch_data)
    prim = dict(PRIMARY)
    if ev < FLOOR_EVENTS:
        prim["control"] = CONTROL_FALLBACK
    return prim, {"control_events_total": ev, "floor_events": FLOOR_EVENTS, "control_fallback": ev < FLOOR_EVENTS,
                  "control_primary": prim["control"][0]}


# ==================================================================================================== batch discovery

def find_launches(batch: Path) -> dict[int, Path]:
    out = {}
    for p in batch.iterdir() if batch.is_dir() else []:
        m = re.fullmatch(r"launch_(\d+)", p.name)
        if m and p.is_dir():
            out[int(m[1])] = p
    return dict(sorted(out.items()))


def launch_problems(ld: Path) -> list[str]:
    return [f"no {x}" for x in ("gen/assignment.csv", "raw/udp.bin") if not (ld / x).exists()]


def read_assignment(path: Path) -> dict[str, dict[str, int]]:
    with path.open(encoding="utf-8", newline="") as f:
        return {r["driver"]: {x: int(r[x]) for x in FACTORS} for r in csv.DictReader(f)}


def resolve_seed(arg: str | None, launches: dict[int, Path]) -> tuple[int | None, str]:
    found = {}
    for n, ld in launches.items():
        p = ld / "seed.txt"
        if p.exists():
            m = re.search(r"-?\d+", p.read_text(encoding="utf-8"))
            if m:
                found[n] = int(m[0])
    vals = set(found.values())
    if arg is not None:
        if vals and vals != {int(arg)}:
            return None, f"--seed {arg} disagrees with seed.txt {sorted(vals)}"
        return int(arg), ""
    if len(vals) == 1:
        return vals.pop(), ""
    return None, ("seed.txt values disagree: " + str(found)) if vals else "no --seed and no launch_<n>/seed.txt"


def surname(label: str) -> str:
    """oscar_piastri -> PIASTRI, carlos_sainz-jr -> SAINZ, andrea-kimi_antonelli -> ANTONELLI."""
    return label.split("_")[-1].split("-")[0].upper()


def norm_name(name: str) -> str:
    return "".join(ch for ch in unicodedata.normalize("NFKD", name) if not unicodedata.combining(ch)).upper().strip()


def map_drivers(participants: list[dict] | None, n: int, player: int | None) -> tuple[dict[int, str], list[str]]:
    """{car index: roster label} from the UDP participant names; problems if the 19 don't map one to one."""
    want = {surname(d): d for d in ROSTER}
    out, seen = {}, set()
    for c, p in enumerate((participants or [])[:n]):
        if c == player:
            continue
        d = want.get(norm_name(p.get("name", "")))
        if d and d not in seen:
            out[c] = d
            seen.add(d)
    missing = sorted(set(ROSTER) - seen)
    return out, ([f"participants don't map to the roster, missing {', '.join(missing)}"] if missing else [])


# ==================================================================================================== one pass per capture

def scan_capture(path: Path) -> dict[int, dict]:
    """One pass over a launch's capture: per session uid, the session type, the LGOT arrival (wall), the last LapData
    frame before it and the frames up to MOVE_WINDOW_S after it (wall time, totalDistance, grid bytes), the speeds at
    SPEED_AT_S after it, and the frames after it in which a car had >= OFF_WHEELS unpaved wheels or a spin-like slip
    (session time). Packets are size-checked against udp_parse's layouts; a mismatch is skipped and counted."""
    out: dict[int, dict] = {}
    for wall, p in u.records(path):
        if len(p) < u.HEADER.size:
            continue
        fmt, _, _, _, _, pid, uid, stime, _, _, player, _ = u.HEADER.unpack_from(p, 0)
        d = out.get(uid)
        if d is None:
            d = out[uid] = {"uid": uid, "first_wall": wall, "type": None, "track": None, "player": player,
                            "lgot_wall": None, "pre": None, "post": [], "tel1": None, "off": [], "slip": [],
                            "bad": defaultdict(int), "n_lap": 0, "n_motion": 0, "n_tel": 0}
        lay = u.LAYOUTS.get(fmt)
        if lay is None:
            d["bad"]["format"] += 1
            continue
        n = lay["cars"]
        body = p[u.HEADER.size:]
        lg = d["lgot_wall"]
        if pid == 1 and len(body) >= 9:
            d["type"], d["track"] = body[6], struct.unpack_from("<b", body, 7)[0]
        elif pid == 3 and len(body) >= 4:
            if body[:4] == b"LGOT" and lg is None:
                d["lgot_wall"] = wall
        elif pid == 2:
            if len(body) != n * u.LAP.size + 2:
                d["bad"]["lap_data"] += 1
                continue
            d["n_lap"] += 1
            if lg is None or wall <= lg + MOVE_WINDOW_S:
                cars = [u.LAP.unpack_from(body, c * u.LAP.size) for c in range(n)]
                rec = (wall, [x[u.L_TOTDIST] for x in cars], [(x[u.L_GRID], x[u.L_DSTATUS]) for x in cars])
                if lg is None:
                    d["pre"] = rec
                else:
                    d["post"].append(rec)
        elif pid == 6:
            ts = lay["tel_size"]
            if len(body) != n * ts + lay["tel_trailer"]:
                d["bad"]["car_telemetry"] += 1
                continue
            d["n_tel"] += 1
            if lg is None:
                continue
            if d["tel1"] is None and wall >= lg + SPEED_AT_S:
                d["tel1"] = [struct.unpack_from("<H", body, c * ts)[0] for c in range(n)]
            offs = tuple(sum(1 for w in body[c * ts + ts - 4:c * ts + ts] if w in OFF_SURFACES) for c in range(n))
            if max(offs) >= OFF_WHEELS:
                d["off"].append((stime, offs))
        elif pid == 0:
            size = next((e for e in MOTION_ENTRY if len(body) == n * e), None)
            if size is None:
                d["bad"]["motion"] += 1
                continue
            d["n_motion"] += 1
            if lg is None:
                continue
            flags = []
            for c in range(n):
                vx, _, vz = struct.unpack_from("<3f", body, c * size + 12)
                fx, _, fz = struct.unpack_from("<3h", body, c * size + 24)
                v, fn = math.hypot(vx, vz), math.hypot(fx, fz)
                slip = (math.degrees(math.acos(max(-1.0, min(1.0, (vx * fx + vz * fz) / (v * fn)))))
                        if v >= SPIN_MIN_MS and fn > 0 else 0.0)
                flags.append(slip >= SPIN_SLIP_DEG)
            if any(flags):
                d["slip"].append((stime, tuple(flags)))
    return out


def race_uids(scan: dict[int, dict]) -> list[int]:
    """Race sessions (type 15) with a lights-out event, in capture order."""
    return [d["uid"] for d in sorted(scan.values(), key=lambda x: x["first_wall"])
            if d["type"] == 15 and d["lgot_wall"] is not None]


# ==================================================================================================== per-race measures

def start_measures(d: dict, cars: list[int], grid_order: str = "spec") -> dict[int, dict]:
    """{car: reaction_s, launch_m, speed_1s_kph, grid} from one race's scan (the reference implementation, validated
    on Phase 0)."""
    post = d["post"]
    if d["lgot_wall"] is None or not post:
        return {}
    base = (d["pre"] or post[0])[1]
    gridrec = (d["pre"] or post[0])[2]
    out = {}
    for c in cars:
        g = gridrec[c][0] if grid_order == "spec" else gridrec[c][1]
        mv = next((w for w, td, _ in post if td[c] - base[c] >= MOVE_M), None)
        r = {"grid": g, "reaction_s": None, "launch_m": None,
             "speed_1s_kph": d["tel1"][c] if d["tel1"] is not None else None}
        if mv is not None:
            d0 = next(td[c] for w, td, _ in post if w >= mv)
            d2 = next((td[c] for w, td, _ in post if w >= mv + LAUNCH_S), None)
            r["reaction_s"] = mv - d["lgot_wall"]
            r["launch_m"] = d2 - d0 if d2 is not None else None
        out[c] = r
    return out


def episodes(times: list[float], merge_s: float) -> int:
    n, last = 0, None
    for t in sorted(times):
        if last is None or t - last > merge_s:
            n += 1
        last = t
    return n


def corner_pace(s: dict, fin: dict[int, float], ai: list[int]) -> tuple[dict[int, float], dict[int, float], dict]:
    """(entry_kph, exit_kph) per car relative to the field, from race_feel's clean corner passes (see the doc)."""
    frames = s["lap_frames"]
    ft = [t for t, _ in frames]
    track_len = s.get("track_length")

    def frame_at(t):
        return frames[max(bisect.bisect_right(ft, t) - 1, 0)][1]
    pit_laps = defaultdict(set)
    for _, cars in frames:
        for c in ai:
            if cars[c][u.L_PIT]:
                pit_laps[c].add(cars[c][u.L_LAPNUM])
    gap_samples = {c: [(t, cars[c][u.L_LAPDIST], rf.gap_ahead(cars[c])) for t, cars in frames] for c in ai}
    rows = {c: [] for c in ai}
    for (t, speeds), (_, brakes) in zip(s["tel_frames"], s["brake_frames"]):
        cars = frame_at(t)
        for c in ai:
            if rf.racing(fin, c, t):
                rows[c].append((t, cars[c][u.L_LAPNUM], cars[c][u.L_LAPDIST], brakes[c], speeds[c]))
    clean, passes = defaultdict(list), defaultdict(list)
    for c in ai:
        for t, lap, dd in rf.brake_onsets([r[:4] for r in rows[c]]):
            if lap >= 2 and lap not in pit_laps[c] and dd >= 0:
                ok = rf.clean_before(gap_samples[c], t, dd, track_len=track_len)
                if ok:
                    clean[c].append(dd)
                passes[c].append((t, lap, dd, ok))
    table = [x["field"] for x in rf.corner_table(clean) if x["scored"]]
    tabs = {key: (defaultdict(lambda: defaultdict(list)), defaultdict(lambda: defaultdict(list)))
            for key in ("clean", "all")}
    for c in ai:
        times = [r[0] for r in rows[c]]
        for t0, lap, d0, is_clean in passes[c]:
            keys = ("clean", "all") if is_clean else ("all",)
            near = [k for k, fd in enumerate(table) if abs(fd - d0) <= rf.CLUSTER_M]
            if not near:
                continue
            k = min(near, key=lambda k: abs(table[k] - d0))
            j = bisect.bisect_left(times, t0)
            vmin = apex = None
            while j < len(rows[c]) and rows[c][j][1] == lap and rows[c][j][2] <= d0 + ZONE_M:
                if vmin is None or rows[c][j][4] < vmin:
                    vmin, apex = rows[c][j][4], rows[c][j][2]
                j += 1
            if vmin is None or j >= len(rows[c]) or rows[c][j][1] != lap:
                continue        # the zone runs over the line or past the data: not scored
            for key in keys:
                tabs[key][0][c][k].append(vmin)
            while j < len(rows[c]) and rows[c][j][1] == lap and rows[c][j][2] < apex + EXIT_M:
                j += 1
            if j < len(rows[c]) and rows[c][j][1] == lap:
                for key in keys:
                    tabs[key][1][c][k].append(rows[c][j][4])

    def rel(tab):
        field = defaultdict(list)
        for c in tab:
            for k, v in tab[c].items():
                field[k] += v
        fmed = {k: statistics.median(v) for k, v in field.items()}
        return {c: statistics.fmean(statistics.median(v) - fmed[k] for k, v in tab[c].items())
                for c in tab if tab[c]}
    return ({"entry_kph": rel(tabs["clean"][0]), "exit_kph": rel(tabs["clean"][1]),
             "entry_all_kph": rel(tabs["all"][0]), "exit_all_kph": rel(tabs["all"][1])},
            {"corners_scored": len(table), "corner_m": [round(x) for x in table]})


def race_measures(s: dict, d: dict, rows_rf: list[dict], ai: list[int]) -> tuple[dict[int, dict], dict]:
    frames = s["lap_frames"]
    n = s["n_active"] or s.get("cars", u.CARS)
    fin = rf.finish_times(frames, n)
    ft = [t for t, _ in frames]

    def frame_at(t):
        return frames[max(bisect.bisect_right(ft, t) - 1, 0)][1]

    def counts(samples, merge_s, flag):
        times = defaultdict(list)
        for t, vals in samples:
            if t <= 0:
                continue
            cars = frame_at(t)
            for c in ai:
                if flag(vals[c]) and rf.racing(fin, c, t) and not cars[c][u.L_PIT]:
                    times[c].append(t)
        return {c: episodes(times[c], merge_s) for c in ai}
    off = counts(d["off"], OFF_MERGE_S, lambda x: x >= OFF_WHEELS)
    spin = counts(d["slip"], SPIN_MERGE_S, bool) if d["n_motion"] else {}
    # lap times (laps 2+, no pit lap), positions at T1 and at the end of lap 1
    last, lt, pits, t1, l1 = {}, defaultdict(list), defaultdict(set), {}, {}
    for t, cars in frames:
        for c in ai:
            lap = cars[c][u.L_LAPNUM]
            if cars[c][u.L_PIT]:
                pits[c].add(lap)
            if c in last and lap == last[c] + 1:
                if cars[c][u.L_LAST] > 0 and last[c] >= 2 and last[c] not in pits[c]:
                    lt[c].append(cars[c][u.L_LAST] / 1000)
                if lap == 2 and c not in l1:
                    l1[c] = cars[c][u.L_POS]
            if c not in t1 and lap == 1 and cars[c][u.L_LAPDIST] >= T1_M:
                t1[c] = cars[c][u.L_POS]
            last[c] = lap
    pace, info = corner_pace(s, fin, ai)
    by_car = {r["car"]: r for r in rows_rf}
    out = {}
    for c in ai:
        r = by_car.get(c, {})
        sp = spin.get(c) if d["n_motion"] else None
        out[c] = {"passes_made": r.get("held_passes_net_2plus"), "passes_suffered": r.get("held_suffered_net_2plus"),
                  "contacts": r.get("collisions"), "offtracks": off.get(c), "spins": sp,
                  "offtracks_spins": off.get(c) + sp if sp is not None and off.get(c) is not None else None,
                  **{k: v.get(c) for k, v in pace.items()},
                  "laptime_sd_s": statistics.stdev(lt[c]) if len(lt[c]) >= 2 else None,
                  "_t1_pos": t1.get(c), "_l1_pos": l1.get(c)}
    return out, info


def validity(ld: Path, uid: int, sessions: dict, gamedb: int | None, track: str, work: Path) -> tuple[str, list[str]]:
    if _VALIDITY_OVERRIDE is not None:
        return _VALIDITY_OVERRIDE(ld, uid)
    udp = ld / "udp"
    have = udp / "sessions.csv"
    if not (have.exists() and any(r.get("session_uid") == str(uid) for r in ac.read_csv(have))):
        udp = work / "udp"
        u.write(sessions, udp, [])
    inv, fails, _ = ac.check(ld, gamedb, track, "spectator", uid=str(uid), udp_dir=udp)
    return ac.verdict(inv, fails), [f"INVALID: {x}" for x in inv] + [f"FAIL: {x}" for x in fails]


def process_launch(n: int, ld: Path, gamedb: int | None, track: str, out: Path, log=print) -> dict:
    """Every race of one launch: validity and, for the valid ones, the measures per roster driver."""
    cap = ld / "raw" / "udp.bin"
    scan = scan_capture(cap)
    races = []
    for k, uid in enumerate(race_uids(scan), 1):
        d = scan[uid]
        sessions = u.parse(cap, [], uids={uid})
        s = sessions[uid]
        n_cars = s["n_active"] or s.get("cars", u.CARS)
        player = s.get("player")
        ai = [c for c in range(n_cars) if c != player]
        cmap, probs = map_drivers(s["participants"], n_cars, player)
        verdict, reasons = validity(ld, uid, sessions, gamedb, track, out / f"launch_{n}" / f"race_{k}")
        if probs:
            verdict, reasons = "INVALID", reasons + [f"INVALID: {p}" for p in probs]
        race = {"launch": n, "race": k, "uid": str(uid), "verdict": verdict, "valid": verdict == "PASS",
                "reasons": reasons, "drivers": {}, "info": {}}
        if race["valid"]:
            st = start_measures(d, ai, s.get("grid_order", "spec"))
            rows_rf, _ = rf.analyse(cap, uid=uid, sessions=sessions)
            rm, race["info"] = race_measures(s, d, rows_rf, ai)
            for c, drv in cmap.items():
                v = {**st.get(c, {}), **rm.get(c, {})}
                g = v.get("grid")
                v["side"] = (g % 2) if g else None          # 1 = odd grid slot (pole side), 0 = even
                v["gain_t1"] = g - v["_t1_pos"] if g and v.get("_t1_pos") else None
                v["gain_lap1"] = g - v["_l1_pos"] if g and v.get("_l1_pos") else None
                v["car"] = c
                race["drivers"][drv] = v
        log(f"  launch {n} race {k} uid {uid}: {verdict}" + (f" ({'; '.join(reasons)})" if reasons else ""))
        races.append(race)
    return {"launch": n, "races": races, "grids": [r["drivers"] and tuple(sorted((v["grid"], dv) for dv, v in
                                                                                r["drivers"].items() if v.get("grid")))
                                                   for r in races]}


# ==================================================================================================== the analysis

def launch_tables(launch_data: dict[int, dict]) -> dict:
    """{measure: {launch: {driver: (launch mean, centred value or None)}}} after grid-side residualisation of the
    start measures. launch_data[L] = {"races": [{"valid", "drivers": {driver: {measure: value, "side"}}}]}."""
    side_mean = {}
    for m, (_, start, _) in MEASURES.items():
        if start:
            by = defaultdict(list)
            for L in launch_data.values():
                for r in L["races"]:
                    if r["valid"]:
                        for v in r["drivers"].values():
                            if v.get(m) is not None and v.get("side") is not None:
                                by[v["side"]].append(v[m])
            side_mean[m] = {k: statistics.fmean(x) for k, x in by.items()}
    out = {}
    for m, (_, start, _) in MEASURES.items():
        means = {}
        for n, L in launch_data.items():
            vals = defaultdict(list)
            for r in L["races"]:
                if not r["valid"]:
                    continue
                for drv, v in r["drivers"].items():
                    x = v.get(m)
                    if x is None:
                        continue
                    if start:
                        if v.get("side") is None:
                            continue
                        x = x - side_mean[m][v["side"]]
                    vals[drv].append(x)
            means[n] = {drv: statistics.fmean(x) for drv, x in vals.items()}
        tab = {n: {} for n in launch_data}
        for drv in ROSTER:
            have = [n for n in launch_data if drv in means[n]]
            mu = statistics.fmean(means[n][drv] for n in have) if have else None
            for n in have:
                tab[n][drv] = (means[n][drv], means[n][drv] - mu if len(have) >= 2 else None)
        out[m] = tab
    return out


class Stat:
    """Fast (1 - 0) statistic for one measure: per launch, the centred values as a roster-ordered vector."""

    def __init__(self, tab: dict[int, dict], launches: list[int]):
        self.rows = []
        for n in launches:
            v = [tab[n].get(d, (None, None))[1] for d in ROSTER]
            vals = [x if x is not None else 0.0 for x in v]
            pres = [1 if x is not None else 0 for x in v]
            self.rows.append((n, vals, pres, sum(vals), sum(pres)))

    def __call__(self, idx_by_launch: dict[int, tuple]) -> float | None:
        diffs = []
        for n, vals, pres, ts, tn in self.rows:
            idx = idx_by_launch[n]
            s1 = sum(map(vals.__getitem__, idx))
            n1 = sum(map(pres.__getitem__, idx))
            n0 = tn - n1
            if n1 and n0:
                diffs.append(s1 / n1 - (ts - s1) / n0)
        return sum(diffs) / len(diffs) if diffs else None


def ones(assign: dict[str, dict[str, int]]) -> dict[str, tuple]:
    return {f: tuple(i for i, d in enumerate(ROSTER) if assign[d][f]) for f in FACTORS}


def perm_seeds(seed: int, k: int) -> list[int]:
    rng = random.Random(f"v1-check-perm|{seed}")
    out, seen = [], {seed}
    while len(out) < k:
        x = rng.getrandbits(62)
        if x not in seen:
            seen.add(x)
            out.append(x)
    return out


def fe_slope(tab: dict[int, dict], assigns: dict[int, dict], f: str) -> float | None:
    """Info only: the driver-fixed-effects OLS slope on the launch means (the spec'd statistic is attenuated by
    about (L-1)/L when a driver's own share of 1s is centred out with its mean)."""
    num = den = 0.0
    for drv in ROSTER:
        have = [n for n in tab if drv in tab[n]]
        if len(have) < 2:
            continue
        abar = statistics.fmean(assigns[n][drv][f] for n in have)
        ybar = statistics.fmean(tab[n][drv][0] for n in have)
        for n in have:
            a = assigns[n][drv][f] - abar
            num += a * (tab[n][drv][0] - ybar)
            den += a * a
    return num / den if den else None


def analyse(launch_data: dict[int, dict], assigns: dict[int, dict], seed: int, perms: int = N_PERMS,
            draw=None) -> dict:
    """The per-factor tests. assigns[L] = the launch's real assignment (= draw(seed, L)). Pure in its inputs."""
    draw = draw or vm.draw
    launches = sorted(launch_data)
    tables = launch_tables(launch_data)
    stats = {m: Stat(tables[m], launches) for m in MEASURES}
    prim, floor = primaries(launch_data)
    pairs = [(f, prim[f][0]) for f in FACTORS] + [(f, m) for f in FACTORS for m in secondaries(f, prim)]
    prim_pairs = [(f, prim[f][0]) for f in FACTORS]
    real = {n: ones(assigns[n]) for n in launches}
    obs = {(f, m): stats[m]({n: real[n][f] for n in launches}) for f, m in pairs}
    live = [p for p in pairs if obs[p] is not None]
    null = {p: [] for p in live}
    null_fe = {p: [] for p in prim_pairs}     # the FE slope's own permutation null (its SE for the band comparison)
    t0 = time.perf_counter()
    for sk in perm_seeds(seed, perms):
        drawn = {n: draw(sk, n) for n in launches}
        idx = {n: ones(drawn[n]) for n in launches}
        for f, m in live:
            v = stats[m]({n: idx[n][f] for n in launches})
            if v is not None:
                null[(f, m)].append(v)
        for f, m in prim_pairs:
            v = fe_slope(tables[m], drawn, f)
            if v is not None:
                null_fe[(f, m)].append(v)
    perm_s = time.perf_counter() - t0

    def test(f, m):
        t = obs[(f, m)]
        raw = [v.get(m) for L in launch_data.values() for r in L["races"] if r["valid"] for v in r["drivers"].values()
               if v.get(m) is not None]
        res = {"measure": m, "unit": MEASURES[m][0], "estimate": t, "n_values": len(raw),
               "constant": len(set(raw)) <= 1 if raw else None,
               "drivers": sum(1 for d in ROSTER if sum(d in tables[m][n] for n in launches) >= 2),
               "fe_slope_info": fe_slope(tables[m], assigns, f)}
        nl = null.get((f, m), [])
        if t is None or not nl:
            return {**res, "se": None, "p": None}
        hits = sum(1 for x in nl if abs(x) >= abs(t) - 1e-12)
        return {**res, "se": statistics.pstdev(nl), "p": (1 + hits) / (1 + len(nl)), "null_n": len(nl)}

    out = {}
    for f in FACTORS:
        m, sign = prim[f]
        r = test(f, m)
        band, src = NULL_BAND[m]
        fe = r["fe_slope_info"]
        nf = null_fe.get((f, m), [])
        se_fe = statistics.pstdev(nf) if len(nf) > 1 else None
        r.update(predicted="+" if sign > 0 else "-", null_band=band, null_band_source=src, fe_slope=fe, se_fe=se_fe)
        # prereg v3 labels (ruling on #155): p from the centred statistic; the band comparison uses the FE slope.
        if r["p"] is None or fe is None or se_fe is None:
            r["decision"] = "NO DATA"
        elif r["p"] < ALPHA and abs(fe) <= band:
            r["decision"] = "ALIVE-SMALL"
        elif r["p"] < ALPHA:
            r["decision"] = "ALIVE" if (r["estimate"] > 0) == (sign > 0) else "ALIVE-REVERSED"
        elif fe - 2 * se_fe >= -band and fe + 2 * se_fe <= band:
            r["decision"] = "DEAD"
        else:
            r["decision"] = "INCONCLUSIVE"
        r["secondary"] = {sm: test(f, sm) for sm in secondaries(f, prim)}
        out[f] = r
    return {"factors": out, "perm_runtime_s": round(perm_s, 2), "perms": perms, "launches": launches,
            "tables": tables, "floor": floor}


# ==================================================================================================== output

def fnum(x, nd=4):
    return "NA" if x is None else (f"{x:.{nd}f}" if isinstance(x, float) else str(x))


def report(res: dict, head: list[str], partial: bool) -> list[str]:
    lines = list(head)
    lines.append(f"{'factor':<15}{'primary':<17}{'pred':>5}{'estimate':>10}{'SE':>9}{'p':>8}{'FE slope':>10}{'SE(FE)':>9}"
                 f"  {'null band (FE slope)':<42}decision")
    for f, r in res["factors"].items():
        band = f"+/-{fnum(r['null_band'], 2)} {r['unit']} {r['null_band_source']}"
        dec = PARTIAL if partial else r["decision"]
        flag = " [measure constant: floor]" if r["constant"] else ""
        lines.append(f"{f:<15}{r['measure']:<17}{r['predicted']:>5}{fnum(r['estimate']):>10}{fnum(r['se']):>9}"
                     f"{fnum(r['p'], 4):>8}{fnum(r.get('fe_slope')):>10}{fnum(r.get('se_fe')):>9}  {band:<42}{dec}{flag}")
    fl = res.get("floor") or {}
    if fl:
        lines.append(f"control floor rule: {fnum(fl['control_events_total'], 0)} off-track + spin events in the batch "
                     f"(threshold {fl['floor_events']}) -> control primary {fl['control_primary']}"
                     + (" (FALLBACK)" if fl["control_fallback"] else ""))
    lines.append("secondaries (no decision): estimate / SE / p")
    for f, r in res["factors"].items():
        lines.append(f"  {f:<15}" + "; ".join(f"{m} {fnum(x['estimate'], 3)}/{fnum(x['se'], 3)}/{fnum(x['p'], 3)}"
                                             for m, x in r["secondary"].items()))
    lines.append(f"provisional: T1_M {T1_M:g} m (Austria T1); launch_m null band +/-{NULL_BAND['launch_m'][0]} m; "
                 f"control = off-tracks (surfaceType, >= {OFF_WHEELS} unpaved wheels) + spins (slip >= "
                 f"{SPIN_SLIP_DEG:g} deg); the statistic is attenuated about (L-1)/L vs the FE slope (summary.json)")
    return [f"{PARTIAL} | {ln}" for ln in lines] if partial else lines


def write_outputs(out: Path, launch_data: dict, assigns: dict, res: dict, meta: dict) -> None:
    out.mkdir(parents=True, exist_ok=True)
    mcols = list(MEASURES)
    with (out / "per_race.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["launch", "race", "session_uid", "valid", "verdict", "reasons", "driver", "team", "car", "grid",
                    "side_odd"] + FACTORS + mcols)
        for n, L in sorted(launch_data.items()):
            for r in L["races"]:
                drivers = r["drivers"] or {}
                if not drivers:
                    w.writerow([n, r["race"], r["uid"], int(r["valid"]), r["verdict"], " | ".join(r["reasons"])] +
                               [""] * (5 + len(FACTORS) + len(mcols)))
                for drv in ROSTER:
                    if drv in drivers:
                        v = drivers[drv]
                        w.writerow([n, r["race"], r["uid"], int(r["valid"]), r["verdict"], " | ".join(r["reasons"]),
                                    drv, vm.TEAM_OF[drv], v.get("car"), v.get("grid"), v.get("side")] +
                                   [assigns[n][drv][x] for x in FACTORS] + [fnum(v.get(m), 6) for m in mcols])
    tabs = res["tables"]
    with (out / "per_driver_launch.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["launch", "driver", "team", "valid_races"] + FACTORS +
                   [f"{m}_{k}" for m in mcols for k in ("mean", "centred")])
        for n, L in sorted(launch_data.items()):
            for drv in ROSTER:
                nr = sum(1 for r in L["races"] if r["valid"] and drv in r["drivers"])
                row = [n, drv, vm.TEAM_OF[drv], nr] + [assigns[n][drv][x] for x in FACTORS]
                for m in mcols:
                    mean, cen = tabs[m][n].get(drv, (None, None))
                    row += [fnum(mean, 6), fnum(cen, 6)]
                w.writerow(row)
    js = {**meta, "perms": res["perms"], "perm_runtime_s": res["perm_runtime_s"], "factors": res["factors"]}
    (out / "summary.json").write_text(json.dumps(js, indent=1, default=str) + "\n", encoding="utf-8")


def run(batch: Path, gamedb: int | None, seed_arg: str | None, track: str, perms: int, allow_partial: bool,
        quiet: bool = False) -> int:
    say = (lambda *a: None) if quiet else print
    pre = (lambda s: f"{PARTIAL} | {s}") if allow_partial else (lambda s: s)
    launches = find_launches(batch)
    complete = {n: ld for n, ld in launches.items() if not launch_problems(ld)}
    full = set(complete) == set(range(1, N_LAUNCHES + 1)) and len(launches) == N_LAUNCHES
    if not full and not allow_partial:
        print(f"REFUSED: {len(complete)} complete launch(es) of {N_LAUNCHES} in {batch} "
              f"(found {sorted(launches)}; incomplete {[n for n in launches if n not in complete]}). No interim looks: "
              f"run after launch {N_LAUNCHES}, or --allow-partial (NOT SCORED).")
        return 3
    if not complete:
        print(pre(f"no complete launch in {batch}"))
        return 3
    seed, why = resolve_seed(seed_arg, complete)
    if seed is None:
        print(pre(f"REFUSED: {why}"))
        return 3
    assigns = {}
    for n, ld in complete.items():
        a = read_assignment(ld / "gen" / "assignment.csv")
        if a != vm.draw(seed, n):
            print(pre(f"REFUSED: launch_{n}/gen/assignment.csv is not draw({seed}, {n}): the permutation test needs the "
                      f"real randomisation"))
            return 3
        assigns[n] = a
    if gamedb is None and _VALIDITY_OVERRIDE is None:
        print(pre("REFUSED: --gamedb <expected overwritten count> is required (fix it from race 1's readback)"))
        return 2
    out = batch / "v1_check"
    t0 = time.perf_counter()
    launch_data = {}
    for n, ld in complete.items():
        launch_data[n] = process_launch(n, ld, gamedb, track, out, log=lambda s: say(pre(s)))
    parse_s = time.perf_counter() - t0
    res = analyse(launch_data, assigns, seed, perms)
    races = [r for L in launch_data.values() for r in L["races"]]
    valid = [r for r in races if r["valid"]]
    dropped = [r for r in races if not r["valid"]]
    odd = {n: len(L["races"]) for n, L in launch_data.items() if len(L["races"]) != RACES_PER_LAUNCH}
    grids = {n: len({g for g in L["grids"] if g}) for n, L in launch_data.items()}
    meta = {"batch": str(batch), "seed": seed, "scored": full and not allow_partial, "launches": sorted(complete),
            "races_total": len(races), "races_valid": len(valid), "track": track, "gamedb": gamedb,
            "dropped": [{"launch": r["launch"], "race": r["race"], "uid": r["uid"], "verdict": r["verdict"],
                         "reasons": r["reasons"]} for r in dropped],
            "launches_not_4_races": odd, "grids_per_launch_info": grids, "parse_runtime_s": round(parse_s, 1),
            "constants": {"MOVE_M": MOVE_M, "LAUNCH_S": LAUNCH_S, "SPEED_AT_S": SPEED_AT_S,
                          "T1_M": f"{T1_M} PROVISIONAL", "OFF_SURFACES": sorted(OFF_SURFACES), "OFF_WHEELS": OFF_WHEELS,
                          "OFF_MERGE_S": OFF_MERGE_S, "SPIN_SLIP_DEG": SPIN_SLIP_DEG, "SPIN_MIN_MS": SPIN_MIN_MS,
                          "SPIN_MERGE_S": SPIN_MERGE_S, "ZONE_M": ZONE_M, "EXIT_M": EXIT_M, "ALPHA": ALPHA,
                          "null_bands": {m: f"+/-{b} {MEASURES[m][0]} {s}" for m, (b, s) in NULL_BAND.items()}},
            "direction_notes": {"mistakes": "a skill (F-29, F-37): 1 = fewer mistakes, predicted LONGER launch_m"}}
    write_outputs(out, launch_data, assigns, res, meta)
    head = [f"V-1 check {batch}: seed {seed}, {len(complete)} launches, {len(valid)}/{len(races)} races valid, "
            f"{perms} permutations with the launch as the block ({res['perm_runtime_s']} s; parsing {parse_s:.0f} s)"]
    head += [f"  dropped: launch {r['launch']} race {r['race']} (uid {r['uid']}): {r['verdict']}: "
             f"{'; '.join(r['reasons'])}" for r in dropped]
    if odd:
        head.append(f"  launches without {RACES_PER_LAUNCH} races: {odd}")
    for ln in report(res, head, allow_partial):
        say(ln)
    say(pre(f"wrote {out / 'summary.json'}, per_race.csv, per_driver_launch.csv"))
    return 0


# ==================================================================================================== selftest

def synth_launch_data(seed: int, plant: dict[str, tuple[str, float]], rng_seed: int = 3, n_launch: int = N_LAUNCHES,
                      races: int = RACES_PER_LAUNCH) -> tuple[dict, dict]:
    """Synthetic per-race measure tables injected below the parsing layer: driver effects, launch-level noise shared
    by a launch's races (the correlation), race noise, and plant = {factor: (measure, effect of 1 vs 0)}."""
    rng = random.Random(rng_seed)
    scale = {"reaction_s": (0.47, 0.03, 0.015, 0.04), "launch_m": (19.0, 1.0, 0.4, 1.2),
             "speed_1s_kph": (35.0, 3.0, 1.0, 3.0), "gain_t1": (0.0, 0.5, 0.3, 0.8), "gain_lap1": (0.0, 0.7, 0.4, 1.2),
             "passes_made": (1.0, 0.3, 0.2, 0.7), "passes_suffered": (1.0, 0.3, 0.2, 0.7),
             "offtracks": (0.0, 0.02, 0.01, 0.03), "spins": (0.0, 0.01, 0.01, 0.02),
             "entry_kph": (0.0, 1.5, 0.3, 0.6), "exit_kph": (0.0, 1.5, 0.3, 0.6),
             "entry_all_kph": (0.0, 1.5, 0.4, 0.8), "exit_all_kph": (0.0, 1.5, 0.4, 0.8),
             "laptime_sd_s": (0.4, 0.05, 0.03, 0.08), "contacts": (0.5, 0.2, 0.1, 0.5)}
    alpha = {(m, d): rng.gauss(0, sc[1]) for m, sc in scale.items() for d in ROSTER}
    data, assigns = {}, {}
    for n in range(1, n_launch + 1):
        a = vm.draw(seed, n)
        assigns[n] = a
        order = ROSTER[:]
        rng.shuffle(order)
        side = {d: (i + 1) % 2 for i, d in enumerate(order)}
        lnoise = {(m, d): rng.gauss(0, sc[2]) for m, sc in scale.items() for d in ROSTER}
        rs = []
        for k in range(races):
            drivers = {}
            for d in ROSTER:
                v = {"side": side[d]}
                for m, (mu, _, _, sd) in scale.items():
                    v[m] = mu + alpha[(m, d)] + lnoise[(m, d)] + rng.gauss(0, sd) + 0.01 * side[d]
                for f, (m, eff) in plant.items():
                    v[m] += eff * a[d][f]
                v["offtracks_spins"] = v["offtracks"] + v["spins"]
                drivers[d] = v
            rs.append({"race": k + 1, "valid": True, "drivers": drivers, "uid": f"{n}{k}", "verdict": "PASS",
                       "reasons": []})
        data[n] = {"launch": n, "races": rs, "grids": []}
    return data, assigns


W0 = 1794849000.0
PHASE0_REL = Path("runs") / "2026-11-16-V1-phase0" / "race_1"    # raw/udp.bin is gitignored: local only, read-only


def phase0_candidates() -> list[Path]:
    """The Phase 0 capture in this checkout, or in the main checkout when run from .claude/worktrees/<name>."""
    repo = Path(__file__).resolve().parent.parent
    out = [repo / PHASE0_REL]
    if repo.parent.name == "worktrees" and repo.parent.parent.name == ".claude":
        out.append(repo.parents[2] / PHASE0_REL)
    return out


def write_synth_capture(path: Path, order: list[str], reaction: dict[str, list[float]], accel: dict[str, float],
                        uid0: int) -> None:
    """A capture in udp_parse's own layouts (format 2026, 24 cars, player car 19): per race a new uid, a session
    packet (race, Austria, 5 laps, difficulty 100), participants, SSTA/LGOT events, LapData at 60 Hz and CarTelemetry
    at 20 Hz around the start. order = the grid (car i starts P(i+1)); reaction[driver][race] = seconds after LGOT,
    a multiple of 1/60."""
    lay = u.LAYOUTS[2026]
    ncar, ts = lay["cars"], lay["tel_size"]
    recs = []

    def pkt(wall, pid, uid, st, body):
        h = u.HEADER.pack(2026, 25, 1, 27, 1, pid, uid, st, 0, 0, 19, 255)
        recs.append(struct.pack("<dH", wall, len(h) + len(body)) + h + body)

    for k in range(len(next(iter(reaction.values())))):
        uid = uid0 + k
        w0 = W0 + 600 * k
        sess = bytearray(897)
        sess[3], sess[6], sess[7] = 5, 15, int(TRACK_AUSTRIA)
        struct.pack_into("<H", sess, 4, 4318)
        sess[640] = 100
        pkt(w0, 1, uid, 0.0, bytes(sess))
        part = bytes([20])
        for c in range(ncar):
            name = (surname(order[c]) if c < 19 else "PLAYER").encode() if c < 20 else b""
            rec = lay["part"].pack(0 if c == 19 else 1, c, c, 0, 0, c + 1, 1, name.ljust(32, b"\0"))
            part += rec.ljust(lay["part_size"], b"\0")
        pkt(w0 + 0.01, 4, uid, 0.0, part)
        pkt(w0 + 0.02, 3, uid, 0.0, b"SSTA" + bytes(12))
        lg = w0 + 1.0
        for i in range(-30, int(MOVE_WINDOW_S * 60) + 30):
            wall = lg + i / 60 + 0.0005
            st = max(i / 60, 0.0)
            if i == 0:
                pkt(lg, 3, uid, 0.0, b"LGOT" + bytes(12))
            body = b""
            for c in range(ncar):
                base = -8.0 * c
                td = base
                if c < 19 and i >= 0:
                    t = i / 60 - reaction[order[c]][k]
                    if t >= -1e-9:
                        td = base + 0.35 + 0.5 * accel[order[c]] * t * t
                lap = [0] * 33
                lap[u.L_LAPDIST], lap[u.L_TOTDIST] = float(td), float(td)
                lap[u.L_POS], lap[u.L_LAPNUM], lap[u.L_GRID], lap[u.L_DSTATUS] = c + 1, 1, c + 1, 4 if c < 19 else 0
                lap[u.L_RSTATUS] = 2
                body += u.LAP.pack(*lap)
            pkt(wall, 2, uid, st, body + b"\0\0")
            if i % 3 == 0:
                tel = b""
                for c in range(ncar):
                    t = max(i / 60 - reaction[order[c]][k], 0.0) if c < 19 else 0.0
                    tel += (u.TEL_LEAD.pack(int(accel[order[c]] * t * 3.6) if c < 19 else 0, 0.0, 0.0, 0.0, 0, 1)
                            .ljust(ts, b"\0"))
                pkt(wall + 0.0002, 6, uid, st, tel + bytes(lay["tel_trailer"]))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"".join(recs))


def write_synth_batch(batch: Path, seed: int, n_launch: int, plant_reaction: float, rng_seed: int = 3) -> dict:
    """On-disk batch: launch_<n>/gen/assignment.csv (v1_make.write_launch), seed.txt, raw/udp.bin with 4 races."""
    rng = random.Random(rng_seed)
    base_rt = {d: rng.choice(range(22, 32)) for d in ROSTER}        # frames (1/60 s)
    accel = {d: rng.uniform(9.0, 11.0) for d in ROSTER}
    truth = {}
    for n in range(1, n_launch + 1):
        ld = batch / f"launch_{n}"
        with redirect_stdout(io.StringIO()):
            vm.write_launch(seed, n, ld / "gen", 3)
        (ld / "seed.txt").write_text(f"{seed}\n", encoding="utf-8")
        a = vm.draw(seed, n)
        order = ROSTER[:]
        rng.shuffle(order)
        react = {d: [(base_rt[d] + round(plant_reaction * 60) * a[d]["reaction_speed"] + rng.choice((-2, -1, 0, 1, 2)))
                     / 60 for _ in range(RACES_PER_LAUNCH)] for d in ROSTER}
        write_synth_capture(ld / "raw" / "udp.bin", order, react, accel, uid0=1000 * n)
        truth[n] = {"order": order, "react": react}
    return truth


def selftest() -> int:
    global _VALIDITY_OVERRIDE
    results, ok = [], True

    def chk(name: str, cond: bool, detail: str = "") -> None:
        nonlocal ok
        ok &= bool(cond)
        results.append(f"{'ok  ' if cond else 'FAIL'} {name}" + (f": {detail}" if detail else ""))

    seed = 20261116
    # ---- 1. measure tables injected below the parsing layer
    data, assigns = synth_launch_data(seed, {"reaction_speed": ("reaction_s", -0.05)})
    t0 = time.perf_counter()
    res = analyse(data, assigns, seed, N_PERMS)
    full_s = time.perf_counter() - t0
    fx = res["factors"]
    chk("planted reaction_speed (-0.05 s at 1) is ALIVE", fx["reaction_speed"]["decision"] == "ALIVE",
        f"estimate {fnum(fx['reaction_speed']['estimate'])} SE {fnum(fx['reaction_speed']['se'])} "
        f"p {fnum(fx['reaction_speed']['p'], 4)}")
    others = {f: fx[f]["decision"] for f in FACTORS if f != "reaction_speed"}
    chk("no null factor is ALIVE", not any(v.startswith("ALIVE") for v in others.values()), str(others))
    chk("a null factor with a tight measure is DEAD (speed_in, band +/-2 km/h)", fx["speed_in"]["decision"] == "DEAD",
        f"{fnum(fx['speed_in']['estimate'])} +/- 2 x {fnum(fx['speed_in']['se'])}")
    chk(f"10,000 permutations on 12 launches x 4 races, {sum(1 + len(secondaries(f)) for f in FACTORS)} tests",
        res["perms"] == N_PERMS and all(fx[f]["null_n"] == N_PERMS for f in FACTORS),
        f"permutation {res['perm_runtime_s']} s (analysis total {full_s:.1f} s)")
    rev, ra = synth_launch_data(seed, {"reaction_speed": ("reaction_s", +0.05)})
    chk("a planted effect in the wrong direction is ALIVE-REVERSED",
        analyse(rev, ra, seed, 1000)["factors"]["reaction_speed"]["decision"] == "ALIVE-REVERSED")
    # prereg v3 labels: a significant effect whose FE slope sits inside the null band is ALIVE-SMALL
    sm, sa = synth_launch_data(seed, {"speed_in": ("entry_all_kph", +0.8)})
    smr = analyse(sm, sa, seed, 1000)["factors"]["speed_in"]
    chk("a significant effect inside the band (speed_in +0.8 km/h, band +/-2) is ALIVE-SMALL",
        smr["decision"] == "ALIVE-SMALL", f"p {fnum(smr['p'], 4)} FE slope {fnum(smr['fe_slope'])}")
    big, ba = synth_launch_data(seed, {"speed_in": ("entry_all_kph", +3.0)})
    bgr = analyse(big, ba, seed, 1000)["factors"]["speed_in"]
    chk("all-pass corner pace is speed_in's primary, and +3 km/h (outside the band) is ALIVE",
        bgr["measure"] == "entry_all_kph" and bgr["decision"] == "ALIVE", f"FE slope {fnum(bgr['fe_slope'])}")
    # the control floor fallback: decided by the batch's total event count only
    fl0 = primaries(data)[1]
    chk("control floor: < 10 off-track + spin events in the batch -> primary exit_all_kph (fallback)",
        fl0["control_fallback"] and fl0["control_primary"] == "exit_all_kph", str(fl0))
    ev = {k2: v2 for k2, v2 in data.items()}
    for L in ev.values():
        for r0 in L["races"]:
            for v0 in r0["drivers"].values():
                v0["offtracks_spins"] = abs(v0["offtracks_spins"]) + 0.2
    fl1 = primaries(ev)[1]
    chk("control floor: >= 10 events -> primary stays offtracks_spins",
        not fl1["control_fallback"] and fl1["control_primary"] == "offtracks_spins",
        f"{fl1['control_events_total']:.0f} events")
    data, assigns = synth_launch_data(seed, {"reaction_speed": ("reaction_s", -0.05)})   # restore the base batch
    fp = tests = 0
    for k in range(10):
        nd, na = synth_launch_data(seed + k, {}, rng_seed=100 + k)
        r = analyse(nd, na, seed + k, 300)["factors"]
        tests += len(FACTORS)
        fp += sum(r[f]["p"] < ALPHA for f in FACTORS)
    chk("type I error: 10 null batches x 8 factors, p < 0.05 in about 5% (allowed <= 12 of 80)", fp <= 12,
        f"{fp}/{tests}")

    # ---- 2. the launch is the block
    base = analyse(data, assigns, seed, 1000)["factors"]
    shuf = {n: {**L, "races": random.Random(n).sample(L["races"], len(L["races"]))} for n, L in data.items()}
    sres = analyse(shuf, assigns, seed, 1000)["factors"]
    chk("shuffling races within a launch changes nothing (estimate, SE, p, every factor)",
        all((base[f]["estimate"], base[f]["se"], base[f]["p"]) == (sres[f]["estimate"], sres[f]["se"], sres[f]["p"])
            for f in FACTORS))
    one = {n: {**L, "races": L["races"][:1]} for n, L in data.items()}
    four = {n: {**L, "races": [L["races"][0]] * 4} for n, L in data.items()}
    r1, r4 = analyse(one, assigns, seed, 1000)["factors"], analyse(four, assigns, seed, 1000)["factors"]
    chk("4 copies of a race carry no more weight than 1 (same SE and p: races are not independent)",
        all(abs(r1[f]["se"] - r4[f]["se"]) < 1e-9 and r1[f]["p"] == r4[f]["p"] for f in FACTORS))
    calls = []

    def counting(s, n):
        calls.append((s, n))
        return vm.draw(s, n)
    analyse(data, assigns, seed, 200, draw=counting)
    chk("each redraw replaces every launch's assignment once: draw(seed_k, launch), 200 x 12 calls, fresh seeds",
        len(calls) == 200 * N_LAUNCHES and len({s for s, _ in calls}) == 200 and seed not in {s for s, _ in calls}
        and all({n for s2, n in calls if s2 == s} == set(range(1, 13)) for s, _ in calls[:24]), f"{len(calls)} calls")

    # ---- 3. synthetic UDP (udp_parse's layouts) through the whole tool, validity stubbed
    with tempfile.TemporaryDirectory() as tmp:
        batch = Path(tmp) / "batch"
        truth = write_synth_batch(batch, seed, N_LAUNCHES, -5 / 60)
        _VALIDITY_OVERRIDE = lambda ld, uid: ("PASS", [])   # noqa: E731
        scan = scan_capture(batch / "launch_1" / "raw" / "udp.bin")
        rus = race_uids(scan)
        chk("races split by session uid (4 in launch 1)", rus == [1000, 1001, 1002, 1003], str(rus))
        st = start_measures(scan[1001], list(range(19)))
        d0 = truth[1]["order"][0]
        want = truth[1]["react"][d0][1]
        chk("reaction from LapData = the planted frame (+0.5 ms write offset)", abs(st[0]["reaction_s"] - want - 0.0005)
            < 1e-6, f"{st[0]['reaction_s']:.4f} vs {want:.4f}")
        chk("grid from LapData gridPosition", [st[c]["grid"] for c in range(19)] == list(range(1, 20)))
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = run(batch, None, None, TRACK_AUSTRIA, 1000, False)
        js = json.loads((batch / "v1_check" / "summary.json").read_text(encoding="utf-8"))
        dec = {f: js["factors"][f]["decision"] for f in FACTORS}
        chk("end to end: 12 launches scored, 48/48 races", rc == 0 and js["scored"] and js["races_valid"] == 48,
            f"rc {rc}")
        chk("end to end: planted reaction_speed (-5 frames) ALIVE, mistakes (no plant) not ALIVE",
            dec["reaction_speed"] == "ALIVE" and not dec["mistakes"].startswith("ALIVE"), str(dec))
        rows = list(csv.DictReader((batch / "v1_check" / "per_race.csv").open(encoding="utf-8")))
        chk("per_race.csv: 48 races x 19 drivers", len(rows) == 48 * 19 and (batch / "v1_check" /
                                                                             "per_driver_launch.csv").exists())
        # ---- 4. no interim looks
        part = Path(tmp) / "partial"
        for n in (1, 2):
            shutil.copytree(batch / f"launch_{n}", part / f"launch_{n}")
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc3 = run(part, None, None, TRACK_AUSTRIA, 200, False)
        chk("a partial batch (2 of 12 launches) is refused, exit 3", rc3 == 3 and "REFUSED" in buf.getvalue())
        buf = io.StringIO()
        with redirect_stdout(buf):
            rcp = run(part, None, None, TRACK_AUSTRIA, 200, True)
        lines = [ln for ln in buf.getvalue().splitlines() if ln.strip()]
        pj = json.loads((part / "v1_check" / "summary.json").read_text(encoding="utf-8"))
        chk("--allow-partial runs and prints NOT SCORED (partial) on every line", rcp == 0 and lines and
            all(PARTIAL in ln for ln in lines) and pj["scored"] is False, f"{len(lines)} lines")
        (batch / "launch_3" / "gen" / "assignment.csv").write_text(
            (batch / "launch_4" / "gen" / "assignment.csv").read_text(encoding="utf-8"), encoding="utf-8")
        buf = io.StringIO()
        with redirect_stdout(buf):
            rcm = run(batch, None, None, TRACK_AUSTRIA, 200, False)
        chk("an assignment.csv that isn't draw(seed, launch) is refused", rcm == 3 and "is not draw" in buf.getvalue())
        _VALIDITY_OVERRIDE = None

    # ---- 5. Phase 0 (real capture, read-only): the reference start measures, and per-uid validity
    p0 = next((p for p in phase0_candidates() if (p / "raw" / "udp.bin").exists()), PHASE0_REL)
    if (p0 / "raw" / "udp.bin").exists():
        t1 = time.perf_counter()
        scan = scan_capture(p0 / "raw" / "udp.bin")
        rus = race_uids(scan)
        per = defaultdict(list)
        launch = []
        for uid in rus:
            for c, v in start_measures(scan[uid], list(range(19))).items():
                if v["reaction_s"] is not None:
                    per[c].append(round(v["reaction_s"], 3))
                    launch.append(round(v["launch_m"], 1))
        rts = [x for v in per.values() for x in v]
        sd = statistics.median(statistics.pstdev(v) for v in per.values() if len(v) > 1)
        got = (len(rts), min(rts), round(statistics.median(rts), 3), max(rts), round(sd, 3))
        chk("Phase 0: 4 races by uid; 76 car-starts, reaction 0.351-0.570 s, median 0.468, per-car SD 0.044",
            len(rus) == 4 and got == (76, 0.351, 0.468, 0.57, 0.044), str(got))
        chk("Phase 0: launch 16-23 m", 16 <= min(launch) and max(launch) < 24, f"{min(launch)}-{max(launch)} m")
        vals = []
        for uid in rus:
            inv, fl, m = ac.check(p0, 52, "9", "", uid=str(uid))
            vals.append((ac.verdict(inv, fl), m.get("ai_finished")))
        chk("Phase 0: aionly per uid: the three lap-1 restarts INVALID (< 18 finished), the full race has 19",
            all(v[0] == "INVALID" and (v[1] or 0) < 18 for v in vals[:3]) and vals[3][1] == 19, str(vals))
        uid = rus[-1]
        sess = u.parse(p0 / "raw" / "udp.bin", [], uids={uid})
        rows_rf, _ = rf.analyse(p0 / "raw" / "udp.bin", uid=uid, sessions=sess)
        rm, info = race_measures(sess[uid], scan[uid], rows_rf, list(range(19)))
        cnt = {m: [v[m] for v in rm.values() if v[m] is not None]
               for m in ("entry_kph", "exit_kph", "entry_all_kph", "exit_all_kph")}
        ctl = [v["offtracks_spins"] for v in rm.values()]
        chk("Phase 0 full race (Hungary, stock): corner table found, clean-pass pace for a few cars, all-pass pace "
            "for >= 17, control measured (0 at stock), passes counted (0 net, as its race_feel.csv)",
            info["corners_scored"] >= 8 and len(cnt["entry_kph"]) >= 3 and len(cnt["entry_all_kph"]) >= 17
            and len(cnt["exit_all_kph"]) >= 17 and all(x == 0 for x in ctl)
            and all(v["passes_made"] is not None for v in rm.values()),
            f"{info['corners_scored']} corners; cars with entry/exit: clean {len(cnt['entry_kph'])}/"
            f"{len(cnt['exit_kph'])}, all {len(cnt['entry_all_kph'])}/{len(cnt['exit_all_kph'])}; all-pass entry "
            f"{min(cnt['entry_all_kph']):+.1f}..{max(cnt['entry_all_kph']):+.1f} km/h; off-tracks+spins {sum(ctl)}; "
            f"held passes {sum(v['passes_made'] for v in rm.values())} ({time.perf_counter() - t1:.0f} s)")
    else:
        results.append("skip Phase 0 capture not on this PC (runs/2026-11-16-V1-phase0/race_1/raw/udp.bin)")
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
    opts = {"--seed": None, "--gamedb": None, "--track": TRACK_AUSTRIA, "--perms": str(N_PERMS)}
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
               int(opts["--perms"]), allow)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
