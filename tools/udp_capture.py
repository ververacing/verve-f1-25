#!/usr/bin/env python3
"""Record F1 25's UDP telemetry to a raw file, for tools/udp_participants.py and later #4 analysis.

Usage:
    python3 tools/udp_capture.py --out udp.bin --seconds 2400
    python3 tools/udp_capture.py --out udp.bin --stop-file stop.flag   # ends when the file appears

The game sends to 127.0.0.1:20777 when <udp enabled="true" ...> is set in
Documents/My Games/F1 25/hardwaresettings/hardware_settings_config.xml (docs/harness.md).

Record format, repeated: f64 wall-clock seconds, u16 payload length, payload bytes (little-endian).
"""
from __future__ import annotations

import argparse
import socket
import struct
import sys
import time
from pathlib import Path


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=20777)
    ap.add_argument("--seconds", type=float, default=3600.0, help="stop after this long")
    ap.add_argument("--stop-file", type=Path, help="stop as soon as this file exists")
    args = ap.parse_args()

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind((args.host, args.port))
    sock.settimeout(0.5)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    end = time.time() + args.seconds
    n = 0
    with args.out.open("wb") as f:
        print(f"listening on {args.host}:{args.port} -> {args.out}", flush=True)
        while time.time() < end and not (args.stop_file and args.stop_file.exists()):
            try:
                data, _ = sock.recvfrom(4096)
            except socket.timeout:
                continue
            f.write(struct.pack("<dH", time.time(), len(data)))
            f.write(data)
            n += 1
            if n % 5000 == 0:
                f.flush()
                print(f"{n} packets", flush=True)
    print(f"done: {n} packets", flush=True)


if __name__ == "__main__":
    sys.exit(main())
