-- Read-only: one creature by object ID (ARGS.id), for the weapon-hit dummy: identity, HP, position,
-- enemy-ally value, state and its lab effects (every CBRT* source).
local function try(f)
    local ok, value = pcall(f)
    if ok then return value end
    return "error: " .. tostring(value)
end
local id = tonumber(type(ARGS) == "table" and ARGS.id or nil)
local object = id and EEex_GameObject_Get(id)
assert(object and object:isSprite(true), "NO_CREATURE")
local out = {id = object.m_id, name = try(function() return EEex_Sprite_GetName(object) end),
    resref = try(function() return object.m_resref:get() end),
    hp = try(function() return object.m_baseStats.m_hitPoints end),
    ea = try(function() return object.m_typeAI.m_EnemyAlly end),
    state = try(function() return EEex_Sprite_GetState(object) end),
    x = object.m_pos.x, y = object.m_pos.y,
    action = try(function() return object.m_curAction.m_actionID end), effects = {}}
try(function()
    EEex_Utility_IterateCPtrList(object.m_timedEffectList, function(effect)
        local source = effect.m_sourceRes:get()
        if source:sub(1, 4) == "CBRT" then
            out.effects[#out.effects + 1] = {source = source, opcode = effect.m_effectId,
                deadline = effect.m_duration}
        end
    end)
end)
return {game_time = EngineGlobals.g_pBaldurChitin.m_pObjectGame.m_worldTime.m_gameTime, creature = out}
