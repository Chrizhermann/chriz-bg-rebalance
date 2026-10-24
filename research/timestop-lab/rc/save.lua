-- The stock load screen's save list (menu LOAD). ARGS.op = "list": read only. ARGS.op = "select":
-- selects one save (the list's own currentSave variable, as a click on its row would), so the
-- named Load button loads it: ARGS.file names its folder exactly (fileName), or ARGS.prefix starts
-- its name; refuses no or several matches.
-- A row shows the save's name from slotName; sName is the party leader's name. The engine rotates
-- quick saves through several folders (Quick-Save, Quick-Save-2, ...), so a prefix can be ambiguous.
assert(type(ARGS) == "table" and (ARGS.op == "list" or ARGS.op == "select"), "ARGS.op required")
local value = Infinity_IsMenuOnStack("LOAD")
assert(value ~= nil and value ~= false and value ~= 0, "EXPECTED_MENU:LOAD")
assert(type(gameSaves) == "table" and type(gameSaves.files) == "table", "NO_SAVE_LIST")
local function given(name)
    return type(ARGS[name]) == "string" and #ARGS[name] > 0
end
assert(ARGS.op == "list" or (given("file") ~= given("prefix")), "ARGS.file or ARGS.prefix required")
local saves, match = {}, {}
for index, save in ipairs(gameSaves.files) do
    saves[#saves + 1] = {index = index, name = save.slotName, leader = save.sName, file = save.fileName}
    if ARGS.op == "select" then
        if given("file") and save.fileName == ARGS.file
                or given("prefix") and type(save.slotName) == "string"
                    and save.slotName:sub(1, #ARGS.prefix) == ARGS.prefix then
            match[#match + 1] = index
        end
    end
end
if ARGS.op == "select" then
    assert(#match == 1, "SAVE_MATCHES:" .. #match)
    currentSave = match[1]
end
return {saves = saves, current = currentSave}
