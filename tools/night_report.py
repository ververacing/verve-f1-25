"""Turn a testing window's run folders into one summary, for a fast morning review.

Usage:
    python -I tools/night_report.py runs/<folder or glob prefix> [more] [--out runs/<id>/night_report.md]

Example:
    python -I tools/night_report.py runs/2026-11-04-*          # PowerShell: pass the folders; the script globs too

A run is any folder holding transcript.txt (tools/sandbox_run.ps1 -Session) or report.json (`swofty test run`). Runs
in the same parent folder form a batch; a run with no batch folder stands alone. Each run gets a status:

    pass, fail, invalid   from the batch's own check, where it has one (BATCH_CHECKS)
    ran                   finished with no checks to score it
    problem               the plan or test stopped early, or the sandbox wasn't confirmed
    SAVES CHANGED         Tyler's saves or Steam's records changed: stop and read this first

Reads only. It never runs the game, and it doesn't replace reading a batch's own summary. Exit 1 if any run's saves
changed, otherwise 0.
"""
from __future__ import annotations

import csv
import glob
import json
import re
import subprocess
import sys
from pathlib import Path

# batch name in the folder name -> script in tools/ and its arguments; the first match wins, so longer names go first
BATCH_CHECKS = {"B-0012b": ("b0012_check.py", ["--menu"]), "B-0012": ("b0012_check.py", [])}
TOOLS = Path(__file__).resolve().parent
REACTION = re.compile(r"RaceStarts: Reaction Time")
GAMEDB = re.compile(r"gamedb: (\d+) overwritten, (\d+) created")
PLAN = re.compile(r"^plan: (.*?); test exit: (\S*); sandbox (.*?); took (\d+) s", re.M)
LAUNCH = re.compile(r"^(?:launched|attempt \d+ started) (\S+)", re.M)
SHELL_RESULT = re.compile(r"^result: (.*)$", re.M)
SEAT = re.compile(r"the player drives for (\S+) as (\S+)")
GRID_SIGNAL = re.compile(r"(\d\d:\d\d:\d\d\.\d+) .*\[test\] screen garage_monitor_container")
GREEN = re.compile(r"(\d\d:\d\d:\d\d\.\d+) .*RaceStarts: Reaction Time")


def seconds(stamp: str) -> float:
    h, m, s = stamp.rstrip(":").split(":")
    return int(h) * 3600 + int(m) * 60 + float(s)


def read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8-sig", errors="replace")
    except OSError:
        return ""


def find_runs(args: list[str]) -> list[Path]:
    found: set[Path] = set()
    for a in args:
        for root in [Path(p) for p in glob.glob(a)] or [Path(a)]:
            if not root.is_dir():
                continue
            for marker in ("transcript.txt", "report.json"):
                found.update(p.parent for p in root.rglob(marker) if "batches" not in p.parts)
    # a `test run` report sits in <run>/raw/: name the run, not its raw folder
    return sorted({p.parent if p.name == "raw" else p for p in found})


def batch_of(run: Path) -> str:
    return next((b for b in BATCH_CHECKS if b in str(run)), run.parent.name if run.parent.name != "runs" else "")


def scored(run: Path) -> tuple[str, str]:
    """Status and a one-line detail from the batch's own check, or ('', '') when it has none."""
    entry = next((c for b, c in BATCH_CHECKS.items() if b in str(run)), None)
    if not entry:
        return "", ""
    script, extra = entry
    out = subprocess.run([sys.executable, "-I", str(TOOLS / script), *extra, str(run)], capture_output=True, text=True).stdout
    result = re.search(r"RESULT: (PASS|FAIL|INVALID)", out)
    block = re.search(r"first block: (.*)", out)
    rolls = re.search(r"all logged re-rolls: (.*)", out)
    detail = "; ".join(m[1].strip() for m in (block, rolls) if m)
    why = re.findall(r"(?:FAIL|INVALID): (.*)", out)
    if why:
        detail += " | " + "; ".join(why[:3])
    return (result[1].lower() if result else "problem"), detail


def udp_summary(run: Path) -> str:
    rows = []
    try:
        with open(run / "udp" / "sessions.csv", newline="", encoding="utf-8") as f:
            rows = [r for r in csv.DictReader(f) if r.get("session_type")]
    except OSError:
        return "none"
    if not rows:
        return "no session data"
    return ", ".join(f"{r['session_type']} ({r['n_active']} cars)" for r in rows)


