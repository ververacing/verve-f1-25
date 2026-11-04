"""Check one direct-start race against B-0012's pre-registered criterion (#57).

Usage:
    python -I tools/b0012_check.py [--expect-overwritten N] runs/<id> [more runs]

Reads <run>/raw/loader.log and <run>/udp/ (tools/sandbox_run.ps1 -Session -Udp). Each run is PASS, FAIL or INVALID.
Exit 0 if every run passes, 1 if any fails, 3 if none fails but some are invalid and must be rerun.

PASS, as ruled on #57 before any data:
- the first 20 reaction lines after the first lights-out cover 20 distinct vehicles;
- exactly one car at 0.650 in each of the 9 tagged teams, and no 0.650 car anywhere else;
- the UDP Participants join maps each 0.650 vehicle id to the expected driver.
Aston (player Stroll, untagged Alonso) is excluded. Later re-rolls are reported, as the log's rate limit makes them
incomplete, and don't count toward the criterion.

INVALID (supervisor, on #68): a run with the wrong game-database count, the wrong seat or a pinned player car is
discarded and rerun, not scored, even if the tags read right.
"""
from __future__ import annotations

import csv
import re
import sys
from pathlib import Path

TAGGED = {"RUSSELL", "LECLERC", "VERSTAPPEN", "SAINZ", "GASLY", "LAWSON", "OCON", "PIASTRI", "BORTOLETO"}
EXPECT_OVERWRITTEN = 52 + 36  # stock baseline on 1.8.4, plus 9 drivers x 4 bounds
PINNED = 0.65
TOLERANCE = 0.0005
REACTION = re.compile(r"RaceStarts: Reaction Time for driver with vehicle id (\d+): ([\d.]+)")
GAMEDB = re.compile(r"gamedb: (\d+) overwritten, (\d+) created")
LAPNAME = re.compile(r"v\((\d+), [^)]*?([A-Z][A-Z'\- ]+)\)")


def race_uid(udp: Path) -> str:
    with open(udp / "sessions.csv", newline="", encoding="utf-8") as f:
        rows = [r for r in csv.DictReader(f) if r["session_type"] == "race"]
    if len(rows) != 1:
        raise SystemExit(f"{udp}: expected one race session, found {len(rows)}")
    return rows[0]["session_uid"]


def participants(udp: Path) -> tuple[dict[int, str], int]:
    uid = race_uid(udp)
    with open(udp / "sessions.csv", newline="", encoding="utf-8") as f:
        player = next(int(r["player_car"]) for r in csv.DictReader(f) if r["session_uid"] == uid)
    with open(udp / "cars.csv", newline="", encoding="utf-8") as f:
        names = {int(r["car"]): r["name"].upper() for r in csv.DictReader(f) if r["session_uid"] == uid}
    return names, player


def is_pinned(value: float) -> bool:
    return abs(value - PINNED) < TOLERANCE


def check(run: Path, expect_overwritten: int) -> str:
    print(f"=== {run.name}")
    log = (run / "raw" / "loader.log").read_text(encoding="utf-8", errors="replace").splitlines()
    draws = [(int(m[1]), float(m[2])) for m in map(REACTION.search, log) if m]
    try:
        names, player = participants(run / "udp")
    except (OSError, SystemExit, StopIteration) as e:
        # the run never produced a usable race session: nothing to score, and the rest of a batch must still be read
        print(f"  INVALID: no usable UDP race session ({e})")
        print("  RESULT: INVALID, discard and rerun")
        return "invalid"
    problems = []

    first = draws[:20]
    vehicles = [v for v, _ in first]
    if len(first) != 20 or len(set(vehicles)) != 20:
        problems.append(f"first block: {len(first)} lines, {len(set(vehicles))} distinct vehicles (want 20 and 20)")
    if len(names) != 20:
        problems.append(f"UDP Participants names {len(names)} cars (want 20)")

    pinned = {v for v, r in first if is_pinned(r)}
    expected = {v for v, n in names.items() if n in TAGGED}
    missing_names = TAGGED - set(names.values())
    if missing_names:
        problems.append(f"tagged drivers not in UDP: {sorted(missing_names)}")
    for v in sorted(expected - pinned):
        got = next((r for x, r in first if x == v), None)
        problems.append(f"tagged {names[v]} (vehicle {v}) reads {got}, not 0.650")
    for v in sorted(pinned - expected):
        problems.append(f"untagged {names.get(v, '?')} (vehicle {v}) reads 0.650")

    print(f"  first block: {len(first)} lines, {len(set(vehicles))} vehicles, {len(pinned)} at 0.650")
    for v, r in sorted(first):
        mark = "TAG " if names.get(v) in TAGGED else "    "
        print(f"    {mark}{v:2d} {names.get(v, '?'):<12} {r:.6f}")

    # reported, not counted: the log's rate limit cuts these off
    tagged_all = [(names[v], r) for v, r in draws if names.get(v) in TAGGED]
    stray = sum(1 for v, r in draws if names.get(v) not in TAGGED and is_pinned(r))
    off = [(n, r) for n, r in tagged_all if not is_pinned(r)]
    print(f"  all logged re-rolls: {len(draws)} lines. Tagged cars: {len(tagged_all)} lines, {len(off)} off 0.650. "
          f"Untagged lines at 0.650: {stray}")
    if off:
        print(f"    off 0.650: {off[:10]}")

    # validity of the run: breaking any of these discards it, whatever the tags read
    invalid = []
    counts = [(int(m[1]), int(m[2])) for m in map(GAMEDB.search, log) if m]
    if not counts:
        invalid.append("no gamedb count in the log")
    elif counts[0][0] != expect_overwritten:
        invalid.append(f"gamedb {counts[0][0]} overwritten, expected {expect_overwritten}")
    seat = next((m[0] for m in (re.search(r"the player drives for \S+ as \S+", l) for l in log) if m), "no seat line")
    print(f"  gamedb: {counts[0] if counts else 'none'}; {seat}; UDP player car {player} ({names.get(player, '?')})")
    if "forceindia as lance_stroll" not in seat:
        invalid.append(f"player is not Stroll: {seat}")
    if player in pinned:
        invalid.append(f"the player's car {player} reads 0.650")

    if invalid:
        for p in invalid:
            print(f"  INVALID: {p}")
        for p in problems:
            print(f"  (not scored): {p}")
        print("  RESULT: INVALID, discard and rerun")
        return "invalid"
    for p in problems:
        print(f"  FAIL: {p}")
    print("  RESULT: PASS" if not problems else f"  RESULT: FAIL ({len(problems)})")
    return "fail" if problems else "pass"


def main() -> int:
    args = sys.argv[1:]
    expect = EXPECT_OVERWRITTEN
    if args[:1] == ["--expect-overwritten"]:
        expect = int(args[1])
        args = args[2:]
    runs = [Path(a) for a in args]
    if not runs:
        print(__doc__)
        return 2
    results = [check(r, expect) for r in runs]
    print(f"\n{results.count('pass')} pass, {results.count('fail')} fail, {results.count('invalid')} invalid, "
          f"of {len(results)} run(s)")
    if "fail" in results:
        return 1
    return 3 if "invalid" in results else 0


if __name__ == "__main__":
    sys.exit(main())
