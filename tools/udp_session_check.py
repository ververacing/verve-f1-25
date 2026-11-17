#!/usr/bin/env python3
"""At race 1's lights out, check the live capture's Session packet: AI difficulty, track and weather (V-1 guard).

Usage:
    python -I tools/udp_session_check.py --bin <udp.bin> --difficulty 100 --track 17 --weather 0 [--max-s 90]
        [--lgot-wait-s 60] [--exclude-uids a,b] [--stop-file <pause flag>] [--game-pid <pid>]
    python -I tools/udp_session_check.py --selftest [--real <a finished capture>]

Why (supervisor's ruling, 2026-11-17): V-1 launch 6 ran all four races at AI difficulty 99, found only after the whole
35-minute launch. This reads the settings at race 1's lights out instead, so a wrong launch ends at once
(`@sessioncheck` in tools/sandbox_shell.ps1; tools/v1_run.ps1 reruns that launch once). It changes no measure or rule.

Follows the growing capture (udp_capture.py records <wall f64><length u16><packet>) the way tools/udp_finish_watch.py
does. Takes the newest RACE session (Session packet sessionType 15-17) whose uid is not in --exclude-uids and reads
its Session packets: the first one at or after that session's lights-out event (LGOT) when there is one; if no LGOT
comes within --lgot-wait-s of the race session appearing, the latest Session packet seen. Session packets whose AI
difficulty reads 0 are skipped (the first one or two of a session read 0; tools/udp_parse.py ignores them too).
The offsets are udp_parse's S_* constants (one source of truth).

Prints one verdict line, then a `source:` line:
    exit 0  session ok uid <uid>: difficulty D track T weather W
    exit 6  invalid: difficulty D[, track T][, weather W] (uid <uid>)     (every field that doesn't match)
    exit 2  no race session within --max-s, or no Session packet with the difficulty set by the LGOT wait
    exit 3  no capture file within 30 s
    exit 4  the Session layout doesn't check out (udp_parse's offsets aren't the expected ones, or a race Session
            packet is too short to hold the AI difficulty); nothing is judged
    exit 5  stopped: the pause flag (--stop-file) appeared or the game (--game-pid) exited. The liveness check is the
            watcher's read-only one (OpenProcess + GetExitCodeProcess, never os.kill)
"""
from __future__ import annotations

import argparse
import os
import struct
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import udp_parse as u  # noqa: E402   the Session offsets
import udp_finish_watch as fw  # noqa: E402   the read-only stop check (pause flag, game pid)

HEADER = u.HEADER
REC = struct.Struct("<dH")
RACE_TYPES = (15, 16, 17)
CHUNK = 4 << 20   # read a big backlog (the menu part of a capture) in pieces, not all at once
# F1 25 spec (formats 2025 and 2026); the difficulty byte checked on the menu's 19 (2026-11-03) and on the V-1
# Austria discovery's 100 (2026-11-16, format 2026)
EXPECT = {"S_WEATHER": 0, "S_TYPE": 6, "S_TRACK": 7, "S_AI_DIFFICULTY": 640}


def layout_ok() -> bool:
    return all(getattr(u, k, None) == v for k, v in EXPECT.items())


class Check:
    def __init__(self, exclude: frozenset = frozenset()):
        self.exclude = exclude
        self.races: dict[int, dict] = {}   # uid -> {"at_lgot": (d, t, w, stime) | None, "latest": ... | None}
        self.order: list[int] = []         # race uids in the order they first appeared
        self.lgot: set[int] = set()
        self.short: int | None = None      # the body length of a race Session packet too short for the difficulty

    def feed(self, pkt: bytes):
        if len(pkt) < HEADER.size:
            return
        h = HEADER.unpack_from(pkt, 0)
        pid, uid = h[5], h[6]
        if uid in self.exclude or pid not in (1, 3):
            return
        body = pkt[HEADER.size:]
        if pid == 3:
            if body[:4] == b"LGOT":
                self.lgot.add(uid)
            return
        if len(body) <= u.S_TRACK or body[u.S_TYPE] not in RACE_TYPES:
            return
        if len(body) <= u.S_AI_DIFFICULTY:
            self.short = len(body)
            return
        r = self.races.get(uid)
        if r is None:
            r = self.races[uid] = {"at_lgot": None, "latest": None}
            self.order.append(uid)
        d = body[u.S_AI_DIFFICULTY]
        if not d:
            return
        vals = (d, struct.unpack_from("<b", body, u.S_TRACK)[0], body[u.S_WEATHER], round(h[7], 1))
        r["latest"] = vals
        if uid in self.lgot and r["at_lgot"] is None:
            r["at_lgot"] = vals

    def newest(self):
        return self.order[-1] if self.order else None


