#!/usr/bin/env python3
"""Follow a live udp_capture.py recording and return when the AI-only race is over (#134 ruling 4).

Usage:
    python -I tools/udp_finish_watch.py --bin <udp.bin> [--max-s 900] [--after-leader-s 150] [--exclude-uids <a,b,..>]
    python -I tools/udp_finish_watch.py --bin <udp.bin> --start-only <cutoff s> [--max-s 120] [--exclude-uids <a,b,..>]
    python -I tools/udp_finish_watch.py --selftest [--real <a finished capture>]

Reads the growing capture (records of <wall f64><length u16><packet>) from where it last stopped. In the race session
(Session packet type 15-17), from LapData: done when every active AI car (not the player car, header playerCarIndex;
resultStatus 2 or more seen) has resultStatus >= 3 (finished, DNF, DSQ, retired, ...). The player car is ignored: on the
spectator garage route it stays at 2 (active) in the garage.
Exit 0 all AI done; 1 timeout at the leader's finish + --after-leader-s (the first AI status 3) with AI still running;
2 --max-s passed with no finish (or no race session); 3 no capture file; 4 the LapData layout from tools/udp_parse.py
isn't the expected one (57-byte entry, resultStatus at byte 45), so nothing is watched. Prints one summary line, then
`finished uid <uid>` (exit 0) or `timeout uid <uid>` (exit 1): the race session uid it ended on.
--stop-file <pause flag> and --game-pid <pid>: exit 5 at once ("stopped: pause flag" / "stopped: game exited") when the
flag appears or the game is gone. The liveness check is read-only (OpenProcess + GetExitCodeProcess, never os.kill).

Several races per launch (V-1, `@restart` in tools/sandbox_shell.ps1): each restart is a new session uid in the same
capture. --exclude-uids lists race session uids to ignore (the races already ended in this launch), so a later call
waits for the next race instead of returning at once on an earlier one. The done check runs after every LapData
packet, so the first race not excluded that is done ends the watch even when a later session follows it in the file.

--start-only <cutoff s> (C-1, docs/verve_c1_prereg.md: start-only restarts; `@startwait` in tools/sandbox_shell.ps1):
no finish is waited for. The newest race session (type 15-17) whose uid is not in --exclude-uids must show its lights-out
event (LGOT), then the wait lasts until the capture's wall time (its records' wall clock) is >= the LGOT's arrival +
<cutoff s>. Prints one summary line, then `started uid <uid>`. Exit 0 started; 2 no LGOT in a new race session within
--max-s (default 120 in this mode), or the capture stalled after the LGOT (not past LGOT + cutoff within cutoff +
STALL_S 30 s of seeing it); 3 no capture file; 5 the pause flag or the game gone (as above). LapData isn't read in this
mode, so the layout check (exit 4) doesn't apply.
"""
from __future__ import annotations

import os
import struct
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import udp_parse as u  # noqa: E402   one source of truth for the LapData layout (#139 review)

HEADER = u.HEADER
REC = struct.Struct("<dH")
LAP_SIZE = u.LAP.size
# resultStatus's byte offset in a LapData entry: the size of the fields before L_RSTATUS in udp_parse's LAP format
RSTATUS_OFF = struct.calcsize("<" + u.LAP.format.lstrip("<=>!@")[:u.L_RSTATUS])
EXPECT_LAP_SIZE, EXPECT_RSTATUS_OFF = 57, 45   # F1 25 spec (formats 2025 and 2026)


def layout_ok() -> bool:
    return LAP_SIZE == EXPECT_LAP_SIZE and RSTATUS_OFF == EXPECT_RSTATUS_OFF


