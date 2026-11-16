# DRAFT, NOT POSTED: Swofty issue on the test agent's player-car control on Steam 1.0.145

Status: draft for Tyler's decision (supervisor, 2026-11-16). Nothing here has been sent anywhere. It contains no
account names, paths or personal details; keep it that way if it is posted.

---

**Title:** `ai_drives_player` unavailable on Steam 1.0.145 (build 26566308): car field offsets are KB-build only

**Versions:** Swofty Launcher 1.9.58 and 1.9.59, swofty.core 0.2.13, F1 25 Steam 1.0.145.2472 (build 26566308),
Windows 10.

**What happens:** in a `swofty test shell` session on Steam 1.0.145, the test agent's `ai_drives_player` command
returns:

```
{"status":"unavailable","error":"the player's car: the car field offsets are the KB build's and this is not that build"}
```

The agent's `status` reports `ai_drives_player: ok` but `car: the car field offsets are the KB build's and this is
not that build`. So the command looks available, but it fails as soon as it is called in a race. As far as we can
read it, `car_unbound()` in `native/src/core/testagent/agent.cpp` refuses whenever `runtime::same_build()` is false,
and `live_car::kb_fields()` is true on the KB build only. The test agent's `title`, `resume` and `advance` bindings
report the same KB-build message.

**What still works on 1.0.145:** route, pad, wait screen, the save sandbox (verified by
`bindings.steam-26566308.json`), add-on loading, and the menu flow to a Grand Prix and through the grid to the race.

**Impact:** unattended test sessions can't hand the player's car to the AI, so it sits on the grid and is
black-flagged (DSQ about 20 s in, retired about 30 s in). Any automated AI-only race test on Steam 1.0.145 is blocked
until the car field offsets are ported.

**Ask:** are the live-car field offsets (and the AI-control flag `ai_drives_player` sets) planned for 1.0.145? Is
there a supported interim route for AI-only test races?

**Repro:**
1. On Steam 1.0.145, run `swofty test shell` on any profile with a plan that reaches a Grand Prix race.
2. At the garage monitor, send `{"cmd":"ai_drives_player","args":{"on":true}}`.
3. The reply is `unavailable` with the message above.
