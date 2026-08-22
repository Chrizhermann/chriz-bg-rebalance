-- Behavioral simulation harness for M_CBRAPR.lua (component 407 listener).
--
-- Runs under EET's bundled Lua 5.3 (tests/test_cbrapr_listener.py). It fakes
-- exactly the slice of the EEex API the listener touches and drives the
-- engine cadence that the 2026-08-22 disassembly of
-- CGameSprite::ProcessEffectList established:
--
--   * the ListsResolved hook fires once per PASS (every AI tick);
--   * CDerivedStats is REBUILT (Reload + effect lists re-applied, spell
--     states cleared) only on some passes;
--   * the other passes reach the hook with the same, unrebuilt struct.
--
-- usage: lua cbrapr_sim.lua <stamped-listener.lua> <marker-state-id> <scenario>
-- Output: one "key<TAB>value" line per observation.

local listenerPath = arg[1]
local markerState = tonumber(arg[2])
local scenario = arg[3]

local TEMPUS_KIT = 16425
local STAT_KIT = 152
local PROF_FLAIL = 100
local PROF_LONGSWORD = 90

-------------------------------------------------------------------------------
-- Fake EEex surface (Lua 5.3 operators here; the listener itself must use the
-- EEex_* helpers because the live runtime is LuaJIT 5.1 syntax).
-------------------------------------------------------------------------------

EEex_BAnd = function(a, b) return a & b end
EEex_BOr = function(a, b) return a | b end
EEex_LShift = function(a, n) return a << n end

