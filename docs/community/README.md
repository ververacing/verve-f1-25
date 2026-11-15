# Community addons: reference pages

Date: 2026-11-14. Five community F1 25 addons for the Swofty launcher. Each page lists what the addon touches, with stock and addon values and where each value comes from.

| Addon | Version | Summary |
|---|---|---|
| [Lap 1 Realistic AI](swofty.lap1-ai.md) (`swofty.lap1-ai`) | 1.0.0 | Lap 1 only: 30 live AI layers (10 % more grip, earlier and longer overtakes, defence from 45 m, quicker queue exits). No settings. Closed DLL; lever table in its README. |
| [AI Driver Behaviour](kizi.ai-driver-behaviour.md) (`kizi.ai-driver-behaviour`) | 0.1.9 (repo 0.1.8) | 17,131 database sets: car gap, make-room point, per-driver spread, steering PID, traction control, slide limits, damaged-car pace. Pace options removed in 0.1.7. MIT, source public. |
| [Contact Physics](kizi.ai-tweaks.md) (`kizi.ai-tweaks`) | 0.6.2 | Rigid-body car contact for every car, AI reaction time after hits, softening off, punctures. Memory only, no racecraft keys. MIT, source public. Not installed here. |
| [F1 25 + 26 Aggressive AI (Alternate)](kizi.f1-25-more-aggresive-ai-2.md) (`kizi.f1-25-more-aggresive-ai-2`) | 2.0.1 | Replaces the `.aispline`, `.tsmd` and `.trackmarkup` of 28 layouts. Data only, binary track files, licence not stated. Not installed here. |
| [Skip Cutscenes](dromodf.skip-cutscenes.md) (`dromodf.skip-cutscenes`) | 1.9.4 | Skips cutscenes with the accept button, or removes them (intros, grid, rundown, celebration, podium, career hub). Native hooks only. MIT, source shipped. |

None of the five touches a `cede_position.*`, `yellow_flag_*` or `flying_lap_yield_*` key.

## Sources used

- Swofty public catalog, `https://api.f1.swofty.net/v1/addons` (pulled 2026-11-14): all five entries.
- Installed copies, read only, in `%LOCALAPPDATA%\Swofty\addons\<id>\`: `swofty.lap1-ai`, `kizi.ai-driver-behaviour`, `dromodf.skip-cutscenes` (manifests, READMEs, data ops, shipped source).
- Public GitHub repos: `https://github.com/Kizikafuka/f1-25-ai-driver-behaviour`, `https://github.com/Kizikafuka/f1-25-contact-physics`.
- The `kizi.f1-25-more-aggresive-ai-2` 2.0.1 package from the catalog download URL (sha256 matches the catalog). Text files read; track files listed, not decoded.
- `swofty addons list` and `swofty settings list <id> --profile verve-test` (read only, Swofty 1.9.51).
- Stock values: `docs/stock/ai_driver_config.csv` and `docs/stock/ai_vehicle_config_redbull_2025.txt` (Swofty 1.6.11 dump, build 25251167).

No closed DLL was disassembled or decompiled. Lap 1 Realistic AI's DLL has no public source; its page uses the catalog and the installed README only.
