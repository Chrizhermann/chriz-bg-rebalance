-- In CHARACTER_SELECT: select one pregenerated character file shipped with the game, the way
-- the list's own row click does (its variable and action), then queue the stock Done click.
-- ARGS.character: the exact list name, e.g. "Abdel - Fighter - Neutral Good".
local function on(name)
    local value = Infinity_IsMenuOnStack(name)
    return value ~= nil and value ~= false and value ~= 0
end
assert(type(ARGS) == "table" and type(ARGS.character) == "string", "ARGS.character required")
assert(on("CHARACTER_SELECT"), "EXPECTED_MENU:CHARACTER_SELECT")
local rows, row = {}, nil
for index, entry in ipairs(character_select) do
    rows[#rows + 1] = tostring(entry.name)
    if tostring(entry.name) == ARGS.character then
        assert(row == nil, "AMBIGUOUS_CHARACTER")
        row = index
    end
end
assert(row, "CHARACTER_NOT_FOUND")
selectedCharacter = row
Infinity_OnCharacterImportItemSelect(row - 1)
Infinity_ClickItem(assert(nameToItem.CBRTSQA_CS_DONE, "QA_ITEM_MISSING:CBRTSQA_CS_DONE"))
return {row = row, rows = rows}
