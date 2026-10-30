#!/usr/bin/env python3
"""Single source of truth for the per-driver ai_driver_config key catalogue.

Writes docs/ai_driver_config_keys.csv and docs/ai_driver_config_keys.md from the ENTRIES table below.
Run from the repo root: python3 tools/build_catalogue.py

Evidence levels follow the Swofty RE convention: L1 named statically (decomp/log string), L2 decompiled with
agreeing verification, L3 confirmed by a runtime trace. "consumer" says whether the code that READS the key at
race time has been located, which is what decides whether a value can be tuned blind.

Blind-tunable rating:
  A  consumer located and semantics decoded; safe to vary per driver now
  B  name is unambiguous enough to hypothesise a direction; consumer not traced; vary in small steps, verify
  C  controller-level, geometric, or rules-related; do not touch until traced (or never, for rules)
"""
from __future__ import annotations

import csv
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PARSERS = {
    "alongside":        ("Ai_Read_AlongsideConfig",     "0x14065da00", "L1", "reads keys by name; log string lists them"),
    "blocking":         ("Ai_Parse_BlockingConfig",     "0x14065dad0", "L1", "decomp cited as re/decomp/14065dad0.c in functions.tsv (decomp files are not in the public repo)"),
    "cede_position":    ("Ai_Parse_CedePositionConfig", "0x14065dc50", "L1", "decomp cited as re/decomp/14065dc50.c (not public); also parses divebomb_defense"),
    "divebomb_defense": ("Ai_Parse_CedePositionConfig", "0x14065dc50", "L1", "decomp cited as re/decomp/14065dc50.c (not public)"),
    "exit_fallibility": ("per-driver AI data +0x348/+0x350", "0x1405f5dd0", "L1", "consumer decoded in Ai_Read_GeneralSettings_3 note"),
    "offset_variation": ("(parser not identified)",     "-",           "L0", "keys exist on every driver row (Classic Seasons fields list); no RE note"),
    "overtake":         ("Ai_Parse_OvertakeConfig",     "0x14065de80", "L1", "decomp cited as re/decomp/14065de80.c (not public); overlap_percentage consumer 0x140650150"),
    "race_start":       ("Ai_Parse_RaceStartConfig",    "0x14065e040", "L1", "decomp cited as re/decomp/14065e040.c (not public); consumer Ai_RaceStart_ReactionTime 0x1406527c0"),
    "space_seeking":    ("Ai_Parse_SpaceSeekingConfig", "0x14065e120", "L1", "decomp cited as re/decomp/14065e120.c (not public)"),
}

