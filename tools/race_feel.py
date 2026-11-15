#!/usr/bin/env python3
"""Race Feel metrics (docs/race_feel_plan.md), per car per race, from a tools/udp_capture.py recording.

Usage:
    python -I tools/race_feel.py udp.bin --out runs/<id>        # writes race_feel.csv and race_feel_summary.json
    python -I tools/race_feel.py --selftest                     # synthetic checks of every metric (exit 0 = pass)

Reads the race session (the one with the most LapData frames) through tools/udp_parse.py. The player car (the
header's player index) is never scored, but it still counts as a car ahead or behind. All times are session time.

Metrics, as the plan defines them (the choices the plan leaves open are marked CHOICE):
1. Lap 1
   - lap1_loss_s: the car's lap-1 time minus the race's median green-flag lap. CHOICE: green-flag laps are AI laps 2+
     without a pit stop, within 110% of the median of all such laps (that drops safety-car and incident laps).
   - lap1_pos_change: |grid - position at the end of lap 1|. Summary: the sum, and the held changes (held passes made
     on lap 1).
   - lap1_spread_s: from the first to the last car to start lap 2 (cars that started it).
   - lap1_collisions: COLL events while the vehicle is on lap 1.
2. Trains
   - train_s / laps2_s: time on laps 2+ within 1.0 s of the car ahead (LapData deltaToCarInFront), weighted by the
     time between frames (capped at 0.5 s), WITHOUT a held pass on that car before the end of the next lap (the 2-lap
     horizon). CHOICE: samples in the pit lane don't count.
   - held_passes_net_2plus (primary): OVTK made on laps 2+ that the same pair doesn't reverse within 10 s AND that
     isn't itself a restoration (reversing that pair's pass from within the previous 10 s), so a flip-flop nets 0.
   - Pit cycles: an OVTK within 20 s of either car's pit-lane time is a pit cycle, not a pass; it never counts as
     net (pit_cycle_passes reports them).
   - held_passes_2plus: the #71 definition (as tools/b0014_check.py), where a restoration counts as held; kept for
     comparability with B-0014.
   - longest train: at each lap line of the leader (lap 2+), the longest run of consecutive cars each within 1.0 s of
     the car ahead, in cars. Summary: the per-race median and max.
3. Sudden braking
   - Braking (supervisor ruling 2026-11-15; by-eye validation in docs/race_feel/phantom_validation.md):
     early_brakes_total = early_brakes_in_traffic (a car within 1.0 s ahead) + phantom_brakes (clear road ahead;
     phantom_brakes_clear2s uses 2.0 s). The Race Feel braking primary is early_brakes_total. Onsets: one per
     braking zone (released >= 1 s before), and pulses within 0.5 s / 20 m of the last onset are merged into it.
     Each counted onset: a brake onset (brake rising above 0.3), while a car is within 1.0 s behind, that starts more
     than 50 m before the reference onset of the next corner ahead (within 300 m). Corner rule (supervisor ruling,
     2026-11-14): a CLEAN corner pass has no car within 2.0 s ahead at any sample in the 300 m before its onset
     (laps 2+, no pit lap). Corners are clusters (30 m) of all cars' clean onsets. A car's own reference is the median
     of its >= 2 clean passes of that corner; otherwise the FIELD median is used (ref=field). A corner with < 4 clean
     passes field-wide is unscored (NA). Phantoms are reported by ref (own / field); the summary gives cars scored,
     the share of onsets scored and the ref counts.
     Validate on 2 races by eye before trusting it (the plan). A car with no clean-lap corner (always in traffic)
     reports NA with phantom_scored 0, never 0; the summary gives phantom_cars_scored.
   - rear_end_as_follower / as_leader: COLL where the two cars' total distance (interpolated between the LapData
     frames either side of the event) differs by 3 to 12 m (CHOICE: under
     3 m is alongside, so a side-swipe; over 12 m isn't a rear-end). The car with less distance is the follower.
   - front_wing_increments / front_wing_added: CarDamage increases of the front-left or front-right wing.
   - Contact outcome, 2 s after each COLL, per car: wing hit (any wing +8 % or more), spin (under 8 m/s), or 2+ places
     lost; costly = any of them. Per car: costly_contacts, contact_wing_hits; the summary lists every contact with its
     pair, kind and outcome.
4. No-harm guards (summary): collisions, wing damage added (all three wings), DNFs, penalties, median green lap.
"""
from __future__ import annotations

import argparse
import bisect
import csv
import json
import statistics
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import udp_parse as u  # noqa: E402

