#!/usr/bin/env python3
"""Follow a live udp_capture.py recording and return when the AI-only race is over (#134 ruling 4).

Usage:
    python -I tools/udp_finish_watch.py --bin <udp.bin> [--max-s 900] [--after-leader-s 150]
    python -I tools/udp_finish_watch.py --selftest

Reads the growing capture (records of <wall f64><length u16><packet>) from where it last stopped. In the race session
(Session packet type 15-17), from LapData: done when every active AI car (not the player car, header playerCarIndex;
resultStatus 2 or more seen) has resultStatus >= 3 (finished, DNF, DSQ, retired, ...). The player car is ignored: on the
spectator garage route it stays at 2 (active) in the garage.
Exit 0 all AI done; 1 timeout at the leader's finish + --after-leader-s (the first AI status 3) with AI still running;
2 --max-s passed with no finish (or no race session); 3 no capture file. Prints one summary line.
"""
from __future__ import annotations

import os
import struct
import sys
import time
from pathlib import Path

HEADER = struct.Struct("<HBBBBBQfIIBB")
LAP_SIZE = 57
RSTATUS_OFF = 0
REC = struct.Struct("<dH")


def _rstatus_offset() -> int:
    # resultStatus is field 26 of the LapData entry (tools/udp_parse.py LAP, L_RSTATUS)
    lap = struct.Struct("<IIHBHBHBHBfffBBBBBBBBBBBBBBBHHBfB")
    fmt = "<IIHBHBHBHBfffBBBBBBBBBBBBBBBHHBfB"[1:]
    return struct.calcsize("<" + fmt[:26]) if lap.size == LAP_SIZE else 0


RSTATUS_OFF = _rstatus_offset()


class Watch:
    def __init__(self):
        self.race_uid = None
        self.player = None
        self.status: dict[int, int] = {}
        self.leader_wall = None

    def feed(self, wall: float, pkt: bytes):
        if len(pkt) < HEADER.size:
            return
        h = HEADER.unpack_from(pkt, 0)
        pid, uid, body = h[5], h[6], pkt[HEADER.size:]
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


def run(path: Path, max_s: float, after_leader_s: float, clock=time.time, sleep=time.sleep) -> tuple[int, str]:
    t0 = clock()
    while not path.exists():
        if clock() - t0 > 30:
            return 3, f"no capture at {path}"
        sleep(1)
    w, pos, buf = Watch(), 0, b""
    while True:
        with open(path, "rb") as f:
            f.seek(pos)
            chunk = f.read()
        pos += len(chunk)
        buf += chunk
        i = 0
        while i + REC.size <= len(buf):
            wall, n = REC.unpack_from(buf, i)
            if i + REC.size + n > len(buf):
                break
            w.feed(wall, buf[i + REC.size:i + REC.size + n])
            i += REC.size + n
        buf = buf[i:]
        n_ai = len(w.status)
        fin = sum(1 for s in w.status.values() if s == 3)
        if w.done():
            return 0, f"all {n_ai} AI cars done ({fin} finished)"
        now = clock()
        if w.leader_wall is not None and now - w.leader_wall > after_leader_s:
            return 1, f"timeout {after_leader_s:.0f} s after the leader's finish: {fin} of {n_ai} AI cars finished"
        if now - t0 > max_s:
            return 2, f"max {max_s:.0f} s with no finish ({fin} of {n_ai} AI cars finished)"
        sleep(2)


def selftest() -> int:
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
        code, msg = run(p, 900, 150, fake_clock, fake_sleep)
        ok &= code == 0
        print("case all AI done:", code, msg)
        one_left = [3] * 18 + [2] + [2]               # one AI car still running, the player active
        clock["t"] = 1000.0
        write([(1000.0, pkt(1, 7, session())), (1001.0, pkt(2, 7, lapdata([2] * 20))), (1000.5, pkt(2, 7, lapdata(one_left)))])
        code, msg = run(p, 900, 150, fake_clock, fake_sleep)
        ok &= code == 1
        print("case timeout after the leader:", code, msg)
        clock["t"] = 1000.0
        write([(1000.0, pkt(1, 7, session(10))), (1001.0, pkt(2, 7, lapdata([2] * 20)))])   # practice only
        code, msg = run(p, 60, 150, fake_clock, fake_sleep)
        ok &= code == 2
        print("case no race session:", code, msg)
        dnf = [3] * 17 + [4, 7] + [2]                 # two AI DNF/DSQ count as done
        clock["t"] = 1000.0
        write([(1000.0, pkt(1, 7, session())), (1001.0, pkt(2, 7, lapdata(dnf)))])
        code, msg = run(p, 900, 150, fake_clock, fake_sleep)
        ok &= code == 0
        print("case DNFs done:", code, msg)
    print("selftest", "ok" if ok else "FAILED", "| resultStatus offset", RSTATUS_OFF)
    return 0 if ok else 1


def main() -> int:
    a = sys.argv[1:]
    if "--selftest" in a:
        return selftest()
    if "--bin" not in a:
        print(__doc__)
        return 3
    path = Path(a[a.index("--bin") + 1])
    max_s = float(a[a.index("--max-s") + 1]) if "--max-s" in a else 900.0
    after = float(a[a.index("--after-leader-s") + 1]) if "--after-leader-s" in a else 150.0
    code, msg = run(path, max_s, after)
    print(f"udp finish watch: {msg} (exit {code})")
    return code


if __name__ == "__main__":
    os.environ.setdefault("PYTHONUNBUFFERED", "1")
    sys.exit(main())
