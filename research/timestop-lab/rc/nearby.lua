-- Read-only: creatures around the subject (portrait 0), without line of sight, so a hostile
-- that could interrupt the unpaused case shows up first. ARGS.range (optional, default 1500).
local function try(f)
    local ok, value = pcall(f)
    if ok then return value end
    return "error: " .. tostring(value)
end
local sprite = assert(EEex_Sprite_GetInPortrait(0), "NO_SUBJECT")
local range = tonumber(type(ARGS) == "table" and ARGS.range or "1500")
assert(range and range > 0 and range <= 5000, "INVALID_RANGE")
local x, y = sprite.m_pos.x, sprite.m_pos.y
local out = {}
for _, object in ipairs(EEex_Area_GetAllOfTypeStringInRange(sprite.m_pArea, x, y, "[ANYONE]", range, 0, 0)) do
    out[#out + 1] = {id = object.m_id, name = try(function() return EEex_Sprite_GetName(object) end),
        ea = try(function() return object.m_typeAI.m_EnemyAlly end),
        resref = try(function() return object.m_resref:get() end),
        hp = try(function() return object.m_baseStats.m_hitPoints end),
        x = object.m_pos.x, y = object.m_pos.y,
        distance = math.floor(math.sqrt((object.m_pos.x - x) ^ 2 + (object.m_pos.y - y) ^ 2))}
end
table.sort(out, function(a, b) return a.distance < b.distance end)
return {range = range, count = #out, creatures = out}