HOLD_S = 10.0
ONSET_LOG: list[dict] = []   # filled by analyse(): every scored onset, for tools/phantom_plots.py (by-eye validation)
TRAIN_GAP_S = 1.0
CLEAN_GAP_S = 2.0
BRAKE_ON = 0.3
BRAKE_OFF = 0.05         # the brake counts as released below this
RELEASE_S = 1.0          # a new braking zone needs the brake released for at least this long (the AI pulses the brake)
MERGE_S, MERGE_M = 0.5, 20.0   # onsets this close (time or distance, same lap) to the previous one are the same onset
CLEAR_AHEAD_S = 1.0      # phantom_brake = clear road: no car within this ahead (2.0 s reported as a variant)
PHANTOM_M = 50.0
CLUSTER_M = 30.0
CORNER_AHEAD_M = 300.0
CLEAN_WINDOW_M = 300.0   # a clean corner pass: no car within CLEAN_GAP_S ahead in this distance before the onset
OWN_MIN_PASSES = 2       # a car's own corner reference needs this many clean passes; else the field's
FIELD_MIN_PASSES = 4     # a corner with fewer clean passes field-wide is unscored (NA)
REAR_MIN_M, REAR_MAX_M = 3.0, 12.0
DT_CAP_S = 0.5
GREEN_FACTOR = 1.10
PIT_CYCLE_S = 20.0      # an OVTK within this of either car's pit-lane time is a pit cycle, not a pass
OUTCOME_S = 2.0         # contact outcome judged this long after the COLL
OUTCOME_WING = 8        # wing damage percent added (any wing) that counts as a wing hit
OUTCOME_SPIN_MS = 8.0   # speed (m/s) under which the car counts as spun or stopped
OUTCOME_PLACES = 2      # places lost that count as a costly contact
L_FRONT_MS, L_FRONT_MIN = 6, 7
FINISHED = 3  # FinalClassification result status


# ---------- pure metric functions (the selftest calls these directly) ----------

def held_passes(ovtk: list[tuple[float, int, int]], hold: float = HOLD_S) -> list[dict]:
    """OVTK (time, overtaker, overtaken), with the time until the same pair swaps back, whether it's held (as #71 and
    tools/b0014_check.py: a reversal that isn't itself reversed counts as held), whether it restores a pass from the
    previous `hold` s, and `net` = held and not a restoration (the Race Feel primary)."""
    ovtk = sorted(ovtk)
    out = []
    for i, (t, a, b) in enumerate(ovtk):
        back = next((t2 - t for t2, a2, b2 in ovtk[i + 1:] if a2 == b and b2 == a), float("inf"))
        # a restoration undoes the same pair's pass from within the previous `hold` s (the flip-flop's second half)
        restore = any(a0 == b and b0 == a and 0 <= t - t0 <= hold for t0, a0, b0 in ovtk[:i])
        out.append({"t": t, "car": a, "other": b, "back": back, "held": back > hold, "restore": restore,
                    "net": back > hold and not restore})
    return out


def pit_intervals(samples: list[tuple[float, bool]]) -> list[tuple[float, float]]:
    """samples = [(t, in_pit_lane)] in time order; returns the [start, end] times of each pit-lane visit."""
    out, start, last = [], None, None
    for t, pit in samples:
        if pit and start is None:
            start = t
        if not pit and start is not None:
            out.append((start, last if last is not None else t))
            start = None
        last = t
    if start is not None:
        out.append((start, last))
    return out


def near_pit(t: float, intervals: list[tuple[float, float]], window: float = PIT_CYCLE_S) -> bool:
    return any(a - window <= t <= b + window for a, b in intervals)


def mark_pit_cycles(passes: list[dict], pits: dict[int, list[tuple[float, float]]]) -> None:
    """Sets p['pit_cycle'] (either car within PIT_CYCLE_S of a pit-lane visit) and narrows p['net'] to real passes."""
    for p in passes:
        p["pit_cycle"] = near_pit(p["t"], pits.get(p["car"], [])) or near_pit(p["t"], pits.get(p["other"], []))
        p["net"] = p["net"] and not p["pit_cycle"]


def contact_outcome(before: dict, after: dict) -> dict:
    """One car's outcome of a contact. before/after: {'wings': (fl, fr, rear), 'speed_ms': float, 'pos': int}, taken
    at the COLL and OUTCOME_S later. Returns the flags and whether the contact cost the car anything."""
    wing_add = sum(max(0, b - a) for a, b in zip(before["wings"], after["wings"]))
    out = {"wing_hit": wing_add >= OUTCOME_WING, "spin": after["speed_ms"] < OUTCOME_SPIN_MS,
           "places_lost": max(0, after["pos"] - before["pos"]) >= OUTCOME_PLACES, "wing_added": wing_add}
    out["costly"] = out["wing_hit"] or out["spin"] or out["places_lost"]
    return out


def train_time(samples: dict[int, list[tuple]], passes: list[dict], lap_starts: dict[int, dict[int, float]],
               gap: float = TRAIN_GAP_S) -> dict[int, tuple[float, float]]:
    """samples[car] = [(t, lap, gap_ahead_s, ahead_car, in_pit)] in time order. Returns car -> (train_s, laps2_s)."""
    held = defaultdict(list)
    for p in passes:
        if p["held"]:
            held[(p["car"], p["other"])].append(p["t"])
    out = {}
    for car, rows in samples.items():
        train = total = 0.0
        for i, (t, lap, g, ahead, pit) in enumerate(rows):
            if lap < 2 or pit:
                continue
            dt = min(rows[i + 1][0] - t, DT_CAP_S) if i + 1 < len(rows) else 0.0
            total += dt
            if g is None or g > gap or ahead is None:
                continue
            horizon = lap_starts.get(car, {}).get(lap + 2, float("inf"))
            if any(t <= pt < horizon for pt in held[(car, ahead)]):
                continue
            train += dt
        out[car] = (train, total)
    return out


