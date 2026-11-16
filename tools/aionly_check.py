#!/usr/bin/env python3
"""AI-only race check (#134 and the batches after it): the player car out of the race, the AI racing live.

Usage:
    python -I tools/aionly_check.py runs/<batch>/race_<n> [--gamedb 56] [--track 9] [--loader-tag spectator]
    python -I tools/aionly_check.py --selftest

Generalised from tools/b0131_check.py with the supervisor's rulings on #134 (2026-11-16). Writes <race>/aionly.txt.
Validity (INVALID): FinalClassification present; the leader (final_position 1) status 3; >= 18 AI cars status 3; the
  track id and difficulty 100; weather.txt LOCKED (#118, second amendment); gamedb == --gamedb; no PAUSE cut.
Live-race check (any failure = FAIL):
  (a) from lights out (the last packet before session time leaves LGOT) to the FIRST of the leader's CHQF event and the
      first FinalClassification packet: session/wall time ratio 0.9-1.1 and no gap between race packets > 5 s. The
      ratio after CHQF is reported as info only (the run-in may be fast-forwarded).
  (b) laps.csv has laps 1..N-1 for every AI car classified as finished (status 3); an AI DNF doesn't fail it.
Pass criteria (FAIL otherwise): no SCAR event; no COLL event involving the player car's index from lights out until it
  is in the garage (LapData driverStatus 0), or to the end if it never gets there.
Reported only: lap-1 disturbance (AI cars > 3 s off the AI lap-1 median), the player's PENA times, when the player car
  first reads driverStatus 0 (garage) after lights out, its final result_status, the ratio and max gap, the grid order,
  and the loader.log lines of the add-on named by --loader-tag (with any "NOT found" among them).
Exit 0 PASS, 1 FAIL, 3 INVALID.
"""
from __future__ import annotations

import csv
import re
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
GAMEDB = re.compile(r"gamedb: (\d+) overwritten")
_POINTS_OVERRIDE: list | None = None      # selftest: synthetic (wall, session time, packet id)
_PLAYER_OVERRIDE: list | None = None      # selftest: synthetic (session time, driverStatus) of the player car
FIXTURE_FAIL = Path(__file__).parent.parent / "runs" / "2026-11-16-pilot-dsq" / "race_1"   # read-only known FAIL


def read_csv(p: Path) -> list[dict]:
    if not p.exists():
        return []
    with p.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def race_session(sessions: list[dict]) -> dict | None:
    r = [s for s in sessions if s.get("session_type") == "race"]
    return r[-1] if r else None


def race_packets(run: Path, uid: str, player: int | None):
    """(points, player_status): every race packet's (wall, session time, packet id), and the player car's
    (session time, driverStatus) from each LapData packet. None, None without raw/udp.bin."""
    if _POINTS_OVERRIDE is not None:
        return _POINTS_OVERRIDE, (_PLAYER_OVERRIDE or [])
    raw = run / "raw" / "udp.bin"
    if not raw.exists():
        return None, None
    import udp_parse as u  # noqa: E402
    pts, ps = [], []
    for wall, pkt in u.records(raw):
        if len(pkt) < u.HEADER.size:
            continue
        h = u.HEADER.unpack_from(pkt, 0)
        if str(h[6]) != uid:
            continue
        pts.append((wall, h[7], h[5]))
        if h[5] == 2 and player is not None:
            body = pkt[u.HEADER.size:]
            o = player * u.LAP.size
            if o + u.LAP.size <= len(body):
                ps.append((h[7], u.LAP.unpack_from(body, o)[u.L_DSTATUS]))
    return pts, ps


def live_window(pts, events):
    """Indices (start, end) of the live window, and the CHQF session time (or None)."""
    lgot = [float(e["session_time"]) for e in events if e["code"] == "LGOT"]
    t0 = lgot[0] if lgot else 0.0
    moving = next((i for i, p in enumerate(pts) if p[1] > t0 + 0.5), None)
    start = max(moving - 1, 0) if moving is not None else None
    chqf = [float(e["session_time"]) for e in events if e["code"] == "CHQF"]
    t_end = chqf[0] if chqf else None
    end_fc = next((i for i, p in enumerate(pts) if p[2] == 8), None)
    # the last packet at or before the leader's CHQF: anything after it is the run-in (may be fast-forwarded)
    end_ch = None
    if t_end is not None:
        before = [i for i, p in enumerate(pts) if p[1] <= t_end]
        end_ch = before[-1] if before else None
    ends = [i for i in (end_fc, end_ch) if i is not None]
    return start, (min(ends) if ends else None), t_end


