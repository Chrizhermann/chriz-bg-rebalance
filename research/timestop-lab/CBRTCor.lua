-- BG2:EE 2.7.3.0 / EEex 1.3 clock correction for every creature (lab step 6). It replaces the
-- one-subject prototype CBRTFix.lua, which stays as the record of steps 4 and 5; only one of the
-- two may be installed in a process. Nothing is patched on load; Install() at the fresh main menu,
-- then Enable() and Disable() while paused.
-- Christopher's rule (research note 10): in a Time Stop everything but the caster and
-- Time-Stop-immune creatures stops; Haste and Slow change actions and movement only, periodic
-- effects keep world time; the native heal pattern at normal speed stays.
--   Time Stop: in each world tick in which the engine marks a creature frozen, every effect of it
--     with an absolute deadline (timing 0x1000) or delayed start (6, 7, 8) moves one tick later,
--     and so does the time origin (+0x6C) of its poison, disease, regeneration and repeated
--     effects (op25, op78, op98, op272), timed or equipped. A slowed creature counts the ticks it
--     skipped from its own frozen passes and, where a stop began or ended on one, from the other
--     frozen creatures' marks. Time compression during a stop moves them by the compressed span.
--   Haste, Slow and pauses: each creature's periodic workers (regeneration, poison, disease,
--     repeated EFF) run once per active tick, world time minus the creature's frozen ticks. The
--     pulse counter is a fixed per-creature offset plus active time, so at normal speed it is the
--     native list counter. A slowed creature's sparser updates count down every active tick since
--     the last one and deliver the pulse that fell in between, but never one from before a new
--     effect existed. A creature not processed for more than MAXGAP ticks (an area left alone)
--     restarts on the native list counter instead of catching up.
--   Rebuilds keep the native reseed, taken at the active tick a creature without Haste, Slow,
--     pauses or stops would have rebuilt: a worker built after its creature's delivery in this
--     tick (a second hasted update, a pause, a frozen tick) seeds and counts down as of the next
--     active tick; one rebuilt in the pass after a slowed pass that delivered a pulse, as of the
--     tick after that pulse. The rebuild the end of a stop forces keeps each worker's phase.
--   Time compression (rest, travel) passes unchanged, counts as delivered and, like a long gap,
--     continues on the native list counter.
-- The bookkeeping is Lua behind thin assembly gates (EEex_GenLuaCall). A Lua error turns every
-- gate off and leaves the game native; per-creature state is not saved and restarts after a load.
-- Lab only: a recorder logs the targets' inputs and decisions for chosen creatures, and Observe()
-- runs the gates with nothing but that recorder, so native controls use the same measurement.
if CBRTC then return end
CBRTC = {schema = 1, installed = false}
local C = CBRTC

local BLOCK_SIZE = 64          -- +0 enabled (the gates read it), +4 Lua errors seen by the gates
local MAXGAP = 14              -- a longer gap since the last delivery restarts the clock
-- Creatures unseen and parents not rebuilt for STALE_AGE ticks are forgotten; a forgotten parent
-- that comes back counts as a new effect.
local STALE_AGE, SWEEP_INTERVAL = 9000, 900
local LIST_COUNTER = 0x1A40    -- the periodic list (+0x1A08) counter (+0x38)
local ERROR = -2               -- what a gate leaves in rax after a Lua error
C.MAXGAP, C.STALE_AGE = MAXGAP, STALE_AGE

-- The four periodic worker classes: vtable RVA, the AIUpdate in slot 1, and the step the worker
-- adds to the counter before testing (counter + step) % 15 == 0.
C.families = {
    {index=1, name="regeneration", vtable=0x598B18, update=0x1A5CA0, step=1},
    {index=2, name="poison",       vtable=0x598AE8, update=0x1A59F0, step=2},
    {index=3, name="disease",      vtable=0x598B00, update=0x1A4D90, step=1},
    {index=4, name="repeat",       vtable=0x598B48, update=0x1A47B0, step=1},
}
local ORIGIN_OPCODES = {[25]=true, [78]=true, [98]=true, [272]=true}
local SHIFT_TIMINGS = {[0x1000]=true, [6]=true, [7]=true, [8]=true}

local REGS = {"rax", "rcx", "rdx", "rbx", "rbp", "rsi", "rdi",
              "r8", "r9", "r10", "r11", "r12", "r13", "r14", "r15"}