local listeners = {}
function EEex_Opcode_AddListsResolvedListener(func)
    listeners[#listeners + 1] = func
end

function EEex_Sprite_GetStat(sprite, statID)
    return sprite:getActiveStats():GetAtOffset(statID)
end

-------------------------------------------------------------------------------
-- Fake engine objects
-------------------------------------------------------------------------------

local function newArray(n, withSet)
    local arr = { _v = {} }
    for i = 0, n - 1 do arr._v[i] = 0 end
    function arr:get(i) return self._v[i] end
    if withSet then
        function arr:set(i, v) self._v[i] = v end
    end
    return arr
end

local function newStats(opts)
    local stats = {
        m_nNumberOfAttacks = 1,
        _stat = {},
    }
    if opts.spellStates ~= false then
        stats.m_spellStates = newArray(8, opts.withSet ~= false)
    end
    function stats:GetAtOffset(id) return self._stat[id] or 0 end
    function stats:GetSpellState(id)
        if not self.m_spellStates then return 0 end
        local word = self.m_spellStates:get(id // 32)
        return ((word >> (id % 32)) & 1)
    end
    return stats
end

local function newItem(prof)
    return { pRes = { pHeader = { proficiencyType = prof } } }
end

local function newSprite(opts)
    local sprite = {
        m_bAllowEffectListCall = 1,
        m_derivedStats = newStats(opts),
        m_tempStats = newStats(opts),
        m_equipment = { m_selectedWeapon = 35, m_items = newArray(39, true) },
    }
    function sprite:getActiveStats()
        if self.m_bAllowEffectListCall ~= 0 then return self.m_derivedStats end
        return self.m_tempStats
    end
    sprite.m_equipment.m_items:set(35, newItem(PROF_FLAIL))      -- quick slot 1
    sprite.m_equipment.m_items:set(36, newItem(PROF_LONGSWORD))  -- quick slot 2
    sprite.m_equipment.m_items:set(10, newItem(0))               -- fist
    return sprite
end

-- Engine cadence -------------------------------------------------------------

local function fire(sprite)
    for _, func in ipairs(listeners) do func(sprite) end
end

-- Full pass: Reload (fresh struct: base APR, spell states cleared), effects
-- re-applied (stat table re-stamped), then the hook.
local function rebuild(sprite, baseKey, stat)
    local stats = sprite.m_derivedStats
    stats.m_nNumberOfAttacks = baseKey
    stats._stat = {}
    for k, v in pairs(stat) do stats._stat[k] = v end
    if stats.m_spellStates then
        for i = 0, 7 do stats.m_spellStates._v[i] = 0 end
    end
    fire(sprite)
end

-- Fast pass: nothing rebuilt, hook still fires.
local function fastPass(sprite, n)
    for _ = 1, (n or 1) do fire(sprite) end
end

local function out(key, value)
    io.write(key, "\t", tostring(value), "\n")
end

local function apr(sprite) return sprite.m_derivedStats.m_nNumberOfAttacks end
local function marker(sprite) return sprite.m_derivedStats:GetSpellState(markerState) end

-------------------------------------------------------------------------------
-- Scenarios
-------------------------------------------------------------------------------

local tempusFlail2 = { [STAT_KIT] = TEMPUS_KIT, [PROF_FLAIL] = 2, [PROF_LONGSWORD] = 0 }

local scenarios = {}

-- Baseline 1.0 APR, 2-pip flail wielded: exactly one +1/2 per rebuild, stable
-- across the fast passes in between.
scenarios.rebuild_then_fast_passes = function()
    local s = newSprite({})
    rebuild(s, 1, tempusFlail2)
    out("after_rebuild", apr(s))
    out("marker_after_rebuild", marker(s))
    fastPass(s, 14)
    out("after_14_fast_passes", apr(s))
    rebuild(s, 1, tempusFlail2)
    out("after_second_rebuild", apr(s))
    fastPass(s, 200)
    out("after_200_fast_passes", apr(s))
end

-- Holy Power tier-1 lands (+1/2 from op1): engine baseline becomes 1.5 = the
-- very value (key 7) the listener wrote last pass. Must still add +1/2 -> 2.0 (key 2).
scenarios.holy_power_baseline_equals_previous_write = function()
    local s = newSprite({})
    rebuild(s, 1, tempusFlail2)
    out("plain", apr(s))
    rebuild(s, 7, tempusFlail2) -- engine now says 1.5 (key 7) = what we wrote last pass
    out("holy_power_tier1", apr(s))
    fastPass(s, 14)
    out("holy_power_tier1_after_fast_passes", apr(s))
    rebuild(s, 1, tempusFlail2)
    out("holy_power_expired", apr(s))
end

-- Marker bookkeeping: clear on a fresh struct before the hook, set after a
-- bump, cleared again by the next rebuild.
scenarios.marker_lifecycle = function()
    local s = newSprite({})
    rebuild(s, 1, tempusFlail2)
    out("marker_after_bump", marker(s))
    -- simulate Reload without firing the hook
    for i = 0, 7 do s.m_derivedStats.m_spellStates._v[i] = 0 end
    s.m_derivedStats.m_nNumberOfAttacks = 1
    out("marker_after_reload_before_hook", marker(s))
    fire(s)
    out("apr_after_hook", apr(s))
    out("marker_after_hook", marker(s))
end

-- Non-qualifying cases never write and never set the marker.
scenarios.not_tempus = function()
    local s = newSprite({})
    rebuild(s, 1, { [STAT_KIT] = 0x4000, [PROF_FLAIL] = 2 })
    fastPass(s, 14)
    out("apr", apr(s)); out("marker", marker(s))
end
scenarios.one_pip = function()
    local s = newSprite({})
    rebuild(s, 1, { [STAT_KIT] = TEMPUS_KIT, [PROF_FLAIL] = 1 })
    fastPass(s, 14)
    out("apr", apr(s)); out("marker", marker(s))
end
scenarios.fist_selected = function()
    local s = newSprite({})
    s.m_equipment.m_selectedWeapon = 10
    rebuild(s, 1, tempusFlail2)
    fastPass(s, 14)
    out("apr", apr(s)); out("marker", marker(s))
end
scenarios.no_selection = function()
    local s = newSprite({})
    s.m_equipment.m_selectedWeapon = 255
    rebuild(s, 1, tempusFlail2)
    fastPass(s, 14)
    out("apr", apr(s)); out("marker", marker(s))
end
scenarios.style_prof_rejected = function()
    local s = newSprite({})
    s.m_equipment.m_items:set(35, newItem(114))
    rebuild(s, 1, { [STAT_KIT] = TEMPUS_KIT, [114] = 2 })
    fastPass(s, 14)
    out("apr", apr(s)); out("marker", marker(s))
end

-- Weapon swaps between rebuilds: swap-in is picked up on the next pass (the
-- marker is only set when a bump happened); swap-out waits for the next
-- rebuild (bounded lag) and never accumulates.
scenarios.weapon_swap_on_fast_path = function()
    local s = newSprite({})
    s.m_equipment.m_selectedWeapon = 36 -- 0-pip long sword
    rebuild(s, 1, tempusFlail2)
    out("longsword", apr(s))
    s.m_equipment.m_selectedWeapon = 35 -- flail, no rebuild
    fastPass(s, 1)
    out("flail_swap_in_next_pass", apr(s))
    fastPass(s, 14)
    out("flail_after_fast_passes", apr(s))
    s.m_equipment.m_selectedWeapon = 36 -- swap out, no rebuild
    fastPass(s, 14)
    out("swap_out_before_rebuild", apr(s))
    rebuild(s, 1, tempusFlail2)
    out("swap_out_after_rebuild", apr(s))
end

-- Whole-number and ceiling arithmetic on the key encoding.
scenarios.encoding = function()
    local s = newSprite({})
    rebuild(s, 2, tempusFlail2); out("from_2", apr(s))    -- 2.0 -> 2.5 = key 8
    rebuild(s, 8, tempusFlail2); out("from_8", apr(s))    -- 2.5 -> 3.0 = key 3
    rebuild(s, 5, tempusFlail2); out("from_5", apr(s))    -- ceiling stays 5
    rebuild(s, 10, tempusFlail2); out("from_10", apr(s))  -- 4.5 -> 5
end

-- Binding surface missing: never write, trip the failure fuse, stay inert.
scenarios.missing_spellstates_array = function()
    local s = newSprite({ spellStates = false })
    rebuild(s, 1, tempusFlail2)
    fastPass(s, 30)
    out("apr", apr(s))
end
scenarios.missing_set_binding = function()
    local s = newSprite({ withSet = false })
    rebuild(s, 1, tempusFlail2)
    fastPass(s, 30)
    out("apr", apr(s))
end

-------------------------------------------------------------------------------

assert(listenerPath and markerState and scenario, "usage: lua cbrapr_sim.lua <listener> <state-id> <scenario>")
dofile(listenerPath)
out("listeners_registered", #listeners)
local run = scenarios[scenario]
assert(run, "unknown scenario " .. tostring(scenario))
run()