def longest_train(gaps_in_order: list[float | None], gap: float = TRAIN_GAP_S) -> int:
    """gaps_in_order: each car's gap to the car ahead, in race order (the leader's is None). Longest train in cars."""
    best = run = 1 if gaps_in_order else 0
    for g in gaps_in_order[1:]:
        run = run + 1 if g is not None and g <= gap else 1
        best = max(best, run)
    return best


def brake_onsets(rows: list[tuple[float, int, float, float]], on: float = BRAKE_ON,
                 off: float = BRAKE_OFF, release_s: float = RELEASE_S) -> list[tuple[float, int, float]]:
    """rows = [(t, lap, lap_distance, brake)]; returns [(t, lap, lap_distance)], one per braking ZONE: the first rise
    above `on` after the brake has been released (below `off`) for at least `release_s`. The AI pulses the brake inside
    a zone (by-eye validation, 2026-11-15), so a bare rising edge would count every pulse as a new onset."""
    out, released_since = [], None
    armed = True
    for t, lap, d, b in rows:
        if b < off:
            if released_since is None:
                released_since = t
            if t - released_since >= release_s:
                armed = True
        else:
            released_since = None
        if armed and b > on:
            if out and out[-1][1] == lap and (t - out[-1][0] <= MERGE_S or abs(d - out[-1][2]) <= MERGE_M):
                pass   # a pulse right after the last onset: the same onset (supervisor ruling, 2026-11-15)
            else:
                out.append((t, lap, d))
            armed = False
    return out


def signed_ahead(target: float, d: float, track_len: float | None) -> float:
    """target - d along the lap, wrapped into [-L/2, L/2) when the track length is known."""
    x = target - d
    if track_len:
        x = (x + track_len / 2) % track_len - track_len / 2
    return x


def corners(clean_onsets: list[float], cluster: float = CLUSTER_M) -> list[float]:
    """Clean-lap onset distances clustered within `cluster` m; returns each cluster's median, sorted."""
    out, group = [], []
    for d in sorted(clean_onsets):
        if group and d - group[-1] > cluster:
            out.append(statistics.median(group))
            group = []
        group.append(d)
    if group:
        out.append(statistics.median(group))
    return out


def clean_before(samples: list[tuple[float, float, float | None]], t: float, d: float,
                 window: float = CLEAN_WINDOW_M, gap: float = CLEAN_GAP_S, track_len: float | None = None) -> bool:
    """samples = [(t, lap_distance, gap_ahead_s)] of one car in time order. True if no sample in the `window` metres
    before the onset at (t, d) has a car within `gap` s ahead (gap None = leader or no data: clear)."""
    i = bisect.bisect_right([x[0] for x in samples], t) - 1
    covered = 0.0
    prev_d = d
    while i >= 0:
        st, sd, sg = samples[i]
        back = prev_d - sd
        if track_len and back < -track_len / 2:
            back += track_len      # crossed the line going backwards in time
        if back < 0:
            break                  # a reset or a new lap we can't follow
        covered += back
        if covered > window:
            break
        if sg is not None and sg <= gap:
            return False
        prev_d = sd
        i -= 1
    return True


def corner_table(clean: dict[int, list[float]], cluster: float = CLUSTER_M) -> list[dict]:
    """clean[car] = onset distances of that car's clean corner passes (laps 2+). Corners are clusters of all cars'
    clean onsets within `cluster` m. Each corner: field median, field count, and own medians for cars with
    >= OWN_MIN_PASSES passes. Corners with < FIELD_MIN_PASSES are kept but flagged unscored."""
    allpts = sorted((d, c) for c, ds in clean.items() for d in ds)
    groups, cur = [], []
    for d, c in allpts:
        if cur and d - cur[-1][0] > cluster:
            groups.append(cur)
            cur = []
        cur.append((d, c))
    if cur:
        groups.append(cur)
    out = []
    for g in groups:
        by_car = defaultdict(list)
        for d, c in g:
            by_car[c].append(d)
        out.append({"field": statistics.median(d for d, _ in g), "count": len(g),
                    "scored": len(g) >= FIELD_MIN_PASSES,
                    "own": {c: statistics.median(ds) for c, ds in by_car.items() if len(ds) >= OWN_MIN_PASSES}})
    return out


def classify_onset(car: int, onset_d: float, table: list[dict], track_len: float | None,
                   out: dict | None = None) -> tuple[str, bool | None]:
    """('own'|'field', phantom?) for an onset, against the next corner ahead (within CORNER_AHEAD_M), or ('NA', None)
    when no corner is near enough or that corner is unscored."""
    best = None
    for corner in table:
        ahead = signed_ahead(corner["field"], onset_d, track_len)
        if -CLUSTER_M <= ahead <= CORNER_AHEAD_M and (best is None or ahead < best[0]):
            best = (ahead, corner)
    if best is None or not best[1]["scored"]:
        return "NA", None
    corner = best[1]
    if car in corner["own"]:
        ref, kind = corner["own"][car], "own"
    else:
        ref, kind = corner["field"], "field"
    ahead = signed_ahead(ref, onset_d, track_len)
    if out is not None:
        out.update(ref=ref, early_m=ahead, corner=corner["field"])
    return kind, ahead > PHANTOM_M