def verdict(uid: int, vals: tuple, want: tuple, source: str) -> tuple[int, str, str, int]:
    d, t, w, st = vals
    bad = [f"{name} {got}" for name, got, exp in (("difficulty", d, want[0]), ("track", t, want[1]), ("weather", w, want[2]))
           if got != exp]
    src = f"source: {source} (session time {st} s)"
    if bad:
        return 6, f"invalid: {', '.join(bad)} (uid {uid})", src, uid
    return 0, f"session ok uid {uid}: difficulty {d} track {t} weather {w}", src, uid


def run(path: Path, want: tuple, max_s: float = 90, lgot_wait_s: float = 60, clock=time.time, sleep=time.sleep,
        exclude: frozenset = frozenset(), stop=lambda: None, chunk: int = CHUNK) -> tuple[int, str, str, int | None]:
    """(exit code, verdict line, source line, uid or None). want = (difficulty, track, weather)."""
    t0 = clock()
    while not path.exists():
        why = stop()
        if why:
            return 5, f"stopped: {why}", "source: none", None
        if clock() - t0 > 30:
            return 3, f"no capture at {path}", "source: none", None
        sleep(1)
    c, pos, buf = Check(exclude), 0, b""
    seen: dict[int, float] = {}   # race uid -> when this check first saw it (its LGOT wait starts there)
    while True:
        with open(path, "rb") as f:   # read-only
            f.seek(pos)
            while True:
                piece = f.read(chunk)
                if not piece:
                    break
                pos += len(piece)
                buf += piece
                i = 0
                while i + REC.size <= len(buf):
                    _, n = REC.unpack_from(buf, i)
                    if i + REC.size + n > len(buf):
                        break
                    c.feed(buf[i + REC.size:i + REC.size + n])
                    i += REC.size + n
                buf = buf[i:]
        if c.short is not None:
            return 4, (f"Session layout: a race Session packet body is {c.short} bytes, too short for the AI difficulty "
                       f"at byte {u.S_AI_DIFFICULTY}; not judged"), "source: none", c.newest()
        now = clock()
        why = stop()
        if why:
            return 5, f"stopped: {why}", "source: none", c.newest()
        uid = c.newest()
        if uid is not None:
            seen.setdefault(uid, now)
            r = c.races[uid]
            if r["at_lgot"]:
                return verdict(uid, r["at_lgot"], want, "the first Session packet at or after lights out (LGOT)")
            if now - seen[uid] >= lgot_wait_s:
                if r["latest"]:
                    return verdict(uid, r["latest"], want, f"no lights out within {lgot_wait_s:.0f} s: the latest Session packet")
                return 2, (f"race session uid {uid} but no Session packet with the AI difficulty set within "
                           f"{lgot_wait_s:.0f} s"), "source: none", uid
        elif now - t0 > max_s:
            return 2, f"no race session within {max_s:.0f} s" + (f" ({len(exclude)} uid(s) excluded)" if exclude else ""), \
                "source: none", None
        sleep(1)