def check(run: Path, gamedb: int, track: str, loader_tag: str) -> tuple[list[str], list[str], dict]:
    invalid: list[str] = []
    fails: list[str] = []
    m: dict = {}
    s = race_session(read_csv(run / "udp" / "sessions.csv"))
    if not s:
        return ["no race session in udp/sessions.csv"], [], m
    uid, player = s["session_uid"], s.get("player_car", "")
    pidx = int(player) if player.isdigit() else None
    if s.get("track_id") != track:
        invalid.append(f"track_id {s.get('track_id')}, expected {track}")
    if s.get("ai_difficulty") != "100":
        invalid.append(f"difficulty {s.get('ai_difficulty')}, expected 100")
    cars = [c for c in read_csv(run / "udp" / "cars.csv") if c["session_uid"] == uid]
    ai = [c for c in cars if c["car"] != player and c.get("ai") == "1"]
    if not any(c.get("result_status") not in ("", "NA", None) for c in cars):
        invalid.append("no FinalClassification")
    leader = [c for c in cars if c.get("final_position") == "1"]
    if not leader or leader[0].get("result_status") != "3":
        invalid.append("leader not classified as finished")
    finished = [c for c in ai if c.get("result_status") == "3"]
    if len(finished) < 18:
        invalid.append(f"{len(finished)} AI cars classified as finished, need >= 18")
    wx = run / "weather.txt"
    if not wx.exists() or not wx.read_text(encoding="utf-8").startswith("weather: LOCKED"):
        invalid.append("weather: " + (wx.read_text(encoding="utf-8").splitlines()[0] if wx.exists() else "no weather.txt"))
    ll = run / "raw" / "loader.log"
    log = ll.read_text(encoding="utf-8", errors="replace") if ll.exists() else ""
    db = GAMEDB.search(log)
    if not db or int(db[1]) != gamedb:
        invalid.append(f"gamedb {db[1] if db else 'none'} overwritten, expected {gamedb}")
    if (run / "pause_cut.txt").exists():
        invalid.append("pause cut")
    if loader_tag:
        tag = [ln.strip() for ln in log.splitlines() if loader_tag.lower() in ln.lower()]
        m["loader_lines"] = tag
        m["loader_not_found"] = [ln for ln in tag if "not found" in ln.lower()]

    events = [e for e in read_csv(run / "udp" / "events.csv") if e["session_uid"] == uid]
    pts, pstat = race_packets(run, uid, pidx)
    start = end = t_chqf = None
    if not pts:
        fails.append("live: no raw/udp.bin race packets to check")
    else:
        start, end, t_chqf = live_window(pts, events)
        if start is None or end is None or end <= start:
            fails.append("live: no lights-out-to-finish window")
        else:
            win = pts[start:end + 1]
            dw, ds = win[-1][0] - win[0][0], win[-1][1] - win[0][1]
            ratio = ds / dw if dw > 0 else float("inf")
            gaps = [b[0] - a[0] for a, b in zip(win, win[1:])]
            m["live_ratio"] = round(ratio, 3)
            m["live_max_gap_s"] = round(max(gaps), 2) if gaps else 0.0
            if not 0.9 <= ratio <= 1.1:
                fails.append(f"live: session/wall time ratio {ratio:.2f} (lights out to finish), outside 0.9-1.1")
            # the live window must reach the flag: a jump that skips past CHQF would otherwise look like a short live race
            if t_chqf is not None and win[-1][1] < t_chqf - 5:
                fails.append(f"live: telemetry stops at session time {win[-1][1]:.1f} s, before the chequered flag at {t_chqf:.1f} s")
            big = [(a[1], b[0] - a[0]) for a, b in zip(win, win[1:]) if b[0] - a[0] > 5]
            if big:
                fails.append(f"live: {len(big)} telemetry gap(s) > 5 s, first at session time {big[0][0]:.1f} s ({big[0][1]:.1f} s)")
            post = pts[end:]
            fc = next((i for i, p in enumerate(post) if p[2] == 8), None)
            if fc:
                pw, pss = post[fc][0] - post[0][0], post[fc][1] - post[0][1]
                m["post_chqf_ratio_info"] = round(pss / pw, 2) if pw > 0 else None
    total = int(s["total_laps"]) if str(s.get("total_laps", "")).isdigit() else 5
    laps = {(r["car"], r["lap"]) for r in read_csv(run / "udp" / "laps.csv") if r["session_uid"] == uid}
    missing = [c["car"] for c in finished if any((c["car"], str(n)) not in laps for n in range(1, total))]
    if missing:
        fails.append(f"live: laps.csv incomplete for {len(missing)} AI finisher(s) (laps 1-{total - 1})")

    m["scar"] = sum(1 for e in events if e["code"] == "SCAR")
    if m["scar"]:
        fails.append(f"SCAR events: {m['scar']}")
    pv = f"vehicle={player}"
    po = f"other={player}"
    t_lgot = next((float(e["session_time"]) for e in events if e["code"] == "LGOT"), 0.0)
    garage = next((t for t, st in (pstat or []) if t > t_lgot and st == 0), None)
    m["player_in_garage_s"] = round(garage, 2) if garage is not None else None
    coll = [float(e["session_time"]) for e in events if e["code"] == "COLL"
            and (pv in e["fields"].split(";") or po in e["fields"].split(";"))
            and float(e["session_time"]) >= t_lgot and (garage is None or float(e["session_time"]) <= garage)]
    m["player_coll_s"] = coll
    if coll:
        fails.append(f"COLL with the player car at {', '.join(f'{t:.1f}' for t in coll)} s")
    m["player_pena_s"] = [float(e["session_time"]) for e in events if e["code"] == "PENA" and pv in e["fields"].split(";")]
    pl = [c for c in cars if c["car"] == player]
    m["player_result_status"] = pl[0].get("result_status") if pl else None
    lap1 = [r for r in read_csv(run / "udp" / "laps.csv") if r["session_uid"] == uid and r["lap"] == "1" and r["car"] != player]
    if lap1:
        t = {r["car"]: int(r["lap_time_ms"]) / 1000 for r in lap1}
        med = statistics.median(t.values())
        m["lap1_median_s_info"] = round(med, 3)
        m["lap1_over_3s_info"] = sorted(c for c, v in t.items() if v - med > 3)
    grid = sorted(((int(c["grid"]), c["name"]) for c in cars if c.get("grid") not in ("NA", "", None)), key=lambda x: x[0])
    m["grid_order"] = [f"{g}:{n}" for g, n in grid]
    return invalid, fails, m


