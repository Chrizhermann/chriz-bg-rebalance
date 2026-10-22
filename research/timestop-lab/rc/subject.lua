-- Read-only: the party slots, HP, fixture effects and raw effect clocks, Time Stop state.
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
        action = try(function() return sprite.m_curAction.m_actionID end),
        -- Raw clocks of the pinned 2.7.3.0 layout. +0x3A0: a full effect check runs only when
        -- its value mod 15 equals the actor ID mod 15 (ProcessEffectList 0x3ABB7C-0x3ABBC5).
        -- +0x1A08 is the regenerated periodic list; the dispatcher copies its counter +0x38 into
        -- each worker (0x22653D). +0x520C: frozen-actor marker (0x3ABA9D). +0x4BA4: m_newEffect,
        -- set when a stop ends (0x3ABACE).
        clocks = try(function()
            local pointer = EEex_UDToPtr(sprite)
            return {check = EEex_Read32(pointer + 0x3A0), list = EEex_Read32(pointer + 0x1A40),
                frozen = EEex_Read32(pointer + 0x520C), new_effect = EEex_Read32(pointer + 0x4BA4)}
        end),
        fixtures = {}}
    try(function()
        EEex_Utility_IterateCPtrList(sprite.m_timedEffectList, function(effect)
            local source = effect.m_sourceRes:get()
            if source == "CBRTBUF" or source == "CBRTREG" or source == "CBRTHST" or source == "CBRTIHS" then
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
