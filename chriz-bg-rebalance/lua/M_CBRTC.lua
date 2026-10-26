-- Chriz BG Rebalance, Time Stop and Haste effect clocks (component 360): switches the correction
-- (CBRTC.lua) on once EEex reports the game state initialized, before the main menu, and keeps it
-- on across every load. Without EEex, on another executable or on anything else unexpected the
-- game stays native, and only the log says why.
if CBRTC and CBRTC.queued then return end
local function off(reason)
    print("[CBR Time Stop/Haste] off, the game stays native: "..reason)
end
if not EEex_Active then
    off("EEex is not active; start the game through InfinityLoader")
    return
end
if type(EEex_GameState_AddInitializedListener) ~= "function" then
    off("this EEex lacks EEex_GameState_AddInitializedListener")
    return
end
local loaded, why = pcall(Infinity_DoFile, "CBRTC")
if not (loaded and type(CBRTC) == "table" and CBRTC.core and type(CBRTC.Start) == "function") then
    off("CBRTC.lua did not load"..(loaded and "" or ": "..tostring(why)))
    return
end
CBRTC.queued = true
-- Start() checks everything before its first change and never raises; the pcall only keeps an
-- unforeseen error out of EEex's listener loop and in the log.
EEex_GameState_AddInitializedListener(function()
    local ok, err = pcall(CBRTC.Start)
    if not ok then off(tostring(err)) end
end)
