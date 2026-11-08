-- Party physical resistance: full value through 80, half value above it.
-- Installed component 310 uses a 90% ceiling. A future 95% option needs a
-- pre-clamp engine integration; changing this constant alone is NOT enough.
-- Short immunity windows stay uncapped: while one timed effect by itself
-- grants 100% to a damage type (e.g. SCS Divine Protection), that type keeps
-- its native value. The window is read from the effect list on every stats
-- rebuild, so it lasts exactly as long as the engine keeps that effect.
-- Nothing is written to CRE base stats, effects, locals or saved games.
-- LuaJIT / Lua 5.1 compatible; use EEex's bit helpers, not Lua 5.3 operators.
local cap = %CBR_RES_CAP%
local markerState = %CBR_RES_STATE%

CBRPhysRes = CBRPhysRes or {apiVersion = 1, failed = false, registered = false}
local state = CBRPhysRes
state.apiVersion, state.failed = 1, false
state.logged = state.logged or {}
local function report(reason)
    reason = tostring(reason)
    if state.logged[reason] then return end
    state.logged[reason] = true
    print("CBR physical resistance: unavailable sprite field; continuing. " .. reason)
end
local function fail(reason)
    if state.failed then return end
    state.failed = true
    print("CBR physical resistance: disabled; restart through InfinityLoader after checking EEex. " .. tostring(reason))
end

local function integer(value)
    return type(value) == "number" and value == value
        and value ~= math.huge and value ~= -math.huge
        and value == math.floor(value)
end

if not integer(cap) or (cap ~= 90 and cap ~= 95)
        or not integer(markerState) or markerState < 0 or markerState > 255 then
    fail("Invalid component configuration.")
    return
end
state.cap, state.markerState = cap, markerState

function state.Transform(value)
    if not integer(value) then return value end
    if value <= 80 then return value end
    return math.min(cap, 80 + math.floor((value - 80) / 2))
end

local required = {
    "EEex_Opcode_AddListsResolvedListener", "EEex_Sprite_GetPortraitIndex",
    "EEex_Utility_IterateCPtrList", "EEex_BAnd", "EEex_BOr", "EEex_LShift",
}
for _, name in ipairs(required) do
    if type(_G[name]) ~= "function" then
        fail("Missing " .. name .. ".")
        return
    end
end

local markerWord = math.floor(markerState / 32)
local markerMask = EEex_LShift(1, markerState % 32)
local fields = {
    "m_nResistSlashing", "m_nResistCrushing", "m_nResistPiercing", "m_nResistMissile",
}
-- Opcodes 86-89 set these four stats, in the order of `fields`.
local fieldOfOpcode = {[86] = 1, [87] = 2, [88] = 3, [89] = 4}
-- The engine stores an applied limited duration as an absolute expiry (4096).
-- Equipped (2), permanent (1, 9) and still-delayed effects never qualify.
local ABSOLUTE_EXPIRY = 4096

-- Which damage types a short immunity window covers right now. Only the
-- timed list is read: items and permanent passives are stacking sources.
-- A window is one effect that alone reaches 100: an increment (mode 0) or
-- a set (mode 1) of at least 100. A percentage (mode 2) never qualifies.
-- An EFF wrapped by opcode 177 is not inspected and stays capped.
local function immunityWindows(sprite)
    local list = assert(sprite.m_timedEffectList, "Timed effect list unavailable.")
    local windows = {}
    EEex_Utility_IterateCPtrList(list, function(effect)
        local opcode = effect.m_effectId
        local index = fieldOfOpcode[opcode]
        if index == nil or windows[index] then return end
        local amount, mode = effect.m_effectAmount, effect.m_dWFlags
        local timing, done = effect.m_durationType, effect.m_done
        if integer(amount) and (mode == 0 or mode == 1) and amount >= 100
                and timing == ABSOLUTE_EXPIRY and (done == 0 or done == false) then
            windows[index] = true
            return windows[1] and windows[2] and windows[3] and windows[4]
        end
    end)
    return windows
end

local function apply(sprite)
    -- Allegiance is not party membership: allies/summons are excluded, while
    -- a charmed roster member remains subject to the same player rule.
    local portrait = EEex_Sprite_GetPortraitIndex(sprite)
    if not integer(portrait) or portrait < 0 or portrait > 5 then return end

    -- Write the block being rebuilt, not getActiveStats(): during effect
    -- processing that helper can return the PREVIOUS snapshot (m_tempStats).
    local stats = assert(sprite.m_derivedStats, "Derived stats unavailable.")
    local states = assert(stats.m_spellStates, "Spell-state array unavailable.")
    local word = states:get(markerWord)
    assert(integer(word), "Invalid spell-state word.")
    if EEex_BAnd(word, markerMask) ~= 0 then return end

    -- Read each channel before applying the curve to the readable values.
    local before, after, lowered = {}, {}, false
    for i, field in ipairs(fields) do
        before[i] = stats[field]
        after[i] = state.Transform(before[i])
        if integer(before[i]) then
            lowered = lowered or after[i] ~= before[i]
        else
            report(field)
        end
    end
    -- Only a value the curve would lower needs the effect-list scan.
    if lowered then
        local windows = immunityWindows(sprite)
        for i = 1, #fields do
            if windows[i] then after[i] = before[i] end
        end
    end

    -- ListsResolved also runs on passes which did not rebuild stats. The
    -- private bit lives in THIS block and is cleared by the engine rebuild.
    -- Without it, repeated callbacks would shrink 100 -> 90 -> 85 -> ...
    states:set(markerWord, EEex_BOr(word, markerMask))
    assert(EEex_BAnd(stats.m_spellStates:get(markerWord), markerMask) ~= 0,
        "Rebuild marker did not persist.")
    local ok, reason = pcall(function()
        for i, field in ipairs(fields) do
            if integer(after[i]) and before[i] ~= after[i] then stats[field] = after[i] end
        end
    end)
    if not ok then
        -- Defensive recovery if a binding rejects a write mid-update. Try
        -- every field even if one setter remains broken. Later callbacks retry;
        -- never leave the marker claiming a successful update.
        local restored = true
        for i, field in ipairs(fields) do
            local reset = pcall(function() stats[field] = before[i] end)
            restored = restored and reset
        end
        local reset = pcall(function() stats.m_spellStates:set(markerWord, word) end)
        if not (restored and reset) then
            error("Resistance write failed and rollback was incomplete: " .. tostring(reason))
        end
        error(reason)
    end
end

function state.Apply(sprite)
    if state.failed then return end
    local ok, reason = pcall(apply, sprite)
    if not ok then report(reason) end
end

-- Reloading the module keeps one callback calling the current implementation.
if not state.registered and not state.failed then
    local ok, reason = pcall(EEex_Opcode_AddListsResolvedListener, function(sprite)
        state.Apply(sprite)
    end)
    if ok then state.registered = true else fail(reason) end
end
