---
name: Race batch
about: A controlled A/B set of test races; one change per batch
title: "[race-batch] B-0000: <change>"
labels: race-batch
---

```yaml
batch_id: B-0001
hypothesis: "<one sentence with predicted direction>"
variant: <ops file or generator flags + git sha>
control: <stock or previous variant sha>
change: <the ONE key or knob changed>
track: <label>        # short lap, e.g. austria
mode: grand_prix
laps: 5
weather: dry_fixed
difficulty: 100
grid: fixed
variation_off: true   # race-form curves + canned DNFs off for isolation
repeats: 5            # per arm
metrics: [reaction_time, overtakes_made, overtakes_suffered, collisions, braking_point, lap_spread, dnf]
```

**Results:** a PR adding `runs/<date>-<batch_id>-<arm>/` (loader.log, ops sha256, summary.csv) plus a comment with
medians and ranges per arm. The supervisor reviews, then closes or queues the follow-up.
