#!/usr/bin/env python3
"""Validity and measures for the #131 workaround race: AI-only, the player car parked last (Starting Grid Custom).

Usage:
    python -I tools/b0131_check.py runs/<batch>/race_<n>     # prints the report and writes <race>/b0131.txt
    python -I tools/b0131_check.py --selftest

Pre-registered on #131 (supervisor, 2026-11-16), with the gamedb addendum (56, Starting Grid's database part):
  Validity: a FinalClassification present (cars.csv result_status set); the race leader (final_position 1) classified
  as finished (status 3); >= 18 AI cars classified (status 3); track id 9; difficulty 100; weather.txt LOCKED (#118 as
  amended); gamedb 56 overwritten; no PAUSE cut. The player car is excluded from every measure.
  Measures:
  - scar: SCAR events (safety car / VSC) in the race session.
  - player_removed_s: the session time of the player's RTMT event (and its first PENA).
  - lap1_disturbance: AI cars whose lap-1 time is > 3 s off the AI field median (laps.csv). "not measurable" when
    laps.csv has no lap-1 rows.
  - grid order: the AI cars by grid slot (cars.csv), for the across-race comparison.
  Added (not in #131; found in the proof race): simulated_from_s. If the UDP race stream has a gap where session time
  jumps far more than wall time (ratio > 2 over > 30 s of session time), the race after that point was simulated, not
  raced live, and nothing after it is measurable.
  Pass: no SCAR, no lap-1 disturbance, a valid race. A simulated remainder is reported beside the verdict.
Exit 0 PASS, 1 FAIL, 3 INVALID.
"""
from __future__ import annotations

import csv
import re
import statistics
import sys
from pathlib import Path

EXPECT_GAMEDB = 56
_POINTS_OVERRIDE: list | None = None   # the selftest's synthetic packet stream
FIXTURE_FAIL = Path(__file__).parent.parent / "runs" / "2026-11-16-pilot-dsq" / "race_1"   # read-only known FAIL
GAMEDB = re.compile(r"gamedb: (\d+) overwritten")


def read_csv(p: Path) -> list[dict]:
    if not p.exists():
        return []
    with p.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def race_session(sessions: list[dict]) -> dict | None:
    r = [s for s in sessions if s.get("session_type") == "race"]
    return r[-1] if r else None


def first_jump(points) -> float | None:
    """points: (wall time, session time) in wall order. The session time where session time jumps > 30 s while wall
    time moves less than half of that (the race was simulated from there)."""
    for (w0, s0), (w1, s1) in zip(points, points[1:]):
        if s1 - s0 > 30 and (s1 - s0) > 2 * max(w1 - w0, 0.001):
            return s0
    return None


def race_points(run: Path, uid: str) -> list[tuple[float, float, int]] | None:
    """(wall time, session time, packet id) of every packet of the race session in raw/udp.bin, or None without it."""
    if _POINTS_OVERRIDE is not None:   # selftest only
        return _POINTS_OVERRIDE
    raw = run / "raw" / "udp.bin"
    if not raw.exists():
        return None
    sys.path.insert(0, str(Path(__file__).parent))
    import udp_parse as u  # noqa: E402
    pts = []
    for wall, pkt in u.records(raw):
        if len(pkt) >= u.HEADER.size:
            h = u.HEADER.unpack_from(pkt, 0)
            if str(h[6]) == uid:
                pts.append((wall, h[7], h[5]))
    return pts


