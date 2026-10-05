-- CBR_SR_PIERCE_MAGIC_V1
-- Component 210. InvokeLua is delivered inside the existing SR/SCS payload,
-- so Spell Shield still absorbs the whole payload before this callback runs.
-- One impact chooses a fixed subtraction. Recasts renew the same saved native
-- effect; they never reconstruct MR from a clamped or not-yet-rebuilt stat.
if not (EEex_Sprite_GetStat and EEex_Utility_IterateCPtrList
    and EEex_GameObject_ApplyEffect and EEex_GetUDAux
    and EEex_Opcode_AddListsResolvedListener) then
    print("CBR Pierce Magic requires EEex; launch through InfinityLoader.")
    return
end

local MR_STAT = %CBR_PM_MR_STAT%
local OWNER = "CBRPM"
local TICKS = 450 -- five rounds, 30 seconds at the engine's 15 ticks/second

local function now()
    return EEex_EngineGlobal_CBaldurChitin.m_pObjectGame.m_worldTime.m_gameTime
end

local function inspect(sprite, tick)
    local reduction, icons, stale = nil, {}, false
    EEex_Utility_IterateCPtrList(sprite.m_timedEffectList, function(fx)
        if string.upper(fx.m_sourceRes:get()) ~= OWNER then return end
        if fx.m_effectId ~= 166 and fx.m_effectId ~= 142 then return end
        if fx.m_effectId == 166 and (fx.m_dWFlags ~= 0
            or fx.m_effectAmount > 0 or fx.m_effectAmount < -40) then
            error("CBR Pierce Magic: malformed owned MR effect")
        end
        if fx.m_durationType ~= 4096 then
            error("CBR Pierce Magic: unexpected owned effect timing")
        end
        if fx.m_done ~= 0 or fx.m_duration <= tick then
            if fx.m_effectId == 166 then stale = true end
            return
        end
        if fx.m_effectId == 166 then
            if reduction then error("CBR Pierce Magic: duplicate owned MR effects") end
            reduction = fx
        elseif fx.m_dWFlags == 106 then
            icons[#icons + 1] = fx
        end
    end)
    return reduction, icons, stale
end

local function arguments(impact, opcode, amount, mode)
    return {
        effectID = opcode, targetType = 1, effectAmount = amount, dwFlags = mode,
        durationType = 0, duration = 30, effectList = 1, immediateResolve = 1,
        m_flags = 2, savingThrow = 0, spellLevel = 0,
        m_sourceRes = OWNER, m_sourceType = 1, m_secondaryType = 4,
        sourceID = impact.sourceID, sourceTarget = impact.sourceTarget,
        m_casterLevel = impact.casterLevel,
    }
end

local function deliver(sprite, impact, tick)
    local reduction, icons, stale = inspect(sprite, tick)
    if stale then return false end
    if not reduction then
        local mr = math.max(0, EEex_Sprite_GetStat(sprite, MR_STAT))
        local amount = math.min(mr, math.max(10, math.min(40, math.ceil(mr / 2))))
        EEex_GameObject_ApplyEffect(sprite, arguments(impact, 166, -amount, 0))
        -- ApplyEffect has no success return; opcode immunity can silently
        -- reject an application. Never fabricate a successful icon/snapshot.
        reduction, icons, stale = inspect(sprite, tick)
        if not reduction then return true end
    end
    reduction.m_duration = impact.deadline
    if #icons == 0 then
        EEex_GameObject_ApplyEffect(sprite, arguments(impact, 142, 0, 106))
        local ignored
        ignored, icons = inspect(sprite, tick)
    end
    for _, icon in ipairs(icons) do icon.m_duration = impact.deadline end
    return true
end

function CBRPM(effect, sprite)
    local tick = now()
    local impact = {
        sourceID = effect.m_sourceId, sourceTarget = effect.m_sourceTarget,
        casterLevel = effect.m_casterLevel, deadline = tick + TICKS,
    }
    local aux = EEex_GetUDAux(sprite)
    if deliver(sprite, impact, tick) then
        aux.CBRPM_pending = nil
    else
        -- An expiry-boundary hit can precede native removal/stat rebuilding.
        -- Wait for that actual resolution boundary, not an arbitrary delay.
        -- Scalars only: no effect/sprite userdata survives this callback.
        aux.CBRPM_pending = impact
    end
end

EEex_Opcode_AddListsResolvedListener(function(sprite)
    local aux = EEex_GetUDAux(sprite)
    local impact = aux.CBRPM_pending
    if not impact then return end
    local tick = now()
    if tick >= impact.deadline then aux.CBRPM_pending = nil; return end
    local _, _, stale = inspect(sprite, tick)
    if stale then return end
    -- Clear before adding an effect: immediate application can reenter the
    -- native resolution callback. A second pass must not consume it again.
    aux.CBRPM_pending = nil
    deliver(sprite, impact, tick)
end)
