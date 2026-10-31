#!/usr/bin/env python3
"""Parse a tools/udp_capture.py recording into per-session, per-car CSVs (#4).

Usage:
    python3 tools/udp_parse.py udp.bin --out runs/<id>/udp [--launch-s 3,6]

Writes, per session found in the capture (keyed by sessionUID):
    sessions.csv            uid, format, game version, session type, track id, total laps, packet counts per id
    cars.csv                one row per session and car: participant (name, team, ai), grid, final position,
                            laps, best lap, pit stops, result status, overtakes made / suffered, collisions,
                            penalties, and the launch metrics below
    laps.csv                one row per session, car and completed lap: lap time, position at the line
    events.csv              every event packet: time, code, the fields that code carries

Launch metrics (the behavioural side of F-38's bad-start draw and F-06's reaction time), relative to the
lights-out event (LGOT): for each --launch-s offset t, the car's speed (CarTelemetry), lap distance and position
(LapData) at the first frame at or after LGOT + t.

Layouts: F1 25 spec (EA forum 12187347). Each packet is checked against its expected size; an entry size that
doesn't match is reported in sessions.csv and that packet type is skipped, never silently misread. Only leading
fields that have kept their place since F1 23 are read. LapData's m_gridPosition / m_driverStatus are read in spec
order, and the parser checks the reported swap (grid must be 1..cars for active cars; driver status 0..4) and records
which order fits in sessions.csv (`lapdata_grid_order`).
"""
from __future__ import annotations

import argparse
import csv
import struct
import sys
from collections import defaultdict
from pathlib import Path

HEADER = struct.Struct("<HBBBBBQfIIBB")  # 29 bytes
CARS = 22  # format 2025; per-session layouts below
PACKET_NAMES = {0: "motion", 1: "session", 2: "lap_data", 3: "event", 4: "participants", 5: "car_setups",
                6: "car_telemetry", 7: "car_status", 8: "final_classification", 9: "lobby_info", 10: "car_damage",
                11: "session_history", 12: "tyre_sets", 13: "motion_ex", 14: "time_trial", 15: "lap_positions",
                16: "car_telemetry_2"}
SESSION_TYPES = {0: "unknown", 1: "P1", 2: "P2", 3: "P3", 4: "short_practice", 5: "Q1", 6: "Q2", 7: "Q3",
                 8: "short_quali", 9: "one_shot_quali", 10: "sprint_shootout_1", 11: "sprint_shootout_2",
                 12: "sprint_shootout_3", 13: "short_sprint_shootout", 14: "one_shot_sprint_shootout", 15: "race",
                 16: "race_2", 17: "race_3", 18: "time_trial"}

# LapData car entry: 57 bytes. Offsets of the fields read here.
LAP = struct.Struct("<IIHBHBHBHBfffBBBBBBBBBBBBBBBHHBfB")
assert LAP.size == 57, LAP.size
L_LAST, L_CUR, L_LAPDIST, L_TOTDIST = 0, 1, 10, 11
L_POS, L_LAPNUM, L_PIT, L_NPIT = 13, 14, 15, 16
L_GRID, L_DSTATUS, L_RSTATUS = 24, 25, 26
# CarTelemetry car entry: 60 bytes; speed u16, throttle f32, steer f32, brake f32, clutch u8, gear i8 lead.
TEL_LEAD = struct.Struct("<HfffBb")
TEL_SIZE = 60
# Participants entry: aiControlled, driverId, networkId, teamId, myTeam, raceNumber, nationality, name[32] lead.
PART_LEAD = struct.Struct("<BBBBBBB32s")

