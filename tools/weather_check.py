#!/usr/bin/env python3
"""Weather of a race session, from a tools/udp_capture.py recording (supervisor ruling 2026-11-15, after B-0016).

Usage:
    python -I tools/weather_check.py <udp.bin> [--out <race folder>] [--locked]   # writes <race>/weather.txt
    python -I tools/weather_check.py --selftest

Reads every Session packet of the race session (session type 15-17):
- the weather byte (body offset 0): 0 clear, 1 light cloud, 2 overcast = dry; 3 light rain, 4 heavy rain, 5 storm = wet;
- the forecast samples (body offset 126: their count; from 127, 8 bytes each: sessionType, timeOffset, weather,
  trackTemp, trackTempChange, airTemp, airTempChange, rainPercentage), for the race session's samples.
  Offsets checked on B-0016 race 7 (storm: weather 5, rain 90) and 13 dry races (rain 3-23, never 0) (#118).
Without --locked (B-0015's rule, #100): "weather: DRY" or "weather: WET". Exit 0 dry, 1 wet, 2 no race session.
With --locked (#118, the dry-weather lock, second amendment 2026-11-16, from #134 on): "weather: LOCKED" only if every
weather byte is 0 AND every race forecast sample has weather 0 AND rainPercentage <= RAIN_MAX (5) in every sample, in
any mix of values. Rationale: rain% is a forecast probability, and under Quick Weather = Clear (Dry) on build 26566308
it floors at 3-4 (a flat 3 in the pilot DSQ race; 3 and 4 in #131), while Dynamic gave 3-90 (supervisor). The first
amendment ("one constant value <= 3") applied to the pilot and #131 only.
Otherwise "weather: NOT LOCKED (...)" or "weather: WET". Exit 0 locked, 1 not, 2 no race session.
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
FC_COUNT, FC_START, FC_SIZE = 126, 127, 8
RAIN_MAX = 5   # the most rain% a LOCKED race may forecast; Clear (Dry) floors at 3-4 (#118, second amendment)


def race_weather(packets) -> tuple[Counter, Counter, Counter]:
    """Counts of the weather byte, and of the race forecast samples' weather and rainPercentage."""
    w: Counter = Counter()
    fw: Counter = Counter()
    fr: Counter = Counter()
    for p in packets:
        if len(p) < u.HEADER.size + 7:
            continue
        if u.HEADER.unpack_from(p, 0)[5] != 1:   # packet id 1 = Session
            continue
        body = p[u.HEADER.size:]
        if body[6] not in RACE_TYPES:
            continue
        w[body[0]] += 1
        if len(body) > FC_COUNT:
            n = min(body[FC_COUNT], 64)
            for i in range(n):
                o = FC_START + FC_SIZE * i
                if o + FC_SIZE > len(body):
                    break
                if body[o] in RACE_TYPES:
                    fw[body[o + 2]] += 1
                    fr[body[o + 7]] += 1
    return w, fw, fr


def verdict(w: Counter) -> str:
    if not w:
        return "NONE"
    return "WET" if any(k in WET for k in w) else "DRY"


def locked_verdict(w: Counter, fw: Counter, fr: Counter) -> str:
    if not w:
        return "NONE"
    if any(k in WET for k in w):
        return "WET"
    rain_ok = bool(fr) and max(fr) <= RAIN_MAX   # every sample at most RAIN_MAX, any mix
    if set(w) == {0} and fw and set(fw) == {0} and rain_ok:
        return "LOCKED"
    why = []
    if set(w) != {0}:
        why.append("weather byte " + ",".join(map(str, sorted(w))))
    if not fw:
        why.append("no forecast samples")
    else:
        if set(fw) != {0}:
            why.append("forecast weather " + ",".join(map(str, sorted(fw))))
        if fr and max(fr) > RAIN_MAX:
            why.append(f"rain% up to {max(fr)}, above {RAIN_MAX}")
    return "NOT LOCKED (" + "; ".join(why) + ")"


