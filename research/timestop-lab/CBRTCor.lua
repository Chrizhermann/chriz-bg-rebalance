-- Lab layer of the clock correction for every creature (lab steps 6 and 7). The correction itself
-- is Rebalance's shipped core, chriz-bg-rebalance/lua/CBRTC.lua, which staging copies beside this
-- file; the game loads it through M_CBRTC.lua only where the component is installed. This layer
-- adds what only the lab needs: installing by console request at the fresh main menu, Enable()
-- and Observe() while paused, and the recorder, attached through CBRTC.SetTrace(). It replaces
-- the one-subject prototype CBRTFix.lua, which stays as the record of steps 4 and 5; only one of
-- the two may be installed in a process. Where the component already started the core, Install()
-- reports it, and the recorder and both modes work on it the same way.
-- Lab only: a recorder logs the targets' inputs and decisions for chosen creatures, and Observe()
-- runs the gates with nothing but that recorder, so native controls use the same measurement.
if not (CBRTC and CBRTC.core) then Infinity_DoFile("CBRTC") end
assert(CBRTC and CBRTC.core, "Stage the correction core CBRTC.lua beside this file")
local C = CBRTC
if C.lab then return end
C.lab = true

local LIST_COUNTER = 0x1A40    -- the periodic list (+0x1A08) counter (+0x38)

-------------------------------------------------------------------------------------------------
-- Lab recorder: one JSON array per event of a watched creature (object ID), kept in memory until
-- exported. null marks what the correction does not know in observe mode; worker fields are read
-- as stored, the 16-bit ones signed.
--   ["F", id, world, counted]  a frozen pass; counted: the ticks it shifted
--   ["E", id, world, elapsed, list counter, check counter (+0x3A0), hp, frozen now, mode, T,
--    kappa, frozen ticks, game +0x7978 (poison, disease and the repeated EFF wait while it is
--    0x1016E or 0x3016E)]
--   ["D", id, world, worker, family, elapsed, result, native counter, counter, period, phase,
--    type (+0x20), +0x22, +0x24, remaining, done]  as the worker's update will see it
--   ["C", id, world, parent, worker, family, origin, deadline, timing, period, native phase,
--    phase, native remaining, remaining, rule, new]  rule: 0 native seed, 1 ahead, 2 carried,
--    3 behind; new: 1 for an effect the correction had not seen
-------------------------------------------------------------------------------------------------

local rec = {on=false, ids={}, lines={}, n=0, dropped=0, limit=400000, dirty=false, observe=false}
C.recorder = rec
local function num(v)
    if v == nil then return "null" end
    return string.format("%.0f", v)
end
local function push(fields)
    if rec.n >= rec.limit then
        rec.dropped = rec.dropped + 1
        return
    end
    rec.n = rec.n + 1
    rec.lines[rec.n] = "["..table.concat(fields, ",").."]"
end

C.SetTrace({
    watching = function(id) return rec.on and rec.ids[id] == true end,
    frozen = function(id, world, counted)
        push({'"F"', num(id), num(world), num(counted)})
    end,
    entry = function(sprite, id, world, game, elapsed, frozen, a)
        local mem = C.memory
        push({'"E"', num(id), num(world), num(elapsed), num(mem.r32(sprite + LIST_COUNTER)),
            num(mem.r32(sprite + 0x3A0)), num(mem.s16(sprite + 0x57C)), frozen and "1" or "0",
            num(a and a.mode), num(a and a.pT), num(a and a.kappa), num(a and a.frozen),
            num(mem.u32(game + 0x7978))})
    end,
    dispatch = function(id, world, worker, elapsed, result, native)
        local mem = C.memory
        local family = C.familyOf[mem.ptr(worker)]
        push({'"D"', num(id), num(world), num(worker), num(family and family.index or 0), num(elapsed),
            num(result), num(native), num(mem.r32(worker + 0x1C)), num(mem.s16(worker + 0x18)),
            num(mem.s16(worker + 0x1A)), num(mem.s16(worker + 0x20)), num(mem.s16(worker + 0x22)),
            num(mem.s16(worker + 0x24)), num(mem.r32(worker + 0x28)), num(mem.u32(worker + 8))})
    end,
    construct = function(id, world, parent, worker, family, nativePhase, nativeRemaining, rule, new)
        local mem = C.memory
        push({'"C"', num(id), num(world), num(parent), num(worker), num(family),
            num(mem.u32(parent + 0x6C)), num(mem.u32(parent + 0x28)), num(mem.u32(parent + 0x24)),
            num(mem.s16(worker + 0x18)), num(nativePhase), num(mem.s16(worker + 0x1A)),
            num(nativeRemaining), num(mem.r32(worker + 0x28)), num(rule), num(new)})
    end,
})