def selftest(real: Path | None) -> int:
    import tempfile

    def pkt(pid, uid, body):
        return HEADER.pack(2026, 25, 1, 0, 1, pid, uid, 0.0, 0, 0, 19, 255) + body

    def sess(uid, diff=100, track=17, weather=0, stype=15, size=868):
        b = bytearray(size)
        b[u.S_WEATHER], b[u.S_TYPE] = weather, stype
        struct.pack_into("<b", b, u.S_TRACK, track)
        if size > u.S_AI_DIFFICULTY:
            b[u.S_AI_DIFFICULTY] = diff
        return pkt(1, uid, bytes(b))

    def lgot(uid):
        return pkt(3, uid, b"LGOT" + bytes(12))

    def race(uid, diff=100, track=17, weather=0, before=None):
        """SSTA-like start: two zero-difficulty packets, a few before lights out, LGOT, then the race's packets."""
        b = before if before is not None else diff
        return ([sess(uid, 0, track, weather)] * 2 + [sess(uid, b, track, weather)] * 3 + [lgot(uid)]
                + [sess(uid, diff, track, weather)] * 3)
    ok = True
    want = (100, 17, 0)
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "udp.bin"

        def write(pkts, mode="wb"):
            with open(p, mode) as f:
                for k, pk in enumerate(pkts):
                    f.write(REC.pack(1000.0 + k, len(pk)) + pk)
        clock = {"t": 1000.0}
        fake_clock = lambda: clock["t"]   # noqa: E731

        def fake_sleep(s):
            clock["t"] += s

        def case(name, expect_code, expect_text, **kw):
            nonlocal ok
            clock["t"] = 1000.0
            code, line, src, uid = run(p, kw.pop("want", want), clock=fake_clock, sleep=kw.pop("sleep", fake_sleep), **kw)
            good = code == expect_code and expect_text in line
            ok &= good
            print(f"case {name}: exit {code} | {line} | {src}" + ("" if good else f"   <-- WRONG (expected exit {expect_code}, '{expect_text}')"))
            return code, line, src, uid
        write([pkt(1, 0, bytes(868))] + race(7))
        case("match", 0, "session ok uid 7: difficulty 100 track 17 weather 0")
        write(race(7, diff=99))
        case("difficulty 99", 6, "invalid: difficulty 99 (uid 7)")
        write(race(7, track=9))
        case("wrong track", 6, "invalid: track 9 (uid 7)")
        write(race(7, weather=1))
        case("weather 1", 6, "invalid: weather 1 (uid 7)")
        write(race(7, diff=99, weather=1))
        case("difficulty and weather, joined", 6, "invalid: difficulty 99, weather 1 (uid 7)")
        write(race(7, diff=100, before=99))
        _, _, src, _ = case("99 before lights out, 100 after -> the LGOT packet wins", 0, "difficulty 100")
        ok &= "LGOT" in src
        write(race(7, diff=99) + race(8))
        case("excluded old uid 7 (99) then new uid 8", 0, "session ok uid 8", exclude=frozenset({7}))
        case("old uid 7 and new uid 8, no exclude -> the newest (8)", 0, "session ok uid 8")
        write(race(7))
        case("only the excluded uid -> no race session", 2, "no race session within 90 s", exclude=frozenset({7}))
        write([pkt(1, 0, bytes(868))] + [sess(5, stype=10)] * 5 + [lgot(5)] + [sess(5, stype=10)])   # practice only
        case("no session (practice only)", 2, "no race session within 90 s")
        write([sess(7, 0)] * 2 + [sess(7, 99)] * 4)                                 # no LGOT at all
        _, _, src, _ = case("no lights out -> the latest Session packet after the wait", 6, "invalid: difficulty 99")
        ok &= "no lights out within 60 s" in src
        write([sess(7, 0)] * 6)
        case("difficulty never set -> unverified", 2, "no Session packet with the AI difficulty set")
        write([sess(7, size=600)])
        case("Session packet too short -> layout", 4, "Session layout")
        # live following: race 7 appears without LGOT; the lights go out (and 99 is read) only after two more reads
        write([pkt(1, 0, bytes(868))] + [sess(7, 0)] * 2 + [sess(7, 100)] * 2)
        grow = {"n": 0}

        def grow_sleep(s):
            fake_sleep(s)
            grow["n"] += 1
            if grow["n"] == 2:
                write([lgot(7), sess(7, 99)], mode="ab")
        case("live: lights out after two reads -> 99", 6, "invalid: difficulty 99", sleep=grow_sleep)
        ok &= grow["n"] == 2
        # the stop flag (a PAUSE) and the game gone: exit 5 at once
        flag = Path(d) / "paused.txt"
        write([pkt(1, 0, bytes(868))])
        sl = {"n": 0}

        def flag_sleep(s):
            fake_sleep(s)
            sl["n"] += 1
            if sl["n"] == 3:
                flag.write_text("PAUSE")
        case("stop flag mid-wait", 5, "stopped: pause flag", sleep=flag_sleep, stop=fw.stop_check(flag, None))
        ok &= clock["t"] < 1010
        flag.unlink()
        case("game gone", 5, "stopped: game exited", stop=fw.stop_check(None, 4242, alive=lambda pid: False))
        write(race(7))
        case("flag absent, game alive -> normal check", 0, "session ok uid 7", stop=fw.stop_check(flag, 4242, alive=lambda pid: True))
    lay = layout_ok()
    ok &= lay
    print("case layout:", ", ".join(f"{k}={getattr(u, k, None)}" for k in EXPECT), "ok" if lay else f"WRONG (expected {EXPECT})")
    if real is not None and real.exists():
        # the V-1 Austria discovery capture (stock, 2 race uids at difficulty 100, track 17, weather 0); read-only
        clock["t"] = 0.0
        code1, line1, src1, uid1 = run(real, want, clock=fake_clock, sleep=fake_sleep)
        print(f"case real capture, newest uid: exit {code1} | {line1} | {src1}")
        code2, line2, src2, uid2 = run(real, want, clock=fake_clock, sleep=fake_sleep,
                                       exclude=frozenset({uid1}) if uid1 is not None else frozenset())
        print(f"case real capture, that uid excluded: exit {code2} | {line2} | {src2}")
        code3, line3, _, _ = run(real, want, clock=fake_clock, sleep=fake_sleep, exclude=frozenset({x for x in (uid1, uid2) if x is not None}))
        print(f"case real capture, both excluded: exit {code3} | {line3}")
        good = code1 == 0 and code2 == 0 and uid1 != uid2 and "LGOT" in src1 and "LGOT" in src2 and code3 == 2
        ok &= good
        print("case real capture:", "ok (difficulty 100, track 17, weather 0 on both uids, at lights out)" if good else "WRONG")
    else:
        print("case real capture: skipped (not present)" + (f": {real}" if real else ""))
    print("selftest", "ok" if ok else "FAILED")
    return 0 if ok else 1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--real", type=Path, default=Path(__file__).resolve().parent.parent / "runs" / "2026-11-16-V1-austria-disc"
                    / "race_1" / "raw" / "udp.bin", help="selftest: a finished capture to check read-only")
    ap.add_argument("--bin", type=Path)
    ap.add_argument("--difficulty", type=int)
    ap.add_argument("--track", type=int)
    ap.add_argument("--weather", type=int)
    ap.add_argument("--max-s", type=float, default=90.0)
    ap.add_argument("--lgot-wait-s", type=float, default=60.0)
    ap.add_argument("--exclude-uids", default="")
    ap.add_argument("--stop-file", type=Path)
    ap.add_argument("--game-pid", type=int)
    a = ap.parse_args()
    if a.selftest:
        return selftest(a.real)
    if a.bin is None or a.difficulty is None or a.track is None or a.weather is None:
        print("udp session check: --bin, --difficulty, --track and --weather are required (exit 3)")
        return 3
    if not layout_ok():   # never guess an offset
        print("udp session check: Session layout mismatch (udp_parse " + ", ".join(f"{k}={getattr(u, k, None)}" for k in EXPECT)
              + f"; expected {EXPECT}); not judged (exit 4)")
        return 4
    try:
        exclude = frozenset(int(x) for x in a.exclude_uids.split(",") if x.strip())
    except ValueError:
        print("udp session check: --exclude-uids needs a comma list of session uids (exit 3)")
        return 3
    code, line, src, _ = run(a.bin, (a.difficulty, a.track, a.weather), a.max_s, a.lgot_wait_s, exclude=exclude,
                             stop=fw.stop_check(a.stop_file, a.game_pid))
    print(line)
    print(src + f" (exit {code})" + (f"; {len(exclude)} earlier race uid(s) excluded" if exclude else ""))
    return code


if __name__ == "__main__":
    os.environ.setdefault("PYTHONUNBUFFERED", "1")
    sys.exit(main())
