// verve.skip skeleton (#65): reads and logs its settings. It installs no game hooks and skips nothing.
//
// The hooks wait for the trace: docs in #65 say to record the real state and event sequence first (Time Trial garage,
// race grid and podium), ask the game to end a scene rather than jump states, swallow the press that triggers a skip,
// and stop auto-skipping a scene type if the next state doesn't arrive within about 5 s.
#include <string_view>

#include <swofty/mixin.hpp>

SWOFTY_SETTING(std::string_view, skip_mode, "button");
SWOFTY_SETTING(std::string_view, skip_input, "game_action");
SWOFTY_SETTING(int, skip_wheel_button, -1);
SWOFTY_SETTING(std::string_view, skip_key, "space");
SWOFTY_SETTING(bool, skip_garage_pushin, true);
SWOFTY_SETTING(bool, skip_scene_podium, true);
SWOFTY_SETTING(bool, skip_scene_grid, true);
SWOFTY_SETTING(bool, skip_scene_garage, true);
SWOFTY_SETTING(bool, skip_scene_results, true);
SWOFTY_SETTING(bool, skip_scene_terminal_damage, true);
SWOFTY_SETTING(bool, skip_scene_intro_flag, true);
SWOFTY_SETTING(bool, skip_scene_track_extras, true);

SWOFTY_ON_CHANGE(skip_mode, std::string_view mode)
{
    swofty::log("[verve.skip] skip_mode is now %.*s", int(mode.size()), mode.data());
}

SWOFTY_ON_CHANGE(skip_input, std::string_view input)
{
    swofty::log("[verve.skip] skip_input is now %.*s", int(input.size()), input.data());
}

SWOFTY_ON_LOAD
{
    std::string_view mode = skip_mode, input = skip_input, key = skip_key;
    swofty::log("[verve.skip] skeleton loaded, no hooks installed: mode %.*s, input %.*s, wheel button %d, key %.*s, "
                "garage push-in %d, scenes podium %d grid %d garage %d results %d terminal_damage %d intro_flag %d "
                "track_extras %d",
                int(mode.size()), mode.data(), int(input.size()), input.data(), int(skip_wheel_button),
                int(key.size()), key.data(), int(bool(skip_garage_pushin)), int(bool(skip_scene_podium)),
                int(bool(skip_scene_grid)), int(bool(skip_scene_garage)), int(bool(skip_scene_results)),
                int(bool(skip_scene_terminal_damage)), int(bool(skip_scene_intro_flag)),
                int(bool(skip_scene_track_extras)));
}

SWOFTY_ADDON()
