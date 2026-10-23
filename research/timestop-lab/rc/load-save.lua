-- In the LOAD screen: list the saves; with ARGS.file (a save folder name, e.g.
-- "000000000-Quick-Save"), select that save the way its list row does (the list's variable
-- currentSave) and queue the stock Load button's click (the QA menu's CBRTSQA_LOAD).
local function on(name)
    local value = Infinity_IsMenuOnStack(name)
    return value ~= nil and value ~= false and value ~= 0
end
assert(on("LOAD"), "EXPECTED_MENU:LOAD")
assert(not Infinity_GetTransitionInProgress(), "TRANSITION_IN_PROGRESS")
assert(type(gameSaves) == "table" and type(gameSaves.files) == "table", "NO_SAVE_LIST")
local saves, row = {}, nil
for index, entry in ipairs(gameSaves.files) do
    saves[#saves + 1] = {file = tostring(entry.fileName), slot = tostring(entry.slotName), time = tostring(entry.time),
        file_time = entry.fileTime}
    if type(ARGS) == "table" and ARGS.file and tostring(entry.fileName) == ARGS.file then
        assert(row == nil, "AMBIGUOUS_SAVE")
        row = index
    end
end
if type(ARGS) ~= "table" or not ARGS.file then return {saves = saves} end
assert(row, "SAVE_NOT_FOUND")
currentSave = row
Infinity_ClickItem(assert(nameToItem.CBRTSQA_LOAD, "QA_ITEM_MISSING:CBRTSQA_LOAD"))
return {queued = "CBRTSQA_LOAD", row = row, file = ARGS.file, saves = saves, frame = Infinity_GetFrameCounter()}
