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
   - held_passes_2plus: OVTK made on laps 2+ that the same pair doesn't reverse within 10 s (as #71).
   - longest train: at each lap line of the leader (lap 2+), the longest run of consecutive cars each within 1.0 s of
     the car ahead, in cars. Summary: the per-race median and max.
3. Sudden braking
   - phantom_brakes: a brake onset (brake rising above 0.3) that starts more than 50 m before the car's own clean-lap
     onset for that corner, while a car is within 1.0 s behind it. Corners: the car's onsets on clean laps (2+, no car
     within 2.0 s ahead for the whole lap), clustered within 30 m; a corner's onset is the cluster median. CHOICE: the
     onset belongs to the next corner ahead within 300 m; an onset with no corner within 300 m ahead isn't scored.
     Validate on 2 races by eye before trusting it (the plan).
   - rear_end_as_follower / as_leader: COLL where the two cars' total distance differs by 3 to 12 m (CHOICE: under
     3 m is alongside, so a side-swipe; over 12 m isn't a rear-end). The car with less distance is the follower.
   - front_wing_increments / front_wing_added: CarDamage increases of the front-left or front-right wing.
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
TRAIN_GAP_S = 1.0
CLEAN_GAP_S = 2.0
BRAKE_ON = 0.3
PHANTOM_M = 50.0
CLUSTER_M = 30.0
CORNER_AHEAD_M = 300.0
REAR_MIN_M, REAR_MAX_M = 3.0, 12.0
DT_CAP_S = 0.5
GREEN_FACTOR = 1.10
L_FRONT_MS, L_FRONT_MIN = 6, 7
FINISHED = 3  # FinalClassification result status


# ---------- pure metric functions (the selftest calls these directly) ----------

def held_passes(ovtk: list[tuple[float, int, int]], hold: float = HOLD_S) -> list[dict]:
    """OVTK (time, overtaker, overtaken), with the time until the same pair swaps back and whether it's held."""
    ovtk = sorted(ovtk)
    out = []
    for i, (t, a, b) in enumerate(ovtk):
        back = next((t2 - t for t2, a2, b2 in ovtk[i + 1:] if a2 == b and b2 == a), float("inf"))
        out.append({"t": t, "car": a, "other": b, "back": back, "held": back > hold})
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


def brake_onsets(rows: list[tuple[float, int, float, float]], on: float = BRAKE_ON) -> list[tuple[float, int, float]]:
    """rows = [(t, lap, lap_distance, brake)]; returns [(t, lap, lap_distance)] where brake rises above `on`."""
    out, prev = [], 0.0
    for t, lap, d, b in rows:
        if b > on >= prev:
            out.append((t, lap, d))
        prev = b
    return out


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

    # sudden braking: onsets per car, corners from its clean laps
    btimes = [t for t, _ in s["brake_frames"]]
    dirty_laps: dict[int, set] = defaultdict(set)
    for t, cars in frames:
        for c in range(n):
            g = gap_ahead(cars[c])
            if g is not None and g <= CLEAN_GAP_S:
                dirty_laps[c].add(cars[c][u.L_LAPNUM])
    phantoms = defaultdict(int)
    for c in ai:
        rows = []
        for t, brakes in s["brake_frames"]:
            car = frame_at(t)[c]
            rows.append((t, car[u.L_LAPNUM], car[u.L_LAPDIST], brakes[c]))
        ons = brake_onsets(rows)
        clean = [d for t, lap, d in ons if lap >= 2 and lap not in dirty_laps[c] and lap not in pit_laps[c]]
        cl = corners(clean)
        if not cl:
            continue
        for t, lap, d in ons:
            if lap < 1 or d < 0:
                continue
            cars = frame_at(t)
            pos = cars[c][u.L_POS]
            behind = next((x for x in range(n) if cars[x][u.L_POS] == pos + 1), None)
            gb = gap_ahead(cars[behind]) if behind is not None else None
            if gb is None or gb > TRAIN_GAP_S:
                continue
            if phantom(d, cl, track_len):
                phantoms[c] += 1
    del btimes

    # contacts
    rear_f, rear_l, lap1_coll, coll_n = defaultdict(int), defaultdict(int), 0, defaultdict(int)
    for t, a, b in coll:
        if a >= n or b >= n:
            continue
        coll_n[a] += 1
        coll_n[b] += 1
        cars = frame_at(t)
        if cars[a][u.L_LAPNUM] == 1:
            lap1_coll += 1
        kind, who = contact_kind(cars[a][u.L_TOTDIST], cars[b][u.L_TOTDIST])
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
            "held_passes_2plus": sum(1 for p in made if p["held"] and p["lap"] >= 2),
            "held_suffered_2plus": sum(1 for p in passes if p["other"] == c and p["held"] and p["lap"] >= 2),
            "phantom_brakes": phantoms[c], "rear_end_as_follower": rear_f[c], "rear_end_as_leader": rear_l[c],
            "front_wing_increments": fw_n, "front_wing_added": fw_add, "wing_damage_added": all_add,
            "collisions": coll_n[c], "penalties": pena[c], "dnf": int(bool(dnf)),
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
        "held_passes_2plus": sum(r["held_passes_2plus"] for r in rows),
        "ovtk_raw": len(passes),
        "longest_train_median": statistics.median(trains) if trains else None,
        "longest_train_max": max(trains) if trains else None,
        "phantom_brakes": sum(r["phantom_brakes"] for r in rows),
        "rear_end_contacts": sum(r["rear_end_as_follower"] for r in rows),
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
    check("brake onsets on rising edges", [d for _, _, d in ons] == [940.0, 1000.0], ons)

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
