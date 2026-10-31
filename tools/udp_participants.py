#!/usr/bin/env python3
"""Per session in a tools/udp_capture.py recording: the player car index and each car's participant entry.

Usage:
    python3 tools/udp_participants.py udp.bin [--csv participants.csv]

Assumes the F1 25 (2025-format) layout: a 29-byte header (packetFormat u16, gameYear, major, minor, packetVersion,
packetId u8, sessionUID u64, sessionTime f32, frame u32, overallFrame u32, playerCarIndex u8, secondaryPlayer u8),
and the Participants packet (id 4) = numActiveCars u8 + 22 entries of aiControlled, driverId, networkId, teamId,
myTeam, raceNumber, nationality, name[32], ... The entry size is taken from the packet length, so a format with a
longer entry still parses as long as those leading fields stay put. Event packets (id 3) are scanned for the
lights-out code LGOT.
"""
from __future__ import annotations

import argparse
import csv
import struct
import sys
from collections import OrderedDict
from pathlib import Path

HEADER = struct.Struct("<HBBBBBQfIIBB")  # 29 bytes
assert HEADER.size == 29
CARS = 22


def records(path: Path):
    data = path.read_bytes()
    i = 0
    rec = struct.Struct("<dH")
    while i + rec.size <= len(data):
        t, n = rec.unpack_from(data, i)
        i += rec.size
        yield t, data[i:i + n]
        i += n


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("capture", type=Path)
    ap.add_argument("--csv", type=Path)
    args = ap.parse_args()

    sessions: "OrderedDict[int, dict]" = OrderedDict()
    for t, p in records(args.capture):
        if len(p) < HEADER.size:
            continue
        fmt, year, major, minor, pver, pid, uid, stime, frame, oframe, player, player2 = HEADER.unpack_from(p, 0)
        s = sessions.setdefault(uid, {"format": fmt, "year": year, "first_t": t, "packets": 0, "players": set(),
                                      "ids": {}, "participants": None, "lights_out": None})
        s["packets"] += 1
        s["players"].add(player)
        s["ids"][pid] = s["ids"].get(pid, 0) + 1
        if pid == 4 and s["participants"] is None:
            body = p[HEADER.size:]
            n_active = body[0]
            size = (len(body) - 1) // CARS
            cars = []
            for c in range(CARS):
                e = body[1 + c * size: 1 + (c + 1) * size]
                if len(e) < 39:
                    break
                ai, driver_id, network_id, team_id, my_team, number, nationality = e[:7]
                name = e[7:39].split(b"\0", 1)[0].decode("utf-8", "replace")
                cars.append({"car_index": c, "ai": ai, "driver_id": driver_id, "team_id": team_id,
                             "race_number": number, "name": name})
            s["participants"] = {"active": n_active, "entry_size": size, "cars": cars}
        if pid == 3 and s["lights_out"] is None and p[HEADER.size:HEADER.size + 4] == b"LGOT":
            s["lights_out"] = stime

    rows = []
    for uid, s in sessions.items():
        print(f"session {uid:#018x}: format {s['format']} year {s['year']}, {s['packets']} packets, "
              f"player car index {sorted(s['players'])}, lights out at session time {s['lights_out']}, "
              f"packet ids {dict(sorted(s['ids'].items()))}")
        part = s["participants"]
        if not part:
            print("  no Participants packet")
            continue
        print(f"  participants: {part['active']} active, entry size {part['entry_size']} bytes")
        for c in part["cars"][:part["active"]]:
            print(f"  car {c['car_index']:2d}: ai={c['ai']} driver_id={c['driver_id']:3d} team_id={c['team_id']:3d} "
                  f"#{c['race_number']:<3d} {c['name']}")
            rows.append({"session": f"{uid:#018x}", "player_car_index": min(s["players"]), **c})
    if args.csv and rows:
        with args.csv.open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()), lineterminator="\n")
            w.writeheader()
            w.writerows(rows)


if __name__ == "__main__":
    sys.exit(main())
