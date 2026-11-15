# Contact Physics

| | |
|---|---|
| Id | `kizi.ai-tweaks` (title "Contact Physics"; formerly "AI Racing Tweaks") |
| Version | 0.6.2 (catalog latest; GitHub `swofty.json`, `README.md` and `res/dll.rc` agree). **Not installed on this PC.** |
| Author | Kizi (`LICENSE`: "Kizikafuka and RK") |
| Licence | MIT (manifest, `LICENSE`, SPDX header in `ai_tweaks.cpp`) |
| Source | https://github.com/Kizikafuka/f1-25-contact-physics (catalog and manifest `repository`) |
| Game build | Catalog text: "Supported build: 25251167 or newer", Steam only (catalog `platforms: ["steam"]`, manifest `compat.platforms`). `docs/CONTACT_HANDLER_RE.md` is a read of the Steam exe with PE timestamp 1789118616 (2026-11-11). Code is found by byte patterns, not fixed addresses. |
| Launcher | `>=1.8.36` (manifest and catalog). The catalog text and `release/READ_ME_FIRST.txt` still say 1.7.0. |
| Requires | `swofty.core >=0.1.0` |
| Kind | native (one DLL, `native/kizi_ai_tweaks.dll`) |

Sources read: catalog entry (2026-11-14); the GitHub repo at `main`: `swofty.json`, `README.md`, `IDEAS.md`, `LICENSE`, `docs/CONTACT_HANDLER_RE.md`, `native/src/ai_tweaks.cpp`, `common/kizi_contact_sim.hpp`, `release/READ_ME_FIRST.txt`, `release/BUILD.txt`, `res/dll.rc`. Downloaded as text to the scratch area; nothing run. The release zip was not downloaded, so the shipped DLL was not compared with this source.

## What it changes

Memory only. No database ops and no game files ("Memory-only implementation", catalog; READ_ME_FIRST).

- **Rigid-body contact:** for every car-to-car touch it computes an impulse from both cars' mass, inertia, speeds and the contact point, with bounce and friction. Tyre-on-tyre contact adds the tyres' rolling speed. It applies the impulse with the game's own apply-impulse function. At most 4 pushes per car pair per physics step (READ_ME_FIRST).
- **AI cars are pushed too,** and AI-vs-AI touches count. The game itself only pushes the player's car (catalog, READ_ME_FIRST).
- **Softening off:** two in-memory game-database bools that soften every car-to-car hit are set to off.
- **AI reaction time:** after a hit the AI's steering is held at its value from the moment of the hit, so the hit can turn the car.
- **Punctures:** hard hits at a tyre can puncture it through the game's own puncture function.

The old simulated spin, twitch, lift and wheel-push settings were removed in 0.6.1. Their code is still in `ai_tweaks.cpp` but is inactive: `physics_mode` defaults to "realistic" and is not in the manifest (`ai_tweaks.cpp` line 48, `IDEAS.md`).

## Settings (manifest)

All apply live (catalog).

| Option id | Label | Values | Default |
|---|---|---|---|
| `exaggerate` | Contact: strength | Normal, x1.5, x2, x3 (scales bounce and friction) | Normal |
| `restitution` | Contact: bounce | Low 0.1, Medium 0.25, High 0.4 of closing speed | Medium |
| `friction` | Contact: friction | Off, Low x0.5, Medium (tyre 1.8, body 0.6), High x1.5 | Medium |
| `tyre_spin` | Contact: tyre rotation | on / off | on |
| `ai_impulse` | Contact: push AI cars | on / off | on |
| `engine_response` | Contact: game's own response | Add (game still fixes overlap), Ignore | Add |
| `reaction` | Contact: AI reaction time | Off, 0.2 s, 0.4 s, 0.6 s, Scales with the hit | Scales with the hit |
| `spin_who` | Contact: applies to | All contacts, Only contacts with you | All |
| `puncture` | Contact: tyre punctures | Off, Rare, Sometimes, Often | Sometimes |
| `puncture_you` | Contact: punctures can hit you | on / off | off |
| `softening` | Contact: softening | Off (realistic), Game default | Off |
| `osd_message` | On-screen messages | on / off | on |
| `contact_log` | Testing: log contacts | on / off | off |