def summarise(run: Path) -> dict:
    transcript = read(run / "transcript.txt")
    log = read(run / "raw" / "loader.log") or read(run / "raw" / "batches" / "1" / "loader.log")
    plan = PLAN.findall(transcript)
    r = {"run": run.name, "batch": batch_of(run), "path": run, "detail": ""}

    diff = read(run / "saves_diff.txt").strip()
    # the guards always record it now; older runs only have the line in their transcript, or nothing
    recorded = (run / "saves_diff.txt").exists() or "saves unchanged" in transcript
    r["saves"] = "CHANGED" if diff else ("unchanged" if recorded else "?")
    db = GAMEDB.search(log)
    r["gamedb"] = f"{db[1]} / {db[2]}" if db else "-"
    seat = SEAT.search(log)
    r["seat"] = f"{seat[1]} / {seat[2]}" if seat else "-"
    r["starts"] = len(REACTION.findall(log))
    r["udp"] = udp_summary(run)

    launch, green = LAUNCH.findall(transcript), GREEN.search(log)
    r["to_green"] = "-"
    if launch and green:
        try:
            r["to_green"] = f"{seconds(green[1]) - seconds(launch[-1]):.0f} s"
        except ValueError:
            pass
    r["tries"] = len(launch) or 1

    status, detail = scored(run)
    if diff:
        status = "SAVES CHANGED"
    elif not status:
        report = None
        for p in (run / "raw" / "report.json", run / "report.json"):
            if p.exists():
                try:
                    report = json.loads(read(p))
                except ValueError:
                    pass
        if report is not None:
            tests = [t.get("status") for t in report.get("tests", [])]
            status = "ran" if tests and all(t == "pass" for t in tests) else "problem"
            detail = ", ".join(str(t.get("reason") or t.get("status")) for t in report.get("tests", []))[:160]
        elif plan and plan[-1][0] == "plan done" and plan[-1][2] == "ON":
            status = "ran"
        elif SHELL_RESULT.search(transcript) and SHELL_RESULT.search(transcript)[1].strip() == "plan done":
            status = "ran"
        else:
            status = "problem"
            detail = (plan[-1][0] if plan else "no plan line in the transcript")[:160]
    r["status"], r["detail"] = status, detail
    return r


def render(runs: list[dict]) -> str:
    lines = ["# Testing window report", ""]
    changed = [r for r in runs if r["status"] == "SAVES CHANGED"]
    if changed:
        lines += [f"**SAVES CHANGED in {', '.join(r['run'] for r in changed)}: stop sandbox runs and tell Tyler.**", ""]
    else:
        unknown = [r["run"] for r in runs if r["saves"] == "?"]
        if unknown:
            lines += [f"Saves and Steam's records: no run reports a change, but {len(unknown)} of {len(runs)} left no "
                      "record of the check. Compare with the last-known-good snapshot.", ""]
        else:
            lines += ["Saves and Steam's records: unchanged on every run.", ""]
    batches: dict[str, list[dict]] = {}
    for r in runs:
        batches.setdefault(r["batch"] or "(single runs)", []).append(r)
    for name, group in batches.items():
        counts = {s: sum(1 for r in group if r["status"] == s) for s in dict.fromkeys(r["status"] for r in group)}
        tally = ", ".join(f"{n} {s}" for s, n in counts.items())
        lines += [f"## {name}: {tally}", ""]
        lines += ["| Run | Status | Launch to green | Tries | gamedb | Seat | Reaction lines | UDP | Saves |",
                  "|---|---|---|---|---|---|---|---|---|"]
        for r in group:
            lines.append(f"| {r['run']} | {r['status']} | {r['to_green']} | {r['tries']} | {r['gamedb']} | {r['seat']} "
                         f"| {r['starts']} | {r['udp']} | {r['saves']} |")
        notes = [r for r in group if r["detail"]]
        if notes:
            lines.append("")
            lines += [f"- **{r['run']}:** {r['detail']}" for r in notes]
        lines.append("")
    return "\n".join(lines)


def main() -> int:
    args = sys.argv[1:]
    out = None
    if "--out" in args:
        i = args.index("--out")
        out = Path(args[i + 1])
        args = args[:i] + args[i + 2:]
    if not args:
        print(__doc__)
        return 2
    runs = [summarise(p) for p in find_runs(args)]
    if not runs:
        print("no runs found")
        return 2
    text = render(runs)
    if out:
        out.write_text(text, encoding="utf-8")
    sys.stdout.reconfigure(encoding="utf-8")
    print(text)
    return 1 if any(r["status"] == "SAVES CHANGED" for r in runs) else 0


if __name__ == "__main__":
    sys.exit(main())