def phantom(onset_d: float, corner_list: list[float], track_len: float | None) -> bool | None:
    """True if the onset is more than PHANTOM_M before the next corner's onset; None if no corner is near enough."""
    best = None
    for c in corner_list:
        ahead = c - onset_d
        if track_len and ahead < -CLUSTER_M:
            ahead += track_len  # the corner is past the line
        if -CLUSTER_M <= ahead <= CORNER_AHEAD_M and (best is None or ahead < best):
            best = ahead
    if best is None:
        return None
    return best > PHANTOM_M


def contact_kind(dist_a: float, dist_b: float) -> tuple[str, int | None]:
    """('rear_end', 0 if a is the follower else 1) or ('side', None) or ('other', None), from total distances."""
    d = abs(dist_a - dist_b)
    if d < REAR_MIN_M:
        return "side", None
    if d <= REAR_MAX_M:
        return "rear_end", 0 if dist_a < dist_b else 1
    return "other", None


def wing_increments(records: list[tuple[int, int, int]]) -> tuple[int, int]:
    """records = [(fl, fr, rear)] in time order for one car: (front-wing increases, front-wing percent added)."""
    n = added = 0
    for prev, cur in zip(records, records[1:]):
        for k in (0, 1):
            if cur[k] > prev[k]:
                n += 1
                added += cur[k] - prev[k]
    return n, added


# ---------- reading a race from udp_parse ----------

def gap_ahead(car: tuple) -> float | None:
    ms, mins = car[L_FRONT_MS], car[L_FRONT_MIN]
    if ms == 0 and mins == 0:
        return None  # the leader, or no data
    return mins * 60 + ms / 1000


def race_session(sessions: dict) -> tuple[int, dict]:
    races = [(uid, s) for uid, s in sessions.items() if s["type"] == 15]
    pool = races or list(sessions.items())
    return max(pool, key=lambda kv: len(kv[1]["lap_frames"]))


