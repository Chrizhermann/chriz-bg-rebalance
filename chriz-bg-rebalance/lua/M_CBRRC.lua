-- The clock hook belongs to the process. Loads only reset its session counters.
CBRRC = CBRRC or {}
if CBRRC.queued then return end
CBRRC.queued = true
local ok, why = pcall(function()
    assert(EEex_Active, "EEex is not active; start the game through InfinityLoader")
    assert(type(EEex_GameState_AddInitializedListener) == "function", "missing EEex_GameState_AddInitializedListener")
    assert(type(Infinity_DoFile) == "function", "missing Infinity_DoFile")
    Infinity_DoFile("CBRRC")
    assert(CBRRC.core and type(CBRRC.Start) == "function", "CBRRC.lua did not load")
    EEex_GameState_AddInitializedListener(CBRRC.Start)
end)
if not ok then
    CBRRC.refused = tostring(why):gsub("[\r\n]+", " ")
    print("[CBR Round Clock] off, the game stays native: "..CBRRC.refused)
end
