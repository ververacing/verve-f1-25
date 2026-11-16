#!/usr/bin/env python3
"""Weather of a race session, from a tools/udp_capture.py recording (supervisor ruling 2026-11-15, after B-0016).

Usage:
    python -I tools/weather_check.py <udp.bin> [--out <race folder>]   # prints and writes <race>/weather.txt
    python -I tools/weather_check.py --selftest

Reads the weather byte (the first byte of the Session packet body, F1 UDP spec) of every Session packet of the race
session (session type 15-17). 0 clear, 1 light cloud, 2 overcast = dry; 3 light rain, 4 heavy rain, 5 storm = wet.
weather.txt: "weather: DRY" or "weather: WET", then the counts per weather code. Exit 0 dry, 1 wet, 2 no race session.
"""
from __future__ import annotations

import struct
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import udp_parse as u  # noqa: E402

RACE_TYPES = {15, 16, 17}
WET = {3, 4, 5}
NAMES = {0: "clear", 1: "light cloud", 2: "overcast", 3: "light rain", 4: "heavy rain", 5: "storm"}


def race_weather(packets) -> Counter:
    """packets: iterable of raw packets. Counts the weather byte of race-session Session packets."""
    w: Counter = Counter()
    for p in packets:
        if len(p) < u.HEADER.size + 7:
            continue
        if u.HEADER.unpack_from(p, 0)[5] != 1:   # packet id 1 = Session
            continue
        body = p[u.HEADER.size:]
        if body[6] in RACE_TYPES:
            w[body[0]] += 1
    return w


def verdict(w: Counter) -> str:
    if not w:
        return "NONE"
    return "WET" if any(k in WET for k in w) else "DRY"


def selftest() -> int:
    def pkt(weather: int, stype: int, pid: int = 1) -> bytes:
        head = u.HEADER.pack(2026, 25, 1, 26, 1, pid, 1, 0.0, 0, 0, 19, 255)
        body = bytes([weather, 30, 20, 5]) + struct.pack("<H", 4318) + bytes([stype, 17]) + bytes(20)
        return head + body
    dry = race_weather([pkt(2, 15)] * 5 + [pkt(5, 10)])           # a wet practice session doesn't count
    wet = race_weather([pkt(0, 15)] * 5 + [pkt(3, 15)])           # one packet of light rain makes it wet
    other = race_weather([pkt(4, 15, pid=2)])                     # not a Session packet
    ok = verdict(dry) == "DRY" and verdict(wet) == "WET" and verdict(other) == "NONE"
    print("selftest", "ok" if ok else "FAILED", dict(dry), dict(wet), dict(other))
    return 0 if ok else 1


def main() -> int:
    args = sys.argv[1:]
    if "--selftest" in args:
        return selftest()
    out = None
    if "--out" in args:
        i = args.index("--out")
        out = Path(args[i + 1])
        del args[i:i + 2]
    if len(args) != 1:
        print(__doc__)
        return 2
    w = race_weather(p for _, p in u.records(Path(args[0])))
    v = verdict(w)
    lines = [f"weather: {v}"] + [f"  {k} {NAMES.get(k, '?')}: {n} session packets" for k, n in sorted(w.items())]
    print("\n".join(lines))
    if out:
        (out / "weather.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {"DRY": 0, "WET": 1, "NONE": 2}[v]


if __name__ == "__main__":
    sys.exit(main())