# (group, leaf, type, what_re_says, consumer_located, rating, verve_axis, direction_hypothesis, trace_needed)
# type: float unless the name says graph/curve. "direction" is a hypothesis unless the rating is A.
ENTRIES = [
    # ---------------------------------------------------------------- overtake (19)
    ("overtake", "attacker_close_enough_car_lengths", "float",
     "Distance (car lengths) behind the car ahead at which this driver counts as close enough to attack.",
     "no", "B", "Aggression", "Aggression up -> value up (attacks from further back)",
     "One race, two drivers at 2x and 0.5x stock; count overtake attempts from the AI_VARIATION/telemetry feed"),
    ("overtake", "braking_zone_abort_overtake_time", "float",
     "Seconds to the braking zone below which an in-progress overtake is aborted.",
     "no", "B", "Risk", "Risk up -> value down (commits later into the braking zone)",
     "Same race; watch late aborts at heavy braking zones"),
    ("overtake", "close_range_car_lengths_to_continue_overtake", "float",
     "Car-length window inside which an overtake already started is continued.",
     "no", "B", "Aggression", "Aggression up -> value up",
     "Pair with _to_start_overtake"),
    ("overtake", "close_range_car_lengths_to_start_overtake", "float",
     "Car-length window inside which an overtake may be started.",
     "no", "B", "Aggression", "Aggression up -> value up",
     "Pair with _to_continue_overtake; keep start <= continue"),
    ("overtake", "concede_slowdown_speed_diff", "float",
     "Speed difference (attacker slower) at which the attacker slows and concedes.",
     "no", "B", "Aggression", "Aggression up -> value up (needs a bigger deficit before giving up)",
     "Verify sign: could be the car-ahead's speed advantage"),
    ("overtake", "concede_speed_diff", "float",
     "Speed difference at which an overtake is conceded outright.",
     "no", "B", "Aggression", "Aggression up -> value up",
     "As above"),
    ("overtake", "concede_time_vs_behind", "float",
     "Time gap to the car behind that makes the attacker concede (to avoid losing the place behind).",
     "no", "C", "-", "unknown",
     "Needs trace; interacts with defending"),
    ("overtake", "danger_overtake_buffer", "float",
     "Extra lateral/longitudinal buffer required for a 'danger' class overtake.",
     "no", "B", "Risk", "Risk up -> value down",
     "Danger overtakes are the risky class; verify by contact count"),
    ("overtake", "danger_overtake_continue_time_adjustment", "float",
     "Time adjustment applied when deciding to continue a danger overtake.",
     "no", "B", "Risk", "Risk up -> continues longer (sign unknown)",
     "Trace with regular_* to learn the sign convention"),
    ("overtake", "danger_overtake_full_heat_time_adjustment", "float",
     "Time adjustment at 'full heat' (fully committed) for a danger overtake.",
     "no", "C", "Risk", "unknown sign",
     "Trace"),
    ("overtake", "danger_overtake_initiate_time_adjustment", "float",
     "Time adjustment applied when deciding to initiate a danger overtake.",
     "no", "B", "Risk", "Risk up -> initiates sooner (sign unknown)",
     "Trace"),
    ("overtake", "danger_overtake_pull_out_time", "float",
     "Seconds before the braking zone at which a danger overtake pulls out of the slipstream.",
     "no", "B", "Risk", "Risk up -> value down (pulls out later)",
     "Trace"),
    ("overtake", "oppertunist_overtake_time", "float",
     "Seconds the car ahead must stay slow (see track_speed_difference) before an opportunist overtake is taken. (sic: game spelling)",
     "no", "B", "Aggression", "Aggression up -> value down",
     "Verify on a slow car ahead (damaged AI)"),
    ("overtake", "oppertunist_overtake_track_speed_difference", "float",
     "Track-speed deficit of the car ahead that qualifies as an opportunist overtake. (sic)",
     "no", "B", "Aggression", "Aggression up -> value down",
     "As above"),
    ("overtake", "overlap_percentage", "curve",
     "DECODED: curve at config +0x1d0, evaluated by the overtake helper 0x140650150 at x = the driver's effective aggression (+0xa8), only when the attacker is within 0.5 lap. Output is the overlap the driver accepts/needs to commit alongside.",
     "yes", "A", "(already driven by aggression)", "Leave stock per driver; aggression is the input",
     "None for v0.2; shape could be retuned globally later"),
    ("overtake", "regular_overtake_continue_time_adjustment", "float",
     "Time adjustment when deciding to continue a regular overtake.",
     "no", "B", "Aggression", "Aggression up -> continues longer (sign unknown)",
     "Trace"),
    ("overtake", "regular_overtake_full_heat_time_adjustment", "float",
     "Time adjustment at full commitment for a regular overtake.",
     "no", "C", "Aggression", "unknown sign",
     "Trace"),
    ("overtake", "regular_overtake_initiate_time_adjustment", "float",
     "Time adjustment when deciding to initiate a regular overtake.",
     "no", "B", "Aggression", "Aggression up -> initiates sooner (sign unknown)",
     "Trace"),
    ("overtake", "regular_overtake_pull_out_time", "float",
     "Seconds before the braking zone at which a regular overtake pulls out.",
     "no", "B", "Aggression", "Aggression up -> value down",
     "Trace"),
    # ---------------------------------------------------------------- blocking (16)
    ("blocking", "avoidance_decrease_rate", "float",
     "Rate at which an avoidance offset decays after a threat passes.",
     "no", "C", "-", "controller-level", "Trace"),
    ("blocking", "blocking_offset_from_car_behind", "float",
     "Lateral offset the defender places itself at relative to the attacker.",
     "no", "C", "-", "geometric; wrong values cause contact", "Trace"),
    ("blocking", "blocking_speed_differential", "float",
     "Closing speed of the attacker that triggers a defensive move.",
     "no", "B", "Aggression", "Aggression up -> value down (defends against smaller threats)",
     "Two defenders at 0.5x/2x; count blocks from the telemetry lateral offset"),
    ("blocking", "blocking_threat_time_modifier", "float",
     "Scales the perceived time-to-threat used to decide when to block.",
     "no", "B", "Aggression", "Aggression up -> value up (sees threats earlier)",
     "Trace sign"),
    ("blocking", "blocking_variable_offset_fraction", "float",
     "Fraction of the blocking offset that is randomised.",
     "no", "B", "Consistency", "Consistency down -> value up (less predictable defender)",
     "Low risk; verify no contact increase"),
    ("blocking", "end_blocking_time_to_corner_vs_offset", "float",
     "Relation between time-to-corner and offset at which blocking ends (name suggests a graph; type unverified).",
     "no", "C", "-", "unknown", "Dump stock value with swofty db get to learn the type"),
    ("blocking", "fraction_of_follow_speed", "float",
     "Speed fraction the defender holds while blocking.",
     "no", "C", "-", "controller-level", "Trace"),
    ("blocking", "fraction_of_follow_speed_at_race_start", "float",
     "As above, during the race start.",
     "no", "C", "-", "controller-level", "Trace"),
    ("blocking", "max_blocking_distance", "float",
     "Maximum distance to the attacker at which the defender still blocks.",
     "no", "B", "Aggression", "Aggression up -> value up",
     "Verify"),
    ("blocking", "max_blocking_distance_at_race_start", "float",
     "As above at the race start.",
     "no", "B", "Aggression", "Aggression up -> value up",
     "Verify"),
    ("blocking", "merge_back_to_racing_line", "float",
     "Rate or time to merge back to the racing line after a block.",
     "no", "C", "-", "controller-level", "Trace"),
    ("blocking", "start_blocking_intersection_time", "float",
     "Time-to-intersection with the attacker's line at which a block starts.",
     "no", "B", "Aggression", "Aggression up -> value up (starts earlier)",
     "Trace sign"),
    ("blocking", "start_blocking_maximum_time_to_corner", "float",
     "Upper bound of the time-to-corner window inside which a block may start.",
     "no", "B", "Aggression", "Aggression up -> value up",
     "Keep min < max"),
    ("blocking", "start_blocking_minimum_time_to_corner", "float",
     "Lower bound of that window (the 'one move' rule lives around here).",
     "no", "C", "-", "rules-adjacent; late blocks read as unfair", "Leave stock"),
    ("blocking", "time_to_corner_for_end_merge_rate", "float",
     "Time-to-corner at which the end-of-block merge rate applies.",
     "no", "C", "-", "controller-level", "Trace"),
    ("blocking", "time_to_corner_for_start_merge_rate", "float",
     "Time-to-corner at which the start-of-block merge rate applies.",
     "no", "C", "-", "controller-level", "Trace"),
    # ---------------------------------------------------------------- space_seeking (13)
    ("space_seeking", "added_buffer", "float",
     "Extra buffer kept while looking for space in traffic.",
     "no", "C", "-", "geometric", "Trace"),
    ("space_seeking", "can_start_track_radius", "float",
     "Minimum track radius (straightness) at which space seeking may start.",
     "no", "B", "Risk", "Risk up -> value down (tries in tighter sections)",
     "Verify at Monaco/Singapore"),
    ("space_seeking", "car_in_front_needed", "float",
     "Whether/how much a car in front is required before seeking space (bool-like).",
     "no", "C", "-", "unknown", "Dump stock value"),
    ("space_seeking", "cars_moving_away_speed_to_ignore", "float",
     "Cars pulling away faster than this are not treated as traffic.",
     "no", "C", "-", "unknown", "Trace"),
    ("space_seeking", "concede_overtake_blocked_by_crowed_time", "float",
     "Seconds after which an overtake blocked by crowding is conceded. (sic)",
     "no", "B", "Aggression", "Aggression up -> value up (persists longer in traffic)",
     "Likely a train-behaviour lever; verify in a DRS train"),
    ("space_seeking", "distance_braking_point", "float",
     "Distance to the braking point used to abort space seeking.",
     "no", "C", "-", "geometric", "Trace"),
    ("space_seeking", "first_speed_below_follow", "float",
     "Initial speed-below-follow threshold that triggers seeking.",
     "no", "B", "Aggression", "Aggression up -> triggers at smaller deficit",
     "Pair with speed_below_follow"),
    ("space_seeking", "remember_crowed", "float",
     "Seconds the driver remembers a crowded situation. (sic)",
     "no", "C", "-", "unknown", "Trace"),
    ("space_seeking", "speed_below_follow", "float",
     "Steady-state speed-below-follow threshold for seeking space.",
     "no", "B", "Aggression", "Aggression up -> triggers at smaller deficit",
     "Pair with first_speed_below_follow"),
    ("space_seeking", "time_to_switch_sides", "float",
     "Seconds before trying the other side of the car ahead.",
     "no", "B", "Aggression", "Aggression up -> value down",
     "Verify; a strong 'style' knob if it works"),
    ("space_seeking", "total_queue_needed", "float",
     "Number of cars queued ahead needed before seeking space.",
     "no", "B", "Aggression", "Aggression up -> value down",
     "Verify"),
    ("space_seeking", "track_abort_distance", "float",
     "Track distance after which seeking is abandoned.",
     "no", "C", "-", "geometric", "Trace"),
    ("space_seeking", "track_distance_needed", "float",
     "Track distance of clear road needed to attempt.",
     "no", "C", "-", "geometric", "Trace"),
    # ---------------------------------------------------------------- race_start (9)
    ("race_start", "max_reaction_time_lower_bound", "float",
     "DECODED (Ai_RaceStart_ReactionTime 0x1406527c0, log channel RaceStarts): reaction ~ U[lo, hi] with lo/hi interpolated from the min_* bounds (characteristic 0) to the max_* bounds (characteristic 1) by k x reaction_speed, k = per-session factor at R+0x14c. Stock corners: min = [0.28, 0.42], max = [0.04, 0.24].",
     "yes", "A", "Consistency", "Consistency up -> narrow the [lower, upper] spread; Pace/Aggression already move the centre via reaction_speed",
     "Turn on RaceStarts:info in swofty/session.json game_log.channels; 'Reaction Time for driver with vehicle id %d: %f' prints per start"),
    ("race_start", "max_reaction_time_upper_bound", "float",
     "See max_reaction_time_lower_bound.", "yes", "A", "Consistency", "as above", "as above"),
    ("race_start", "min_reaction_time_lower_bound", "float",
     "See max_reaction_time_lower_bound.", "yes", "A", "Consistency", "as above", "as above"),
    ("race_start", "min_reaction_time_upper_bound", "float",
     "See max_reaction_time_lower_bound.", "yes", "A", "Consistency", "as above", "as above"),
    ("race_start", "max_bad_start_lower_bound", "float",
     "DECODED (same function): bad-start (wheelspin/bog) magnitude drawn between bounds interpolated by the 'mistakes' characteristic; 'Race Start performance for driver with vehicle id %d: %f' logs it.",
     "yes", "A", "Consistency, Risk", "Consistency down -> widen the spread; mistakes already moves the centre",
     "RaceStarts:info log channel"),
    ("race_start", "max_bad_start_upper_bound", "float",
     "See max_bad_start_lower_bound.", "yes", "A", "Consistency", "as above", "as above"),
    ("race_start", "min_bad_start_lower_bound", "float",
     "See max_bad_start_lower_bound.", "yes", "A", "Consistency", "as above", "as above"),
    ("race_start", "min_bad_start_upper_bound", "float",
     "See max_bad_start_lower_bound.", "yes", "A", "Consistency", "as above", "as above"),
    ("race_start", "stationary_vehicle_space", "float",
     "Space kept around stationary vehicles at the start.",
     "no", "C", "-", "safety/geometric", "Leave stock"),
    # ---------------------------------------------------------------- divebomb_defense (4)
    ("divebomb_defense", "max_presence_alongside", "float",
     "How far alongside a divebombing attacker must be before the defender yields the corner.",
     "no", "B", "Aggression", "Aggression up -> value up (yields later)",
     "Verify by contact count; this is the 'bashes you in corners' complaint area"),
    ("divebomb_defense", "max_time_to_ignore", "float",
     "Seconds the defender ignores a divebomb attempt before reacting.",
     "no", "B", "Aggression", "Aggression up -> value up",
     "As above"),
    ("divebomb_defense", "max_track_offset", "float",
     "Lateral offset limit within which divebomb defence applies.",
     "no", "C", "-", "geometric", "Trace"),
    ("divebomb_defense", "max_track_radius", "float",
     "Corner radius limit within which divebomb defence applies.",
     "no", "C", "-", "geometric", "Trace"),
    # ---------------------------------------------------------------- cede_position (6)
    ("cede_position", "ceding_radius", "float",
     "Corner radius inside which the driver cedes position when required.",
     "no", "C", "-", "rules (blue flags / yielding)", "Leave stock"),
    ("cede_position", "flying_lap_yield_to_human_track_speed_diff", "float",
     "Qualifying courtesy: speed difference at which an AI on an out-lap yields to a human on a flying lap.",
     "no", "C", "-", "fairness to the player", "Leave stock"),
    ("cede_position", "ignore_ceding_over_speed", "float",
     "Above this speed the driver does not cede.",
     "no", "C", "-", "rules", "Leave stock"),
    ("cede_position", "max_cede_time_ratio", "float",
     "Upper bound of the time ratio used when ceding.",
     "no", "C", "-", "rules", "Leave stock"),
    ("cede_position", "min_cede_time_ratio", "float",
     "Lower bound of the time ratio used when ceding.",
     "no", "C", "-", "rules", "Leave stock"),
    ("cede_position", "yellow_flag_ramp_up_time", "float",
     "Seconds over which the driver ramps its yellow-flag response.",
     "no", "C", "-", "rules; relevant to the 'AI overtakes under yellow' complaint but global, not personality",
     "Separate balancing issue, see HANDOFF"),
    # ---------------------------------------------------------------- alongside (8)
    ("alongside", "min_presence_within_buffer", "float",
     "Presence (overlap) needed for a car to count as alongside.",
     "no", "C", "-", "geometric", "Trace"),
    ("alongside", "off_target_angle_interpolation", "float",
     "Interpolation of the steering target angle while alongside.",
     "no", "C", "-", "controller-level", "Trace"),
    ("alongside", "offset_limiter_to_vehicle_blend_graph", "curve",
     "Curve blending the offset limiter toward the neighbouring vehicle.",
     "no", "C", "-", "controller-level", "Trace"),
    ("alongside", "speed_difference_for_limited_zone_yielding", "float",
     "Speed difference at which the driver yields inside a limited-overtake track zone.",
     "no", "C", "-", "interacts with track markup (the Aggressive AI track pack removes those zones)", "Trace"),
    ("alongside", "steering_understeer_offset", "float",
     "Steering offset applied when understeering while alongside.",
     "no", "C", "-", "controller-level", "Trace"),
    ("alongside", "steering_understeer_slip_max_throttle", "float",
     "Throttle cap under understeer slip while alongside.",
     "no", "C", "-", "controller-level", "Trace"),
    ("alongside", "trailbrake_speed_reduction_scalar", "float",
     "Scales the trail-braking speed reduction while alongside.",
     "no", "C", "-", "controller-level", "Trace"),
    ("alongside", "yield_overtake_rate", "float",
     "Rate at which the driver yields to a car that is alongside and ahead.",
     "no", "B", "Aggression", "Aggression up -> value down (holds the line longer)",
     "Verify by contact count"),
    # ---------------------------------------------------------------- exit_fallibility (2)
    ("exit_fallibility", "throttle_error_practice", "curve",
     "DECODED (Ai_Read_GeneralSettings_3 0x1405f5dd0): once per corner exit a random number is mapped through THIS curve (per-driver data +0x348) in practice sessions (session types 1-4), scaled, then capped by the per-CAR ai_vehicle_config.exit_fallibility.max_throttle_error_by_mass / by_grip_dry / by_grip_wet; nothing is added while yaw exceeds max_yaw_angle_deg. The 'throttle_exit_fallibility' parameter map (control characteristic) scales it too (0.75x at high control).",
     "yes", "A", "Consistency", "Consistency down -> shift the curve up (bigger, more frequent errors); stock curve must be dumped first",
     "swofty db get on one driver for the stock curve; then compare telemetry throttle traces at exits"),
    ("exit_fallibility", "throttle_error_qualifying_race", "curve",
     "As throttle_error_practice, for session types 5-18 (qualifying, sprint, race).",
     "yes", "A", "Consistency", "as above; this is the one that matters in races",
     "as above"),
    # ---------------------------------------------------------------- offset_variation (7)
    ("offset_variation", "blend_rate_inside_of_curve", "float",
     "Blend rate of the line offset on the inside of a curve.",
     "no", "C", "-", "controller-level", "Trace"),
    ("offset_variation", "blend_rate_outside_of_curve", "float",
     "Blend rate of the line offset on the outside of a curve.",
     "no", "C", "-", "controller-level", "Trace"),
    ("offset_variation", "half_width_scaling_graph", "curve",
     "Curve scaling the offset by track half-width.",
     "no", "C", "-", "geometric", "Trace"),
    ("offset_variation", "max_offset", "float",
     "Maximum lateral offset from the ideal line the driver may wander.",
     "no", "B", "Consistency", "Consistency down -> value up (scrappier lines); hypothesis, parser not identified",
     "Dump stock; vary one driver 2x; compare world_pos traces from the telemetry feed against a clean driver"),
    ("offset_variation", "offset_limit_at_corner_start", "float",
     "Offset limit at the start of a corner.",
     "no", "C", "-", "geometric", "Trace"),
    ("offset_variation", "offset_limit_blend_distance", "float",
     "Distance over which the offset limit blends in.",
     "no", "C", "-", "geometric", "Trace"),
    ("offset_variation", "radius_scalar_graph", "curve",
     "Curve scaling the offset by corner radius.",
     "no", "C", "-", "geometric", "Trace"),
]