class Watch:
    def __init__(self, exclude: frozenset = frozenset()):
        self.exclude = exclude   # race session uids to ignore (already ended in this launch)
        self.race_uid = None
        self.player = None
        self.status: dict[int, int] = {}
        self.leader_wall = None

    def feed(self, wall: float, pkt: bytes):
        if len(pkt) < HEADER.size:
            return
        h = HEADER.unpack_from(pkt, 0)
        pid, uid, body = h[5], h[6], pkt[HEADER.size:]
        if uid in self.exclude:
            return
        if pid == 1 and len(body) > 6 and body[6] in (15, 16, 17):
            if uid != self.race_uid:
                self.race_uid, self.status, self.leader_wall = uid, {}, None
            self.player = h[10]
        elif pid == 2 and uid == self.race_uid and self.race_uid is not None:
            n = (len(body) - 2) // LAP_SIZE
            for c in range(n):
                if c == self.player:
                    continue
                st = body[c * LAP_SIZE + RSTATUS_OFF]
                if st >= 2 or c in self.status:
                    self.status[c] = st
                    if st == 3 and self.leader_wall is None:
                        self.leader_wall = wall

    def done(self) -> bool:
        return bool(self.status) and all(s >= 3 for s in self.status.values())


def pid_alive(pid: int) -> bool:
    """Read-only liveness check (never os.kill: on Windows any signal but the CTRL events terminates the process)."""
    if os.name != "nt":
        return Path(f"/proc/{pid}").exists()
    import ctypes
    k32 = ctypes.windll.kernel32
    h = k32.OpenProcess(0x1000, False, pid)          # PROCESS_QUERY_LIMITED_INFORMATION
    if not h:
        return False
    try:
        code = ctypes.c_ulong()
        return bool(k32.GetExitCodeProcess(h, ctypes.byref(code))) and code.value == 259   # STILL_ACTIVE
    finally:
        k32.CloseHandle(h)


def stop_check(stop_file: Path | None, game_pid: int | None, alive=pid_alive):
    """A callable giving the reason to stop at once (the pause flag, or our game gone), or None."""
    def check():
        if stop_file is not None and stop_file.exists():
            return "pause flag"
        if game_pid is not None and not alive(game_pid):
            return "game exited"
        return None
    return check


class Tail:
    """The records appended to a growing capture since the last read (<wall f64><length u16><packet>). Read-only."""

    def __init__(self, path: Path):
        self.path, self.pos, self.buf = path, 0, b""

    def packets(self):
        """Yield (wall, packet) for every complete record appended since the last call. A caller may stop early (a
        done watch returns at once); the records not yet yielded are kept for the next call."""
        with open(self.path, "rb") as f:
            f.seek(self.pos)
            chunk = f.read()
        self.pos += len(chunk)
        self.buf += chunk
        i = 0
        try:
            while i + REC.size <= len(self.buf):
                wall, n = REC.unpack_from(self.buf, i)
                if i + REC.size + n > len(self.buf):
                    break
                pkt = self.buf[i + REC.size:i + REC.size + n]
                i += REC.size + n
                yield wall, pkt
        finally:
            self.buf = self.buf[i:]


def wait_capture(path: Path, clock, sleep, stop) -> tuple[int, str] | None:
    """Wait up to 30 s for the capture file: None once it exists, else (exit code, summary)."""
    t0 = clock()
    while not path.exists():
        why = stop()
        if why:
            return 5, f"stopped: {why}"
        if clock() - t0 > 30:
            return 3, f"no capture at {path}"
        sleep(1)
    return None


def run(path: Path, max_s: float, after_leader_s: float, clock=time.time, sleep=time.sleep,
        exclude: frozenset = frozenset(), stop=lambda: None) -> tuple[int, str, int | None]:
    """(exit code, summary, the race session uid it ended on, or None). Exit 5 = stopped at once (stop() said why)."""
    t0 = clock()
    early = wait_capture(path, clock, sleep, stop)
    if early:
        return early[0], early[1], None
    w, tail = Watch(exclude), Tail(path)
    while True:
        for wall, pkt in tail.packets():
            w.feed(wall, pkt)
            # per packet, not per chunk: a done race followed by a newer session in the same chunk still ends the watch
            if w.done():
                fin = sum(1 for s in w.status.values() if s == 3)
                return 0, f"all {len(w.status)} AI cars done ({fin} finished)", w.race_uid
        n_ai = len(w.status)
        fin = sum(1 for s in w.status.values() if s == 3)
        now = clock()
        why = stop()
        if why:   # a PAUSE (tools/pause.ps1) or the game gone: end now, not at max_s (the 14:55 pause waited 10 min)
            return 5, f"stopped: {why} ({fin} of {n_ai} AI cars finished)", w.race_uid
        if w.leader_wall is not None and now - w.leader_wall > after_leader_s:
            return 1, (f"timeout {after_leader_s:.0f} s after the leader's finish: {fin} of {n_ai} AI cars finished"), w.race_uid
        if now - t0 > max_s:
            return 2, f"max {max_s:.0f} s with no finish ({fin} of {n_ai} AI cars finished)", w.race_uid
        sleep(2)


