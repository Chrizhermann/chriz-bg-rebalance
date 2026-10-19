-- Read-only: the party slots, the subject's HP and fixture effects, Time Stop state.
local function try(f)
    local ok, value = pcall(f)
    if ok then return value end
    return "error: " .. tostring(value)
end
local chitin = EngineGlobals.g_pBaldurChitin
local game, world = chitin.m_pObjectGame, chitin.m_pEngineWorld
local gamePointer = EEex_UDToPtr(game)
local function actor(slot)
    local sprite = EEex_Sprite_GetInPortrait(slot)
    if not sprite then return nil end
    local out = {id = sprite.m_id, name = try(function() return EEex_Sprite_GetName(sprite) end),
        hp = try(function() return sprite.m_baseStats.m_hitPoints end),
        max_hp = try(function() return EEex_Sprite_GetActiveStats(sprite).m_nMaxHitPoints end),
        area = try(function() return sprite.m_pArea.m_resref:get() end),
        x = try(function() return sprite.m_pos.x end), y = try(function() return sprite.m_pos.y end),
        ai_speed = try(function() return EEex_ReadU8(EEex_UDToPtr(sprite) + 0x58) end),
        fixtures = {}}
    try(function()
        EEex_Utility_IterateCPtrList(sprite.m_timedEffectList, function(effect)
            local source = effect.m_sourceRes:get()
            if source == "CBRTBUF" or source == "CBRTREG" then
                out.fixtures[#out.fixtures + 1] = {source = source, opcode = effect.m_effectId,
                    timing = effect.m_durationType, deadline = effect.m_duration}
            end
        end)
    end)
    return out
end
return {game_time = game.m_worldTime.m_gameTime,
    paused = (tonumber(world.m_bPaused) or 0) ~= 0 or (tonumber(world.m_bHardPaused) or 0) ~= 0,
    time_stop_remaining = EEex_Read32(gamePointer + 0x9690), time_stop_caster = EEex_Read32(gamePointer + 0x9694),
    portrait0 = actor(0), portrait1 = actor(1), portrait2 = actor(2) ~= nil}