-------------------------------------------------------------------------------------------------
-- Lab steps.
-------------------------------------------------------------------------------------------------

local function readFile(path)
    local f = assert(io.open(path, "rb"), "Missing lab guard: "..path)
    local s = f:read("*a"); f:close(); return s
end
local function assertLab()
    assert(readFile("CBRTSLab.id") == "CBR TimeStop Lab 2730\n", "Not the owned lab")
    assert(readFile("engine.lua"):match('engine_name%s*=%s*"CBR TimeStop Lab 2730"'),
        "Wrong game profile")
end
local function assertPaused()
    local chitin = EngineGlobals and EngineGlobals.g_pBaldurChitin
    local world = chitin and chitin.m_pEngineWorld
    assert(world and ((tonumber(world.m_bPaused) or 0) ~= 0 or
        (tonumber(world.m_bHardPaused) or 0) ~= 0), "Pause the lab before this operation")
end
local function assertFreshMainMenu()
    local chitin = EngineGlobals and EngineGlobals.g_pBaldurChitin
    local game = chitin and chitin.m_pObjectGame
    local active = chitin and chitin.pActiveEngine
    local start = chitin and chitin.m_pEngineStart
    assert(game and active and start and game.m_bGameLoaded == 0 and
        game.m_bInLoadGame == 0 and game.m_bInLoadArea == 0 and
        EEex_UDToPtr(active) == EEex_UDToPtr(start),
        "Install only at the fresh main menu, before loading or creating a game")
end