# ---------------------------------------------------------------------------------------------------- start-only (C-1)
STALL_S = 30.0   # start-only: after the LGOT, the capture must reach LGOT + cutoff within cutoff + this (clock seconds)


class StartWatch:
    """Start-only (C-1, docs/verve_c1_prereg.md): the newest race session (Session packet type 15-17) whose uid is not
    excluded, its lights-out event (LGOT, wall time of arrival), and the capture's latest wall time."""

    def __init__(self, cutoff_s: float, exclude: frozenset = frozenset()):
        self.cutoff_s, self.exclude = cutoff_s, exclude
        self.race_uid = None
        self.lgot: dict[int, float] = {}   # uid -> the LGOT arrival wall (first one), any uid not excluded
        self.last_wall = None

    def feed(self, wall: float, pkt: bytes):
        if len(pkt) < HEADER.size:
            return
        self.last_wall = wall if self.last_wall is None else max(self.last_wall, wall)
        h = HEADER.unpack_from(pkt, 0)
        pid, uid, body = h[5], h[6], pkt[HEADER.size:]
        if uid in self.exclude:
            return
        if pid == 1 and len(body) > 6 and body[6] in (15, 16, 17):
            self.race_uid = uid
        elif pid == 3 and body[:4] == b"LGOT" and uid not in self.lgot:
            self.lgot[uid] = wall

    def lights_out(self) -> float | None:
        return self.lgot.get(self.race_uid) if self.race_uid is not None else None

    def done(self) -> bool:
        lg = self.lights_out()
        return lg is not None and self.last_wall is not None and self.last_wall >= lg + self.cutoff_s


def run_start(path: Path, cutoff_s: float, max_s: float = 120, clock=time.time, sleep=time.sleep,
              exclude: frozenset = frozenset(), stop=lambda: None) -> tuple[int, str, int | None]:
    """Start-only: (exit code, summary, uid). 0 = the newest race uid not excluded showed its LGOT and the capture's wall
    time reached LGOT + cutoff_s; 2 = no LGOT within max_s, or the capture stalled after it (not past LGOT + cutoff
    within cutoff + STALL_S s of seeing the LGOT); 3 = no capture; 5 = stopped (stop() said why)."""
    t0 = clock()
    early = wait_capture(path, clock, sleep, stop)
    if early:
        return early[0], early[1], None
    w, tail = StartWatch(cutoff_s, exclude), Tail(path)
    seen_lgot = None
    while True:
        for wall, pkt in tail.packets():
            w.feed(wall, pkt)
            if w.done():   # per packet: the first race not excluded that reaches its cutoff ends the wait
                return 0, (f"lights out (LGOT) of race uid {w.race_uid}, capture past LGOT + {cutoff_s:g} s"), w.race_uid
        now = clock()
        why = stop()
        if why:
            return 5, f"stopped: {why}", w.race_uid
        lg = w.lights_out()
        if lg is not None:
            if seen_lgot is None:
                seen_lgot = now
            if now - seen_lgot > cutoff_s + STALL_S:
                reached = (w.last_wall - lg) if w.last_wall is not None else 0.0
                return 2, (f"race uid {w.race_uid}: the capture stalled at LGOT + {reached:.1f} s (not past "
                           f"LGOT + {cutoff_s:g} s within {cutoff_s + STALL_S:.0f} s)"), w.race_uid
        elif now - t0 > max_s:
            what = f" (race uid {w.race_uid} seen, no LGOT)" if w.race_uid is not None else " (no new race session)"
            return 2, f"no lights out (LGOT) in a new race session within {max_s:.0f} s{what}", w.race_uid
        sleep(1)


