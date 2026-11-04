# Verve Skip (`verve.skip`)

Skip cutscenes and the garage push-in, on a press or automatically. Tracked in #65.

**This is a skeleton.** The settings load and show up in the launcher and in game, but it installs no game hooks and skips nothing.

## Build

```bash
powershell -File addons/verve-skip/native/build.ps1
```

This uses portable Zig, like Swofty's own addon template, so it needs no MSVC and no UAC prompt. The script's header says where Zig goes. The built DLL isn't committed.

## Settings

All apply live.

| Option | Values | Default |
|---|---|---|
| `skip_mode` | off, button, auto | button |
| `skip_input` | game_action, wheel_button, keyboard | game_action |
| `skip_wheel_button` | learned index, -1 for none | -1 |
| `skip_key` | space, enter | space |
| `skip_garage_pushin` | on, off | on |
| `skip_scene_*` | on, off: podium, grid, garage, results, terminal_damage, intro_flag, track_extras | on |

## Still to do, in order

1. **Trace.** Record the state and event sequence in the Time Trial direct-start garage, and on the race grid.
2. **Check the wheel.** Does the G29 raise `Menu Accept`? This needs Tyler at the wheel. If it doesn't, read the wheel through DirectInput with a learned button.
3. **Add the skip.** Ask the game to end the scene, never jump states. Swallow the press until the button is released, so it can't also fire `Start Race` or `Go to Track`.
4. **Add the watchdog.** If the next state doesn't arrive within about 5 s, stop auto-skipping that scene type for the session.

Acceptance is on #65.