-- At the fresh main menu of the owned lab: the core's checks, then the gates, off.
function C.Install()
    assert(not C.failed, "Earlier install failed; restart this disposable process")
    if C.installed then return {installed=true, already_installed=true, started=C.started == true} end
    assert(not (CBRTF and CBRTF.installed), "The step-5 prototype is installed; restart the lab")
    assertFreshMainMenu()
    assertLab()
    assert(EEex_Active and jit and EEex_GenLuaCall and EEex_HookAfterRestoreWithLabels and
        EEex_HookBeforeRestoreWithLabels, "EEex/LuaJIT unavailable")
    C.Patch(C.Inspect()) -- Validate every site before the first mutation.
    return {installed=true, sites=#C.sites, enabled=false}
end

local function verifyList(list, sprite)
    local walked, bound = {}, {}
    C.Walk(EEex_UDToPtr(list), function(effect) walked[#walked+1] = effect end)
    EEex_Utility_IterateCPtrList(list, function(effect) bound[#bound+1] = EEex_UDToPtr(effect) end)
    assert(#walked == #bound, "Effect list layout mismatch")
    for i = 1, #bound do assert(walked[i] == bound[i], "Effect list layout mismatch") end
    return #bound
end

-- Enable while paused in a loaded game. Portrait 0 proves the effect lists' offsets and node
-- layout; the correction then covers every creature.
function C.Enable(portrait)
    assert(C.installed and not C.failed, "Install the correction first")
    assertPaused()
    assert(not rec.on, "Stop recording before switching modes")
    EEex_Write32(C.block, 0) -- Fail closed: a refused enable leaves the gates off.
    local sprite = assert(EEex_Sprite_GetInPortrait(portrait or 0), "No creature in that portrait")
    local pointer = EEex_UDToPtr(sprite)
    local timed = EEex_UDToPtr(sprite.m_timedEffectList) - pointer
    local equipped = EEex_UDToPtr(sprite.m_equipedEffectList) - pointer
    assert(timed > 0 and timed < 0x10000 and equipped > 0 and equipped < 0x10000,
        "Unexpected effect list offsets")
    C.timedOffset, C.equippedOffset = timed, equipped
    local count = verifyList(sprite.m_timedEffectList, sprite) + verifyList(sprite.m_equipedEffectList, sprite)
    assert(count > 0, "No effect on that creature proves the list layout")
    C.Activate(timed, equipped)
    return C.Status()
end

-- Native controls: the gates run with nothing but the recorder and change no effect or worker.
function C.Observe()
    assert(C.installed and not C.failed, "Install the correction first")
    assertPaused()
    assert(not rec.on, "Stop recording before switching modes")
    EEex_Write32(C.block, 0)
    C.Reset()
    C.observe = true
    EEex_Write32(C.block, 1)
    return C.Status()
end

-- The creatures the recorder follows, by object ID.
function C.Watch(ids)
    for id in pairs(rec.ids) do rec.ids[id] = nil end
    for _, id in ipairs(ids) do
        assert(type(id) == "number" and id > 0 and id % 1 == 0, "Watch object IDs only")
        rec.ids[id] = true
    end
    return C.Status()
end

-- Starts a new record in the current mode, or stops the running one. An unexported record is
-- kept unless `discard`.
function C.Record(on, discard)
    if not on then
        rec.on = false
        return C.Status()
    end
    assert(not rec.on, "Already recording")
    assert(discard or not rec.dirty, "Export the previous record first")
    rec.lines, rec.n, rec.dropped = {}, 0, 0
    rec.observe, rec.dirty, rec.on = C.observe == true, true, true
    return C.Status()
end

-- cbr-timestop-output/NAME.jsonl: a header object, then one event per line.
function C.ExportRecord(name)
    assertPaused()
    assert(not rec.on, "Stop recording before the export")
    assert(type(name) == "string" and name:match("^[%w_-]+$"), "Use a simple unique record name")
    local path = "cbr-timestop-output/"..name..".jsonl"
    local existing = io.open(path, "rb")
    if existing then existing:close(); error("Record already exists: "..path) end
    local ids, counts = {}, {}
    for id in pairs(rec.ids) do ids[#ids + 1] = id end
    table.sort(ids)
    for i, id in ipairs(ids) do ids[i] = num(id) end
    for _, k in ipairs(C.statNames) do counts[#counts + 1] = '"'..k..'":'..num(C.stats[k]) end
    local header = '{"schema":1,"name":"'..name..'","observe":'..tostring(rec.observe)..
        ',"events":'..num(rec.n)..',"dropped":'..num(rec.dropped)..',"watch":['..
        table.concat(ids, ",")..'],"stats":{'..table.concat(counts, ",")..'}}\n'
    local f = assert(io.open(path, "wb"))
    local ok, why = f:write(header, table.concat(rec.lines, "\n", 1, rec.n), rec.n > 0 and "\n" or "")
    f:close()
    assert(ok, why)
    rec.dirty = false
    return {path=path, events=rec.n, dropped=rec.dropped}
end

function C.ActorState(sprite)
    local a = C.actors[sprite]
    if not a then return nil end
    return {id=a.id, frozen=a.frozen, last_frozen=a.lastFrozen, last_pass=a.lastPass, kappa=a.kappa,
        last_t=a.lastT, next_t=a.nextT, seen=a.seen, parents=C.Count(a.parents), fresh=C.Count(a.fresh)}
end

local coreStatus = C.Status
function C.Status()
    local out = coreStatus()
    out.observe = C.observe == true
    out.recorder = {on=rec.on, events=rec.n, dropped=rec.dropped, watched=C.Count(rec.ids),
        unexported=rec.dirty}
    return out
end