def selftest(real: Path | None = None) -> int:
    import tempfile

    def pkt(pid, uid, body, player=19):
        return HEADER.pack(2026, 25, 1, 0, 1, pid, uid, 0.0, 0, 0, player, 255) + body

    def session(stype=15):
        return bytes([0, 30, 20, 5, 0, 0, stype, 9]) + bytes(40)

    def lapdata(statuses):
        b = bytearray(LAP_SIZE * 24 + 2)
        for c, st in enumerate(statuses):
            b[c * LAP_SIZE + RSTATUS_OFF] = st
        return bytes(b)
    ok = True
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "udp.bin"

        def write(recs):
            with open(p, "wb") as f:
                for wall, pk in recs:
                    f.write(REC.pack(wall, len(pk)) + pk)
        clock = {"t": 1000.0}
        fake_clock = lambda: clock["t"]   # noqa: E731

        def fake_sleep(s):
            clock["t"] += s
        all_done = [2] * 0 + [3] * 19 + [2]          # 19 AI finished, the player (19) active
        write([(1000.0, pkt(1, 7, session())), (1001.0, pkt(2, 7, lapdata([2] * 20))), (1400.0, pkt(2, 7, lapdata(all_done)))])
        code, msg, _ = run(p, 900, 150, fake_clock, fake_sleep)
        ok &= code == 0
        print("case all AI done:", code, msg)
        one_left = [3] * 18 + [2] + [2]               # one AI car still running, the player active
        clock["t"] = 1000.0
        write([(1000.0, pkt(1, 7, session())), (1001.0, pkt(2, 7, lapdata([2] * 20))), (1000.5, pkt(2, 7, lapdata(one_left)))])
        code, msg, _ = run(p, 900, 150, fake_clock, fake_sleep)
        ok &= code == 1
        print("case timeout after the leader:", code, msg)
        clock["t"] = 1000.0
        write([(1000.0, pkt(1, 7, session(10))), (1001.0, pkt(2, 7, lapdata([2] * 20)))])   # practice only
        code, msg, _ = run(p, 60, 150, fake_clock, fake_sleep)
        ok &= code == 2
        print("case no race session:", code, msg)
        dnf = [3] * 17 + [4, 7] + [2]                 # two AI DNF/DSQ count as done
        clock["t"] = 1000.0
        write([(1000.0, pkt(1, 7, session())), (1001.0, pkt(2, 7, lapdata(dnf)))])
        code, msg, _ = run(p, 900, 150, fake_clock, fake_sleep)
        ok &= code == 0
        print("case DNFs done:", code, msg)
        # several races per launch (V-1 @restart): race uid 7 finished, then race uid 8 running in the same capture
        two = [(1000.0, pkt(1, 7, session())), (1001.0, pkt(2, 7, lapdata([2] * 20))), (1400.0, pkt(2, 7, lapdata(all_done))),
               (1450.0, pkt(1, 8, session())), (1451.0, pkt(2, 8, lapdata([2] * 20)))]
        clock["t"] = 1000.0
        write(two)
        code, msg, uid = run(p, 60, 150, fake_clock, fake_sleep)
        ok &= code == 0 and uid == 7
        print("case two races, no exclude -> returns on 7:", code, msg, "uid", uid)
        clock["t"] = 1000.0
        code, msg, uid = run(p, 60, 150, fake_clock, fake_sleep, exclude=frozenset({7}))
        ok &= code == 2 and uid == 8
        print("case two races, exclude 7 -> waits for 8 (max):", code, msg, "uid", uid)
        lead = [3] + [2] * 19                          # race 8's leader finished, the others still running
        clock["t"] = 1000.0
        write(two + [(1000.5, pkt(2, 8, lapdata(lead)))])
        code, msg, uid = run(p, 900, 150, fake_clock, fake_sleep, exclude=frozenset({7}))
        ok &= code == 1 and uid == 8
        print("case two races, exclude 7 -> waits for 8 (timeout after its leader):", code, msg, "uid", uid)
        clock["t"] = 1000.0
        write(two + [(1500.0, pkt(2, 8, lapdata(all_done)))])
        code, msg, uid = run(p, 900, 150, fake_clock, fake_sleep, exclude=frozenset({7}))
        ok &= code == 0 and uid == 8
        print("case two races, exclude 7 -> 8 done:", code, msg, "uid", uid)
        clock["t"] = 1000.0
        code, msg, uid = run(p, 60, 150, fake_clock, fake_sleep, exclude=frozenset({7, 8}))
        ok &= code == 2 and uid is None
        print("case two races, exclude 7,8 -> no race left (max):", code, msg, "uid", uid)
        # a PAUSE or the game gone ends the watch at once (the 14:55 pause sat on a 900 s watch): exit 5, uid kept
        flag = Path(d) / "paused.txt"
        clock["t"] = 1000.0
        write(two)
        calls = {"n": 0}

        def flag_on_third_sleep(s):
            fake_sleep(s)
            calls["n"] += 1
            if calls["n"] == 3:
                flag.write_text("PAUSE")
        code, msg, uid = run(p, 900, 150, fake_clock, flag_on_third_sleep, exclude=frozenset({7}),
                             stop=stop_check(flag, None))
        ok &= code == 5 and "pause flag" in msg and uid == 8 and clock["t"] < 1100
        print("case pause flag mid-watch -> stopped at once:", code, msg, "uid", uid, f"after {clock['t'] - 1000:.0f} s")
        flag.unlink()
        clock["t"] = 1000.0
        code, msg, uid = run(p, 900, 150, fake_clock, fake_sleep, exclude=frozenset({7}),
                             stop=stop_check(None, 4242, alive=lambda pid: False))
        ok &= code == 5 and "game exited" in msg and clock["t"] < 1010
        print("case game gone -> stopped at once:", code, msg, "uid", uid)
        clock["t"] = 1000.0
        code, msg, uid = run(p, 60, 150, fake_clock, fake_sleep, exclude=frozenset({7}),
                             stop=stop_check(flag, 4242, alive=lambda pid: True))
        ok &= code == 2
        print("case no flag, game alive -> normal max:", code, msg)
        ok &= pid_alive(os.getpid()) and not pid_alive(0x7FFFFFF0)
        print("case pid_alive (read-only): this process alive, a free pid not:", pid_alive(os.getpid()), pid_alive(0x7FFFFFF0))
        # ---- start-only (C-1): the newest race uid not excluded, its LGOT, then the capture past LGOT + cutoff
        def lgot(uid):
            return pkt(3, uid, b"LGOT" + bytes(12))

        def tick(uid, w0, w1, step=0.5):
            return [(w0 + i * step, pkt(2, uid, lapdata([2] * 20))) for i in range(int((w1 - w0) / step) + 1)]
        start7 = [(990.0, pkt(1, 7, session())), (1000.0, lgot(7))] + tick(7, 1000.5, 1021.0)
        clock["t"] = 1000.0
        write(start7)
        code, msg, uid = run_start(p, 20, 120, fake_clock, fake_sleep)
        ok &= code == 0 and uid == 7
        print("case start-only: LGOT, capture past LGOT + 20 s -> started:", code, msg, "uid", uid)
        clock["t"] = 1000.0
        write([(990.0, pkt(1, 7, session())), (1000.0, lgot(7))] + tick(7, 1000.5, 1019.0))
        code, msg, uid = run_start(p, 20, 120, fake_clock, fake_sleep)
        ok &= code == 2 and uid == 7 and "stalled" in msg
        print("case start-only: capture stops at LGOT + 19 s -> stalled (2):", code, msg, "uid", uid)
        # live: the capture grows past the cutoff only after two reads
        clock["t"] = 1000.0
        write([(990.0, pkt(1, 7, session())), (1000.0, lgot(7))] + tick(7, 1000.5, 1005.0))
        grow = {"n": 0}

        def grow_sleep(s):
            fake_sleep(s)
            grow["n"] += 1
            if grow["n"] == 2:
                with open(p, "ab") as f:
                    for wall, pk in tick(7, 1005.5, 1020.5):
                        f.write(REC.pack(wall, len(pk)) + pk)
        code, msg, uid = run_start(p, 20, 120, fake_clock, grow_sleep)
        ok &= code == 0 and uid == 7 and grow["n"] == 2
        print("case start-only: live, the capture grows past the cutoff -> started:", code, msg, "uid", uid,
              f"after {grow['n']} sleeps")
        clock["t"] = 1000.0
        write([(990.0, pkt(1, 7, session()))] + tick(7, 991.0, 1030.0))           # a race session, no lights out
        code, msg, uid = run_start(p, 20, 120, fake_clock, fake_sleep)
        ok &= code == 2 and "no LGOT" in msg and clock["t"] >= 1120
        print("case start-only: race session with no LGOT -> exit 2 after max:", code, msg, "uid", uid)
        clock["t"] = 1000.0
        write([(990.0, pkt(1, 7, session(10))), (1000.0, lgot(7))] + tick(7, 1000.5, 1030.0))   # practice only
        code, msg, uid = run_start(p, 20, 120, fake_clock, fake_sleep)
        ok &= code == 2 and uid is None
        print("case start-only: a lights-out event outside a race session -> exit 2:", code, msg, "uid", uid)
        two_s = start7 + [(1060.0, pkt(1, 8, session())), (1070.0, lgot(8))] + tick(8, 1070.5, 1091.0)
        clock["t"] = 1000.0
        write(two_s)
        code, msg, uid = run_start(p, 20, 120, fake_clock, fake_sleep)
        ok &= code == 0 and uid == 7
        print("case start-only: two starts, no exclude -> started 7 (the first not excluded):", code, msg, "uid", uid)
        clock["t"] = 1000.0
        code, msg, uid = run_start(p, 20, 120, fake_clock, fake_sleep, exclude=frozenset({7}))
        ok &= code == 0 and uid == 8
        print("case start-only: two starts, exclude 7 -> started 8:", code, msg, "uid", uid)
        clock["t"] = 1000.0
        code, msg, uid = run_start(p, 20, 120, fake_clock, fake_sleep, exclude=frozenset({7, 8}))
        ok &= code == 2 and uid is None
        print("case start-only: two starts, exclude 7,8 -> exit 2:", code, msg, "uid", uid)
        clock["t"] = 1000.0
        write(start7 + [(1060.0, pkt(1, 8, session()))] + tick(8, 1060.5, 1100.0))   # restart 8 not at lights out yet
        code, msg, uid = run_start(p, 20, 120, fake_clock, fake_sleep, exclude=frozenset({7}))
        ok &= code == 2 and uid == 8 and "no LGOT" in msg
        print("case start-only: exclude 7, race 8 without its LGOT (7's packets don't count) -> exit 2:", code, msg, "uid", uid)
        clock["t"] = 1000.0
        write([(990.0, pkt(1, 7, session())), (1000.0, lgot(7))] + tick(7, 1000.5, 1005.0))
        calls["n"] = 0
        code, msg, uid = run_start(p, 20, 120, fake_clock, flag_on_third_sleep, stop=stop_check(flag, None))
        ok &= code == 5 and "pause flag" in msg and clock["t"] < 1010
        print("case start-only: pause flag -> stopped at once (5):", code, msg, "uid", uid)
        flag.unlink()
        clock["t"] = 1000.0
        code, msg, uid = run_start(p, 20, 120, fake_clock, fake_sleep, stop=stop_check(None, 4242, alive=lambda pid: False))
        ok &= code == 5 and "game exited" in msg
        print("case start-only: game gone -> stopped at once (5):", code, msg)
        clock["t"] = 1000.0
        code, msg, uid = run_start(Path(d) / "none.bin", 20, 120, fake_clock, fake_sleep)
        ok &= code == 3
        print("case start-only: no capture -> exit 3:", code, msg)
    if real is not None:
        # a finished multi-race capture: each call with the earlier uids excluded returns the next race, then exit 2
        uids, code, msg = [], None, ""
        rclock = {"t": 0.0}

        def rsleep(s):
            rclock["t"] += s
        for _ in range(25):
            code, msg, uid = run_start(real, 20, 5, lambda: rclock["t"], rsleep, exclude=frozenset(uids))
            if code != 0:
                break
            uids.append(uid)
        good = len(uids) >= 2 and len(set(uids)) == len(uids) and code == 2
        ok &= good
        print(f"case real capture {real}: {len(uids)} starts in order, then exit {code} ({msg})", "ok" if good else "WRONG")
    ok &= layout_ok()
    print("case layout:", f"LapData entry {LAP_SIZE} bytes, resultStatus at byte {RSTATUS_OFF}",
          "ok" if layout_ok() else f"WRONG (expected {EXPECT_LAP_SIZE} / {EXPECT_RSTATUS_OFF})")
    print("selftest", "ok" if ok else "FAILED", "| resultStatus offset", RSTATUS_OFF)
    return 0 if ok else 1