# Packet format 2026 (F1 25 2026 Season Pack, EA spec v1.2): every car array holds 24 entries; LapData's 57-byte
# entry is unchanged; ParticipantData widens driverId / networkId / teamId to uint16 (60 bytes); CarTelemetryData
# narrows engineTemperature to uint8 (59 bytes, leading fields unchanged); packet 16 is CarTelemetry2.
LAYOUTS = {
    2025: {"cars": 22, "tel_size": TEL_SIZE, "tel_trailer": 3, "part": PART_LEAD, "part_size": 57,
           "unknown_driver": 255},
    2026: {"cars": 24, "tel_size": 59, "tel_trailer": 3, "part": struct.Struct("<BHHHBBB32s"), "part_size": 60,
           "unknown_driver": 65535},
}


def is_human(car: int, ai: int, driver_id: int, player: int, player2: int, unknown_driver: int) -> bool:
    """A car whose name may be a player's own account name (public repo: never written out). The player's slot can
    report aiControlled = 1 in benchmark and ai_drives_player runs, so the header's player indices count regardless,
    and so does a driverId outside the game's driver list (the player's own slot reports the unknown id). networkId
    can't tell: offline it is just the car index."""
    return car == player or (player2 != 255 and car == player2) or ai == 0 or driver_id == unknown_driver


def records(path: Path):
    data = path.read_bytes()
    i = 0
    rec = struct.Struct("<dH")
    while i + rec.size <= len(data):
        t, n = rec.unpack_from(data, i)
        i += rec.size
        yield t, data[i:i + n]
        i += n


def event_fields(code: str, d: bytes) -> dict:
    """The leading fields of the event codes #4 uses; others are logged by code only."""
    try:
        if code in ("OVTK",):
            return {"vehicle": d[0], "other": d[1]}  # overtaking, being overtaken
        if code in ("COLL",):
            return {"vehicle": d[0], "other": d[1]}
        if code in ("PENA",):
            return {"penalty_type": d[0], "infringement": d[1], "vehicle": d[2], "other": d[3], "time": d[4],
                    "lap": d[5], "places": d[6]}
        if code in ("FTLP",):
            return {"vehicle": d[0], "lap_time": round(struct.unpack_from("<f", d, 1)[0], 3)}
        if code in ("RTMT",):
            return {"vehicle": d[0], "reason": d[1]}
        if code in ("STLG",):
            return {"lights": d[0]}
        if code in ("DTSV", "SGSV", "TMPT", "RCWN"):
            return {"vehicle": d[0]}
        if code in ("SPTP",):
            return {"vehicle": d[0], "speed": round(struct.unpack_from("<f", d, 1)[0], 1)}
    except (IndexError, struct.error):
        return {"parse_error": 1}
    return {}


def new_session():
    return {"format": None, "version": "", "counts": defaultdict(int), "type": None, "track": None, "laps": None,
            "participants": None, "n_active": None, "lap_frames": [], "tel_frames": [], "events": [], "final": None,
            "bad_sizes": {}, "grid_votes": [0, 0]}


