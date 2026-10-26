-- At the campaign logos: queue the click on the Shadows of Amn logo, then one click on the
-- inert QA label. On 2.7.3 the campaign choice closes START and reopens it only on the next
-- mouse event; a hidden game gets none, so the second click provides it.
local function on(name)
    local value = Infinity_IsMenuOnStack(name)
    return value ~= nil and value ~= false and value ~= 0
end
assert(on("START"), "EXPECTED_MENU:START")
for _, name in ipairs({"START_MAIN", "START_SP", "CHARGEN", "WORLD_ACTIONBAR"}) do
    assert(not on(name), "UNEXPECTED_MENU:" .. name)
end
assert(not Infinity_GetTransitionInProgress(), "TRANSITION_IN_PROGRESS")
local logo = assert(nameToItem.CBRTSQA_SOA, "QA_ITEM_MISSING:CBRTSQA_SOA")
local idle = assert(nameToItem.CBRTSQA_IDLE, "QA_ITEM_MISSING:CBRTSQA_IDLE")
Infinity_ClickItem(logo)
Infinity_ClickItem(idle)
return {queued = {"CBRTSQA_SOA", "CBRTSQA_IDLE"}, frame = Infinity_GetFrameCounter()}