def verdict(invalid: list[str], fails: list[str]) -> str:
    return "INVALID" if invalid else ("FAIL" if fails else "PASS")


def selftest() -> int:
    import tempfile
    global _POINTS_OVERRIDE, _PLAYER_OVERRIDE
    ok = True
    live = [(1000.0 + t / 60, t / 60, 2) for t in range(0, 440 * 60, 6)]                 # 0-440 s live at 60 Hz
    chqf_jump = live + [(1441.0, 470.0, 2), (1441.5, 470.5, 8)]                           # run-in fast-forwarded after CHQF
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

        def cars(dnf=None):
            rows = [["7", str(c), f"D{c}", "1", str(c + 1), str(c + 1), "4" if c == dnf else "3"] for c in range(19)]
            w("cars.csv", ["session_uid", "car", "name", "ai", "grid", "final_position", "result_status"],
              rows + [["7", "19", "player", "0", "20", "20", "7"]])

        def laps(skip_car=None):
            w("laps.csv", ["session_uid", "car", "lap", "lap_time_ms", "position_at_line"],
              [["7", str(c), str(n), "90000", "1"] for c in range(19) for n in range(1, 5) if not (c == skip_car and n > 1)])

        def events(extra=()):
            w("events.csv", ["session_uid", "session_time", "wall_time", "code", "fields"],
              [["7", "0.0", "1000.0", "LGOT", ""], ["7", "440.0", "1440.0", "CHQF", ""]] + list(extra))
        cars(); laps(); events()
        (run / "weather.txt").write_text("weather: LOCKED\n", encoding="utf-8")
        (run / "raw" / "loader.log").write_text("[assets] gamedb: 56 overwritten\n[spectator] START IN GARAGE\n", encoding="utf-8")
        _PLAYER_OVERRIDE = [(0.5, 4), (2.5, 0), (10.0, 0)]
        _POINTS_OVERRIDE = live + [(1440.5, 440.5, 8)]
        inv, fl, m = check(run, 56, "9", "spectator")
        ok &= verdict(inv, fl) == "PASS" and m["player_in_garage_s"] == 2.5 and bool(m["loader_lines"])
        # (a) the run-in after CHQF fast-forwarded: still PASS, ratio reported as info
        _POINTS_OVERRIDE = chqf_jump
        inv, fl, m = check(run, 56, "9", "spectator")
        ok &= verdict(inv, fl) == "PASS" and m.get("post_chqf_ratio_info", 0) > 2
        _POINTS_OVERRIDE = live + [(1440.5, 440.5, 8)]
        # (b) one AI DNF with missing laps: PASS
        cars(dnf=18); laps(skip_car=18)
        inv, fl, m = check(run, 56, "9", "spectator")
        ok &= verdict(inv, fl) == "PASS"
        cars(); laps()
        # (c) a COLL with the player car before it is in the garage: FAIL
        events([["7", "1.5", "1001.5", "COLL", "vehicle=18;other=19"]])
        inv, fl, m = check(run, 56, "9", "spectator")
        ok &= verdict(inv, fl) == "FAIL" and m["player_coll_s"] == [1.5]
        # ... but not after it is in the garage
        events([["7", "30.0", "1030.0", "COLL", "vehicle=18;other=19"]])
        inv, fl, m = check(run, 56, "9", "spectator")
        ok &= verdict(inv, fl) == "PASS"
        events()
        # a simulated remainder before the finish: FAIL
        _POINTS_OVERRIDE = [p for p in live if p[1] <= 31] + [(1121.0, 450.5, 11), (1121.5, 450.5, 8)]
        inv, fl, m = check(run, 56, "9", "spectator")
        ok &= verdict(inv, fl) == "FAIL" and any("before the chequered flag" in f for f in fl)
        # ... and with no CHQF at all (the window then ends at the classification): ratio and gap FAIL
        events([]); w("events.csv", ["session_uid", "session_time", "wall_time", "code", "fields"], [["7", "0.0", "1000.0", "LGOT", ""]])
        inv, fl, m = check(run, 56, "9", "spectator")
        ok &= verdict(inv, fl) == "FAIL" and any("ratio" in f for f in fl) and any("gap" in f for f in fl)
        events()
        _POINTS_OVERRIDE = live + [(1440.5, 440.5, 8)]
        # SCAR: FAIL; gamedb mismatch: INVALID
        events([["7", "100.0", "1100.0", "SCAR", ""]])
        inv, fl, m = check(run, 56, "9", "spectator")
        ok &= verdict(inv, fl) == "FAIL"
        events()
        inv, fl, m = check(run, 52, "9", "spectator")
        ok &= verdict(inv, fl) == "INVALID"
    _POINTS_OVERRIDE = _PLAYER_OVERRIDE = None
    fixture = "skipped (not on this PC)"
    if (FIXTURE_FAIL / "raw" / "udp.bin").exists():
        inv, fl, m = check(FIXTURE_FAIL, 52, "9", "")
        good = any("ratio" in f for f in fl) and any("gap" in f for f in fl)
        ok &= good
        fixture = ("FAIL as expected: " if good else "NOT FAILED: ") + " | ".join(fl)
    print("selftest", "ok" if ok else "FAILED", "| fixture:", fixture)
    return 0 if ok else 1