def analyse(capture: Path) -> tuple[list[dict], dict]:
    sessions = u.parse(capture, [])
    if not sessions:
        raise SystemExit("no sessions in the capture")
    ONSET_LOG.clear()
    uid, s = race_session(sessions)
    frames = s["lap_frames"]
    if not frames:
        raise SystemExit("the race session has no LapData")
    n = s["n_active"] or s.get("cars", u.CARS)
    player = s.get("player")
    ai = [c for c in range(n) if c != player]
    track_len = s.get("track_length")
    ftimes = [t for t, _ in frames]

    def frame_at(t: float):
        i = bisect.bisect_right(ftimes, t) - 1
        return frames[max(i, 0)][1]

    def dist_at(car: int, t: float) -> float:
        """Total distance at time t, interpolated between the neighbouring LapData frames."""
        i = bisect.bisect_right(ftimes, t) - 1
        if i < 0:
            return frames[0][1][car][u.L_TOTDIST]
        if i + 1 >= len(frames):
            return frames[i][1][car][u.L_TOTDIST]
        t0, t1 = ftimes[i], ftimes[i + 1]
        d0, d1 = frames[i][1][car][u.L_TOTDIST], frames[i + 1][1][car][u.L_TOTDIST]
        return d0 + (d1 - d0) * ((t - t0) / (t1 - t0) if t1 > t0 else 0.0)

    # lap starts, lap times, positions at the end of lap 1, grid
    lap_starts: dict[int, dict[int, float]] = defaultdict(dict)
    lap_times: dict[int, dict[int, float]] = defaultdict(dict)
    pit_laps: dict[int, set] = defaultdict(set)
    pos_end_lap1: dict[int, int] = {}
    last_lap = {}
    for t, cars in frames:
        for c in range(n):
            lap = cars[c][u.L_LAPNUM]
            if cars[c][u.L_PIT]:
                pit_laps[c].add(lap)
            if c in last_lap and lap == last_lap[c] + 1:
                lap_starts[c][lap] = t
                if cars[c][u.L_LAST] > 0:
                    lap_times[c][last_lap[c]] = cars[c][u.L_LAST] / 1000
                if lap == 2:
                    pos_end_lap1[c] = cars[c][u.L_POS]
            last_lap[c] = lap
    grid = {c: u.grid_of(s, frames[0][1][c]) for c in range(n)}
    pits = {c: pit_intervals([(t, bool(cars[c][u.L_PIT])) for t, cars in frames]) for c in range(n)}

    others = [lt for c in ai for lap, lt in lap_times[c].items() if lap >= 2 and lap not in pit_laps[c]]
    green_med = None
    if others:
        m0 = statistics.median(others)
        green = [x for x in others if x <= GREEN_FACTOR * m0]
        green_med = statistics.median(green) if green else None

    # events
    def lap_of(car: int, t: float) -> int:
        return frame_at(t)[car][u.L_LAPNUM]
    ovtk = [(st, f["vehicle"], f["other"]) for st, _, code, f in s["events"] if code == "OVTK" and "vehicle" in f]
    passes = held_passes(ovtk)
    for p in passes:
        p["lap"] = lap_of(p["car"], p["t"]) if p["car"] < n else 0
    mark_pit_cycles(passes, pits)
    coll = [(st, f["vehicle"], f["other"]) for st, _, code, f in s["events"] if code == "COLL" and "vehicle" in f]
    pena = defaultdict(int)
    for _, _, code, f in s["events"]:
        if code == "PENA" and "vehicle" in f:
            pena[f["vehicle"]] += 1
    retired = {f["vehicle"] for _, _, code, f in s["events"] if code == "RTMT" and "vehicle" in f}

    # trains: per-car samples, and the longest train at each of the leader's lap lines
    samples = {c: [] for c in ai}
    leader_lap, trains = 1, []
    for t, cars in frames:
        by_pos = {cars[c][u.L_POS]: c for c in range(n) if cars[c][u.L_POS]}
        for c in ai:
            g = gap_ahead(cars[c])
            samples[c].append((t, cars[c][u.L_LAPNUM], g, by_pos.get(cars[c][u.L_POS] - 1), bool(cars[c][u.L_PIT])))
        lead = by_pos.get(1)
        if lead is not None and cars[lead][u.L_LAPNUM] > leader_lap:
            leader_lap = cars[lead][u.L_LAPNUM]
            if leader_lap >= 2:
                order = [by_pos[p] for p in sorted(by_pos)]
                trains.append(longest_train([None] + [gap_ahead(cars[c]) for c in order[1:]]))
    tt = train_time(samples, passes, lap_starts)

    # sudden braking (2026-11-14 ruling): corner references from clean CORNER passes, own (>= 2) or field (>= 4)
    gap_samples = {c: [(t, cars[c][u.L_LAPDIST], gap_ahead(cars[c])) for t, cars in frames] for c in range(n)}
    onsets = {}
    clean = defaultdict(list)
    for c in ai:
        rows = []
        for t, brakes in s["brake_frames"]:
            car = frame_at(t)[c]
            rows.append((t, car[u.L_LAPNUM], car[u.L_LAPDIST], brakes[c]))
        onsets[c] = brake_onsets(rows)
        for t, lap, d in onsets[c]:
            if lap >= 2 and lap not in pit_laps[c] and d >= 0 and clean_before(gap_samples[c], t, d, track_len=track_len):
                clean[c].append(d)
    table = corner_table(clean)
    phantoms = defaultdict(lambda: {"own": 0, "field": 0})   # all early onsets with a follower (the braking primary)
    early_traffic = defaultdict(int)   # car within CLEAR_AHEAD_S ahead: early braking in a train
    clear_road = defaultdict(int)      # no car within CLEAR_AHEAD_S ahead: the "unexplained" phantom
    clear_road_2s = defaultdict(int)   # variant: no car within 2.0 s ahead
    scored = defaultdict(int)
    with_follower = defaultdict(int)
    ref_count = {"own": 0, "field": 0}
    for c in ai:
        for t, lap, d in onsets[c]:
            if lap < 1 or d < 0:
                continue
            cars = frame_at(t)
            pos = cars[c][u.L_POS]
            behind = next((x for x in range(n) if cars[x][u.L_POS] == pos + 1), None)
            gb = gap_ahead(cars[behind]) if behind is not None else None
            if gb is None or gb > TRAIN_GAP_S:
                continue
            with_follower[c] += 1
            info = {}
            kind, is_ph = classify_onset(c, d, table, track_len, info)
            if kind == "NA":
                continue
            ONSET_LOG.append({"car": c, "t": t, "lap": lap, "d": d, "kind": kind, "phantom": bool(is_ph),
                              "follower_gap_s": gb, "ahead_gap_s": gap_ahead(cars[c]), **info})
            scored[c] += 1
            ref_count[kind] += 1
            if is_ph:
                phantoms[c][kind] += 1
                ga = gap_ahead(cars[c])
                if ga is not None and ga <= CLEAR_AHEAD_S:
                    early_traffic[c] += 1
                else:
                    clear_road[c] += 1
                if ga is None or ga > 2.0:
                    clear_road_2s[c] += 1
    phantom_scored = {c for c in ai if scored[c]}

    # contacts
    ttimes = [t for t, _ in s["tel_frames"]]
    dmg_by_car = defaultdict(list)
    for t, c, rec in s["damage"]:
        dmg_by_car[c].append((t, rec[:3]))

    def state_at(car: int, t: float) -> dict:
        i = max(bisect.bisect_right(ttimes, t) - 1, 0)
        speed = s["tel_frames"][i][1][car] / 3.6 if s["tel_frames"] else 99.0
        wings = (0, 0, 0)
        for dt, w in dmg_by_car.get(car, []):
            if dt > t:
                break
            wings = w
        return {"wings": wings, "speed_ms": speed, "pos": frame_at(t)[car][u.L_POS]}

    costly, wing_hits, contacts_out = defaultdict(int), defaultdict(int), []
    lap1_costly = 0
    rear_f, rear_l, lap1_coll, coll_n = defaultdict(int), defaultdict(int), 0, defaultdict(int)
    for t, a, b in coll:
        if a >= n or b >= n:
            continue
        coll_n[a] += 1
        coll_n[b] += 1
        cars = frame_at(t)
        if cars[a][u.L_LAPNUM] == 1:
            lap1_coll += 1
        kind, who = contact_kind(dist_at(a, t), dist_at(b, t))
        oc = {x: contact_outcome(state_at(x, t), state_at(x, t + OUTCOME_S)) for x in (a, b)}
        for x in (a, b):
            costly[x] += oc[x]["costly"]
            wing_hits[x] += oc[x]["wing_hit"]
        if cars[a][u.L_LAPNUM] == 1 and (oc[a]["costly"] or oc[b]["costly"]):
            lap1_costly += 1
        contacts_out.append({"t": round(t, 3), "cars": [a, b], "kind": kind,
                             "outcome": {str(x): {k: v for k, v in oc[x].items()} for x in (a, b)}})
        if kind == "rear_end":
            follower, leader = (a, b) if who == 0 else (b, a)
            rear_f[follower] += 1
            rear_l[leader] += 1

    # damage
    dmg = defaultdict(list)
    for _, c, rec in s["damage"]:
        dmg[c].append(rec[:3])
    final = s["final"]

    rows = []
    for c in ai:
        part = (s["participants"] or [{}] * n)[c] if s["participants"] else {}
        l1 = lap_times[c].get(1)
        fw_n, fw_add = wing_increments(dmg[c]) if dmg[c] else (0, 0)
        all_add = sum(max(0, cur[k] - prev[k]) for prev, cur in zip(dmg[c], dmg[c][1:]) for k in range(3))
        dnf = (final[c]["result_status"] != FINISHED) if final else (c in retired)
        train_s, laps2_s = tt.get(c, (0.0, 0.0))
        made = [p for p in passes if p["car"] == c]
        rows.append({
            "session_uid": uid, "car": c, "name": part.get("name", "NA"), "grid": grid.get(c),
            "lap1_time_s": round(l1, 3) if l1 else "NA",
            "lap1_loss_s": round(l1 - green_med, 3) if l1 and green_med else "NA",
            "lap1_pos_change": abs(grid[c] - pos_end_lap1[c]) if c in pos_end_lap1 and grid.get(c) else "NA",
            "lap1_held_changes": sum(1 for p in made if p["held"] and p["lap"] == 1),
            "train_s": round(train_s, 2), "laps2_s": round(laps2_s, 2),
            "train_share": round(train_s / laps2_s, 4) if laps2_s else "NA",
            "held_passes_net_2plus": sum(1 for p in made if p["net"] and p["lap"] >= 2),
            "held_passes_2plus": sum(1 for p in made if p["held"] and p["lap"] >= 2),
            "held_suffered_2plus": sum(1 for p in passes if p["other"] == c and p["held"] and p["lap"] >= 2),
            "early_brakes_total": (phantoms[c]["own"] + phantoms[c]["field"]) if c in phantom_scored else "NA",
            "early_brakes_in_traffic": early_traffic[c] if c in phantom_scored else "NA",
            "phantom_brakes": clear_road[c] if c in phantom_scored else "NA",
            "phantom_brakes_clear2s": clear_road_2s[c] if c in phantom_scored else "NA",
            "phantom_brakes_own_ref": phantoms[c]["own"] if c in phantom_scored else "NA",
            "phantom_brakes_field_ref": phantoms[c]["field"] if c in phantom_scored else "NA",
            "onsets_with_follower": with_follower[c], "onsets_scored": scored[c],
            "phantom_scored": int(c in phantom_scored),
            "rear_end_as_follower": rear_f[c], "rear_end_as_leader": rear_l[c],
            "front_wing_increments": fw_n, "front_wing_added": fw_add, "wing_damage_added": all_add,
            "collisions": coll_n[c], "costly_contacts": costly[c], "contact_wing_hits": wing_hits[c],
            "pit_cycle_passes": sum(1 for p in made if p["pit_cycle"]),
            "penalties": pena[c], "dnf": int(bool(dnf)),
        })

    starts2 = [lap_starts[c][2] for c in range(n) if 2 in lap_starts[c]]
    tot_train = sum(r["train_s"] for r in rows)
    tot_laps2 = sum(r["laps2_s"] for r in rows)
    losses = [r["lap1_loss_s"] for r in rows if r["lap1_loss_s"] != "NA"]
    summary = {
        "session_uid": uid, "track_id": s["track"], "track_length_m": track_len, "laps": s["laps"],
        "ai_difficulty": s.get("ai_difficulty"), "player_car": player, "ai_cars": len(ai),
        "median_green_lap_s": round(green_med, 3) if green_med else None,
        "lap1_loss_median_s": round(statistics.median(losses), 3) if losses else None,
        "lap1_positions_changed": sum(r["lap1_pos_change"] for r in rows if r["lap1_pos_change"] != "NA"),
        "lap1_held_changes": sum(r["lap1_held_changes"] for r in rows),
        "lap1_spread_s": round(max(starts2) - min(starts2), 3) if len(starts2) > 1 else None,
        "lap1_collisions": lap1_coll,
        "train_time_share": round(tot_train / tot_laps2, 4) if tot_laps2 else None,
        "held_passes_net_2plus": sum(r["held_passes_net_2plus"] for r in rows),
        "held_passes_2plus_as_71": sum(r["held_passes_2plus"] for r in rows),
        "ovtk_raw": len(passes),
        "longest_train_median": statistics.median(trains) if trains else None,
        "longest_train_max": max(trains) if trains else None,
        "early_brakes_total": sum(r["early_brakes_total"] for r in rows if r["phantom_scored"]),
        "early_brakes_in_traffic": sum(r["early_brakes_in_traffic"] for r in rows if r["phantom_scored"]),
        "phantom_brakes": sum(r["phantom_brakes"] for r in rows if r["phantom_scored"]),
        "phantom_brakes_clear2s": sum(r["phantom_brakes_clear2s"] for r in rows if r["phantom_scored"]),
        "phantom_cars_scored": sum(r["phantom_scored"] for r in rows),
        "phantom_onsets_scored_share": round(sum(scored.values()) / sum(with_follower.values()), 3) if sum(with_follower.values()) else None,
        "phantom_ref_counts": ref_count,
        "phantom_by_ref": {"own": sum(v["own"] for v in phantoms.values()), "field": sum(v["field"] for v in phantoms.values())},
        "corners": {"total": len(table), "scored": sum(1 for x in table if x["scored"])},
        "rear_end_contacts": sum(r["rear_end_as_follower"] for r in rows),
        "pit_cycle_passes": sum(1 for p in passes if p["pit_cycle"]),
        "contacts": contacts_out,
        "costly_contact_cars": sum(r["costly_contacts"] for r in rows),
        "lap1_costly_contacts": lap1_costly,
        "front_wing_increments": sum(r["front_wing_increments"] for r in rows),
        "guards": {"collisions": len(coll), "wing_damage_added": sum(r["wing_damage_added"] for r in rows),
                   "dnfs": sum(r["dnf"] for r in rows), "penalties": sum(pena.values()),
                   "median_green_lap_s": round(green_med, 3) if green_med else None},
        "damage_packets_seen": bool(s["damage"]), "bad_sizes": s["bad_sizes"],
    }
    return rows, summary


