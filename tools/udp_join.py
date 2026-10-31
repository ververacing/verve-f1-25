"""Join one race start's RaceStarts draws (tools/racestarts_summary.ps1) with its UDP cars (tools/udp_parse.py) (#4).

Usage:
    python3 tools/udp_join.py --udp runs/<id>/udp --starts runs/<id>/summary.csv --start 1 --out runs/<id>/joined_1.csv
        [--session-uid <uid>]

RaceStarts names cars by vehicle id, UDP by car index. The join assumes vehicle id = car index and checks it: both
sides carry a team id in the same numbering (the session trace's `teams ...` list and the Participants packet's
teamId; e.g. 1 = Ferrari in both), so every row reports whether the two agree. Any mismatch is printed and makes
the exit code 1; don't use the join until it is 0.

The UDP session is the only `race` session in sessions.csv, or the one given with --session-uid. Each row gets
b = 1 - race_start_performance/100 (F-38) next to the UDP grid, launch metrics and result.
"""
from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--udp", type=Path, required=True, help="folder with sessions.csv and cars.csv")
    ap.add_argument("--starts", type=Path, required=True, help="summary.csv from tools/racestarts_summary.ps1")
    ap.add_argument("--start", type=int, required=True, help="start number in summary.csv")
    ap.add_argument("--session-uid", default=None)
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args()

    sessions = list(csv.DictReader((a.udp / "sessions.csv").open()))
    if a.session_uid is None:
        races = [s for s in sessions if s["session_type"] == "race"]
        if len(races) != 1:
            print(f"need exactly one race session, found {len(races)}; pass --session-uid", file=sys.stderr)
            return 2
        a.session_uid = races[0]["session_uid"]
    cars = {int(c["car"]): c for c in csv.DictReader((a.udp / "cars.csv").open()) if c["session_uid"] == a.session_uid}
    draws = [r for r in csv.DictReader(a.starts.open()) if int(r["start"]) == a.start]
    if not draws or not cars:
        print(f"no rows: {len(draws)} RaceStarts draws for start {a.start}, {len(cars)} UDP cars", file=sys.stderr)
        return 2

    udp_cols = [k for k in next(iter(cars.values())) if k not in ("session_uid", "car", "team_id")]
    head = ["start", "vehicle", "team_id_trace", "team_id_udp", "team_match", "reaction_time",
            "race_start_performance", "b"] + udp_cols
    bad = []
    a.out.parent.mkdir(parents=True, exist_ok=True)
    with a.out.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(head)
        for r in sorted(draws, key=lambda r: int(r["vehicle"])):
            v = int(r["vehicle"])
            c = cars.get(v, {})
            match = c.get("team_id") == r["team_id"]
            if not match:
                bad.append((v, r["team_id"], c.get("team_id", "missing")))
            b = 1 - float(r["race_start_performance"]) / 100
            w.writerow([a.start, v, r["team_id"], c.get("team_id", "NA"), match, r["reaction_time"],
                        r["race_start_performance"], round(b, 6)] + [c.get(k, "NA") for k in udp_cols])
    print(f"start {a.start}, session {a.session_uid}: {len(draws)} cars joined -> {a.out}")
    for v, t_trace, t_udp in bad:
        print(f"  team mismatch: vehicle {v} trace team {t_trace}, UDP team {t_udp}")
    print("team ids agree for every car" if not bad else f"{len(bad)} mismatches: vehicle id != car index here")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