Hotkey: Ctrl+F9 toggles softening until the game closes (catalog, READ_ME_FIRST).

## What it touches

No `driver_characteristics.*`, `ai_driver_config.*`, `ai_vehicle_config.*` or `.aispline` data. Provenance: **A:n** = `native/src/ai_tweaks.cpp` line n; **K:n** = `common/kizi_contact_sim.hpp` line n.

| Target | Stock | Addon | Provenance |
|---|---|---|---|
| Contact assist B ("inertia"): in-memory game-database bool, found by byte pattern `ASSIST_B`. Key name not given. | on (READ_ME_FIRST: "game: on") | off when `softening` = Off; put back to the game's value when set to Game default | A:5-8, 76, 242-273, 917 |
| Contact assist A ("velocity"): in-memory game-database bool, pattern `ASSIST_A`. Key name not given. | on | same as above | A:78, 918 |
| Car contact modifier callback (RVA 0x2f04040 on the build it was read from): a jump stub at the `ASSIST_A` site runs the addon's in-step hook for each contact | game response only | adds the rigid-body impulse; `engine_response` = Ignore also drops the game's own response | A:98-123, 919; `docs/CONTACT_HANDLER_RE.md` |
| Bounce (restitution), addon's own impulse | not applicable | 0.1 / 0.25 / 0.4, times strength, capped at 0.8 | K:234-238, 372 |
| Friction, addon's own impulse | not applicable | tyre 1.8, body 0.6, times 0.5 / 1.0 / 1.5 and strength, capped at 3.0 | K:239-243, 401 |
| Strength, addon's own scale | not applicable | 1 (Normal), 1.5, 2, 3 | K:246-250 |
| AI steering after a hit (copies the AI controller vtable, restores the steering value from the moment of impact) | game reaction | Scaled: 100 ms + 900 ms x smoothstep((closing speed - 1 m/s) / 9 m/s), 0.1 s to 1.0 s; or fixed 0.2 / 0.4 / 0.6 s | A:588-598; catalog "Technical Details" |
| Puncture chance per hard tyre hit | no contact punctures | Rare 0.15, Sometimes 0.35, Often 0.7, times clamp((km/h - 10) / 50, 0, 1) | A:480-484, 718 |
| Wheel-to-wheel push params (3 floats; game ships grip -1, scale 0, cap 0) | off | Not written in the current "realistic" mode | A:9-12, 228-239 |

The softening bools: `ai_tweaks.cpp` does not name the database keys. It finds them by code pattern. `IDEAS.md` #15 names `collision_assistance.collisionMassModifier_human/_ai` and `difficulty.collision_impact_modifiers` for a future idea ("not built yet"); those are a different thing (the player's heavier collision mass, 50 vs 45).

## Protected keys

None. No `cede_position.*`, `yellow_flag_*` or `flying_lap_yield_*` key, and no AI racecraft key at all.

## Stacks and conflicts

- Do not run with **Contact Sim Light** or **Contact Sim Heavy** (`kizi.contact-sim-light` / `kizi.contact-sim-heavy`): same hook, only one stays active (catalog, READ_ME_FIRST). Neither is in the public catalog today.
- AI Driver Behaviour handles racecraft and car control; the two "work well together". AI Driver Behaviour's `registry.json` conflicts with this addon below 0.5.0 only.
- Lap 1 Realistic AI says it stacks with this one (Lap 1 catalog).

## What the authors admit

- "Experimental: Physics values are tuned through test races and are not yet fully validated."
- Tested only in Grand Prix races on the Steam build. Practice, qualifying, Career and My Team not tested.
- Game updates may break it; a component that is not found logs `NOT installed` or `NOT found` and stays off.
- The flat-tyre visual is "not thoroughly verified".
- READ_ME_FIRST: "the effect on racing is tuned by test races, not proven, and may be unstable. Back up your save."

## Not determined

- The real database key names of the two softening bools.
- Whether the shipped 0.6.2 DLL matches the GitHub source (zip not downloaded).
- No measured effect on racing is published.