def write(rows: list[dict], summary: dict, out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    with (out / "race_feel.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]) if rows else ["session_uid"])
        w.writeheader()
        w.writerows(rows)
    (out / "race_feel_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")


# ---------- selftest ----------

def selftest() -> int:
    failed = 0

    def check(label: str, ok: bool, got) -> None:
        nonlocal failed
        failed += not ok
        print(f"{'ok  ' if ok else 'FAIL'} {label}: {got}")

    # a pass reversed at 9 s isn't held; one reversed at 11 s is
    p = held_passes([(100.0, 1, 2), (109.0, 2, 1), (200.0, 3, 4), (211.0, 4, 3)])
    check("pass reversed at 9 s is not held", not p[0]["held"] and p[1]["held"] is True, [x["held"] for x in p])
    check("pass reversed at 11 s is held", p[2]["held"] and p[3]["held"], [x["held"] for x in p])
    check("a pass plus its reversal at 9 s nets 0", sum(x["net"] for x in p[:2]) == 0 and p[1]["restore"],
          [(x["held"], x["restore"], x["net"]) for x in p[:2]])
    check("a reversal after 11 s is a new held pass, not a restoration",
          p[2]["net"] and p[3]["net"] and not p[3]["restore"], [(x["held"], x["restore"], x["net"]) for x in p[2:]])

    # a train of 4: leader, then three cars each within 1.0 s, then a gap, then two close cars
    check("longest train of 4", longest_train([None, 0.6, 0.9, 0.4, 2.5, 0.8]) == 4,
          longest_train([None, 0.6, 0.9, 0.4, 2.5, 0.8]))
    # train time: 10 s at 0.5 s gaps behind car 9; a held pass on car 9 later in the same lap clears it
    rows = [(float(t), 2, 0.5, 9, False) for t in range(0, 11)]
    t1 = train_time({1: rows}, [], {1: {2: 0.0, 3: 70.0, 4: 140.0}})
    t2 = train_time({1: rows}, [{"t": 50.0, "car": 1, "other": 9, "held": True}], {1: {2: 0.0, 3: 70.0, 4: 140.0}})
    check("train time counts time stuck behind (5 s at the 0.5 s cap)", abs(t1[1][0] - 5.0) < 1e-9, t1)
    check("a held pass within 2 laps clears it", t2[1][0] == 0.0, t2)

    # phantom brake: corner onset at 1000 m on clean laps; an onset 60 m early is phantom, 20 m early isn't
    cl = corners([998.0, 1000.0, 1003.0, 2500.0, 2510.0])
    check("corners clustered", [round(c) for c in cl] == [1000, 2505], cl)
    check("onset 60 m early is phantom", phantom(940.0, cl, 4300.0) is True, phantom(940.0, cl, 4300.0))
    check("onset 20 m early is normal", phantom(980.0, cl, 4300.0) is False, phantom(980.0, cl, 4300.0))
    check("onset far from any corner is not scored", phantom(1700.0, cl, 4300.0) is None, phantom(1700.0, cl, 4300.0))
    check("corner past the line wraps", phantom(4280.0, [40.0], 4300.0) is True, phantom(4280.0, [40.0], 4300.0))
    ons = brake_onsets([(0, 2, 900.0, 0.0), (1, 2, 940.0, 0.5), (2, 2, 960.0, 0.8), (3, 2, 990.0, 0.1), (4, 2, 1000.0, 0.6)])
    check("pulses inside one zone are one onset", [d for _, _, d in ons] == [940.0], ons)
    zone2 = brake_onsets([(0, 2, 900.0, 0.0), (1, 2, 940.0, 0.5), (2, 2, 960.0, 0.0), (3.5, 2, 1100.0, 0.0), (4, 2, 1150.0, 0.6)])
    check("a new zone after >= 1 s released", [d for _, _, d in zone2] == [940.0, 1150.0], zone2)
    near = brake_onsets([(0, 2, 900.0, 0.0), (1.2, 2, 940.0, 0.6), (1.3, 2, 945.0, 0.0), (2.4, 2, 950.0, 0.0), (2.6, 2, 955.0, 0.7)])
    check("an onset within 20 m of the last is merged", [d for _, _, d in near] == [940.0], near)
    tb = corner_table({1: [400.0, 402.0], 2: [398.0], 3: [401.0]})
    k4 = classify_onset(1, 430.0, tb, 4318.0)
    check("onset 30 m after the corner isn't wrapped to a lap early", k4 == ("own", False), k4)

    # pit cycles: a pass 15 s after the overtaken car left the pit lane is a pit cycle; 25 s after is a pass
    iv = pit_intervals([(100.0, False), (101.0, True), (120.0, True), (121.0, False)])
    check("pit-lane interval", iv == [(101.0, 120.0)], iv)
    pp = held_passes([(135.0, 1, 2), (145.5, 3, 2)])
    mark_pit_cycles(pp, {2: iv})
    check("pass 15 s after a pit visit is a pit cycle", pp[0]["pit_cycle"] and not pp[0]["net"], pp[0])
    check("pass 25.5 s after it is a real pass", not pp[1]["pit_cycle"] and pp[1]["net"], pp[1])

    # contact outcomes
    calm = contact_outcome({"wings": (0, 0, 0), "speed_ms": 60.0, "pos": 5}, {"wings": (3, 0, 0), "speed_ms": 58.0, "pos": 5})
    check("light touch is not costly", not calm["costly"], calm)
    hit = contact_outcome({"wings": (0, 0, 0), "speed_ms": 60.0, "pos": 5}, {"wings": (12, 0, 0), "speed_ms": 55.0, "pos": 5})
    check("front-wing +12 is a wing hit", hit["wing_hit"] and hit["costly"], hit)
    spin = contact_outcome({"wings": (0, 0, 0), "speed_ms": 60.0, "pos": 5}, {"wings": (0, 0, 0), "speed_ms": 4.0, "pos": 6})
    check("under 8 m/s is a spin", spin["spin"] and not spin["places_lost"], spin)
    lost = contact_outcome({"wings": (0, 0, 0), "speed_ms": 60.0, "pos": 5}, {"wings": (0, 0, 0), "speed_ms": 50.0, "pos": 7})
    check("2 places lost is costly", lost["places_lost"] and lost["costly"], lost)

    # clean corner window: a car within 2.0 s ahead 200 m before the onset makes it unclean; 350 m before doesn't
    samp = [(float(i), 1000.0 + 50 * i, 3.0) for i in range(12)]          # 50 m per second, gap 3 s
    check("clean when nothing within 2 s in the 300 m", clean_before(samp, 11.0, 1550.0), clean_before(samp, 11.0, 1550.0))
    s2 = [(t, d, (1.5 if t == 7.0 else g)) for t, d, g in samp]               # 200 m before the onset
    check("unclean when a car is within 2 s 200 m before", not clean_before(s2, 11.0, 1550.0), clean_before(s2, 11.0, 1550.0))
    s3 = [(t, d, (1.5 if t == 4.0 else g)) for t, d, g in samp]               # 350 m before the onset
    check("a close car 350 m before doesn't count", clean_before(s3, 11.0, 1550.0), clean_before(s3, 11.0, 1550.0))
    # own reference needs 2 passes; field fallback; unscored corner
    tbl = corner_table({1: [1000.0, 1004.0], 2: [998.0], 3: [1002.0], 4: [2500.0], 5: [2510.0]})
    check("two corners found", len(tbl) == 2, [(round(x["field"]), x["count"], x["scored"]) for x in tbl])
    check("own reference needs 2 passes", 1 in tbl[0]["own"] and 2 not in tbl[0]["own"], tbl[0]["own"])
    k1 = classify_onset(1, 940.0, tbl, 4300.0)
    check("car with 2 passes uses its own ref", k1 == ("own", True), k1)
    k2 = classify_onset(2, 980.0, tbl, 4300.0)
    check("car with 1 pass falls back to the field ref", k2 == ("field", False), k2)
    k3 = classify_onset(4, 2440.0, tbl, 4300.0)
    check("corner with < 4 clean passes is unscored", k3 == ("NA", None), k3)

    # rear-end vs side-swipe
    check("rear-end: follower 6 m behind", contact_kind(1000.0, 1006.0) == ("rear_end", 0), contact_kind(1000.0, 1006.0))
    check("side-swipe: 1 m apart", contact_kind(1000.0, 1001.0) == ("side", None), contact_kind(1000.0, 1001.0))

    # front-wing increments
    check("front-wing increments", wing_increments([(0, 0, 0), (12, 0, 0), (12, 5, 30), (12, 5, 40)]) == (2, 17),
          wing_increments([(0, 0, 0), (12, 0, 0), (12, 5, 30), (12, 5, 40)]))
    return 1 if failed else 0


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("capture", type=Path, nargs="?")
    ap.add_argument("--out", type=Path)
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        sys.exit(selftest())
    if not a.capture or not a.out:
        ap.error("give a capture and --out, or --selftest")
    rows, summary = analyse(a.capture)
    write(rows, summary, a.out)
    print(json.dumps({k: v for k, v in summary.items() if k not in ("bad_sizes",)}, indent=1))


if __name__ == "__main__":
    main()
