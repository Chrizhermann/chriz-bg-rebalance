-- ARGS.want = "paused" | "running": toggle the engine's own pause only when needed, so a
-- pause the game took by itself (autopause) is reported instead of being undone.
assert(type(ARGS) == "table" and (ARGS.want == "paused" or ARGS.want == "running"), "ARGS.want required")
local chitin = EngineGlobals.g_pBaldurChitin
local world, game = chitin.m_pEngineWorld, chitin.m_pObjectGame
assert(game.m_bGameLoaded ~= 0, "NO_GAME")
local function state()
    return {paused = (tonumber(world.m_bPaused) or 0) ~= 0 or (tonumber(world.m_bHardPaused) or 0) ~= 0,
        game_time = game.m_worldTime.m_gameTime, clock = Infinity_GetClockTicks()}
end
local before = state()
local want = ARGS.want == "paused"
if before.paused ~= want then EEex_GameState_TogglePause(false, true, false, 0, true) end
local after = state()
assert(after.paused == want, "PAUSE_STATE_UNCHANGED")
return {before = before, after = after, toggled = before.paused ~= want}