def parse(path: Path, launch_offsets: list[float]):
    sessions: dict[int, dict] = {}
    for t, p in records(path):
        if len(p) < HEADER.size:
            continue
        fmt, year, major, minor, pver, pid, uid, stime, frame, oframe, player, player2 = HEADER.unpack_from(p, 0)
        s = sessions.setdefault(uid, new_session())
        s["format"] = fmt
        s["version"] = f"{year}.{major}.{minor}"
        s["player"] = player
        s["counts"][pid] += 1
        lay = LAYOUTS.get(fmt)
        if lay is None:
            s["bad_sizes"]["format"] = fmt
            continue
        n_cars = s["cars"] = lay["cars"]
        body = p[HEADER.size:]
        if pid == 1 and len(body) >= 9:
            s["laps"], s["type"], s["track"] = body[3], body[6], struct.unpack_from("<b", body, 7)[0]
        elif pid == 2:
            need = n_cars * LAP.size + 2
            if len(body) != need:
                s["bad_sizes"]["lap_data"] = len(body)
                continue
            cars = [LAP.unpack_from(body, c * LAP.size) for c in range(n_cars)]
            s["lap_frames"].append((stime, cars))
        elif pid == 3 and len(body) >= 4:
            code = body[:4].decode("ascii", "replace")
            s["events"].append((stime, t, code, event_fields(code, body[4:])))
        elif pid == 4 and s["participants"] is None and len(body) >= 1:
            size = lay["part_size"]
            if len(body) != 1 + n_cars * size:
                s["bad_sizes"]["participants"] = len(body)
                continue
            s["n_active"] = body[0]
            parts = []
            for c in range(n_cars):
                ai, drv, net, team, myteam, num, nat, name = lay["part"].unpack_from(body, 1 + c * size)
                human = is_human(c, ai, drv, player, player2, lay["unknown_driver"])
                parts.append({"ai": ai, "driver_id": drv, "team_id": team, "race_number": num,
                              "name": "player" if human else name.split(b"\0", 1)[0].decode("utf-8", "replace")})
            s["participants"] = parts
        elif pid == 6:
            tel = lay["tel_size"]
            if len(body) != n_cars * tel + lay["tel_trailer"]:
                s["bad_sizes"]["car_telemetry"] = len(body)
                continue
            s["tel_frames"].append((stime, [TEL_LEAD.unpack_from(body, c * tel)[0] for c in range(n_cars)]))
        elif pid == 8 and len(body) >= 1:
            size = (len(body) - 1) // n_cars
            if size not in (45, 46):
                s["bad_sizes"]["final_classification"] = len(body)
                continue
            best_off = 7 if size == 46 else 6
            fin = []
            for c in range(n_cars):
                o = 1 + c * size
                fin.append({"position": body[o], "laps": body[o + 1], "grid": body[o + 2], "points": body[o + 3],
                            "pit_stops": body[o + 4], "result_status": body[o + 5],
                            "best_lap_ms": struct.unpack_from("<I", body, o + best_off)[0],
                            "total_time_s": round(struct.unpack_from("<d", body, o + best_off + 4)[0], 3)})
            s["final"] = fin
    for s in sessions.values():
        check_grid_order(s)
        s["launch"] = launch_metrics(s, launch_offsets)
    return sessions


def check_grid_order(s: dict) -> None:
    """Votes on which of the two adjacent LapData bytes is the grid position (spec order vs the reported swap)."""
    cars_max = s.get("cars", CARS)
    n = s["n_active"] or cars_max
    for _, cars in s["lap_frames"][:50]:
        for c in cars[:n]:
            g, d = c[L_GRID], c[L_DSTATUS]
            if 1 <= g <= cars_max and d <= 4:
                s["grid_votes"][0] += 1
            if 1 <= d <= cars_max and g <= 4:
                s["grid_votes"][1] += 1
    a, b = s["grid_votes"]
    s["grid_order"] = "spec" if a >= b else "swapped"


def grid_of(s: dict, car: tuple) -> int:
    return car[L_GRID] if s["grid_order"] == "spec" else car[L_DSTATUS]


def at_or_after(frames: list, t: float):
    for st, cars in frames:
        if st >= t:
            return st, cars
    return None, None


def launch_metrics(s: dict, offsets: list[float]) -> dict:
    lgot = next((st for st, _, code, _ in s["events"] if code == "LGOT"), None)
    out = {"lights_out": lgot}
    if lgot is None:
        return out
    for off in offsets:
        _, tel = at_or_after(s["tel_frames"], lgot + off)
        _, lap = at_or_after(s["lap_frames"], lgot + off)
        out[off] = {"speed": tel, "lap": lap}
    return out


