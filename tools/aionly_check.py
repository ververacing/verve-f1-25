#!/usr/bin/env python3
"""AI-only race check (the spectator garage-start route, #134; B-0018 and after): the player car parked in the garage,
the AI racing live. The player never finishes, so there is no CHQF and no FinalClassification: LapData is the finish.

Usage:
    python -I tools/aionly_check.py runs/<batch>/race_<n> [--gamedb 56] [--track 9] [--loader-tag spectator]
    python -I tools/aionly_check.py --selftest

Rulings (supervisor, #134 Option A, 2026-11-16). Writes <race>/aionly.txt.
1. Finish source = LapData. "Finished" = LapData resultStatus 3. Validity (INVALID otherwise): the leader (LapData
   position 1 in the last frame) is status 3; >= 18 AI cars are status 3 (an AI car not finished when the session was
   quit counts as not finished); track id and difficulty 100; weather.txt LOCKED (#118, second amendment); gamedb ==
   --gamedb; no PAUSE cut. A missing FinalClassification is not INVALID.
2. Live window (FAIL otherwise): lights out (the last packet before session time leaves LGOT) to the leader's finish
   (the first AI LapData status 3; or CHQF / the first FinalClassification if earlier): session/wall time ratio 0.9-1.1,
   no gap between race packets > 5 s, and the window must reach the finish (within 5 s). laps.csv has laps 1..N-1 for
   every AI finisher. The run-in ratio after the leader's finish is info only.
5. Pass (FAIL otherwise): no COLL with the player car's index from lights out until it is in the garage (LapData
   driverStatus 0); no PENA for the player car before it is in the garage; no SCAR.
Reported: lap-1 > 3 s off the AI median (report only), the player's garage time, PENAs and final LapData status, each
AI finish time, the ratio and max gap, the grid order, the final order, and the add-on's loader.log lines.
(Rule 3, the per-car race-feel window, lives in tools/race_feel.py; rule 4, the quit trigger, in the runner.)
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
_RACE_OVERRIDE: dict | None = None   # selftest: {"points": [(wall, st, pid)], "player": [(st, dstatus)], "laps": {...}}
FIXTURE_FAIL = Path(__file__).parent.parent / "runs" / "2026-11-16-pilot-dsq" / "race_1"   # read-only known FAIL


def read_csv(p: Path) -> list[dict]:
    if not p.exists():
        return []
    with p.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def race_session(sessions: list[dict]) -> dict | None:
    r = [s for s in sessions if s.get("session_type") == "race"]
    return r[-1] if r else None


def race_stream(run: Path, uid: str, player: int | None, n_cars: int = 20) -> dict | None:
    """From raw/udp.bin: points (wall, session time, packet id) of every race packet; player (session time, driverStatus)
    from each LapData packet; laps {car: {"status", "pos", "finish_s"}} from the last LapData frame, with each car's
    first status-3 session time."""
    if _RACE_OVERRIDE is not None:
        return _RACE_OVERRIDE
    raw = run / "raw" / "udp.bin"
    if not raw.exists():
        return None
    import udp_parse as u  # noqa: E402
    pts, ps, last, fin = [], [], None, {}
    for wall, pkt in u.records(raw):
        if len(pkt) < u.HEADER.size:
            continue
        h = u.HEADER.unpack_from(pkt, 0)
        if str(h[6]) != uid:
            continue
        pts.append((wall, h[7], h[5]))
        if h[5] != 2:
            continue
        body = pkt[u.HEADER.size:]
        cars = [u.LAP.unpack_from(body, c * u.LAP.size) for c in range(min(n_cars, (len(body) - 2) // u.LAP.size))]
        if player is not None and player < len(cars):
            ps.append((h[7], cars[player][u.L_DSTATUS]))
        for c, car in enumerate(cars):
            if car[u.L_RSTATUS] == 3 and c not in fin:
                fin[c] = h[7]
        last = cars
    laps = {}
    for c, car in enumerate(last or []):
        laps[c] = {"status": car[u.L_RSTATUS], "pos": car[u.L_POS], "finish_s": fin.get(c)}
    return {"points": pts, "player": ps, "laps": laps}


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
    names = {c["car"]: c.get("name", c["car"]) for c in cars}
    ai_idx = [int(c["car"]) for c in cars if c["car"] != player and c.get("ai") == "1"]
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

    rs = race_stream(run, uid, pidx)
    laps = (rs or {}).get("laps", {})
    if not laps:
        invalid.append("no LapData for the race session (raw/udp.bin)")
    finished = sorted(c for c in ai_idx if laps.get(c, {}).get("status") == 3)
    m["ai_finished"] = len(finished)
    if len(finished) < 18:
        invalid.append(f"{len(finished)} AI cars finished (LapData status 3), need >= 18")
    leader = [c for c, v in laps.items() if v.get("pos") == 1]
    if not leader or laps[leader[0]].get("status") != 3:
        invalid.append("the leader (LapData position 1) is not status 3")
    fin_times = [laps[c]["finish_s"] for c in finished if laps[c].get("finish_s") is not None]
    t_finish = min(fin_times) if fin_times else None
    m["leader_finish_s"] = round(t_finish, 1) if t_finish is not None else None
    m["final_order"] = [f"{v['pos']}:{names.get(str(c), c)}" for c, v in sorted(laps.items(), key=lambda x: x[1].get("pos") or 99)
                        if v.get("pos")]

    events = [e for e in read_csv(run / "udp" / "events.csv") if e["session_uid"] == uid]
    t_lgot = next((float(e["session_time"]) for e in events if e["code"] == "LGOT"), 0.0)
    pts = (rs or {}).get("points") or []
    if not pts:
        fails.append("live: no raw/udp.bin race packets to check")
    else:
        moving = next((i for i, p in enumerate(pts) if p[1] > t_lgot + 0.5), None)
        start = max(moving - 1, 0) if moving is not None else None
        ends = [t for t in (t_finish,) if t is not None]
        ends += [float(e["session_time"]) for e in events if e["code"] == "CHQF"][:1]
        fc = next((p[1] for p in pts if p[2] == 8), None)
        if fc is not None:
            ends.append(fc)
        t_end = min(ends) if ends else None
        before = [i for i, p in enumerate(pts) if t_end is not None and p[1] <= t_end]
        end = before[-1] if before else None
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
            if win[-1][1] < t_end - 5:
                fails.append(f"live: telemetry stops at session time {win[-1][1]:.1f} s, before the finish at {t_end:.1f} s")
            big = [(a[1], b[0] - a[0]) for a, b in zip(win, win[1:]) if b[0] - a[0] > 5]
            if big:
                fails.append(f"live: {len(big)} telemetry gap(s) > 5 s, first at session time {big[0][0]:.1f} s ({big[0][1]:.1f} s)")
            post = pts[end:]
            if len(post) > 1:
                pw, pss = post[-1][0] - post[0][0], post[-1][1] - post[0][1]
                m["run_in_ratio_info"] = round(pss / pw, 2) if pw > 0 else None
    total = int(s["total_laps"]) if str(s.get("total_laps", "")).isdigit() else 5
    lap_rows = {(r["car"], r["lap"]) for r in read_csv(run / "udp" / "laps.csv") if r["session_uid"] == uid}
    missing = [c for c in finished if any((str(c), str(n)) not in lap_rows for n in range(1, total))]
    if missing:
        fails.append(f"live: laps.csv incomplete for {len(missing)} AI finisher(s) (laps 1-{total - 1})")
    # a plausible finish: the leader's LapData finish comes after its own recorded laps 1..N-1. (After a player DSQ the
    # game flips every AI car to status 3 at once when it switches to simulating, F-45: a "finish" at 30 s.)
    if leader and t_finish is not None:
        lt = {int(r["lap"]): int(r["lap_time_ms"]) / 1000 for r in read_csv(run / "udp" / "laps.csv")
              if r["session_uid"] == uid and r["car"] == str(leader[0])}
        done = sum(lt.get(n, 0) for n in range(1, total))
        if done == 0 or t_finish < t_lgot + done:
            fails.append(f"live: implausible finish at {t_finish:.1f} s (the leader's recorded laps 1-{total - 1} total {done:.1f} s)")

    m["scar"] = sum(1 for e in events if e["code"] == "SCAR")
    if m["scar"]:
        fails.append(f"SCAR events: {m['scar']}")
    pv, po = f"vehicle={player}", f"other={player}"
    garage = next((t for t, st in (rs or {}).get("player", []) if t > t_lgot and st == 0), None)
    m["player_in_garage_s"] = round(garage, 2) if garage is not None else None

    def before_garage(t: float) -> bool:
        return t >= t_lgot and (garage is None or t <= garage)
    coll = [float(e["session_time"]) for e in events if e["code"] == "COLL"
            and (pv in e["fields"].split(";") or po in e["fields"].split(";")) and before_garage(float(e["session_time"]))]
    m["player_coll_s"] = coll
    if coll:
        fails.append(f"COLL with the player car at {', '.join(f'{t:.1f}' for t in coll)} s")
    pena = [float(e["session_time"]) for e in events if e["code"] == "PENA" and pv in e["fields"].split(";")]
    m["player_pena_s"] = pena
    early = [t for t in pena if garage is None or t <= garage]
    if early:
        fails.append(f"PENA for the player car before it was in the garage, at {', '.join(f'{t:.1f}' for t in early)} s")
    m["player_lapdata_status"] = laps.get(pidx, {}).get("status") if pidx is not None else None
    lap1 = [r for r in read_csv(run / "udp" / "laps.csv") if r["session_uid"] == uid and r["lap"] == "1" and r["car"] != player]
    if lap1:
        t = {r["car"]: int(r["lap_time_ms"]) / 1000 for r in lap1}
        med = statistics.median(t.values())
        m["lap1_median_s_info"] = round(med, 3)
        m["lap1_over_3s_info"] = sorted(names.get(c, c) for c, v in t.items() if v - med > 3)
    grid = sorted(((int(c["grid"]), c["name"]) for c in cars if c.get("grid") not in ("NA", "", None)), key=lambda x: x[0])
    m["grid_order"] = [f"{g}:{n}" for g, n in grid]
    return invalid, fails, m


def verdict(invalid: list[str], fails: list[str]) -> str:
    return "INVALID" if invalid else ("FAIL" if fails else "PASS")


def selftest() -> int:
    import tempfile
    global _RACE_OVERRIDE
    ok = True
    results = []
    live = [(1000.0 + t / 60, t / 60, 2) for t in range(0, 550 * 60, 6)]   # 0-550 s live at 60 Hz, no FC packet

    def lapstate(n_finished=19, leader_ok=True):
        st = {c: {"status": 3 if c < n_finished else 2, "pos": c + 1, "finish_s": 400.0 + c if c < n_finished else None}
              for c in range(19)}
        if not leader_ok:
            st[0]["status"] = 2
        st[19] = {"status": 2, "pos": 20, "finish_s": None}   # the player, active in the garage
        return st

    def race(points=None, player=None, laps=None):
        return {"points": points if points is not None else live, "player": player if player is not None else [(0.5, 4), (2.5, 0)],
                "laps": laps if laps is not None else lapstate()}
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
        # cars.csv with NO FinalClassification (result_status NA), as on this route
        w("cars.csv", ["session_uid", "car", "name", "ai", "grid", "final_position", "result_status"],
          [["7", str(c), f"D{c}", "1", str(c + 1), "NA", "NA"] for c in range(19)] + [["7", "19", "player", "0", "20", "NA", "NA"]])

        def laps_csv(skip_car=None):
            w("laps.csv", ["session_uid", "car", "lap", "lap_time_ms", "position_at_line"],
              [["7", str(c), str(n), "90000", "1"] for c in range(19) for n in range(1, 5) if not (c == skip_car and n > 1)])

        def events(extra=()):
            w("events.csv", ["session_uid", "session_time", "wall_time", "code", "fields"], [["7", "0.0", "1000.0", "LGOT", ""]] + list(extra))
        laps_csv(); events()
        (run / "weather.txt").write_text("weather: LOCKED\n", encoding="utf-8")
        (run / "raw" / "loader.log").write_text("[assets] gamedb: 56 overwritten\n[spectator] START IN GARAGE\n", encoding="utf-8")

        def case(name, want, **kw):
            nonlocal ok
            global _RACE_OVERRIDE
            _RACE_OVERRIDE = race(**kw)
            inv, fl, m = check(run, kw.pop("gamedb", 56) if "gamedb" in kw else 56, "9", "spectator")
            v = verdict(inv, fl)
            good = v == want
            ok &= good
            results.append(f"{'ok' if good else 'FAIL'} {name}: {v}")
            return m
        m = case("no FinalClassification, LapData finishes (19), live", "PASS")
        ok &= m["leader_finish_s"] == 400.0 and m["player_in_garage_s"] == 2.5 and m["ai_finished"] == 19
        case("timeout with 17 AI finished", "INVALID", laps=lapstate(n_finished=17))
        case("18 AI finished (one DNF-at-quit), its laps missing", "PASS", laps=lapstate(n_finished=18))
        case("leader not status 3", "INVALID", laps=lapstate(leader_ok=False))
        case("run-in fast-forwarded after the leader's finish", "PASS",
             points=[p for p in live if p[1] <= 401] + [(1402.0, 470.0, 2), (1402.5, 470.5, 2)])
        case("simulated past the finish (31 -> 450 s)", "FAIL",
             points=[p for p in live if p[1] <= 31] + [(1121.0, 450.5, 2), (1121.5, 451.0, 2)])
        events([["7", "1.5", "1001.5", "COLL", "vehicle=18;other=19"]])
        case("COLL with the player car before the garage", "FAIL")
        events([["7", "30.0", "1030.0", "COLL", "vehicle=18;other=19"]])
        case("COLL with the player car after the garage", "PASS")
        events([["7", "1.8", "1001.8", "PENA", "penalty_type=5;infringement=1;vehicle=19"]])
        case("PENA for the player before the garage", "FAIL")
        events([["7", "100.0", "1100.0", "SCAR", ""]])
        case("SCAR", "FAIL")
        events()
        laps_csv(skip_car=5)
        case("an AI finisher missing laps", "FAIL")
        laps_csv()
        (run / "raw" / "loader.log").write_text("[assets] gamedb: 52 overwritten\n", encoding="utf-8")
        case("gamedb mismatch", "INVALID")
    _RACE_OVERRIDE = None
    fixture = "skipped (not on this PC)"
    if (FIXTURE_FAIL / "raw" / "udp.bin").exists():
        inv, fl, m = check(FIXTURE_FAIL, 52, "9", "")
        good = any("implausible finish" in f for f in fl) and any("incomplete" in f for f in fl)
        ok &= good
        fixture = ("not PASS as expected: " if good else "PASSED (wrong): ") + " | ".join(inv + fl)
    print("\n".join(results))
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
    for k in ("ai_finished", "leader_finish_s", "live_ratio", "live_max_gap_s", "run_in_ratio_info", "scar",
              "player_in_garage_s", "player_pena_s", "player_coll_s", "player_lapdata_status", "lap1_median_s_info",
              "lap1_over_3s_info", "loader_not_found"):
        if k in m:
            lines.append(f"  {k}: {m[k]}")
    lines.append("  grid: " + ", ".join(m.get("grid_order", [])))
    lines.append("  final: " + ", ".join(m.get("final_order", [])))
    for ln in m.get("loader_lines", [])[:40]:
        lines.append(f"  loader: {ln}")
    print("\n".join(lines))
    (run / "aionly.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {"PASS": 0, "FAIL": 1, "INVALID": 3}[v]


if __name__ == "__main__":
    sys.exit(main())
