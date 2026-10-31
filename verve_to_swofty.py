#!/usr/bin/env python3
"""Verve driver profiles -> Swofty Launcher data addon for F1 25 (v0.2: #5 crosswalk, #6 recalibration).

Usage:
    powershell -File tools/fetch_verve.ps1           # once: Verve's drivers.lua at the pinned commit -> .cache/
    python3 verve_to_swofty.py --out verve-f1-addon --print-table

Inputs:
    Verve lib/drivers.lua at VERVE_COMMIT (checked by git blob hash, VERVE_BLOB): pace, aggr, risk, cons per profile,
        each 0..1 with 0.5 = field average. Only the rows the crosswalk names are read.
    data/crosswalk_f1.csv: verve_key -> real name, F1 25 driver-row label, statistics-holder label, grid. A row whose
        verve_key is "-" is a grid driver with no Verve profile; it is reported and left stock.
    docs/stock/driver_characteristics_grid.csv: each driver's stock row driver_characteristics (the anchor).
    docs/stock/pace_curves_grid.csv: each holder's stock pace evolution curve, per dataset.

Every characteristic is the driver's own stock row value moved by Verve: value = stock + K * (signal - center),
clamped to 0..1, where signal is a blend of Verve scalars (MAPPING) and center is that signal's grid mean (CENTER). Rows win over ratings in benchmark (F-36), so
the row is what the AI reads; anchoring on it keeps every driver's F1 25 baseline and lets Verve move it.
`mistakes` is a skill, higher = fewer mistakes (F-37, verified in benchmark), so its signal rises with consistency
and falls with risk. Strategy stays stock: Verve has no strategy axis, and risk is not a strategy input.

The pace rating moves the stock curve, keeping its shape (season progression, #21): Verve pace sets the order and
the written drivers' stock season-0 ratings are handed out in that order, so the grid keeps its stock spread;
drivers within PACE_TOL (0.03) of each other in Verve pace form a group whose slots go out in stock order (Verve's
pace is mostly a floor for drivers without a winning record, so inside a group the game's order is the better
information; --tie-mode mean shares the slots' mean instead); each dataset's curve is shifted by target - its own season-0 value. A linear map would
squash the field: Verve puts two drivers at 0.96-1.00 and most at 0.62-0.71. Simulated sessions read the ratings, so they follow Verve pace too.

Output: <out>/swofty.json, <out>/db/verve.json and <out>/table.csv (stock vs Verve per driver, with the F-39
start-model predictions).
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent

# --------------------------------------------------------------------------------------
# Pinned Verve source (#5)
# --------------------------------------------------------------------------------------

VERVE_COMMIT = "80d1798385ac4d62c20677a68ef508a4740dfd68"
VERVE_BLOB = "22d6d2cf342904296162b758950d83f601d4954f"   # git blob sha of lib/drivers.lua at VERVE_COMMIT

# --------------------------------------------------------------------------------------
# Mapping (#6). Signals are blends of Verve scalars, each 0..1; inv_risk = 1 - risk.
# --------------------------------------------------------------------------------------

MAPPING = {
    # driver_characteristics.<name>: signal weights
    "aggression":     {"aggression": 1.00},                     # no risk input
    "control":        {"consistency": 0.70, "inv_risk": 0.30},
    "mistakes":       {"inv_risk": 0.60, "consistency": 0.40},  # a skill (F-37); risk = mistake proneness
    "reaction_speed": {"aggression": 0.60, "pace": 0.40},       # Verve has no reaction axis
    "speed_in":       {"pace": 1.00},                           # no risk input
    "speed_out":      {"pace": 0.80, "consistency": 0.20},
}
# gain: stock + GAIN * (signal - center). Kept at 0.5 on purpose. The predicted start spread is small (F-39: sd
# 0.014 s reaction, 0.007 b over the grid) because the game's start draws are wide uniforms, not because the gain is
# low; don't raise it to make starts look different. It gets tuned on behavioural metrics (pace, overtaking) once
# UDP works, and later by the strength slider (#22).
GAIN = 0.50
# Verve pace values closer than this share a pace-rating slot (see rank_map)
PACE_TOL = 0.03
# center: "grid" = each signal's mean over the drivers written, so a grid-average driver keeps their stock row. Verve's
# 0.5 is the average of its whole F1 bucket (classic and IndyCar drivers included); the modern grid sits well above it
# (consistency ~0.79), so centering at 0.5 lifts nearly everyone and clamps 26 of 138 values at 1. --center 0.5 keeps
# that behaviour for comparison.
CENTER = "grid"

# F-39 start model (benchmark): E[reaction] = 0.35 - 0.21 k rs, E[b] = 0.24 - 0.08 k m. Contrasts and level fits give
# different k for written rows (supervisor ruling, #55), so absolute predictions use the level fit and the change vs
# stock (the difference between drivers) uses the contrast slope. Reaction: 0.53 for both until the form of k is known.
REACTION_K = 0.53
BAD_START_K_LEVEL = 0.5     # pooled level fit: stock field 0.52, B-0011 written rows 0.48
BAD_START_K_CHANGE = 0.8    # contrasts between written levels: B-0009 0.70, B-0010 0.93 (dE[b]/dm ~ -0.064)

DRIVER_ROW = "entrants.drivers.driver[_metadata_={label}]"
PACE_STAT = (
    "driver_statistics.driver_statistics.DriverStatisticsHolder[driver={label}]"
    ".StatisticsDataSet[_metadata_={dataset}].Statistic[_metadata_=pace]"
)
LUA_ROW = re.compile(r"\{\s*key='(?P<key>[^']+)'.*?\bpace=(?P<pace>[\d.]+),\s*aggr=(?P<aggression>[\d.]+),"
                     r"\s*risk=(?P<risk>[\d.]+),\s*cons=(?P<consistency>[\d.]+)")


# --------------------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------------------

def clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


def fmt(x: float) -> str:
    """Values are always strings in Swofty db ops. 4 decimals is plenty for a 0..1 float."""
    return f"{x:.4f}".rstrip("0").rstrip(".") if x != 0 else "0"


def blend(weights: dict[str, float], s: dict[str, float]) -> float:
    return clamp(sum(w * s[k] for k, w in weights.items()) / sum(weights.values()))


def git_blob_sha(data: bytes) -> str:
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


def read_csv(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(line for line in f if not line.startswith("#")))


def read_verve(path: Path, keys: set[str]) -> dict[str, dict[str, float]]:
    data = path.read_bytes()
    sha = git_blob_sha(data)
    if sha != VERVE_BLOB:
        sys.exit(f"{path}: blob {sha} is not Verve lib/drivers.lua at {VERVE_COMMIT[:7]} (expected {VERVE_BLOB}); "
                 "run tools/fetch_verve.ps1")
    found = {}
    for m in LUA_ROW.finditer(data.decode("utf-8")):
        if m["key"] in keys:
            found[m["key"]] = {k: float(m[k]) for k in ("pace", "aggression", "risk", "consistency")}
    missing = sorted(keys - set(found))
    if missing:
        sys.exit(f"crosswalk keys not in drivers.lua: {missing}")
    return found


def curve_points(evolution: str) -> tuple[str, list[tuple[str, float]]]:
    """'@v2@minx:0,maxx:10,miny:0,maxy:100,0:0.96,...' -> ('@v2@minx:0,...,maxy:100', [('0', 0.96), ...])."""
    head, *pts = evolution.split(",")
    meta = [head] + [p for p in pts if p.split(":")[0] in ("maxx", "miny", "maxy")]
    points = [(p.split(":")[0], float(p.split(":")[1])) for p in pts if p.split(":")[0] not in ("maxx", "miny", "maxy")]
    return ",".join(meta), points


def shift_curve(evolution: str, delta: float) -> str:
    meta, points = curve_points(evolution)
    return meta + "," + ",".join(f"{x}:{clamp(y + delta):.4f}".rstrip("0").rstrip(".") for x, y in points)


def set_op(select: str, field: str, value: str) -> dict:
    return {"op": "set", "select": select, "field": field, "value": value}


# --------------------------------------------------------------------------------------
# build
# --------------------------------------------------------------------------------------

def rank_map(values: dict[str, float], targets: list[float], tol: float, stock: dict[str, float],
             tie_mode: str) -> dict[str, float]:
    """Give the i-th lowest value the i-th lowest target. Going up from the lowest value, each group takes every
    value within `tol` of the group's first: Verve can't tell those drivers apart. Inside a group, tie_mode "stock"
    hands the group's slots out in stock order (Verve orders the groups, the game orders within them); "mean" gives
    the whole group the mean of its slots (#52 review)."""
    order = sorted(values, key=values.get)
    targets = sorted(targets)
    out, i = {}, 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and values[order[j + 1]] - values[order[i]] <= tol + 1e-9:
            j += 1
        group, slots = order[i:j + 1], targets[i:j + 1]
        if tie_mode == "mean":
            for k in group:
                out[k] = sum(slots) / len(slots)
        else:
            for k, slot in zip(sorted(group, key=lambda d: (stock[d], d)), slots):
                out[k] = slot
        i = j + 1
    return out


def build(crosswalk: list[dict], verve: dict, stock_rows: dict, pace_curves: dict, ratings: bool, center,
          gain: float, pace_tol: float, tie_mode: str):
    drivers = [c for c in crosswalk if c["verve_key"] != "-"]
    scalars = {}
    for c in drivers:
        s = dict(verve[c["verve_key"]])
        s["inv_risk"] = 1.0 - s["risk"]
        scalars[c["f1_25_label"]] = s
    signals = {label: {n: blend(w, s) for n, w in MAPPING.items()} for label, s in scalars.items()}
    centers = {n: (sum(sig[n] for sig in signals.values()) / len(signals) if center == "grid" else float(center))
               for n in MAPPING}
    # pace rating: Verve pace decides the order, the grid's stock season-0 ratings keep their spread
    stock_x0 = {c["f1_25_label"]: curve_points(pace_curves[(c["stats_label"], "default")])[1][0][1] for c in drivers}
    targets = rank_map({label: s["pace"] for label, s in scalars.items()}, list(stock_x0.values()), pace_tol,
                       stock_x0, tie_mode)

    ops, table = [], []
    for c in drivers:
        label, s = c["f1_25_label"], scalars[c["f1_25_label"]]
        stock = {k: float(v) for k, v in stock_rows[label].items() if k != "label"}
        row = DRIVER_ROW.format(label=label)
        out = {}
        for name in MAPPING:
            out[name] = clamp(stock[name] + gain * (signals[label][name] - centers[name]))
            ops.append(set_op(row, f"driver_characteristics.{name}", fmt(out[name])))

        target = targets[label]
        if ratings:
            for ds in ("default", "2026"):
                evo = pace_curves.get((c["stats_label"], ds))
                if evo:
                    delta = target - curve_points(evo)[1][0][1]
                    ops.append(set_op(PACE_STAT.format(label=c["stats_label"], dataset=ds), "evolution",
                                      shift_curve(evo, delta)))

        rt = lambda rs: 0.35 - 0.21 * REACTION_K * rs
        bad = lambda m: 0.24 - 0.08 * BAD_START_K_LEVEL * m
        table.append({
            "label": label, "real_name": c["real_name"], "verve_key": c["verve_key"], "grid": c["grid"],
            **{f"verve_{k}": s[k] for k in ("pace", "aggression", "risk", "consistency")},
            **{f"{n}_stock": stock[n] for n in MAPPING}, **{f"{n}_verve": round(out[n], 4) for n in MAPPING},
            "pace_rating_stock": round(100 * stock_x0[label], 1), "pace_rating_verve": round(100 * target, 1),
            "pred_reaction_stock": round(rt(stock["reaction_speed"]), 4),
            "pred_reaction_verve": round(rt(out["reaction_speed"]), 4),
            "pred_reaction_change": round(-0.21 * REACTION_K * (out["reaction_speed"] - stock["reaction_speed"]), 4),
            "pred_bad_start_stock": round(bad(stock["mistakes"]), 4),
            "pred_bad_start_verve": round(bad(out["mistakes"]), 4),
            "pred_bad_start_change": round(-0.08 * BAD_START_K_CHANGE * (out["mistakes"] - stock["mistakes"]), 4),
        })
    missing = [c for c in crosswalk if c["verve_key"] == "-"]
    return ops, table, missing, centers


def manifest(addon_id: str, name: str, author: str, version: str, n_drivers: int) -> dict:
    return {
        "schema_version": 1,
        "id": addon_id,
        "name": name,
        "version": version,
        "author": author,
        "description": f"Verve driver personalities for {n_drivers} F1 drivers: aggression, control, mistakes, "
                       "reaction, entry and exit speed, and pace rating, moved from each driver's stock values.",
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
    ap.add_argument("--verve-lua", type=Path, default=ROOT / ".cache" / "verve" / VERVE_COMMIT / "drivers.lua")
    ap.add_argument("--crosswalk", type=Path, default=ROOT / "data" / "crosswalk_f1.csv")
    ap.add_argument("--stock-rows", type=Path, default=ROOT / "docs" / "stock" / "driver_characteristics_grid.csv")
    ap.add_argument("--stock-pace", type=Path, default=ROOT / "docs" / "stock" / "pace_curves_grid.csv")
    ap.add_argument("--out", type=Path, default=ROOT / "verve-f1-addon")
    ap.add_argument("--addon-id", default="verve.driver-profiles")
    ap.add_argument("--name", default="Verve Driver Profiles")
    ap.add_argument("--author", default="TC Verve")
    ap.add_argument("--version", default="0.2.0")
    ap.add_argument("--no-ratings", action="store_true", help="leave the pace rating curves stock")
    ap.add_argument("--center", default=CENTER, help='"grid" (default) or a number; 0.5 = the literal #6 spec')
    ap.add_argument("--gain", type=float, default=GAIN, help="stock + gain * (signal - center)")
    ap.add_argument("--pace-tol", type=float, default=PACE_TOL,
                    help="Verve pace values this close form one group; 0 = pure rank map")
    ap.add_argument("--tie-mode", choices=("stock", "mean"), default="stock",
                    help="inside a group: stock order on the group's slots (default), or the slots' mean")
    ap.add_argument("--print-table", action="store_true", help="print stock vs Verve per driver")
    args = ap.parse_args()

    crosswalk = read_csv(args.crosswalk)
    verve = read_verve(args.verve_lua, {c["verve_key"] for c in crosswalk if c["verve_key"] != "-"})
    stock_rows = {r["label"]: r for r in read_csv(args.stock_rows)}
    pace_curves = {(r["stats_label"], r["dataset"]): r["evolution"] for r in read_csv(args.stock_pace)
                   if r["evolution"] != "NA"}
    for c in crosswalk:
        if c["verve_key"] != "-" and c["f1_25_label"] not in stock_rows:
            sys.exit(f"{c['f1_25_label']}: no stock row in {args.stock_rows}")
        if c["verve_key"] != "-" and (c["stats_label"], "default") not in pace_curves:
            sys.exit(f"{c['stats_label']}: no stock pace curve in {args.stock_pace}")

    ops, table, missing, centers = build(crosswalk, verve, stock_rows, pace_curves, ratings=not args.no_ratings,
                                         center=args.center, gain=args.gain, pace_tol=args.pace_tol,
                                         tie_mode=args.tie_mode)

    out = args.out
    (out / "db").mkdir(parents=True, exist_ok=True)
    # newline="\n": LF on every OS, so a Windows run doesn't rewrite every line in git
    (out / "db" / "verve.json").write_text(
        json.dumps({"schema_version": 1, "ops": ops}, indent=1) + "\n", encoding="utf-8", newline="\n")
    (out / "swofty.json").write_text(
        json.dumps(manifest(args.addon_id, args.name, args.author, args.version, len(table)), indent=1) + "\n",
        encoding="utf-8", newline="\n")
    with (out / "table.csv").open("w", newline="\n", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(table[0].keys()), lineterminator="\n")
        w.writeheader()
        w.writerows(table)

    print(f"{len(table)} drivers, {len(ops)} ops -> {out}/db/verve.json; table -> {out}/table.csv")
    print(f"Verve source: ververacing/verve lib/drivers.lua @ {VERVE_COMMIT[:7]}")
    print("signal centers: " + ", ".join(f"{n} {v:.3f}" for n, v in centers.items()))
    for c in missing:
        print(f"no Verve profile (left stock): {c['real_name']} ({c['f1_25_label']}, grid {c['grid']})")
    clamped = sum(1 for r in table for n in MAPPING if r[f"{n}_verve"] in (0.0, 1.0) and r[f"{n}_stock"] not in (0.0, 1.0))
    print(f"values clamped at 0 or 1: {clamped} of {len(table) * len(MAPPING)}")
    if args.print_table:
        cols = ["label"] + [c for n in MAPPING for c in (f"{n}_stock", f"{n}_verve")] + [
            "pace_rating_stock", "pace_rating_verve", "pred_reaction_stock", "pred_reaction_verve",
            "pred_reaction_change", "pred_bad_start_stock", "pred_bad_start_verve", "pred_bad_start_change"]
        widths = {c: max(len(c), *(len(str(r[c])) for r in table)) for c in cols}
        print("  ".join(c.ljust(widths[c]) for c in cols))
        for r in table:
            print("  ".join(str(r[c]).ljust(widths[c]) for c in cols))


if __name__ == "__main__":
    main()
