# Test runs

One folder per run: `runs/<YYYY-MM-DD>-<variant>/`, holding the run's `loader.log`, the SHA-256 of the ops file it
built, the telemetry/metrics CSV, and a short `summary.md` (what changed, what was measured, verdict). Raw captures go
in a `raw/` subfolder, which git ignores. See HANDOFF.md section 13.