def main() -> int:
    args = sys.argv[1:]
    if "--selftest" in args:
        return selftest()
    opts = {"--gamedb": "56", "--track": "9", "--loader-tag": "spectator"}
    for k in list(opts):
        if k in args:
            i = args.index(k)
            opts[k] = args[i + 1]
            del args[i:i + 2]
    if len(args) != 1:
        print(__doc__)
        return 3
    run = Path(args[0])
    invalid, fails, m = check(run, int(opts["--gamedb"]), opts["--track"], opts["--loader-tag"])
    v = verdict(invalid, fails)
    lines = [f"AI-only check: {v}"] + [f"  INVALID: {i}" for i in invalid] + [f"  FAIL: {f}" for f in fails]
    for k in ("live_ratio", "live_max_gap_s", "post_chqf_ratio_info", "scar", "player_pena_s", "player_in_garage_s",
              "player_coll_s", "player_result_status", "lap1_median_s_info", "lap1_over_3s_info", "loader_not_found"):
        if k in m:
            lines.append(f"  {k}: {m[k]}")
    lines.append("  grid: " + ", ".join(m.get("grid_order", [])))
    for ln in m.get("loader_lines", [])[:40]:
        lines.append(f"  loader: {ln}")
    print("\n".join(lines))
    (run / "aionly.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {"PASS": 0, "FAIL": 1, "INVALID": 3}[v]


if __name__ == "__main__":
    sys.exit(main())
