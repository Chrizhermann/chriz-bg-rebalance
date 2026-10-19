-- Conversation through the stock WORLD_DIALOG_CONFIRM button (queued click).
-- ARGS.mode = "confirm-on" | "confirm-off": set the game's confirm-dialogue option, under
--   which the reply list only selects and the button answers. Nothing is clicked.
-- ARGS.mode = "step": with replies, select ARGS.row (default 1) in the reply list's own
--   variable, then queue the button click; without replies the button continues.
local function on(name)
    local value = Infinity_IsMenuOnStack(name)
    return value ~= nil and value ~= false and value ~= 0
end
assert(type(ARGS) == "table" and type(ARGS.mode) == "string", "ARGS.mode required")
if ARGS.mode == "confirm-on" or ARGS.mode == "confirm-off" then
    local before = gameOptions.m_bConfirmDialog
    gameOptions.m_bConfirmDialog = ARGS.mode == "confirm-on"
    return {before = before, after = gameOptions.m_bConfirmDialog}
end
assert(ARGS.mode == "step", "UNKNOWN_MODE")
assert(on("WORLD_DIALOG"), "EXPECTED_MENU:WORLD_DIALOG")
assert(not Infinity_GetTransitionInProgress(), "TRANSITION_IN_PROGRESS")
local replies = {}
for index = 1, #worldPlayerDialogChoices do replies[index] = getDialogEntryText(index) end
if #replies > 0 then
    assert(gameOptions.m_bConfirmDialog == true, "CONFIRM_MODE_REQUIRED")
    local row = tonumber(ARGS.row or "1")
    assert(row and row >= 1 and row <= #replies and row % 1 == 0, "INVALID_ROW")
    worldPlayerDialogSelection = row
end
assert(getDialogButtonEnabled() and getDialogButtonClickable(), "DIALOG_BUTTON_NOT_CLICKABLE")
Infinity_ClickItem(assert(nameToItem.CBRTSQA_DIALOG_CONFIRM, "QA_ITEM_MISSING:CBRTSQA_DIALOG_CONFIRM"))
return {npc = worldNPCDialogText, replies = replies, selected = worldPlayerDialogSelection,
    button = dialogButtonText}
