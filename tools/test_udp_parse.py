"""Checks for tools/udp_parse.py on synthetic packets. Run: python3 tools/test_udp_parse.py (exit 0 = all pass)."""
import struct
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import udp_parse as u  # noqa: E402

ACCOUNT = b"SECRET_ACCOUNT"


def header(fmt: int, pid: int, player: int, player2: int = 255) -> bytes:
    return u.HEADER.pack(fmt, 25, 1, 26, 1, pid, 42, 1.0, 1, 1, player, player2)


def participants(fmt: int, rows) -> bytes:
    lay = u.LAYOUTS[fmt]
    body = bytes([len(rows)])
    for c in range(lay["cars"]):
        ai, drv, name = rows[c] if c < len(rows) else (1, 0, b"")
        rec = lay["part"].pack(ai, drv, c, 3, 0, 10 + c, 1, name.ljust(32, b"\0"))
        body += rec.ljust(lay["part_size"], b"\0")
    return body


def capture(packets) -> Path:
    f = Path(tempfile.mkdtemp()) / "t.bin"
    with f.open("wb") as w:
        for i, p in enumerate(packets):
            w.write(struct.pack("<dH", float(i), len(p)) + p)
    return f


def names(fmt: int, player: int, player2: int, rows):
    s = u.parse(capture([header(fmt, 4, player, player2) + participants(fmt, rows)]), [])
    return [p["name"] for p in s[42]["participants"][:len(rows)]]


failed = 0
cases = [
    # the player's slot reports aiControlled = 1 (benchmark / ai_drives_player): still blanked
    ("2026 player slot ai=1", 2026, 0, 255, [(1, 7, ACCOUNT), (1, 8, b"Max Verstappen")], ["player", "Max Verstappen"]),
    ("2025 player slot ai=1", 2025, 1, 255, [(1, 7, b"Lando Norris"), (1, 8, ACCOUNT)], ["Lando Norris", "player"]),
    ("secondary player", 2026, 0, 1, [(1, 7, ACCOUNT), (1, 8, ACCOUNT), (1, 9, b"Oscar Piastri")],
     ["player", "player", "Oscar Piastri"]),
    ("ai=0 elsewhere", 2026, 0, 255, [(1, 7, b"A"), (0, 8, ACCOUNT)], ["player", "player"]),
    ("unknown driverId", 2026, 5, 255, [(1, 65535, ACCOUNT), (1, 8, b"George Russell")], ["player", "George Russell"]),
]
for label, fmt, p1, p2, rows, want in cases:
    got = names(fmt, p1, p2, rows)
    ok = got == want and all(ACCOUNT.decode() not in n for n in got)
    failed += not ok
    print(f"{'ok  ' if ok else 'FAIL'} {label}: {got}")

def damage_entry(size: int, fl: int, fr: int, rear: int) -> bytes:
    e = bytearray(size)
    off = u.DAMAGE_PART_OFF[size]
    e[off:off + 3] = bytes([fl, fr, rear])
    return bytes(e)


def damage_packet(fmt: int, size: int, car1) -> bytes:
    n = u.LAYOUTS[fmt]["cars"]
    return header(fmt, 10, 0) + b"".join(damage_entry(size, *(car1 if c == 1 else (0, 0, 0))) for c in range(n))


for fmt in (2025, 2026):
    for size in (46, 42):
        pk = [damage_packet(fmt, size, (0, 0, 0)), damage_packet(fmt, size, (0, 0, 0)),
              damage_packet(fmt, size, (12, 0, 0)), damage_packet(fmt, size, (12, 0, 30))]
        s = u.parse(capture(pk), [])[42]
        car1 = [rec[:3] for _, c, rec in s["damage"] if c == 1]
        ok = car1 == [(0, 0, 0), (12, 0, 0), (12, 0, 30)] and not s["bad_sizes"]
        failed += not ok
        print(f"{'ok  ' if ok else 'FAIL'} car damage {fmt} entry {size}: car 1 changes {car1}")
bad = u.parse(capture([header(2026, 10, 0) + bytes(24 * 44)]), [])[42]
ok = "car_damage" in bad["bad_sizes"] and not bad["damage"]
failed += not ok
print(f"{'ok  ' if ok else 'FAIL'} car damage wrong entry size reported: {bad['bad_sizes']}")
sys.exit(1 if failed else 0)
