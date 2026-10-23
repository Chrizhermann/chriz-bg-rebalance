-- Quick save through the world's own quick save button (the QA menu's CBRTSQA_QUICKSAVE), the
-- way a click on it does. Only in the world screen, paused, without a transition or a dialogue,
-- and with the sidebar clickable; the game itself may still refuse to save (its own message).
-- The new save is the profile's newest quick save folder (the driver compares BALDUR.GAM times).
local function on(name)
    local value = Infinity_IsMenuOnStack(name)
    return value ~= nil and value ~= false and value ~= 0
end
local chitin = EngineGlobals.g_pBaldurChitin
local world, game = chitin.m_pEngineWorld, chitin.m_pObjectGame
assert(game.m_bGameLoaded ~= 0 and game.m_bGameLoaded ~= false, "NO_GAME")
assert(worldScreen == e:GetActiveEngine(), "NOT_THE_WORLD_SCREEN")
assert((tonumber(world.m_bPaused) or 0) ~= 0 or (tonumber(world.m_bHardPaused) or 0) ~= 0, "PAUSE_FIRST")
assert(not Infinity_GetTransitionInProgress(), "TRANSITION_IN_PROGRESS")
assert(not on("WORLD_DIALOG"), "IN_DIALOGUE")
assert(on("LEFT_SIDEBAR_BOTTOM"), "EXPECTED_MENU:LEFT_SIDEBAR_BOTTOM")
assert(sidebarsGreyed ~= 1, "SIDEBAR_GREYED")
Infinity_ClickItem(assert(nameToItem.CBRTSQA_QUICKSAVE, "QA_ITEM_MISSING:CBRTSQA_QUICKSAVE"))
return {queued = "CBRTSQA_QUICKSAVE", game_time = game.m_worldTime.m_gameTime,
    time_stop_remaining = EEex_Read32(EEex_UDToPtr(game) + 0x9690), frame = Infinity_GetFrameCounter()}
