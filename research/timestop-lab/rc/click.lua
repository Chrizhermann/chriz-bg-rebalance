-- Queue the normal click of one stock item the QA UI.MENU named (Infinity_ClickItem).
-- ARGS.item: a CBRTSQA_* name. ARGS.menu: the menu that must be on the stack.
-- ARGS.top (optional): the menu that must be the current screen.
local function on(name)
    local value = Infinity_IsMenuOnStack(name)
    return value ~= nil and value ~= false and value ~= 0
end
assert(type(ARGS) == "table" and type(ARGS.item) == "string" and type(ARGS.menu) == "string", "ARGS_REQUIRED")
assert(ARGS.item:match("^CBRTSQA_[A-Z0-9_]+$"), "QA_ITEM_REQUIRED")
assert(not Infinity_GetTransitionInProgress(), "TRANSITION_IN_PROGRESS")
assert(on(ARGS.menu), "EXPECTED_MENU:" .. ARGS.menu)
if ARGS.top then
    local top = Infinity_GetCurrentScreenName()
    assert(top == ARGS.top, "EXPECTED_TOP:" .. ARGS.top .. " got " .. tostring(top))
end
Infinity_ClickItem(assert(nameToItem[ARGS.item], "QA_ITEM_MISSING:" .. ARGS.item))
return {queued = ARGS.item, frame = Infinity_GetFrameCounter()}
