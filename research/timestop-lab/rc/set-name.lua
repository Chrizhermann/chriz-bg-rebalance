-- In CHARGEN_NAME: fill the name edit's own variable, then queue the stock Done click.
-- ARGS.name: 1-20 visible characters.
local function on(name)
    local value = Infinity_IsMenuOnStack(name)
    return value ~= nil and value ~= false and value ~= 0
end
assert(type(ARGS) == "table" and type(ARGS.name) == "string", "ARGS.name required")
assert(#ARGS.name >= 1 and #ARGS.name <= 20 and not ARGS.name:find("[%c]"), "INVALID_NAME")
assert(on("CHARGEN_NAME"), "EXPECTED_MENU:CHARGEN_NAME")
local before = charNameEdit
charNameEdit = ARGS.name
Infinity_ClickItem(assert(nameToItem.CBRTSQA_NAME_DONE, "QA_ITEM_MISSING:CBRTSQA_NAME_DONE"))
return {before = before, name = charNameEdit}