def live_check(run: Path, uid: str, events: list[dict], total_laps: int, ai_cars: list[str]) -> list[str]:
    """The supervisor's live-race check (#131 ruling 2): from lights out to the first FinalClassification packet, session
    time advances with wall time (ratio 0.9-1.1) and no gap between race packets is over 5 s; and laps.csv has laps
    1..total_laps-1 for every AI car (the last lap's time is in the classification, not in laps.csv)."""
    fails = []
    pts = race_points(run, uid)
    if not pts:
        fails.append("live: no raw/udp.bin race packets to check")
    else:
        lgot = [float(e["session_time"]) for e in events if e["code"] == "LGOT"]
        t0 = lgot[0] if lgot else 0.0
        # session time sits at lights-out (frozen) while the grid waits; start at the last packet before it moves on
        moving = next((i for i, p in enumerate(pts) if p[1] > t0 + 0.5), None)
        start = max(moving - 1, 0) if moving is not None else None
        end = next((i for i, p in enumerate(pts) if p[2] == 8), None)   # packet id 8 = FinalClassification
        if start is None or end is None or end <= start:
            fails.append("live: no lights-out-to-classification window")
        else:
            win = pts[start:end + 1]
            dw, ds = win[-1][0] - win[0][0], win[-1][1] - win[0][1]
            ratio = ds / dw if dw > 0 else float("inf")
            if not 0.9 <= ratio <= 1.1:
                fails.append(f"live: session/wall time ratio {ratio:.2f} (lights out to classification), outside 0.9-1.1")
            gaps = [(a[1], b[0] - a[0]) for a, b in zip(win, win[1:]) if b[0] - a[0] > 5]
            if gaps:
                fails.append(f"live: {len(gaps)} telemetry gap(s) > 5 s, first at session time {gaps[0][0]:.1f} s ({gaps[0][1]:.1f} s)")
    laps = {(r["car"], r["lap"]) for r in read_csv(run / "udp" / "laps.csv") if r["session_uid"] == uid}
    missing = [c for c in ai_cars if any((c, str(n)) not in laps for n in range(1, total_laps))]
    if missing:
        fails.append(f"live: laps.csv incomplete for {len(missing)} AI car(s) (laps 1-{total_laps - 1})")
    return fails


def simulated_from(run: Path, events: list[dict], uid: str) -> float | None:
    """From the raw capture's packet headers when raw/udp.bin is there, else from the race's events."""
    pts = race_points(run, uid)
    if pts:
        return first_jump([(w, st) for w, st, _ in pts])
    return first_jump(sorted((float(e["wall_time"]), float(e["session_time"])) for e in events if e["session_uid"] == uid))


def check(run: Path) -> tuple[list[str], dict]:
    invalid: list[str] = []
    m: dict = {}
    s = race_session(read_csv(run / "udp" / "sessions.csv"))
    if not s:
        return ["no race session in udp/sessions.csv"], m
    uid, player = s["session_uid"], s.get("player_car", "")
    if s.get("track_id") != "9":
        invalid.append(f"track_id {s.get('track_id')}, expected 9")
    if s.get("ai_difficulty") != "100":
        invalid.append(f"difficulty {s.get('ai_difficulty')}, expected 100")
    cars = [c for c in read_csv(run / "udp" / "cars.csv") if c["session_uid"] == uid]
    ai = [c for c in cars if c["car"] != player and c.get("ai") == "1"]
    if not any(c.get("result_status") not in ("", "NA") for c in cars):
        invalid.append("no FinalClassification")
    leader = [c for c in cars if c.get("final_position") == "1"]
    if not leader or leader[0].get("result_status") != "3":
        invalid.append("leader not classified as finished")
    finished = [c for c in ai if c.get("result_status") == "3"]
    if len(finished) < 18:
        invalid.append(f"{len(finished)} AI cars classified, need >= 18")
    wx = run / "weather.txt"
    if not wx.exists() or not wx.read_text(encoding="utf-8").startswith("weather: LOCKED"):
        invalid.append("weather: " + (wx.read_text(encoding="utf-8").splitlines()[0] if wx.exists() else "no weather.txt"))
    ll = run / "raw" / "loader.log"
    db = GAMEDB.search(ll.read_text(encoding="utf-8", errors="replace")) if ll.exists() else None
    if not db or int(db[1]) != EXPECT_GAMEDB:
        invalid.append(f"gamedb {db[1] if db else 'none'} overwritten, expected {EXPECT_GAMEDB}")
    if (run / "pause_cut.txt").exists():
        invalid.append("pause cut")

    events = [e for e in read_csv(run / "udp" / "events.csv") if e["session_uid"] == uid]
    m["scar"] = sum(1 for e in events if e["code"] == "SCAR")
    pv = f"vehicle={player}"
    rt = [float(e["session_time"]) for e in events if e["code"] == "RTMT" and pv in e["fields"].split(";")]
    pe = [float(e["session_time"]) for e in events if e["code"] == "PENA" and pv in e["fields"].split(";")]
    m["player_removed_s"] = rt[0] if rt else None
    m["player_first_penalty_s"] = pe[0] if pe else None
    sim = simulated_from(run, read_csv(run / "udp" / "events.csv"), uid)
    m["simulated_from_s"] = round(sim, 1) if sim is not None else None
    total = int(s["total_laps"]) if s.get("total_laps", "").isdigit() else 5
    m["live_fail"] = live_check(run, uid, events, total, [c["car"] for c in ai])
    laps = [r for r in read_csv(run / "udp" / "laps.csv") if r["session_uid"] == uid and r["lap"] == "1" and r["car"] != player]
    if laps:
        t = {r["car"]: int(r["lap_time_ms"]) / 1000 for r in laps}
        med = statistics.median(t.values())
        m["lap1_median_s"] = round(med, 3)
        m["lap1_disturbed"] = sorted(c for c, v in t.items() if v - med > 3)
    else:
        m["lap1_disturbed"] = "not measurable (no lap-1 rows in laps.csv)"
    grid = sorted(((int(c["grid"]), c["name"]) for c in cars if c.get("grid", "NA") not in ("NA", "")), key=lambda x: x[0])
    m["grid_order"] = [f"{g}:{n}" for g, n in grid]
    return invalid, m


