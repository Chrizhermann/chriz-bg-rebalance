-- Read-only: the effects of the creatures ARGS.ids (object IDs separated by spaces): HP, state,
-- every timed effect with opcode, timing, deadline (+0x28) and source, and the time origin (+0x6C)
-- of the periodic opcodes (25, 78, 98, 272), timed or equipped.
assert(type(ARGS) == "table" and type(ARGS.ids) == "string", "ARGS.ids required")
local PERIODIC = {[25] = true, [78] = true, [98] = true, [272] = true}
local creatures = {}
for word in ARGS.ids:gmatch("%S+") do
    local id = tonumber(word)
    local object = id and EEex_GameObject_Get(id)
    assert(object and object:isSprite(true), "NOT_A_CREATURE")
    local out = {id = object.m_id, name = EEex_Sprite_GetName(object), hp = object.m_baseStats.m_hitPoints,
        state = EEex_Sprite_GetState(object), timed = {}, equipped = {}}
    local function list(effects, into, all)
        EEex_Utility_IterateCPtrList(effects, function(effect)
            local opcode = effect.m_effectId
            if all or PERIODIC[opcode] then
                local entry = {opcode = opcode, timing = effect.m_durationType, deadline = effect.m_duration,
                    source = effect.m_sourceRes:get()}
                if PERIODIC[opcode] then entry.origin = EEex_ReadU32(EEex_UDToPtr(effect) + 0x6C) end
                into[#into + 1] = entry
            end
        end)
    end
    list(object.m_timedEffectList, out.timed, true)
    list(object.m_equipedEffectList, out.equipped, false)
    creatures[#creatures + 1] = out
end
assert(#creatures > 0, "NO_CREATURES")
return {game_time = EngineGlobals.g_pBaldurChitin.m_pObjectGame.m_worldTime.m_gameTime, creatures = creatures}
