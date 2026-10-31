#!/usr/bin/env python3
"""Verve profiles (Pace, Aggression, Risk, Consistency; each 0..1) -> Swofty Launcher data addon for F1 25.

Usage:
    python3 verve_to_swofty.py profiles.csv --out verve-f1-addon
    python3 verve_to_swofty.py profiles.csv --out verve-f1-addon --mistakes-is-skill --no-strategy

Input CSV columns: label,display,pace,aggression,risk,consistency[,preferred_tracks]
    label            the driver row's _metadata_ in entrants.drivers (max_verstappen, carlos_sainz-jr, ...)
    preferred_tracks optional, track labels separated by | (monaco|singapore)

Output: <out>/swofty.json and <out>/db/verve.json (database "set" ops), ready to zip and drop on the launcher.

All weights live in MAPPING below so a tuning pass is a one-line change.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

# --------------------------------------------------------------------------------------
# Mapping weights. Every input scalar is 0..1; every characteristic is 0..1.
# --------------------------------------------------------------------------------------

MAPPING = {
    # driver_characteristics.<name>: linear blend of Verve scalars, then clamped to [0, 1]
    "aggression":     {"aggression": 0.70, "risk": 0.30},
    "control":        {"consistency": 1.00},
    "reaction_speed": {"aggression": 0.60, "pace": 0.40},
    "speed_in":       {"pace": 0.80, "risk": 0.20},
    "speed_out":      {"pace": 0.80, "consistency": 0.20},
    # "mistakes" is handled separately: see mistakes_value()
}

# mistakes as a SKILL (higher = fewer mistakes): 0.60 Consistency + 0.40 (1 - Risk)
# mistakes as PRONENESS (higher = more mistakes, the script default): 1 - the skill value
MISTAKES_SKILL = {"consistency": 0.60, "inv_risk": 0.40}

# pace rating band written to the driver's statistics (0..100 scale)
RATING_FLOOR = 70.0
RATING_CEILING = 99.0

# driver_strategy: (field, lo, hi, scalar, direction). value = lo + (hi - lo) * s, or hi - (hi - lo) * s when inverted
STRATEGY = [
    ("driver_strategy.fastest_strategy_base_selection_chance", 0.15, 0.85, "risk", False),
    ("driver_strategy.safety_car_pit_wear_min",                0.10, 0.35, "risk", True),
    ("driver_strategy.safety_car_pit_wear_max",                0.20, 0.50, "risk", True),
]

DRIVER_ROW = "entrants.drivers.driver[_metadata_={label}]"
PACE_STAT = (
    "driver_statistics.driver_statistics.DriverStatisticsHolder[driver={label}]"
    ".StatisticsDataSet[_metadata_={dataset}].Statistic[_metadata_=pace]"
)


# --------------------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------------------

def clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


def fmt(x: float) -> str:
    """Values are always strings in Swofty db ops. 4 decimals is plenty for a 0..1 float."""
    return f"{x:.4f}".rstrip("0").rstrip(".") if x != 0 else "0"


def blend(weights: dict[str, float], s: dict[str, float]) -> float:
    total = sum(weights.values())
    return clamp(sum(w * s[k] for k, w in weights.items()) / total)


def mistakes_value(s: dict[str, float], as_skill: bool) -> float:
    skill = blend(MISTAKES_SKILL, s)
    return skill if as_skill else clamp(1.0 - skill)


def pace_curve(pace: float, floor: float, ceiling: float) -> str:
    """Flat evolution curve at the rating, the shape Classic Seasons writes (y normalised to 0..1 over 0..100)."""
    rating = floor + clamp(pace) * (ceiling - floor)
    y = f"{rating / 100.0:.3f}"
    return f"@v2@minx:0,maxx:10,miny:0,maxy:100,0:{y},0:{y},1:{y},1:{y}"


def set_op(select: str, field: str, value: str) -> dict:
    return {"op": "set", "select": select, "field": field, "value": value}


# --------------------------------------------------------------------------------------
# main
# --------------------------------------------------------------------------------------

def read_profiles(path: Path) -> list[dict]:
    rows = []
    with path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        needed = {"label", "pace", "aggression", "risk", "consistency"}
        missing = needed - set(reader.fieldnames or [])
        if missing:
            sys.exit(f"CSV is missing columns: {sorted(missing)}")
        for n, r in enumerate(reader, start=2):
            label = (r.get("label") or "").strip()
            if not label or label.startswith("#"):
                continue
            try:
                s = {k: float(r[k]) for k in ("pace", "aggression", "risk", "consistency")}
            except ValueError as e:
                sys.exit(f"line {n} ({label}): bad number: {e}")
            for k, v in s.items():
                if not 0.0 <= v <= 1.0:
                    sys.exit(f"line {n} ({label}): {k}={v} is outside 0..1")
            s["inv_risk"] = 1.0 - s["risk"]
            rows.append({
                "label": label,
                "display": (r.get("display") or label).strip(),
                "scalars": s,
                "preferred_tracks": [t.strip() for t in (r.get("preferred_tracks") or "").split("|") if t.strip()],
            })
    if not rows:
        sys.exit("no profiles in the CSV")
    labels = [r["label"] for r in rows]
    dupes = sorted({l for l in labels if labels.count(l) > 1})
    if dupes:
        sys.exit(f"duplicate labels: {dupes}")
    return rows


def build_ops(profiles: list[dict], *, mistakes_is_skill: bool, strategy: bool, ratings: bool,
              datasets: list[str], floor: float, ceiling: float) -> tuple[list[dict], list[dict]]:
    ops: list[dict] = []
    table: list[dict] = []
    for p in profiles:
        s = p["scalars"]
        row = DRIVER_ROW.format(label=p["label"])
        chars = {name: blend(w, s) for name, w in MAPPING.items()}
        chars["mistakes"] = mistakes_value(s, mistakes_is_skill)

        for name in ("aggression", "control", "mistakes", "reaction_speed", "speed_in", "speed_out"):
            ops.append(set_op(row, f"driver_characteristics.{name}", fmt(chars[name])))

        if p["preferred_tracks"]:
            ops.append(set_op(row, "driver_characteristics.preferred_tracks", ",".join(p["preferred_tracks"])))

        strat = {}
        if strategy:
            for field, lo, hi, key, inverted in STRATEGY:
                v = hi - (hi - lo) * s[key] if inverted else lo + (hi - lo) * s[key]
                strat[field.split(".")[-1]] = v
                ops.append(set_op(row, field, fmt(v)))

        rating = None
        if ratings:
            rating = floor + s["pace"] * (ceiling - floor)
            for ds in datasets:
                ops.append(set_op(PACE_STAT.format(label=p["label"], dataset=ds), "evolution",
                                  pace_curve(s["pace"], floor, ceiling)))

        table.append({"label": p["label"], "display": p["display"], **{k: round(v, 3) for k, v in chars.items()},
                      "pace_rating": None if rating is None else round(rating, 1),
                      **{k: round(v, 3) for k, v in strat.items()}})
    return ops, table


def manifest(addon_id: str, name: str, author: str, version: str, n_drivers: int) -> dict:
    return {
        "schema_version": 1,
        "id": addon_id,
        "name": name,
        "version": version,
        "author": author,
        "description": f"Verve driver personalities for {n_drivers} drivers: aggression, control, mistakes, "
                       "reaction, entry and exit speed, pace rating and pit strategy, from real-driver data.",
        "license": "MIT",
        "category": "ai",
        "kind": ["database"],
        # pinned to the build the stock values in docs/stock/ were dumped from; widen after re-dumping on a new build
        "compat": {"game": "f1_25", "game_builds": ["25251167"], "launcher": ">=1.5.13"},
        "requires": [{"id": "swofty.core", "version": ">=0.2.13"}],
        "saves": {"affects": False},
        "operations": {"database": ["db/verve.json"]},
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("csv", type=Path)
    ap.add_argument("--out", type=Path, default=Path("verve-f1-addon"))
    ap.add_argument("--addon-id", default="verve.driver-profiles")
    ap.add_argument("--name", default="Verve Driver Profiles")
    ap.add_argument("--author", default="TC Verve")
    ap.add_argument("--version", default="0.1.0")
    ap.add_argument("--mistakes-is-skill", action="store_true",
                    help="treat driver_characteristics.mistakes as mistake resistance (higher = fewer mistakes)")
    ap.add_argument("--no-strategy", action="store_true", help="leave driver_strategy.* stock")
    ap.add_argument("--no-ratings", action="store_true", help="leave the pace rating stock")
    ap.add_argument("--datasets", default="default",
                    help="comma-separated StatisticsDataSet labels to write the pace rating into (default: default)")
    ap.add_argument("--rating-floor", type=float, default=RATING_FLOOR)
    ap.add_argument("--rating-ceiling", type=float, default=RATING_CEILING)
    ap.add_argument("--print-table", action="store_true", help="print the resolved values per driver")
    args = ap.parse_args()

    profiles = read_profiles(args.csv)
    ops, table = build_ops(
        profiles,
        mistakes_is_skill=args.mistakes_is_skill,
        strategy=not args.no_strategy,
        ratings=not args.no_ratings,
        datasets=[d.strip() for d in args.datasets.split(",") if d.strip()],
        floor=args.rating_floor,
        ceiling=args.rating_ceiling,
    )

    out = args.out
    (out / "db").mkdir(parents=True, exist_ok=True)
    (out / "db" / "verve.json").write_text(
        json.dumps({"schema_version": 1, "ops": ops}, indent=1) + "\n", encoding="utf-8")
    (out / "swofty.json").write_text(
        json.dumps(manifest(args.addon_id, args.name, args.author, args.version, len(profiles)), indent=1) + "\n",
        encoding="utf-8")

    print(f"{len(profiles)} drivers, {len(ops)} ops -> {out}/db/verve.json, manifest -> {out}/swofty.json")
    print(f"mistakes written as {'SKILL (higher = fewer)' if args.mistakes_is_skill else 'PRONENESS (higher = more)'}")
    if args.print_table:
        cols = list(table[0].keys())
        widths = {c: max(len(c), *(len(str(r[c])) for r in table)) for c in cols}
        print("  ".join(c.ljust(widths[c]) for c in cols))
        for r in table:
            print("  ".join(str(r[c]).ljust(widths[c]) for c in cols))


if __name__ == "__main__":
    main()