def verdict(invalid: list[str], m: dict) -> str:
    if invalid:
        return "INVALID"
    if m.get("live_fail"):          # not a live race: FAIL whatever else passes (#131 ruling 2)
        return "FAIL"
    disturbed = m.get("lap1_disturbed")
    if m.get("scar", 0) == 0 and isinstance(disturbed, list) and not disturbed:
        return "PASS"
    return "FAIL"


def selftest() -> int:
    import tempfile
    global _POINTS_OVERRIDE
    ok = True
    # a live race: 60 Hz packets, session time 1:1 with wall time from lights out (0 s) to 450 s, then the classification
    live = [(1000.0 + t / 60, t / 60, 2) for t in range(0, 450 * 60, 6)] + [(1450.5, 450.5, 8)]
    with tempfile.TemporaryDirectory() as d:
        run = Path(d)
        (run / "udp").mkdir()
        (run / "raw").mkdir()

        def w(name, header, rows):
            with (run / "udp" / name).open("w", newline="", encoding="utf-8") as f:
                cw = csv.writer(f)
                cw.writerow(header)
                cw.writerows(rows)
        w("sessions.csv", ["session_uid", "session_type", "track_id", "total_laps", "player_car", "ai_difficulty"],
          [["7", "race", "9", "5", "19", "100"]])
        cars = [["7", str(c), f"D{c}", "1", str(c + 1), str(c + 1), "3"] for c in range(19)] + [["7", "19", "player", "0", "20", "20", "4"]]
        w("cars.csv", ["session_uid", "car", "name", "ai", "grid", "final_position", "result_status"], cars)
        w("events.csv", ["session_uid", "session_time", "wall_time", "code", "fields"],
          [["7", "0.0", "1000.0", "LGOT", ""], ["7", "20.0", "1020.0", "PENA", "penalty_type=6;vehicle=19"],
           ["7", "30.0", "1030.0", "RTMT", "vehicle=19;reason=6"], ["7", "450.0", "1450.0", "CHQF", ""]])

        def laps(slow_car=None):
            w("laps.csv", ["session_uid", "car", "lap", "lap_time_ms", "position_at_line"],
              [["7", str(c), str(n), str(90000 + (4000 if (c == slow_car and n == 1) else 0)), "1"]
               for c in range(19) for n in range(1, 5)])
        laps()
        (run / "weather.txt").write_text("weather: LOCKED\n", encoding="utf-8")
        (run / "raw" / "loader.log").write_text("[assets] gamedb: 56 overwritten, 322 created\n", encoding="utf-8")
        _POINTS_OVERRIDE = live
        inv, m = check(run)
        ok &= verdict(inv, m) == "PASS" and m["player_removed_s"] == 30.0 and m["simulated_from_s"] is None
        ok &= len(m["grid_order"]) == 20 and m["grid_order"][-1] == "20:player" and not m["live_fail"]
        # a back-marker 4 s slow on lap 1 -> FAIL
        laps(slow_car=18)
        inv, m = check(run)
        ok &= verdict(inv, m) == "FAIL" and m["lap1_disturbed"] == ["18"]
        laps()
        # a simulated remainder (session 31 -> 450 s in 90 wall-s) -> FAIL on the live check
        _POINTS_OVERRIDE = [p for p in live if p[1] <= 31] + [(1121.0, 450.5, 11), (1121.5, 450.5, 8)]
        inv, m = check(run)
        ok &= verdict(inv, m) == "FAIL" and any("ratio" in f for f in m["live_fail"]) and m["simulated_from_s"] is not None
        # a 6 s telemetry gap in an otherwise live race -> FAIL
        _POINTS_OVERRIDE = [p for p in live if not 100 < p[1] < 106]
        inv, m = check(run)
        ok &= verdict(inv, m) == "FAIL" and any("gap" in f for f in m["live_fail"])
        _POINTS_OVERRIDE = live
        # no lap rows -> laps.csv incomplete and lap 1 not measurable -> FAIL
        w("laps.csv", ["session_uid", "car", "lap", "lap_time_ms", "position_at_line"], [])
        inv, m = check(run)
        ok &= verdict(inv, m) == "FAIL" and str(m["lap1_disturbed"]).startswith("not measurable")
        ok &= any("incomplete" in f for f in m["live_fail"])
        laps()
        # wrong gamedb -> INVALID
        (run / "raw" / "loader.log").write_text("[assets] gamedb: 52 overwritten\n", encoding="utf-8")
        inv, m = check(run)
        ok &= verdict(inv, m) == "INVALID" and any("gamedb" in i for i in inv)
    _POINTS_OVERRIDE = None
    # the known-FAIL fixture: the pilot DSQ race's real capture (read-only), simulated from 31 s
    fixture = "skipped (not on this PC)"
    if (FIXTURE_FAIL / "raw" / "udp.bin").exists():
        s = race_session(read_csv(FIXTURE_FAIL / "udp" / "sessions.csv"))
        ev = [e for e in read_csv(FIXTURE_FAIL / "udp" / "events.csv") if e["session_uid"] == s["session_uid"]]
        ai = [c["car"] for c in read_csv(FIXTURE_FAIL / "udp" / "cars.csv") if c["session_uid"] == s["session_uid"] and c.get("ai") == "1"]
        lf = live_check(FIXTURE_FAIL, s["session_uid"], ev, int(s["total_laps"]), ai)
        good = any("ratio" in f for f in lf) and any("incomplete" in f for f in lf)
        ok &= good
        fixture = ("FAIL as expected: " if good else "NOT FAILED: ") + " | ".join(lf)
    print("selftest", "ok" if ok else "FAILED", "| fixture:", fixture)
    return 0 if ok else 1


def main() -> int:
    args = sys.argv[1:]
    if "--selftest" in args:
        return selftest()
    if len(args) != 1:
        print(__doc__)
        return 3
    run = Path(args[0])
    invalid, m = check(run)
    v = verdict(invalid, m)
    lines = [f"#131 check: {v}"] + [f"  INVALID: {i}" for i in invalid]
    for f in m.get("live_fail", []):
        lines.append(f"  FAIL {f}")
    for k in ("scar", "player_first_penalty_s", "player_removed_s", "simulated_from_s", "lap1_median_s", "lap1_disturbed"):
        if k in m:
            lines.append(f"  {k}: {m[k]}")
    lines.append("  grid: " + ", ".join(m.get("grid_order", [])))
    print("\n".join(lines))
    (run / "b0131.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {"PASS": 0, "FAIL": 1, "INVALID": 3}[v]


if __name__ == "__main__":
    sys.exit(main())
