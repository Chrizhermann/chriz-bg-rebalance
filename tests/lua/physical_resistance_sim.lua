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
-- Same contract as EEex_Utility.lua: visit node data in order, stop on a truthy return.
-- Simulated lists are plain arrays; `visited` counts every node handed to the callback.
local visited = 0
EEex_Utility_IterateCPtrList = function(list, fn)
    for _, data in ipairs(list) do
        visited = visited + 1
        if fn(data) then break end
    end
end
if scenario == "missing_iterate" then EEex_Utility_IterateCPtrList = nil end
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

-- Effect-list fixtures. 4096 is how the engine stores an applied limited
-- duration; a rebuild is modelled by replacing the derived stats AND the
-- timed list the engine just resolved.
local ABSOLUTE = 4096
local function effect(opcode, amount, mode, timing, done)
    return {
        m_effectId = opcode, m_effectAmount = amount, m_dWFlags = mode,
        m_durationType = timing == nil and ABSOLUTE or timing,
        m_done = done == nil and 0 or done,
    }
end
-- Divine Protection as SCS ships it: opcodes 86-89 set to 100 for 18 seconds.
local function divineProtection(done)
    local list = {}
    for opcode = 86, 89 do list[#list + 1] = effect(opcode, 100, 1, ABSOLUTE, done) end
    return list
end
local function all(opcodeAmount, mode, timing, done)
    local list = {}
    for opcode = 86, 89 do list[#list + 1] = effect(opcode, opcodeAmount, mode, timing, done) end
    return list
end
local function rebuildWith(s, values, list)
    s.m_timedEffectList = list
    rebuild(s, values)
end

assert(modulePath and markerState and scenario, "missing simulator arguments")
dofile(modulePath)
if scenario == "missing_iterate" then
    -- Load-time capability check: no callback, no partial runtime, one notice.
    out("failed", CBRPhysRes.failed == true)
    out("listeners", #listeners)
    out("failure_logs", #logs)
    out("apply_defined", type(CBRPhysRes.Apply) == "function")
    out("forbidden_calls", forbiddenCalls)
    print = printOriginal
    return
end
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

scenarios.window_set = function()
    local s = newSprite({100, 100, 100, 100})
    s.m_timedEffectList = divineProtection()
    apply(s); out("divine_protection", fields(s))
    -- During the window the native value passes through unchanged.
    rebuildWith(s, {100, 95, 87, 81}, divineProtection())
    out("native_passthrough", fields(s))
    rebuildWith(s, {100, 100, 100, 100}, all(100, 0))
    out("increment_100", fields(s))
    rebuildWith(s, {100, 100, 100, 100}, all(150, 0))
    out("increment_150", fields(s))
    rebuildWith(s, {100, 100, 100, 100}, all(120, 1))
    out("set_120", fields(s))
end
scenarios.window_partial = function()
    local s = newSprite({100, 100, 100, 100})
    s.m_timedEffectList = {effect(88, 100, 1)}
    apply(s); out("piercing_only", fields(s))
    rebuildWith(s, {100, 100, 100, 100}, {effect(86, 100, 1), effect(89, 120, 0)})
    out("slashing_and_missile", fields(s))
    -- Mixed list order and unrelated effects around the window.
    rebuildWith(s, {100, 100, 100, 100}, {
        effect(166, 100, 1), effect(87, 100, 1), effect(31, 100, 1), effect(0, 5, 0),
    })
    out("crushing_among_others", fields(s))
end
scenarios.not_windows = function()
    local candidates = {
        {"set_99", all(99, 1)},
        {"increment_99", all(99, 0)},
        {"percentage_200", all(200, 2)},
        {"two_increments_of_50", {
            effect(86, 50, 0), effect(86, 50, 0), effect(87, 50, 0), effect(87, 50, 0),
            effect(88, 50, 0), effect(88, 50, 0), effect(89, 50, 0), effect(89, 50, 0),
        }},
        {"timing_0_unapplied", all(100, 1, 0)},
        {"timing_1_permanent", all(100, 1, 1)},
        {"timing_2_equipped", all(100, 1, 2)},
        {"timing_3_delayed", all(100, 1, 3)},
        {"timing_4_delayed", all(100, 1, 4)},
        {"timing_9_permanent", all(100, 1, 9)},
        {"timing_10_ticks", all(100, 1, 10)},
        {"done_integer", divineProtection(1)},
        {"done_boolean", divineProtection(true)},
        {"opcode_177_wrapper", {effect(177, 0, 2), effect(177, 2, 2)}},
        {"other_resistances", {effect(27, 100, 1), effect(31, 100, 1), effect(166, 100, 1)}},
    }
    for _, candidate in ipairs(candidates) do
        local s = newSprite({100, 100, 100, 100})
        s.m_timedEffectList = candidate[2]
        apply(s)
        out(candidate[1], fields(s))
    end
end
scenarios.equipped_list_ignored = function()
    local s = newSprite({100, 100, 100, 100})
    s.m_equippedEffectList = divineProtection()
    apply(s); out("physical", fields(s))
end
scenarios.window_lifecycle = function()
    -- Stacking alone: 90 (e.g. Hardiness 40 + Defensive Stance 50) -> 85.
    local s = newSprite({90, 90, 90, 90})
    apply(s); out("before_cast", fields(s))
    for _ = 1, 30 do apply(s) end
    out("before_fast_passes", fields(s))
    -- The rebuild that applies Divine Protection already sees it.
    rebuildWith(s, {100, 100, 100, 100}, divineProtection())
    out("cast_rebuild", fields(s))
    for _ = 1, 200 do apply(s) end
    out("during_fast_passes", fields(s))
    rebuildWith(s, {100, 100, 100, 100}, divineProtection())
    out("during_periodic_rebuild", fields(s))
    -- The first rebuild without it caps again: never longer than the effect.
    rebuildWith(s, {90, 90, 90, 90}, {})
    out("expired_rebuild", fields(s))
    for _ = 1, 30 do apply(s) end
    out("after_fast_passes", fields(s))
    -- Still listed but already completed by the engine: no window.
    rebuildWith(s, {90, 90, 90, 90}, divineProtection(1))
    out("completed_not_purged", fields(s))
    rebuildWith(s, {100, 100, 100, 100}, divineProtection())
    out("recast_rebuild", fields(s))
    -- Dispelled or removed early: capped at the next rebuild.
    rebuildWith(s, {90, 90, 90, 90}, {})
    out("removed_rebuild", fields(s))
end
scenarios.window_negative_after = function()
    -- Divine Protection followed by a -15 penalty: the window is still active.
    local s = newSprite({85, 85, 85, 85})
    s.m_timedEffectList = divineProtection()
    apply(s); out("physical", fields(s))
end
scenarios.scan_scope = function()
    local noise = {}
    for i = 1, 60 do noise[i] = effect(i % 2 == 0 and 0 or 54, 1, 0) end
    local function listWithDp()
        local list = {}
        for i, value in ipairs(noise) do list[i] = value end
        for _, value in ipairs(divineProtection()) do list[#list + 1] = value end
        return list
    end
    local s = newSprite({80, 80, 80, 80})
    s.m_timedEffectList = listWithDp()
    visited = 0; apply(s)
    out("visited_nothing_lowered", visited); out("not_lowered", fields(s))
    visited = 0; rebuildWith(s, {81, 81, 81, 81}, listWithDp())
    out("visited_one_scan", visited); out("window_81", fields(s))
    visited = 0
    for _ = 1, 100 do apply(s) end
    out("visited_fast_passes", visited)
    local outsider = newSprite({100, 100, 100, 100}, -1)
    outsider.m_timedEffectList = listWithDp()
    visited = 0; apply(outsider)
    out("visited_nonparty", visited); out("nonparty", fields(outsider))
    local early = newSprite({100, 100, 100, 100})
    early.m_timedEffectList = divineProtection()
    for _, value in ipairs(noise) do early.m_timedEffectList[#early.m_timedEffectList + 1] = value end
    visited = 0; apply(early)
    out("visited_early_exit", visited); out("early", fields(early))
end
scenarios.window_registered_callback = function()
    local s = newSprite({100, 100, 100, 100})
    s.m_timedEffectList = divineProtection()
    for _, listener in ipairs(listeners) do listener(s) end
    out("with_window", fields(s))
    s.m_timedEffectList = {}
    s.m_derivedStats = newStats({100, 100, 100, 100})
    for _ = 1, 20 do
        for _, listener in ipairs(listeners) do listener(s) end
    end
    out("after_window", fields(s))
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
    elseif kind == "missing_timed_list" then s.m_timedEffectList = nil
    elseif kind == "bad_effect_opcode" then s.m_timedEffectList = {effect("86", 100, 1)}
    elseif kind == "bad_effect_amount" then s.m_timedEffectList = {effect(86, 0/0, 1)}
    elseif kind == "bad_effect_mode" then s.m_timedEffectList = {{m_effectId = 86,
        m_effectAmount = 100, m_durationType = ABSOLUTE, m_done = 0}}
    elseif kind == "bad_effect_timing" then s.m_timedEffectList = {effect(86, 100, 1, "4096")}
    elseif kind == "bad_effect_done" then s.m_timedEffectList = {effect(86, 100, 1, ABSOLUTE, "0")}
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