def selftest() -> int:
    def pkt(weather: int, stype: int, pid: int = 1, fc=((15, 0, 0, 0),)) -> bytes:
        head = u.HEADER.pack(2026, 25, 1, 26, 1, pid, 1, 0.0, 0, 0, 19, 255)
        body = bytearray(bytes([weather, 30, 20, 5]) + struct.pack("<H", 4318) + bytes([stype, 17]) + bytes(640))
        body[FC_COUNT] = len(fc)
        for i, (st, off, wx, rain) in enumerate(fc):
            o = FC_START + FC_SIZE * i
            body[o:o + FC_SIZE] = bytes([st, off, wx, 30, 0, 20, 0, rain])
        return head + bytes(body)
    dry = race_weather([pkt(2, 15, fc=((15, 0, 2, 20),))] * 5 + [pkt(5, 10)])   # a wet practice doesn't count
    wet = race_weather([pkt(0, 15)] * 5 + [pkt(3, 15)])                          # one packet of light rain makes it wet
    other = race_weather([pkt(4, 15, pid=2)])                                     # not a Session packet
    lock = race_weather([pkt(0, 15, fc=((15, 0, 0, 0), (15, 5, 0, 0), (10, 0, 2, 40)))] * 5)   # practice samples ignored
    floor = race_weather([pkt(0, 15, fc=((15, 0, 0, 3), (15, 5, 0, 3)))] * 5)     # a flat 3% (Clear (Dry)): locked
    mix34 = race_weather([pkt(0, 15, fc=((15, 0, 0, 3), (15, 5, 0, 4)))] * 5)     # 3 and 4 mixed (#131): locked
    six = race_weather([pkt(0, 15, fc=((15, 0, 0, 3), (15, 5, 0, 6)))] * 5)       # any 6%: not locked
    cloud = race_weather([pkt(0, 15, fc=((15, 0, 0, 3), (15, 5, 1, 3)))] * 5)     # forecast weather 1 anywhere: not locked
    cloud_now = race_weather([pkt(0, 15, fc=((15, 0, 0, 3),))] * 4 + [pkt(1, 15, fc=((15, 0, 0, 3),))])   # weather byte 1
    ok = (verdict(dry[0]) == "DRY" and verdict(wet[0]) == "WET" and verdict(other[0]) == "NONE"
          and locked_verdict(*lock) == "LOCKED" and locked_verdict(*floor) == "LOCKED"
          and locked_verdict(*mix34) == "LOCKED" and locked_verdict(*six).startswith("NOT LOCKED")
          and locked_verdict(*cloud).startswith("NOT LOCKED") and locked_verdict(*cloud_now).startswith("NOT LOCKED")
          and locked_verdict(*dry).startswith("NOT LOCKED") and locked_verdict(*wet) == "WET")
    print("selftest", "ok" if ok else "FAILED", locked_verdict(*mix34), "|", locked_verdict(*six), "|",
          locked_verdict(*cloud), "|", locked_verdict(*cloud_now), "|", locked_verdict(*dry))
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
    locked = "--locked" in args
    args = [a for a in args if a != "--locked"]
    if len(args) != 1:
        print(__doc__)
        return 2
    w, fw, fr = race_weather(p for _, p in u.records(Path(args[0])))
    v = locked_verdict(w, fw, fr) if locked else verdict(w)
    lines = [f"weather: {v}"] + [f"  {k} {NAMES.get(k, '?')}: {n} session packets" for k, n in sorted(w.items())]
    lines.append("  forecast (race samples): weather " + str(dict(sorted(fw.items()))) + ", rain% " + str(dict(sorted(fr.items()))))
    print("\n".join(lines))
    if out:
        (out / "weather.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    if locked:
        return 0 if v == "LOCKED" else (2 if v == "NONE" else 1)
    return {"DRY": 0, "WET": 1, "NONE": 2}[v]


if __name__ == "__main__":
    sys.exit(main())
