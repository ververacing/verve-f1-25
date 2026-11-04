"""Build B-0014's two addons (#71) from the seeded draw. Reproducible: same seed, same roster.

Usage:
    python -I tools/b0014_make.py

Pool: every AI driver except McLaren, Ferrari, Red Bull and Aston Martin. Draw 8 with seed 14014, split 4/4 into G1
and G2. verve.b0014a: G1 aggression 1.0, G2 0.05. verve.b0014b: swapped. 8 ops each, row key only, ratings stock.
"""
from __future__ import annotations

import json
import random
from pathlib import Path

SEED = 14014
KEY = "driver_characteristics.aggression"
# in list order, so the draw doesn't depend on anything but the seed
POOL = ["george_russell", "andrea-kimi_antonelli", "alex_albon", "carlos_sainz-jr", "pierre_gasly", "franco_colapinto",
        "esteban_ocon", "oliver_bearman", "liam_lawson", "isack_hadjar", "nico_hulkenberg", "gabriel_bortoleto"]
HIGH, LOW = "1.0", "0.05"
ROOT = Path(__file__).resolve().parent.parent / "harness" / "addons"


def draw() -> tuple[list[str], list[str]]:
    rng = random.Random(SEED)
    chosen = rng.sample(POOL, 8)
    return sorted(chosen[:4]), sorted(chosen[4:])


def op(driver: str, value: str) -> dict:
    return {"op": "set", "select": f"entrants.drivers.driver[_metadata_={driver}]", "field": KEY, "value": value}


def write_addon(arm: str, high: list[str], low: list[str]) -> None:
    folder = ROOT / f"verve.b0014{arm}"
    (folder / "db").mkdir(parents=True, exist_ok=True)
    ops = [op(d, HIGH) for d in high] + [op(d, LOW) for d in low]
    (folder / "db" / f"b0014{arm}.json").write_text(json.dumps({"schema_version": 1, "ops": ops}, indent=2) + "\n", "utf-8")
    manifest = {
        "schema_version": 1, "id": f"verve.b0014{arm}", "name": f"Verve test B-0014{arm} (row aggression crossover)",
        "version": "0.0.1", "author": "TC Verve",
        "description": f"Test-only addon for race batch B-0014, order {arm}: {KEY} = {HIGH} on {', '.join(high)}; "
                       f"{LOW} on {', '.join(low)}. Not for play.",
        "license": "MIT", "category": "ai", "kind": ["database"],
        "compat": {"game": "f1_25", "game_builds": ["25251167"], "launcher": ">=1.5.13"},
        "requires": [{"id": "swofty.core", "version": ">=0.2.13"}], "saves": {"affects": False},
        "operations": {"database": [f"db/b0014{arm}.json"]},
    }
    (folder / "swofty.json").write_text(json.dumps(manifest, indent=2) + "\n", "utf-8")


if __name__ == "__main__":
    g1, g2 = draw()
    print("G1:", ", ".join(g1))
    print("G2:", ", ".join(g2))
    print("left out:", ", ".join(sorted(set(POOL) - set(g1) - set(g2))))
    write_addon("a", g1, g2)
    write_addon("b", g2, g1)