local SAVED = {}
for i, name in ipairs(REGS) do SAVED[name] = (#REGS - i) * 8 end
local ARGS = {"r12", "r13", "r14", "r15"}
C.argRegisters = ARGS

-- Each window was decoded from the pinned executable; none holds a relative operand or a branch
-- target past its first byte. "after" replays the window first, "before" last. `args` are the
-- registers whose values the Lua function receives, in order; `family` is appended as a constant.
C.sites = {
    -- ProcessEffectList: the engine has just marked a frozen noncaster (sprite +0x520C).
    {id=1, name="frozen", rva=0x3ABA9D, bytes="44 89 AE 0C 52 00 00", kind="after",
        fn="CBRTC_Frozen", args={"rsi"}},
    -- Periodic dispatcher entry, reached by every ProcessEffectList tail and time compression.
    {id=2, name="entry", rva=0x226513, bytes="48 8B 79 08 45 8B F0 4C 8B FA 48 8B F1 48 8B EF",
        kind="after", fn="CBRTC_Entry", args={"r15", "r14"}},
    -- The list counter has been copied into the worker; r8d holds elapsed.
    {id=3, name="dispatch", rva=0x226543, bytes="89 43 1C 49 8B D7", kind="after",
        fn="CBRTC_Dispatch", args={"r15", "rbx", "r8"}, filter="vtable", result="r8"},
    -- The four ApplyEffects: phase seeded (and SlowPoison applied where it precedes the seed),
    -- before CObList::AddTail. Disease's SlowPoison and repeated EFF's come after the hook.
    {id=4, name="construct_regeneration", rva=0x1BEDD6, bytes="48 8D 8D 08 1A 00 00", kind="before",
        fn="CBRTC_Construct", args={"rbp", "rdi", "rbx"}, family=1},
    {id=5, name="construct_poison", rva=0x1BBB09, bytes="48 8D 8D 08 1A 00 00", kind="before",
        fn="CBRTC_Construct", args={"rbp", "rdi", "rbx"}, family=2},
    {id=6, name="construct_disease", rva=0x1B1894, bytes="48 8D 8F 08 1A 00 00", kind="before",
        fn="CBRTC_Construct", args={"rdi", "rsi", "rbx"}, family=3},
    {id=7, name="construct_disease_resource", rva=0x1B1AC1, bytes="48 8D 8F 08 1A 00 00",
        kind="before", fn="CBRTC_Construct", args={"rdi", "rsi", "rbx"}, family=3},
    {id=8, name="construct_repeat", rva=0x1BFEC8, bytes="66 89 53 1A 8B 57 64", kind="after",
        fn="CBRTC_Construct", args={"rsi", "rdi", "rbx"}, family=4},
}

local function hex(n) return string.format("0x%X", n) end
local function u32(n) return n % 4294967296 end
local function s32(n) n = u32(n); return n >= 2147483648 and n - 4294967296 or n end

-- Native memory access, replaceable by host tests: signed and unsigned 32-bit reads and writes,
-- signed 16-bit read, 16-bit write, pointer read.
local mem
function C.UseMemory(m) mem = m end
local function eeexMemory()
    return {r32=EEex_Read32, u32=EEex_ReadU32, s16=EEex_Read16, w32=EEex_Write32,
        wu32=EEex_WriteU32, w16=EEex_WriteU16, ptr=EEex_ReadPtr}
end

-------------------------------------------------------------------------------------------------
-- Per-creature state, keyed by sprite pointer and reset when the object ID (+0x48) differs.
-------------------------------------------------------------------------------------------------

local actors, familyOf = {}, {}
C.actors = actors
local stats = {}
local STAT_NAMES = {"frozen_ticks", "deadline_shifts", "origin_shifts", "delivered", "suppressed",
    "stretched", "boundaries", "restarts", "compressed", "compressed_frozen", "ahead", "behind",
    "carried", "fresh", "unmatched", "actors_created", "actors_swept", "constructs"}
local function resetStats() for _, k in ipairs(STAT_NAMES) do stats[k] = 0 end end
resetStats()
C.stats = stats
local NATIVE, SUPPRESS, RESTART, DELIVER = 0, 1, 2, 3
C.modes = {native=NATIVE, suppress=SUPPRESS, restart=RESTART, deliver=DELIVER}
local lastSweep = 0

function C.Reset()
    for sprite in pairs(actors) do actors[sprite] = nil end
    C.current, C.currentSprite, lastSweep = nil, nil, 0
    C.stopStart, C.stopLast = nil, nil
    resetStats()
end

local function actorOf(sprite, world)
    local id = mem.u32(sprite + 0x48)
    local a = actors[sprite]
    if a == nil or a.id ~= id then
        a = {id=id, frozen=0, lastFrozen=-1, prevFrozen=false, lastPass=-1, seen=world, parents={},
            fresh={}, byWorker={}, behind={}, mode=NATIVE, pT=0, pLast=0, pNext=0}
        actors[sprite] = a
        stats.actors_created = stats.actors_created + 1
    elseif world > a.seen then
        a.seen = world
    end
    return a
end

local function worldTime()
    local chitin = mem.ptr(C.chitinGlobal)
    if chitin == 0 then return nil end
    local game = mem.ptr(chitin + 0x1090)
    if game == 0 then return nil end
    return mem.u32(game + 0x3FA0), game
end

-- Active time: world time minus frozen ticks. At the value a pause stepped back to during a stop,
-- the frozen tick already counted above it lies between now and the next active tick, so a
-- worker built there counts it in its `ahead` ticks; the stop's end rebuilds it anyway.
local function activeTime(a, world)
    return world - a.frozen
end

-- The first clock of a creature: nothing delivered yet at T, unless T was delivered before a stop
-- that is freezing it now.
local function startClock(a, T, delivered)
    a.lastT = delivered and T or T - 1
    a.nextT = a.lastT + 1
end

-- CPtrList: m_pNodeHead +8; CNode pNext +0, data +0x10. Bounded against a corrupt cyclic list.
local function walk(list, fn)
    local node, guard = mem.ptr(list + 8), 4096
    while node ~= 0 and guard > 0 do
        local effect = mem.ptr(node + 0x10)
        node = mem.ptr(node)
        guard = guard - 1
        if effect ~= 0 then fn(effect) end
    end
end

local function shiftEffects(sprite, d)
    walk(sprite + C.timedOffset, function(effect)
        if SHIFT_TIMINGS[mem.u32(effect + 0x24)] then
            local deadline = mem.u32(effect + 0x28)
            -- A deadline at the top of the range is effectively endless; never wrap it.
            if deadline <= 4294967295 - d then
                mem.wu32(effect + 0x28, deadline + d)
                stats.deadline_shifts = stats.deadline_shifts + 1
            end
        end
        if ORIGIN_OPCODES[mem.u32(effect + 0x10)] then
            mem.wu32(effect + 0x6C, u32(mem.u32(effect + 0x6C) + d))
            stats.origin_shifts = stats.origin_shifts + 1
        end
    end)
    walk(sprite + C.equippedOffset, function(effect)
        if ORIGIN_OPCODES[mem.u32(effect + 0x10)] then
            mem.wu32(effect + 0x6C, u32(mem.u32(effect + 0x6C) + d))
            stats.origin_shifts = stats.origin_shifts + 1
        end
    end)
end

-- The engine's own freeze test (0x3ABA67..0x3ABA9B): a stop runs, the creature is not its caster,
-- and its Time Stop immunity stat (op310) is zero.
local function frozenNow(sprite, game)
    if mem.u32(game + 0x9690) == 0 or mem.u32(game + 0x9694) == mem.u32(sprite + 0x48) then
        return false
    end
    local stat = mem.u32(sprite + 0x4EA4) == 0 and 0x20A0 or 0x13F8
    return mem.u32(sprite + stat) == 0
end

-- A stop that ended on a tick a slowed creature skipped: the ticks after its last frozen pass in
-- which other creatures were still frozen count for it too. Runs before anything in the creature's
-- first pass after the stop reads its effects.
local function catchUp(a, sprite, world)
    local last = C.stopLast
    if a.prevFrozen and last and a.lastFrozen >= 0 and last > a.lastFrozen and last < world
            and last - a.lastFrozen <= MAXGAP then
        local d = last - a.lastFrozen
        shiftEffects(sprite, d)
        a.frozen = a.frozen + d
        a.lastFrozen = last
        stats.frozen_ticks = stats.frozen_ticks + d
    end
end

local function sweep(world)
    if world - lastSweep < SWEEP_INTERVAL then return end
    lastSweep = world
    for sprite, a in pairs(actors) do
        if a.seen < world - STALE_AGE then
            actors[sprite] = nil
            stats.actors_swept = stats.actors_swept + 1
        elseif a.lastT then
            for parent, e in pairs(a.parents) do
                if a.lastT - e.T > STALE_AGE then
                    a.parents[parent] = nil
                    if a.byWorker[e.worker] == e then a.byWorker[e.worker] = nil end
                end
            end
        end
    end
end

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
local function watched(id) return rec.on and rec.ids[id] == true end

local function noteFrozen(id, world, counted)
    push({'"F"', num(id), num(world), num(counted)})
end
local function noteEntry(sprite, id, world, game, elapsed, frozen, a)
    push({'"E"', num(id), num(world), num(elapsed), num(mem.r32(sprite + LIST_COUNTER)),
        num(mem.r32(sprite + 0x3A0)), num(mem.s16(sprite + 0x57C)), frozen and "1" or "0",
        num(a and a.mode), num(a and a.pT), num(a and a.kappa), num(a and a.frozen),
        num(mem.u32(game + 0x7978))})
end
local function noteDispatch(id, world, worker, elapsed, result, native)
    local family = familyOf[mem.ptr(worker)]
    push({'"D"', num(id), num(world), num(worker), num(family and family.index or 0), num(elapsed),
        num(result), num(native), num(mem.r32(worker + 0x1C)), num(mem.s16(worker + 0x18)),
        num(mem.s16(worker + 0x1A)), num(mem.s16(worker + 0x20)), num(mem.s16(worker + 0x22)),
        num(mem.s16(worker + 0x24)), num(mem.r32(worker + 0x28)), num(mem.u32(worker + 8))})
end
local function noteConstruct(id, world, parent, worker, family, nativePhase, nativeRemaining, rule, new)
    push({'"C"', num(id), num(world), num(parent), num(worker), num(family),
        num(mem.u32(parent + 0x6C)), num(mem.u32(parent + 0x28)), num(mem.u32(parent + 0x24)),
        num(mem.s16(worker + 0x18)), num(nativePhase), num(mem.s16(worker + 0x1A)),
        num(nativeRemaining), num(mem.r32(worker + 0x28)), num(rule), num(new)})
end

-------------------------------------------------------------------------------------------------
-- Gate targets. Each returns a number: Dispatch the elapsed to use (-1 keeps the native one), the
-- others 0. None may return ERROR.
-------------------------------------------------------------------------------------------------

function C.Frozen(sprite)
    local world = worldTime()
    if not world then return 0 end
    if C.observe then
        local id = mem.u32(sprite + 0x48)
        if watched(id) then noteFrozen(id, world, nil) end
        return 0
    end
    local a = actorOf(sprite, world)
    -- Every frozen creature marks the stop's ticks.
    if C.stopLast == nil or world > C.stopLast + 1 then C.stopStart = world end
    if C.stopLast == nil or world > C.stopLast then C.stopLast = world end
    -- A hasted creature passes twice per tick; a pause steps world time back.
    if a.lastFrozen >= 0 and world <= a.lastFrozen then
        if watched(a.id) then noteFrozen(a.id, world, 0) end
        return 0
    end
    local d = 1
    if a.prevFrozen and a.lastFrozen >= 0 and world - a.lastFrozen <= MAXGAP then
        -- A slowed creature whose previous pass was frozen too: so were the ticks in between.
        d = world - a.lastFrozen
    elseif a.lastPass >= 0 and C.stopStart > a.lastPass and world - C.stopStart <= MAXGAP then
        -- The stop began on a tick it skipped.
        d = world - C.stopStart + 1
    end
    shiftEffects(sprite, d)
    a.frozen = a.frozen + d
    a.lastFrozen = world
    stats.frozen_ticks = stats.frozen_ticks + d
    if watched(a.id) then noteFrozen(a.id, world, d) end
    return 0
end

function C.Entry(sprite, elapsed)
    C.current, C.currentSprite = nil, nil
    local world, game = worldTime()
    if not world then return 0 end
    if C.observe then
        local id = mem.u32(sprite + 0x48)
        if watched(id) then noteEntry(sprite, id, world, game, elapsed, frozenNow(sprite, game), nil) end
        return 0
    end
    local a = actorOf(sprite, world)
    catchUp(a, sprite, world)
    local frozenPass = a.lastFrozen == world
    -- Time compression during a stop: a frozen creature's effects do not run through the span.
    if elapsed > 1 and frozenNow(sprite, game) then
        shiftEffects(sprite, elapsed)
        a.frozen = a.frozen + elapsed
        a.lastFrozen = world
        frozenPass = true
        stats.compressed_frozen = stats.compressed_frozen + 1
    end
    local T = activeTime(a, world)
    if a.kappa == nil then a.kappa = mem.r32(sprite + LIST_COUNTER) - T end
    if a.lastT == nil then startClock(a, T, frozenPass) end
    a.prevFrozen = frozenPass
    a.pT, a.pLast, a.pNext = T, a.lastT, a.nextT
    if elapsed ~= 1 then
        a.mode = NATIVE
        if elapsed > 1 and not frozenPass then
            -- Rest and travel: the engine delivers the jump itself and moves the creature's pulse
            -- grid against world time; continue on the native list counter.
            if a.lastT < T then a.lastT = T end
            if a.nextT < T + 1 then a.nextT = T + 1 end
            a.kappa = mem.r32(sprite + LIST_COUNTER) - T
            stats.compressed = stats.compressed + 1
        end
    elseif T <= a.lastT then
        -- A second hasted update, a frozen tick, or the repeated tick after a pause.
        a.mode = SUPPRESS
    elseif T - a.lastT > MAXGAP then
        -- Not processed for a while: continue from the native list counter.
        a.mode = RESTART
        a.kappa = mem.r32(sprite + LIST_COUNTER) - T
        a.lastT, a.nextT = T, T + 1
        stats.restarts = stats.restarts + 1
    else
        a.mode = DELIVER
        a.lastT, a.nextT = T, T + 1
    end
    if next(a.fresh) ~= nil then
        for worker, first in pairs(a.fresh) do
            if first < T - MAXGAP then a.fresh[worker] = nil end
        end
    end
    if next(a.behind) ~= nil then
        for worker, from in pairs(a.behind) do
            if from < T - MAXGAP then a.behind[worker] = nil end
        end
    end
    -- The previous pass's pulses served this pass's rebuild; this pass records its own.
    a.pulse = nil
    if elapsed == 1 then a.lastPass = world end
    C.current, C.currentSprite, C.currentWorld = a, sprite, world
    if watched(a.id) then noteEntry(sprite, a.id, world, game, elapsed, frozenNow(sprite, game), a) end
    sweep(world)
    return 0
end

local function dispatch(a, worker)
    -- The phase the worker's last update left; a stop's forced rebuild continues from it.
    local e = a.byWorker[worker]
    if e then e.phase = mem.s16(worker + 0x1A) end
    local mode = a.mode
    if mode == NATIVE then return -1 end
    if mode == SUPPRESS then
        -- A no-op call: elapsed 0 and no 15-tick boundary.
        mem.w32(worker + 0x1C, 0)
        stats.suppressed = stats.suppressed + 1
        return 0
    end
    local T = a.pT
    local family = familyOf[mem.ptr(worker)]
    local step = family and family.step or 1
    if mode == RESTART then
        local counter = s32(T + a.kappa)
        mem.w32(worker + 0x1C, counter)
        if s32(counter + step) % 15 == 0 then a.pulse = T end
        return 1
    end
    -- The pulse scan reaches back to the last delivered tick, but not before a new effect existed.
    local floor = a.pLast
    local first = a.fresh[worker]
    if first ~= nil then
        a.fresh[worker] = nil
        if first - 1 > floor then floor = first - 1 end
    end
    -- Count down every active tick since the first one not yet counted: 1 normally, 2 slowed.
    local nextT = a.behind[worker] or a.pNext
    a.behind[worker] = nil
    local ticks = T - nextT + 1
    if ticks < 0 then ticks = 0 end
    local deliver, gap = T, T - floor
    if gap >= 2 then
        -- Deliver nothing past the tick the remaining duration runs out, nextT + remaining - 1.
        local lastTick = nextT + mem.r32(worker + 0x28) - 1
        if lastTick < T then
            deliver = lastTick
            if deliver < floor + 1 then deliver = floor + 1 end
            gap = deliver - floor
        end
    end
    local tick = deliver
    if gap >= 2 then
        -- The latest boundary, (counter + step) % 15 == 0, in the gap's ticks floor+1 .. deliver.
        local m = s32(deliver + a.kappa + step) % 15
        if m < gap then
            tick = deliver - m
            stats.boundaries = stats.boundaries + 1
        end
    end
    local counter = s32(tick + a.kappa)
    mem.w32(worker + 0x1C, counter)
    if s32(counter + step) % 15 == 0 and (a.pulse == nil or tick > a.pulse) then a.pulse = tick end
    if ticks ~= 1 then stats.stretched = stats.stretched + 1 end
    stats.delivered = stats.delivered + 1
    return ticks
end

function C.Dispatch(sprite, worker, elapsed)
    if C.observe then
        local id = mem.u32(sprite + 0x48)
        if watched(id) then noteDispatch(id, worldTime(), worker, elapsed, -1, mem.r32(worker + 0x1C)) end
        return -1
    end
    local a = C.current
    if a == nil or C.currentSprite ~= sprite then
        stats.unmatched = stats.unmatched + 1
        return -1
    end
    local native = watched(a.id) and mem.r32(worker + 0x1C)
    local result = dispatch(a, worker)
    if native then noteDispatch(a.id, C.currentWorld, worker, elapsed, result, native) end
    return result
end

-- The native phase seed, floor(u32(at - origin) / 15) % movsx(period) with unsigned division
-- (0x1BEDA2 and CPersistantEffect::SetPeriodCounter), for the world time `at`.
local function seed(worker, at, origin)
    local period = mem.s16(worker + 0x18)
    local phase = 0
    if period ~= 0 then
        local divisor = period < 0 and period + 4294967296 or period
        phase = math.floor(u32(at - origin) / 15) % divisor
    end
    mem.w16(worker + 0x1A, phase % 65536)
end

function C.Construct(sprite, parent, worker, family)
    local world = worldTime()
    if not world then return 0 end
    -- The site's own class: anything else means the registers are not what the gate assumes.
    if familyOf[mem.ptr(worker)] ~= C.families[family] then
        stats.unmatched = stats.unmatched + 1
        return 0
    end
    local nativePhase, nativeRemaining = mem.s16(worker + 0x1A), mem.r32(worker + 0x28)
    if C.observe then
        local id = mem.u32(sprite + 0x48)
        if watched(id) then
            noteConstruct(id, world, parent, worker, family, nativePhase, nativeRemaining, nil, nil)
        end
        return 0
    end
    local a = actorOf(sprite, world)
    catchUp(a, sprite, world)
    local T = activeTime(a, world)
    if a.lastT == nil then startClock(a, T, a.lastFrozen == world) end
    stats.constructs = stats.constructs + 1
    -- A rebuilt parent keeps its origin, moved only by the frozen ticks counted since; a reused
    -- address with another origin is a new effect. Rebuilds follow events, not a schedule, so
    -- there is no time limit.
    local origin = mem.u32(parent + 0x6C)
    local e = a.parents[parent]
    local known = e ~= nil and origin == u32(e.origin + a.frozen - e.frozen)
    local phase = known and e.phase or nil
    if e == nil then
        e = {}
        a.parents[parent] = e
    elseif a.byWorker[e.worker] == e then
        a.byWorker[e.worker] = nil
    end
    e.T, e.origin, e.frozen, e.worker, e.phase = T, origin, a.frozen, worker, nil
    a.byWorker[worker] = e
    a.behind[worker] = nil
    local first, rule = T, 0
    if a.lastT >= T then
        -- Built after this tick's delivery: seed and count down as a rebuild on the next active
        -- tick would.
        local ahead = a.lastT - T + 1
        seed(worker, world + ahead, origin)
        mem.w32(worker + 0x28, s32(mem.r32(worker + 0x28) - ahead))
        first = a.lastT + 1
        rule = 1
        stats.ahead = stats.ahead + 1
    elseif phase ~= nil and a.prevFrozen and a.lastFrozen ~= world then
        -- The rebuild the end of a stop forces: the phase continues where the stop froze it.
        mem.w16(worker + 0x1A, phase % 65536)
        rule = 2
        stats.carried = stats.carried + 1
    elseif known and a.pulse ~= nil and a.pulse + 1 < T then
        -- After a slowed pass that delivered a pulse: seed and count down as the rebuild on the
        -- tick after that pulse would have. The pulse scan needs nothing more, the next boundary
        -- being 15 ticks after it.
        local behind = T - a.pulse - 1
        seed(worker, world - behind, origin)
        mem.w32(worker + 0x28, s32(mem.r32(worker + 0x28) + behind))
        a.behind[worker] = a.pulse + 1
        rule = 3
        stats.behind = stats.behind + 1
    end
    a.nextT = first
    if known then
        a.fresh[worker] = nil
    else
        -- A new effect pulses only after the tick it was applied: its origin, in active time.
        a.fresh[worker] = T - u32(world - origin) + 1
        stats.fresh = stats.fresh + 1
    end
    if watched(a.id) then
        noteConstruct(a.id, world, parent, worker, family, nativePhase, nativeRemaining, rule, known and 0 or 1)
    end
    return 0
end

CBRTC_Frozen, CBRTC_Entry = C.Frozen, C.Entry
CBRTC_Dispatch, CBRTC_Construct = C.Dispatch, C.Construct

-------------------------------------------------------------------------------------------------
-- Assembly gates. Public for offline assembly/emulation; no native memory is accessed here.
-- `opts.luaCall(fn, nargs, prefix)` returns the fragment that calls Lua with the arguments in
-- ARGS order and leaves the result in rax, or ERROR in rax on a Lua error. `opts.macros` emits
-- EEex's #STACK_MOD bookkeeping.
-------------------------------------------------------------------------------------------------

function C.BuildGate(site, opts)
    local out, lines = {}, {}
    local function emit(s) lines[#lines+1] = s end
    local function flush()
        if #lines > 0 then
            out[#out+1] = table.concat(lines, "\n").."\n"
            lines = {}
        end
    end
    local prefix = "cbrtc_"..site.id.."_"
    local function label(s) return prefix..s end
    -- The saved registers lie above the 96 bytes of saved xmm0-xmm5.
    local function saved(reg) return "[rsp+"..(96 + SAVED[reg]).."]" end
    emit("pushfq")
    for _, reg in ipairs(REGS) do emit("push "..reg) end
    if opts.macros then emit("#STACK_MOD(128)") end
    emit("lea rsp, [rsp-96]")
    if opts.macros then emit("#STACK_MOD(96)") end
    for i = 0, 5 do emit("movdqu xmmword ptr [rsp+"..(i * 16).."], xmm"..i) end
    emit("mov rax, "..hex(opts.block))
    emit("cmp dword ptr [rax], 1")
    emit("jne "..label("exit"))
    if site.filter == "vtable" then
        -- Only the four periodic worker classes reach Lua.
        emit("mov rax, qword ptr "..saved(site.args[2]))
        emit("mov rax, qword ptr [rax]")
        for _, family in ipairs(C.families) do
            emit("mov rcx, "..hex(opts.base + family.vtable))
            emit("cmp rax, rcx")
            emit("je "..label("call"))
        end
        emit("jmp "..label("exit"))
        emit(label("call")..":")
    end
    for i, reg in ipairs(site.args) do emit("mov "..ARGS[i]..", qword ptr "..saved(reg)) end
    local nargs = #site.args
    if site.family then
        nargs = nargs + 1
        emit("mov "..ARGS[nargs]..", "..site.family)
    end
    flush()
    out[#out+1] = opts.luaCall(site.fn, nargs, prefix)
    emit("cmp rax, "..ERROR)
    emit("jne "..label("ok"))
    -- A Lua error: every gate goes native from the next pass on.
    emit("mov rcx, "..hex(opts.block))
    emit("mov dword ptr [rcx], 0")
    emit("inc dword ptr [rcx+4]")
    emit("jmp "..label("exit"))
    emit(label("ok")..":")
    if site.result then
        emit("test rax, rax")
        emit("js "..label("exit"))
        emit("mov qword ptr "..saved(site.result)..", rax")
    end
    emit(label("exit")..":")
    for i = 0, 5 do emit("movdqu xmm"..i..", xmmword ptr [rsp+"..(i * 16).."]") end
    emit("lea rsp, [rsp+96]")
    if opts.macros then emit("#STACK_MOD(-96)") end
    for i = #REGS, 1, -1 do emit("pop "..REGS[i]) end
    if opts.macros then emit("#STACK_MOD(-128)") end
    emit("popfq")
    flush()
    return out
end

-- The in-game Lua call: EEex_GenLuaCall reads its arguments from ARGS and calls the named global.
local function eeexLuaCall(fn, nargs, prefix)
    local args = {}
    for i = 1, nargs do
        local reg = ARGS[i]
        args[i] = function(offset) return {"mov qword ptr ss:[rsp+#$(1)], "..reg.." #ENDL", {offset}} end
    end
    return EEex_FlattenTable({
        -- GenLuaCall needs 16 bytes of pcallk arguments, 16 of locals and 8 per argument.
        {"#MAKE_SHADOW_SPACE(#$(1)) #ENDL", {32 + 8 * nargs}},
        EEex_GenLuaCall(fn, {args=args, returnType=EEex_LuaCallReturnType.Number}),
        {"jmp "..prefix.."lua_ok #ENDL",
         "call_error: #ENDL",
         "mov rax, "..ERROR.." #ENDL",
         prefix.."lua_ok: #ENDL",
         "#DESTROY_SHADOW_SPACE #ENDL"},
    })
end

-------------------------------------------------------------------------------------------------
-- Lab steps.
-------------------------------------------------------------------------------------------------

local function byteList(s)
    local out = {}
    for b in s:gmatch("%x%x") do out[#out+1] = tonumber(b, 16) end
    return out
end
local function checkBytes(address, bytes)
    for i, b in ipairs(byteList(bytes)) do
        assert(EEex_ReadU8(address+i-1) == b,
            "Unexpected instruction at "..hex(address+i-1).."; no correction installed")
    end
end
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

function C.Inspect()
    assertLab()
    assert(EEex_Active and jit and EEex_GenLuaCall and EEex_HookAfterRestoreWithLabels and
        EEex_HookBeforeRestoreWithLabels, "EEex/LuaJIT unavailable")
    local base = EEex_Label("Data-CGameEffect::vftable") - 0x58F020
    assert(base > 0 and base % 4096 == 0, "Unexpected image base")
    assert(EEex_GetImageBase() == base, "Image base disagrees with EEex")
    checkBytes(base, "4D 5A")
    local nt = EEex_Read32(base+0x3C)
    assert(nt >= 0x40 and nt <= 0x1000, "Unexpected PE header")
    checkBytes(base+nt, "50 45 00 00 64 86")
    assert(EEex_Read32(base+nt+8) == 0x6A18D73D, "Wrong executable timestamp")
    for _, family in ipairs(C.families) do
        assert(EEex_ReadPtr(base+family.vtable+8) == base+family.update,
            "Wrong "..family.name.." vtable")
    end
    for _, site in ipairs(C.sites) do checkBytes(base+site.rva, site.bytes) end
    return {base=base, sites=#C.sites, game="2.7.3.0"}
end

local function bindBase(base)
    C.base = base
    C.chitinGlobal = base + 0x667548
    for key in pairs(familyOf) do familyOf[key] = nil end
    for _, family in ipairs(C.families) do familyOf[base + family.vtable] = family end
end
-- Host tests bind a synthetic image base and list offsets without installing.
function C.Bind(base, timedOffset, equippedOffset)
    bindBase(base)
    C.timedOffset, C.equippedOffset = timedOffset, equippedOffset
end

function C.Install()
    assert(not C.failed, "Earlier install failed; restart this disposable process")
    if C.installed then return {installed=true, already_installed=true} end
    assert(not (CBRTF and CBRTF.installed), "The step-5 prototype is installed; restart the lab")
    assertFreshMainMenu()
    local inspected = C.Inspect() -- Validate every site before the first mutation.
    mem = eeexMemory()
    bindBase(inspected.base)
    C.block = EEex_Malloc(BLOCK_SIZE)
    assert(C.block and C.block ~= 0, "Cannot allocate correction block")
    for offset = 0, BLOCK_SIZE - 4, 4 do EEex_Write32(C.block + offset, 0) end
    local opts = {block=C.block, base=C.base, macros=true, luaCall=eeexLuaCall}
    local bodies = {}
    for _, site in ipairs(C.sites) do bodies[site.id] = EEex_FlattenTable(C.BuildGate(site, opts)) end
    -- Assemble every body once before patching; an assembly error stops here.
    for _, site in ipairs(C.sites) do EEex_JITNear(EEex_FlattenTable({bodies[site.id], "ret #ENDL"})) end
    EEex_DisableCodeProtection()
    local ok, why = pcall(function()
        for _, site in ipairs(C.sites) do
            local address, n = C.base+site.rva, #byteList(site.bytes)
            if site.kind == "after" then
                EEex_HookAfterRestoreWithLabels(address, 0, n, n, {}, bodies[site.id])
            else
                EEex_HookBeforeRestoreWithLabels(address, 0, n, n, {}, bodies[site.id])
            end
        end
    end)
    EEex_EnableCodeProtection()
    if not ok then
        C.failed = true; EEex_Write32(C.block, 0)
        error("Correction install incomplete; restart lab: "..tostring(why))
    end
    C.installed = true
    -- Object IDs and pointers start over in a new session; the correction itself stays enabled.
    EEex_GameState_AddDestroyedListener(function()
        C.Reset()
        C.sessions = (C.sessions or 0) + 1
    end)
    return {installed=true, sites=#C.sites, enabled=false}
end

local function verifyList(list, sprite)
    local walked, bound = {}, {}
    walk(EEex_UDToPtr(list), function(effect) walked[#walked+1] = effect end)
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
    C.Reset()
    C.observe = false
    EEex_Write32(C.block, 1)
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

-- One aligned store; a gate already running finishes its pass, later passes stay native.
function C.Disable()
    if C.block then EEex_Write32(C.block, 0) end
    return C.Status()
end

local function count(t) local n = 0; for _ in pairs(t) do n = n + 1 end; return n end

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
    for _, k in ipairs(STAT_NAMES) do counts[#counts + 1] = '"'..k..'":'..num(stats[k]) end
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
    local a = actors[sprite]
    if not a then return nil end
    return {id=a.id, frozen=a.frozen, last_frozen=a.lastFrozen, last_pass=a.lastPass, kappa=a.kappa,
        last_t=a.lastT, next_t=a.nextT, seen=a.seen, parents=count(a.parents), fresh=count(a.fresh)}
end

function C.Status()
    local out = {installed=C.installed, failed=C.failed or false, enabled=false, errors=0,
        observe=C.observe == true, sessions=C.sessions or 0, actors=count(actors),
        timed_offset=C.timedOffset, equipped_offset=C.equippedOffset, stats={},
        recorder={on=rec.on, events=rec.n, dropped=rec.dropped, watched=count(rec.ids),
            unexported=rec.dirty}}
    for _, k in ipairs(STAT_NAMES) do out.stats[k] = stats[k] end
    if C.block then
        out.enabled = EEex_Read32(C.block) == 1
        out.errors = EEex_Read32(C.block + 4)
    end
    return out
end