assert len(ENTRIES) == 84, len(ENTRIES)
FIELDS = ["key", "group", "leaf", "type", "scope", "parser", "parser_addr", "parser_level", "parser_evidence",
          "what_re_says", "consumer_located", "blind_tunable", "verve_axis", "direction_hypothesis", "trace_needed"]


def rows():
    for g, leaf, typ, what, consumer, rating, axis, direction, trace in ENTRIES:
        p = PARSERS[g]
        yield {
            "key": f"entrants.drivers.driver_N.ai_driver_config.{g}.{leaf}",
            "group": g, "leaf": leaf, "type": typ, "scope": "per driver (driver row); stock identical on all 197 rows",
            "parser": p[0], "parser_addr": p[1], "parser_level": p[2], "parser_evidence": p[3],
            "what_re_says": what, "consumer_located": consumer, "blind_tunable": rating,
            "verve_axis": axis, "direction_hypothesis": direction, "trace_needed": trace,
        }


def write_csv(path: Path):
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        for r in rows():
            w.writerow(r)


def write_md(path: Path):
    out = []
    out.append("# `ai_driver_config` key catalogue (per driver, 84 keys)\n")
    out.append("Generated by `tools/build_catalogue.py`; edit that file, not this one. "
               "Scope: every key lives on `entrants.drivers.driver_N` and is **identical on all 197 stock rows** "
               "(RE note, `re/db/subsystems/ai.md` inbox 2026-10-29). None of these keys is in the launcher's key "
               "catalogue (`row_keys.txt.gz`). That does not block a plain `set`: `dbx.rs::set_text` resolves the key by its "
               "FNV hash and keeps the stock type tag (`packages/core/src/activation/dbx.rs`). It does matter for `add-row` "
               "copies of a driver (Driver Manager, Classic Seasons), where the names must be declared in the op file's "
               "`fields` block; Classic Seasons ships the full list in `addons/classicseasons/classic-seasons-2024/db/season.json`.\n")
    out.append("**Important discrepancy to resolve:** the parser notes in `re/db/functions.tsv` say these sections come "
               "\"from ai_vehicle_config\", but the leaf names match the per-driver `ai_driver_config.*` keys exactly, and the "
               "2026-10-29 inbox note says `ai_driver_config` is parsed per driver (`0x142463b40 -> 0x14065dc50 at 0x14246671e`, "
               "`default_driver` copy at `0x14249a4f0`). The per-car `ai_vehicle_config` has its own, differently named "
               "`blocking` (5 keys), `overtake` (4 keys) and `exit_fallibility` (4 keys) groups. Treat the function notes' "
               "attribution as loose wording until a trace confirms which struct each parser fills.\n")
    out.append("Rating: **A** consumer located and decoded, tune now. **B** direction hypothesised from the name, consumer "
               "not traced, vary in small steps and verify. **C** controller-level, geometric or rules; do not touch until traced.\n")
    counts = {}
    for r in rows():
        counts[r["blind_tunable"]] = counts.get(r["blind_tunable"], 0) + 1
    out.append(f"Totals: A = {counts.get('A',0)}, B = {counts.get('B',0)}, C = {counts.get('C',0)}.\n")
    cur = None
    for r in rows():
        if r["group"] != cur:
            cur = r["group"]
            p = PARSERS[cur]
            n = sum(1 for e in ENTRIES if e[0] == cur)
            out.append(f"\n## {cur} ({n})\n")
            out.append(f"Parser: `{p[0]}` {p[1]} [{p[2]}], {p[3]}.\n")
            out.append("| Key | Type | Rating | Verve axis | What the RE says | Direction hypothesis | Trace / verification |")
            out.append("|---|---|---|---|---|---|---|")
        esc = lambda s: s.replace("|", "\\|")
        out.append(f"| `{r['leaf']}` | {r['type']} | {r['blind_tunable']} | {esc(r['verve_axis'])} | {esc(r['what_re_says'])} "
                   f"| {esc(r['direction_hypothesis'])} | {esc(r['trace_needed'])} |")
    out.append("\n## Sources\n")
    out.append("- `re/db/functions.tsv` rows for the parsers and consumers named above (Swofty Launcher repo, commit of 2026-10-30)")
    out.append("- `re/db/subsystems/ai.md` (vocabulary, inbox notes 2026-10-28/29)")
    out.append("- `addons/classicseasons/classic-seasons-2024/db/season.json` `fields` block (the 84 key names)")
    out.append("- `native/src/gamelog/log_channels.tsv` (RaceStarts, CANNED_EVENTS, AI_VARIATION, QUALI_PACE_DEBUG channels)")
    path.write_text("\n".join(out) + "\n", encoding="utf-8")


if __name__ == "__main__":
    docs = ROOT / "docs"
    docs.mkdir(exist_ok=True)
    write_csv(docs / "ai_driver_config_keys.csv")
    write_md(docs / "ai_driver_config_keys.md")
    print("wrote", docs / "ai_driver_config_keys.csv", "and .md", f"({len(ENTRIES)} keys)")