def main() -> int:
    a = sys.argv[1:]
    if "--selftest" in a:
        return selftest(Path(a[a.index("--real") + 1]) if "--real" in a else None)
    if "--bin" not in a:
        print(__doc__)
        return 3
    start_only = None
    if "--start-only" in a:
        try:
            start_only = float(a[a.index("--start-only") + 1])
        except (IndexError, ValueError):
            print("udp start wait: --start-only needs the cutoff in seconds (exit 3)")
            return 3
    if start_only is None and not layout_ok():   # never guess an offset: a wrong one could read lastLapTime's low byte and quit mid-race
        print(f"udp finish watch: LapData layout mismatch (entry {LAP_SIZE} bytes, resultStatus at {RSTATUS_OFF}; "
              f"expected {EXPECT_LAP_SIZE} / {EXPECT_RSTATUS_OFF}); not watching (exit 4)")
        return 4
    path = Path(a[a.index("--bin") + 1])
    max_s = float(a[a.index("--max-s") + 1]) if "--max-s" in a else (120.0 if start_only is not None else 900.0)
    after = float(a[a.index("--after-leader-s") + 1]) if "--after-leader-s" in a else 150.0
    exclude = frozenset()
    if "--exclude-uids" in a:
        try:
            exclude = frozenset(int(x) for x in a[a.index("--exclude-uids") + 1].split(",") if x.strip())
        except (IndexError, ValueError):
            print("udp finish watch: --exclude-uids needs a comma list of session uids (exit 3)")
            return 3
    stop_file = Path(a[a.index("--stop-file") + 1]) if "--stop-file" in a else None
    game_pid = int(a[a.index("--game-pid") + 1]) if "--game-pid" in a else None
    if start_only is not None:
        code, msg, uid = run_start(path, start_only, max_s, exclude=exclude, stop=stop_check(stop_file, game_pid))
        print(f"udp start wait: {msg} (exit {code})" + (f"; {len(exclude)} earlier race uid(s) excluded" if exclude else ""))
        if code == 0 and uid is not None:
            print(f"started uid {uid}")
        return code
    code, msg, uid = run(path, max_s, after, exclude=exclude, stop=stop_check(stop_file, game_pid))
    print(f"udp finish watch: {msg} (exit {code})" + (f"; {len(exclude)} earlier race uid(s) excluded" if exclude else ""))
    if code == 0 and uid is not None:
        print(f"finished uid {uid}")
    elif code == 1 and uid is not None:
        print(f"timeout uid {uid}")
    return code


if __name__ == "__main__":
    os.environ.setdefault("PYTHONUNBUFFERED", "1")
    sys.exit(main())
