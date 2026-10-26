-- Read-only: the menu stack and what a hidden driver needs to decide its next request.
local function on(name)
    local value = Infinity_IsMenuOnStack(name)
    return value ~= nil and value ~= false and value ~= 0
end
local function try(f)
    local ok, value = pcall(f)
    if ok then return value end
    return "error: " .. tostring(value)
end
local stack = {}
for index = 0, EngineGlobals.nextStackMenuIdx - 1 do
    stack[#stack + 1] = try(function()
        local entry = EngineGlobals.menuStack:get(index)
        if type(entry) == "userdata" and entry.reference then entry = entry.reference end
        local name = entry.name
        if type(name) == "userdata" and name.get then name = name:get() end
        return tostring(name)
    end)
end
local chitin = EngineGlobals.g_pBaldurChitin
local game, world = chitin.m_pObjectGame, chitin.m_pEngineWorld
local out = {
    stack = table.concat(stack, " > "),
    top = Infinity_GetCurrentScreenName(),
    transition = Infinity_GetTransitionInProgress() and true or false,
    cutscene = Infinity_GetInCutsceneMode and try(Infinity_GetInCutsceneMode) or nil,
    start_state = startEngine and try(function() return startEngine:GetEngineState() end) or nil,
    game_loaded = game.m_bGameLoaded,
    paused = world and ((tonumber(world.m_bPaused) or 0) ~= 0 or (tonumber(world.m_bHardPaused) or 0) ~= 0),
    game_time = game.m_worldTime and game.m_worldTime.m_gameTime or nil,
    portrait0 = EEex_Sprite_GetInPortrait(0) ~= nil,
    portrait1 = EEex_Sprite_GetInPortrait(1) ~= nil,
    clock = Infinity_GetClockTicks(),
}
if on("CHARGEN") then
    out.chargen = {step = try(function() return createCharScreen:GetCurrentStep() end),
        complete = try(function() local v = createCharScreen:IsChargenComplete() return v ~= nil and v ~= false and v ~= 0 end)}
end
if on("POPUP_THREEBUTTON") and type(Popup3Button) == "table" then
    out.popup3 = {left = Popup3Button.leftText, mid = Popup3Button.midText, right = Popup3Button.rightText}
end
if on("WORLD_DIALOG") then
    local replies = {}
    for index = 1, #(worldPlayerDialogChoices or {}) do
        replies[index] = try(function() return getDialogEntryText(index) end)
    end
    out.dialog = {replies = replies, npc = worldNPCDialogText, button = dialogButtonText,
        confirm_mode = try(function() return gameOptions.m_bConfirmDialog end)}
end
return out
