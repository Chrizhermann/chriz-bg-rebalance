-- CBR_DRAGON_VORPAL_RUNTIME_V1
-- CBR 110: the opcode-402 rider already resolved its chance and death save.
-- Native death type 8 preserves the engine's gore and anti-chunking settings.
-- No listeners, saved state, or changes to the target's protections are needed.

local warned = {}
local function disabled(reason)
    if not warned[reason] then
        warned[reason] = true
        print("[CBR 110] Dragon vorpal disabled: " .. reason)
    end
end

local function available()
    return EEex_Active and type(EEex_GameObject_ApplyEffect) == "function"
        and type(EEex_Sprite_GetStat) == "function"
end

function CBRDVGO(effect, target)
    if not available() then
        disabled("required EEex effect/stat API unavailable")
        return
    end
    if not effect or not target then
        disabled("missing effect or target")
        return
    end

    -- noSave bypasses application checks, so preserve plot immortality here.
    -- GetStat reads the current active derived stats; 83 is MINHITPOINTS.
    local ok, minimum_hp = pcall(EEex_Sprite_GetStat, target, 83)
    if not ok or type(minimum_hp) ~= "number" or minimum_hp ~= minimum_hp then
        disabled("minimum-HP guard unavailable")
        return
    end
    if minimum_hp > 0 then return end

    local function source_number(field, fallback)
        local ok, value = pcall(function() return effect[field] end)
        return ok and tonumber(value) or fallback
    end
    local read_ok, source_res = pcall(function() return effect.m_sourceRes:get() end)
    local args = {
            effectID = 13,
            targetType = 1,
            effectAmount = 0,
            dwFlags = 8,
            durationType = 1,
            m_flags = 2,
            noSave = 1,
            immediateResolve = 1,
            probabilityUpper = 100,
            probabilityLower = 0,
            savingThrow = 0,
            saveMod = 0,
            sourceID = source_number("m_sourceId", -1),
            sourceTarget = source_number("m_sourceTarget", -1),
            m_sourceRes = read_ok and tostring(source_res or "") or "",
            m_sourceType = source_number("m_sourceType", 1),
            m_sourceFlags = source_number("m_sourceFlags", 0),
        }
    -- This public wrapper owns native effect allocation and forwards noSave
    -- to AddEffect. Do not remove Death Ward, opcode-101 effects, or spell states.
    local applied, reason = pcall(EEex_GameObject_ApplyEffect, target, args)
    if not applied then disabled("effect application failed: " .. tostring(reason)) end
end

if not available() then
    disabled("required EEex effect/stat API unavailable")
end
