-- Isolated core simulation, not proof of native hook ordering or game damage.
-- Lua 5.3 operators here model EEex helpers; production stays LuaJIT-compatible.
-- Usage: lua physical_resistance_sim.lua <stamped-module> <state-id> <scenario>
local modulePath, markerState, scenario = arg[1], tonumber(arg[2]), arg[3]
local physical = {
    "m_nResistSlashing", "m_nResistCrushing", "m_nResistPiercing", "m_nResistMissile",
}
local other = {
    m_nResistFire = 117, m_nResistCold = 94, m_nResistElectricity = 100,
    m_nResistAcid = 91, m_nResistMagic = 83, m_nResistMagicDamage = 119,
    m_nNumberOfAttacks = 8, m_nMaxHitPoints = 93,
}
local printOriginal, logs = print, {}
print = function(...) logs[#logs + 1] = table.concat({...}, " ") end
local forbiddenCalls, listeners = 0, {}
local function forbidden()
    forbiddenCalls = forbiddenCalls + 1
    error("persistent effect/save APIs must not be called by the core")
end
EEex_Active = true
EEex_BAnd = function(a, b) return a & b end
EEex_BOr = function(a, b) return a | b end
EEex_LShift = function(a, b) return a << b end
EEex_Sprite_GetPortraitIndex = function(s) return s.portrait end
EEex_Sprite_GetActiveStats = function(s) return s.m_derivedStats end
EEex_Opcode_AddListsResolvedListener = function(fn) listeners[#listeners + 1] = fn end
EEex_GameObject_ApplyEffect = forbidden
EEex_Sprite_ApplyEffect = forbidden
EEex_Sprite_SetLocalInt = forbidden
EEex_Sprite_AddMarshalHandlers = forbidden
EEex_GetUDAux = forbidden

local function out(k, v) io.write(k, "\t", tostring(v), "\n") end
local function newArray()
    local a = {_v = {}}
    for i = 0, 7 do a._v[i] = 0 end
    function a:get(i) return self._v[i] end
    function a:set(i, v) self._v[i] = v end
    return a
end
local function newStats(values)
    local data, writes = {m_spellStates = newArray()}, {}
    for i, field in ipairs(physical) do data[field] = values[i] end
    for field, value in pairs(other) do data[field] = value end
    return setmetatable({}, {
        __index = data,
        __newindex = function(_, key, value)
            writes[#writes + 1] = {key, value}
            data[key] = value
        end,
    }), data, writes
end
local function newSprite(values, portrait)
    local stats, data, writes = newStats(values or {100, 100, 100, 100})
    local base = {m_nResistSlashing = 5, m_nResistCrushing = 6}
    local temp = {m_nResistSlashing = 2, m_nResistCrushing = 3}
    local s = {
        portrait = portrait == nil and 0 or portrait,
        m_derivedStats = stats, m_baseStats = base, m_tempStats = temp,
        m_timedEffectList = {}, m_equippedEffectList = {},
    }
    function s:getActiveStats() return self.m_derivedStats end
    return s, data, writes
end
local function fields(s)
    local result = {}
    for _, field in ipairs(physical) do result[#result + 1] = s.m_derivedStats[field] end
    return table.concat(result, ",")
end
local function marker(s)
    local word = s.m_derivedStats.m_spellStates:get(math.floor(markerState / 32))
    return (word >> (markerState % 32)) & 1
end
local function apply(s) CBRPhysRes.Apply(s) end
local function rebuild(s, values)
    -- Core contract only: these inputs have NOT been clamped to 100 by the engine.
    local stats = newStats(values)
    s.m_derivedStats = stats
    apply(s)
end

assert(modulePath and markerState and scenario, "missing simulator arguments")
dofile(modulePath)
assert(type(CBRPhysRes) == "table", "module did not publish CBRPhysRes")
assert(type(CBRPhysRes.Transform) == "function", "Transform entry point missing")
assert(type(CBRPhysRes.Apply) == "function", "Apply entry point missing")
-- Ignore loader diagnostics in the count of one fault diagnostic per process.
logs = {}

local scenarios = {}
scenarios.curve = function()
    for _, value in ipairs({-100, -1, 0, 79, 80, 81, 82, 89, 90, 99, 100, 101, 109, 110, 200}) do
        out("raw_" .. value, CBRPhysRes.Transform(value))
    end
    local previous, monotonic = -101, true
    for value = -100, 200 do
        local actual = CBRPhysRes.Transform(value)
        if actual < previous or actual > value then monotonic = false end
        previous = actual
    end
    out("monotonic", monotonic)
end
scenarios.mixed = function()
    local s = newSprite({80, 90, 110, -20})
    local base, temp = s.m_baseStats, s.m_tempStats
    local timed, equipped = s.m_timedEffectList, s.m_equippedEffectList
    apply(s)
    out("physical", fields(s))
    local unchanged = true
    for field, value in pairs(other) do
        if s.m_derivedStats[field] ~= value then unchanged = false end
    end
    out("other_unchanged", unchanged)
    out("base_unchanged", s.m_baseStats == base and base.m_nResistSlashing == 5 and base.m_nResistCrushing == 6)
    out("temp_unchanged", s.m_tempStats == temp and temp.m_nResistSlashing == 2 and temp.m_nResistCrushing == 3)
    out("effects_unchanged", s.m_timedEffectList == timed and next(timed) == nil and s.m_equippedEffectList == equipped and next(equipped) == nil)
end
scenarios.cadence = function()
    local s = newSprite({90, 90, 90, 90})
    apply(s); out("first", fields(s))
    for _ = 1, 200 do apply(s) end
    out("after_200_passes", fields(s))
    rebuild(s, {85, 85, 85, 85}); out("same_value_fresh_rebuild", fields(s))
    rebuild(s, {100, 100, 100, 100}); out("buff_applied", fields(s))
    rebuild(s, {70, 70, 70, 70}); out("buff_expired", fields(s))
end
scenarios.marker = function()
    local s = newSprite()
    local word, siblingMask = math.floor(markerState / 32), 1 << ((markerState + 1) % 32)
    s.m_derivedStats.m_spellStates:set(word, siblingMask)
    apply(s); out("after_apply", marker(s))
    local preserved = (s.m_derivedStats.m_spellStates:get(word) & siblingMask) == siblingMask
    s.m_derivedStats = newStats({100, 100, 100, 100})
    out("before_reapply", marker(s))
    apply(s); out("after_reapply", marker(s))
    out("sibling_states_preserved", preserved)
end
scenarios.nonparty = function()
    local writes, markers, unchanged = 0, 0, true
    for _, ea in ipairs({2, 4, 128, 255}) do
        local s, _, written = newSprite(nil, -1)
        s.m_typeAI = {m_EnemyAlly = ea}
        for _ = 1, 20 do apply(s) end
        writes, markers = writes + #written, markers + marker(s)
        if fields(s) ~= "100,100,100,100" then unchanged = false end
    end
    out("writes", writes); out("markers", markers); out("all_unchanged", unchanged)
end
scenarios.membership = function()
    local s, _, writes = newSprite(nil, -1)
    apply(s); out("before_join", fields(s))
    s.portrait = 2; apply(s); out("after_join", fields(s))
    local before = #writes
    s.portrait = -1
    for _ = 1, 20 do apply(s) end
    out("writes_after_exit", #writes - before)
    out("exit_without_rebuild", fields(s))
    rebuild(s, {100, 100, 100, 100}); out("exit_after_rebuild", fields(s))
    s.portrait = 1; apply(s); out("after_rejoin", fields(s))
end
scenarios.save_load = function()
    local s = newSprite(); s.m_id = 42; apply(s)
    out("before_load", fields(s))
    local fresh = newSprite({90, 90, 90, 90}); fresh.m_id = 42
    apply(fresh)
    out("after_load", fields(fresh))
    out("old_untouched", fields(s) == "90,90,90,90")
end
scenarios.registered_callback = function()
    out("listeners", #listeners)
    local s = newSprite()
    for _, listener in ipairs(listeners) do listener(s) end
    out("physical", fields(s))
    for _ = 1, 100 do
        for _, listener in ipairs(listeners) do listener(s) end
    end
    out("after_fast_passes", fields(s))
end
scenarios.successful_reload = function()
    local s = newSprite()
    for _, listener in ipairs(listeners) do listener(s) end
    dofile(modulePath)
    dofile(modulePath)
    out("listeners", #listeners)
    for _, listener in ipairs(listeners) do listener(s) end
    out("after_reload", fields(s))
    local fresh = newSprite({90, 90, 90, 90})
    for _, listener in ipairs(listeners) do listener(fresh) end
    out("fresh_after_reload", fields(fresh))
end
scenarios.party_hostile_ea = function()
    local s = newSprite()
    s.m_typeAI = {m_EnemyAlly = 255}
    apply(s)
    out("physical", fields(s))
    out("marker", marker(s))
end
scenarios.setter_failure = function()
    local s = newSprite()
    local meta, failedOnce = getmetatable(s.m_derivedStats), false
    local ordinaryWrite = meta.__newindex
    meta.__newindex = function(object, key, value)
        if key == "m_nResistPiercing" and not failedOnce then
            failedOnce = true
            error("synthetic native setter failure")
        end
        ordinaryWrite(object, key, value)
    end
    apply(s)
    for _ = 1, 30 do apply(s) end
    out("physical", fields(s)); out("marker", marker(s))
    out("failed", CBRPhysRes.failed == true); out("failure_logs", #logs)
    local healthy = newSprite()
    apply(healthy)
    out("later_healthy_unchanged", fields(healthy) == "100,100,100,100")
end

local function failure(kind)
    local s, data, writes = newSprite()
    if kind == "missing_field" or kind == "failure_reload" then data.m_nResistMissile = nil
    elseif kind == "string_field" then data.m_nResistMissile = "100"
    elseif kind == "nan_field" then data.m_nResistMissile = 0/0
    elseif kind == "infinite_field" then data.m_nResistMissile = math.huge
    elseif kind == "missing_stats" then s.m_derivedStats = nil
    elseif kind == "missing_states" then data.m_spellStates = nil
    elseif kind == "missing_get" then data.m_spellStates.get = nil
    elseif kind == "missing_set" then data.m_spellStates.set = nil
    elseif kind == "bad_portrait_index" then s.portrait = "0"
    elseif kind == "copy_states" then
        local original = data.m_spellStates
        data.m_spellStates = nil
        setmetatable(data, {__index = function(_, key)
            if key == "m_spellStates" then
                local copy = newArray()
                for i = 0, 7 do copy._v[i] = original._v[i] end
                return copy
            end
        end})
    else error("unknown fault " .. kind) end
    apply(s)
    for _ = 1, 30 do apply(s) end
    if kind == "failure_reload" then dofile(modulePath); apply(s) end
    out("writes", #writes)
    out("failed", CBRPhysRes.failed == true)
    out("failure_logs", #logs)
    local healthy = newSprite()
    apply(healthy)
    out("later_healthy_unchanged", fields(healthy) == "100,100,100,100")
end

if scenarios[scenario] then scenarios[scenario]() else failure(scenario) end
out("forbidden_calls", forbiddenCalls)
print = printOriginal