def write(sessions: dict, out: Path, offsets: list[float]) -> None:
    out.mkdir(parents=True, exist_ok=True)
    with (out / "sessions.csv").open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["session_uid", "format", "game_version", "session_type", "track_id", "total_laps", "n_active",
                    "player_car", "lights_out_s", "lapdata_grid_order", "bad_sizes", "packets"])
        for uid, s in sessions.items():
            w.writerow([uid, s["format"], s["version"], SESSION_TYPES.get(s["type"], s["type"]), s["track"],
                        s["laps"], s["n_active"], s.get("player"), s["launch"].get("lights_out"), s["grid_order"],
                        ";".join(f"{k}={v}" for k, v in s["bad_sizes"].items()),
                        ";".join(f"{PACKET_NAMES.get(k, k)}={v}" for k, v in sorted(s["counts"].items()))])
    with (out / "events.csv").open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["session_uid", "session_time", "wall_time", "code", "fields"])
        for uid, s in sessions.items():
            for st, wt, code, fields in s["events"]:
                w.writerow([uid, round(st, 3), round(wt, 3), code, ";".join(f"{k}={v}" for k, v in fields.items())])
    with (out / "laps.csv").open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["session_uid", "car", "lap", "lap_time_ms", "position_at_line"])
        for uid, s in sessions.items():
            last = {}
            for _, cars in s["lap_frames"]:
                for c, car in enumerate(cars):
                    n = car[L_LAPNUM]
                    if c in last and n == last[c] + 1 and car[L_LAST] > 0:
                        w.writerow([uid, c, last[c], car[L_LAST], car[L_POS]])
                    last[c] = n
    head = ["session_uid", "car", "name", "team_id", "ai", "race_number", "grid", "final_position", "laps",
            "best_lap_ms", "pit_stops", "result_status", "overtakes_made", "overtakes_suffered", "collisions",
            "penalties"]
    for off in offsets:
        head += [f"speed_kph_at_{off:g}s", f"lap_distance_m_at_{off:g}s", f"position_at_{off:g}s"]
    with (out / "cars.csv").open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(head)
        for uid, s in sessions.items():
            cars_max = s.get("cars", CARS)
            n = s["n_active"] or cars_max
            ev = defaultdict(lambda: defaultdict(int))
            for _, _, code, fields in s["events"]:
                if code == "OVTK":
                    ev[fields.get("vehicle")]["made"] += 1
                    ev[fields.get("other")]["suffered"] += 1
                elif code == "COLL":
                    ev[fields.get("vehicle")]["coll"] += 1
                    ev[fields.get("other")]["coll"] += 1
                elif code == "PENA":
                    ev[fields.get("vehicle")]["pen"] += 1
            first = s["lap_frames"][0][1] if s["lap_frames"] else None
            for c in range(n):
                part = (s["participants"] or [{}] * cars_max)[c]
                fin = (s["final"] or [None] * cars_max)[c]
                row = [uid, c, part.get("name", "NA"), part.get("team_id", "NA"), part.get("ai", "NA"),
                       part.get("race_number", "NA"),
                       fin["grid"] if fin else (grid_of(s, first[c]) if first else "NA"),
                       fin["position"] if fin else "NA", fin["laps"] if fin else "NA",
                       fin["best_lap_ms"] if fin else "NA", fin["pit_stops"] if fin else "NA",
                       fin["result_status"] if fin else "NA",
                       ev[c]["made"], ev[c]["suffered"], ev[c]["coll"], ev[c]["pen"]]
                for off in offsets:
                    m = s["launch"].get(off)
                    if not m or m["speed"] is None:
                        row += ["NA", "NA", "NA"]
                        continue
                    lap = m["lap"][c] if m["lap"] else None
                    row += [m["speed"][c], round(lap[L_LAPDIST], 1) if lap else "NA", lap[L_POS] if lap else "NA"]
                w.writerow(row)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("capture", type=Path)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--launch-s", default="3,6", help="comma-separated offsets after lights out, seconds")
    args = ap.parse_args()
    offsets = [float(x) for x in args.launch_s.split(",") if x.strip()]
    sessions = parse(args.capture, offsets)
    write(sessions, args.out, offsets)
    for uid, s in sessions.items():
        print(f"session {uid}: format {s['format']} {SESSION_TYPES.get(s['type'], s['type'])}, "
              f"{sum(s['counts'].values())} packets, lap frames {len(s['lap_frames'])}, "
              f"events {len(s['events'])}, bad sizes {s['bad_sizes'] or 'none'}")
    if not sessions:
        print("no sessions in the capture", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
