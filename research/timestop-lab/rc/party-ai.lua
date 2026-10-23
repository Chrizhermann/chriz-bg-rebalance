-- ARGS.want = "off" | "on": the party AI the world's AI button switches (game:ToggleAI), toggled
-- only when needed. Off in the Time Clocks cases, so no party member acts on its own script.
assert(type(ARGS) == "table" and (ARGS.want == "off" or ARGS.want == "on"), "ARGS.want required")
local game = EngineGlobals.g_pBaldurChitin.m_pObjectGame
assert(game.m_bGameLoaded ~= 0 and game.m_bGameLoaded ~= false, "NO_GAME")
assert(worldScreen == e:GetActiveEngine(), "NOT_THE_WORLD_SCREEN")
local function state()
    local value = _G.game:GetPartyAI()
    return value ~= nil and value ~= false and value ~= 0
end
local before = state()
local want = ARGS.want == "on"
if before ~= want then _G.game:ToggleAI() end
local after = state()
assert(after == want, "PARTY_AI_UNCHANGED")
return {before = before, after = after, toggled = before ~= want}
