-- Read-only (Time Clocks lab): the mod's status and counters, the Time Stop state, the party AI
-- and the sampler, and for the party slots 0 and 1 (plus ARGS.ids, comma-separated object IDs)
-- HP, AI speed, the raw effect clocks and every timed effect from ARGS.sources (comma-separated
-- resrefs; default: the lab's fixtures and the stock spells of the area cases).
local function try(f)
    local ok, value = pcall(f)
    if ok then return value end
    return "error: " .. tostring(value)
end
local function list(text, default)
    local out = {}
    for item in ((type(ARGS) == "table" and ARGS[text]) or default):gmatch("[^,%s]+") do out[#out + 1] = item end
    return out
end
local sources = {}
for _, resref in ipairs(list("sources", "CBRTBUF,CBRTREG,CBRTHST,CBRTIHS,CBRTSLW,CBRTSRH,CBRTDIS,CBRTSTP," ..
        "CBRTDMG,CBRTCON,CBRTHIT,CBRTSTL,CBRTSAV,SPWI112,SPWI304,SPWI213,SPWI502,SPWI712,SPWI313,CBRTSRCK")) do
    sources[resref:upper()] = true
end
local chitin = EngineGlobals.g_pBaldurChitin
local game, world = chitin.m_pObjectGame, chitin.m_pEngineWorld
local gamePointer = EEex_UDToPtr(game)
local function effects(sprite, listName)
    local out = {}
    EEex_Utility_IterateCPtrList(sprite[listName], function(effect)
        local source = effect.m_sourceRes:get():upper()
        if sources[source] then
            local pointer = EEex_UDToPtr(effect)
            out[#out + 1] = {source = source, opcode = effect.m_effectId, timing = effect.m_durationType,
                deadline = effect.m_duration, origin = EEex_Read32(pointer + 0x6C),
                p1 = effect.m_effectAmount, p2 = effect.m_dWFlags}
        end
    end)
    return out
end
local function actor(sprite)
    if not sprite then return nil end
    local pointer = EEex_UDToPtr(sprite)
    return {id = sprite.m_id, name = try(function() return EEex_Sprite_GetName(sprite) end),
        hp = try(function() return sprite.m_baseStats.m_hitPoints end),
        x = try(function() return sprite.m_pos.x end), y = try(function() return sprite.m_pos.y end),
        ai_speed = EEex_ReadU8(pointer + 0x58), action = try(function() return sprite.m_curAction.m_actionID end),
        -- +0x3A0 check counter, +0x1A08+0x38 periodic list counter, +0x520C frozen marker,
        -- +0x4BA4 m_newEffect (see subject.lua).
        clocks = {check = EEex_Read32(pointer + 0x3A0), list = EEex_Read32(pointer + 0x1A40),
            frozen = EEex_Read32(pointer + 0x520C), new_effect = EEex_Read32(pointer + 0x4BA4)},
        timed = try(function() return effects(sprite, "m_timedEffectList") end),
        equipped = try(function() return effects(sprite, "m_equipedEffectList") end)}
end
local actors = {portrait0 = actor(EEex_Sprite_GetInPortrait(0)), portrait1 = actor(EEex_Sprite_GetInPortrait(1))}
for _, id in ipairs(list("ids", "")) do
    local object = EEex_GameObject_Get(tonumber(id))
    actors["id" .. id] = object and object.m_objectType == CGameObjectType.SPRITE and actor(object) or false
end
local clocks = CBTC_TimeClocks
local options = {}
if clocks and type(clocks.options) == "table" then
    for key, value in pairs(clocks.options) do
        if type(value) == "boolean" then options[key] = value end
    end
end
local sampler = CBTCLab
return {game_time = game.m_worldTime.m_gameTime,
    paused = (tonumber(world.m_bPaused) or 0) ~= 0 or (tonumber(world.m_bHardPaused) or 0) ~= 0,
    time_stop_remaining = EEex_Read32(gamePointer + 0x9690), time_stop_caster = EEex_Read32(gamePointer + 0x9694),
    -- The AI scheduler's counter (30 per second), when its object exists.
    scheduler = (function()
        local object = EEex_ReadPtr(EEex_GetImageBase() + 0x667560)
        return object ~= 0 and EEex_Read32(object + 0xFA0) or nil
    end)(),
    party_ai = try(function() local v = _G.game:GetPartyAI() return v ~= nil and v ~= false and v ~= 0 end),
    area = try(function() return EEex_Sprite_GetInPortrait(0).m_pArea.m_resref:get() end),
    time_clocks = clocks and {status = clocks.Status, installed = clocks.installed, options = options,
        stats = clocks.core and clocks.core.stats} or "not loaded",
    sampler = sampler and {active = sampler.active, records = sampler.count, overflow = sampler.overflow,
        errors = sampler.errors, last_error = sampler.lastError, projectiles = #sampler.projectiles,
        pending = (function() local n = 0 for _ in pairs(sampler.pending) do n = n + 1 end return n end)()}
        or "not installed",
    actors = actors}
